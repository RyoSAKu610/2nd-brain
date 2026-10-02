"""Offline end-to-end checks for the GitHub Actions scheduled series."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from radar import gha
from radar.config import load
from radar.report import render
from radar.runner import Radar

ROOT = Path(__file__).resolve().parent.parent
GHA_CONFIG = ROOT / 'radar' / 'config.gha.json'
ADDRESS = 'So11111111111111111111111111111111111111112'
POOL = '11111111111111111111111111111111'


def pair(price):
    return {'chainId': 'solana', 'baseToken': {'address': ADDRESS, 'symbol': 'TEST'},
            'pairAddress': POOL, 'priceUsd': str(price), 'liquidity': {'usd': 100000},
            'volume': {'m5': 10000}, 'txns': {'m5': {'buys': 40, 'sells': 10}},
            'priceChange': {'m5': 10}, 'pairCreatedAt': 1600000000000}


class FakeDex:
    def __init__(self):
        self.price = 1.0
        self.calls = []

    def __call__(self, url, payload=None, key=None):
        self.calls.append(url)
        if 'nansen' in url:
            raise AssertionError('Nansen must not be called without a key')
        if url.endswith('/token-profiles/latest/v1'):
            return [{'chainId': 'solana', 'tokenAddress': ADDRESS}], {}
        return [pair(self.price)], {}


class GhaSeriesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name) / 'state'
        self.now = 1790000000.0
        self.dex = FakeDex()

    def tearDown(self):
        self.temp.cleanup()

    def run_once(self):
        """One scheduled job: fresh process, state restored from the previous run."""
        radar = Radar(self.state, GHA_CONFIG, http=self.dex, now=lambda: self.now)
        try:
            config = radar.tick()
            return render(self.state, radar.store, config)
        finally:
            radar.close()

    def test_config_is_paper_and_fetches_every_run(self):
        config = load(GHA_CONFIG)
        self.assertEqual((config['mode'], config['chain']), ('paper', 'solana'))
        self.assertEqual(config['key_file'], '')
        # A run can start <15 min after the previous one; quotes/profiles must still be due.
        self.assertLessEqual(config['loop_seconds'], 60)
        self.assertLessEqual(config['discovery_interval_seconds'], 60)
        self.assertTrue(config['brain_sync'])

    def test_state_persists_across_runs_and_digest_reports_only_changes(self):
        data = self.run_once()
        self.assertEqual(len(data['paper']['open']), 1)
        quote_calls = [c for c in self.dex.calls if '/tokens/v1/solana/' in c]
        self.assertEqual(len(quote_calls), 1)

        markdown, marker = gha.build_digest(self.state, 'https://example.invalid/', now=self.now)
        self.assertIn('新規候補（仮説・未検証）', markdown)
        self.assertNotIn('終了した紙取引', markdown)
        gha.write_digest(self.state, Path(self.temp.name) / 'd.md')
        gha.commit_digest(self.state)

        # 15 minutes later in a new process: price +50% hits take-profit.
        self.now += 900
        self.dex.price = 1.5
        data = self.run_once()
        self.assertEqual(len(data['paper']['closed']), 1)
        self.assertEqual(data['paper']['closed'][0]['reason'], 'take_profit')
        self.assertEqual(len([c for c in self.dex.calls if '/tokens/v1/solana/' in c]), 2)

        markdown, _ = gha.build_digest(self.state, now=self.now)
        self.assertIn('終了した紙取引（新規）', markdown)
        self.assertIn('take_profit', markdown)
        self.assertNotIn('新規候補（仮説・未検証）', markdown)  # same-day candidate already reported

        # Brain memory lives in the cached state and received the ledger fact.
        brain = sqlite3.connect(self.state / 'memory.sqlite3')
        try:
            kinds = {row[0] for row in brain.execute('SELECT kind FROM memories')}
        finally:
            brain.close()
        self.assertTrue({'fact', 'hypothesis'} <= kinds)

    def test_digest_commit_requires_pending(self):
        self.state.mkdir(parents=True)
        with self.assertRaises(ValueError):
            gha.commit_digest(self.state)

    def test_schedule_gates(self):
        self.assertTrue(gha.is_due(self.state, 'digest', 6, now=self.now))
        gha.mark(self.state, 'digest', now=self.now)
        self.assertFalse(gha.is_due(self.state, 'digest', 6, now=self.now + 3600))
        self.assertTrue(gha.is_due(self.state, 'digest', 6, now=self.now + 6 * 3600 - 600))
        # A future timestamp (clock skew / corrupt file) never blocks forever.
        gha.mark(self.state, 'digest', now=self.now + 10 ** 6)
        self.assertTrue(gha.is_due(self.state, 'digest', 6, now=self.now))

    def test_prune_keeps_recent_observations_trades_and_memories(self):
        self.run_once()
        self.now += 40 * 86400
        self.dex.price = 0.5  # distinct payload; identical payloads only refresh the old row
        self.run_once()
        db = sqlite3.connect(self.state / 'radar.sqlite3')
        try:
            before = db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
            trades = db.execute('SELECT COUNT(*) FROM trades').fetchone()[0]
        finally:
            db.close()
        deleted = gha.prune_observations(self.state / 'radar.sqlite3', 30, now=self.now)
        self.assertGreater(deleted, 0)
        db = sqlite3.connect(self.state / 'radar.sqlite3')
        try:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0], before - deleted)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM trades').fetchone()[0], trades)
            self.assertGreater(db.execute('SELECT COUNT(*) FROM memories').fetchone()[0], 0)
        finally:
            db.close()
        with self.assertRaises(ValueError):
            gha.prune_observations(self.state / 'radar.sqlite3', 3)

    def test_site_bundle_has_pages_and_no_wallets(self):
        self.run_once()
        out = Path(self.temp.name) / '_site'
        files = gha.build_site(self.state, GHA_CONFIG, out)
        for name in ('index.html', 'status.json', 'slim.json', 'org.html', 'digest.html', 'evolution.html', '.nojekyll'):
            self.assertIn(name, files)
        status = json.loads((out / 'status.json').read_text())
        self.assertNotIn('wallets', status)
        index = (out / 'index.html').read_text()
        self.assertIn('GitHub Actions 約15分毎', index)
        self.assertIn('digest.html', index)
        for path in out.iterdir():
            self.assertLess(path.stat().st_size, 1_048_576)

    def test_site_before_first_run(self):
        out = Path(self.temp.name) / '_site'
        files = gha.build_site(self.state, GHA_CONFIG, out)
        self.assertIn('index.html', files)
        self.assertNotIn('slim.json', files)


if __name__ == '__main__':
    unittest.main()
