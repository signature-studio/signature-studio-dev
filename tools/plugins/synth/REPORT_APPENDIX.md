# tools/plugins/synth/REPORT_APPENDIX.md — #534: C++ x64 DLL 9 本の `emcc -c` (現 HEAD 実測)

- 本書は REPORT.md (250 行上限) の付録。 結論は REPORT.md §0-4 と §5 を見る。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/plugins/synth/cpp_lift.sh <block>` (出力は `tools/plugins/work/synth/cpp<block>/`。 `HLL_CAP` の既定 300 s)
- 素材: `fl-win64` / `toolchain-emsdk` / `toolchain-retdec` (`docs/WORKFLOW.md` §11)。 本測定の run で 3 つとも `$HOME/artifacts` に実在し、`tar --zstd -xf` で展開して使用した。

## A. 現 HEAD の実測 (`cpp_lift.sh`、既定 `PLUG_AVX256=0`)

測定: 上 8 本 (Morphine 以外) は変更前の script で 3 本並列 (`xargs -P 3`)、総経過 409 s。 Morphine (23944) は変更後の再開経路 (§B) で別測定し、lift 秒 89 (表の値と §B の値は同じ)。

| DLL | block | `.pdata` 関数 | define | 欠落 define | 未実装 helper | i256 trap | f80 関数 | `emcc -c` rc | lift 秒 | 最初のエラー |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| BooBass_Eng | 21202 | 1,579 | 1,393 | 211 | 15 | 3 | 0 | **1** | 60 | `'%arg2' defined with type 'i32' but expected 'i64'` (E3) |
| Kepler engine | 23914 | 3,194 | 3,697 | 2 | 103 | 3 | 0 | **0** | 144 | — |
| Kepler Exo engine | 23916 | 3,193 | 3,694 | 2 | 104 | 3 | 1 | **1** | 171 | `no libcall available for fp_round with type f80` |
| PoiZone engine | 24159 | 1,638 | 1,790 | 1 | 101 | 3 | 0 | **0** | 69 | — |
| Sakura engine | 24163 | 1,644 | 1,707 | 1 | 84 | 3 | 1 | **1** | 66 | `do not know how to soften fp_extend` |
| Sawer engine | 24167 | 1,676 | 1,833 | 1 | 83 | 3 | 1 | **1** | 78 | `do not know how to soften fp_extend` |
| Toxic Biohazard | 24216 | 1,841 | 1,927 | 1 | 94 | 3 | 1 | **1** | 99 | `do not know how to soften fp_extend` |
| Transistor Bass engine | 24298 | 3,257 | 3,741 | 2 | 87 | 3 | 0 | **0** | 147 | — |
| Morphine | 23944 | 3,050 | 3,321 | 1 | 121 | 24 | 0 | **0** | 89 (再開経路) | — |

- `emcc -c` 通過は **4 / 9**。 内訳: 変更前 script の 8 本で **3 / 8** (23914 / 24159 / 24298)、変更後の再開経路の Morphine 23944 で **1 / 1**。 E2 (SSA 値入り定数式) と E4 (def 消失) は、この HEAD の 4 本では再現しなかった。
- E1 (icmp ptr/i64) は共有鎖 `tools/plugins/lift/passes/fix_icmp_ptr.py` で解消済み。
- 残る不通過 5 本の類型: E3 (21202) 1 本、f80 libcall (23916 / 24163 / 24167 / 24216) 4 本。
- `known.json` の 23914 / 23944 / 24159 / 24298 から `emcc_c_rc` を外した (baseline 更新。 外さないと judge が FIXED で落ちる)。 9 本を judge にかけ、KNOWN 9 / NEW-FAIL 0 / FIXED 0 / exit 0 を確認。

## B. Morphine の再開経路 (修正済み)

- `cpp_lift.sh` の旧再開経路は `sed` で `lift_ranges.sh` から RetDec 行だけを削っていたが、削除範囲が `if/else/fi` を壊し、`lift_resume.sh: line 49: syntax error` で落ちていた (旧 Morphine 23944 は lift_rc 2)。
- 修正: `sed` を止め、`PLUG_REUSE_DRC=1` で既存 `e.drc.ll` から `lift_ranges.sh` を再開する (RetDec を飛ばす既存の仕組み)。 kill は `pkill -f` を止め、`pgrep -f` で得た PID を個別に `kill` する。
- 検証: `RESUME=1 bash synth/cpp_lift.sh 23944 2400` → lift_rc 0 / emcc_c_rc 0 / lift 秒 89 (表 A と同値)。 通常経路 (HLL 段を最後まで回す) の実測は未実施。

## C. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| E3 (i32 仮引数の i64 使用) BooBass_Eng `function_180049450` | 1 本 (不通過) | #534 (本 issue) |
| f80 (x86_fp80) の libcall (`fp_extend` / `fp_round`) | 4 本 (不通過)。 f80→f64 は精度を落とすため既定外 | #534 (本 issue)。 扱いの判断は別 |
| define 欠落 (BooBass_Eng 211 件) の原因 | 1 本 | #534 (本 issue) |
| VEX helper 未実装 (Kepler 79 本等) と `PLUG_AVX256` 有効時の再測定 | lift 結果の完全性 | #534 (本 issue) |
| Morphine の通常経路 (HLL 段を最後まで) の実測 | 未測定 | #534 (本 issue) |
