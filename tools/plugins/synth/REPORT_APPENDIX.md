# tools/plugins/synth/REPORT_APPENDIX.md — #534: C++ x64 DLL 9 本の `emcc -c` (現 HEAD 実測)

- 本書は REPORT.md (250 行上限) の付録。 結論は REPORT.md §0-4 と §5 を見る。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/plugins/synth/cpp_lift.sh <block> 1500` (出力は `tools/plugins/work/synth/cpp<block>/`)。
- 素材: `fl-win64` / `toolchain-emsdk` ([EMSDK]) / `toolchain-retdec` ([RETDEC]) (`docs/REFERENCES.md`・`docs/WORKFLOW.md` §11)。

## A. 現 HEAD の実測 (測定 HEAD = main 9aad4595 を worktree `ws-534` で実行)

- 実行: 9 本を `xargs -P 3` で並列実行。 総経過 7 分 42 秒 (`time` の実測)。 9 本とも `cpp_lift.sh` の終了コードは 0。
- `emcc -c` 通過 **4/9**: 23914 Kepler / 23944 Morphine / 24159 PoiZone / 24298 Transistor Bass (`emcc_c_rc` = 0)。
- 不通過 5 本 (最初のエラー):

| DLL | block | `.pdata` 関数 | 欠落 define | `emcc -c` | 最初のエラー |
|---|--:|--:|--:|--:|---|
| BooBass_Eng | 21202 | 1,579 | 211 | 1 | `'%arg2' defined with type 'i32' but expected 'i64'` (E3) |
| Kepler Exo engine | 23916 | 3,193 | 2 | 1 | `no libcall available for fp_round with type f80` |
| Sakura engine | 24163 | 1,644 | 1 | 1 | `do not know how to soften fp_extend` |
| Sawer engine | 24167 | 1,676 | 1 | 1 | `do not know how to soften fp_extend` |
| Toxic Biohazard | 24216 | 1,841 | 1 | 1 | `do not know how to soften fp_extend` |

- 局所修復 (`engine_fixcmp.py`) の適用件数 (`fixcmp_patched`) は 9 本とも 0 で、修復後の `emcc -c` 結果は修復前と同じ。 E1 (icmp ptr/i64) は共有鎖 `tools/plugins/lift/passes/fix_icmp_ptr.py` で解消済み。
- 未実装 helper (distinct 宣言数) は 83〜121 (BooBass 15)。 `i256_trap` は 3 (Morphine のみ 24)。 `f80_funcs` が非 0 なのは 23916・24163・24167・24216 の 4 本。
- Morphine (23944): RetDec の HLL 生成段が `HLL_CAP` (既定 300 s) を超えたため、RetDec を kill して `e.drc.ll` から後段を再開した (`hll_killed_s` = 352、`lift_s` = 404)。 通常経路 (kill 無し) の最後までの実測は無い。
- 生データ: `summary.csv` の 9 行は `tools/plugins/work/synth/cpp<block>/summary.csv` (生成物・gitignore)。
- judge (C++ 9 本のみ。 shell 12 本の結果が無いので `synth_e2e.sh` 全体の判定ではない): KNOWN 9 / NEW-FAIL 0 / FIXED 0 / MISSING 0 / exit 0。 `known.json` からは通過 4 本の `emcc_c_rc` を外した。

## B. 残件 (起票先付き)

| 残件 | 影響 | 起票先 |
|---|---|---|
| E3 (i32 仮引数の i64 使用) BooBass_Eng `function_180049450` | 21202 の `emcc -c` 不通過 | 子 issue (本 PR の後に起票) |
| BooBass_Eng の define 欠落 211 件 (25,828 B、うち 67 件は call 先) | 21202 の link 時未解決 | 同上 |
| Morphine の通常経路 (kill 無し) の実測 | 未測定 (今回は再開経路で通過) | 同上 |
| f80 libcall (`fp_extend` / `fp_round`) 4 本 | 不通過 4 本 | #197 (f80→f64 lowering)・#523 (Delay 3 の fp_extend) |
| VEX helper 未実装・CPUID 分岐での SSE 固定の可否 | lift 結果の完全性 | #527・#779・#1163 |
| E2 (SSA 値入り定数式) / E4 (`fix_asm_stores` の def 欠落) | 今回の 9 本の最初のエラーには出なかった | 再現時に起票 |
