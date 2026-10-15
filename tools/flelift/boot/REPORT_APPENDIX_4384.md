# tools/flelift/boot — #4384 (WIN-49) CFI 経路の値の観測 (REPORT_APPENDIX_2719 §13 から移動)

> 正本の節は `tools/flelift/boot/REPORT_APPENDIX_2719.md` §13 から移した。REPORT 本体の上限 (250 行) のための分割移動。測定 commit: `c05537cfd`。


- 測定 commit: origin/main `131902f65` を取り込んだ worktree (`4384-x64c-cfi-indirect-call-target`)。素材は `fl-win64` (展開先 `$RUNNER_TEMP/fl-win64`)・`toolchain-emsdk` (emsdk 6.0.12)。
- 既定 lift の再現 (`FLE_BOOT_RUNS=tol`・mode 1): dispatch 209・停止 unit 245 (`0x733090` exit)・clobber 695・GetMem 2,314 / FreeMem 1,199・CFI `oob`。§11 と一致。
- **再現性 (未再現)**: 下の値は、生成 C の作業コピー (`work/probe/`・コミットしない) に probe を入れて取った観測記録。probe は commit していない。`work/probe/` は現在の runner に無く、本 commit (fix) では再実行していないため、この値は再現できていない。再現は子 issue の受入条件 1 で行う。
- **probe の詳細 (未保存)**: probe の具体的な実装 (出力先・挿入方法) は残っていない。対象の VA は `0x1375990`・`0x13752f0`・`0x1105350`・`0x5af120`・`0x410320` の 5 個で、各入口の `rcx`・`rdx`・`dl` を記録した。再現の手順は子 issue で新しく作る。
- 観測された値は、順に `0x1375990` 入口 (`rcx`=0, `rdx`=0)・`0x13752f0`・`0x1105350`・`0x5af120` (`rcx`=0, `rdx`=1)・`0x410320` (`rcx`=0, `dl`=1)。
- `0x410320` は `dl>=0` のとき `call [rax-0x30]` を行う。このとき `rax`=`rcx`=0 のため、読み出し先は `0xffffffffffffffd0` (oob)。**間接 call の受け手 VA は取れなかった** (受入条件 1 は未達)。
- 原因: harness (`fle_boot.mjs` の CFI 観測) が `fle_run(0x1375990)` を全引数 0 で呼んでおり、`self` (`rcx`) が渡されていない。実機の呼出し元と `self` の値は未特定。
- 実機の呼出し元の探索: PE 内 (展開済み 25,166 ファイル) に `0x1375990` の 8B/4B 絶対ポインタは無し。lift 済みコードに `0x1375990` への直接 call の注釈は無し。
- 受入条件 2 (oob の段) は、`0x410320` の読み出し (`rax`=0 基準) が最初の oob と読めるが、これは harness の呼出し方に依存するため、実機の段としての結論にはならない (未達)。
- 受入条件 3 (`boot_metric.py` の `last_step` 文言): 本 commit で、harness 呼出しが引数 0 である事実を文言に入れた。`boot_metric.json` の再生成は #4381 の範囲。
