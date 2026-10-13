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
   ├ issue 起票 (gh issue create) ──┤                                  │
   ├ worktree 指名 ─────────────────┤                                  │
   │                                ├ gh issue view N                  │
   │                                ├ git worktree add ../ws-N         │
   │                                ├ 実装 + e2e + REPORT              │
   │                                ├ commit (scope)                   │
   │                                ├ push -u origin <N>-<slug>        │
   │                                ├ gh pr create --base main         │
   │                                ├ gh issue comment N (進捗・実測)   │
   │                                └ Status → In review を依頼 ────────┤
   │                                                                   ├ 自分の worktree で
   │                                                                   │  PR branch を checkout
   │                                                                   ├ e2e 独立再実行 + 別算法検算
   │                                                                   ├ ネガティブコントロール
   │                                                                   ├ PR review (approve / request changes)
   │                                                                   └ 誤記は fix commit で同 branch に push
   ├ review approve 確認 ──────────────────────────────────────────────┤
   └ gh pr merge --merge ──→ branch/worktree 削除
```

- **worktree の場所**: リポジトリの**親ディレクトリの `ws-<N>`**
  (`git worktree add ../ws-<N> -b <N>-<slug> origin/main`)。
  既存 worktree は `git worktree list` で確認。**他人の worktree には触れない** (消さない・checkout しない)。
- **merge は PM のみ**。merge 後、`git worktree remove --force` で**自分が使った worktree** を片付ける。
- **競合時**: `git rebase origin/main` で解消してから `push --force-with-lease` (自分 branch のみ)。
- **既定ブランチは `main`** (`origin/HEAD → origin/main`)。旧 `origin/master` は `main` の祖先で
  12+ commits 遅れの凍結枝。master を base にした PR・master への pull/push は行わない。

## 3. ステータスと責任区分

| 役割 | 着手時 | 完了時 | 禁止 |
|---|---|---|---|
| 実装 subagent | In progress | **In review** (自分を Done にしない) | Done への変更・他チケットの Status 変更 |
| 検収 subagent | 対象が In review 確認 | 合格 → Done + コメント / 条件付き → **In review 維持** + 所見 | In review でないものを Done にしない |
| PM (main) | 起票・milestone 確定 | merge・方針変更・是正 | — |

- **チケット状態の唯一の正は Project V2 の Status フィールド + issue の open/closed**
  (技術進捗の正本は `docs/STATUS.md`)。不変条件: `CLOSED ⇔ Done`、`OPEN ⇔ Backlog|Ready|In progress|In review`。
- **label `state:*` は使わない** (2026-10-12 実測で全削除済み・0 件)。新規作成・付与しない。
- **1 状態遷移 = 1 コメント**。コメントなしの状態変更は禁止。
- **Status を変えるのは PM の責務**。subagent は依頼コメントを書く (PM が委任プロンプトで明示許可した場合を除く)。
- **中断・ブロックで終了する場合**: Status は In progress のまま、中断コメント (到達点・WIP 所在・再開手順) を残し、
  最終回答の冒頭に「未完・In Progress のまま」と明記。

## 4. 着手前の確認 (毎回・省略不可)

1. `gh issue view <N>` でスコープ・受入条件・親 issue・検証方法を確認。
2. 同一チケット / 同一 dir に In progress または In review があれば**着手せず報告**。
3. lift / 逆アセ / IR pass / ハーネス系は `docs/DEFECTS.md` を先に読み、REPORT 冒頭に
   「既知類型との関係: 該当 ID / 該当なし」を 1 行書く。
   **番号体系の注意**: `docs/DEFECTS.md` の D1〜D16 と `tools/icall/REPORT.md` §4 の D1〜D13 は
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
  work-liftlib-targets / work-liftlib / work-icall / analysis-ott-binaries。それ以外は
  run が失敗する)。全素材は約 17.7 GiB (2026-10-13 実測) のため必要分だけ指定する。
  - `toolchain-retdec` → `/opt/retdec`、`toolchain-emsdk` → `/opt/emsdk` に展開される。
  - `work-m6-ott` → `tools/m6/work/` + `tools/ott/work/` + `tools/m8/work/` + `tools/m9/work/` + `tools/m10/work/`
    (`tar --zstd -tf` で実測)、`work-liftlib` → `tools/liftlib/work/`、
    `work-icall` → `tools/icall/work/`、`work-liftlib-targets` → `tools/targets/{freshair,kilohearts}/work/`
    の HeartCore / SlateCore のみ (liftlib_e2e.sh の `need` 対象) に展開される
  - `analysis-ott-binaries` → `$HOME/analysis/plugins/ott/binaries/` (OTT_vst2_win64.dll ほか実機バイナリ。
    展開後は `ANALYSIS_DIR=$HOME/analysis` が環境に入る。tools/shared/env.sh の既定 /home/ubuntu/work/analysis を上書きする)
  - `work-m11` → `tools/m11/work/`、`work-liftdiff` → `tools/liftdiff/work/` に展開される
    (gitignore 対象の検証スナップショット。commit しない)。
  - 追加の `work-*` は R2 に置いて、`prepare-event-context.sh` の allowlist に足す (#293)。
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
- **レビュー run の素材**: review ジョブも PR 本文の `oc_artifacts:` 行を読んで素材を取得する
  (素材を要する e2e をレビュワーが独立再実行するため)。PR 作成者は、素材を要する PR の本文に
  実装時と同じ行を書くこと。
- **結果**: agent の text ブロックは全て run のログ (`gh run view <id> --log` の `Write step summary`) と
  `$GITHUB_STEP_SUMMARY` の両方に出る。`Dump OpenCode events` には作業の流れ (tool 名・状態・所要 ms・
  入力の先頭 200 文字・cost) が出る。repo が public のため、**tool の出力と生 JSONL はログに出さない**
  (認証情報・FL 由来物の漏洩防止。secret マスクは登録値との完全一致でしか効かない)。
  issue へのコメントは agent が `gh issue comment` で行う。
- **上限**: job は 60 分。収まらない作業は中間 commit + draft PR で区切る。
- 稼働本数は「走っている Actions run 数」で数える (`gh run list --status in_progress`)。
- **PM の watch ルール (依頼者指示 116)**: 起動した全ての run は無条件で `gh run watch` する。PM が
  応答を終える時は、background で `gh run watch` が 1 本以上走っていること。完了通知を受けたら、
  結果の処理に入る前に、次の watcher を起動し直す。
- **実装が始まったチケットは merge まで止めない (依頼者指示 119・120)**: open PR は常に次のいずれかの状態で、
  各状態に「次の一手」が決まっている。止まっている PR を残さない。
  判定は表の上から順に評価し、**最初に該当した行**を採る。draft の PR は、CONFLICT・FIX に該当しなければ
  review の有無・種別によらず DRAFT になる。

  | 状態 | 判定 | 次の一手 |
  |---|---|---|
  | CONFLICT | main と競合 (`mergeable=CONFLICTING`)。draft でも適用。**競合 PR は review run が起動しない** | main を merge して競合を解消する run |
  | FIX | oc-reviewer の最新 review が現在の head に CHANGES_REQUESTED。draft でも適用 | 指摘 (reviewer・Copilot・inline) の修正 run。妥当でない指摘は実測を添えて理由を PR に残す。draft なら修正後に ready にする |
  | NOREVIEW | ready で現在の head に review が無い | review 再起動 (run が既にあれば待つ) |
  | DRAFT | draft (CONFLICT・FIX に該当せず、review の有無・種別を問わない) | ready にして review 再起動 |
  | COPILOT | reviewer が COMMENTED (Copilot の review 待ち) | 30 分経ったら close→reopen |
  | APPROVED | approve 済みで未 merge | merge。PR 本文にマージ順があれば先行 PR の後。base が別 PR のブランチなら先行 merge 後に付け替え |

  `sweep_prs.sh` が 15 分間隔で全 open PR を判定し、止まっているものを自動で次の run に載せる。
  着手報告だけで終わった run は `find_silent_runs.sh` で検出して再投入する。
  どちらも repo 外の PM 運用スクリプトで、所在は `docs/REFERENCES.md` `[PM-SCRIPTS]` が正本 (repo からは挙動を検証できない)。

