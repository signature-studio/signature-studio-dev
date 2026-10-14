# #2672: unit 477 の `0x10a9f910` 下位 4B 書込みの主体 (C 版 `function_4133f0` の局所スロット)

親: #1620 (経緯は `REPORT_1046.md` §10〜§19)。測定 commit: `c05f4b16` (コードを変えた最後の commit。比較スクリプト `compare_kinds_2672.py` を含む)。
build 入力 (m11 の IR・C・build スクリプト) は origin/main `208b4ef9` から変更していない (§8)。
既知類型との関係: DEFECTS.md の D1a〜D23 のどれにも当たらない。D17 とは機構が違う (§5)。

## 0. 結論

- unit 477 で `0x10a9f910` の下位 4B を `0x1029e5d8` → `2` にした store の**主体は C 関数 `function_4133f0`** (`tools/m11/m11_ov.c:340`、`System._UStrAsg` の C 版)。IR の store ではない。#1620 の前提 (C 側の書込み) と一致する。
- 書込み先は `function_4133f0` の shadow stack フレーム (基底 `0x10a9f8e0`、+48 の 4B 局所 `u32 len`)。`0x10a9f910` はスタック番地。書込み値 `2` は src 文字列の長さ (`len = D(s - 4)`) で、refcount ではない。書込み自体は正常。
- 問題は後段。unit 492 の `UStrAsg(dest=0x10a9f910)` が、このスタック残骸 (`0x100000003`) を旧値 `old` として読む (REPORT_1046 §10)。類型案は §5 (仮説・未検証)。
- 行は `m11_ov.c:345` (`u32 len = D(s - 4);`) と判定した (wat の store 式による。§3)。DWARF 無し (`-g1`) のため、DWARF 付きでの最終確認は子 issue #2706。

## 1. 手法: IR にも C にも手を入れない wasm 計装

- 既存の計装は C 呼出し (`m11_sw`) や IR の変更で、shadow stack の残骸を変えて結果が変わった (REPORT_1046 §18・§19)。本節は C・IR のどちらも変えない。
- `wasm-opt --instrument-memory` (binaryen 133、`[EMSDK]` の `upstream/bin`) で `m11_boot.cjs.wasm` の全 store に `env.store_ptr(id, bytes, offset, ptr)` と `env.store_val_*` の hook を入れた `instr.wasm` を作る (`work/trap_2672/`、commit しない)。
- hook は JS import。`ptr` をそのまま返し、線形メモリには書かない (wasm の local と call は線形メモリの shadow stack を使わない)。
- 記録条件 (issue の条件そのまま): 実効アドレス `ptr + offset` が `W = 0x10a9f910` (8B) と重なり、かつ現在の下位 4B が `OLD` に等しい store。hit では `new Error().stack` の wasm frame を取る。`store_val` で書込み値を取る。
- 計装版は glue の `instantiateWasm` で読む。survey の手順 (`m11_image.bin` の投入・`m11_boot_enter`・unit ループ) は `survey_units.mjs` と同一。
- store id (59,261 件・重複 0) → (wasm 関数, wat 行, bytes, offset) の表は `store_sites_2672.py` で作る。
- 関数番号の注意: wasm-dis の `$N` は defined index。V8 の `wasm-function[N]` は import 37 本を足した絶対 index (`N_V8 = N_wat + 37`)。`function_4133f0` は defined 14848 = 絶対 14885。`oob_insn.py` で `0x51d25c` の命令が `call 32` (store_ptr) で、直前の引数が id 133950 (bytes 4・offset 48) と一致することを確認した。

## 2. 実測

### 2.1 基準 (計装なし)

- `m11_gen_ir2.sh` rc 0 (490,735 行、ldfix applied) → `m11_build.sh` rc 0 → `survey_units.mjs` rc 0。build 出力は `86e83ad5` の作業ツリーで生成した (build 入力は同一、§8)。
- 結果 `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` (REPORT_1046 §2 と一致)。n=1 (本 run)。

### 2.2 陰性対照: 計装版の挙動が基準と同じ

- 計装版の全 942 unit (`OLD=0x1029e5d8`、`c05f4b16`): kind 分布 `ok 870 / miss 47 / other 1 / halt0 7 / oob 16 / noproc 1`。基準と **unit 単位で差分 0 件** (`compare_kinds_2672.py`: `compared_units=942 kind_diff=0`)。
- unit 0〜477 だけ: `ok 422 / miss 45 / other 1 / halt0 4 / oob 6`。基準の 0〜477 も同じ (issue の `ok 422 / oob 6` と一致)。
- 所要時間は記載しない (単発値で、`docs/WORKFLOW.md` §5 の n≥3 の条件を満たさない)。load は未記録。

### 2.3 陽性対照: `OLD=0` で unit 1 が発火

- `WATCH_OLD=0 WATCH_UNITS=0,1` (`c05f4b16`): unit 1 で 5 hit (`hits=5`)。
  - id 42743 (`function_409070`、8B、offset 32)
  - id 42744 (同、2 回)
  - id 136067 (wasm 14966、4B、offset 16)
  - id 139419 (`GetSystemInfo` の shim、2B)
- 検出機構が動くことを確認 (issue の条件 2)。

### 2.4 本番: `OLD=0x1029e5d8`

- hit は **1 件**: unit 477、store id 133950、アドレス `0x10a9f910`、4B、書込み値 `0x2` (`store_val` で実測)。`compare_kinds_2672.py` の出力は `hitN=1`。
- 全 942 unit の計装版でも hit は 1 件 (同一)。
- 値の遷移 (REPORT_1046 §14) と一致: unit 477 で下位 4B が `0x1029e5d8` → `2`。

## 3. 書込みの所属 (wasm 逆引き・wat の式)

- 呼出し chain (V8 の絶対 index → defined index → 名前):
  - 14885 → 14848 → `function_4133f0` (store の所在)
  - 5998 → 5961 → `function_abeef0`
  - 6000 → 5963 → `function_abfd60`
  - 13227 → 13190 → `m11_tr_function_abfd60`
  - 14861 → 14824 → `m11_icall`
  - 14877 → 14840 → `m11_call_unit`
- store の所在は wat 3198825 行の `(i32.store offset=48 ...)` (`function_4133f0` の body)。番地の hook 呼出し `(call $fimport$32 (i32.const 133950) (i32.const 4) (i32.const 48) (local.get $2))` は 3198826 行で、`store_sites_2672.py` の id 133950 → `func 14848`・`line 3198826`・`bytes 4`・`offset 48` はこの行。
- `$2 = global$0 − 80` (prologue で 80 B のフレームを取る)。`i64.store offset=72` で第 1 引数 (dest) を保存する。これは `m11_ov.c` の C 版 (-O0) の形。IR 版 `@function_4133f0` (`boot_final3.ll` L118870〜L118955) は本体が違い、IR の `weak` 定義は C 版で override されている。
- 書込み式の値は `D(Q(frame+56) − 4)`。wat 3198832〜3198861 行の値式は `i32.load (i64.sub (i64.load offset=56 <frame>) (i64.const 4))` (hook 呼出しで包まれている)。`frame+56` は `s` (8B)。
- 直後の wat 3198862 行 `i64.store offset=56` の値は 3198871 行の `call $2030` の結果。`$2030` は export `function_412c20` で、引数は `i64.load32_u offset=48` (= `len`)。つまり `s = function_412c20(len)` の store。
- よって `0x10a9f910` = `function_4133f0` のフレーム (基底 `0x10a9f8e0`) の +48 の 4B 局所 `u32 len`。
- 行: `m11_ov.c:345` の `u32 len = D(s - 4);` (L345)。直後の `s = function_412c20(len);` (L346) の store が +56 に対応し、`len * 2u` を引数に取る `function_409c80` の呼出し (L347) とも整合する。L344・L349・L352・L356 は +48 の store ではないので候補から外す。DWARF 無しのため、行の最終確認は #2706。

## 4. 受入条件の判定 (#2672)

| # | 条件 | 判定 |
|---|---|---|
| 1 | C 側の書込み関数と行 (ファイル:行) を特定し、trap の wasm 位置から site を引く | **達成** (行は wat の store 式で同定。DWARF による最終確認は #2706)。関数 (`function_4133f0`・`m11_ov.c:340`)・wasm 位置・フレーム位置 (§2.4・§3)・行 `m11_ov.c:345` (§3)。計装は trap ではなく JS hook (§1) |
| 2 | 陽性対照 (OLD = 0 で unit 1 付近が発火) | **達成** (§2.3) |
| 3 | 計装版の 0〜477 の per-unit kind と frames が基準と一致 | **部分**: kind は 942 unit 全件で一致 (§2.2)。frames は未比較 (未解決 2) |
| 4 | D17 か別類型かを判定し、DEFECTS の類型に対応づける。無ければ類型案 | **判定達成**: D17 ではない (§5)。既存類型に無いため類型案を §5 に書く |

## 5. 類型判定と類型案

- 書込み (`function_4133f0` の 4B 局所 store) は C -O0 の正しい store。縮退は無く、値 `2` は src の文字列長 (`D(s - 4)`)。DEFECTS の D17 (IR の qword → 4B 縮退) とは書込み主体の機構が違う。D1a〜D23 のどれにも当たらない。
- ただし症状 (8B の読みが上位 4B の未初期化を拾い OOB になる) は D17 の記述と同型である。unit 492 の caller に D17 の検出信号 (8B の 0 初期化の 4B 縮退) を当てたかは**未検証** (#2706 の範囲)。
- 類型案 (**仮説・未検証**): 「管理型局所 (PPointer・文字列) のエントリ時ゼロ初期化の欠落 → 未初期化のスタック番地を文字列参照として読む」。
  - 根拠 (a): unit 492 の `UStrAsg` の dest `0x10a9f910` は、unit 477 で `function_4133f0` の局所が書いた番地 (§2.4)。unit 484 も同じ番地を書く (値 `3`。主体は未確認)。
  - 根拠 (b): 埋め値 (`FILL`) で結果が変わる (REPORT_1046 §19)。読まれる値がスタック残骸に依存する。
  - 未検証: unit 492 の dest を渡す caller が、その PPointer 局所をゼロ初期化していないこと。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1. 行 `m11_ov.c:345` の DWARF による最終確認 (wat の式による同定は §3 で済み)。DWARF 付きの計装 build が要る (所要は未実測) | 受入 1 の行部分の最終確認 | #2706 (子 issue `[M11-N153]`) |
| 2. 計装版の frames の基準一致 (受入 3 の後半) | 受入 3 | #2706 |
| 3. 類型案 (§5) の検証: unit 492 の dest を渡す caller の初期化欠落。D17 の検出信号の適用を含む | DEFECTS への類型追加の判断 (PM 判断) | #2706 |
| 4. unit 484 の書込み主体 (値 `3`) | 類型案の根拠 (a) | #2706 |

## 7. 再現

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C "$RUNNER_TEMP/fl-win64"   # 展開先を先に作る (WORKFLOW §11)
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst -C .                       # tools/m11/work/ (素材)
tar --zstd -xf $ARTIFACTS_DIR/toolchain-emsdk.tar.zst -C "$RUNNER_TEMP"   # $RUNNER_TEMP/emsdk/upstream/bin に wasm-opt・wasm-dis
export PATH="$RUNNER_TEMP/emsdk/upstream/bin:$PATH"
bash tools/m11/m11_gen_ir2.sh && bash tools/m11/m11_build.sh
mkdir -p tools/m11/work/trap_triage tools/m11/work/trap_2672
node tools/m11/trap_triage/survey_units.mjs tools/m11/work/trap_triage/base.json          # 基準 (§2.1)
wasm-opt --instrument-memory tools/m11/work/m11_boot.cjs.wasm -o tools/m11/work/trap_2672/instr.wasm
wasm-dis tools/m11/work/trap_2672/instr.wasm -o tools/m11/work/trap_2672/instr.wat
python3 tools/m11/trap_triage/store_sites_2672.py tools/m11/work/trap_2672/instr.wat tools/m11/work/trap_2672/sites.json
WATCH_OLD=0 WATCH_UNITS=0,1 node tools/m11/trap_triage/watch_store_2672.mjs tools/m11/work/trap_2672/out_pos.json   # 陽性対照 (§2.3)
python3 tools/m11/trap_triage/compare_kinds_2672.py tools/m11/work/trap_triage/base.json tools/m11/work/trap_2672/out_pos.json
WATCH_OLD=0x1029e5d8 node tools/m11/trap_triage/watch_store_2672.mjs tools/m11/work/trap_2672/out_main.json   # 本番 (§2.2・§2.4)
python3 tools/m11/trap_triage/compare_kinds_2672.py tools/m11/work/trap_triage/base.json tools/m11/work/trap_2672/out_main.json   # kind 差分 (942 unit)・0〜477 集計・hit
```

- `compare_kinds_2672.py` の出力: `compared_units=N kind_diff=0` (差分 0 件)、`0-477 base:` と `0-477 watch:` の集計 (本番では両方 `halt0 4 miss 45 ok 422 oob 6 other 1`)、`hitN=1` と hit の行 (陽性対照では unit 1 の 5 件)。
- `watch_store_2672.mjs` の既定の計装版は `work/trap_2672/instr.wasm` (環境変数 `WATCH_WASM` で変更可)。
- 計装版は `work/` にだけ置く。build の出力 (`m11_boot.cjs.wasm`) は変えていない (基準 survey は計装前に取った)。

## 8. 測定 commit からの差分 (差分 0 の証跡)

- 測定 commit: `c05f4b16` (コードを変えた最後の commit)。build 出力 (`m11_boot.cjs.wasm`) は `86e83ad5` の作業ツリーで生成した。その後の code 変更は比較スクリプト `compare_kinds_2672.py` の追加・修正のみで、build 入力ではない。
- build 入力 (IR・C・build スクリプト) は origin/main `208b4ef9` と同一。`git diff --stat 208b4ef9 c05f4b16 -- tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/m11_ov.c tools/m11/m11_rt.c tools/m11/m11_win.c tools/m11/trap_triage/survey_units.mjs tools/m11/ldfix` の出力は空。
- 測定 commit 以降の `tools/m11` の差分: 本 REPORT を更新した commit 時点で `git diff --stat c05f4b16 HEAD -- tools/m11` は本ファイルのみ (コード差分 0)。main 取り込み後の再測定は不要 (`docs/WORKFLOW.md` §6)。
- origin/main (`b7df55e6`) は `208b4ef9` 以降に `tools/m11` の 20 ファイル (`ldfix/` の解析スクリプト・結果・REPORT、`shimx_link/`、`trap_triage/REPORT_1620.md`・`trap_w1620.py`) を更新している。いずれも IR 生成・build・survey の経路から呼ばれず、`ldfix/ldfix.py` と C ソース・`m11_build.sh`・`survey_units.mjs` は `208b4ef9` と差分 0 (`git diff --stat 208b4ef9 origin/main -- tools/m11` の内訳で確認)。`git merge-tree` は衝突なし。
- 参考: `git diff --stat 39fe9fad c05f4b16 -- tools/m11` は `REPORT_2672.md` と `compare_kinds_2672.py` の 2 ファイル。
