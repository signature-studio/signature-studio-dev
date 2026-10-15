# tools/pm — oc-pm run の所要時間と同時実行数の実測 (#3463・CI-166)

親 #3189 (oc-pm の毎時上限を 12 から 24 に上げた件) の残り。上限を上げたときの同時 run 数を見積もるための実測。
再現スクリプト: [`oc_pm_duration.py`](oc_pm_duration.py)・単体テスト: [`test_oc_pm_duration.py`](test_oc_pm_duration.py)。

- **測定 commit**: `ee50c01de` (測定に使ったコード。`tools/pm/oc_pm_duration.py` と `tools/pm/test_oc_pm_duration.py` を入れた commit)。
  以後の commit は本書と `tools/pm/README.md`・`docs/DOC_MAP.md` だけ。`git diff ee50c01de HEAD -- tools/pm/oc_pm_duration.py tools/pm/test_oc_pm_duration.py` は 0 行 (§6)。
- **取得時刻**: UTC 2026-10-15 02:05〜02:12 (GitHub REST の読み取りのみ)。窓の終わりは `--now 2026-10-15T02:03:34Z` で固定。

## 0. 結論

1. 直近 24 時間 (2026-10-14T02:03:34Z〜2026-10-15T02:03:34Z) に完了した oc-pm run は **151 件** (全件完了・進行中 0)。
   所要 (run_started_at → updated_at) は **平均 3.65 分・最大 7.90 分** (中央値 3.60・最小 0.22)。pm job 単独 (started_at → completed_at) は平均 3.45 分・最大 7.57 分。
2. 24 起動/時の**平均同時数** (issue の式): 24 × 3.65 ÷ 60 = **1.46**。issue の『最悪』 (timeout 30 分) は 24 × 30 ÷ 60 = **12.0** で、これは平均同時数の上限であって、瞬間の同時数の上限ではない。
3. **瞬間の同時実行数の実測最大は 13** (2026-10-15 01:40:20〜27Z に 13 件が 8 秒で送られ、全件が稼働中になった)。12 を超えたので、『最悪 12』を瞬間の上限として使えない。
   Worker の上限 (24 件/時) の下での瞬間の上界は **24** (§5)。
4. 24 件/時に届いたのは 1 時間だけ (2026-10-15 の 01:05:50〜02:05:50Z の窓で 24 件)。**24 件/時が続く定常の同時実行は未実測**。

## 1. 取得方法 (再現コマンド)

```
python3 tools/pm/oc_pm_duration.py --now 2026-10-15T02:03:34Z
```

- gh (REST のみ・認証済み)。1 回 102 秒 (初回)、87 秒 (HEAD 再測定)。測定直後の uptime の load average は 0.15 (1 分値)。Python 3.14.8。
- 対象の取得: `GET repos/signature-studio/signature-studio-dev/actions/workflows/opencode.yaml/runs?event=repository_dispatch&created=<窓の始め−24 時間>..<now>`。
  題名が `oc-pm ` で始まる run だけを使う (run-name は `.github/workflows/opencode.yaml` L7)。
- 窓: `updated_at` (完了時刻) が (now − 24 時間, now] の completed run。作成が窓より前の run も完了が窓内なら入るように、作成側は 1 日余分に取る。
- 所要: run の `run_started_at` → `updated_at` (issue の受入条件)。併記: pm job の `started_at` → `completed_at` (`GET .../runs/{id}/jobs` の name=`pm`)。
- 一覧は `created` の上限を `now` で止める。上限を付けずに測ると、測定中に新規 dispatch が増えてページがずれ、件数が `total_count` と合わなかった (874 件 と 873 件・1 回目の失敗。修正後は一致)。
- 整合チェック: 一覧の件数 (`repository_dispatch` の全 event) が同じ取得の `total_count` (873 件) と一致しなければ終了コード 1 にする。
- 生データ: `tools/pm/work/oc_pm_runs.json` (gitignore。run の API 応答と行ごとの表)。

## 2. 所要 (窓内 151 件・分)

| 指標 | run (run_started → updated) | pm job (started → completed) | 待ち (created → run_started) |
|---|---|---|---|
| n | 151 | 151 | 151 |
| 平均 | 3.65 | 3.45 | 0.00 |
| 中央値 | 3.60 | 3.50 | 0.00 |
| 最小 | 0.22 | 0.15 | 0.00 |
| 最大 | 7.90 | 7.57 | 0.00 |

- 待ちは 0 秒 (全件で created_at と run_started_at が秒単位で一致)。同時数は待ちに影響されない。
- 結論: success 150・failure 1。failure は run `38574188945` (`oc-pm x #5`・2026-10-14T13:43Z)。pm job の `Refuse the dispatch` が失敗
  (kind `x` は値域外のため `prepare-event-context.sh` が refuse)。pm job は 9 秒で終わり agent は起動していない。送り手の誤りで、同時数には影響しない。
- 種類別 (jq で集計。全 151 件): needs_decision 95 件 (平均 3.29・最大 7.53)、no_pr 45 件 (平均 4.71・最大 7.90)、stuck 5 件 (平均 2.98・最大 3.43)、
  user_answered 4 件 (平均 1.52・最大 1.92)、refs_orphan 1 件 (5.35)、x 1 件 (0.22・refuse)。

## 3. 起動 (created_at) の時間別件数 (UTC)

| 時 (UTC) | 件数 |
|---|---|
| 10-14 13 時 | 1 |
| 10-14 14 時 | 8 |
| 10-14 15 時 | 10 |
| 10-14 16 時〜10-15 00 時 (9 時間) | 各 1 時間 12 件 |
| 10-15 01 時 | 24 |
| 合計 | 151 |

- 16〜00 時の 12 件/時の張り付きは、#3189 以前の Worker 上限 (`PM_LIMITS.hourMax` 12) と整合する (推定。上限の deploy 時刻は未確認)。
- 01 時の内訳 (10 分刻み): 01:00 が 2 件、01:10 が 2 件、01:20 が 2 件、**01:40 が 16 件**、01:50 が 2 件。
  01:40:20〜27Z に 13 件が 8 秒で送られ、13 件はすべて別の ref (kind は user_answered・needs_decision・no_pr)。Worker の 1 回の送信と推定 (Worker のログは未確認)。
- 60 分の窓の最大は 24 件 (窓の始め 2026-10-15T01:05:50Z)。30 分の窓の最大は 19 件。
- 送り手は 2 系統ある。(a) Worker (`infra/pm-worker`・上限 `PM_LIMITS`・`hourMax` 24)、(b) watchdog (`.github/scripts/watchdog.sh` L652〜L660・上限 `PM_HOUR_MAX=12`)。
  (b) は Worker が live かつ fresh のとき送らない (L665)。run の情報からは送り手を区別できず、内訳は未測定。

## 4. 同時実行数の実測

- 平均 (Little の法則の検算): 窓内の run 所要の合計 ÷ 1440 分 = **0.383**。起動率 λ = 151 ÷ 1440 = 0.1049 件/分、平均所要 W = 3.65 分、λW = 0.383 で一致。
- 瞬間の最大: **13**。区間 [run_started, updated) の掃引 (`max_concurrency`)。jq の別算法 (30 秒刻みのサンプリング) でも 13 (初出 2026-10-15T01:40:34Z・3 サンプル)。
  13 件は 01:40:20〜27 に始まり、所要はどれも 100 秒以上なので 01:40:34 には全件が稼働中だった。
- 30 分の窓の最大起動数: 19 件 (瞬間の同時数の上界の算出に使う。§5)。

## 5. 24 起動/時の同時実行数の見積り

| 式 | 値 | 意味 |
|---|---|---|
| 24 × 平均 3.65 ÷ 60 | **1.46** | 平均同時数 (Little)。定常・平均所要の仮定 |
| 24 × 最大 7.90 ÷ 60 | 3.16 | 平均同時数の目安 (最も長い run の所要で置いた場合) |
| 24 × timeout 30 ÷ 60 (issue の『最悪』) | **12.0** | 平均同時数の上限 (全 run が timeout まで続く仮定) |
| 観測の瞬間最大 | 13 | 実測 (2026-10-15 01:40:34Z) |
| 瞬間の上界 (24 × 1 窓 30 分) | **24** | 上界 (下の注) |

判断:

- 上の 3 つの式 (1.46・3.16・12.0) は平均同時数であり、瞬間の同時数の上限ではない。実測の瞬間最大 13 は 12 を超えた。
- 瞬間の上界: 同時数 (時刻 t) ≤ 「t の直前 30 分に始まった run の数」 (run の所要は timeout 30 分以内)、
  その数は上限 (24 件/時) の下で 24 以下。実測の 30 分窓の最大は 19 件。
- 注 (前提): 上界は Worker の上限 (24 件/時) が全ての送信に効く前提で成り立つ。watchdog の経路 (上限 12) は Worker が live のときは送らないので同時には効かない想定だが、
  両経路が同じ時間に送るケースは本測定では確認していない (未検証)。

## 6. 検証

- コード: `tools/pm/oc_pm_duration.py`・`tools/pm/test_oc_pm_duration.py` (測定 commit `ee50c01de`)。
- 単体テスト: `python3 -m unittest discover -s tools/pm -p 'test_oc_pm_duration.py'` → **13 件 PASS** (0.001 s)。CI の `scripts-test` は `tools/pm/test_*.py` を同じ discover で実行する。
- 再現: コミット後の HEAD `ee50c01de` で `--now 2026-10-15T02:03:34Z` を再実行し、コミット前に取った同じ窓の要約 JSON と比べた → **同一** (`diff` 0 行)。
- 独立検算 (別算法: jq・生データ `tools/pm/work/oc_pm_runs.json`):
  - 所要の件数・平均・最大・最小: `jq -c '[.runs[] | select(.status=="completed") | ((.updated_at|fromdate) - (.run_started_at|fromdate))/60] | {n: length, mean: (add/length*100|round/100), max: (max*100|round/100), min: (min*100|round/100)}'` → `{"n":151,"mean":3.65,"max":7.9,"min":0.22}` (一致)。
  - 瞬間の最大: 30 秒刻みのサンプリングで 13 (一致)。60 分の窓の最大起動数: 24 (`max_by`・窓の始め 01:05:50Z)。30 分の窓: 19。
  - 結論の内訳: success 150・failure 1 (一致)。
- ネガティブコントロール (単体テストを変異させて FAIL を確認。変異は一時コピーで、コミットしていない):
  - (a) 掃引の同時刻の並び (終了を先に数えない) を変える → `test_touching_is_not_overlap` が FAIL (1 件)。
  - (b) `is_pm_run` の題名の条件を外す (oc-fix も数える) → `test_only_oc_pm_dispatch` が FAIL (1 件)。
  - 本来のコード: 13 件すべて PASS。
- 検証範囲: 1 つの 24 時間窓 (2026-10-14T02:03:34Z〜2026-10-15T02:03:34Z) の oc-pm (repository_dispatch) run。
  範囲外: (i) 24 件/時が続く定常 (実測は 1 時間分のみ)、(ii) oc-pm 以外の run (implement・review・watchdog) の同時数、
  (iii) GitHub Actions のアカウントの同時 job 数の上限 (プラン)、(iv) 上限変更の deploy 時刻 (#3189 の記録が正本)、(v) 送り手 (Worker・watchdog) の内訳。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 瞬間の同時数の上界 (24) を抑えるか (Worker の 1 回の送信数を制限するか) | 24 件を 1 回で送ると、同時 run が最大 24 件 (各 3.5 分前後)。Actions 側の同時 job 上限に届くかは未測定 | PM 判断。#3463 のコメントで依頼 |
| 24 件/時の定常の実測 | 本書の 24/h の見積りは平均の式。実測の定常は 1 時間分のみ | #3463 のコメントで依頼 (次の 24 時間で `python3 tools/pm/oc_pm_duration.py --now <時刻>` を再実行) |
| 送り手 (Worker と watchdog) の混在時の上界 | 両経路が同じ時間に送ると上界が 24 を超えうる | 未測定。#3463 のコメントで PM に依頼 |
