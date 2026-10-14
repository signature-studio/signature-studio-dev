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
- Morphine (23944): `hll_killed_s` 354 — RetDec の HLL 段を kill して `.ll` から再開した経路 (§A の実測)。通常経路 (HLL 段を含む) の実測は §D。
- `known.json`: 通過 4 本の `emcc_c_rc` を除去。残りの fails (`declares_unimpl` / `i256_trap` / `missing_define` と不通過 5 本の `emcc_c_rc`) は未解決。
- judge (C++ 9 本の行のみ、`mk_status.py` 相当の列で作成): KNOWN 9 / NEW-FAIL 0 / FIXED 0 / MISSING 0 / exit 0。`synth_e2e.sh` 全体 (shell 12 本) は未実行。

## D. E3 修復 (#1485; `function_180049450` の i32 仮引数)

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

実測 (`bash tools/plugins/synth/cpp_lift.sh 21202 1500`、fl-win64 の 21202 PE・RetDec v5.0・emcc 6.0.12 を使用。測定 HEAD = 05a73875。fc53b943 から 05a73875 までの lift 経路の差分は `lift_ranges.sh` の opt-in 変数 `PLUG_NO_STATIC_DETECT` のみで、未設定時は動作不変):

| 条件 | lift rc | summary.csv | `emcc_c_rc` | 最初のエラー |
|---|--:|---|--:|---|
| 修復前 (main f3ffd7ba) | 0 | `21202,1579,0,1393,0,3,3,1,0,1,36,211,25828,67,23,1391,0` | 1 | `e.final.ll:114486:21 '%arg2' defined with type 'i32' but expected 'i64'` |
| 既定 (opt-in 無効、05a73875) | 0 | `21202,1579,0,1393,0,3,3,1,0,1,42,211,25828,67,23,1391,0` | 1 | 同上 (baseline と同一) |
| `PLUG_I32PTR_FUNCS=function_180049450` (05a73875) | 1 | `21202,1579,1,-1,-1,-1,-1,-1,0,-1,42,-1,-1,-1,-1,-1,0` (pass 停止のため emcc 列は未生成) | — | `[P-T2] FAIL: 呼出の実引数 %arg1 が trunc 定義でも定数でもない (line 134718)` |

- 測定の鮮度 (fc53b943 → 05a73875): `git diff fc53b943 05a73875 -- tools/plugins/lift tools/plugins/synth` の変更は `lift_ranges.sh` の 2 行 (コメント 1 行と RetDec 呼出行) と REPORT のみ。
  RetDec 呼出行は `--select-decode-only ${PLUG_NO_STATIC_DETECT:+--disable-static-code-detection} --timeout ...` になった。変数が未設定なら `${…:+…}` は空に展開され、RetDec に渡る argv は変わらない (実測: 未設定時は `--select-decode-only --timeout 5` の 3 語で、旧行と同一)。
  `git diff fc53b943 05a73875 -- tools/plugins/lift tools/plugins/synth` の lift 側の出力 (抜粋・全文):
  ```diff
  -  --select-ranges "$DEC_RANGES" --select-decode-only --timeout "$TMO" > "$OUT/$NAME.retdec.log" 2>&1
  +  --select-ranges "$DEC_RANGES" --select-decode-only ${PLUG_NO_STATIC_DETECT:+--disable-static-code-detection} --timeout "$TMO" > "$OUT/$NAME.retdec.log" 2>&1
  ```
  よって既定経路・opt-in 経路の測定は流用できる (fc53b943 と 05a73875 の summary の差は既定経路の `lift_s` 列のみ 45 → 42。`emcc_c_rc`・欠落数・最初のエラーは同一)。ただし `PLUG_NO_STATIC_DETECT=0` も「設定済み」扱いで `--disable-static-code-detection` が付く (空文字のときだけ付かない)。
- opt-in 経路は、仕様どおり `function_180056120(i32 %arg1, …)` の呼出で止まる。出力 `.i3.ll` は作られず、`.final.ll` も無い。
  外側の `i32` 署名を i64 化すると範囲が広がるため、本 pass では扱わない (下記 未解決)。
- そのため「opt-in の `.ll` が `llvm-as`/clang で構文検証を通る」という受入条件は、実データでは**達成していない**。
  代わりに検証用の入力 (実データの `e.fh.ll` で `function_180056120` の `i32 %arg1` 1 件だけを定数 0 に置換したコピー。本番の修復ではない) を作り、
  pass の出力 (const 9 / trunc 10) が `clang -x ir -fsyntax-only` を通ることを確認した。
- 既定経路の summary は修復前と同一 (`emcc_c_rc`=1、最初のエラーも同一)。`lift_s` のみ測定ごとに変動 (36 → 45 秒)。他 8 本の `emcc_c_rc` は未測定。
- 注: `e.fh.ll` は llvm-as 18 では 7651 行の `add i64 0, i64 %...` で不正 (RetDec 出力の元からの問題)。clang 18 の `-fsyntax-only` は通る。検証は clang で行う。

## E. E3 残件の修復 (#1509; `function_180056120` の i32 仮引数)

修復前: `e.final.ll:114486` の `'%arg2' defined with type 'i32' but expected 'i64'` (`function_180049450`)。
`function_180056120(i32 %arg1, …)` の `%arg1` は本体で `inttoptr` されず、`function_180049450` へ渡すだけのため、#1485 の pass 規則 (inttoptr で使われる仮引数のみ) では対象外だった。

修正: `fix_i32_ptr_arg.py` に伝播を追加した。`--func` で指定した呼出元 C の `i32` 仮引数 `%P` は、受け先 (変換済み callee) へ `i64` で渡す場合に限り `i64` 化する (C は `--func` の順序で受け先の後)。定数・trunc 規則は不変。 `cpp_lift.sh` は block 21202 のみ `PLUG_I32PTR_FUNCS="function_180049450 function_180056120"` を既定にする (他の block は従来どおり)。

- 回帰テスト: `TMPDIR=$RUNNER_TEMP bash tools/plugins/lift/passes/test_fix_i32_ptr_arg.sh` → `ALL PASS` (既存 5 ケース + 伝播成功 (clang -fsyntax-only 通過) + 順序逆で失敗・出力無し)。
- 実測 (`bash tools/plugins/synth/cpp_lift.sh 21202 1500`、既定 = 受入コマンドそのまま、測定 commit `dae815ef`、素材 fl-win64・toolchain-retdec・toolchain-emsdk・work-liftlib・work-fw-stage1 を展開):

| 条件 | lift rc | summary.csv | `emcc_c_rc` | 最初のエラー |
|---|--:|---|--:|---|
| 修復前 (1e3ee7af) | 0 | `21202,1579,0,1393,0,2,3,0,0,0,57,211,25828,67,23,1391,0` | 1 | `e.final.ll:114486 '%arg2' … i64` |
| 修復後 (dae815ef、既定) | 0 | `21202,1579,0,1393,0,2,3,0,0,0,57,211,25828,67,23,1391,0` | **0** | — |

- 修復前の既定実行 (1e3ee7af) の所要 58.6 秒、修復後 (dae815ef) 59.3 秒。load は 0.84 → 0.74 (測定前後)。`emcc_c_rc_after_fixcmp` は 0。`P-T2` 分類: const 11 / trunc 11 / param 1。
- 測定 commit 以降のコード差分: `git diff dae815ef HEAD -- tools/plugins/lift tools/plugins/synth` (本 REPORT の commit は文書のみ)。

### 他 block の emcc_c_rc (受入条件 3) の測定

既定経路 (修復無し) の値。`cpp_lift.sh` の既定変更は 21202 のみ、他 block は `PLUG_I32PTR_FUNCS` 未設定の経路を通るため、既定値は不変 (pass は `cp` のみ)。

| block | summary.csv (dae815ef、既定) | emcc_c_rc |
|---|---|--:|
| 23914 | `23914,3194,0,3697,0,34,3,0,0,0,165,2,111,0,503,3695,0` | 0 |
| 23916 | `23916,3193,0,3694,1,35,3,1,0,1,169,2,111,0,501,3692,0` | 1 |
| 23944 | `23944,3050,0,3321,0,41,24,0,0,0,448,1,61,0,271,3320,354` | 0 |

- 23916 の `emcc_c_rc=1` は本 run では修復前の比較値を採取していないため、#534 の既存結果との一致は**未確認** (本 run の修復は 21202 以外に効かない設計のため、変化は無いはず、と推定)。残り 5 本 (24159・24163・24167・24216・24298) は未測定。
- 測定時間の制約 (3 本で 13 分 26 秒) により、残り 5 本は本 run で測定しない。修復は `PLUG_I32PTR_FUNCS` 未設定時 `cp` のみで既定経路に影響しないことをコードで確認した。

## B. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| f80 (x86_fp80) の libcall (`fp_extend` / `fp_round`) | 不通過 4 本 (23916 / 24163 / 24167 / 24216) | #534 (本 issue)。f80→f64 は精度が変わるため既定外。扱いは判断が要る |
| E3 (i32 仮引数の i64 使用) BooBass_Eng `function_180049450` | 不通過 1 本 | #1301 (PLG-G2-13) |
| define 欠落 (BooBass_Eng 211 件) | 1 本 (他 8 本は 1〜2 件) | #1301 (PLG-G2-13) |
| Morphine (23944) の HLL 段を含む通常経路の実測 | §D で解消 (kill 無しで最後まで実測。`emcc_c_rc` 0) | #1487 (解消済み) |
| VEX helper 未実装 (未実装 helper 件数 83〜121) と `PLUG_AVX256` 有効時の再測定 | lift 結果の完全性 | #534 (本 issue) |
| E2 (SSA 値入り定数式) / E4 (`fix_asm_stores` の def 欠落) | 今回の最初のエラーには出ず未再現。 網羅の確認は未実施 | #534 (本 issue) |

## C. #1486: BooBass_Eng (21202) の define 欠落 211 件の原因分類

- 測定 commit: **0b233323** (コードを変えた最後の commit。`git diff 0b233323 HEAD -- tools/plugins/lift tools/plugins/synth` は 0 行)。 測定 HEAD も 0b233323。
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` / `work-liftlib` / `work-fw-stage1` / `plugins-ott` を `$HOME/artifacts` から展開して使用。
- 測定: `bash tools/plugins/synth/cpp_lift.sh 21202 1500` (既定) = 40 s、 load (測定前後) `0.20 0.35 0.25` → `0.59 0.43 0.29`。
  `summary.csv` = `21202,1579,0,1393,0,3,3,1,0,1,39,211,25828,67,23,1391,0` (欠落 211 / 25,828 B / 参照 67 は #1301 の実測と一致)。
- 分類コマンド: `python3 tools/plugins/synth/missing_define_classify.py tools/plugins/work/synth/cpp21202` (新規)。

### C-1. 原因の分類 (件数)

| 原因 | 件数 | 参照あり (`missing_ref`) | 長さ合計 (B) | 切り分けの根拠 |
|---|--:|--:|--:|---|
| (a) RetDec の静的コード検出で `statically linked function` 扱い | **209** | 67 | 25,411 | `e.drc.dsm` が `; statically linked function: ... at <VA>` と label。 `define` が出ない |
| (b) RetDec が関数名で `define` を出す (`function_<VA>` でない) | **2** | 0 | 417 | `CreatePlugInstance` (0x1800029a0) と `entry_point` (0x180005a50)。 `e.drc.ll` に `@CreatePlugInstance` / `@entry_point` として定義あり |
| (c) 未分類 | 0 | 0 | 0 | — |

- 209 件の内訳 (長さ): 64 B 以下 137 件 / 65〜256 B 60 件 / 257 B 以上 12 件。
- 「pass 鎖で消える」は **0 件**。 `e.drc.ll` の define 数 (1391) は、正規化 → `ir5_patch` → … → `e.final.ll` の全段で変わらない (`for f in e.*.ll` の計数で確認)。 欠落は RetDec 段で生じる。
- 別名化 (`function_<VA>` が無く、範囲の内側に別の define がある) は 0 件。 23 件の余分な define (range 開始 VA でない) は既存で、欠落とは別。

### C-2. 代表例と再現コマンド

- (a) 代表 `0x180002bf0-0x180002c1a` (len 43, 参照なし):
  `RetDec` を単独 range で実行すると `; statically linked function: ??_G?$codecvt@DDU_Mbstatet@@@std@@MEAAPEAXI@Z at 0x180002bf0` と出て `define` が無い。
  再現: `$RETDEC_ROOT/bin/retdec-decompiler`（`[RETDEC]`）$RUNNER_TEMP/fl-win64/extracted/block21202_PE.bin -o x.c --select-ranges 0x180002bf0-0x180002c1a --select-decode-only` → `grep -c ^define x.ll` = 0。
  同じ range に `--disable-static-code-detection` を付けると `define i64 @function_180002bf0(i64, i64)` が出る。
  参照ありの代表 `0x180005a98-0x180005acb` (len 52) も同じ経路 (`__raise_securityfailure`)。
- (b) 代表 `0x1800029a0-0x180002b03` (`CreatePlugInstance`, len 356):
  `grep -n '^define .*@CreatePlugInstance' work/synth/cpp21202/e.drc.ll` でヒット。 `function_1800029a0` は無い。 `missing_define` 判定 (開始 VA の `function_<VA>` 有無) では欠落扱いになるが、関数としては出力されている。

### C-3. 修復 (opt-in)

- `tools/plugins/lift/lift_ranges.sh` に `PLUG_NO_STATIC_DETECT=1` を追加 (既定 0 = 挙動不変)。 RetDec に `--disable-static-code-detection` を渡す。 pass 鎖 (`lift/passes/`) は触らない (原因は RetDec 段のため)。
- 実測 (0b233323、 `PLUG_NO_STATIC_DETECT=1 bash tools/plugins/synth/cpp_lift.sh 21202 1500`): 40 s、 `summary.csv` = `21202,1579,0,1602,0,21,3,1,0,1,39,2,417,0,23,1600,0`。
  欠落 **211 → 2** (B 25,828 → 417)、参照欠落 **67 → 0**。 未実装 helper 3 → 21 (`__asm_vroundsd` / `__asm_vucomisd` 等。 新規に見えた関数の VEX 命令。 今回は未対処)。
- `emcc -c` は既定と同じく **rc 1** (最初のエラーは既存の E3 `'%arg2' defined with type 'i32' but expected 'i64'`)。 emcc は最初のエラーで止まるため、回復した 209 関数に後段の型エラーがあるかは未確認。
- 既定にしない理由: 既定化は `lift_ranges.sh` を使う全 lift の出力を変える。 8 本の他 C++ DLL は `static_labels=0` で出力不変 (下記) だが、 他の batch への影響を未確認のため opt-in に留める。
- 他 8 本 (`PLUG_NO_STATIC_DETECT=1` と既定の両方で測定、 HEAD 0b233323): `summary.csv` は 8 本とも両者で同一。 `emcc_c_rc` は 604e900f の表 (§A) と同一 (23914=0 / 23916=1 / 23944=0 / 24159=0 / 24163=1 / 24167=1 / 24216=1 / 24298=0)。 `static_labels` は 8 本とも 0。

### C-4. 未解決 (起票先)

| 未解決 | 件数 | 起票先 |
|---|--:|---|
| 静的検出の既定化 (`PLUG_NO_STATIC_DETECT` を既定 1 にする) と他 batch への影響確認 | 209 件 (BooBass_Eng) | 子 issue (本 run で起票) |
| 関数名で出る 2 件 (`CreatePlugInstance` / `entry_point`) の `function_<VA>` への正規化 | 2 件 | 子 issue (本 run で起票) |
| 回復 209 関数の後段 (emcc 型エラー) の確認。 E3 が先に止めるため未確認 | 209 件 | #1301 (PLG-G2-13) |

## D. Morphine (23944) 通常経路の実測 (f3ffd7ba、#1487)

- 測定 commit: **f3ffd7ba**。 その後の `tools/plugins` 差分 (`git diff f3ffd7ba HEAD -- tools/plugins ':!tools/plugins/synth/REPORT_APPENDIX.md'`) は **5 files, +78 / -2** (main 取り込み #1486 由来と #1222 由来):
  - `lift/lift_ranges.sh` (+1 行 env 分岐): `PLUG_NO_STATIC_DETECT` 未設定時は RetDec 引数が従来と同一 (`${PLUG_NO_STATIC_DETECT:+...}` が空展開)。測定は既定の環境変数で実行したため経路は不変。
  - `framework/hostshim/hs_disp_emu.py` (+6 / -1): `HS_DISP_RET_ARG=1` のときだけ挙動が変わる。測定では未設定。
  - `synth/missing_define_classify.py` (新規 30 行) / `reverb_delay/REPORT_APPENDIX.md` (+10) / `framework/hostshim/REPORT_DISPATCHER.md` (+29): 測定経路から呼ばれない (lift 本体ではない)。
  - 上記により f3ffd7ba 以降のコード経路は変わっていない。測定値はそのまま f3ffd7ba の値として成立する。
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

## E. #1537: 名前 define 2 件の `function_<VA>` 正規化 (opt-in `PLUG_NAME_DEFS=1`)

- 測定 commit: **4609ee03** (コードを変えた最後の commit)。 `git diff 4609ee03 HEAD -- tools/plugins/lift tools/plugins/synth` の出力は 0 行 (HEAD = 4609ee03)。
- 修復: `tools/plugins/lift/passes/name_defs_to_va.py` (新規)。 PE の export 名 (`CreatePlugInstance`) と entry point (`entry_point`) で RetDec が出した define を、`function_<VA>` に改名する。 `sampler/export_rename.py` (#707) は export 名だけを扱うため、entry point を加えた別 pass にした。
  `lift_ranges.sh` に `PLUG_NAME_DEFS=1` の時だけ掛ける。 既定 (未設定) は従来と同一。
- 改名の対象 (21202): `CreatePlugInstance` (0x1800029a0) → `function_1800029a0`、 `entry_point` (0x180005a50) → `function_180005a50`。

### E-1. 実測 (4609ee03、`bash tools/plugins/synth/cpp_lift.sh 21202 1500`)

| 条件 | summary.csv | `emcc_c_rc` | 最初のエラー |
|---|---|--:|---|
| 既定 (`PLUG_NAME_DEFS` 未設定) | `21202,1579,0,1393,0,2,3,1,0,1,57,211,25828,67,23,1391,0` | 1 | `'%arg2' defined with type 'i32' but expected 'i64'` |
| `PLUG_NAME_DEFS=1` | `21202,1579,0,1393,0,2,3,1,0,1,57,209,25411,67,23,1393,0` | 1 | 同上 |

- `PLUG_NAME_DEFS=1` の lift.log: `[name_defs_to_va] renamed 2: CreatePlugInstance->function_1800029a0, entry_point->function_180005a50`。
- 欠落 define は **211 → 209** (B 25,828 → 25,411)。 defines 1391 → 1393 (+2)。 参照欠落 `missing_ref` 67 は不変 (改名は `@<名前>` の参照も書き換えるが、欠落参照の集計は変わらなかった)。
- 上記の 209 件は静的検出 ON の時の数。#1699 (`PLUG_NO_STATIC_DETECT` 既定 1) の後の現 HEAD では **E-2** の通り `missing_define` = 0。
- `emcc -c` は既定・opt-in とも rc 1 (E3 が先に止める)。 両者の `first_errors.txt` は同一。

### E-2. 受入条件の実測 (現 HEAD、env 指定なし。21202 は cpp_lift.sh が `PLUG_NAME_DEFS=1` を既定化)

- 測定 commit: **002c750f** (`cpp_lift.sh` に 21202 のみ `PLUG_NAME_DEFS` 既定 1 を入れた commit)。 `git diff 002c750f HEAD -- tools/plugins/lift tools/plugins/synth` は測定後のコード差分 (本節のみ更新するため 0 行)。
- コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/plugins/synth/cpp_lift.sh 21202 1500` (42.9 s、rc 0、load 1.23 → 0.80)。
- summary.csv: `21202,1579,0,1602,0,12,3,1,0,1,42,0,0,0,23,1602,0` (`missing_define` 0 / `missing_bytes` 0 / defines 1602)。 cpp_lift.sh 変更前 (`PLUG_NAME_DEFS` 未設定) の同条件は `...,42,2,417,0,23,1600,0` (欠落 2 件、同日の実測)。
- `[name_defs_to_va] renamed 2: CreatePlugInstance->function_1800029a0, entry_point->function_180005a50`。
- `emcc_c_rc` は 1 のまま (E3 `%arg2` i32/i64 が先に止める。受入条件の対象外)。


## F. #1536 (PLUG_NO_STATIC_DETECT の既定化) の節

§F は 250 行上限のため [REPORT_APPENDIX_F.md](REPORT_APPENDIX_F.md) に分割移動した。

## G. 現 head (f1d1db11 = main 取り込み後) での 9 本再測定と known.json 判定 (#534)

- **測定 commit: f1d1db11** (`origin/main` を merge した commit。tools/plugins のコードを変えた最後の commit)。`git diff f1d1db11 HEAD -- tools/plugins ':!*.md'` は **0 行** (測定後のコード差分 0。md の差分のみ)。
- 旧表 (測定 HEAD ba4babca, 2 関数版) は現 head に対応しないため撤回した。
- コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/plugins/synth/cpp_lift.sh <block> 2400` を 9 本 `xargs -P 3`。既定 env (21202 は `PLUG_I32PTR_FUNCS` 既定の 3 関数 `function_180049450 function_180056120 function_1800599bc`)。素材 fl-win64 / toolchain-emsdk / toolchain-retdec。
- 総経過 **8 分 22 秒** (real 502.7 s)、9 本とも終了コード 0。 load 1.83 (開始時) → 1.42 (終了時)。 23944 は HLL 生成が HLL_CAP (300 s) を超えたため RetDec を止めて `.ll` から後段を再開 (`hll_killed_s` 361)。

| block | 名前 | lift_rc | defines | f80 | unimpl | i256 | emcc_c_rc | missing_define | lift_s |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|
| 21202 | BooBass | 0 | 1,602 | 0 | 12 | 3 | **1** | 2 | 60 |
| 23914 | Kepler | 0 | 3,697 | 0 | 34 | 3 | **0** | 2 | 144 |
| 23916 | Kepler Exo | 0 | 3,694 | 1 | 35 | 3 | 1 | 2 | 189 |
| 23944 | Morphine | 0 | 3,321 | 0 | 41 | 24 | **0** | 1 | 429 |
| 24159 | PoiZone | 0 | 1,790 | 0 | 36 | 3 | **0** | 1 | 57 |
| 24163 | Sakura | 0 | 1,707 | 1 | 21 | 3 | 1 | 1 | 73 |
| 24167 | Sawer | 0 | 1,833 | 1 | 22 | 3 | 1 | 1 | 60 |
| 24216 | Toxic Biohazard | 0 | 1,927 | 1 | 30 | 3 | 1 | 1 | 103 |
| 24298 | Transistor Bass | 0 | 3,741 | 0 | 21 | 3 | **0** | 2 | 129 |

- **判定**: 9 行の判定 CSV を `judge.py --want <9 本>` (known.json 既定) に通した結果は KNOWN 9 / NEW-FAIL 0 / FIXED 0 / MISSING 0 (exit 0)。known.json は main と同一のまま変更なし。 `--strict` は NEW-FAIL 9 (known を無視した全件不合格。想定どおり)。
- 注: `mk_status.py` は shell 12 本の行 (work/batch) も必須で exit 1 になるため、C++ 9 行だけを `mk_status.py` の cpp 行と同じ列対応で組んだ (組み立てスクリプトは未 commit)。 `mk_status.py` 全体の判定は未実行。
- **21202 の 2 関数版の確認**: `PLUG_I32PTR_FUNCS="function_180049450 function_180056120"` では `lift_rc` 1 (`[P-T2] FAIL: function_180049450 の仮引数 %arg1 を伝播できない (呼出元 function_1800599bc は --func に未指定)`)。 3 関数指定が必要。
- **21202 の emcc 失敗**: `e.final.ll:123490:45: error: '%penv' defined with type 'i64' but expected 'ptr'` (FreeEnvironmentStringsW)。 旧表の 21202 emcc 0 は現 head で再現しない。
- 受入条件 (未達): `emcc -c` 通過 **4/9** (23914・23944・24159・24298)。 不通過 5 本: 21202 (`%penv` i64/ptr)・23916 (`no libcall available for fp_round with type f80`)・24163・24167・24216 (`do not know how to soften fp_extend`)。 `missing_define` 0 は **0/9** (1〜2 件)。
- 未解決: f80 libcall → #197 / #523。 `missing_define` → #1301 / #1536。 21202 の `%penv` i64/ptr 型不一致 → 起票先未定 (既存 issue の確認は未実施。PM 確認を要する)。 VEX helper → #527 / #779 / #1163。
