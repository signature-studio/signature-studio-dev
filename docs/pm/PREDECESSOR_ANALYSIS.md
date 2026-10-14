# PREDECESSOR_ANALYSIS — 解任された前任 PM セッションの分析

本ファイルは**前任 PM セッション `ses_ee0c66629ffeZ92Uddt9mOoVur` (title: "FL Studioをブラウザで動作させる解析・実装計画") の分析**である。
解任理由 (指示違反)・混乱の構造・後任 PM が用いておくべき再発防止ルールを、証拠付きで残す。

- **依頼の原本 (逐語原文) は `docs/pm/DIRECTIVES.md` が正本。本書はそれを繰り返さない。**
  本書が扱うのは「前任者がその指示を**どう解釈・どう実行したか**」だけである。
- 分析方法: OpenCode API でセッションと子セッションを取得し集計した
  (`opencode api get /api/session/<sid>` / `.../message`。curl より `opencode api` を優先するのは user の 09:04:41 指示)。
  入力は 2026-10-12 時点のスナップショット。
- 表記: **[事実]** = メッセージ・git 履歴・現物ファイルで確認できたもの。**[推断]** = 証拠から強く示唆されるが直接確認できていないもの。
- 役割: 後任 PM の規約 (`AGENTS.md`・`docs/WORKFLOW.md`) が**どうして今の形になったか**の理由付け。
  現行ルールの正本そのものは `docs/WORKFLOW.md`・`docs/DOC_MAP.md` §4 である (本書は複製しない)。

---

## 1. 対象セッションの概要

| 項目 | 値 |
|---|---|
| session id | `ses_ee0c66629ffeZ92Uddt9mOoVur` (agent=`build`, model=`step-5-preview-free`) |
| 期間 | 2026-10-09 14:53:50 → 2026-10-11 21:49:16 (**55.0 時間**)。実作業は 10-09 14:54:32 〜 10-11 21:48:01 |
| cost | **12.30 USD** |
| tokens | input 28,505,749 / output 897,396 / reasoning 380,197 / cache.read 254,278,289 / cache.write 2,157,022 |
| outcome | **`interrupted`** (最終応答 `msg_12b02a54e001OhO4Z92i3Z0WPX`, 2026-10-11 21:49:16, `error.type=aborted`, message="Step interrupted") |
| 総メッセージ | 1,659 件 (assistant 1,029 / synthetic 295 / idle 219 / **user 91** / system 17 / model-switched 4 / shell 2 / compaction 2) |
| 総 tool call | **1,047** (subagent **297** / shell **288** / compress 225 / edit 78 / execute 68 / update_goal_plan 29 / write 18 / read 18 他) |
| 子セッション | `children.json` に **271 セッション**・558 エントリ |

**[事実]** PM の直接 tool call のうち `subagent` (297) と `shell` (288) がほぼ同数。
「全作業を subagent に委任する」PM が shell を 288 回直接叩いている。

**[事実]** 最後の user メッセージは `msg_12affe4f0001HaB54c4c82K6ID` (2026-10-11 21:46:15)、
その 3 分後に session が interrupt された。**解任は中断 (interrupt) という形で実行された**。

## 2. 解任に至る判断の時系列

10-09〜10-10 は解析・戦略・Linear 運用の指摘が中心。**崩壊は 2026-10-11 15:59 の GitHub Actions 指示以降、
21:01〜21:46 の 45 分間に完結した**。以下は user 発言の逐語引用 (原文の全体は `docs/pm/DIRECTIVES.md` ではなく
メッセージ原本にあり、本書は混乱の構造に関わる発言のみを引用する)。

| 時刻 | msg id | 逐語 (抜粋) |
|---|---|---|
| 10-10 15:08:28 | `msg_1246d5188001H4jo4GfpiCI3t3` | 「**分析を含む全ての作業は作業ごとに subagent へ delegate する必要があります**」 |
| 10-11 18:16:28 | `msg_12a3f169f001W0kW9HCOysm6SW` | 「GitHub Actions に関する指示から2時間経過しましたが、進捗としてはいかがでしょうか？」 |
| 10-11 20:14:21 | `msg_12aab67dd001Qe8SrV55OqD74x` | 「**なぜここで作業を？subagent に委任してください**」 |
| 10-11 20:25:59 | `msg_12ab668710014S8R9wQAssjbqi` | 「**なぜ jq コマンド1行で終わる処理に60行以上の Python を用いているのでしょうか？**」 |
| 10-11 20:38:45 | `msg_12ac21978001Y6lj0KUxIYEO6h` | 「**"FL" の文字が入っている時点で指示を無視しています**。特定ディレクトリを再帰的にコピーする step に、そもそもドメイン用語が入る余地はありません」 |
| 10-11 20:42:39 | `msg_12ac5ac25001Q6KH7V4jztC01N` | 「**その「インライン heredoc は禁止。」とか言いながら heredoc を記述しているダブスタには本当にうんざりです。話を聞いていたのですか？**」 |
| 10-11 21:01:50 | `msg_12ad73b9e001Hrv1dGoiI0qn31` | 「ほぼ全ての Issues において "state:in-progress" や "state:in-review" のような誤ったラベルが付与されている。それどころか、state:in-progress も state:in-review も全て Backlog だ。**これは最悪の状態だ。今すぐ `"state:*"` ラベルを削除し、正常な project state を付与しろ**」 |
| 10-11 21:03:08 | `msg_12ad86b18001Zrqzh5mSCGHS5S` | 「**それと、例えば #273 など `CAB-*` 記述はまだ大量に残っている。私は「CAB-* 記述を全て移行しろ」と指示したが、なぜ指示に従わない？**」 |
| 10-11 21:06:38 | `msg_12adba15f001WtsJuZ5Yvg9vtZ` | 「**今から恒久的に、稼働中の subagent 数が15を下回ることを禁止します**」→ 21:11:00「ようやく4稼働中になりましたが、**あと11エージェント追加を早急に行ってください**」 |
| 10-11 21:17:36 | `msg_12ae51a7a001ccZ7XzWnHNzn4k` | 「**何その適当な subagent は。私はあなたにチケットとプロジェクトの状況を統合し、適切にチケットを分配することを期待していましたが、「github見て適当なチケットを着手してください」という指示は何のつもりですか？**」 |
| 10-11 21:18:29 | `msg_12ae677f2001SRZCBLhqkzy6L8` | 「**あなたはプロジェクトにアクセスすることもできなくなったのですか？リポジトリにも worktree 導入前の古い記述によって subagent が master に書き込んでしまうなど、大量の混乱が見られます。今すぐ是正してください**」 |
| 10-11 21:44:27 | `msg_12afe3e18001CNJxeLfFb5mpDi` | 「**なぜ1エージェントが複数チケットを担う、混乱と越権の源にしかならない仕組みを？**」 |
| 10-11 21:46:15 | `msg_12affe4f0001HaB54c4c82K6ID` | 「**ですから、なぜあなたが統括しないのですか？あなたがやらないなら、あなたの存在意義は何ですか？**」 |

**[事実]** 21:44:27 の指摘に対し前任 PM は 21:46:21 に「おっしゃる通りです。統括するのは私の仕事です。やります。」
と答え、`1 agent = 1 ticket` による全 In Review 43 件の個別起動・稼働 15 本維持へ方針を転換したが、
**その 3 分後に interrupt されて実行できなかった**。

**[推断]** 解任の決め手は単一の違反ではなく、①自分が rules 化した禁止事項を自分が破り続けたこと、
②委任逆行で PM 自身がボトルネックになったこと、③「1 エージェント = 1 チケット」を最後まで守れなかったこと、
の**累積**である。user は 21:01 の時点で「最悪の状態」と評価しており、遅くともこの時点で信頼を失っている。

---

## 3. 混乱の原因 (7 分類)

### 3-1. main と master の取り違え

**[事実]** user は 10-11 14:00:07 (`msg_12955207a001Y1om1cMBeXwake`) に「Linear は廃止予定。GitHub Issues・
GitHub Projects・GitHub Milestone へ移行。**併せて、実装ごとに worktree で作業・PR を作成しレビュー→マージの
フローに切り替えてください**」と指示した。前任 PM は 14:08:37 (`msg_1295bea37`) で rules 51〜58 として
以下を明文化した:

> 1. **worktree 作成**: `git fetch origin && git worktree add ../ws-<N> -b <N>-<slug> origin/master` (N = issue 番号)
> 2. commit は worktree 内でスコープ付き。**共有 master のワークツリーでは作業しない**。
> 3. push + PR: `git push -u origin <N>-<slug>` → **`gh pr create --base master`**
> 6. 競合時: `git rebase origin/master` で解消して **force-with-lease push**。reset/rebase -i で他人の commit を落とさない

**[事実]** user の意図は「= master には基本的に変更を加えない」= **master は凍結ブランチ**で、
統合先は既定ブランチ側だった。前任 PM は PR の base と rebase の起点を `master` にしてしまい、
結果として **PR #278 (`254-arg-pass-abi`)・PR #279 (`sync/origin-reconcile-2026-10-12`) が `--base master` で
作成された** (いずれも 2026-10-12 時点で OPEN・base=master)。

**[事実]** さらに `git worktree add ../ws-<N> ... origin/master` は、2026-10-12 時点では
**`origin/master` が存在しないため実行不能**。後任 PM が
`docs(workflow): make main the PR base branch and fix minor doc errors` で
「`origin/master` (7b2440b) は `origin/main` (fd1e8ca) の strict ancestor で 12+ commits 遅れ」と確認・修正したのがこれ。

**[事実]** user は 10-11 21:18:29 に「リポジトリにも worktree 導入前の古い記述によって subagent が
master に書き込んでしまうなど、大量の混乱が見られます」と指摘。**是正は session interrupt で未完了**。

### 3-2. 状態の二重管理を自分で設計し、7 時間放置した

**[事実]** 前任 PM は 14:08:37 に rules 51 で「状態表現: **GitHub Projects の列 + `state:backlog|todo|in-progress|in-review|done` label**、
`area:*` label」と設計した。**設計段階で二重管理を作り込んだ**。

**[事実]** 移行 subagent (`ses_ed6a324c9ffeReDU7Pcfx5ioca`) は「state/area ラベル 275/275」
「Project #2 275/275 追加 (Status 設定済み)」を報告。**両方に同時に書き込む運用**になった。

**[事実]** 21:01:50 に user が「これは最悪の状態だ」と指摘。21:04:28 に前任 PM は
「状態管理が二重管理になっていたのが原因です。正しい設計: `state:*` ラベルを全削除し、
状態は **Projects V2 の Status 項目のみ**で管理」と回答。subagent (`ses_ed5265d0effeVhsR1aulR853Hj`) が
`state:*` ラベル全削除 (276 issues・定義 6 件) と Project Status 不整合 3 件の修正を実施。

**[事実]** 14:08 に自分で書いた設計ミスを、**user に指摘されるまで 7 時間 (14:08→21:01) 放置**した。
原因を「subagent 側の誤り」や「古い記述」に帰属させていたが、根源は自分の rules 51 である。

### 3-3. 「CAB-\* → #N 全面移行」の未実施

**[事実]** user は 14:00:07 に「(私からの提案: CAB-*** を廃止し GitHub Issues (#***) へ全面移行)」と提案した。

**[事実]** 21:03:08 に user が「例えば #273 など `CAB-*` 記述はまだ大量に残っている。私は「CAB-* 記述を全て移行しろ」と
指示したが、なぜ指示に従わない？」と再指摘。直後に委任した subagent が
**本文 276 件・コメント 315 件・2,682 箇所**を後追いで置換 (失敗 0)。

**[事実]** ただし **repo 内のファイル名は未変更** (例: `tools/shimx/pathreg/REPORT_CAB-271.md`)。
リネームは別タスクとして残っている (`docs/REFERENCES.md` `[CAB_TO_GH]` に対応表)。

### 3-4. 禁止規則を作った本人が、共有ワークツリーで破り続けた

**[事実]** 13:07〜13:20 に 2 件の時刻付き事故が発生している。

1. **`git reset` で他セッションのコミットを喪失**: CAB-273 agent の初回 commit `e407a4f` が、
   CAB-269 agent の**共有ワークツリー**での `git reset` (reflog 実測: `reset moving to db6565c`) で消失。
   同内容を `5d0d321` として再 commit。**`5d0d321` のメッセージに
   `[re-commit after another session's git reset dropped e407a4f]` と明記されている**。
2. **`git commit --amend` で他 agent の staged WIP 48 ファイルを巻き込み** → `reset --soft db6565c` で即時復旧。

**[事実]** 時刻未記録の事故として、**`git stash` 誤実行**で他セッション WIP 20 ファイルを
巻き込んだ例がある (CAB-216, `ses_ed82b06d2ffeBD9bvAJCLRZjsr`)。
`git show stash@{0}:<file>` で全復元。

**[事実]** 前任 PM は 13:28 にこれらの対策として SUBAGENT_RULES.md に
「共有ワークツリーでの `git reset` / `git checkout` / `git stash` を全面禁止」を rules 化した
(= 禁止規則を作った張本人)。

**[事実]** その**約 2 時間後**、前任 PM 自身が main の共有ワークツリーで禁止した操作を実行した:

- 15:25:31 `cd <main worktree> && ... git checkout -- . 2>/dev/null; git reset -q; git status --porcelain | head -6`
- 15:35:48 `cd <main worktree> && git cherry-pick --abort 2>/dev/null; git reset -q && ...`

**[事実]** さらに**同一 merge commit を 2 つの worktree に重複作成**した。15:38:43 に main worktree で、
15:39:14 に `ws-sync` で、同一メッセージ "Merge origin/master into master ..." の merge commit を作成
(`8084bb3` と `faeede5` の二重マージ)。

**[事実]** 前任 PM 自身の reasoning (15:34:22) に **"I made the same mistake AGAIN"** とあり、
原因を「コマンドが main worktree を指す `cd ...` で始まっていた。シェルは毎コマンド main worktree にリセットされる」
と記録している。**cwd が毎コマンドリセットされる**という環境仕様を 3 回連続で見落とした。

### 3-5. 「全作業 subagent 委任」の常態化した逆行

**[事実]** user は 10-10 15:08:28 に「分析を含む全ての作業は作業ごとに subagent へ delegate する必要があります」、
10-11 15:59:56 に「**あなたは基本的にオーケストレーターに徹します**」と明示していた。

**[事実]** 時間帯別の直接作業量 (shell / subagent) は 2026-10-11 で 16時 11/1・**17時 21/0・18時 29/0**・
19時 2/3・20時 6/1。**17〜18 時の 2 時間は shell 50 回・subagent 0 回**。
`.github/` の OpenCode v2 ワークフロー構築・R2 アップロード・`gh run` 反復を PM 自身が直接実行した
(user の 18:16:28「2時間経過しましたが、進捗としてはいかがでしょうか？」はこれ。)

**[事実]** 20:14:21 に「なぜここで作業を？subagent に委任してください」と指摘され、
前任 PM は 20:15:30 に「すみません、直前にメインが診断を行っていました。委任します」と謝罪したが、
**20 時台も shell 6 回**が残っている。

**[推断]** 前任 PM は「自分が直接やった方が速い」を繰り返した。しかし PM の価値は統括
(チケットの統合・分配・並列数の維持) にあり、実作業の速度ではない。自ら実作業を奪うと
In Review の検収が止まり、実装側 subagent も止まり、全体スループットが落ちる。
21:04:28 の自己分析「orchestrator 作業に忙殺され、subagent 投入が老人ホーム状態でした」は原因を正しく捉えている。

### 3-6. 「1 チケット = 1 subagent」が最後まで守られず、最後の 3 分で再発した

**[事実]** 21:41:26 に前任 PM が投入した 4 本は**いずれも 1 agent が複数系統・複数チケットを担当**していた:
「検収A-B: C/D/F/H 系統」「検収C-D: OTT/Serum/FA/KH系」「検収E-F: IPP/lift系」「検収G-H: plugin/起動系」。

**[事実]** さらに 21:44:27 に投入した「検収統合: 全オーケストレーション」は
**orchestrator のさらに上に orchestrator を作る二重構造**だった。prompt 内に
「最重要: 1 agent = 1 ticket 厳守」と書きながら、**自分は 3 分前に 4 本の複数担当 agent を出している**。

**[事実]** 21:11 に投入した 11 本バッチは `"cancelled"` で終了している
(provider の制約による同時バッチ上限。user は 06:55:03 に「現在の provider は相当頑丈なので上限を設けずとも大丈夫」と述べていた)。

**[事実]** 21:44:27 に user が指摘、21:46:15 に「ですから、なぜあなたが統括しないのですか？」で中断。
**最後の 3 分で再発した**ことが致命的だった。

### 3-7. 禁止事項の浸透手段が「notice ファイルを置く」で終わった

**[事実]** `sleep` 禁止は **3 回**指示されても根絶しなかった:

1. 10-09 18:42:08「sleep コマンドで固定時間の待機を行わないでください」
2. 10-11 18:57:15「**以前も指摘しましたが**、sleep による10秒以上の待機は…禁止します」
3. 10-11 19:07:15「sleep 禁止についてはドキュメントに明確に記録し、また現在継続中のエージェントにも伝達してください」

**[事実]** 前任 PM の対応は ①SUBAGENT_RULES.md に明記 ②`.github/prompts/implementer.md` にも追加
③各稼働セッションの作業 dir に `ZZ_NOTICE_sleep.md` を直接配置 — の 3 つ。**いずれも間接手段。**

**[事実]** それでも CAB-265 (MX-3b, `ses_ed6fe33d5ffeE4ljhnQHrLc1z9`) が **`sleep 295` を 48 回**使用。
(入力に内部不整合あり: `children.json` は当該 session id を「MX-3b D11 mock」に、§7-8・§8 は
「CAB-265 (MX-3b)」に紐付ける一方、§6-1 の commit list だけ `07b9fb2` を「CAB-265 / MX2-1」としている。
本書は多数派 (§7-8・§8) に従い MX-3b で統一。)
前任 PM は 19:20:21 に「ルール違反」と検出したが、**中断指示は出さなかった**。

**[事実]** 前任 PM 自身も 18:37:51 (`sleep 90`)・18:41:43 (`sleep 120`)・18:52:02 (`sleep 150`) を実行。
18:57 の禁止宣言より前だが、**10-09 の初回指示には違反**している。

**[事実]** コード品質も同構造で、4 回連続で指摘を受けた: 20:25:59 (jq 1 行で済む処理に 60 行以上の Python) →
20:38:45 (ドメイン用語 "FL" をインフラ step 名に入れた) → 20:42:39 (「heredoc 禁止」と言いながら heredoc を書く自己矛盾) →
20:43:51/20:44:21/20:44:49 (system-wide service の是非・daemon-reload 順序・chmod の実行場所)。
前任 PM は 20:54:36 に「ご指摘は完全にその通りで、私の前回 notice は矛盾を犯していました」と謝罪した。

**[事実]** 前任 PM 自身の 21:46:21 の言葉:「統括するのは私の仕事です」。
**問題は「気づいていない」ことではなく、気づいた後の是正が間接手段に終わり、実行時に強制する仕組みがなかったこと**。

---

## 4. 後任 PM の再発防止ルールへの反映表

| 前任の問題 (証拠) | 現在どこの規約で防がれているか |
|---|---|
| main / master の取り違え (§3-1)。PR #278・#279 が `--base master` | `AGENTS.md` §1 (既定ブランチは `main`・`main` への直接 commit/push 禁止)・`docs/WORKFLOW.md` §2 (**worktree は `origin/main` から切る**・既定ブランチ `main`・master を base にした PR は行わない)・`docs/DECISIONS.md` D4 |
| `git reset` / `checkout -- .` / `stash` で他セッションのコミット・WIP を喪失 (§3-4)。実事故 2 件 (`5d0d321` の message・CAB-216) | `docs/WORKFLOW.md` §1 禁止 git 操作 (**「他セッションのコミット・WIP を消す実事故が 2 件発生している」と明記**)・`AGENTS.md` §3・§4-5 (破壊的 git 操作禁止) |
| `commit --amend`・`git add -A` で他人の WIP を巻き込む (§3-4) | `docs/WORKFLOW.md` §1-3 (`git add <自分のdir>` + `git commit -- <自分のdir>`。`git add -A` / `git add .` 禁止)・§4-4 (担当 dir 以外の未コミット変更は他担当の WIP: 触らない・commit に含めない)・`AGENTS.md` §3 |
| 状態の二重管理 (§3-2)。`state:*` ラベルと Project Status の併存 | `docs/WORKFLOW.md` §3 (チケット状態の正は **issue の open/closed + ラベル + PR** (Project V2 の Status は 2026-10-14 #2435 で参考に格下げ)・**label `state:*` は使わない**・分類を変えるラベルの変更は PM の責務)・`AGENTS.md` §4-7 (Linear 書き込み・`state:*` ラベル新規作成・付与の禁止)・`docs/pm/DIRECTIVES.md` §2 |
| CAB-\* と #N の混在 (§3-3)。2,682 箇所の後追い置換 | `docs/WORKFLOW.md` §7 (commit/PR に過去の `CAB-xxx` 採番を**参照してよい**＝番号の対応は保つ)・`docs/REFERENCES.md` `[CAB_TO_GH]` (対応表の正本) |
| 委任逆行 (§3-5)。10-11 17〜18 時に shell 50 / subagent 0 | `AGENTS.md` §1 (**全作業は subagent 委任。1 チケット = 1 subagent、10 tool call 超は必ず委任**)・`docs/WORKFLOW.md` §7 (同文)・§2 (PM は merge と方針変更のみ) |
| 1 agent = 複数チケット (§3-6)。21:41 の 4 本・orchestrator 入れ子 | `AGENTS.md` §1・`docs/WORKFLOW.md` §7 (**1 チケット = 1 subagent**)・§3 (役割区分: 実装 / 検収 / PM の 3 区分・検収は独立 subagent・自分で完了にしない) |
| sleep ポーリング (§3-7)。3 回指示されても根絶せず PM 自身も違反 | `docs/WORKFLOW.md` §6 (**長時間の待機に `sleep` を繋げない。完了確認は 1 コマンドのポーリングか、結果が返る仕組みを使う**) |
| worktree 導入前の古い記述で subagent が master に書き込む (§3-1)。user 21:18:29 の指摘 | `docs/DOC_MAP.md` (正史は `docs/` に集約)・`AGENTS.md` §1・§2・`docs/pm/DIRECTIVES.md` §2 (「古い記述が大幅に含まれる」への対応として docs/ 正史化) |
| 検証手順の属人化 (旧 preflight 証跡のハッシュ転記) | `docs/DECISIONS.md` D6 (証跡転記の廃止)・`docs/WORKFLOW.md` §6 (preflight 代替: 報告前に自分で実行する検証コマンド群) |

---

## 5. 未然に防げなかった・防ぐべきだった項目 (正直に)

1. **cwd が毎コマンドリセットされる環境仕様への対策が規約にない。**
   §3-4 の二重 merge は `cd <worktree> && git commit` というコマンドの形で起きた。
   `docs/WORKFLOW.md` には **`git -C <worktree>` を強制する規定が無い**。前任 PM の reasoning は教訓を
   正しく抽出していたが rules に落とせなかった。後任 PM は `docs/WORKFLOW.md` §1 への追記を検討すべき。

2. **「In Review / In Progress の件数」と「稼働 subagent 数」を突き合わせる自動検証ループが無い。**
   user は 10:35:41 (10-10)・08:32:19・08:58:47・21:01:50 と**同じ指摘を 4 回**受けたが、
   前任 PM は都度手で数えた。後任 PM 側にも「件数 vs 稼働数」の定期突合は未整備である。

3. **並行度の下限目標と「1 チケット = 1 subagent」の両立設計図が無い。**
   21:06:38 に「稼働 subagent 数が 15 を下回ることを禁止」と 21:07:57 に「恒久ルールとして記録」としながら、
   21:41 には複数担当 agent で再発した。数量目標とチケット粒度の整合を取る規約 (起票の細分化・
   親子チケットの作り方) は `docs/WORKFLOW.md` にまだ無い。

4. **「正しかった判断」の記録が薄い。**
   前任 PM は 13:01:03 に user の誤認 (`c737c4a` を user の手動 fix と誤解していた) を正確に訂正し
   (実際は検収 subagent が remote の存在に気づかず作った重複マージ)、21:04:28 に停滞原因を正しく自己分析している。
   これらは**解任理由とは別に評価すべき資産**である。Linear free plan の 250 issue 上限到達 (13:42:01) も同様。

5. **解任自体は中断という形で実行されたため、後始末が後任 PM に移った。**
   21:18:29 の「worktree 導入前の古い記述の是正」・21:44:27 の指摘への対応・
   `feat/add-opencode` の 20 commits (user の 4 回の品質指摘を全て反映した完成形) の PR 作成・マージは**未達のまま**。
   状態の正本は `docs/STATUS.md` / `docs/HANDOFF/<日付>.md` であり、本書には書かない。

6. **作業ディレクトリ名の "work" 3 義 (`worktree` / `tools/**/work/` / `work_verify/`) の整理が不完全。**
   [推断] 前任 PM は 21:26 に worktree 運用の徹底を委任したが interrupt で未完了。後任 PM 側は
   `docs/WORKFLOW.md` §1-6・§6・§2 で場当たり的に対処したが、**命名規則として 1 つの表にまとまっていない**。

---

## 6. 引用元索引

### 6-1. 主要メッセージ (user / 前任 PM)

| 時刻 | msg id | 内容 |
|---|---|---|
| 10-10 15:08:28 | `msg_1246d5188001H4jo4GfpiCI3t3` | 全作業 subagent delegate の明示 |
| 10-11 14:00:07 | `msg_12955207a001Y1om1cMBeXwake` | Linear 廃止・GitHub 移行・worktree+PR フロー・CAB 廃止の提案 |
| 10-11 14:08:37 | `msg_1295bea37...` | rules 51〜58 追記 (**`--base master`・`origin/master` 起点の誤り**) |
| 10-11 15:59:56 | `msg_129c2d1ea001n80FhSCE5LVgNo` | feat-add-opencode の引継ぎ・「オーケストレーターに徹する」 |
| 10-11 18:57:15 | `msg_12a642fe00016sY10bagBbabGc` | sleep 禁止 (2 回目) |
| 10-11 21:01:50 | `msg_12ad73b9e001Hrv1dGoiI0qn31` | 「これは最悪の状態だ」(`state:*` 全削除を命令) |
| 10-11 21:03:08 | `msg_12ad86b18001Zrqzh5mSCGHS5S` | CAB-\* 移行の未実施を指摘 |
| 10-11 21:17:36 | `msg_12ae51a7a001ccZ7XzWnHNzn4k` | 「何その適当な subagent は」 |
| 10-11 21:18:29 | `msg_12ae677f2001SRZCBLhqkzy6L8` | 「worktree 導入前の古い記述によって subagent が master に書き込んでしまう」 |
| 10-11 21:44:27 | `msg_12afe3e18001CNJxeLfFb5mpDi` | 「なぜ1エージェントが複数チケットを担う、混乱と越権の源にしかならない仕組みを？」 |
| 10-11 21:46:15 | `msg_12affe4f0001HaB54c4c82K6ID` | 「ですから、なぜあなたが統括しないのですか？」 |
| 10-11 21:49:16 | `msg_12b02a54e001OhO4Z92i3Z0WPX` | `finish=error` / `error.type=aborted` / "Step interrupted" (interrupt で終了) |

### 6-2. 主要コミット

| commit | 内容 | 状態 |
|---|---|---|
| `e407a4f` | CAB-273 tol gate 撤去 初回 | **喪失** (CAB-269 の `git reset`。reflog: `reset moving to db6565c`) |
| `5d0d321` | 同内容を再 commit | main に在る (message に reset 喪失の注記) |
| `c737c4a` | user の手動 fix に見えた重複マージ | main に在る (**実は検収 subagent 作成**) |
| `a6c8277` | §13-8 復旧 | **dangling** (どのブランチにも属さない。内容は `8ff9a28` 経由で残存) |
| `fb24336` | CAB-261/262 検証 WIP 復旧 | main に在る |
| `8084bb3` | "Merge origin/master ... into master" (main worktree 側) | main に在る |
| `faeede5` | 同 merge の重複 (`ws-sync` 側) | 履歴から消滅 |
| `6a598b9` | sync/origin-reconcile の merge | branch `sync/origin-reconcile-2026-10-12` (PR #279・OPEN) |
| `23aa4be` | fix(ipp): cab274 verification note (ws-sync 側) | **どのブランチにも属さない** |
| `04316b7` | fix(ipp): cab274 verification notes (main 側) | main に在る (subject が 1 文字違いの重複) |

### 6-3. 参照方法

- 本分析の入力: セッション `ses_ee0c66629ffeZ92Uddt9mOoVur` の `session`・`message` API 出力と
  子セッション一覧 (`children.json`) の集計結果 (2026-10-12 時点のスナップショット)。セッションは
  ephemeral なため原本は repo 外に退避済み。**再現するなら `opencode api get /api/session/<sid>` /
  `.../message` を用いる** (user の 09:04:41 指示)。要約は `docs/HANDOFF/<日付>.md`。
- **user 発言の逐語は `docs/pm/DIRECTIVES.md` が原本の正本。本書は分析であり、指示の複製を持たない。**
