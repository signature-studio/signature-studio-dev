> **正本**: 本書 (`tools/pm/REPORT_APPENDIX_2591.md`) が #2591 の測定の正本。`tools/pm/REPORT.md` は 250 行上限のため本体へ追記しない (`docs/DOC_MAP.md` §1)。pm.md の文字列検査の前歴は `tools/pm/REPORT_APPENDIX_2349.md`。

# #2591: pm.md の needs_decision を PR 起点に直し、rule=skip と投稿前の確認を足す

測定した commit: `870c381e` (コードを変えた最後の commit)。親 #2319 (PM agent の初回 live 監査の欠陥 5 件の是正)。
既知類型との関係: 該当なし (lift の欠陥ではなく PM 運用の prompt)。

## 1. 問題と変更

- 問題 (監査の報告による。本付録では再測定していない): (1) `needs_decision` の節は「`needs-user-input` が付いた issue」を読むと書いていたが、Worker (`infra/pm-worker/src/pm.ts` の `detectPm`) は PR 起点で ref は PR 番号。(2) 「対象なし」用の rule が無く R9 を流用していた。(3) `/oc` を含む否定形の文をコメントに書いた (#2303)。(4) closed・merge 済みの対象を確かめずに質問を出した。(5) closed の issue に `needs-user-input` が残った。
- 変更 `.github/prompts/pm.md`:
  - `needs_decision` 節: 起点を PR (ref = PR 番号) に変えた。Worker の条件 `sig.review.state === "CHANGES_REQUESTED" && sig.review.needs` と、語の正本 `NEEDS_KEY` (`infra/pm-worker/src/needs.ts`) を引用した。判断の印は ref の PR に残す。質問の `needs-user-input` は `Closes #N` の issue に付ける。`Closes #N` の無い PR はコメントだけにして既定案で進める (R9)。
  - 判断の記録: `rule=skip` を新設 (対象が無い・解消済み・語が引用だけ。`reversible=yes`)。R9 の代わりに使う。印は ref に残す (Worker は ref ごとの応答で再送を止めるため)。
  - 「投稿・質問の前の確認 (必須)」節を新設: (1) 対象の状態 (issue が closed なら質問しない・残る `needs-user-input` は外す。PR が merge 済みなら判断しない・merge 後の検収や訂正があればそれに従う。論点が後の push で解消していれば判断しない。いずれも `rule=skip`)、(2) 投稿する本文の `grep -c '/oc'` が 0 件であること。
  - 「書いてはいけない操作」: `/oc` を否定形・引用・説明でも書かない (「launch 行なし」と書く)。既存の禁止文は残した。
  - ダイジェストの件数: `skip` を加えた (印が集計から漏れないように)。
- 変更 `docs/WORKFLOW.md` §12: 判断の印 (`rule=skip`・ref に残す) と、正本 (`.github/prompts/pm.md`) への参照だけを足した。規約本文は複製しない。
- 変更 `.github/scripts/tests/test-dispatch-context.sh` §10c: 上の新規文言 15 件を `pm_has` で検査する (文言を消すと FAIL する)。
- 変えないもの: `infra/pm-worker/` (検出条件・`PM_MARK_RE`・マーカー仕様)、`.github/workflows/`。

## 2. 測定

- 検査: `bash .github/scripts/tests/test-dispatch-context.sh` (pm.md の節 10・10b・10c を含む)。環境: GitHub Actions の runner (4 CPU)。測定時の load average `0.29 0.20 0.10`。

| 測定 | 結果 | 所要 |
|---|---|---:|
| 変更前 (`origin/main` `d460d139` の pm.md とテスト。作業ツリー `5d33ba04` で測定。両者の該当ファイルは同一) | 135 passed, 0 failed | 3.9 s |
| 変更後 HEAD `870c381e` | 150 passed, 0 failed | 3.9 s |
| ネガコン: pm.md から `<!-- oc-pm-decision: rule=skip reversible=yes -->` の行を削除 | 148 passed, 2 failed (FAIL: 当該例示行・`R9 の代わりに使う`) | 3.9 s |
| ネガコン後に `git checkout -- .github/prompts/pm.md` で戻す (HEAD と同一) | 150 passed, 0 failed | 3.9 s |

- 他のテスト: `.github/scripts/tests/test-*.sh` の残り 7 本 (`no-pr-outcome`・`opencode-stdin`・`pr-lint`・`pr-loop`・`run-outcome`・`watchdog`・`workflow-pm-job`) はすべて終了 0。`python3 -m unittest discover -s tools/pm -p 'test_*.py'` は `Ran 42 tests` で OK。
- 追加した検査は 15 件 (`test-dispatch-context.sh` §10c の for ループ。PASS 数 135 → 150 の差分と一致)。

## 3. 受入条件の判定 (issue #2591)

| # | 受入条件 | 判定 | 根拠 |
|---|---|---|---|
| 1 | `needs_decision` を PR 起点に書き直す | 達成 | pm.md の `needs_decision` 節 (Worker の条件・ref は PR 番号・印は PR に残す) |
| 2 | `rule=skip` を新設し R9 の流用をやめる。marker の説明に skip | 達成 | pm.md「判断の記録」・`needs_decision` 判断 1・digest の件数 |
| 3 | `/oc` を含む文字列を書かない。`grep -c '/oc'` を必須にし「launch 行なし」と言い換える | 達成 | 「書いてはいけない操作」・「投稿・質問の前の確認」2 |
| 4 | 質問の前に対象の closed・merge 済み・merge 後の検収の有無を確かめる | 達成 | 「投稿・質問の前の確認」1 |
| 5 | closed の issue から `needs-user-input` を外す | 達成 | 「投稿・質問の前の確認」1 (`rule=skip`) |
| 6 | marker 仕様 (`PM_MARK_RE`) と `infra/pm-worker/`・`.github/workflows/` は変えない | 達成 | §4 の差分 0 行 |
| 7 | WORKFLOW §12 は pm.md を参照する範囲だけ合わせる | 達成 | `docs/WORKFLOW.md` §12「不在中の自動判断」(3 行増) |
| 8 | `test-dispatch-context.sh` の pm.md 節 (10) が通る | 達成 | 150 passed, 0 failed (§2) |

- issue 本文の「post-merge review」は repo の文書に定義が無い。pm.md では「merge 後の検収・訂正 (同じ論点を直した後続 PR やコメント)」と具体的に書いた。

## 4. 測定後のコード差分

`git diff 870c381e HEAD -- .github infra/pm-worker` の出力: 0 行 (差分 0)。main 取り込み後の再測定は不要 (`docs/WORKFLOW.md` §6)。

## 5. 未解決

- live の PM run で `needs_decision` が PR 起点で動き、印が PR に付くことは、次の実 run の digest (`rule=skip` の件数) で観測する。本付録は文書と検査の変更だけを測った。
