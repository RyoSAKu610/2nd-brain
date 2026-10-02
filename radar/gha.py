"""GitHub Actions helpers for the free scheduled series (PAPER only, no signer).

The workflow restores the state directory from the Actions cache, runs one
``radar once`` pass, then calls these subcommands:

- ``due NAME HOURS`` / ``mark NAME``: wall-clock gates stored in the state dir,
  robust to cron delays (no minute-modulo arithmetic).
- ``maintain``: drop raw observations older than the retention window so the
  cached SQLite stays bounded. Trades and memories are never deleted.
- ``digest``: 6-hour research digest (Markdown) with only what changed since
  the previous posted digest. ``digest-commit`` records it after posting.
- ``site``: static Pages bundle (report, slim.json, org page, digest, GA).

No key material is read or written here. Everything published is derived from
the same whitelisted fields the local report already shows.
"""
import argparse
import html
import json
import math
import os
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config as settings
from .gha_snapshot import build_slim, write_slim
from .org_page import build_org_html

SCHEDULE_FILE = 'gha_schedule.json'
DIGEST_FILE = 'gha_digest.json'
DIGEST_PENDING = 'gha_digest_pending.json'
EVOLUTION_DIR = 'evolution-runs'


def iso(ts):
    try:
        value = float(ts)
    except (TypeError, ValueError):
        return '未取得'
    if not math.isfinite(value):
        return '未取得'
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds')


def _read_json(path, default):
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
    os.replace(temporary, path)


# --- schedule gates -------------------------------------------------------

def is_due(state, name, hours, now=None):
    now = time.time() if now is None else now
    last = _read_json(Path(state) / SCHEDULE_FILE, {}).get(name)
    if not isinstance(last, (int, float)) or not math.isfinite(last) or last > now:
        return True
    # 5% slack so a 6h gate does not slip to 6h15m when cron runs a little early.
    return now - last >= hours * 3600 * 0.95


def mark(state, name, now=None):
    path = Path(state) / SCHEDULE_FILE
    schedule = _read_json(path, {})
    schedule[name] = time.time() if now is None else now
    _write_json(path, schedule)


# --- maintenance ----------------------------------------------------------

def prune_observations(db_path, retention_days, now=None):
    """Delete raw observations last seen before the retention window."""
    if not isinstance(retention_days, int) or retention_days < 7:
        raise ValueError('retention_days must be an integer >= 7')
    if not Path(db_path).is_file():
        return 0
    now = time.time() if now is None else now
    cutoff = now - retention_days * 86400
    db = sqlite3.connect(db_path, timeout=30)
    try:
        with db:
            deleted = db.execute('DELETE FROM observations WHERE at < ?', (cutoff,)).rowcount
        if deleted:
            db.execute('VACUUM')
        return deleted
    finally:
        db.close()


# --- digest ---------------------------------------------------------------

def _ro(db_path):
    db = sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def _latest_evolution(state):
    reports = sorted((Path(state) / EVOLUTION_DIR / 'observed').glob('*/report.json'),
                     key=lambda p: p.stat().st_mtime)
    if not reports:
        return None
    report = _read_json(reports[-1], {})
    return {'run_id': report.get('run_id'), 'status': report.get('status'),
            'evaluated_at': report.get('evaluated_at'),
            'reasons': report.get('insufficient_reasons') or [],
            'interpretation': (report.get('holdout') or {}).get('interpretation'),
            'markdown': reports[-1].with_name('report.md')}


def _signal(status, now):
    """Traffic light for the collector itself (not for profitability)."""
    feeds = status.get('feeds') or []
    dex = [f for f in feeds if str(f.get('name', '')).startswith('dex:')]
    dex_bad = [f for f in dex if f.get('state') not in ('ok', 'ok_empty')]
    last = status.get('last_completed_tick')
    stale = not isinstance(last, (int, float)) or now - last > 3 * 3600
    if status.get('runtime_error') or stale or (dex and len(dex_bad) == len(dex)):
        return '🔴'
    if dex_bad or status.get('brain_sync_error') or status.get('clock_warning'):
        return '🟡'
    return '🟢'


def build_digest(state, pages_url='', now=None):
    """Return (markdown, marker). Only changes since the last committed digest are listed."""
    now = time.time() if now is None else now
    state = Path(state)
    status = _read_json(state / 'status.json', {})
    previous = _read_json(state / DIGEST_FILE, {})
    last_closed_at = previous.get('closed_max_at', 0)
    last_memory_at = previous.get('memory_max_at', 0)
    new_closed, new_hypotheses = [], []
    db_path = state / 'radar.sqlite3'
    if db_path.is_file():
        db = _ro(db_path)
        try:
            # Trades open in id order but close in any order, so watermark on closed_at.
            new_closed = [dict(r) for r in db.execute(
                'SELECT id,symbol,address,pnl,reason,closed_at FROM trades'
                ' WHERE closed_at IS NOT NULL AND closed_at>? ORDER BY closed_at', (last_closed_at,))]
            new_hypotheses = [dict(r) for r in db.execute(
                "SELECT content,at FROM memories WHERE kind='hypothesis' AND at>? ORDER BY at", (last_memory_at,))]
        finally:
            db.close()
    closed_max = max([last_closed_at] + [t['closed_at'] for t in new_closed])
    memory_max = max([last_memory_at] + [h['at'] for h in new_hypotheses])
    paper = status.get('paper') or {}
    cash = paper.get('cash')
    pnl = paper.get('realized_pnl')
    closed_n = len(paper.get('closed') or [])
    open_n = len(paper.get('open') or [])
    feeds = {f.get('name'): f.get('state') for f in status.get('feeds') or []}
    changed_feeds = {name: state_ for name, state_ in feeds.items()
                     if (previous.get('feeds') or {}).get(name) != state_}
    light = _signal(status, now)
    pnl_light = '🟡' if not isinstance(pnl, (int, float)) or abs(pnl) < 1e-9 else ('🟢' if pnl > 0 else '🔴')

    def money(value):
        return f'${value:.4f}' if isinstance(value, (int, float)) else '未取得'

    def delta(key, value):
        old = previous.get(key)
        if isinstance(value, (int, float)) and isinstance(old, (int, float)):
            return f'（前回比 {value - old:+.4f}）'
        return ''

    lines = [f'## {light} Radar 6時間ダイジェスト · {iso(now)}', '',
             f'{light} 収集 / {pnl_light} 紙成績 / 🟡 新規仮説{len(new_hypotheses)}件（未検証）', '',
             '| 項目 | 値 |', '|---|---|',
             f"| 最終tick | {iso(status.get('last_completed_tick'))} |",
             f'| 紙 現金 | {money(cash)}{delta("cash", cash)} |',
             f'| 紙 実現損益 | {money(pnl)}{delta("pnl", pnl)} |',
             f'| 保有 / 終了 | {open_n} / {closed_n} |',
             f"| 観測行 / 記憶イベント | {status.get('observation_rows', '未取得')} / {status.get('memory_events', '未取得')} |",
             f"| Nansen credits 日 / 月 | {(status.get('credits') or {}).get('day', 0)} / {(status.get('credits') or {}).get('month', 0)} |",
             '']
    errors = [x for x in (status.get('runtime_error'), status.get('brain_sync_error'), status.get('clock_warning')) if x]
    if errors:
        lines += ['**要確認:** ' + ' / '.join(str(e) for e in errors), '']
    if new_closed:
        lines += ['### 終了した紙取引（新規）', '', '| 銘柄 | 損益 | 理由 | 終了 |', '|---|---:|---|---|']
        lines += [f"| {t['symbol'] or t['address'][:8]} | {money(t['pnl'])} | {t['reason']} | {iso(t['closed_at'])} |"
                  for t in new_closed[:20]]
        lines.append('')
    if new_hypotheses:
        lines += ['### 新規候補（仮説・未検証）', '']
        lines += ['- ' + h['content'] for h in new_hypotheses[:10]]
        lines.append('')
    if changed_feeds:
        lines += ['### データ接続の状態変化', '']
        lines += [f'- `{name}`: {state_}' for name, state_ in sorted(changed_feeds.items())]
        lines.append('')
    evolution = _latest_evolution(state)
    if evolution and evolution.get('run_id') != previous.get('evolution_run'):
        lines += ['### GA実験（研究用・自動適用なし）', '',
                  f"- `{evolution['run_id']}`: **{evolution['status']}**（{evolution['evaluated_at']}）"]
        lines += ['  - ' + str(r) for r in evolution['reasons'][:5]]
        if evolution.get('interpretation'):
            lines.append('  - ' + evolution['interpretation'])
        lines.append('')
    if not (new_closed or new_hypotheses or changed_feeds or errors):
        lines += ['前回から新しい終了取引・候補・接続変化はありません。', '']
    if pages_url:
        lines += [f'ダッシュボード: {pages_url}', '']
    lines += ['_PAPERのみ・実売買なし。GitHub Actions間欠系列（約15分毎）で、Mac常駐の連続系列とは比較しない。'
              '得点はルール通過であり利益・売却可能性を保証しない。_']
    marker = {'at': now, 'closed_max_at': closed_max, 'memory_max_at': memory_max, 'feeds': feeds,
              'cash': cash, 'pnl': pnl,
              'evolution_run': evolution.get('run_id') if evolution else previous.get('evolution_run')}
    return '\n'.join(lines) + '\n', marker


def write_digest(state, out, pages_url=''):
    markdown, marker = build_digest(state, pages_url)
    Path(out).write_text(markdown)
    _write_json(Path(state) / DIGEST_PENDING, marker)
    return markdown


def commit_digest(state):
    pending = Path(state) / DIGEST_PENDING
    if not pending.exists():
        raise ValueError('No pending digest to commit')
    os.replace(pending, Path(state) / DIGEST_FILE)


# --- Pages site -----------------------------------------------------------

def _pre_page(title, text):
    return (f'<!doctype html><html lang="ja"><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
            '<style>body{background:#111722;color:#e4e9f2;font:15px/1.7 system-ui;margin:0;padding:24px}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;max-width:1100px;margin:auto}a{color:#95cfff}</style>'
            f'<pre>{html.escape(text)}</pre><p style="text-align:center"><a href="index.html">ダッシュボードへ戻る</a></p></html>')


def build_site(state, config_path, out):
    state, out = Path(state), Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / '.nojekyll').write_text('')
    config = settings.load(config_path)
    report = state / 'report.html'
    if report.exists():
        shutil.copyfile(report, out / 'index.html')
    else:
        (out / 'index.html').write_text(_pre_page('Radar', 'まだ収集結果がありません。次の定期実行を待ってください。'))
    if (state / 'status.json').exists():
        # Wallet watchlist stays private to the state cache.
        status = _read_json(state / 'status.json', {})
        status.pop('wallets', None)
        _write_json(out / 'status.json', status)
    db = state / 'radar.sqlite3'
    if db.exists():
        slim = build_slim(db, config)
        write_slim(slim, out / 'slim.json')
        (out / 'org.html').write_text(build_org_html(slim))
    digest = state / 'last_digest.md'
    (out / 'digest.html').write_text(_pre_page(
        'Radar digest', digest.read_text() if digest.exists() else '最初の6時間ダイジェストはまだ作成されていません。'))
    evolution = _latest_evolution(state)
    text = evolution['markdown'].read_text() if evolution and evolution['markdown'].exists() else \
        'GA実験はまだ実行されていません（週1回・データ不足の間は insufficient_data で停止）。'
    (out / 'evolution.html').write_text(_pre_page('GA experiment', text))
    return sorted(p.name for p in out.iterdir())


def main(argv=None):
    parser = argparse.ArgumentParser(description='GitHub Actions helpers for the PAPER radar')
    parser.add_argument('--state', type=Path, default=Path('.gha_state'))
    sub = parser.add_subparsers(dest='command', required=True)
    due = sub.add_parser('due')
    due.add_argument('name')
    due.add_argument('hours', type=float)
    sub.add_parser('mark').add_argument('name')
    maintain = sub.add_parser('maintain')
    maintain.add_argument('--retention-days', type=int, default=30)
    digest = sub.add_parser('digest')
    digest.add_argument('--out', type=Path, required=True)
    digest.add_argument('--pages-url', default='')
    sub.add_parser('digest-commit')
    site = sub.add_parser('site')
    site.add_argument('--config', type=Path, required=True)
    site.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'due':
        print('true' if is_due(args.state, args.name, args.hours) else 'false')
    elif args.command == 'mark':
        mark(args.state, args.name)
    elif args.command == 'maintain':
        if is_due(args.state, 'maintain', 24):
            deleted = prune_observations(args.state / 'radar.sqlite3', args.retention_days)
            mark(args.state, 'maintain')
            print(json.dumps({'pruned_observations': deleted, 'retention_days': args.retention_days}))
        else:
            print(json.dumps({'pruned_observations': 0, 'skipped': 'not_due'}))
    elif args.command == 'digest':
        markdown = write_digest(args.state, args.out, args.pages_url)
        shutil.copyfile(args.out, args.state / 'last_digest.md')
        print(markdown)
    elif args.command == 'digest-commit':
        commit_digest(args.state)
    elif args.command == 'site':
        print(json.dumps({'site': str(args.out), 'files': build_site(args.state, args.config, args.out)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
