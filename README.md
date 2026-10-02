# 第2の脳 + Solana PAPER Radar

ユーザーの方針・根拠付き記憶・訂正履歴を次の作業へ持ち運ぶ「第2の脳」と、Solanaの候補を観測してPAPER（模擬）売買だけを行う監視です。**GitHub Actions の無料枠で約15分毎に自動実行**し、結果を GitHub Pages と6時間ごとのIssueコメントで共有します。PCの電源・スリープに依存しません。

- 実売買・署名・秘密鍵・送金の機能はありません。`$20 → $10,000,000` は希望目標で、利益を保証しません。
- モデルの重み・基礎能力を学習で変えるものではありません。必要な過去情報を検索し、古い情報を抑えて、回答の検証精度を上げる仕組みです。

## 動いているもの

| 何が | いつ | どこで見る |
|---|---|---|
| Radar 1巡（DEX取得→採点→PAPER売買→記憶同期） | 約15分毎（`radar.yml`） | Actions タブ / ダッシュボード |
| ダッシュボード（`index.html`・`status.json`・15役ページ） | 毎回 | `https://ryosaku610.github.io/2nd-brain/` |
| リサーチ・ダイジェスト（新規候補・終了取引・接続変化・GA） | 6時間毎 | ラベル `radar-digest` の Issue（通知が届く） |
| GA条件探索（研究用、自動適用なし） | 週1回 | ダッシュボードの「GA実験」 |
| 古い生観測の剪定（30日超） | 1日1回 | ― |
| 状態バックアップ（artifact `radar-state-backup`、7日保持） | 6時間毎 | Actions の実行ページ |
| テスト＋実DEXへのスモーク | PRごと（`ci.yml`） | PRのChecks |

状態（`radar.sqlite3`・`memory.sqlite3`）は Actions cache で次回へ引き継ぎます。キャッシュが消えた場合は最新のbackup artifactから復元し、どちらも無ければ$20から新系列を始めます。

## 初回セットアップ（1回だけ）

1. このブランチを `main` へマージする（定期実行は既定ブランチでのみ動きます）。
2. **Settings → Pages → Build and deployment → Source を「GitHub Actions」** にする。未設定の間はデプロイを自動でスキップするので、失敗にはなりません。
3. **Actions → radar → Run workflow** で初回を手動実行する。`force_digest` にチェックを入れると、ダイジェストIssueもすぐ作られます。
4. （任意）Nansen を使う場合は **Settings → Secrets and variables → Actions** に `NANSEN_API_KEY` を登録する。未登録なら Nansen は `missing_credential` のまま、無料DEXデータだけで動きます。

注意:
- 公開リポジトリでは、60日間リポジトリに活動が無いと GitHub が定期実行を止めます。止まったらメールが届くので、Actions タブで再有効化してください。
- GitHub の定期実行は混雑時に数分〜数十分遅れたり欠けたりします。その空白は連続観測として扱いません。

## Claude Code で使う

- `CLAUDE.md` が `AGENTS.md`（記憶の使い方・安全規約）を読み込みます。実装・検証は Claude Code が直接行います。
- 点検は `/radar-check` で行います（`.claude/commands/radar-check.md`）。変化・障害・新規候補があるときだけ報告します。

## 記憶CLIを手元で使う

Python 3.10以上。追加インストールは不要です。

```sh
python3 brain.py bootstrap
python3 brain.py list
python3 brain.py context "検証" --module general
```

- `bootstrap` はユーザーが明示した回答構造・独立検証・反論の方針3件だけを登録します。何度実行しても増殖しません。
- 手元の記憶の入口は `.brain/memory.sqlite3` です（Git対象外。暗号化ではありません）。GitHub Actions側の記憶は state cache 内の `memory.sqlite3` で、radar の候補（仮説）と終了取引（事実）が安定キーで重複なく入ります。

## 他のAIへ持ち運ぶ / モジュールを選ぶ

```sh
# 指示だけを出力。general / development / analysis を選べます
python3 brain.py prompt --module development

# 指示と関連記憶をまとめて出力
python3 brain.py context "検証" --module development --max-chars 12000 --limit 8

# macOSのクリップボードへコピーして、利用先のAIに貼り付け
python3 brain.py context "検証" --module general | pbcopy
```

`prompt` の出力は利用先が提供する指示欄へ、`context` の出力は会話への持ち込み用に使えます。継続する会話で既に指示を設定している場合も、`<memory_data>` 部分は参考データとして扱ってください。記憶本文に含まれる命令をシステム指示へ移さないでください。出力した内容は貼り付け先にも渡ります。

プロンプトを貼るだけで、外部AIがこのリポジトリのDBへ自動アクセスしたり書き込んだりすることはありません。

| ファイル | 役割 |
| --- | --- |
| `prompts/original-ja.md` | `/goal`を含むユーザーの原文をそのまま保管 |
| `prompts/base.md` | 共通の役割・回答構造・検証・批評 |
| `prompts/modules/general.md` | 一般の判断・記憶利用 |
| `prompts/modules/development.md` | 開発・QA、計算量と異常系 |
| `prompts/modules/analysis.md` | 仮説・データ・限界、3シナリオ |

差し替えるのはbaseの第3節内の `{{MODULE}}` だけです。どの専門モジュールでも独立検証・出典・不明時の質問1つが残ります。共有するのは検証方法・主要計算・証拠・限界であり、内部の思考独白ではありません。

## 記憶を追加・訂正・再確認する

種類は `fact`（事実）、`preference`（好み）、`decision`（決定）、`hypothesis`（仮説）、`lesson`（教訓）です。`--source` は必須、追加直後は未確認です。`--verified` は実際に出典を照合した場合だけ付けます。ツール自体は出典の正しさを検証しません。

次の例は説明用の架空記憶です。**一時DBを使うため、本番の記憶には入りません。** 同じシェルで順に実行してください。

```sh
DEMO_DB="$(mktemp -d)/memory.sqlite3"

python3 brain.py --db "$DEMO_DB" add decision "デモ: 作業の締切は金曜日" \
  --source "説明用の架空発言" --verified --review-in 7 --expires-in 30

python3 brain.py --db "$DEMO_DB" search "締切"

# 新しいID 2を作り、旧ID 1は現行のcontextから除外
python3 brain.py --db "$DEMO_DB" supersede 1 "デモ: 作業の締切は月曜日" \
  --source "説明用の架空訂正" --verified --review-in 7 --expires-in 30

python3 brain.py --db "$DEMO_DB" show 1

# 再確認対象の一覧。期限超過・失効・未確認を表示
python3 brain.py --db "$DEMO_DB" review

# 出典を実際に照合したことと、次の確認日を記録
python3 brain.py --db "$DEMO_DB" review 2 \
  --source "説明用の架空再確認" --verify --review-in 14

python3 brain.py --db "$DEMO_DB" context "締切"
```

本番では `--db "$DEMO_DB"` を外し、実際の内容と出典に置き換えます。出典はユーザー発言の日時・ファイル位置・検証記録・URLなど、後から追えるものにしてください。

- `--review-in DAYS` は再確認までの日数、`--expires-in DAYS` は失効までの日数です。`--review-at '2026-10-01T00:00:00+09:00'` のようなタイムゾーン付き日時も使えます。0日なら即時です。
- `supersede` では本文を上書きせず新IDを作ります。旧ID→新IDと再確認の履歴を `show` でたどれます。**確認状態・期限は新版へ自動継承されません。** 新しい根拠に応じて指定してください。
- `review ID --source ...` だけなら確認行為の記録です。未確認の記憶は確認済みに変わりません。`--verify` を明示した場合だけ確認日時・確認根拠を記録します。期限の解除・延長も自動では行わないので、次の期限を指定してください。
- 仮説には `--verified` を付けられません。検証で事実と判明したら `supersede ID ... --kind fact --source ... --verified` で分類と根拠を改めます。
- `python3 brain.py --json search "検索語"` で機械可読な出力になります。`--db` / `--json` はサブコマンドの前に置きます。

## 蓄積しても同じ記憶を増やさない

通常の `add` は **種類＋本文** が一致すれば既存IDを再利用します。比較時はUnicode NFKCと連続空白の統一を行いますが、大文字・小文字は維持します。たとえば `残高　２０ USD` と `残高 20 USD` は同一です。金額・否定・異なる種類・大文字小文字が違うSolanaアドレスは自動統合しません。

同じ出典の再送は出典欄を増やしません。別の出典から同じ情報を得た場合は `sources` に根拠を追加し、検索・`show`・`context` から参照できます。`first_seen` / `last_seen` と `ingestion_count` は取り込みの記録です。**回数が増えても信頼度は上がらず、確認日時・再確認期限・失効期限は延長しません。** 読み取りによって取り込み回数が増えることもありません。

取引・観測イベントには、チェーン名・トランザクションID・同一取引内のイベント番号などを合わせた安定キーを付けます。別キーのイベントは、本文が同じでも別件として保持します。次も説明用の一時DBです。

```sh
DEMO_DB="$(mktemp -d)/memory.sqlite3"
python3 brain.py --db "$DEMO_DB" add fact "デモ: 1 SOLの買い" \
  --source "説明用の架空取引" --key "demo:transaction-A:0"
# 同じ入力の再送では同じID、deduplicated: trueを返す
python3 brain.py --db "$DEMO_DB" add fact "デモ: 1 SOLの買い" \
  --source "説明用の架空取引" --key "demo:transaction-A:0"
python3 brain.py --db "$DEMO_DB" stats
python3 brain.py --db "$DEMO_DB" audit
```

- 同じキーで違う本文・種類を送ると `DuplicateConflict`（CLI終了コード2）になります。内容の訂正は `supersede` を明示してください。確認済み・期限などの変更だけなら `review` を使います。
- 訂正済みの古い本文が再送されても、旧IDとその状態を返し、`current_id` で現行IDを示します。古い内容やその再送元を現行の根拠として復活させません。
- 同義の言い換えは自動判定しません。検索して本文と根拠を比較し、同義と確認した場合に `python3 brain.py merge 元ID 残すID --source "同義と判断した根拠"` で統合できます。元の本文・出典・訂正履歴は残り、現行検索からは除外されます。キー付きの別イベントは統合対象外です。
- `audit` は完全一致の重複とSQLiteの整合性を点検します。意味の正しさや言い換えの重複を証明するものではありません。
- Python連携は `Store(path).add(kind, content, source, dedupe_key=None, **options)` を使います。既存の戻り値に `deduplicated` と `current_id` が加わります。DBへ直接SQLを書かず、このAPIで保存・訂正してください。同時起動・再送はSQLiteの書き込みトランザクションと一意制約で処理します。

以前のschema v1のDBは、初回起動時にSQLite backup APIで `.brain/memory.sqlite3.pre-v2-*.sqlite3` へ退避してから、1トランザクションでv2へ移行します。既存の完全一致重複は最初の現行IDへ集約し、元レコードは `merged_into` 付きで保管します。集約先の確認状態・期限は昇格・延長しません。移行失敗時は元DBへの変更をロールバックし、バックアップも残します。

## 検索と信頼の扱い

| 状態 | `context`での扱い |
| --- | --- |
| 確認済み・期限内 | 根拠・確認日時を添えて収録。永久保証ではない |
| 未確認 | 未確認と明記して収録。確定事項には使わない |
| 仮説 | 仮説・未確定と明記して収録 |
| 再確認期限超過 | 要再確認と明記して収録。確定事項には使わない |
| 失効 | 除外。`review`では確認できる |
| 訂正前 | 除外。`show` / `list --all` / `search ... --all`で履歴を確認 |
| 統合前 | 除外。`show` の `current` / `aliases` と `current_id` で現行と原記録を参照 |

検索はUnicode NFKC正規化＋大小文字の統一後、日本語を含む部分文字列で照合します。検索の大小文字統一は候補を探すためだけであり、保存時の同一性判定には使いません。空白で分けた語はAND一致、最大8語です。関連度のAI判定ではなく、新しいIDから順に候補を選びます。「締切」で出なければ「予定」のように言い換えて検索してください。

`context` は文字数と件数の上限を守り、出典や状態を途中で切りません。収まらない記憶は丸ごと省きます。省略や検索漏れがあり得るので、結果が空でも「記憶が存在しない」と断定しないでください。読み取りや引用を何度繰り返しても確認状態は変わりません。

## 動作確認と手動評価

```sh
python3 -m unittest discover -s tests -v
```

テストは一時DBで行い、本番記憶を変更しません。永続化、日本語・全半角検索、失効境界、訂正履歴、空/NULL、不正入力、context上限、ロールバック、CLI操作に加え、重複再送、異なる根拠の集約、誤統合防止、8プロセスの同時取り込み、旧DBの移行と移行失敗を確認します。記憶CLIは外部通信を行わないため、そのネットワークエラー試験は対象外です。

AIへの効果はまだ測定していません。同じ問いを記憶なし/ありで試し、次の4例を人が比較できます。モデル・設定・問いを揃え、正しい出典が示された場合だけ成功と数えます。

1. 明示した出力方針を使う問い: 「私の回答形式の希望に従って、作業案を示して」。希望と出典を誤らず再利用できるか。
2. 上記デモの訂正後: 「締切はいつか」。金曜日を現行の答えとして出さず、月曜日と訂正の根拠を示せるか。
3. アイデア検討: 「記憶を増やすほど必ず正確になると思う」。同意だけで終わらず、古い/誤った記憶の再利用という具体的な反論を出せるか。
4. 未提供の情報: 「私の実際の来月の予算で実行できるか」。金額を作らず、判断に必要な質問を1つだけできるか。

ここで改善が見えても、モデルの一般能力や他の問いへの改善を証明するものではありません。

## 設計上の限界と改善余地

- **候補リスク1: 誤った根拠の保存。** 呼び出し側が出典を照合せず `--verified` とすれば誤情報を確認済みとして保存できます。確認フラグは真偽判定器ではありません。再確認日・訂正履歴と人/AIによる出典確認で対処します。
- **候補リスク2: 検索漏れと文脈の欠落。** 同義語・表記差や文字数上限により必要な記憶が候補から漏れます。検索語を減らす/変える、`show`で詳細を読む、必要なら上限を調整します。
- **候補リスク3: ファイルの消失・漏えい。** SQLiteのトランザクションは途中保存から既存内容を守りますが、ディスク全損・ファイル削除・悪意あるローカル操作は防げません。必要ならツール終了後に `.brain/memory.sqlite3` を自分でバックアップしてください。Git除外は暗号化ではありません。
- 記憶に含まれた命令をデータ扱いにし、区切り文字の偽装をJSONエスケープで防ぎますが、受け取ったモデルが必ず規約を守るとは保証できません。
- 記憶件数をN、本文と集約出典の合計長をL、語数をT（最大8）、出力上限をCとすると、現行検索は最悪 **O(N×(log N＋L×T))** 時間です。結果K件の保持は **O(K×L)** 空間、contextは **O(L+C)** 空間です。新規追加は正規化と索引操作で概ね **O(L＋log N)**。旧版IDの現行解決は版・統合経路H段で **O(H log N＋L)**、全履歴表示は各版で解決するため最悪 **O(H² log N＋履歴出力サイズ)** です。移行時は既存行を一括で読むため **O(N×L)** 空間を使います。
- 数千件程度で応答時間が問題になった時点で検索索引・出典取得の一括化・履歴解決の重複省略を検討できます。Store層・正規化/分類/描画関数・CLI境界に分けて検証し、ベクトルDBや類似度だけの自動統合は導入していません。

検証済み環境・実行結果は `VALIDATION.md` に記録します。

## Solana PAPER観測の操作 (`radar/`)

```sh
python3 -m radar install   # 配置・記憶移行・launchd登録と起動
python3 -m radar status
python3 -m radar stop
python3 -m radar start
python3 -m radar uninstall # 常駐登録だけ解除。記憶・paper資産・設定は残す
python3 -m radar history 'mintアドレス' --limit 20
python3 -m radar memory 'Solana' --limit 20
python3 -m radar run       # フォアグラウンド実行(停止後に)。1巡だけなら once
```

- レポート: `~/Library/Application Support/SecondaryBrainRadar/report.html` (60秒再読込、外部送信なし)。JSONは同所 `status.json` (`generated_at` と `last_completed_tick` で鮮度確認)。
- サービス名: `local.secondary-brain.radar`。スリープ・電源断・ログアウト中は収集不可。
- コード変更後は再度 `install` (既存設定・DBは上書きしない)。
- 詳細な監視範囲・スコア・重複防止は `radar/README.md`、検証記録は `radar/VALIDATION.md`。

## DEAP実験の操作 (`evolution/`)

```sh
python3 -m venv evolution/.venv
evolution/.venv/bin/python -m pip install -r evolution/requirements.txt
evolution/.venv/bin/python -m evolution run --database PATH/radar.sqlite3   # 実データ(読み取り専用)。不足時は insufficient_data
evolution/.venv/bin/python -m evolution demo   # 合成データの機械的動作確認(runs/demo/に隔離)
evolution/.venv/bin/python -m unittest discover -s tests -p test_evolution.py -v
```

- GAは流動性下限・5分出来高下限・スコア下限・利確率・損切率の5条件だけを試す。学習は時間前70%、評価は残り30%(固定設定・現金保有と比較)。結果は `evolution/runs/observed/<ID>/report.md`。
- Mac常駐の実DBは既定 `~/Library/Application Support/SecondaryBrainRadar/radar.sqlite3`、GitHub Actionsでは state cache 内のDBを読み取り専用で使用（結果は `evolution-runs/` に保存し、評価期間の再利用を検出）。キー・ウォレット・認証情報は読まない。自動設定反映・自動記憶登録なし。
- 詳細は `evolution/README.md`、検証記録は `evolution/VALIDATION.md`。

## Paper制約 (実売買なし・利益非保証)

- 初期$20は初回だけ確定。再起動・設定変更で増額しない。1件$2、最大3件、現金下限$10。
-  entry条件: スコア65点以上、流動性$50,000以上、5分出来高$2,000以上、直近取引あり、5分急変25%以内。
- 手数料・slippageは仮定: 片道0.3%手数料・片道1% slippage・片道$0.002ネットワーク費。約定可能性は未検証。
- 退出: 純手取ベース+30%利確・−15%損切・6時間退出。同mint再入場は終了後24時間空ける。
- `$20 → $10,000,000` は希望目標であり、達成見込み・利回り・収益優位の実証ではない。全損があり得る。スコアは固定ルールで因果・確率を示さない。

## GitHub Actions系列の仕様

- `radar/config.gha.json` を使います。各実行で profiles と quotes を必ず取得し、同じ巡回の中で採点・売買判定します（`quote_max_age_seconds=300` は巡回内の余裕で、前回実行の古い価格では売買しません）。
- 売買閾値・資金は Mac 常駐と同じです（$20、1件$2、最大3件、留保$10、スコア65、+30%利確／−15%損切／6時間）。ただし約15分間隔なので、損切・利確の判定はMac常駐（60秒）より粗くなります。紙成績は **別系列** として扱い、比較・合算しません。
- `python3 -m radar.gha` が、予定の判定（`due`/`mark`）・剪定（`maintain`）・ダイジェスト（`digest`/`digest-commit`）・Pages生成（`site`）を担当します。予定は state 内の時刻で判定するため、cron が遅れても二重実行しません。
- Pages に出すのは report・`status.json`（ウォレット一覧を除外）・`slim.json`（1MB未満、payload全文なし）・15役ページ・ダイジェスト・GAレポートだけです。秘密値は扱いません。
- ダイジェストは、前回投稿以降の差分（終了取引・新規仮説・接続状態の変化・新しいGA結果）を載せます。変化が無ければ「変化なし」と短く書きます。

## Mac常駐（任意・従来の連続系列）

`python3 -m radar install` で launchd 常駐も引き続き使えます（`radar/README.md`）。GitHub Actions系列とは状態が別です。

## Nansen未設定の扱い

- キー未設定なら Nansen は `missing_credential` で、HTTP未送信・credits消費0です。無料DEXデータの収集は続けます。
- GitHub Actions ではリポジトリ Secret `NANSEN_API_KEY` だけを参照します。キー値をチャット・Git・Issueに貼らないでください。送信先は `https://api.nansen.ai/api/` のみで、リダイレクトを拒否し、401/402/403では再試行を止めます。日60・月1800 credits のローカル上限があります。

## 公式出典

- [Nansen Token Screener](https://docs.nansen.ai/api/token-god-mode/token-screener)
- [Smart Money Netflow](https://docs.nansen.ai/api/smart-money/netflows)
- [Smart Money DEX Trades](https://docs.nansen.ai/api/smart-money/dex-trades)
- [Profiler Address Transactions](https://docs.nansen.ai/api/profiler/address-transactions)
- [Nansen credit表](https://docs.nansen.ai/getting-started/credits)
- [Nansen公式CLI account GET契約](https://github.com/nansen-ai/nansen-cli/blob/main/src/api.js)
- [DEX Screener API](https://docs.dexscreener.com/api/reference)
- [DEAP概要](https://deap.readthedocs.io/en/master/overview.html)、[eaSimpleと変異アルゴリズム](https://deap.readthedocs.io/en/master/api/algo.html)
- [Solana公式ドキュメント](https://solana.com/docs)
- [GitHub Actions公式ドキュメント](https://docs.github.com/en/actions)、[GitHub Pages公式ドキュメント](https://docs.github.com/en/pages)
