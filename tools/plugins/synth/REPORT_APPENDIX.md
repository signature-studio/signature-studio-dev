# tools/plugins/synth/REPORT_APPENDIX.md — #534: C++ x64 DLL 9 本の `emcc -c` 実測

- 本書は REPORT.md (250 行上限) の付録。結論は REPORT.md §0-4 と §5 を見る。
- 測定 HEAD: **604e900f** (origin/main。本 commit はコードを変えていない)。素材 `fl-win64` / `toolchain-emsdk` (emcc 6.0.12) / `toolchain-retdec` を `$HOME/artifacts` から展開して使用。
- 測定コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/plugins/synth/cpp_lift.sh <block> 2400` (9 本を `xargs -P 3`。既定の `HLL_CAP=300` のまま)。
- 測定の総経過: 472 s (9 本、終了コード 0 が 9 本)。 load (測定後): `1.35 1.85 1.09`。
- 出力: `tools/plugins/work/synth/cpp<block>/` (gitignore。`summary.csv` / `emcc.log` / `e.final.ll`)。

## A. 実測 (604e900f)

`summary.csv` 各列の値 (列名は `cpp_lift.sh` の先頭コメント参照)。`emcc_c_rc` 0 = `emcc -c` 通過。

| block | DLL | `.pdata` 関数 | defines | 欠落 define | 未実装 helper | i256 trap | f80 関数 | `emcc_c_rc` | lift 秒 | hll_killed_s | 最初のエラー |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| 21202 | BooBass_Eng | 1,579 | 1,393 | 211 | 15 | 3 | 0 | **1** | 54 | 0 | `'%arg2' defined with type 'i32' but expected 'i64'` (E3) |
| 23914 | Kepler engine | 3,194 | 3,697 | 2 | 103 | 3 | 0 | **0** | 159 | 0 | — |
| 23916 | Kepler Exo engine | 3,193 | 3,694 | 2 | 104 | 3 | 1 | **1** | 138 | 0 | `no libcall available for fp_round with type f80` |
| 23944 | Morphine | 3,050 | 3,321 | 1 | 121 | 24 | 0 | **0** | 407 | 354 | — |
| 24159 | PoiZone engine | 1,638 | 1,790 | 1 | 101 | 3 | 0 | **0** | 54 | 0 | — |
| 24163 | Sakura engine | 1,644 | 1,707 | 1 | 84 | 3 | 1 | **1** | 57 | 0 | `do not know how to soften fp_extend` |
| 24167 | Sawer engine | 1,676 | 1,833 | 1 | 83 | 3 | 1 | **1** | 57 | 0 | `do not know how to soften fp_extend` |
| 24216 | Toxic Biohazard | 1,841 | 1,927 | 1 | 94 | 3 | 1 | **1** | 93 | 0 | `do not know how to soften fp_extend` |
| 24298 | Transistor Bass engine | 3,257 | 3,741 | 2 | 87 | 3 | 0 | **0** | 108 | 0 | — |

- `emcc -c` 通過: **4/9** (23914 / 23944 / 24159 / 24298)。不通過 5 本: BooBass_Eng (E3 1 件)、f80 libcall 4 本 (23916 / 24163 / 24167 / 24216)。
- E1 (`fix_icmp_ptr.py`): `fixcmp_patched` は 9 本とも 0 (`engine_fixcmp.py` の適用なし)。共有鎖で解消済みのため、修復前後の rc は不変。
- Morphine (23944): `hll_killed_s` 354 — RetDec の HLL 段を kill して `.ll` から再開した経路。通常経路 (HLL 段を含む) の最後までの実測は無い。
- `known.json`: 通過 4 本の `emcc_c_rc` を除去。残りの fails (`declares_unimpl` / `i256_trap` / `missing_define` と不通過 5 本の `emcc_c_rc`) は未解決。
- judge (C++ 9 本の行のみ、`mk_status.py` 相当の列で作成): KNOWN 9 / NEW-FAIL 0 / FIXED 0 / MISSING 0 / exit 0。`synth_e2e.sh` 全体 (shell 12 本) は未実行。

## B. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| f80 (x86_fp80) の libcall (`fp_extend` / `fp_round`) | 不通過 4 本 (23916 / 24163 / 24167 / 24216) | #534 (本 issue)。f80→f64 は精度が変わるため既定外。扱いは判断が要る |
| E3 (i32 仮引数の i64 使用) BooBass_Eng `function_180049450` | 不通過 1 本 | #1301 (PLG-G2-13) |
| define 欠落 (BooBass_Eng 211 件) | 1 本 (他 8 本は 1〜2 件) | #1301 (PLG-G2-13) |
| Morphine (23944) の HLL 段を含む通常経路の実測 | 未実測 (再開経路のみ) | #1301 (PLG-G2-13) |
| VEX helper 未実装 (未実装 helper 件数 83〜121) と `PLUG_AVX256` 有効時の再測定 | lift 結果の完全性 | #534 (本 issue) |
| E2 (SSA 値入り定数式) / E4 (`fix_asm_stores` の def 欠落) | 今回の最初のエラーには出ず未再現。 網羅の確認は未実施 | #534 (本 issue) |
