# WORKFLOW — subagent 運用・PR・レビュー・検収 (repo 内正本)

本ファイルは**subagent 運用ルールの repo 内正本**である。外部 `[SUBAGENT-RULES]` (`docs/REFERENCES.md`) から
必要な規則を import して repo 内自己完結化したもの。

- 原本: `docs/REFERENCES.md` `[SUBAGENT-RULES]` (repo 外・凍結)。原本に無い規則はここに追加してよく、
  矛盾時は本ファイルを正とする。
- 旧 `preflight: RULES_SHA=...` 証跡は廃止 (`docs/DECISIONS.md` D6)。検証手順は本ファイル §6。
- Linear は 2026-10-12 に廃止。issue 管理は GitHub Issues。旧 `CAB-xxx` と issue `#N` の対応は
  `docs/REFERENCES.md` `[CAB_TO_GH]`。

---

## 1. 絶対遵守 (事故防止・上書き)

1. **`master` / `main` の共有ワークツリー (PM が管理する既定の作業ツリー) では作業しない。**
   変更は branch → worktree → PR のみ。`git push origin master` 禁止。
2. **禁止 git 操作**: `git reset` / `git reset --hard` / `git stash` / `git checkout -- <他人のfile>` /
   `git checkout .` / `git restore` / `git clean` / **`git push --force` / `--force-with-lease`**。
   他セッションのコミット・WIP を消す実事故が 2 件発生している。
3. **commit はスコープ付き** (`git add <自分のdir>` + `git commit -- <自分のdir>`)。`git add -A` / `git add .` 禁止。
   `flock /tmp/opencode/git.lock` で直列化する。
4. **誤りを見つけたら `fix(<name>): report corrections` で別コミットを積む** (reset/rebase -i で歴史を巻き戻さない)。
5. **最大 blob 20 MiB 超の commit 禁止。** `work/`・`__pycache__/`・`node_modules/` は commit しない (gitignore)。
6. **`tools/**/work/` と `tools/**/venv/` は vendored / 検証スナップショット。絶対に触らない・commit しない。**

## 2. フロー (branch → worktree → 実装 → レビュー → merge)

```
PM (main)                      subagent (実装)                  subagent (検収)
   │                                │                                  │
   ├ issue 起票 (PM。子 issue は実装も可 §3) ──┤                       │
   ├ worktree 指名 ─────────────────┤                                  │
   │                                ├ gh issue view N                  │
   │                                ├ git worktree add ../ws-N         │
   │                                ├ 実装 + e2e + REPORT              │
   │                                ├ commit (scope)                   │
   │                                ├ push -u origin <N>-<slug>        │
   │                                ├ gh pr create --base main         │
   │                                ├ gh issue comment N (進捗・実測)   │
   │                                └ ready PR を出して依頼 ───────────┤
   │                                                                   ├ 自分の worktree で
   │                                                                   │  PR branch を checkout
   │                                                                   ├ e2e 独立再実行 + 別算法検算
   │                                                                   ├ ネガティブコントロール
   │                                                                   ├ PR review (approve / request changes)
   │                                                                   └ 誤記は fix commit で同 branch に push
   ├ review approve 確認 ──────────────────────────────────────────────┤
   └ gh pr merge --merge ──→ branch/worktree 削除
```

- 流れ図の「issue 起票」は PM が行う。ただし実装 subagent も、1 run に収まらない実装・修復の作業の残りを子 issue として起票してよい (§3 の規定 (#835・#1758)。PR は自分の issue を `Closes #N` で閉じる。milestone・優先度は PM が確定する。Project の Status は参考で、§3)。
- **worktree の場所**: リポジトリの**親ディレクトリの `ws-<N>`**
  (`git worktree add ../ws-<N> -b <N>-<slug> origin/main`)。
  既存 worktree は `git worktree list` で確認。**他人の worktree には触れない** (消さない・checkout しない)。
- **merge の担い手**: 通常は reviewer App が approve 後の同じ run で merge し、PM は緊急時だけ merge する (下の「merge の担い手と main の Ruleset」節)。merge 後、`git worktree remove --force` で**自分が使った worktree** を片付ける。
- **競合時**: `git rebase origin/main` で解消してから `push --force-with-lease` (自分 branch のみ)。
- **既定ブランチは `main`** (`origin/HEAD → origin/main`)。旧 `origin/master` は `main` の祖先で
  12+ commits 遅れの凍結枝。master を base にした PR・master への pull/push は行わない。

### merge の担い手と main の Ruleset (`main-require-review`)

- **Ruleset**: GitHub Ruleset `main-require-review` (id `25094342`。対象は既定ブランチ `~DEFAULT_BRANCH`、enforcement `active`、
  2026-10-14 16:03Z 作成)。main への merge は **APPROVED の承認が 1 件以上**ある PR だけが通る (`required_approving_review_count=1`)。
  merge 方式は merge commit のみ (`allowed_merge_methods=[merge]`)。CODEOWNERS・最後の push 後の承認・thread 解決は要求しない。
- **効果**: 承認の無い PR の merge は 405 で失敗する。reviewer App (`oc-reviewer-for-signature-studio`) の APPROVED は承認として数えられる
  (PM の canary 記録。再測定していない。所見と取得方法は `tools/pm/REPORT.md` §18)。実装 App 単独の承認では merge できない見込み (未検証)。
- **通常経路**: reviewer App が approve し、同じ run で `gh pr merge --merge --match-head-commit <レビューした head>` を行う
  (`.github/prompts/reviewer.md` の手順 4)。実装 agent が `gh pr merge --auto --merge` で Auto Merge を有効化しても、承認が要るため
  承認の後に merge される見込み。**Auto Merge の挙動は未検証。**
- **PM の緊急 merge (Admin bypass)**: 次の手順。ただし **2026-10-14 16:26Z の API 確認では bypass は未設定**
  (全体 JSON に `bypass_actors` が無く、`current_user_can_bypass` は `never`)。issue #2648 の記録にある Admin (actor_id 5) の bypass は、
  現在の Ruleset には入っていない。
  1. まず reviewer App に承認させ、承認の後に merge する (通常経路)。
  2. bypass が要るときは、PM が Ruleset に Admin (`RepositoryRole`、`pull_request` モード) の bypass を設定する。設定の有無は
     `gh api repos/signature-studio/signature-studio-dev/rulesets/25094342 --jq .bypass_actors` で確かめる。
  3. 緊急 merge の理由と PR 番号を issue に残す。bypass の設定から merge までの一連は**未検証**。
- **無効化・ロールバック**: `enforcement` を `disabled` にする。部分 JSON ではなく、取得した全体 JSON の `enforcement` だけを書き換えて PUT する
  (PUT は未実行・未検証。作業ファイルは gitignore 対象の `work/` に置く):

  ```
  gh api repos/signature-studio/signature-studio-dev/rulesets/25094342 > work/ruleset.json
  jq '.enforcement = "disabled" | del(.id, .node_id, .source, .source_type, .created_at, .updated_at, .current_user_can_bypass, ._links)' work/ruleset.json > work/ruleset-off.json
  gh api -X PUT repos/signature-studio/signature-studio-dev/rulesets/25094342 --input work/ruleset-off.json
  ```

  戻すときは `enforcement` を `active` にして同じ PUT を行う。無効化・bypass の設定変更は PM が issue に記録する。
- **未解決 (未検証)**: reviewer token が取れない場合の挙動は `.github/README.md` の「main の Ruleset」節。本節の merge 担い手は
  AGENTS.md §1 の「merge は PM が行う」と食い違うが、AGENTS.md は規約の要約なので、この変更では直さない (PM 判断)。

## 3. ステータスと責任区分

| 役割 | 着手時 | 完了時 | 禁止 |
|---|---|---|---|
| 実装 subagent | `/oc` で着手 (open PR が無い間は『着手済み』(`started`)) | **ready の PR を出す** (open PR は『レビュー中』か『修正中』。自分で完了にしない) | issue の手動 close・他チケットの分類やラベルの変更 |
| 検収 subagent | 対象が open な ready PR であることを確認 | 合格 → approve + コメント / 条件付き → **request-changes** + 所見 | approve していない PR の merge |
| PM (main) | 起票 (実装 subagent も下記の条件で可)・milestone 確定・ラベルの付け外し | 緊急時の merge (通常は reviewer App。下の節)・方針変更・是正 | — |

- **PR は自分の issue を `Closes #N` で閉じる** (2026-10-14 PM 是正。#1758): 「`Refs #N` のみで merge」を原則にしない
  (Refs のみの merge は、親が open のまま残り、open 数の水増しと自動着手の分類の乱れを生んだ)。残りの作業は子 issue (`親: #N`) に分離する。
  受入条件を全て満たせないときは、満たした範囲を完了単位として **issue 自体の範囲を縮め** (未達の受入条件を子 issue に移し、
  元の issue の本文から外す)、縮めた issue を `Closes #N` で閉じる。`Refs #N` を使うのは、その PR が issue の受入条件を
  1 つも満たさず (調査の中間記録など)、かつ issue の範囲を縮める余地も無い場合だけで、理由を PR 本文の先頭に 1 行書く。
- **子 issue の起票**: PM のほか、実装 subagent も、**1 run に収まらない実装・修復の作業の残り**を子 issue として起票してよい
  (2026-10-14 PM 判断。PM の処理待ちで止まるのを避けるため。#833)。起票してよいのは **実装・修復の作業に限る**
  (原因特定は、実装に直結するものだけ)。**再測定・REPORT の文言修正・「未解決の追跡」だけの子は起票せず**、PR 本文の未解決表
  (`| 未解決 | 影響 | 起票先 |`) に書く。**1 PR あたりの子は最大 3 件**。親 issue が子の完了待ちのときは、**`blocked_by` を付けない**
  (親を blocker にしない。子を親の blocker にもしない)。子の本文に `親: #N` を書くだけにする。
  条件: ① 題名は `[AREA-n]` 形式。`<AREA>` は
  親 issue の AREA に置き換える (未置換の `<AREA>` のまま実行しない)。既存の最大の n を次のコマンドで調べ、
  その値 +1 を使う (欠番があっても最大値 +1 とする。`"[AREA-"` のような GitHub 検索は `[` `]` を区切りとして扱うため使わない):
  `gh issue list --repo <R> --state all --limit 5000 --json title --jq '.[].title' | grep -oE '^\[<AREA>-[0-9]+[a-z]?\]' | grep -oE '[0-9]+' | sort -n | tail -1`
  起票の直前にもう一度、`gh issue list --repo <R> --state all --limit 5000 --json title --jq '.[].title' | grep -cF '[<AREA>-<n>]'`
  が 0 になることを確認する (番号の重複を作らない)。② 本文に `親: #N`・受入条件・
  必要な `oc_artifacts:` 行を書く。③ milestone・優先度は PM が確定する (subagent は触らない。Project の Status は参考のため触らない)。
  ④ 起票した番号を、最終回答と issue コメントに書く。
- **チケット状態の正は issue の open/closed + ラベル + PR の状態** (技術進捗の正本は `docs/STATUS.md`)。
  open な issue は次の表のどれかに分類する。語は `/status` (PM Worker) と `tools/pm/launch_issues.py plan` が出すもので、新しい語は作らない。
  上から順に判定し、最初に当たったものが分類になる。

| 分類 | 判定 (GitHub の事実) | 意味・次の一手 |
|---|---|---|
| `user` | `needs-user-input` ラベル、または `pm-apply` ラベル (workflow 変更の適用待ち) が付いている | 依頼者の回答・適用待ち。自動着手しない |
| `blocked` | open な blocked_by (issue dependencies) がある、本文の依存行 (`依存:`・`blockedBy:` など) が open な issue を指す、`tools/pm/manual_deps.json` の依存 (停止報告に根拠のあるもの) が open、または子 issue を持つ親で PR が無い | blocker が close されるまで着手しない |
| `started` (着手済み) | open PR が `N-<slug>` ブランチか `Closes/Refs/Fixes #N` で紐づく、または実装 run が稼働中 | 実装・レビュー・修正の途中。二重に着手しない |
| `stopped` | 直近 24 時間以内の bot の最後のコメントが停止報告で、再投入の素材が無い、または再投入の上限 (2 回) に達した | PM の判断待ち |
| `ready` | 上のどれにも当たらない (未着手・非ブロック) | 次の `launch` の対象 |

- 停止報告の窓は **24 時間**。24 時間を過ぎた停止報告は `stopped` にならず、`ready` 扱いで次の `launch` の対象になる (`classify` の窓は `launch_issues.py` と Worker で同じ)。
- `pm-apply` の issue は、Worker の `plan()` が着手も再投入もせず `user` 行に置く (`oc:no-pr` の有無に依らない)。
- `recent` (`/oc` の投稿から 3 時間以内で報告がまだ無い、または bot のコメントから 1.5 時間以内) は着手直後の待ちとして `started` と同様に扱う。
  `relaunch` (停止報告の素材名で再投入する候補) は `plan` の一時分類。`oc:stuck` の PR は着手数の律速に数えない。
- **Project V2 の Status は参考**。VM の `tools/pm/sync_status.py` が動いている間だけ同期し、VM 退役後は更新されない。
  判断の根拠にしない (根拠: #2353 の PM 判断)。
- **label `state:*` は使わない** (2026-10-12 実測で全削除済み・0 件)。新規作成・付与しない。
- **1 状態遷移 = 1 コメント**。コメントなしの状態変更は禁止。
- **分類を変えるラベル (`needs-user-input`・`pm-apply`・`oc:stuck`・`oc:no-pr`) と milestone の変更は PM の責務**。subagent は依頼コメントを書く (PM が委任プロンプトで明示許可した場合を除く)。
- **中断・ブロックで終了する場合**: issue は open のまま (分類は `started` か `stopped`)。中断コメント (到達点・WIP 所在・再開手順) を残し、
  最終回答の冒頭に「未完・open のまま」と明記。

## 4. 着手前の確認 (毎回・省略不可)

1. `gh issue view <N>` でスコープ・受入条件・親 issue・検証方法を確認。
2. 同一チケット / 同一 dir に open PR (`started`) か稼働中の実装 run があれば**着手せず報告**。
3. lift / 逆アセ / IR pass / ハーネス系は `docs/DEFECTS.md` を先に読み、REPORT 冒頭に
   「既知類型との関係: 該当 ID / 該当なし」を 1 行書く。
   **番号体系の注意**: `docs/DEFECTS.md` の D1a〜D23 と `tools/icall/REPORT.md` §4 の D1〜D13 は
   **別体系**。参照時は `(DEFECTS.md)` / `(icall §4)` を必ず併記。
4. **担当 dir 以外の未コミット変更は他担当の WIP**: 触らない・commit に含めない・stash/checkout/clean しない。
5. ユーザへ追加アーティファクトを依頼する前に必ず検証する (`docs/REFERENCES.md` `[DOWNLOADS]` と
   既存抽出物で足りないことを確認し、確認コマンドと結果を併記)。

## 5. 成果物の書き方 (報告の質)

- **結論先出し・日本語**。`REPORT.md` は**日本語 250 行以内**を基本 (`docs/DOC_MAP.md` の上限ルール)。
- 数値はすべて**実測**。推定は「推定」と明記し根拠を添える。「約」「≈」「ほぼ」で丸めない。
- 所要は実測秒 + load average + 並列数。変動する値は n≥3 の **min–max レンジ**。
- 「N 関数/件/%/B」には**単位・分母・除外・集計コマンド**を添える。定義を書けない数値は書かない。
- 主要数値ごとに **1 コマンド再現スクリプト**を `<dir>/` に置く。検収側は**別アルゴリズム**の検算を 1 本追加する。
- 主要検査ごとに **ネガティブコントロール** (1 件を壊して FAIL することを確認) を数値で書く。
- 「検証範囲 / 範囲外」を明記。範囲外の主張は弱める。
- 未解決・限界は **1 件ごとに起票先** (既存 issue にコメント / 新規子チケット / 親への提案) を付ける。
  `| 未解決 | 影響 | 起票先 |` の表形式。
- 環境の恒久化: PATH/TMPDIR 等は `<dir>/env.sh` に書き e2e スクリプト自身が source する。
  `/tmp` は tmpfs なので大物は `<dir>/work/` (gitignore) へ。
- 新しく見つけた silent miscompile 類型は `docs/DEFECTS.md` 形式 (症状/根本原因/観測/検出信号/修復) の
  行案を REPORT に書いて報告する。DEFECTS.md 自体の直接編集は PM 判断。

## 6. 検証 (preflight 代替・旧 RULES_SHA 証跡の廃止)

旧「preflight 実行 → RULES_SHA 転記」は廃止。代わりに以下を**報告前に**自分で実行し結果を REPORT/最終回答に書く。

```sh
git status --porcelain=v1 -- <自分のdir>      # 取りこぼし・他担当 WIP 混入がないこと
git diff <検証起点commit> HEAD -- <dir>      # 範囲が自分の dir のみか
git rev-list --objects --all | awk '$2 ~ /^[0-9a-f]{40}$/' >/dev/null  # (任意) blob 監査
find <dir> -type f -size +20M -not -path '*/work/*'   # 20MiB 超 blob が無いこと
```

- 検証起点の commit hash を REPORT に書く (`規則 45 相当`)。
- **実測値の鮮度の基準 (#1268)**: 測定対象は「コード差分の最終 commit」。main 取り込み merge と文書のみの
  commit では測定対象は変わらない。REPORT に測定 commit と `git diff <測定 commit> HEAD -- <範囲>` の出力
  (差分 0 の証跡) を書けば、reviewer は現 head での再測定を求めない。差分が有れば、その分だけ再測定する。
- 検証は**コミット済み HEAD の内容**で再現してから報告する。未コミット WIP に依存した数値を報告しない。
- クリーン HEAD 検証: `git worktree add --detach <dir>/work/wt_verify HEAD` で展開して実行し、
  終了時に `git worktree remove --force`。`work_verify/` を使う場合は gitignore 外なので **commit 前に必ず削除**。
- 長時間の待機に `sleep` を繋げない。完了確認は 1 コマンドのポーリングか、結果が返る仕組みを使う。

## 7. コミット・PR

- commit メッセージは **conventional commits**。scope はサブシステム名。観察された既存書式:
  `fix(ipp): ...` / `feat(flelift): ... (CAB-252)`。過去の `CAB-xxx` 採番を参照してもよい。
- 例: `docs(liftlib): ...`・`fix(plugins): report corrections (CAB-269)`・
  `feat(kh): add DecompAt2 ghidra postScript`。
- PR は `--base main` を基本 (repo の既定ブランチ = `main`)。body に `Closes #N`・受入条件・検証結果を書く。
- **1 チケット = 1 subagent。** チケット化されていない作業も subagent 委任する。
  10 回以上の tool call が必要になる作業は必ず subagent に委任すること。

## 8. 最終回答 (必須)

テキスト報告なしの完了は禁止。以下を必ず含める:

1. commit ハッシュ / PR URL
2. 成果 (実測値 + 数え方の定義)
3. 検証結果 (秒・load average・ネガティブコントロール)
4. 未解決 (起票先付き)・ブロッカー
5. ユーザ依頼事項 (あれば・事前検証の結果付き)
6. 次タスク提案 (下流チケット案)
7. 事前推定と実測の差 (あれば・推定ラベル付き)

## 9. Issue / PR の命名規則

- タイトル: **`[AREA-n]` prefix** + 英語表題。`AREA` は**次の一覧が正本**で `n` は AREA 内の連番
  (同名族・重複タイトルを作らない):
  `KH`・`PLG` / `P0c`・`SHX` / `T-SH`・`AU`・`HB`・`IPP`・`LIFTLIB` / `L`・`RT`・`GUI`・`SR`・`MX`・`FA`・`OTT`・`E2E`・`LGL`・`ST`・`PY`・`PERF`・`LD` / `ICALL`・`M11`・`CI`・`DOCS`・`FLE`・`H`。
- `CI`: CI 基盤・GitHub Actions (Issue #284 など)
- `DOCS`: ドキュメント整備 (Issue #281 など)
- `FLE`: x64c lift による FLEngine boot 連鎖 (tools/flelift/boot/, DOC_MAP が FLE-2〜FLE-5 シリーズを既に参照、親チケットは [ICALL-1] #227)
- `H`: 静的配信・ホスティング (R2 / Cloudflare / Cloudflare Access)。repo 前例 [H-1] #62 (closed)。Issue #8 が [H-2] として採番済。
- 過去の採番は尊重する (例: `[IPP-7]`・`[KH-2b]`・`[HB-H2]`)。
  `[HB-H4']` のような記号付き・`[ユーザ依頼]` のような日本語 prefix は**作らない**
  (`needs-user-input` ラベルとの二重表現もしない)。
- **既存 prefix の正規化方針**: 新規 Issue は `[AREA-n]` に統一する。既存の `[HB-H2]`・
  `[PLG-P0c]` のような接頭の入れ子、`[HB-H4']` のような記号付き prefix、prefix 無し
  (GitHub テンプレ残骸 #4〜#6 を含む)・完全重複タイトル (`[FA-2c]` #260/#261・
  `[KH-6]` #61/#259/#274) は**追跡のみ**とし、**PM が Issue 整理時に正規化する**
  (実装 subagent は勝手にリネームしない)。
- 旧 Linear からの移行フッタ（`元 Linear:` ブロック）は **provenance として保持**する。書式は統一済み（全 203 open Issue 中 200 件が同一形式）なので清理は不要。クローズ時に除去してよい。
- 起票前に `gh issue list --search "<kw>"` で重複確認。**重複タイトルを作らない。**
- 子チケットは親と同じ milestone を付ける (milestone の確定は PM)。
- PR タイトルは commit と同じ conventional commits 書式。
- 本文: 背景 (実測値・推定はラベル付き) / 受入条件 / 範囲 / 検証方法 / 親 issue。

## 10. CI 期待事項

- **現状の CI**: `.github/workflows/opencode.yaml` (OpenCode セットアップ・検証用)。
- PR では最低限これが緑であること。typecheck / build / `pnpm runtime:e2e` はローカルで実行して結果を REPORT に書く。
- OpenCode 基盤は 2026-10-12 に main で稼働開始 (PR #282, merge `bec32da`)。PR では review ジョブが OpenCode レビュワーを自動起動し、approve と必要に応じたマージまで実行する (実行実績あり: run 38220632379 / 38228263935)。
- commit 前に `find <dir> -type f -size +20M` で巨大 blob がないことを確認すること (GitHub の hard limit 対策)。

## 11. Actions 上での実行 (依頼者指示 112: 全作業は Actions へ移行済み)

実装・調査は Actions 上の OpenCode が行う。ローカルは起動・監視 (`gh run watch`)・検収・統合のみ。

- **起動**: issue に `/oc oc_actions_allow_write` をコメントする (1 issue = 1 run)。
  `oc_actions_allow_write` が無いと read 専用で、PR は作れない。
- **素材**: 既定で取得されるのは `fl-win64` のみ。他は本文に `oc_artifacts: fl-win64 plugins-ott` の
  行を書く (許可名: fl-win64 / plugins-ott / plugins-freshair / plugins-serum2 / plugins-massivex /
  plugins-kilohearts / toolchain-retdec / toolchain-emsdk / work-m11 / work-liftdiff / work-m6-ott /
  work-liftlib-targets / work-liftlib / work-icall / work-fw-stage1 / analysis-ott-binaries / analysis-mac-shared / apt-mingw。それ以外は
  run が失敗する)。`oc_artifacts: none` は「追加素材なし」の明示で、単独なら空扱い (既定の fl-win64 になる)。他の名前との混在は失敗する。
  全素材は約 17.7 GiB (2026-10-13 実測) のため必要分だけ指定する。
  - `toolchain-retdec` → [RETDEC]、`toolchain-emsdk` → [EMSDK] に展開される (環境変数の対応は `docs/REFERENCES.md` §4)。`m11_lift.sh` は PATH に無ければ `$RETDEC_ROOT/bin` → 既定 `/opt/retdec/bin` の順で解決するため、PATH 設定は不要 (#928)。
  - `work-m6-ott` → `tools/m6/work/` + `tools/ott/work/` + `tools/m8/work/` + `tools/m9/work/` + `tools/m10/work/`
    (`tar --zstd -tf` で実測)、`work-liftlib` → `tools/liftlib/work/`、
    `work-icall` → `tools/icall/work/`、`work-liftlib-targets` → `tools/targets/{freshair,kilohearts}/work/`
    の HeartCore / SlateCore のみ (liftlib_e2e.sh の `need` 対象) に展開される
  - `analysis-ott-binaries` → `$HOME/analysis/plugins/ott/binaries/` (OTT_vst2_win64.dll ほか実機バイナリ。
    展開後は `ANALYSIS_DIR=$HOME/analysis` が環境に入る。tools/shared/env.sh の既定 /home/ubuntu/work/analysis を上書きする)
  - `analysis-mac-shared` → `$HOME/analysis/mac/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL/Shared/` に FL の mac 版 dylib (`libkio_x64.dylib` 等 25 本) が展開される
    (`analysis-*` の規約で `ANALYSIS_DIR=$HOME/analysis` が環境に入り、`FL_MAC_DIR` の既定 `$ANALYSIS_DIR/mac` から見える)。
    T-SH 系 (shared ライブラリ lift) の native 参照オラクルが `mmap(RWX)` + ctypes で実行する。#761。
  - `apt-mingw` は R2 の素材ではなく、`gcc-mingw-w64-x86-64` を runner に apt 導入する
    (`x86_64-w64-mingw32-gcc`。PE を作るテスト用で tools/ の 22 ファイルが使う。#646)。
  - `work-m11` → `tools/m11/work/`、`work-liftdiff` → `tools/liftdiff/work/` に展開される
    (gitignore 対象の検証スナップショット。commit しない)。`work-m11` は #516 qstore 以前の生成
    (`qstore_report.json`・`ir_conditions.json` 無し) で現 main の生成手順と一致しない (#680)。survey の基準には使わない。
    IR の正は `bash tools/m11/m11_e2e.sh --full` (RetDec から再生成) の出力とする。`--full` は head `2e128c5c` で rc 0 まで通る (633 秒・素材 + Ghidra 再生成が前提。`tools/m11/REPORT_N27.md` §12・#728)。ただし reached_stage は 4 で trap が残る。IR の sha256 は A7 の空行除去 (#1664) より前は実行ごとに変わった (原因と修正後の一致は `tools/m11/REPORT_APPENDIX_960.md` §19)。
    `functions_dll.csv` は素材に無い Ghidra headless の中間物で、Ghidra 12.1.4 (`support/analyzeHeadless`・JDK 21・`tools/m2/ghidra_scripts/DumpFunctions.java`) で作る。lift 成果物は `work/lift_pe.sha256` に生成時の PE 指紋を記録し、PE が変われば作り直す。PE とパスは `FL_WIN64_DIR` 経由・相対パス化済み。
    `work/ir_conditions.json` の `ldfix=applied` と `ir_sha256` (IR の指紋) が一致しない IR は build されない (`m11_build.sh`)。
    **使う側が最初に `bash tools/m11/m11_gen_ir2.sh` を実行して `ir_conditions.json` を作る** (`FL_WIN64_DIR` の PE が要るので `fl-win64` も指定する)。
    Python の `capstone`・`pefile` が要る。無いと ldfix が skipped になり fail-closed で `exit 1` する。agent-setup が `~/.local/agent-py` の venv に `pefile` `capstone` `numpy` を入れる (#893)。版と hash は `.github/actions/agent-setup/requirements-py.txt` で固定し、`--require-hashes` で入れる (#2621)。venv の bin は PATH に載せず、`python` / `python3` を venv の python へ委譲するラッパーの dir (`~/.local/agent-py-shim`) を PATH 先頭に置く。venv 無しで動かす場合は同じ venv を手で作る。
    `ir_conditions.json` は生成時の PE の絶対パスを記録し、`m11_build.sh` は現在の PE と一致しないと build を拒否するため、別の環境で作った json を素材に同梱しても使えない。
  - `work-fw-stage1` → `tools/plugins/work/fw/` に framework stage-1 成果物 (fw_icall.dll / fw_map.json /
    fw[0-7].restored.ll / r2.restored.ll / r3.restored.ll の 12 ファイル。#610)。`fw_269_verify.sh` の既定 SRC がそのまま使える。
    作成・検証は `bash tools/plugins/framework/fw_pack_stage1.sh pack` → `artifacts/work-fw-stage1.tar.zst` (`verify` で単独検査も可)。
    R2 への投入の手順は下の「R2 への投入 (VM 非依存の手順)」。現状は PM が VM 上で行い、VM 退役後の担い手は依頼者とする。
  - 追加の `work-*` は R2 に置いて、`prepare-event-context.sh` の allowlist に足す (#293)。
- **R2 への投入 (VM 非依存の手順・#2434)**: 担い手は依頼者 (現状の PM は VM 上で行う。VM 退役後は依頼者が行う)。
  素材の原本の所在は `docs/REFERENCES.md` の「素材の原本と R2 bundle の対応」、投入の頻度は `tools/pm/REPORT.md` §13 が正本。
  1. **権限を昇格**: Cloudflare で R2 の API token の権限を、バケット `signature-studio-artifacts` に限り「Workers R2 Storage Bucket Item Read」から「Read + Write」へ変える。画面上の操作名は `[未確認]`。昇格中は、この token を使う全ての経路が書ける (Actions の `CF_R2_*` が同じ token かは `[未確認]`)。投入は短時間で終える。
  2. **投入**: 梱包した `<name>.tar.zst` を S3 互換 API で置く。大きい object は aws cli が multipart で送る (`tools/plugins/framework/fw_pack_stage1.sh` の注記と同じ形): `aws s3 cp <name>.tar.zst s3://signature-studio-artifacts/artifacts/<name>.tar.zst --endpoint-url "https://$CF_ACCOUNT_ID.r2.cloudflarestorage.com"`。S3 のキーは環境変数で渡し、値を repo・ログ・issue に書かない。
  3. **照合**: R2 から同じ object を取り直し、梱包元と sha256 が一致することを確認する。不一致なら 2 からやり直す。
  4. **権限を戻す**: 手順 1 の逆 (Read のみ)。戻したことを確認する方法は `[未確認]`。
  5. **許可名を足す場合**: 同じ PR で `.github/scripts/prepare-event-context.sh` と `.github/scripts/watchdog.sh` の `ARTIFACT_RE` と、本節の許可名一覧を更新する。`pr-lint.sh` は watchdog.sh の値を読むため、`grep -n '^ARTIFACT_RE=' .github/scripts/*.sh` で両者の一致を確認する。
  - **Actions から投入しない理由**: (1) Actions の R2 認証 (`CF_ACCOUNT_ID`・`CF_R2_ACCESS_KEY_ID`・`CF_R2_SECRET_ACCESS_KEY`) は素材の取得に使う。`tools/pm/README.md` の運用の約束は、投入を「R2 への投入は既存 token の一時昇格だけで行い、終わったら必ず Read のみへ戻す」と定める。Write 可能な token を repo secret に置くと、`/oc` を書ける人の run (実装 agent を含む) がバケットに書ける。(2) 原本の一部は VM のディスクにしか無い (`docs/REFERENCES.md` の原本表)。run からは `~/ダウンロード/` や mac pkg の展開物を再作成できない。
- **fl-win64 の展開と `FL_WIN64_DIR`**: tarball は最上位に `extracted/` と installer exe を持つ
  (`extracted/block00031_PE.bin` 等)。展開先ディレクトリがそのまま `FL_WIN64_DIR` になる。
  tools/ のスクリプトは `tools/shared/env.sh` (bash)・`paths.py`・`paths.mjs` 経由でこの変数を読む
  (使い方は `docs/REFERENCES.md` §4)。`block_manifest.json` 等は tarball に含まれない。

  ```sh
  mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
  export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
  ```

  agent-setup での自動展開・`$GITHUB_ENV` への `FL_WIN64_DIR` 設定は未実施 (必要なら別 PR)。
  `PLUGINS_DIR` も同様に `plugins-*` の展開先を指定する。
- **plugins-freshair の展開 (#693)**: tarball は最上位に `Fresh Air.Win.zip` / `Fresh Air.pkg` を持つ。agent-setup は
  展開しないので、必要な run が自分で展開して `tools/targets/freshair/fetch.sh` に渡す。`fetch.sh` は zip から
  `work/win/Fresh Air/.../FACTORY Presets/Factory Bank/*.epf` (8 本) を必ず補完する (`work-liftlib-targets` が先に
  `work/win/Fresh Air` を作っても欠けない)。mac 側は `xar` と pkg が無ければ skip する。

  ```sh
  mkdir -p "$RUNNER_TEMP/plugins-freshair" && tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$RUNNER_TEMP/plugins-freshair"
  FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
  ```
- **レビュー run の素材**: review ジョブも PR 本文の `oc_artifacts:` 行を読んで素材を取得する
  (素材を要する e2e をレビュワーが独立再実行するため)。PR 作成者は、素材を要する PR の本文に
  実装時と同じ行を書くこと。
- **結果**: agent の text ブロックは全て run のログ (`gh run view <id> --log` の `Write step summary`) と
  `$GITHUB_STEP_SUMMARY` の両方に出る。`Dump OpenCode events` には作業の流れ (tool 名・状態・所要 ms・
  入力の先頭 200 文字・cost) が出る。repo が public のため、**tool の出力と生 JSONL はログに出さない**
  (認証情報・FL 由来物の漏洩防止。secret マスクは登録値との完全一致でしか効かない)。
  issue へのコメントは agent が `gh issue comment` で行う。
- **上限**: job は 60 分。収まらない作業は中間 commit + **ready PR** で区切る (満たした範囲に issue の範囲を縮めて `Closes #N`、残りは子 issue か PR 本文の未解決表。§3) (draft は禁止: REVIEWING でも FIXING でもない状態になる)。
- 稼働本数は「走っている Actions run 数」で数える (`gh run list --status in_progress`)。
- **PM の watch ルール (依頼者指示 116)**: 起動した全ての run は無条件で `gh run watch` する。PM が
  応答を終える時は、background で `gh run watch` が 1 本以上走っていること。完了通知を受けたら、
  結果の処理に入る前に、次の watcher を起動し直す。
- **PM は依頼者の不在 (最大 2 日) を前提とする (依頼者指示 144)**: 依頼者は一度指示すると最低 2 時間、最大 2 日間は不在になり、
  依頼者の指示がないと進行できない状態はそのまま遅延になる。依頼者の操作が必要な項目は非ブロッキングにする
  (`needs-user-input` で積み、それを待たずに他の作業を進める)。依頼者の応答を、他の作業の前提条件にしない。
- **open PR は 2 状態のみ (依頼者指示 119・120・122・123)**: 実装が始まったチケットは merge まで止めない。
  open PR は常に次の **どちらか** であり、「レビューも修正もされていない状態」(IDLE) を 1 秒も作らない。

  | 状態 | 意味 | 担い手 | 次の遷移 (人手 = PM を介さない) |
  |---|---|---|---|
  | REVIEWING | review job が走っている / 待機中 | oc-reviewer | approve -> 同じ run で merge (PR は閉じる)。request-changes -> FIXING |
  | FIXING | 差し戻しを受けた implement job (fix モード) が走っている / 待機中 | 実装 agent | push -> `pull_request:synchronize` で REVIEWING |

  遷移は workflow のイベントで自動に起きる (`.github/workflows/opencode.yaml`)。

  | きっかけ | 動くもの |
  |---|---|
  | PR opened / synchronize / reopened / ready_for_review | review job |
  | oc-reviewer が `changes_requested` を提出 (`pull_request_review`) | implement job (fix モード)。`gh pr checkout` した PR ブランチを直して push |

  無音終了を許さない仕組み:

  - **review**: run の最後に `verify-review-verdict.sh` が現在の head への verdict (APPROVED / CHANGES_REQUESTED) を
    確認し、無ければ PR にコメントを残して close -> reopen で review を再起動する (同じ head に 3 回まで。超えたら警告して失敗)。
    close -> reopen は `reopen-pr.sh` が行い、reopen が 3 回失敗したら PR に `oc:stuck` を付けて失敗する (closed のまま放置しない)。
    先に PR の状態を読み、merge 済み・close 済み (未 merge) なら再 review する対象が無いので notice を残して成功で終わる (fix run が merge 済みの PR を close しようとして `could not close PR` で落ちない。#2597)。状態を読めない・open のまま close できないのは失敗にする。
    reviewer の step に 50 分の上限 (`timeout-minutes: 50`) を置くと、verify を job の 60 分と App token の 1 時間寿命の内側で
    必ず走らせられる。この変更は App に `workflows` 権限が無く
    agent は push できないため、PM が `.github/workflows/` を直接 push して適用した (現行の運用は下の「workflow 変更の運用」)。
    COMMENT だけの review は verdict と認めない。**Copilot の review を待って verdict を保留することはしない**
    (Copilot の review は来ないことがあり、保留した PR は誰にも動かされず止まるため)。Copilot の review が
    approve 前に既にあれば読んで判断する。run の途中で head が進んだ場合は、その push の synchronize が起動する
    review が担当するので検証は免除する。
  - **fix**: 起動前に `fix-progress.sh record` が、merge 済み・close 済み (未 merge) の PR と、差し戻しの元の review の commit が現在の head と違う (古い head への差し戻し) の場合は、agent を起動せず notice のみを残して終える (`stop=true`。`oc:stuck` は付けない。#2601)。agent を起動した後は、run の最後に `fix-progress.sh` が「head が進んだ (pushed)」「push せずコメントした (answered: close -> reopen で
    review を起動)」「どちらもしていない (none: 1 回再試行し、なお none なら job を失敗させる)」を判定する。
    判定・再試行・reopen・失敗の各 step は `!cancelled()` なので、agent step が失敗しても走る。run の cancel では走らない
    (step の timeout 後に走るかは未実測。merge 後の実 run で確認する)。
    (fix モードの step 上限は agent 40 分・retry 15 分。setup を足すと job の 60 分に近い。素材指定で setup が長い PR では
    retry の上限を縮めることを検討する)。
  - **往復の上限**: oc-reviewer の CHANGES_REQUESTED が 1 PR で 5 件に達すると、fix を起動せず PR にコメントを残し
    ラベル `oc:stuck` を付けて止める (`changes_requested -> fix -> review` と `answered -> reopen -> review` の
    どちらの循環も 1 周に 1 件増えるため)。件数は直前の停止コメント (`<!-- oc-fix-limit -->`、bot 投稿) 以降の差し戻しに限る。
    ラベルを外すと再開し、次の差し戻しから数え直す (停止前の件数を持ち越さない)。停止コメントの無いラベル (手動付与・reopen 失敗) は
    数える起点が無く全期間を数えるため、外すと即座に再停止しうる (扱いは #719 で決める)。
  - **起動主体は完全一致**: fix を起動する reviewer (`oc-reviewer-for-signature-studio[bot]`、`user.type == 'Bot'`) と、
    停止コメント・完了コメントの実装 App (`opencode-for-signature-studio[bot]`) は login の完全一致で見る
    (前方一致だと別名のアカウントでも write 権限の fix が起動し、停止コメントを偽装して数え直しもできてしまう)。
  - **テスト**: `.github/scripts/tests/test-pr-loop.sh` (fix / verify / reopen) と `test-watchdog.sh` (watchdog の判定と操作)
    と `test-dispatch-context.sh` (dispatch・投稿者の入力検証) と `test-run-outcome.sh` (implement 終了時の記録・review の打ち切りの再起動) を、fake gh で `.github/workflows/scripts-test.yaml` が `.github/scripts/**`・`.github/actions/**`・`opencode.yaml` の
    変更ごとに実行する。
  - **並行制御**: implement job は `opencode-impl-<N>`、review job は `opencode-review-<N>` と group を分ける。
    同じ group だと fix が pending の間に review が入って fix が黙って取り消される (pending は 1 件しか持てない)。
    その代わり fix と review が重なりうるので、reviewer は `gh pr merge --match-head-commit <レビューした head>` で
    未レビューの commit を巻き込まない。
  - PR は **常に ready・base は main** で作る (draft / stacked は REVIEWING でも FIXING でもない状態を作るため禁止)。
    未完でも ready で出す。満たした範囲に issue の範囲を縮めて `Closes #N` とし、未解決は子 issue か PR 本文の未解決表に書く (§3)。前提 PR が未 merge の作業は着手しない。

  **watchdog** (`.github/scripts/watchdog.sh`、`opencode.yaml` の `watchdog` job): `push` to main と 5 分おきの
  `schedule` で、REVIEWING でも FIXING でもない PR (IDLE) を機械的に元の 2 状態へ戻す。実行中の run と PR を突き合わせ、
  push 直後の PR は SETTLE (4 分) の間は触らない。1 回の点検で動かす PR は 12 件までで、REST だけを使う。

  | IDLE の理由 | watchdog がすること |
  |---|---|
  | main と競合している | `repository_dispatch` (type `oc-fix`) で fix モードの実装 run を起動する。競合 PR は `pull_request`・`pull_request_review` でワークフローが起動せず、差し戻しでは動かせない (往復回数を消費するだけ)。dispatch は競合に左右されない。同じ head への dispatch は 3 回までで、超えたら `oc:stuck`。fork からの PR (`head.repo` が本リポジトリでない) は dispatch しない (write 権限の run を第三者の入力で動かさないため)。`oc:stuck` も付けず、一覧に出して人が判断する |
  | draft | ready にする |
  | 現在の head に verdict が無い | close -> reopen で review を再起動する |
  | 差し戻し済みだが fix が動いていない | `[watchdog]` の request-changes を出し直す (-> fix) |
  | approve 済みで未 merge | `gh pr merge --merge --match-head-commit <head>`。失敗したら `[merge-failed]` の request-changes |

  **repository_dispatch (oc-fix)**: 送れるのは `contents: write` を持つトークンだけ。payload は PR 番号 (数字のみ)・理由 (`conflict`)・
  素材名 (PR 本文の `oc_artifacts:` から allowlist に一致する語だけ) で、自由な文字列は持たない。`prepare-event-context.sh` が
  値域を検証し、指示文は理由から組み立てる。run は `run-name` が `oc-fix #<PR 番号>` になり、watchdog はこの名前で担当 run を突き合わせる。
  dispatch の前に `<!-- oc-dispatch:<head12> -->` のマーカー付きコメントを残し、同じ head への回数を数える。

  `oc:stuck` ラベルの PR は触らない (人の判断待ち)。同じ head への watchdog の差し戻しが 6 回、または review の再起動が
  3 回に達したら `oc:stuck` を付けて止める。`DRY=1` なら計画だけを出す。reviewer は login の完全一致 + `Bot` 型で見る。

  **issue の不変条件 (#1950)**: 全ての open issue は『blocked』『着手済み (open PR か実行中の implement run がある)』のいずれかで、
  どちらでもなければ明示的な終了状態 (`oc:no-pr`・`needs-user-input`・`oc:stuck`) を持つ。実測では implement run (issue_comment) の約 70% が
  PR を出さずに終わっていた (着手報告のみ・停止報告・1 run に収まらない・素材不足)。

  - **implement の終了時** (`record-run-outcome.sh`、`opencode.yaml` の最終 step。`always()` で、agent の失敗・cancel の後も走る。job は失敗させない):
    issue の `/oc` run が、open PR も (run の開始以降に作成・merge された PR を含む。#2590)、明示的な終了状態 (`oc:stuck`・`needs-user-input`・`blocked`・open な依存) も残さずに終わったら、
    issue にラベル `oc:no-pr` と構造化コメント `<!-- oc-run-outcome: no-pr reason=<stop|split|blocked|artifact|unknown> run=<run id> -->` を残す。
    PM Worker はコメント本文を解析せず、**ラベルとマーカー**で扱う。`oc:no-pr` は、次の run が PR を出す (または issue が close・明示的な状態になる) と、この script が外す。
    `state:*` ラベルは作らない。reason は agent の最終回答の語彙で決める (`tools/pm/launch_issues.py` の `stop_re`・`NEED_RE` と同じ。優先順 artifact > blocked > split > stop):
    `artifact` 素材不足・`blocked` 依存 issue・前提 PR 未 merge・`split` 1 run に収まらない・`stop` 判断待ち/停止報告/着手不可・`unknown` 上のどれでもない (着手報告のみ・run の失敗)。
    コメント本文に起動コマンド (行頭の `/oc`) は書かない (自分のコメントで implement を起動しないため)。
  - **review の打ち切り** (`review-recover.sh`、`review-recover` job): review job が runner の打ち切り (job の annotation が `shutdown signal`・`exit code 143`・
    `exceeded the maximum execution time`) で cancelled になると、job 内の verify step は走らない (#1420: 同じ head で 7 回連続)。新しい runner の
    `review-recover` job が、watchdog を待たずに `verify-review-verdict.sh` を呼んで同じ head の review を再起動する。**上限**: 同じ head への再起動は
    `review-retry` マーカー 3 回まで (verify の step と watchdog と共有。超えたら PR に警告して oc:stuck への経路に入る)。PM の手動 cancel (annotation 無し) では再起動しない。
    annotation が読めないときは何もしない (watchdog が拾う)。
  - **watchdog の集計** (`watchdog.sh`): open issue で、blocked でなく、open PR が無く、実行中の implement run も無く、`oc:no-pr`・`needs-user-input`・`oc:stuck` も無い
    issue を `floating-issues=N` として出力する (step summary にも出る)。**数えるだけで何もしない** (launch は PM Worker の責務)。本文の『依存: #N』『親: #N』による待ちは見ないため、上限値の目安である。
  - **PM Worker の停止検知** (`watchdog.sh`、#2328): `tools/pm/worker_url` の URL の `/status` を `curl -fsS -m 10` で読む。`configured` と `installed` がともに true
    (一度でも稼働に入った Worker) で、`fresh` が false または `last_tick` が 15 分より古ければ、題名 `[CI-n] PM Worker 停止 (<日付>)`・ラベル `pm-worker-down` の issue を起票する
    (本文は `/status` の写しと `@pycabbage`。`needs-user-input` は付けない)。**`configured:false` / `installed:false` (`/setup` 未了) では起票しない。**
    重複排除: ラベル付きの open issue があれば追記のみ (1 時間に 1 回まで)、24 時間以内に close した issue は reopen して追記する。
    回復 (`fresh` が true かつ `last_tick` が 5 分以内) で、open の障害 issue にコメントして close する。ファイルが無い・取得失敗・JSON 不正は警告だけで何もしない (終了コードは変えない)。
  - **bot の `/oc`** (#1949): PM 用 GitHub App の `/oc` は `vars.OC_PM_BOT_LOGIN` との完全一致 + `user.type == 'Bot'` で許可する (`.github/README.md`)。

  PM の運用スクリプト (`pr_gaps.py` で IDLE を計測、`sweep_prs.sh` で復旧) は **バックストップ**であり、
  IDLE が 1 件でも出たらそれ自体を workflow の不具合として扱う (所在は `docs/REFERENCES.md` `[PM-SCRIPTS]`)。
  着手報告だけで終わった実装 run は `find_silent_runs.sh` で検出する。

### workflow 変更の運用 (VM 退役後の凍結・`pm-apply`)

実装 App には `workflows` 権限が無く、agent は `.github/workflows/` を push できない。これまでは PM の PAT で
PR を出し、ラベル `pm-apply` で管理していた。VM 退役後は次の運用に置き換える (判断: 2026-10-14、#2319。運用の正本はこの節)。

- **(a) 凍結**: VM 退役後は `.github/workflows/` の変更を凍結する。ロジックは `.github/scripts/`・`.github/prompts/` に寄せ、workflow は薄い配線に保つ。
- **(b) 依頼**: 変更が必要になったら、issue に `pm-apply` と `needs-user-input` を付け、`git apply` できる unified diff をコメントに書いて止まる。diff は `.github/workflows/` の変更だけにする。PM agent は `pm-apply` を付けられない (許可ラベル外。`.github/prompts/pm.md`)。その場合は `needs-user-input` だけを付けて依頼者へ渡し、依頼者が `pm-apply` を付ける。
- **(c) 適用 (依頼者が手元で行う)**: 依頼者は diff の内容 (特に `permissions:` と `secrets.*` の参照) を確かめてから、コメントの diff を `diff.patch` に保存し、次を実行する。merge は reviewer App が行うため、PAT は要らない。

  ```sh
  git fetch origin main && git switch -c <N>-workflow origin/main && git apply diff.patch
  git add .github/workflows && git commit -m "ci: <要旨>" -- .github/workflows
  git push -u origin HEAD
  gh pr create --base main --title "ci: <要旨>" --body "Closes #<N>"
  ```

- **(d) App に `workflows` 権限を足さない理由**: 足すと、検査 (review) を通らない workflow 変更を agent が作れ、`OC_APP_PRIVATE_KEY`・`OC_REVIEW_APP_PRIVATE_KEY`・`OC_AUTH_EXPORT`・`CF_R2_*` などの secrets を読む workflow を書けてしまう。検査を迂回する経路が 1 つでもあれば、secrets の持ち出しに直結する。足す場合の条件は、org owner の承認と、workflow 変更を機械的に検査してから適用する設計の両方が揃うこと。経緯は #2352 (staged-apply、不採用)。
- **退役の条件**: VM の timer・PAT・keyring を止める前に、open の `pm-apply` の issue が 0 件であること (確認: `gh api "repos/<R>/issues?labels=pm-apply&state=open" --jq length`)。


## 12. 依頼者不在時の運用 (needs-user-input・assume-and-proceed)

依頼者は指示後、最低 2 時間・最大 2 日間不在になりうる。依頼者の判断が要る事項は `needs-user-input` で積み、
他の作業を止めない。規則 R1〜R9 と境界 U1〜U8 の**正本は `.github/prompts/pm.md`** である (本節に複製しない)。

- **書式**: `needs-user-input` を付けた issue の本文先頭に、次の 4 項目を順に書く。
  1. 質問
  2. 既定案 (依頼者の回答が無いときに採る案)
  3. 既定で進むと何が起きるか
  4. 答えを変えたときの戻し方
- **依存 issue は既定案で進める (assume-and-proceed)**。依存 issue を `blocked_by` にしない。
  依存する側の issue に「仮定で進む」旨をコメントし、既定案のまま実装・PR を進める。
- **依頼者の回答の検出 (`user_answered`)**: `needs-user-input` の issue に依頼者 (人間) が返したコメントを、
  PM agent が読んで反映する。回答は既定案より優先する。値域外 (allowlist 外の素材名など) の部分だけ無視する。
- **PR 起点の判断待ち (`needs_decision`)**: 対象は `needs-user-input` の issue でなく PR (ref は PR 番号)。reviewer の最新の差し戻し
  (`CHANGES_REQUESTED`) の本文が PM の判断・起票を求めているとき (`review.needs`) に Worker が送る。条件は `infra/pm-worker/src/pm.ts` の `detectPm`。
- **質問の前の状態確認**: 質問・`needs-user-input` を出す前に、対象 issue が closed でないこと、PR が merge 済みでないこと、
  post-merge review の有無を確かめる。当たれば質問せず `rule=skip` で終える。closed の issue に残った `needs-user-input` は外す。
  手順は `.github/prompts/pm.md` の「質問・`needs-user-input` の前に対象の状態を確認する」。
- **不在中の自動判断**: PM agent が行った判断は `<!-- oc-pm-decision: rule=Rn reversible=yes/no -->` マーカーで残る。
  対象なしで終えた run は判断でなく `rule=skip` のマーカーを残す。事後の確認はダイジェスト ([CI-70]) で行う。
