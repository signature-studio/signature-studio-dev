# #1620: unit 477 の `0x10a9f910` 下位 4B 上書きの書込み元 (IR 外か) の切り分け (結論は部分)

親: #1288 (経緯は `REPORT_1046.md` §10〜§19)。測定 commit: `2ba1bce8` (`trap_w1620.py` を追加した commit。計測に使ったコードはこれ)。検証 HEAD: `f4fa48f9` (origin/main) に上記 1 ファイルを足したもの。

**結論 (本 run): 受入 1 (書込み元 store の IR site) は未達。ただし、unit 477 で `0x10a9f910` の下位 4B を `0x1029e5d8` から `2` に変えた書込みは、IR の `store` 経路ではないことを、挙動を変えない計装 (C 呼出しなし) で確かめた。** D17 (IR の 8B→4B 縮退) の仮説は、この書込みには当てはまらない見込み。

## 1. 基準

- 素材: `fl-win64` は `extracted/block00031_PE.bin` だけを `tar --zstd --wildcards` で展開 (2.9 s)。`work-m11`・`work-liftdiff` は worktree に展開 (4.8 s)。toolchain は `[EMSDK]`・`[RETDEC]` (既存のインストール先)。
- `m11_gen_ir2.sh` rc 0 (51.5 s、490,735 行) → `m11_build.sh` rc 0 (26.1 s) → `survey_units.mjs` rc 0 (13.3 s): `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` (§2 と一致)。

## 2. スタック埋めへの感度 (`SV_STK_FILL`: 各 unit の直前に SP 直下 8 KiB を埋める)

| 埋め値 | ok | oob | abort |
|---|--:|--:|--:|
| なし | 870 | 16 | 0 |
| 00 | 872 | 12 | 2 |
| aa | 866 | 18 | 2 |

- kind が変わる unit は 8 件: 134 (なし ok → aa oob)・144 (なし oob → 00 ok)・149・153・158・265・304 (oob → abort)・555 (oob → abort)。最初の分岐は unit 134 (埋め aa)。
- 結果が埋め値に依存する = lift 側が書かれていない stack 領域を読んでいる。§19 の結論を survey で再確認した。

## 3. unit 134 (埋め aa) の trap 位置

- frames: `function_413870 ← function_639920 ← function_63a330 ← function_63a5e0`。最上位は wasm-function[2080]:0x14dec3 の `i32.load8_u offset=0`。
- 直前の列: `local0+48` の qword を読み (`i64.load offset=48`)、`local0+72` へ複製し、その値を `i32.wrap_i64` して読み取りアドレスに使う。値が 0 なら分岐で飛ばされる。
- 推定 (未実測): `local0+48` は未初期化の stack 残骸。埋め 00 では 0 になり分岐が飛んで ok、埋め aa では OOB、と整合する。
- 注意: IR の `define i64 @function_413870()` は引数なしだが、呼出し側 `function_639920` は 3 引数で呼ぶ。wasm 側の型との対応は未確認。

## 4. 計装の副作用 (C 呼出しを含む計装は挙動を変える)

| 版 | 0..477 の survey | 基準との差分 unit |
|---|---|---|
| 基準 (計装なし) | ok 422 / oob 6 | — |
| 対照: 計装なし・同じ経路 (`emcc -c boot_final3.ll -o work/obj/boot.o` + `M11_KEEP_BOOT_O=1`) | ok 422 / oob 6 | 0 |
| `watch_store_682.py --fns function_903d20,function_904190,function_abfd60` (store 7 件に `m11_sw` 呼出し) | ok 423 / oob 5 | unit 304 (oob → ok) |

- unit 304 は §2 で埋め値に依存する unit。`m11_sw` の呼出しが stack 残骸の並びを変えたと読める。以後、C 呼出しを使う計装 (`watch_store_682.py` 系) は、基準との差分を必ず確認すること。

## 5. unit 477 の UStrAsg (`SV_TRACE_AT=477`、0..477 の実行)

- unit 477 の trace の `[m11][UStrAsg]` は 1 件のみ: `dest=0x10bd5a08 src=0x6befcc old=0x0`。`dest=0x10a9f910` は無い。よって UStrAsg (`m11_ov.c` の C helper) は unit 477 の書込み元ではない。
- 同じ trace の icall は `0x6bfd60`・`0xf960`。OOB 直前は `function_903d20 ← function_904190 ← function_abfd60`。

## 6. C 呼出しなしの計装 (`tools/m11/trap_triage/trap_w1620.py`)

- 方式: IR の全 store 54,041 件 (store 行の全数と一致、未マッチ 0) の直前に、「`0x10a9f910` の下位 4B が OLD と等しく、store 範囲がその 4B と重なる」を判定する。真なら、site 固有の OOB アドレス (`0xE0000000 + site`) への volatile load に `select` で差し替える。C 呼出し・新規 global は無い。site は trap の wasm 位置から引く (`sites_trap.json`)。
- 陰性対照 (OLD = `0x1029e5d8`、unit 477 直前の値): 0..477 の全 unit で kind と frames が対照と一致 (差 0)。site trap は発火しなかった。unit 477 の trap は従来どおりの自然 OOB (`function_903d20` wasm[5371]:0x5c949c、`i64.load offset=0` = `*(arg-8)` の参照カウント読み)。
- 陽性対照 (OLD = 0): unit 1 で発火 (W への初回書込みを検出)。検出機構は IR store に対して動く。OLD = 0 では 75 unit の kind が変わるが、これは trap で unit が止まるため。
- 解釈: 0..477 の実行で、`0x10a9f910` の下位 4B が `0x1029e5d8` の間に、W と重なる IR store は実行されていない。よって unit 477 の `0x1029e5d8 → 2` (下位 4B) の書込みは、IR の store 経路ではなく、C 側 (`m11_simd.c`・`m11_rt.c`・`m11_win.c`・`m11_fnstubs.c`・shim の C、またはそれらの生成元) の書込みと推定する。根拠: IR の store は全数計装済み、`llvm.memcpy`/`llvm.memset` の呼出しは IR に 0 件。

## 7. 含意

- D17 (IR の qword store が 4B に縮退) の仮説は、unit 477 の下位 4B 書込みには当てはまらない (その書込みは IR store ではない)。
- 残る構図: 上位 4B の `1` は 477 より前の 8B 書込み (`0x1_1029e5d8`、§14) の残り。下位 4B だけを後から C 側が書き、上位が残る。「上位が残る」は埋め値依存 (§2・§19) と整合する。
- 次の手順 (子 issue に分割): (a) C 側の書込み主体を特定する。C 呼出しを増やさない方式 (C 側で「W と重なる & 下位 4B == OLD」のとき不正アドレスへ書いて trap) で、対応する C 関数を絞る。(b) 陽性対照を先に取る。(c) 0..477 の kind と frames が計装なしの基準と一致することを実測で確認する。

## 8. 受入条件の判定

| # | 条件 | 判定 |
|---|---|---|
| 1 | 書込み元 store の IR site | 未達。IR store 経路ではないと判明 (§6)。C 側の書込み主体は未特定 (子 issue) |
| 2 | D17 か別類型か | 未達。unit 477 の書込みは IR 縮退 (D17) に当たらない見込み (§7) |
| 3 | 修復後の回帰 | 未達 (修復未実施) |

## 9. 差分 0 の証跡 / 再現

- 測定 commit `2ba1bce8`: 追加は `tools/m11/trap_triage/trap_w1620.py` のみ。`git diff --stat f4fa48f9 HEAD -- tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/m11_ov.c tools/m11/m11_rt.c tools/m11/m11_win.c tools/m11/trap_triage/survey_units.mjs tools/m11/ldfix` の出力は空 (既存コードの差分 0)。
- 計装 build は `work/` にだけ置き、各回の後に `m11_build.sh` で基準へ戻した (restore rc 0 を 4 回確認)。`git status` に `work/` 以外の差分なし。
- 再現 (`CF` は `store_watch_2270.sh` と同じ `-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=0 -DM11_OV_CLASSCREATE=0 -I.`):
  1. `python3 trap_triage/trap_w1620.py --out work/probe1620 --old 0x1029e5d8`
  2. `rm -f work/obj/boot.o work/obj/ov.o; emcc -c work/probe1620/boot_trap.ll -o work/obj/boot.o $CF`
  3. `M11_KEEP_BOOT_O=1 bash m11_build.sh`
  4. `SV_RAW=1 SV_ONLY=0,1,...,477 node trap_triage/survey_units.mjs work/probe1620/trap.json`
  5. 復元: `rm -f work/obj/sw682.o work/obj/boot.o work/obj/ov.o; touch work/boot_final3.ll; bash m11_build.sh`
