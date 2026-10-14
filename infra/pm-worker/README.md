# signature-studio-pm (PM Worker)

PM の launch / watchdog を、VM のポーリング (systemd timer) から **webhook 駆動 + Cron / alarm** の Cloudflare Worker に移す (#1751)。
コードの既定は **dry-run** (GitHub へは書き込まない)。稼働中の `wrangler.toml` は 2026-10-14 から **live** (後述『切替の記録』)。書き込みの有効化と VM timer の停止は PM の判断。
書き込みは経路ごとに独立したスイッチを持つ: launch の `/oc` コメント投稿 = `LIVE_LAUNCH`、`repository_dispatch` (`oc-watchdog` と `oc-pm`) の送信 = `LIVE_DISPATCH` (#2417)、失敗した webhook 配送の再送 = `LIVE_REDELIVER` (#2339。未設定なら記録のみ)。

## 構成

| 要素 | 役割 |
|---|---|
| `POST /webhook` | GitHub App の webhook。`X-Hub-Signature-256` を HMAC-SHA256 (定数時間) で検証してから状態に反映する。対象: `issues` `issue_comment` `issue_dependencies` `pull_request` `pull_request_review` `workflow_run` |
| Durable Object `PmDO` (SQLite) | issue / PR / run / 最後の bot 報告 / blocked_by / launch 時刻を保持。App の鍵は AES-GCM で封じて保管 |
| alarm (webhook の 2 秒後 / 毎分) と Cron Trigger (毎分) | `tick`: 同期 (6 時間ごとに full、5 分ごとに reconcile。保存値の版 `SIGNAL_VER` が記録と違うときは、周期を待たずに full を 1 回走らせる。その full が失敗したときは `SIGNAL_RETRY_MS` (15 分) ごとに再試行する。下の『保存値の版 (`SIGNAL_VER`) を上げる』)・`repository_dispatch` (`oc-watchdog`、前回の送信から 5 分未満は送らない。`LIVE_DISPATCH`。検出した `oc-pm` も同じスイッチ)・launch (`LIVE_LAUNCH`) |
| `POST /admin/resync` | 管理用の全体同期 (#2339)。派生状態を REST の内容で作り直す (`fullSync` と同じ。永続状態は触らない)。認証は呼び出し側の GitHub token (Bearer) が repo の push 権限を持つこと (新規の API token は作らない)。**未認証・不明な token・読み取りだけの token は 404** (入口で DO を呼ばない)。1 時間に 2 回まで、3 回目は 429 (`retry-after`) |
| `POST /admin/import` `GET /admin/export` | VM の状態 (`launched`・`relaunch`・`phase`・`pm_art`) の取り込みと書き出し (#2343)。認証は `/admin/resync` と同じ。既定は検証のみで、`?apply=1` のときだけ保存する。取り込み前は launch しない。下の『VM の状態の取り込みと書き出し』 |
| `GET /setup` `GET /setup/callback` | GitHub App `oc-pm-for-signature-studio` の manifest flow (org 所有)。`/setup` は無認証だが、期限内 (1 時間) の state があれば上書きせず同じ state を返す。state は org 所有の App への変換に成功したときだけ消費する |
| `GET /status` | 集計のみ (実行中 run 数・ready/blocked 数・最終 reconcile 時刻・モード・健全性の観測。下の『/status の観測』)。`mode_launch` / `mode_dispatch` が経路ごとのモード (`live` / `dry-run`)。`mode` は両方 `live` のときだけ `live` (片方だけなら `partial`、どちらもなら `dry-run`。`tools/pm/pm_gate.sh` は `mode=live` を『VM の command を止めてよい』と読む)。`?detail=1` は repo の push 権限を持つ GitHub token (Bearer) が必要 |

`GET /` (#2658) は `/status` を 15 秒ごとに読む簡易 GUI (単一 HTML。`src/gui.ts`。DO は呼ばない)。外部のスクリプト・スタイル・フォントを読まず、CSP は `default-src 'none'` + 応答ごとの nonce (App の秘密鍵を持つ制御面に、外部の供給元の侵害を持ち込まないため)。値は `textContent` だけで描く。

launch の規則は `tools/pm/launch_issues.py` の `classify` と同じ入出力 (固定 JSON を Python 版と TS 版の両方で読む突き合わせテスト: `test/classify.test.ts`)。差分は次の 7 点で、いずれも issue 本文を解析しない。

1. blocked_by の一覧が不明な issue は着手しない。
2. open な子 (`親: #N`) を持つ親 issue は着手対象から外す。
3. ラベル `oc:no-pr` は『PR を出さずに終わった』run の後。最後の `oc-run-outcome` の reason で再着手を決める (`plan()` の `noPr`)。cooldown (既定 6 時間。`NO_PR_COOLDOWN_H`) の間は着手しない。`prio:critical` の issue は cooldown を半分 (3 時間) にする (`noPrCooldownMs`。意図の投稿の判定 `intentGate` も同じ)。cooldown の後は次のとおり。
   - `unknown`: 1 回だけ再着手する。
   - `artifact`: 直前の報告 (`botReport`。run-outcome と PM のマーカーを含むコメントを除く) が停止報告 (`STOP_RE`) で、その報告に前回の `oc_artifacts` に無い allowlist 内の素材があるときだけ 1 回再着手する (増えなければ再投入しない)。
   - `stop`・`split`: 再投入せず、PM agent (`oc-pm`・下の oc-pm 節) に回す。
   - `blocked`: blocker (`blocked_by`・本文の依存) が open の間は `blocked` の行に置き、再着手しない。blocker が 0 になった tick で、**その blocked の報告 (`run-outcome` の時刻) につき 1 回だけ**再着手する (`np:<n>.blocked` に報告の時刻を残す。連続する tick では二重に投稿しない)。
     解除後の扱い: 同じ報告のまま blocker が再び付いて解除されても、再着手しない (`stopped` に `oc:no-pr blocked 再着手済み` と残る)。新しい blocked の報告が出れば、その報告につき 1 回だけ再着手する。blocker を持たない blocked の報告は、報告につき 1 回だけ cooldown の後に再着手する (依存が一覧に無いので、解消したとみなして試す)。
   - 再投入の計数は `unknown`・`artifact`・`blocked` の再投入 (上限 3 回。上限に達した後は stopped に残す)。`launch-unobserved` (投稿の run が 5 分で現れなかった) は再投稿せず stopped に残す。
   `oc:stuck` は人の判断待ち。`pm-apply`・`needs-user-input` は下の oc-pm 節のとおり、再着手せず `user` 行に置く。
   `/status` の `no_pr_needs_pm` は、最後の run-outcome が `artifact` で stopped に残った `oc:no-pr` の件数 (PM の判断待ち)。
4. 同期が 15 分以上止まっている間、または一覧を上限ページで打ち切った間 (下の「同期の窓と打ち切り」) は、投稿も `oc-watchdog` の dispatch もしない (`/status` の `fresh=false`)。
5. relaunch (`oc:no-pr` の再投入・素材の追加) も 1 tick の枠 `min(room, BATCH, relaunch + ready)` に入り、残りの枠を ready が使う (`src/launch.ts` の `planLaunch`)。relaunch は room や BATCH を超えても全件出す。枠を `ready` の件数だけで頭打ちにする VM の `launch_issues.py` の式とは、relaunch がある tick で最大 relaunch の件数だけ差が出る (VM の式は変えていない)。relaunch は classify が issue ごとに 2 回までに絞る。
7. **優先の区分 (`prio:critical` / `prio:low`)**: ready の並びは、区分 (critical → 区分なし (normal) → low) が先。同じ区分の中は従来の並び (被ブロック数の多い順 → 『任意』でない順 → 番号順)。`prio:critical` が付いた ready が枠より多いときは、critical を先に選ぶ。critical が無ければ、他の ready を従来どおり枠の残りに入れる (枠を遊ばせない)。relaunch は従来どおり枠の先頭に全件入り、残りの枠を ready が使う (critical は ready の中で先頭)。ラベルは作成しない (`prio:*` が無ければ従来と同じ並び)。
   **prio:low の上限 (`LOW_CAP`、#2721)**: 着手済み (started)・launch 可能 (ready・relaunch) で blocked でない `prio:critical` が 1 件以上ある間だけ、未完了の `prio:low` の run (`active_by_prio.low`) を数えて、新しい low の launch を `LOW_CAP - 実行中の low` までに抑える (0 未満にはしない)。critical が無ければ上限は効かない (枠を遊ばせない)。実行中の low の run は止めない。再投入の意図 (`oc-pm-intent: relaunch`) の投稿と picks は同じ枠を共有する (意図は枠が空くまで処理済みにしない)。low の run の対応は、run の題名が issue の題名と一意に一致する `issue_comment`・`workflow_dispatch` の run だけ。対応が取れない run は normal として数える。
6. **room の基準は opencode.yaml の全 run の総数**: `room = max(0, target_eff - active_all)` (`target_eff` は上の『同時実行の上限の推定』で決まり、推定が無ければ `TARGET`)。`active_all` は `workflow_run.path` が `opencode.yaml` の未完了の run (in_progress・queued・pending・waiting・requested) を **event を問わず** 全て数える (`src/active.ts`)。VM 版の `active_runs` は実装・fix の run (`issue_comment` `workflow_dispatch` `pull_request_review` と題名が `oc-fix` の `repository_dispatch`) だけを数え、review (`pull_request`)・oc-pm・watchdog を数えなかった。同時実行の上限 (Team プランで 60) はこれらを含む opencode.yaml の全 run が共有するので、旧い数え方では `room` が過大になり、上限を超えて queued が出た (実測は #2625)。別 workflow (`scripts-test.yaml` `terms-watch.yaml`) の run は別枠で数えない。`path` を持たない run (この版より前の保存値) は opencode.yaml として数える (過大に数える側)。reconcile (5 分ごと) が REST の `path` で埋める。TARGET の既定は **58** (上限 60 から 2 を残す)。推定の観測 (`running` / `queued`) は従来どおり workflow を問わない (同時実行の上限は repo の全 workflow の job が共有するため)。
7. ラベル `oc:hold` の open な issue (Worker の自動着手を見送る印。#2651) は `hold` 行に置き、着手 (picks) も再投入の意図 (`oc-pm-intent`) も投稿しない。判定は `needs-user-input` の次で、`blocked`・`started` より前 (付いていれば、ほかの行を見ない)。詳細は下の『oc:hold ラベル』の節。

`/oc` コメントの本文は固定テンプレートで、可変なのは `oc_artifacts:` 行と、再投入の意図に `focus=K` があるときの受入条件 1 行だけ。素材名は `.github/scripts/prepare-event-context.sh` の `ARTIFACT_RE` と同じ集合 (`ALLOW_ARTS`) を通ったものだけ。webhook の自由文 (タイトル・本文・コメント) は指示文に入らない。

再投入の意図 (`<!-- oc-pm-intent: relaunch issue=N arts="..." focus=K -->`、#2475): issue ごとに最新の意図マーカーを保持する。実装 App の意図は第三者の意図より優先する。意図のコメントは bot の投稿でも `botLast` (停止報告の窓) を動かさない。次を**全て**通ったときだけ `/oc` を投稿する。
  - 検査 (`src/launch.ts` の `checkRelaunchIntent`): 書き手は実装 App・`issue=` がコメントの issue と一致・`arts` が `ALLOW_ARTS` の部分集合・`focus` は 1〜9 (任意)・同じ issue に 24 時間で 3 回まで。
  - 分類 (`plan()` の rows): 投稿してよいのは picks と同じ `ready`・`relaunch`・`stopped` (PM の判断待ち) だけ。`user`・`blocked` は投稿しない。`started` は open な PR があれば投稿しない (理由 `started`)。実行中の run だけで started のときは、run の完了後に分類し直すまで待つ (処理済みにしない)。`recent` (着手直後の待ち) と `blocked_by` が未同期 (unknown) の issue も、処理済みにせず次の tick に回す。`oc:stuck`・`pm-apply`・`needs-user-input`・`oc:hold` は投稿しない。`oc:no-pr` は picks の再着手と同じ cooldown (`NO_PR_COOLDOWN_H`) と上限 (3 回) を見る。子 issue (open) を持つ親は、停止報告の行 (`stopped`) でも投稿しない (停止報告に素材行があるかどうかに依らない)。未観測の launch (`launch-unobserved`) も投稿しない。
  - 順序: 意図は picks より先に処理し、意図で扱った issue は picks から外す (picks が先だと、同じ issue の意図が focus なしで処理済みになるため)。403/429 や REST の残量で止まったら、同じ tick の picks も止める。
  - 枠: 意図の投稿は `room`・`BATCH` の枠に入らず、条件を通ったものは全件出す (picks の relaunch と同じ)。一斉に意図が届くと、同時に走る run の数 (`TARGET`) を超え得る。
  - 最後の `/oc` より前に出た意図 (PM の手動の `/oc` を含む) は捨てる。停止中 (review-only・stuck 上限・REST の残量不足) は処理しない (意図も残し、停止が明けたら判定する)。
  - 拒否は理由ごとに `counters.intentRejected` へ数え (語彙: `author` `issue` `arts` `focus` `limit` `user` `hold` `blocked` `started` `stopped`)、その意図は処理済みにする。
  - 投稿の可否は `LIVE_LAUNCH` に従う (コードの既定は dry-run。dry-run では `counters.intentWouldLaunch` と `log` に記録し、処理済みにしない)。
  - **稼働中の `wrangler.toml` は `LIVE_LAUNCH = "1"` なので、この版をデプロイすると、意図の経路も dry-run を経ずに即 live で `/oc` を投稿する。** 待ち (oc:no-pr の cooldown・blocked_by の未同期) が明けた意図は、その tick で投稿され得る。
  - `would_launch_now` は picks (launch の計画) だけを出す。保留中の意図 (待ち・処理済みでないもの) は `/status` に出ない。`counters.intentWouldLaunch` は dry-run の期間に記録された件数で、live では増えない。
  - **PM agent の判断待ち**: deploy 時に、既存の意図を live で処理してよいか。既定案: issue #2475 の受入条件 4 どおり `LIVE_LAUNCH` に従う (現状 `"1"` なので live)。focus の値域は #2575 で決める (pm.md の `focus=K` は issue 番号で、検査は受入条件番号 1〜9)。

## oc:hold ラベル (#2651)

Worker の自動着手 (`/oc` の投稿) を見送らせる印。PM の subagent が自分で実装する issue に付け、Worker が同じ issue に着手コメントを重ねて重複 PR を作るのを防ぐ。

- **判定**: `src/classify.ts` が、`oc:hold` の付いた open な issue を `hold` 行に置く。launch (picks) と再投入の意図 (`oc-pm-intent`) の対象から外れる (意図は `counters.intentRejected.hold` に数える)。`/status` の `hold` はこの行の件数。`needs_user` (`needs-user-input` のラベル数) には含まれない。hold の間に届いた再投入の意図は拒否として処理済みになるので、ラベルを外しても古い意図では投稿されない (ready の issue は通常の着手で拾われる)。
- **付ける (推奨)**: 起票時に `labels` を指定する。ラベルは issue の作成と同時に付くので、Worker が最初に受け取る `issues` 配送から見えており、着手と競合しない (作成 API の仕様からの推論。実測は未検証)。
  `gh api repos/signature-studio/signature-studio-dev/issues -f title='[AREA-n] ...' -f body='...' -f 'labels[]=oc:hold'`
  起票後に `gh issue edit <N> --add-label oc:hold` で付けると、付与の前に次の tick が着手する窓が残るため、避ける。
- **外す**: `gh issue edit <N> --remove-label oc:hold`。`issues` 配送で labels が更新され、次の tick (webhook の 2 秒後) から通常の分類に戻る。ready なら着手対象になる。
- **ラベルが無いとき (初回のみ)**: `gh api repos/signature-studio/signature-studio-dev/labels -f name=oc:hold -f color=ededed -f description='Worker の自動着手を見送る (#2651)'`。作成の前に、存在しないラベル名を起票時に指定した場合の挙動は**未検証** (実測していない)。起票の前に作成しておく。
- 対象は launch だけ。`oc-pm` の検出 (`no_pr` など) は `oc:hold` を見ない (`oc:hold` と `oc:no-pr` が両方付くと PM agent を起こし得る)。
- VM 版の `tools/pm/launch_issues.py` は `oc:hold` を見ない。VM の timer は停止したままにする (再開すると、この印を素通しで着手する)。

## oc-pm: PM agent を起こす終端状態の検出と送信 (#2333)

PM の判断が要る終端状態を **決定的に** (ラベル・マーカー・正規表現だけ。LLM は使わず、自由文は解析しない。番号の正規表現だけ読む: `src/refs.ts`) 検出し、`repository_dispatch` の `oc-pm` を送る。入口側は `.github/scripts/prepare-event-context.sh` (#2327)。

| kind | 検出 (すべて open の対象。起票者は後述の絞り込みを通ったものだけ) |
|---|---|
| `stuck` | `oc:stuck` の PR で、最新の停止コメント (`<!-- oc-fix-limit -->`、bot 投稿) に `<!-- oc-pm-intent: stuck pr=N ... -->` がある (`pr=` が当該 PR の番号) |
| `no_pr` | `oc:no-pr` の issue で、最後の `<!-- oc-run-outcome: no-pr reason=... -->` が `split` / `stop`、または `unknown` で Worker が再投入済み (再投入の後の run でも `unknown`)。または実装 run の打ち切りが連続して自動の再着手を止めた issue (『実装 run の打ち切りの連続』。`oc:no-pr` の標識は付かない) |
| `needs_decision` | reviewer の最新の verdict が CHANGES_REQUESTED で、本文が `NEEDS_KEY` (`src/needs.ts`。`tools/pm/pm_needs.py` の `KEY` と同じ正規表現・同じ行分割) に一致し、その後に PM 応答が無い |
| `user_answered` | `needs-user-input` の issue に、ラベルが付いた後に非 bot のユーザーのコメントが付いた (コメント者が `MEMBER` / `OWNER` / `COLLABORATOR` のものだけ。第三者のコメントでは起こさない #2461) |
| `refs_orphan` | `Refs #N` のみ (閉じキーワード `Closes` / `Fixes` / `Resolves` の系が無い) で merge された PR の N が open で、本文に `親: #N` を持つ open の子が無い。`ref` は親 N (`src/refs.ts`。merge 時点の本文から番号だけを `prs[PR].refsOnlyNums` に残す) |

- マーカーは **bot (実装 App・reviewer App) の投稿だけ** を信じる (誰でもコメントできるため)。PM 応答は、PM のログイン (`PM_LOGINS` と PM App) のコメント、または bot の `oc-pm-decision` / `oc-pm-intent: relaunch` マーカー付きコメント。根拠より後にあれば、その対象は送らない。
- 状態は `sig` (issue / PR 番号ごとの時刻・列挙値・真偽。本文は持たない)。webhook の増分で更新し、webhook で埋まらない reviewer の verdict と `needs-user-input` の付与時刻は reconcile で REST から一度だけ補う (best effort)。
- 送信: payload は `{"event_type":"oc-pm","client_payload":{"kind":<列挙>,"ref":<数字>}}` だけ。値は検証済みの列挙・整数から組み立て、issue / PR の自由文は入らない。PM App の installation token で送る。スイッチは `LIVE_DISPATCH` (oc-watchdog と同じ。別スイッチは作らない)。
- 絞り込み: 起票者が `MEMBER` / `OWNER` / `COLLABORATOR`、または許可 bot (`opencode-for-signature-studio[bot]` `oc-reviewer-for-signature-studio[bot]`) の対象だけ。起票者が未取得の対象は送らない。
- 抑止 (DO の `meta/pmDispatch`): 同じ (kind, ref) は 60 分に 1 回・全体で 1 時間に 12 起動・同じ ref に 24 時間で 3 回まで。未送信の対象を先に、送信済みは古い順に選ぶ。失敗した試行も数える (403 / 429 はその tick を打ち切る)。同期が 15 分以上止まっている間は送らない。`refs_orphan` だけは種類ごとの上限 (`KIND_LIMITS`) が加わり、同じ N に 24 時間 1 回・1 日 10 件まで (全体の上限にも従う)。
- **dry-run (既定。`LIVE_DISPATCH` が `"1"` でないとき)**: 送らず、`/status` の `would_dispatch_pm` (`?detail=1` のみ) と `counters.wouldDispatchPm`、`pm_detected` (kind ごとの検出数) に記録する。履歴は live と分ける (`meta/pmWould`)。`LIVE_LAUNCH` は関係しない。
- ラベル `pm-apply` / `needs-user-input` の issue (着手しても PR を出さない/出せない) は、`no_pr` の検出から除く。`plan()` は、この 2 ラベルの issue を ready・再投入の対象であっても着手せず `user` 行に置く (`oc:no-pr` の有無に依らない)。`user_answered` は `needs-user-input` が対象。`tools/pm/launch_issues.py` との差は PR 本文の未解決表に書く。
- 検出するのは上の 5 kind。`refs_orphan` は [CI-58]、`supply` は [CI-71] が担当する。
- `digest` (#2349・CI-70) は状態ではなく時刻で送る: `ref` は 0 だけ。初回の tick は起点を置くだけで、以後 24 時間に 1 回 (`meta/digestAt`)。送信に失敗した試行も 1 回と数え、毎分叩き直さない。dry-run は `would_dispatch_pm` に `digest#0` を記録するだけ。PM agent 側の集計は `.github/prompts/pm.md` の digest 節。

## 実装 run の打ち切りの連続 (killed)

実装 run (`issue_comment`) が **PR も出さずに** cancelled / failure / timed_out で終わると、`oc:no-pr` の標識が付かない (runner の shutdown では `record-run-outcome.sh` の `always()` step が走らない)。標識が無いと、Worker は『着手済みで run が終わった』issue として cooldown (3 時間) ごとに同じ指示で再着手し続ける。重い issue ではこれが同じ失敗の繰り返しになる。そこで **`workflow_run.completed` の conclusion だけで** (標識に依らず) 数える (`src/webhook.ts` の `applyKill`)。

- **数える**: conclusion が `cancelled` / `failure` / `timed_out` で、題名が **一意な open issue** に当たる `issue_comment` の run。PR 上のコメントの run (題名が PR) や、同じ題名の open issue が複数あるときは数えない。
- **数えない**: (a) open PR がある (ブランチ名 `N-...` か本文の `Closes` / `Refs` / `Fixes` / `Resolves #N`。着手済み)、または run の開始以降に merge された PR がある (run 中に open から merge まで済んだ PR は open の一覧に出ない。closed の PR は本文を持たないので、ブランチ名 `N-...` だけで当てる。`record-run-outcome.sh` と同じ考え方)、(b) `oc:stuck` `needs-user-input` `blocked` `pm-apply` のラベルか blocked_by がある (明示的な終了状態)、(c) **後続の run がある** (同じ題名の `issue_comment` の run で id が大きく、`skipped` で終わったものを除く。concurrency で置換された待機中の run の cancelled)。
- **連続**: 成功した run は連続を断つ。`skipped` の run は断たない (agent 自身のコメントでも `issue_comment` の run が起き、`skipped` で終わる)。同じ run の再配送と順不同の配送は、最後に数えた run の id (`sig[N].killRun`) より大きい run だけを数えて重ねない。`killRun` は連続の解除では消さず、閉じた issue でも残す (run が prune された後の再配送も数えない)。
- **止める**: 連続 **2 回** (`KILLED_STOP_AT`) で、`plan()` は ready・relaunch・recent から `stopped` (`killed x2`) に移す。`oc:no-pr` の cooldown・再投入の枠 (`np`) には載せない。`oc-pm` の **`no_pr`** (既存の kind。新しい kind は作らない) で PM agent の判断に回す。ラベル・コメントは書かない。
- **解除 (連続を 0 に戻す)**: その issue の open PR が出た / issue が close された / 成功した run / kill より後の PM の応答 (PM のログインの通常コメント、PM のマーカー `oc-pm-decision:` `oc-pm-intent: relaunch` 付きの bot コメント) か人 (MEMBER / OWNER / COLLABORATOR) のコメント。**`/oc` の投稿は解除にしない** (Worker 自身の再投稿が連続を解かないように)。人の `/oc` では自動の再着手は止めたままで、`oc-pm` の `no_pr` だけを送らない (PM が応答済み)。その run がまた打ち切られれば再び送る。
- **`/status`**: `killed_stopped` (止めている open issue の件数)、`killed_issues` (その番号。最大 100 件)。`pm_detected.no_pr` にも入る。
- **限界**: (1) `completed` の配送を取りこぼすと数えない (reconcile が『一覧に無い』ことから付ける `conclusion=unknown` は数えない。失敗した配送の回収 #2339 が補う)。(2) 『push はしたが PR は出していない』run も PR 無しとして数える (`record-run-outcome.sh` と同じ定義)。(3) この版より前の打ち切りは数えない (連続は配送を受けた時点から)。(4) `prepare-event-context.sh` の `no_pr` は `oc-run-outcome` コメントを PM agent に渡すが、打ち切りの issue には無いので、PM agent には issue 本文とラベルだけが渡る。
- 実測と受入条件は #2626。

## 自動 close: 規則 A (#2336)

merged PR を持つ親 issue を閉じる (`src/autoclose.ts`)。判定は保存状態だけで行い REST は呼ばない。tick の最後 (`autoClose`) で動く。
全てを満たす open issue N を閉じる:

1. N を Closes / Fixes / Resolves / Refs で参照する merged PR がある (参照は PR 本文の全文から取り `PrState.closes` に持つ)
2. N を親 (『親: #N』) とする open の子 issue が 1 つ以上ある
3. N に `needs-user-input` が付いていない
4. N の番号を題名・本文に含む open PR がない (`PrState.mentions`)
5. N を blocker にしている open issue が、N の子以外にない

- **保存の範囲**: merged PR の参照は、Worker が見たものだけ (webhook、または全体同期の窓 24 時間)。窓より前に merge された PR は見ていないので、その親は閉じない (保守的な側に倒す)。
- **抜けは閉じないほうに倒す**: `mentions` の無い open PR (保存形式の移行前) が 1 件でもあれば全体で閉じない。blocked_by の一覧が件数に足りない open issue (件数 `total_blocked_by` > 一覧の件数) があれば、子でない限り全体で閉じない。この状態は同期 (`syncBlockers`) が REST から一覧を取り直して直す。同期が古い間 (`fresh=false`) も閉じない。
- 1 tick で最大 5 件。同じ issue は書き込みを試してから 24 時間は再試行しない (閉じ損ねた後のコメントの二重投稿を防ぐ)。
- **書き込みは `LIVE_CLOSE="1"` のときだけ** (`LIVE` や `LIVE_LAUNCH` / `LIVE_DISPATCH` では動かない)。既定は記録のみ: `/status` の `counters.wouldClose` と log の `would-close`。`mode_close` が `live` / `dry-run` を示す。
- live の順序: コメント (`[auto-close] 規則 A: merged PR #<x>、残りは #<c> が追跡 <!-- oc-auto-close: rule=A -->`) → `PATCH` で `state=closed`・`state_reason=completed` (PM App の token、issues:write)。閉じた後の状態は Worker の手元でも closed にする。

### 誤って閉じたとき

1. 対象の一覧: `gh api -X GET search/issues -f q='repo:signature-studio/signature-studio-dev "oc-auto-close: rule=A" in:comments' --jq '.items[]|"#\(.number) \(.title)"'`
2. 再開: `gh issue reopen <N>`。
3. **再開だけでは、次の tick で閉じ直さない**。閉じ直すのは、最後の書き込みの試行 (`meta.autoClose`) から 24 時間 (`AUTO_CLOSE_RETRY_MS`) を過ぎた tick だけ。それより前に止めたいときは `needs-user-input` を付ける (条件 3 で候補から外れる)。条件が揃っていれば閉じ直されるので、残す条件 (子・merged PR・open PR の言及) も直す。
4. 規則 A を止める: `LIVE_CLOSE` を `"0"` (または外す) にして再デプロイする。`/status` の `mode_close` が `dry-run` になる。

## /status の観測 (#2338)

Worker の健全性を外から判断するための集計。既存のキーは変えず、次を足した (個票・自由文は出さない)。

| キー | 意味 |
|---|---|
| `last_webhook_at` | 署名を検証できた webhook の最後の受信時刻 (401 では進めない)。無ければ `null` |
| `last_dispatch_at` | `repository_dispatch` (`oc-watchdog`) に成功した最後の時刻。dry-run では `null` のまま (would は既存の `last_watchdog`) |
| `last_digest_at` | 直近の digest (`oc-pm kind=digest`) を試行した時刻。起点の tick・送信・送信失敗・dry-run の記録を含む (24 時間に 1 回進む)。無ければ `null` |
| `running` | `{in_progress, queued, pending}`: DO が持つ未完了 run を状態別に数えた値。event も workflow も問わない (TARGET に数える `active_runs` とは別)。`running.queued` は status が `queued` のものだけ (`pending`・`waiting` は数えない)。top-level の `queued` は queued・pending・waiting の合計で、定義が違う |
| `target_eff` / `cap_est` / `peak_running` / `queued` / `oldest_queued_age_min` | 同時実行の上限の推定 (#2381)。`target_eff` は launch の目標、`cap_est` は推定の上限 (無ければ `null`)、`peak_running` は直近 24 時間の tick ごとの `in_progress` の最大値。`queued` は queued・pending・waiting の数、`oldest_queued_age_min` は最も古い queued の経過分 (無ければ `null`)。詳細は下の節 |
| `active_runs` / `active_all` | TARGET に数える run の総数 (opencode.yaml の未完了の run。上の 6)。同じ値。`room = max(0, target_eff - active_all)` (`target_eff` は推定が無ければ `target`) |
| `active_impl` / `active_other` | `active_all` の内訳。`active_impl` は `/oc` 起点の実装 run (`issue_comment` `workflow_dispatch`)、`active_other` は review (`pull_request`)・fix (`pull_request_review` と `oc-fix`)・oc-pm・watchdog など |
| `active_by_event` | `active_all` の event 別の件数。`repository_dispatch` は run-name の先頭で `repository_dispatch:oc-fix` `:oc-pm` `:watchdog` に分ける |
| `dry_run_skipped_posts` | dry-run のために投稿しなかった書き込み (`/oc` 投稿 + `repository_dispatch`) の累計 (`counters.wouldLaunch + wouldDispatch`) |
| `reconcile_diff` | `{last, total}`: reconcile が REST を適用して DO の内容が変わった entity (issue・PR・run・bot/PM のコメント) の件数と累計。webhook の欠落の指標。`updatedAt` だけの違い (コメント追加で進む) と full sync は数えない。配送遅延の最中の差も数えるので、1 回の小さな値は欠落とは限らない |
| `build` | デプロイした commit hash (`wrangler deploy --var BUILD_COMMIT:<hash>` で渡した値)。渡していない・小文字 hex の 7〜40 字でないときは `null`。方式と理由は下の『再デプロイ』手順 4 |
| `rest_remaining` / `rest_used` / `rest_reset_at` | Worker の GitHub REST クライアント (installation token) の全応答の `x-ratelimit-remaining` / `-used` / `-reset` (ヘッダが正。`gh api rate_limit` の本文は食い違う)。失敗応答も含む。ヘッダの無い応答・数値でない値では更新しない。一度も観測していなければ `null` (0 ではない)。JWT で叩く `/app/*` と、`/status?detail=1` の呼び出し側の token は別枠なので記録しない |

自律運転の指標 (#2335)。件数と時間だけを返す (題名・本文・login は出さない。issue / PR 番号は可)。

| キー | 意味 |
|---|---|
| `stuck` | open な PR のうち `oc:stuck` の数 |
| `stuck_age_max_min` | 上の PR の経過分の最大。起点は最新の停止コメント (無ければ PR の更新時刻)。該当が無ければ `null` |
| `needs_pm` | open な issue と PR のうち `needs-pm` の付いた数 (合計) |
| `needs_user` | open な issue と PR のうち `needs-user-input` の付いた数 (合計) |
| `no_pr_needs_pm` | 最後の run-outcome が `artifact` で stopped に残った open な `oc:no-pr` の件数 (新しい素材が無い・停止報告でない・再投入済み・上限に達したものを含む。PM の判断待ち)。`split`・`stop`・`blocked`・`unknown` は数えない |
| `no_pr_by_reason` | `{split, artifact, unknown, blocked, stop}`: open な `oc:no-pr` の issue を、最新の outcome の理由別に数えた値。outcome の無いものは数えない |
| `ready_by_prio` | `{critical, normal, low}`: 着手待ち (`ready`) の件数を優先の区分別に数えた値。`prio:critical`・`prio:low` のラベルで決まり、無ければ normal。合計は `ready` と一致する |
| `active_by_prio` | `{critical, normal, low}`: 未完了の opencode.yaml の run (`active_all` と同じ集合) を優先の区分別に数えた値。対応の取れない run は normal。合計は `active_all` と一致する (#2721) |
| `low_cap` | `{cap, running, applied}`: prio:low の上限 (`LOW_CAP`)・実行中の low の run 数・上限が効いているか (critical が着手済みか launch 可能な間だけ真。投稿の直後は、投稿した critical が recent に移るので偽になり得る) (#2721) |
| `refs_only_merge_rate_24h` | `{merged, refs_only, rate}`: 直近 24 時間に merge された PR の件数 (`merged`) と、そのうち本文が `Refs #N` のみ (`Closes` / `Fixes` / `Resolves` が 1 つでもあれば数えない) の件数 (`refs_only`) と率。0 件なら `rate` は `null`。merge 済み PR の『Refs のみ』は merge 時点の本文から取った真偽値だけを持つ (本文は保存しない)。導入前に merge された PR は、次の全体同期 (6 時間以内) で埋まる |
| `open_issues_delta_24h` | 現在の open issue 数から、24 時間前以前で最も新しい 1 時間ごとの点 (`meta/openHist`、最大 48 点) の数を引いた差。点が無い (履歴が 24 時間分に満たない) ときは `null`。同期が古い間と一覧を打ち切った間は点を残さない |
| `pm_dispatch_1h` | 直近 1 時間の `oc-pm` の送信数 (dry-run の would を含む。`pmHistory` と同じ live / dry-run の別) |
| `launch_halted` | launch を止めている区間 `{reason, since}` (止まっていなければ `null`)。`reason` は先頭の理由、`since` は止まり始めた時刻。詳細は下の『launch の停止と通知』 (#2795) |
| `launch_halted_overdue` | 15 分以上止まり、着手待ち (`ready`) と空き枠 (`room`) がある間は `true` (#2795) |

**rate-guard**: `rest_remaining` が 1,500 未満の間は launch を止める (`launch_stop: "rate-guard"`)。1,499 で止まり、1,500 で継続する。未観測 (`null`) は止めない。
reconcile の読み取りと watchdog の dispatch は続く。launch の途中でも、投稿の応答で残量が下がれば残りを投稿しない。遷移 (on/off) のときだけログに 1 行残す。
`stuck-ceiling` (既存) が立っているときは `launch_stop` はそちらを返す。dry-run でも計画 (`would_launch_now`) は止まる (投稿はもともとしない)。

## launch の停止と通知 (#2795)

launch を止める条件は次の 5 つ。`src/halt.ts` の `haltReasons` が決める (先頭が `launch_halted.reason`)。

| reason | 条件 | 判定 |
|---|---|---|
| `no-import` | `IMPORT_REQUIRED=1` で、VM の状態を取り込む前 | `plan.blocked` |
| `stuck-ceiling` | `oc:stuck` の open PR が `STUCK_HIGH` (既定 40) を超えた | `plan.stop` |
| `rate-guard` | REST の残量が 1,500 未満 | `plan.stop` |
| `review-only` | Review-Only (open PR が 80 を超えた。10 を下回るまで続く) | `plan.phase.review_only` |
| `stale` | 同期が古い (reconcile から 15 分以上) か、一覧を打ち切った。launch は書かない | `fresh()` |

含めないもの: `/oc` の投稿で 403/429 が返ったとき (一時的。次の tick で再試行し、`last_error` に出る)。`room` が 0 (同時実行の上限に達しただけで、正常な待ち)。

- **区間**: 止まった時刻を `meta.halt.since` に保存する。止まり続けている間は起点を変えない。全ての条件が無くなると区間を消す (次の停止の起点に使い回さない)。
- **/status**: `launch_halted` (`{reason, since}`。止まっていなければ `null`) と `launch_halted_overdue` (15 分以上止まり、かつ `ready` と `room` がある間は `true`)。
- **PM agent への通知** (30 分継続で 1 回): 新しい kind は作らず、`oc-pm` の `digest` (`ref` 0) を送る。同じ停止区間では 1 回だけ (失敗した試行も数える)。`pmHistory` の上限 (同じ digest#0 は 60 分に 1 回、全体は 1 時間に 12 件) に従う。`LIVE_DISPATCH` が `"1"` のときだけ送り、そうでなければ `counters.wouldDispatchPm` に数える。
- **限界**: `digest` の PM run が受け取るのは kind と ref だけで、`/status` は読まない (oc-pm の workflow に `PM_WORKER_URL` は無い)。そのため通知を受けた PM agent は『launch が止まっている』とは分からず、通常の digest の集計をする。停止の理由を通知に載せるには、CI 側 (`.github/scripts/watchdog.sh` が `/status` を読んで障害 issue を起票する経路) への接続が要る。この PR の範囲外 (未解決の表に起票先を書く)。
- **変異テスト**: `npm run test:mutation` が、既定値・閾値・区間の起点・解消・重複抑止の 7 か所を 1 つずつ壊し、テストが落ちることを確かめる (`scripts/mutation_halt.mjs`)。

## /oc 投稿の観測 (#2342)

投稿した `/oc` (launch) に対して、題名が issue 題名と一致する `issue_comment` 由来の run (`in_progress`・`queued`・`pending`・`completed`) が現れたかを DO (`launchObs`) に記録する。
投稿の応答時刻から 5 分以内に観測できなければ `failed` (着手失敗) とし、`/status.launch_unobserved` に issue 番号を出す。`failed` の issue は**自動では再投稿しない** (`stopped` に `launch-unobserved` として置く)。
後から同じ題名の run が作成時刻 (投稿の 1 分前以降) で現れたら `observed` に直す。dry-run は投稿しないので記録しない。
観測の判定は同期が新しいときだけ `failed` にする。観測済みの launch は、観測した run の完了時刻 (`launchObs.doneAt`・run の `updatedAt`) から 3 時間を `recent` の基準にする (run が進行中は `started` が先に効く)。完了時刻は観測の tick で記録する (`RunState` は完了 1 時間後に prune されるため)。完了時刻の無い観測済み・記録の無い古い launch は従来どおり投稿から 3 時間の `recent` 判定を残す (完了済みで報告の無い run を即時に再投稿しないため)。

**secrets を出さない**: `/status` は集計だけで、issue のタイトル・本文・コメントは載せない。自由文は `last_error.what` とログの `note` だけ (どちらも `?detail=1` のみ)。
これらと `console.log` は `src/redact.ts` を通し、PEM・`gh*_` / `github_pat_` の token・JWT・`Bearer …`・`sha256=…` と、実行時に分かっている secret (webhook secret・PEM・STORE_KEY・直近の installation token) を `[redacted]` にする。

## 同時実行の上限の推定 (#2381)

GitHub の同時実行の上限は契約で変わる (Team 60、終了後 20 など)。固定の `TARGET` だと、上限が下がったときに queued が際限なく積まれる。そこで tick ごとに run 数を観測し、上限を推定する (`src/saturation.ts` の純関数。GitHub への書き込みは増やさない)。

- 観測: 全 event の run を `in_progress` (running) と `queued`・`pending`・`waiting` (queued) に数え、1 分ごとに 1 件を `meta/obs` に残す (24 時間で捨てる)。
  記録するのは `fresh` な tick だけ (launch と同じ条件)。同期が古い間や一覧を打ち切った間は run 一覧が不完全で、偽の飽和を作り得るため記録しない。
- 飽和: queued > 0 のまま running が**同じ値で 30 分続いた**とき、その値を `cap_est` とする。途中で running が変わればそこから数え直す。
  連続する 2 件の観測の間隔が 2 分 (`SAT_GAP_MS`) を超えたら、その間は連続とみなさない (空いた後の streak は空きの後の観測から数える)。
- 引き上げ: 推定の後の観測 (`cap_est` を決めた時刻以降) の peak が推定を超えたら、その peak に上げる (上限が上がった場合)。古い peak で押し上げ直さないよう、窓は推定を決めた時刻から始まる。
- 期限: 推定を決めた (更新した) 時刻から 24 時間たって更新が無ければ推定を消す。
- 目標: `target_eff = min(TARGET, max(TARGET_MIN, cap_est + QUEUE_MARGIN))`。推定が無ければ `TARGET` のまま。`room = target_eff − active_all` (`active_all` は opencode.yaml の未完了の run の総数。上の 6)。
- env: `QUEUE_MARGIN` (既定 10)、`TARGET_MIN` (既定 30)。`TARGET` は上限のままで、推定はそれを超えない。

現行の `wrangler.toml` は `TARGET="58"` なので、推定が 48 以上のとき `target_eff` は 58 に張り付く (上限 60 でも 58 まで。上限 60 から 2 を残す)。

## 失敗した webhook 配送の回収と `/admin/resync` (#2339)

- **再送**: GitHub は失敗した配送を自動で再送しない。tick は 5 分ごとに、App の JWT (`appJwt`。installation token とは別枠) で `GET /app/hook/deliveries?per_page=100` を 1 ページ読み、`status != OK` の配送を古い順に `POST /app/hook/deliveries/{id}/attempts` で再送する。同じ `guid` に OK の配送が 1 つでもあれば回収済みとみなして触らない。再送された配送 (`redelivery: true`) は、失敗しても再送しない (連鎖させない。元の配送の上限だけで止まる)。
- **上限**: 1 回の走査で再送は 10 件まで (試行の少ないものから)。同じ `guid` は 3 回まで (失敗した試行も数える)。rate-guard (`rest_remaining` < 1,500) の間は再送しない。
- **スイッチ**: `LIVE_REDELIVER` が `"1"` のときだけ POST する。`LIVE` には従わない (単独のスイッチ)。未設定 (既定) は一覧を読むだけで、送るはずだった配送を guid ごとに 1 回ずつ `counters.wouldRedeliver` に数える。
- **観測**: `/status` の `counters.redelivered` (送った件数の累計)・`counters.wouldRedeliver`・`last_redeliver_scan` (最後の走査の時刻)・`hook_failed_last_scan` (直近の一覧で `status != OK` だった配送の件数)。
- **限界**: 1 走査は最新 100 件の 1 ページだけを読む。それより古い失敗は読まない (GitHub は配送を約 3 日保持する)。失敗が 1 日に 100 件を超えると取りこぼし得る。
- **`POST /admin/resync`**: 派生状態 (issue・PR・run・コメント・blocked_by・レビュー) を `fullSync` で作り直す。ページ上限と REST の回数は全体同期と同じ。永続状態 (`launchedAt`・`relaunch`・`planned`・`phase`・`counters`) は同期が触らないので残る。1 時間に 2 回まで (試行は失敗しても数える)、3 回目は 429。tick と同時には走らせない (409)。認証と 404 の扱いは上の表を参照。

## VM の状態の取り込みと書き出し (#2343)

Worker の状態 (Durable Object) に、VM が持っていた `launched`・`relaunch`・`phase`・`pm_art` を移す。どれも GitHub から作り直せない値 (`launched` は 3 時間の重複防止、`phase` は Review-Only の現在値、`pm_art` は 24 時間より前の PM の素材指定)。

- **取り込むファイル**: VM の `tools/pm/` の 3 ファイルと、`issues_state.json` の `pm_art`。
  - `launched.json` → `launched` (`{"<n>": "<ISO 8601>"}`)
  - `relaunch.json` → `relaunch` (`{"<n>": {"count": 0〜3, "art": "oc_artifacts: …" または null}}`)
  - `phase.json` → `phase` (`{"review_only": bool, "open_prs": 整数, "since": "<ISO 8601>"}`)。**VM の `phase.json` は使わない。** 切替 (『切替の記録』) の後は、fresh な tick ごとに `launch()` が DO の `meta/phase` を保存するので、DO の値が live の現在値になる。VM の `phase.json` は切替の時点で凍結されていて、取り込むと live の Review-Only の状態が古い値に戻る (open PR が 10〜80 の間は直前の値を保つ規則のため、ずれが残る)。取り込みの `phase` は `GET /admin/export` の DO の現在値を使う (下の手順)
  - `issues_state.json` の `pm_art` → `pm_art` (`{"<n>": {"at": "<ISO 8601>", "line": "oc_artifacts: <ALLOW_ARTS の部分集合>" または "oc_artifacts: none"}}`)。`issues_state.json` は `issue_snapshot.py` が書き、`launch_issues.py` が読む
- **値域** (外れると 400 で何も保存しない。`problems` に理由が返る): issue 番号は 1 以上の数字 (7 桁まで)。時刻はタイムゾーン付きの ISO 8601。`launched` と `pm_art.at` は、取り込み時の現在時刻 + 5 分より後なら 400 (`phase.since` は未来の値も通る)。`count` は 0〜3 の整数。素材行は `oc_artifacts: none` (追加素材なし) か、`src/launch.ts` の `ALLOW_ARTS` の部分集合 (`none` と素材名の混在は 400)。キーは 4 つだけ (未知のキー・欠落は 400)。200 KB を超えると 413。
- **手順** (`$PM_WORKER_URL` は Worker の URL、`$TOKEN` は repo の push 権限を持つ GitHub token。新しい API token は作らない):

  ```sh
  curl -fsS -H "authorization: Bearer $TOKEN" "$PM_WORKER_URL/admin/export" > export.json   # DO の現在値 (phase はここから取る)
  jq -n --slurpfile l launched.json --slurpfile r relaunch.json --slurpfile e export.json --slurpfile s issues_state.json \
    '{launched: $l[0], relaunch: $r[0], phase: $e[0].phase, pm_art: $s[0].pm_art}' > import.json
  curl -sS -H "authorization: Bearer $TOKEN" --data-binary @import.json "$PM_WORKER_URL/admin/import"          # 検証のみ (保存しない)
  curl -sS -H "authorization: Bearer $TOKEN" --data-binary @import.json "$PM_WORKER_URL/admin/import?apply=1"  # 保存
  curl -sS -H "authorization: Bearer $TOKEN" "$PM_WORKER_URL/admin/export"                                     # 確認 (VM の形式で返る)
  ```

  検証で 400 が返ったら、`problems` の issue 番号を直してから送り直す (許可外の素材名は VM の `pm_art` に残っていることがある)。
  送る前に、`relaunch.json` の `art` に `none` と素材名が並ぶ行がないか確かめる。VM の `launch_issues.py` は、既存の行が `none` のとき不足の素材を足すので (`cand = base + extra`)、`oc_artifacts: none fl-win64` の形を書き得る。この形の行が 1 件でもあると、取り込みは全件 400 になる。見つけたら `none` を外して (`oc_artifacts: fl-win64` の形に) 直してから送る。見つける方法: `jq -r 'to_entries[] | select(.value.art != null and (.value.art | contains(" none "))) | "\(.key) \(.value.art)"' relaunch.json`
- **取り込みを求める (`IMPORT_REQUIRED=1`)**: 既定は求めない (#2795 で既定を反転した。それ以前は、取り込みが一度も成功していない間は launch を止めていた)。`IMPORT_REQUIRED=1` のときだけ、`?apply=1` の取り込みが一度も成功していない間は、新規・再投入の picks を空にし、`/status` に `launch_blocked: "no-import"` を出す (取り込み時刻は `imported_at`)。再投入の意図 (`oc-pm-intent`) による /oc の投稿も同じく止める (意図は処理済みにせず、取り込み後の tick で投稿する)。取り込み済み (`imported_at` がある) なら、フラグに関係なく通常どおり launch する。`wrangler.toml` の `[vars]` には置かない (本番で既定のまま止まる事故の再発防止。dashboard で入れた値は deploy で消える)。
- **反映の順序** (依頼者の操作。この変更は `wrangler.toml` を変えていない):
  1. この変更を反映する (「デプロイ」節の手順 4)。既定では取り込みを待たずに launch する。`/admin/import` はこの変更で初めて存在するので、反映の前には取り込めない。
  2. 上の手順で取り込む (`?apply=1`)。`curl -fsS "$PM_WORKER_URL/status"` の `imported_at` が時刻になったことを確認する。
  - `IMPORT_REQUIRED=1` を付けて反映すると、取り込みまで launch が止まる (`launch_blocked: "no-import"`)。付けるかどうかは依頼者の判断。付けた場合は、取り込んだ後に変数を外す (残すと、取り込みの確認なしで止まる状態が続く)。
- **取り込みの扱い**: 同じ issue が既に DO にあるときは、`launched`・`pm_art` は時刻が新しい方、`relaunch` は回数の多い方を残す。VM の凍結値が DO の新しい値を消すことはない (切替の後に DO が launch した issue の時刻は、VM の凍結値より新しい)。`relaunch` は VM だけが持つ履歴で、切替の前の `relaunch.json` (件数は `tools/pm/REPORT.md` §12-6) を Worker に入れる。これが無いと、履歴の無い issue を最大 2 回余分に再投入し得る。`phase` は取り込んだ値 (上の手順では DO の現在値) にする。取り込んだ `launched` が 3 時間以内の issue は `recent` に入り、着手したばかりの issue に二重に着手しない。取り込んだ値は全体同期 (`/admin/resync`) でも消えない。
- **書き出し**: `GET /admin/export` は VM の形式で返す (`launched`・`relaunch` (issue 番号のキーだけ。`np:<n>` は VM に無いので出さない)・`phase` (一度も保存していなければ null)・`pm_art`)。VM へ戻すときの順序は『切替』の節と `tools/pm/README.md` に従う (両方が live だと二重投稿になる)。
- **往復の例外**: 書き出した JSON を取り込み直して通るのは、許可内の値だけ。Worker の webhook は PM の `oc_artifacts:` 行を検証せずに保存するので、許可外の素材名の行 (例: `oc_artifacts: fetchsh`) が `pm_art` に入ると、その行の書き出しは取り込み直しで 400 になる。取り込みではその行は消えず、新しい PM 投稿で上書きされるまで残る。`phase` が一度も保存されていないとき (最初の tick の前) は `phase` が null で、取り込み直しは 400 になる。取り込み直しの前に、書き出しの `pm_art` の行と `phase` を確認する。
- **認証**: `/admin/resync` と同じ。入口 (`index.ts`) と DO (`app.ts`) の両方で確認し、未認証・不明な token・読み取りだけの token・メソッドの違いは 404 で、DO の状態に触れない。

## 同期の窓と打ち切り

- 全体同期 (6 時間ごと) と reconcile (5 分ごと) は、GitHub の一覧を `per_page=100` のページで読む。`Gh.list` は、上限ページで止めて続きがあるときだけ `truncated=true` を返す
  (上限ちょうどで読み尽くしたときは、次の 1 ページを読んで空 (または窓の外だけ) なら `false`)。
- コメントは `sort=created&direction=desc` で**新しい順**に読み、`created_at` が窓より古いコメントに達したら止める。窓は全体同期で `COMMENT_WINDOW_H` 時間 (既定 24。24 未満は 24)、
  reconcile は `reconcileAt - 2 分`。ページ上限は `COMMENT_MAX_PAGES` (既定 80 = 8,000 件。`wrangler.toml` の値は実測に合わせて引き上げてある)。
  状態に使うコメント (bot と PM) 以外は本文を持たない。`botLast` / `botReport` / `pmArt` / `launchedAt` は適用の順序に依らず `created_at` (同時刻は comment id) が最新のものになる。`botReport` は bot の投稿のうち run-outcome と PM のマーカーを含まないものの最新 (停止報告の素材名の入力。`botLast` は run-outcome で上書きされるので別に持つ。古い保存値には無い)。
- PR は全体同期で open を全件・closed を `sort=updated&direction=desc` で窓の中だけ読む (`state=all` の全件は PR の増加で上限を超える)。reconcile も起点より古い更新で止める。
- 打ち切った一覧は `meta.syncTruncated` (対象名・読んだページ数・時刻。本文・題名は入れない) に残し、1 件でもあれば `fresh=false`。同じ一覧を次に読んで打ち切りが無ければ自動で消える。
  打ち切ったときは『一覧に無い』ことを根拠にした close / completed 扱い (issue・PR・run) をしない。`/status` は `sync_truncated` と `last_full_sync_rest_calls` (全体同期の REST 回数。うちコメントは `last_full_sync_comment_rest_calls`) を出す。

## ファイル構成

- `src/index.ts` Worker の入口 (対象外のイベントは DO を起こさず捨てる)。`src/do.ts` Durable Object `PmDO` (SQLite の `kv` 表 + alarm)。
- `src/app.ts` HTTP 面 (`/webhook` `/setup` `/setup/callback` `/status` `/tick`)。`src/engine.ts` 同期・分類・launch・watchdog・status。`src/ratelimit.ts` `src/redact.ts` は #2338 の rate limit の解釈と自由文の redact (純関数)。`src/saturation.ts` は #2381 の同時実行の上限の推定 (純関数)。`src/active.ts` は同時実行の計数 (上の 6。純関数)。
- `src/webhook.ts` `src/classify.ts` `src/launch.ts` `src/hmac.ts` は純関数 (#1751 / #1795)。`src/pm.ts` (oc-pm の検出・抑止) と `src/needs.ts` (PM 判断を求める語彙) も純関数 (#2333)。`src/halt.ts` (launch の停止の判定と区間・通知の期限。#2795) も純関数。
- `src/store.ts` `src/route.ts` は #1882 の entity 単位の SQLite 増分保存 (`receiveWebhook`)。`src/kvstore.ts` は Engine が使う汎用の保管 (bucket/key)。
  Worker の本番経路は `index.ts` → `do.ts` → `app.ts` → `engine.ts` (kvstore)。`store.ts` / `route.ts` は #1882 のテスト (`test/route.test.ts`) で検証される増分保存の実装で、
  PmState の全 entity (pmArt / blockedBy / launchedAt を含む) を保存・読み出せる。経路の一本化は #1882 側の判断 (本 PR では両方を残す)。

## テスト

```
cd infra/pm-worker && npm test      # Node >= 22.6 (--experimental-strip-types)。依存パッケージなし。Python 3 が要る (突き合わせ)
cd infra/pm-worker && npm run test:unit   # vitest (fetch モック・workerd なし)。test/unit/。/admin/resync と失敗配送の回収 (#2339) のネガコン・/oc 投稿の観測 (#2342) のネガコン・VM の状態の取り込み (#2343 test/unit/vm_import.test.ts)
cd infra/pm-worker && npm run test:workers # vitest + workerd (実 Durable Object)。test/runtime/
cd infra/pm-worker && npm run test:mutation # launch の停止の規則 (#2795) を 1 か所ずつ壊し、test/halt*.test.ts が落ちることを確かめる (7 変異)
```

依存は pnpm (`pnpm-lock.yaml`)。`pnpm install --frozen-lockfile` を先に実行する (`test:unit` と `test:workers` は devDependencies の vitest を使う)。`npm test` は依存なしで動く。既定設定 (`minimumReleaseAge` を変えない) の `pnpm install --frozen-lockfile` が通る版の組を lock に入れてある (理由と版の選び方は『Workers Builds の接続状態と pnpm 経路』の節の release-age の項)。

`npm run build` は bun、デプロイは wrangler を使う。wrangler は `login --device` がある版 (公式 docs の例は 4.119.0 の出力。VM は 4.151.0 で `--device` の存在を `wrangler login --help` で確認済み)。VM では root 不要で `$HOME/.local/bin` に置く
(`npm install --prefix $HOME/.local/wrangler wrangler@<版>`、bun は npm の `bun` パッケージ)。

## デプロイ (dry-run)

### 依頼者の操作 (デプロイ前に 1 回)

VM のシェルで `wrangler login` を行う。VM にブラウザが無く localhost の callback (8976) に届かないため `--device` を使う。

```
wrangler login --device --browser=false
```

表示された URL (`https://dash.cloudflare.com/oauth2/device`) を手元のブラウザで開き、表示されたコードを入力して **Allow** を押す (コードの有効期限は 5 分。切れたら再実行)。
ログインする Cloudflare のメンバーには、後述の **Workers の Admin** (Workers product スコープ) が要る。デプロイ後も `wrangler logout` はしない。保存された OAuth を VM に残し、以後の再デプロイに PM が使う (PM 判断 2026-10-14、#2357。手順は後述の「再デプロイ」)。新規 API token は作らない。

### 必要な Cloudflare の権限

- **新規 Worker の作成 (初回の `wrangler deploy`) には、Workers の `Admin` (Workers product スコープ) が要る。`Workers Scripts: Edit` (= Workers の `Editor`) では足りない。**
  公式: 「Creating new Workers requires product-level `Admin` access」「per-Worker permissions can only apply to Workers that already exist」。
  根拠: <https://developers.cloudflare.com/workers/authorization/workers/> (Wrangler の表に『Create a new Worker: product-level Admin』)、<https://developers.cloudflare.com/workers/authorization/> (Common access patterns: 『Create or delete Workers: Workers product / Admin』)。
- `Editor` で足りるのは**既存 Worker** の更新: script・settings・schedules (cron)・versions・deployments・`wrangler secret put` まで。作成と削除はできない。2 回目以降の deploy と `STORE_KEY` の更新は `Editor` でよい。
- Durable Object には別の権限は無い。DO を実装する Worker への Workers ロールで決まる (<https://developers.cloudflare.com/workers/authorization/durable-objects/>)。
- 旧名との対応: `Workers Scripts: Edit` = `Editor`、旧 `Workers Admin` (改名後 `Workers Platform Admin`) = `Admin` (Developer Platform スコープ)。旧名の対応表は上の Workers ページの『Legacy Workers permissions』、改名は <https://developers.cloudflare.com/changelog/post/2025-06-16-workers-platform-admin-role/>。
- 補足: `wrangler login` の OAuth は、粒度の細かい権限 (granular authorization) に未対応と公式にある (<https://developers.cloudflare.com/workers/authorization/>)。OAuth で Worker を作れるかどうかは、ログインしたメンバー自身のロール (Workers の Admin か、アカウントの Administrator 等) で決まる。公式には、API token は『platform-level の権限を持てない』とある。この手順は API token を作らず OAuth だけを使う (指示 4・9)。
- 未確認 (docs に記載なし): `workers.dev` サブドメインの有効化 (`POST .../subdomain`) と、アカウントに workers.dev のサブドメインが未登録のときの登録に必要な権限。

```
npm run build                                   # dist/index.js (bun)
npm run metadata > metadata.json                # wrangler.toml と同じ bindings / migration
# PUT /accounts/{id}/workers/scripts/signature-studio-pm  (multipart: metadata + index.js (application/javascript+module))
# PUT /accounts/{id}/workers/scripts/signature-studio-pm/schedules  [{"cron":"* * * * *"}]
# POST /accounts/{id}/workers/scripts/signature-studio-pm/subdomain  {"enabled":true}
# PUT /accounts/{id}/workers/scripts/signature-studio-pm/secrets  {"name":"STORE_KEY","text":"<32 バイトの base64url>","type":"secret_text"}
```

`wrangler deploy` でも同じ (`wrangler.toml`)。`STORE_KEY` は `openssl rand -base64 32 | tr '+/' '-_' | tr -d '='` で作り、シェルの履歴・ファイル・ログに残さない。
`LIVE_LAUNCH` / `LIVE_DISPATCH` は、初回のデプロイでは `"0"` (dry-run)。今の `wrangler.toml` は `"1"` (下記『切替の記録』)。

## 依頼者の操作 (1 回、ブラウザ)

1. `https://signature-studio-pm.<subdomain>.workers.dev/setup` を開く。
2. **Create GitHub App** を押す (org `signature-studio` の owner。App 名は `oc-pm-for-signature-studio`)。
3. 次の画面で **Install** を押し、`signature-studio-dev` だけを選ぶ。

App の id・private key・webhook secret は Worker が受け取って暗号化保管する。依頼者には表示されない。
権限: issues write / pull_requests write / contents write (`repository_dispatch` のため) / actions read / metadata read。

## 切替の記録 (2026-10-14、#2443)

VM の `pm-launch.timer` `pm-watchdog.timer` は依頼者の指示で停止済み。Worker が着手と `oc-watchdog` の dispatch を担う状態にするため、`LIVE_LAUNCH` `LIVE_DISPATCH` を `"1"` にした。VM の timer は**再開しない**。

- 前提 (merged): #2398 (Review-Only と `oc:stuck` の上限)、#2418 (LIVE の分離)、#2420 (#2380 コメントを新しい順に 24 時間分読む)、#2422 (#2338 `/status` の観測・redact・rate-guard。Worker の REST 残量が 1,500 未満の間は launch を止める)。未 merge の #2343 (VM 状態の取り込み)・#2334 (no-pr の理由別再着手)・#2340 (shadow の自己昇格) は前提から外した。VM が止まっているので二重着手の窓が無く、phase は『open PR < 10 で解除』の規則で足りる。
- merge 後に動く版は #2422 (rate-guard) と #2423 (#2333 oc-pm) を含む (この PR の差分には無い)。rate-guard は Worker の REST 残量 (`rest_remaining`) が 1,500 未満の間 launch を止める (`launch_stop: rate-guard`。未観測の間は止めない)。**`LIVE_DISPATCH="1"` は `oc-pm` (PM agent の起動) も送る**(別スイッチは無い。上限は全体で 1 時間に 12 起動・同じ (kind, ref) は 60 分に 1 回・同じ ref に 24 時間で 3 回。pm job の token は issues / pull-requests の write だけで contents を持たない)。止めるときは `LIVE_DISPATCH="0"` (`oc-watchdog` も止まる)。oc-pm を含めて live にするのは既定案 (#2319 の設計どおり)。PM の判断は PR #2453 の未解決表と PM のコメントに記録した。突き合わせはこの版 (`e88e1890`) で測り直した。
- 暫定の安全装置: `TARGET="50"` (最初の 1 時間。80 に戻す作業は #2458)。`NO_PR_COOLDOWN_H` は 24 から 6 に短縮した (#2650。理由別の再着手の規則 (上の 3.) が入ったため。値は下の表)。`TARGET` は後で『opencode.yaml の全 run の総数の目標』に意味を改め、既定を 58 にした (上の 6。#2458 は置き換え)。Review-Only は `phase.ts` / `engine.ts` が既に持つ (open PR が 80 超で launch しない、`oc:stuck` が `STUCK_HIGH` 超で止める)。
- 突き合わせ: dry-run の Worker と VM の `launch_issues.py` の差は、open な子を持つ親の除外・`pm-apply` の user 扱い・`oc:no-pr` の cooldown・VM の `relaunch.json` の有無で説明がつく (推定を含む。測定は #2422・#2423 を含む版。内訳と未解決は `tools/pm/REPORT.md` §12)。(この版の時点では `NO_PR_COOLDOWN_H` の既定 3 が `oc:no-pr` の issue を大量に候補へ戻すので 24 にしていた。#2650 で、理由別の規則に合わせて 6 にした。)
- 初回のデプロイ (2026-10-14) では、保存状態を整える一時ビルド (全体同期の前倒しと、phase を VM の `phase.json` に合わせる) を使った。リポジトリの差分には無い。理由と結果は `tools/pm/REPORT.md` §12-5。その後も保存 outcome の欠落が観測されている。観測と計測は `tools/pm/REPORT_APPENDIX_2652.md` §4・§5、原因の追跡は子 #2757 (根因は未特定)。保存状態の補完は下の『保存値の版 (`SIGNAL_VER`) を上げる』の仕組みで行う想定だが、その効果は本番で未確認。
- 後から入れる取り込み (『VM の状態の取り込みと書き出し』) では、取り込みの `phase` に DO の現在値を使う (VM の `phase.json` は切替の時点で凍結されている)。反映の時点で launch が取り込みまで止まる (同節の『反映の順序』)。

戻し方 (VM の timer は再開しない): `wrangler.toml` の `LIVE_LAUNCH` を `"0"` にして再デプロイ (`npx wrangler deploy`)。dispatch も止めるなら `LIVE_DISPATCH` も `"0"`。`/status` の `mode_launch` / `mode_dispatch` が `dry-run` になる。`STORE_KEY` は変わらない。

## 保存値の版 (`SIGNAL_VER`) を上げる (#2652)

派生値 (issue の起票者 `author`・`assoc`、PR・issue の手がかり `sig.outcome` など) を作る規則を変えたら、`src/engine.ts` の `SIGNAL_VER` を 1 上げて deploy する (現行は 2)。版は全体同期が完了したときに `meta.signalVer` へ記録する。保存値の版が `SIGNAL_VER` と違う最初の tick は、周期 (6 時間) を待たずに全体同期を 1 回走らせて、古い保存値を補完する。その全体同期が失敗したときは `SIGNAL_RETRY_MS` (15 分) ごとに再試行し、それより頻繁には叩かない。上げると次のことが起きる: (1) 全体同期の REST 呼び出しが 1 回増える (周期の全体同期と同じ量)。(2) 補完で新たに `no_pr` の対象になった issue の oc-pm 起動が増え得る (全体で 1 時間 12 件まで。同じ (kind, ref) は 60 分に 1 回)。(3) `artifact` の再投入の候補も増え得る。deploy 前の `/status` の `pm_detected` は今の保存値から数えた値なので、版の補完で増える件数は deploy 前には見えない (REST で再計算した件数は `tools/pm/REPORT_APPENDIX_2652.md` §5)。deploy は `LIVE_LAUNCH` / `LIVE_DISPATCH` の状態を確認してから行う (merge とデプロイは別)。

全体同期が一覧を打ち切った (`sync_truncated`) ままでも版は記録する。打ち切りは `Gh.list` のページ上限に一覧の件数が届いたときに起きる (上の『同期の窓と打ち切り』)。窓 (`COMMENT_WINDOW_H`) が読む量を決めるのはコメントの一覧だけで、open の issue・PR の一覧は窓に依らない。そのため 15 分後の再試行も同じ打ち切りになりやすい (推定。再試行は REST を増やすだけになる)。打ち切りが残る間は `fresh=false` で launch と watchdog の dispatch が止まり、周期の全体同期 (6 時間) が次の機会になる。

## 切替 (PM の判断)

> **旧案 (段階的な切替) の記録。** 2026-10-14 の切替は上の『切替の記録』の手順で行った (`LIVE_LAUNCH` と `LIVE_DISPATCH` を一度に `"1"`、VM の timer は再開しない)。戻し方は『切替の記録』が正本。下の A・B にある『VM の timer を再開する』は VM の timer を使っていた当時の手順で、今は使わない。

スイッチは `wrangler.toml` の `[vars]` にある 2 つ。値は秘密ではない (`wrangler secret` は使わない)。`"1"` だけが live で、それ以外 (`"0"`・`""`・`"true"`・未設定) は dry-run。

| 変数 | 経路 | `wrangler.toml` の既定 |
|---|---|---|
| `LIVE_LAUNCH` | launch の `/oc` コメント投稿 (`POST /repos/{o}/{r}/issues/{n}/comments`) | `"1"` (2026-10-14〜。コードの既定は dry-run) |
| `LIVE_DISPATCH` | `repository_dispatch` の送信 (`POST /repos/{o}/{r}/dispatches`)。`oc-watchdog` と、oc-pm 節の `oc-pm` (PM agent の起動) の両方。別スイッチは無い | `"1"` (同上) |
| `LIVE` (旧) | 上の 2 つのうち、未設定のほうにだけ効く (両方の既定値) | (置かない) |
| `LIVE_CLOSE` | 規則 A の自動 close (コメント + `state=closed`)。`"1"` のときだけ書く。`LIVE` では動かない | 未設定 (dry-run)。`wrangler.toml` には置かない |
| `TARGET` | 同時に走らせる **opencode.yaml の run の総数** の上限 (room = target_eff − active_all。`active_all` は実装・review・fix・oc-pm・watchdog の全て。推定が無ければ target_eff = TARGET。推定の仕組みは『同時実行の上限の推定』) | `"58"` (上限 60 から 2 を残す。以前の暫定 `"50"` と、80 に戻す案 #2458 は置き換えた) |
| `QUEUE_MARGIN` | 推定の上限 (`cap_est`) に足す余裕。`target_eff = min(TARGET, max(TARGET_MIN, cap_est + QUEUE_MARGIN))` | 未設定 (コードの既定 10) |
| `TARGET_MIN` | `target_eff` の下限 | 未設定 (コードの既定 30) |
| `NO_PR_COOLDOWN_H` | `oc:no-pr` の issue を再着手するまでの時間。`prio:critical` の issue は半分 (#2683) | `"6"` (コードの既定も 6。#2650 で 24 から短縮) |
| `LOW_CAP` | `prio:low` の issue の未完了の run の上限。`prio:critical` が着手済みか launch 可能な間だけ効く (#2721)。空・非数・負は既定に戻す | `"10"` (`config.ts` の `DEFAULT_LOW_CAP` と同じ) |

個別の設定があれば `LIVE` より優先する (`LIVE=1` かつ `LIVE_LAUNCH=0` なら launch だけ dry-run)。`LIVE=1` だけの旧デプロイは従来どおり両方 live。
切替は `[vars]` を書き換えて**再デプロイ**する (`cd infra/pm-worker && npx wrangler deploy`。`STORE_KEY` の secret は変わらない)。リポジトリと稼働中の値を一致させるため、書き換えは PR で merge してから、その main でデプロイする。

### A. repository_dispatch を先に live にする (oc-watchdog と oc-pm)

`LIVE_DISPATCH` を `"1"` にすると **oc-pm も live になる** (oc-pm 専用のスイッチは無い)。launch は dry-run のまま。
`oc-watchdog` の送信は Actions の watchdog job を起こすだけで、VM の `pm-launch.timer` と二重着手にならない (watchdog job は同じ concurrency group `opencode-watchdog` で直列。`cancel-in-progress: false`)。
Worker が送る type は `oc-watchdog` と `oc-pm` の 2 つだけ。`oc-watchdog` は `DISPATCH_TYPES` (`src/github.ts`) を通り、payload は `{"event_type":"oc-watchdog"}` のみで `client_payload` を持たない。`oc-pm` は `dispatchPm` だけが送り、payload は `kind` と `ref` だけ。`oc-fix` (PR 番号・理由・素材名の `client_payload` を検証して送る) は Actions の `watchdog.sh` の仕事で、Worker は送らない。

1. 本 PR を merge する。
2. `wrangler.toml` の `LIVE_DISPATCH` を `"1"` にして (`LIVE_LAUNCH` は `"0"` のまま)、`npx wrangler deploy --dry-run` で bindings を確かめてから再デプロイする。切替の前に `GET /status` の `pm_detected` (kind ごとの検出数) を確認する。0 以外があれば、切替後すぐに対象の oc-pm が送られる (PM agent が起動する)。
   `GET /status` が `mode_dispatch: "live"`・`mode_launch: "dry-run"`・`mode: "partial"` になる。
3. Worker 由来の `repository_dispatch` の run が届くことを確認する (VM 由来の actor は `pycabbage`、Worker 由来は `oc-pm-for-signature-studio[bot]`):
   `gh api "repos/signature-studio/signature-studio-dev/actions/runs?event=repository_dispatch&per_page=10" --jq '.workflow_runs[]|"\(.created_at) \(.display_title) \(.triggering_actor.login)"'`
   併せて `GET /status` の `counters.dispatched` が増え、`last_watchdog` が 5 分ごとに進むこと。ここまでの間は VM の ping も動いている (どちらかが欠けても watchdog は途切れない)。
4. VM の `pm-watchdog.timer` を止める: `systemctl --user disable --now pm-watchdog.timer`。
5. 24 時間後にも watchdog の run が途切れないことを確認する (`display_title` が `watchdog` の run の間隔が 10 分以内であること。送信が重なる期間に、待機中の run が後続の run に置き換わって `cancelled` になるのは正常):
   ```
   S=$(date -u -d '24 hours ago' +%FT%TZ)
   gh api --paginate "repos/signature-studio/signature-studio-dev/actions/runs?event=repository_dispatch&per_page=100&created=%3E%3D$S" \
     --jq '.workflow_runs[]|select(.display_title=="watchdog")|.created_at' | sort | python3 -c 'import sys,datetime as d; t=[d.datetime.fromisoformat(l.strip().replace("Z","+00:00")) for l in sys.stdin if l.strip()]; g=[(b-a).total_seconds() for a,b in zip(t,t[1:])]; print(len(t),"runs, max gap",max(g),"s")'
   ```

戻す場合 (旧案。今は『切替の記録』の戻し方に従い、VM の timer は再開しない): `pm-watchdog.timer` を `enable --now` で再開し、`LIVE_DISPATCH` を `"0"` にして再デプロイする (oc-pm の送信も止まる)。

### B. launch を live にする

1. dry-run の出力 (`GET /status?detail=1` の `would_launch_now` と `log`) を、VM の `launch_issues.py plan` と数時間比較する。
2. 一致したら `LIVE_LAUNCH` を `"1"` にして再デプロイする (A の後なら `mode` が `live` になる)。同時に Actions 側の `vars.OC_PM_BOT_LOGIN` に `GET /status` の `pm_bot_login` (`oc-pm-for-signature-studio[bot]`) を設定する (別 issue)。
3. VM の `pm-launch.timer` を止める (A を済ませていなければ `pm-watchdog.timer` も)。
4. 戻す場合 (旧案。今は『切替の記録』の戻し方に従い、VM の timer は再開しない): `LIVE_LAUNCH` を `"0"` にして再デプロイし、VM の timer を再開する (VM 版は変更していない)。同期が壊れたら `/status` の `fresh` が false になり、Worker は投稿しない。

## 再デプロイ (PM。VM に残した wrangler の OAuth)

Worker のコード (`src/`・`wrangler.toml`) を変更して main に merge したら、PM が VM から再デプロイする。認証は初回デプロイで保存された OAuth を使う (wrangler が refresh token で access token を自動更新する)。
Workers Builds の接続状態は後述の『Workers Builds の接続状態と pnpm 経路』を見る。デプロイするのは **main に merge 済みの commit だけ**。以下のコマンドは wrangler 4.151.0 で、`--help` とソース、認証なしで実行できるものは実行して確認した。実 Worker への実行は未確認の項目として最後に列挙する。

1. 認証の確認 (token の値は表示しない・書かない)。

   ```
   cd infra/pm-worker
   wrangler whoami --json
   ```

   終了コード 0・`loggedIn` が `true`・`authType` が `OAuth Token` ならよい。`--json` を付けない `wrangler whoami` は、資格情報が無い環境でも終了コード 0 になる (`--json` は 1。認証なしの環境で確認)。判定には `--json` を使う。
   `authType` が `OAuth Token` でないときは、環境変数の token が OAuth より優先されている。止めて原因を調べる (この VM に token の環境変数を置かない。指示 4・9)。失敗したら後述の「OAuth が失効したとき」。
   OAuth の保存先 `~/.config/.wrangler/config/default.toml` は平文で token を含む。中身を表示・commit・コメントに貼らない。
2. 戻し先の記録。デプロイ前に `wrangler deployments status` を実行し、稼働中の version id を控える (ロールバックの戻し先)。あわせて `curl -fsS "$PM_WORKER_URL/status"` の `mode` `mode_launch` `mode_dispatch` `fresh` `last_tick` を控える (`PM_WORKER_URL` は `tools/pm/README.md` の `pm_gate.sh` と同じ)。
3. ビルドの確認: `wrangler deploy --dry-run --outdir <作業用の一時 dir> --var BUILD_COMMIT:<commit hash>`。認証なしで通り、bindings の一覧 (`PM` と `[vars]` と `BUILD_COMMIT`) が出る (`BUILD_COMMIT` の値は `(hidden)` で表示される)。migration の有無はここでは分からない。
4. デプロイ: 作業する commit は main に merge 済みの HEAD (`git rev-parse HEAD` の全 40 字) にして、次のように渡す。`wrangler deploy --var BUILD_COMMIT:<commit hash 全体> --tag <commit の先頭 7 桁> --message "<commit hash> <issue または PR の番号>"`。`--tag` `--message` は version に付き、`wrangler deployments status` と `wrangler versions list` に出る (ロールバックで戻し先を選ぶ手がかり)。`--var` の値は `/status` の `build` に出る (手順 5)。
   - **`BUILD_COMMIT` の渡し方 (#2416)。** `--var` を選んだ理由: (a) Worker のコードを書き換えない。(b) `wrangler.toml` の `[vars]` には置かず、deploy のたびに CLI から渡す。`--keep-vars` なし (既定) では前回の deploy の値を残さない指定にあたるので、渡し忘れた deploy の `build` は古い hash ではなく `null` になると読んだ (実機の確認は末尾の `[未確認]`)。(c) CLI の `--var` は `[vars]` の同名キーより優先される (wrangler 4.151.0 のソース `cli.js` で、CLI の値を config の binding の後に入れることを確認。dry-run で `--var TARGET:999` を付けると `TARGET` が `58` (`wrangler.toml`) から `(hidden)` に変わることも確認)。`--define` は採らない。`--define BUILD_COMMIT:<hash>` (引用符なし) は、hash が数字で始まると `Invalid define value` で build が失敗する (英字で始まると通るが、hash は bundle に入らない)。`--define 'BUILD_COMMIT:"<hash>"'` (引用符付き) は build が通るが、`env.BUILD_COMMIT` の参照は定数置換されず、hash は bundle に入らない (dry-run で確認。測定は `tools/pm/REPORT_2416.md` §3)。
   - **`[vars]` は deploy のたびに `wrangler.toml` の値で置き換わる。** `--keep-vars` なしの既定では、dashboard 等で変えた var は消える (`wrangler deploy --help` の説明)。特に `LIVE_LAUNCH` / `LIVE_DISPATCH`: dashboard 等で変えても、再デプロイすると `wrangler.toml` の値 (2026-10-14 以降は `"1"`) で置き換わる。切替の手順は「切替」節 (A・B) が正本で、値を変えるときも `wrangler.toml` を変えて merge してから deploy する (正本はリポジトリ)。デプロイ前に手順 2 の `mode` `mode_launch` `mode_dispatch` を見て、意図しない `live` → `dry-run` の変化が出ないことを確かめる。
   - secret (`STORE_KEY`) は deploy で消えない (ソースで `keepSecrets: true`、`--help` に『secrets are never deleted by deployments』)。`STORE_KEY` を作り直さない (App の鍵が復号できなくなる)。
   - Durable Object のコードを変えるだけなら migration は要らない (公式: <https://developers.cloudflare.com/durable-objects/reference/durable-object-class-migrations-legacy/>)。migration は適用済みの tag を飛ばして、新しい tag の分だけが deploy 時に適用される。現在の `wrangler.toml` は `v1` (`new_sqlite_classes = ["PmDO"]`) だけ。`[[migrations]]` を足す変更は、ロールバックできなくなる境界を作る (後述)。単独の PR・単独のデプロイにする。
5. 反映の確認。
   - `wrangler deployments status` に、手順 4 の `--tag` と `--message` を持つ version が 100% で出る。出力の項目 (version id・Created・Tag・Message) はソースで確認した。実 Worker での表示は未確認 (末尾のチェックリスト)。
   - `curl -fsS "$PM_WORKER_URL/status"` が応答し、`fresh` が `true`、`last_tick` が deploy 後の時刻に進む。
   - `curl -fsS "$PM_WORKER_URL/status"` の `build` が、手順 4 で `--var BUILD_COMMIT:` に渡した commit hash (全体) と一致すること。`null` のままなら、その deploy は `--var` を付けずに出ている (反映とは判断しない。手順 4 をやり直す)。`build` は公開の `/status` にも出る (集計の一部で、秘密ではない)。
   - 反映の判定は `/status` の `build` で行う (外から見られる。watchdog や他の agent も同じ確認ができる)。`wrangler deployments status` の Tag / Message は、wrangler にログインした VM で 100% の version を確かめる補助に使う。

## ロールバック

1. 戻し先を決める。`wrangler versions list` (直近 10 件) または `wrangler deployments status` で、手順 4 の Tag / Message から選ぶ。
2. `wrangler rollback <version-id> --message "<理由>"`。`--message` を付けると確認の prompt が省かれる。version id を省くと『最新の 1 つ前に upload された version』に戻る (公式: <https://developers.cloudflare.com/workers/wrangler/commands/workers/#rollback>)。戻すと新しい deployment ができ、全 route で即座に有効になる。
3. 戻し先の `build` を見る。`curl -fsS "$PM_WORKER_URL/status"` の `build` が、戻し先の version を deploy したときに `--var BUILD_COMMIT:` へ渡した commit hash (全体) と一致すること。戻し先が `--var` なしの version なら `build` は `null`。`fresh`・`last_tick` の確認は「再デプロイ」の手順 5 と同じ。戻し先の `BUILD_COMMIT` が戻るかは末尾の `[未確認]` の項目。戻した理由と戻し先の version id を、起点の issue に書く。**main に問題の commit が残ったままだと、次の再デプロイで同じ版がまた出る。** revert の PR を出すか、修正を merge してから再デプロイする。

制約 (公式: <https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/>):

- 戻せるのは直近 100 version まで。
- **Durable Object のクラス lifecycle の変更 (`[[migrations]]` の追加) を跨いでは戻せない。** 現在の稼働中 version と戻し先の間に migration の追加があると、rollback は拒否される。本 Worker は `v1` 1 件だけなので、`v1` を含む version 同士の rollback は、公式の記述では可能と読める (実機では未実行: 後述 [未確認])。
- rollback で戻るのはコードだけで、binding の先 (DO の SQLite の保存内容) は戻らない。DO に保存する形式を変える変更は、旧コードが新しい形式を読める (後方互換) ようにしてから出す。公式にも『データの構造が変わると、旧 version のコードでエラーが起きうる』とある。
- OAuth が失効している間は、`wrangler rollback` も実行できない。dashboard の Workers & Pages → 対象 Worker → Deployments → Rollback でも戻せるが、dashboard へのログインは依頼者の操作になる。

## OAuth が失効したとき

**検知。**

- 再デプロイ・ロールバックの直前の `wrangler whoami --json` が、終了コード 1 で失敗する。OAuth の失効を自動で知らせる経路は無い。Worker は OAuth を使わない (デプロイ操作だけが使う) ので、失効しても Worker は止まらず、Worker 側の監視 (`/status`) にも出ない。
- Worker 自体の停止は別: `/status` の `fresh=false` または応答なしを watchdog が検知して `[CI] PM Worker 停止` の issue を起票する設計 ([CI-49] #2328)。**この文書の作成時点 (main 0ca7f8c5) で #2328 は open で、`.github/scripts/watchdog.sh` に該当の処理は無い** (`PM Worker 停止` の grep が 0 件)。実装されるまでは、停止も自動では検知されない。
- wrangler の挙動 (4.151.0 のソースで確認): access token は期限が切れたときだけ refresh token で更新される。refresh が拒否されたとき、TTY が無い・CI の環境では『`Not logged in. Your auth token has expired and could not be refreshed, and the environment is non-interactive.`』で失敗する。TTY のある端末では、ブラウザでの再ログインが自動で始まる。Cloudflare に届かないだけのときは別の理由 (`token-refresh-unreachable`) で、保存済みの資格情報は変更されない。
- 擬似的な再現: 隔離した設定 dir に、期限切れの access token と無効な refresh token を入れて `CI=1 wrangler whoami` (`--json` の有無を問わず) を実行すると、終了コード 1 で上のメッセージが出た。これは実機の失効 (Cloudflare 側で refresh token が失効した場合) の再現ではない。
- エラー文は、`CLOUDFLARE_API_TOKEN` を設定する方法も案内する。**この手順では従わない** (token を作らない・設定しない。指示 4・9)。

**失効している間の状態。** 稼働中の Worker は、最後にデプロイしたコードのまま動き続ける (webhook・Cron・alarm・DO は Cloudflare 側で動く)。遅れるのは『コード変更の反映』と『ロールバック』だけ。main に merge した修正は、再認証までデプロイされない。

**対処。** 再認証にはブラウザでの承認が要るので、依頼者の操作になる。

1. 依頼者が VM のシェルで `wrangler login --device --browser=false` を実行する。表示された URL を手元のブラウザで開き、コードを入力して **Allow** を押す (コードの有効期限は 5 分。切れたら再実行)。ログインするメンバーのロールは、既存 Worker の更新だけなら `Editor` で足りる (上の「必要な Cloudflare の権限」)。
2. 実行後に `wrangler whoami --json` が通ることを確認し、保留していた再デプロイをする。
3. 依頼者が不在のときは待たない。`needs-user-input` の issue に積む (既定案: 『再認証まで反映を遅らせる』。他の作業は止めない。`docs/WORKFLOW.md` §12)。

## Workers Builds を接続しない理由

> **注意 (#2585)**: 下の判断 (接続しない) は、2026-10-14 の実測で Workers Builds のビルド記録が見えた事実と食い違う。接続の有無と判断の見直しは PM (#2357) が決める。接続の状態と pnpm 経路の注意は次の節を見る。接続した場合、Workers Builds の deploy には `--var BUILD_COMMIT` が付かないので、その版の `/status` の `build` は `null` になる (推定。未確認)。

Workers Builds (Cloudflare 側に repo を接続し、main への merge で自動ビルド・デプロイする機能) は、既定ではビルド用の API token を Cloudflare がアカウントに**自動で発行**する (公式: <https://developers.cloudflare.com/workers/ci-cd/builds/configuration/#api-token>)。依頼者の指示 4・9 (無断で token を作らない・secrets を平文で保存しない) の趣旨に反しうるため、PM 判断 (2026-10-14、#2357 [CI-78]) で接続しないと決めた。代わりに、上の手順で PM が VM の OAuth を使って再デプロイする。引き換えに、merge から反映までは PM の操作を待ち、OAuth が失効している間は反映できない (稼働中の Worker は止まらない)。依頼者が判断を変えたら、#2357 を再開して判断する。

## Workers Builds の接続状態と pnpm 経路 (#2585)

- **Workers Logs (observability)**: `wrangler.toml` の `[observability]` (`enabled = true`) が無いと、`wrangler deploy` は Workers Logs を無効にする設定を送る。`[observability]` の table は消さない。
- **pnpm 経路**: Workers Builds は、リポジトリ直下の `package.json` の `packageManager` (`pnpm@12.10.1`) から pnpm を選び、`infra/pm-worker` で `pnpm install --frozen-lockfile` を実行する。そのため `infra/pm-worker` は pnpm のプロジェクトにしてある。
  - `pnpm-lock.yaml`: `package-lock.json` から `pnpm import` で作った。版は変えていない。`package-lock.json` は置かない。
  - `pnpm-workspace.yaml` の `allowBuilds` (esbuild・workerd): pnpm 12 は既定で依存の build script を止める。無いと `ERR_PNPM_IGNORED_BUILDS` で install が落ちる。新しい依存が install script を持つときは、ここに足す。
  - `infra/pm-worker/package.json` に npm の `packageManager` を書かない。pnpm 12 は npm 指定のプロジェクトで実行を拒否する (`ERR_PNPM_OTHER_PM_EXPECTED`)。
- 確認の手順: `cd infra/pm-worker && pnpm install --frozen-lockfile && pnpm exec wrangler deploy --dry-run --outdir work/dryrun` (認証なしで通る。install が `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION` で落ちたら、下の release-age の項)。
- 2026-10-14 の時点で、Workers Builds の install 段は上の 2 点 (npm 指定と lockfile の無さ) で失敗していた (#2585)。merge 後の Workers Builds の結果は、この README では確認していない。
- **pnpm 12 の release-age (`minimumReleaseAge` = 1440 分)**: 公開から 24 時間未満の版は既定で install を拒否する。2026-10-14 05:43Z〜05:55Z 公開の `miniflare@5.20261012.0-beta`・`wrangler@4.151.0`・`@cloudflare/vitest-plugin@1.4.2` は、既定設定の `pnpm install --frozen-lockfile` を `ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION` で落とした (#2691 で実測)。そこで範囲を `wrangler` `^4.150.0`・`@cloudflare/vitest-plugin` `^1.4.1` に下げ、公開から 24 時間以上たつ版の組 (`wrangler@4.150.0` が依存する `miniflare@5.20261006.2-beta`・`workerd@1.20261006.1`) で lock を作り直した。
  - 除外しない理由: `minimumReleaseAgeExclude` や `--config.minimum-release-age=0` で通すと、公開直後の版が Workers Builds の token (権限が広い) で入る。このポリシーが防ぐ侵害の入口になるので、ポリシーは変えない。
  - 版の選び方: `pnpm view <pkg> time --json` で公開時刻を見て、24 時間以上たつ最新版を範囲に書く。lock に古い版が残ると範囲を書き換えても残るので、`pnpm remove <pkg>` の後に `pnpm add -D <pkg>@^<版>` で解決し直す。推移的な依存 (miniflare・workerd) も同じ確認の対象。
  - Workers Builds の install の結果 (merge 後) は、この README では確認していない (PM が確認する)。

## 確認できていない点 `[未確認]` のチェックリスト

公式 docs・wrangler のソース・認証なしで実行できるコマンドで確認できなかった点。推測では書かない。実 Worker で確かめたら、結果をここに移して `[未確認]` を外す。

- [ ] `[未確認]` refresh token の有効期間と失効の条件。公式 docs に記載を見つけられなかった (確認した範囲: `wrangler login` のページ、`wrangler auth token` の『automatically refreshed if expired』)。wrangler のソースでは、refresh の応答に新しい refresh token があればそれを保存し、無ければ従来のものを使い続ける。ただし有効期間が固定か、使うたびに延びるか、使わない期間が長いと失効するか、パスワード変更・ロール剥奪・ユーザーによる取り消しで失効するか、`--device` で得た token が通常の `wrangler login` と同じ寿命かは不明。確認の方法: 失効が起きたときの日時と、直前の `wrangler` 実行の日時を issue に記録して比べる。
- [ ] `[未確認]` 稼働中の script の `migration_tag` が `v1` か。wrangler は deploy 時にこの tag を取得して、`wrangler.toml` の最後の tag と同じなら migration を送らない (ソースで確認)。初回デプロイを REST (`scripts/metadata.mjs`) と `wrangler deploy` のどちらでしたかの記録が無く、tag が付いていなければ wrangler は `v1` を再送する。その場合に、既存の DO namespace に対して Cloudflare がどう応答するかは不明。確認の方法: 最初の再デプロイの出力に migration の適用が出ないこと。出たら止めて、依頼者に報告する。
- [ ] `[未確認]` `wrangler rollback` を本 Worker (migration は `v1` の 1 件のみ) で実行したときの成否。公式の制約は『lifecycle 変更を跨ぐと不可』で、本 Worker の `v1` 同士なら可と読めるが、実機では未実行。確認の方法: `LIVE_LAUNCH` / `LIVE_DISPATCH` を `"1"` にする前に、最初の再デプロイで 2 つ目の version ができた後、`wrangler rollback <旧 version> --message "rollback test"` で戻し、もう一度 deploy する。
- [ ] `[未確認]` rollback で `[vars]` (特に `LIVE_LAUNCH` / `LIVE_DISPATCH`) と Cron の schedule が戻し先の version の値に戻るか。公式は『binding の先は変わらない』とだけ書き、`[vars]` と schedule の扱いは書いていない。`LIVE_LAUNCH` または `LIVE_DISPATCH` が `"1"` の運用中に rollback すると、戻し先の値が `"0"` ならその経路が dry-run に戻る (投稿・dispatch が止まる) 恐れがある。`--var` で渡した `BUILD_COMMIT` (binding) も戻るかは未確認で、戻らないときに `build` が何になるか (戻す前の hash のままか、`null` か) も分からない。確認の方法: 上のテストの後に `GET /status` の `mode_launch` / `mode_dispatch` (と `mode`)・`build`、dashboard の Triggers の cron が残っていることを見る。
- [ ] `[未確認]` `wrangler deployments status` と `wrangler versions list` の実際の出力 (Tag / Message の表示を含む)。項目名はソースで確認した。実 Worker での表示は未確認。
- [ ] `[未確認]` `--var BUILD_COMMIT:<hash>` の値が、実 Worker の `/status` の `build` に出ること。`--var` を付けない deploy で `build` が `null` に戻ること (`--keep-vars` なしの既定。wrangler の help の説明どおりと読んだが、実機では未確認)。確認の方法: 次の再デプロイで手順 4 の hash を渡し、手順 5 の `build` が一致すること。`null` に戻る挙動は、`--var` を付けない deploy が次に行われたときに見る (テストのためだけの deploy はしない)。ローカルでは `wrangler deploy --dry-run` と vitest (node と workerd) で確認済み。
