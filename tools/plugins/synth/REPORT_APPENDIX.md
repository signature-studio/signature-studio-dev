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
- Morphine (23944): `hll_killed_s` 354 — RetDec の HLL 段を kill して `.ll` から再開した経路 (§A の実測)。通常経路 (HLL 段を含む) の実測は §C。
- `known.json`: 通過 4 本の `emcc_c_rc` を除去。残りの fails (`declares_unimpl` / `i256_trap` / `missing_define` と不通過 5 本の `emcc_c_rc`) は未解決。
- judge (C++ 9 本の行のみ、`mk_status.py` 相当の列で作成): KNOWN 9 / NEW-FAIL 0 / FIXED 0 / MISSING 0 / exit 0。`synth_e2e.sh` 全体 (shell 12 本) は未実行。

## B. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| f80 (x86_fp80) の libcall (`fp_extend` / `fp_round`) | 不通過 4 本 (23916 / 24163 / 24167 / 24216) | #534 (本 issue)。f80→f64 は精度が変わるため既定外。扱いは判断が要る |
| E3 (i32 仮引数の i64 使用) BooBass_Eng `function_180049450` | 不通過 1 本 | #1301 (PLG-G2-13) |
| define 欠落 (BooBass_Eng 211 件) | 1 本 (他 8 本は 1〜2 件) | #1301 (PLG-G2-13) |
| Morphine (23944) の HLL 段を含む通常経路の実測 | §C で解消 (kill 無しで最後まで実測。`emcc_c_rc` 0) | #1487 (解消済み) |
| VEX helper 未実装 (未実装 helper 件数 83〜121) と `PLUG_AVX256` 有効時の再測定 | lift 結果の完全性 | #534 (本 issue) |
| E2 (SSA 値入り定数式) / E4 (`fix_asm_stores` の def 欠落) | 今回の最初のエラーには出ず未再現。 網羅の確認は未実施 | #534 (本 issue) |

## C. Morphine (23944) 通常経路の実測 (f3ffd7ba、#1487)

- 測定 commit: **f3ffd7ba** (= origin/main 取り込み後の HEAD)。`git diff f3ffd7ba HEAD -- tools/plugins ':!tools/plugins/synth/REPORT_APPENDIX.md'` は 0 行 (REPORT_APPENDIX.md を除くコード範囲の差分 0)。
- 測定コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP HLL_CAP=100000000 bash tools/plugins/synth/cpp_lift.sh 23944 2400`。
  `HLL_CAP` を 1e8 秒にして HLL 段の kill 判定が発火しないようにした (= kill 無しの通常経路)。`timeout 2280` で包んで実行。
- 所要時間: 壁時計 14 分 27 秒 (23:03:30 開始 → 23:17:57 終了、`date` 実測)。lift 秒 **854** (summary.csv)。
- RetDec の段別内訳 (IR 出力 / HLL 段 / finalization の秒数) は **未確認**。測定時の `e.retdec.log` は残っておらず (作業ツリー・`$RUNNER_TEMP`・`$ARTIFACTS_DIR` のいずれにも無い)、段別の秒数は記載しない。
- load: 実行終了時 `1.07 1.02 0.74`、測定後 `0.71 0.93 0.72`。
- 結果 (summary.csv): `23944,3050,0,3321,0,52,24,0,0,0,854,1,61,0,271,3320,0`

| 項目 | 通常経路 (f3ffd7ba) | §A 再開経路 (604e900f) |
|---|--:|--:|
| lift_rc | 0 | 0 |
| defines | 3,321 | 3,321 |
| 未実装 helper | 52 | 121 |
| i256 trap | 24 | 24 |
| f80 関数 | 0 | 0 |
| `emcc_c_rc` | **0** | 0 |
| lift 秒 | 854 | 407 |
| `hll_killed_s` | **0** | 354 |

- `emcc -c` は通過 (`emcc.log` 0 バイト、`first_errors.txt` 空)。未実装 helper は §A と不一致 (52 vs 121)。差の原因は `m11_simd2.py` の変更 (711d9ece・f2bbad10、#1163。VEX 3 オペランド形の SSE 委譲、cvt/rep 系の対応追加) で、§A (604e900f) の時点より未実装が減ったことによる。コードの差分からの説明であり、旧 commit での再測定はしていない。それ以外の列 (defines / i256 trap / f80 / emcc_c_rc / lift 秒を除く) は §A の再開経路と一致した。`.ll` 本体の差分比較はしていない。
- 出力: `tools/plugins/work/synth/cpp23944/` (gitignore)。
