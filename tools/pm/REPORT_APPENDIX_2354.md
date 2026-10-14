# tools/pm 付録: REPORT §11 の全文 (idle_report.sh の検証 #2354)

> **REPORT の付録**: `tools/pm/REPORT.md` §11 の全文 (250 行上限のため無変更で分割移動)。測定値の正本はこの付録。

## 11. `idle_report.sh` の検証 (#2354・watchdog の担当なし時間の集計)

既知類型との関係: 該当なし (lift の欠陥ではなく PM 運用ツール)。使い方と数え方の定義は [`README.md`](README.md) の `idle_report.sh` の節。

- 測定 commit: `95b501b2` (コードを変えた最後の commit)。それ以降の `tools/pm/idle_report.sh` `tools/pm/test_idle_report.sh` の差分: `git diff 95b501b2 HEAD -- tools/pm/idle_report.sh tools/pm/test_idle_report.sh` の出力は 0 行。`f10dfd36` から `95b501b2` までの変更は説明文 (コメント・README) だけ (`git diff f10dfd36 95b501b2 -- tools/pm/idle_report.sh tools/pm/test_idle_report.sh` の非コメント行は 0 行)。
- 環境: runner (4 コア)。load average は各測定の直後の `/proc/loadavg` の 1 分値。

### 11-1. fake gh のテスト (`bash tools/pm/test_idle_report.sh`)

| 項目 | 結果 |
|---|---|
| 判定数 | 41 件中 41 PASS・0 FAIL (3 回とも同じ) |
| 所要 (n=3、95b501b2) | 7.3〜7.6 秒 (load 0.24〜0.28) |
| (a) idle=0 が 10 標本 | 0 回 |
| (b) idle>0 が 14 分 (ネガコン) | 0 回 (区間 14 分)。`--threshold-min 14` なら 1 回 |
| (b2) idle>0 がちょうど 15 分 | 1 回 (境界は数える) |
| (c) idle>0 が 16 分 | 1 回 (区間 16 分・標本 9 件・最大 idle=3) |
| (d) idle=0 を挟む | 16 分 + 0 + 16 分 → 2 回。10 分 + 0 + 10 分 → 0 回 (区間 2 つ、合算しない) |
| (e) `X-Ratelimit-Remaining` | 1,499 → 終了コード 3・標準エラーに `X-Ratelimit-Remaining=1499`・JSON は出さない。1,500 → 続行。jobs 応答だけ 1,499 でも中断 |
| 全ページ・窓の分割 | `per_page=2`・窓 1 時間で、窓の境界をまたぐ 20 分の区間を 1 回・標本 6 件 (欠落・重複なし)・`page=2` を取得 |
| 窓の上限 | `total_count` が 1,000 超 → 終了コード 4 |
| REST のみ | gh の呼び出しは全て `api <path>`。graphql の呼び出し 0 件 (fake gh は graphql を exit 99 にする) |

ネガコン (実装を 1 行壊して FAIL を確認。コピーに対して `f10dfd36` のコードで実施。以後の変更は説明文だけで、判定のロジックは同じ):

| 壊し方 | FAIL した判定 |
|---|---|
| 区間の判定 `>=` を `>` に | 3 件 (b の閾値 14 分・b2・ANSI 付き 15 分) |
| 残量の検査を無効化 | 4 件 (e の全部) |
| idle=0 で区間を閉じない | 3 件 (d の全部) |

### 11-2. 実データの確認 (`signature-studio/signature-studio-dev` の REST)

2026-10-14T13:04Z に取得 (測定 commit `95b501b2`)。`--since 2026-10-14T10:00:00Z --until 2026-10-14T12:30:00Z`・`--bucket` 既定 (day)・`--events` 既定 (3 event)。期間は run の作成時刻で切る。標本の時刻は `--until` を数分越えうる (例: run `38564218200` は作成 12:29:44Z で期間内、その標本は 12:30:26Z)。

| 項目 | 値 |
|---|---|
| run 一覧 (3 event・重複除去後) | 155 件 (うち oc-fix 19・watchdog job が cancelled でログ無し 12) |
| 標本 | 124 件 (idle>0: 112 件・最大 idle=19・最長の標本間隔 4.97 分・15 分超の間隔 0 回) |
| idle>0 が 15 分以上続いた回数 | 1 回 (10:00:33Z〜12:07:40Z の 127.12 分) |
| 同 (`excluding_stuck_labelled`: STUCK_LABELLED の行数を引いた idle) | 2 回 (11:10:04Z〜11:25:52Z の 15.8 分と 11:34:59Z〜12:07:40Z の 32.68 分) |
| 所要・API | 144 秒 (load 0.21)・276 回・`X-Ratelimit-Remaining` の最小 4,155 |
| `--cache` 付きの 2 回目 | 8 秒・API 4 回 (cache_hits 136) |

- 別算法の検算: 同じ測定の JSONL (124 標本) を Python で集計し直した (時刻順に idle>0 を畳む。ツールの jq とは別の実装)。
  通常の idle は 1 回 (127.12 分)・stuck 除外は 2 回 (15.8 分・32.68 分) で一致した。
- この期間は oc:stuck の PR が残っており、通常の idle は 127 分連続で 0 にならなかった。stuck 除外の値で soak を判定する理由は README に書いた。

### 11-3. 検証範囲・未解決

確認範囲: `schedule` の run は実リポジトリで 5 件 (`actions/workflows/opencode.yaml/runs?event=schedule`: 2026-10-13 18:23Z・23:00Z、2026-10-14 01:48Z・06:47Z (cancelled)・12:29:44Z)。うち 12:29:44Z の run `38564218200` は実測期間に入り (作成 10:00〜12:30Z)、その watchdog job (`115852677230`) のログの idle 行 (12:30:26.96Z・`idle=1`) を読めた (標本 124 件に含む)。この標本は 12:27:49Z〜12:30:26Z の区間 (5 標本・2.62 分・不計数) の末尾。他の 4 件は実測期間の外で、ログは未確認。
レート制限の中断と 1,000 件上限は fake gh でだけ確認した (実 API で残量を 1,500 未満にはしていない)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `schedule` の run のうち実測期間の外の 4 件 (cancelled 1 件を含む) のログは未確認。cron は約 18 時間に 5 件と疎 | 今後の発火ぶんの標本が読めるかは未確認 (読めなければ `runs.skipped.no_idle_line` に数えるので気づける) | #2355 (timer 停止の手順書) の soak 開始時の確認項目 (訂正コメント済み) |
| soak の合格ライン (何日・何回までを許すか) は未決 | ツールは回数を出すだけで、判定はしない | #2355 にコメント (判定は PM) |
