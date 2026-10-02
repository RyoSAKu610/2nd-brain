@AGENTS.md

# Claude Code 向けメモ

## 構成

| パス | 役割 |
|---|---|
| `brain.py` | 第2の脳の記憶CLI（SQLite・標準ライブラリのみ） |
| `radar/` | Solana PAPER監視。`gha.py` がGitHub Actions用の補助（予定判定・剪定・ダイジェスト・Pages生成） |
| `evolution/` | DEAPによるオフライン条件探索（研究用・自動適用なし） |
| `.github/workflows/radar.yml` | 約15分毎の定期実行。状態はActions cache（`radar-state-*`）＋6時間毎のbackup artifact |
| `.github/workflows/ci.yml` | PRでのテスト（3.11/3.14）＋実DEXへの1巡スモーク |
| `prompts/` | 共通規約と専門モジュール |

## よく使うコマンド

```sh
python3 -m unittest discover -s tests          # 全テスト（GAはdeap未導入ならskip）
python3 brain.py context "Solana" --module analysis
python3 -m radar --state .gha_state --config radar/config.gha.json once   # 手元で1巡
python3 -m radar.gha --state .gha_state digest --out /tmp/digest.md
python3 -m radar.gha --state .gha_state site --config radar/config.gha.json --out _site
```

## 稼働データの読み方

- 公開ダッシュボード: `https://ryosaku610.github.io/2nd-brain/`（`status.json`・`slim.json`・`digest.html`・`evolution.html`）。
- 6時間ダイジェスト: ラベル `radar-digest` の Issue へのコメント。
- 稼働DB（`radar.sqlite3`・`memory.sqlite3`）はActions cache内にあり、リポジトリには置かない。手元で調べるときは backup artifact `radar-state-backup` を取得する。
- この開発コンテナからは DexScreener へ直接接続できない場合がある。実データの確認はActionsの実行結果とPagesで行う。

## 変更時の注意

- `radar/runner.py` / `radar/feeds.py` を変えるとGA実験の再現hashが変わり、別実験として扱われる。
- `radar/config.gha.json` の売買閾値・資金を変えると紙系列の比較性が切れる。変更はユーザー承認を得て、ダイジェストで明示する。
- 公開リポジトリのため、Pagesやartifactに出す内容へ秘密値・ウォレット一覧を含めない（`gha.build_site` は `wallets` を除外する）。
