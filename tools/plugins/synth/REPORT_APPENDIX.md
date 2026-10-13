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

## C. E3 修復 (#1485; `function_180049450` の i32 仮引数)

修復 pass: `tools/plugins/lift/passes/fix_i32_ptr_arg.py` [P-T2] (opt-in: `PLUG_I32PTR_FUNCS=function_180049450`)。

修復 pass: `tools/plugins/lift/passes/fix_i32_ptr_arg.py` [P-T2] (opt-in: `PLUG_I32PTR_FUNCS=function_180049450`)。
pass は次の場合に**出力を書かず非 0 終了**する (`lift_ranges.sh` が `set -e` で止まる): 実引数が定数・`trunc` 定義以外 / 本体で `inttoptr`・`icmp` 以外に使われる / 呼出が解釈できない形。
`i32` → `i64` の書換えは、`trunc` 定義を変えず `add i64 %W, 0` を挿入して行う (定義元を変えると他の `i32` 使用が壊れるため)。

呼出側の分類 (`function_180049450` の呼出 19 件。`classify_i32_callers.py` で再生成可):

| 種別 | 件数 | 扱い |
|---|--:|---|
| `i32 0`〜定数 | 8 | `i64 0` (値は同じ) |
| `i32 %V`、定義元 `%V = trunc i64 %W to i32` (同一 define 内、距離制限なし) | 10 | `%i3x.N = add i64 %W, 0` を挿入し、それを渡す (上位 32bit を保つ) |
| `i32 %arg1` (呼出元 `function_180056120` の `i32` 仮引数) | 1 | 対象外 → pass が失敗 |

- 件数の揃え: 「呼出 4 箇所」は `function_180056120` 自体の呼出数 (4 件)。上の 19 件は `function_180049450` の呼出数で、混同していた。
- 決定の根拠: ネイティブ `0x180049450` は第 2 引数 (rdx) の 64bit 全体を `test rdx, rdx` / `movups [rdx]` でポインタとして使う。
  `trunc` による上位 32bit の切り捨ては、非 0 の上位を持つポインタで別アドレスを読むため silent に値が変わる。よって `i64` 化して上位を保つ。
  定数 (0 〜 2^31-1) は `i32`/`i64` で値が同じ。0 拡張・符号拡張は使わない。

回帰テスト: `bash tools/plugins/lift/passes/test_fix_i32_ptr_arg.sh` (5 ケース: 定数 / trunc 定義 (定義と呼出が 30 行以上離れる) → 変換して clang 構文検証 / 仮引数の受け渡し → 失敗 / 本体が i32 を別用途に使う → 失敗 / icmp の被演算子が変数 → 失敗)。

実測 (`bash tools/plugins/synth/cpp_lift.sh 21202 1500`、fl-win64 の 21202 PE・RetDec v5.0・emcc 6.0.12 を使用):

| 条件 | lift rc | summary.csv | `emcc_c_rc` | 最初のエラー |
|---|--:|---|--:|---|
| 修復前 (main f3ffd7ba) | 0 | `21202,1579,0,1393,0,3,3,1,0,1,36,211,25828,67,23,1391,0` | 1 | `e.final.ll:114486:21 '%arg2' defined with type 'i32' but expected 'i64'` |
| 既定 (opt-in 無効、f6274470 の pass) | 0 | `21202,1579,0,1393,0,3,3,1,0,1,45,211,25828,67,23,1391,0` | 1 | 同上 (baseline と同一) |
| `PLUG_I32PTR_FUNCS=function_180049450` | 1 | (lift が pass で停止、summary の emcc 列は未生成) | — | `[P-T2] FAIL: 呼出の実引数 %arg1 が trunc 定義でも定数でもない (line 134656)` |

- opt-in 経路は、仕様どおり `function_180056120(i32 %arg1, …)` の呼出で止まる。出力 `.i3.ll` は作られず、`.final.ll` も無い。
  外側の `i32` 署名を i64 化すると範囲が広がるため、本 pass では扱わない (下記 未解決)。
- そのため「opt-in の `.ll` が `llvm-as`/clang で構文検証を通る」という受入条件は、実データでは**達成していない**。
  代わりに検証用の入力 (実データの `e.fh.ll` で `function_180056120` の `i32 %arg1` 1 件だけを定数 0 に置換したコピー。本番の修復ではない) を作り、
  pass の出力 (const 9 / trunc 10) が `clang -x ir -fsyntax-only` を通ることを確認した。
- 既定経路の summary は修復前と同一 (`emcc_c_rc`=1、最初のエラーも同一)。`lift_s` のみ測定ごとに変動 (36 → 45 秒)。他 8 本の `emcc_c_rc` は未測定。
- 注: `e.fh.ll` は llvm-as 18 では 7651 行の `add i64 0, i64 %...` で不正 (RetDec 出力の元からの問題)。clang 18 の `-fsyntax-only` は通る。検証は clang で行う。

## B. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| f80 (x86_fp80) の libcall (`fp_extend` / `fp_round`) | 不通過 4 本 (23916 / 24163 / 24167 / 24216) | #534 (本 issue)。f80→f64 は精度が変わるため既定外。扱いは判断が要る |
| E3 (i32 仮引数の i64 使用) BooBass_Eng `function_180049450` | 不通過 1 本 | #1301 (PLG-G2-13) |
| define 欠落 (BooBass_Eng 211 件) | 1 本 (他 8 本は 1〜2 件) | #1301 (PLG-G2-13) |
| Morphine (23944) の HLL 段を含む通常経路の実測 | 未実測 (再開経路のみ) | #1301 (PLG-G2-13) |
| VEX helper 未実装 (未実装 helper 件数 83〜121) と `PLUG_AVX256` 有効時の再測定 | lift 結果の完全性 | #534 (本 issue) |
| E2 (SSA 値入り定数式) / E4 (`fix_asm_stores` の def 欠落) | 今回の最初のエラーには出ず未再現。 網羅の確認は未実施 | #534 (本 issue) |
