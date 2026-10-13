# tools/plugins/synth/REPORT_APPENDIX.md — #534: C++ x64 DLL 9 本の `emcc -c` (HEAD 3418333a 再測定は未実施)

- 本書は REPORT.md (250 行上限) の付録。 結論は REPORT.md §0-4 と §5 を見る。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 HLL_CAP=100000 bash tools/plugins/synth/cpp_lift.sh <block>` (出力は `tools/plugins/work/synth/cpp<block>/`)
- 素材: `fl-win64` (`tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開)。 `toolchain-emsdk` ([EMSDK]) / `toolchain-retdec` ([RETDEC]) が必要 (`docs/REFERENCES.md`・`docs/WORKFLOW.md` §11)。 本 runner では両者が無く、再測定していない (462812e4 は HEAD 3418333a の再測定を記録しているが、run ID・`summary.csv` が残っておらず本書では根拠にしない)

## A. 未測定

- `emcc -c` の現 HEAD での通過本数は**未測定**。 再測定には上記 2 つの toolchain 素材が必要。
- 旧記録の数値表は出所を確認できないため本書から外し、#534 のコメントへ「出所不明の旧転記・未検証」として移した (分割移動)。
- Morphine (23944) の `PLUG_REUSE_DRC=1` 再開経路 (`cpp_lift.sh` の `resume_lift`) は**未実測**。 lift 秒の値も未確認。

## B. E1 修復 (`fix_icmp_ptr.py`)

- 共有鎖 `tools/plugins/lift/passes/fix_icmp_ptr.py` は HEAD に組込済み (PLG-F6-2 #545)。 `engine_fixcmp.py` (synth 局所) は `cpp_lift.sh` の表示用に残っている。
- E1 修復の効果は未測定 (再測定には上記の素材が必要)。

## C. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| f80 (x86_fp80) の libcall (`fp_extend` / `fp_round` / `frem`) | `emcc -c` 不通過の要因 (件数は未測定) | #534 (本 issue)。 f80 の扱い (f64 化の精度・同値試験) は別判断 |
| E3 (i32 仮引数の i64 使用) BooBass_Eng `function_180049450` | 件数は未測定 | #1301 (PLG-G2-13) |
| Morphine (23944) の HLL 段を含む通常経路の実測 | 未測定 | #1301 (PLG-G2-13) |
| VEX helper 未実装 (Kepler 79 本等) と `PLUG_AVX256` 有効時の再測定 | lift 結果の完全性 | #534 (本 issue) |
| define 欠落 (BooBass_Eng 211 件) の原因 | 1 本 | #1301 (PLG-G2-13) |
| E2 (SSA 値入り定数式) / E4 (`fix_asm_stores` の def 欠落) の現 HEAD での再測定 | 再測定の未実施 | #534 (本 issue) |
