# REPORT_APPENDIX_3608 — trap 144・149・114 の引き金の採取 (REPORT_3608 §8 の分割移動)

本文の要約と未解決は `REPORT_3608.md` §8 を参照。以下は採取の詳細 (分割移動・内容は不変)。


- 採取スクリプト (commit 済み): `trap144_probe_3608.py` (prod fix の IR に entry 引数と store 書込み元の記録を入れる) と `trap144_read_3608.mjs` (trap 時に読む)。前 run の撤回済みの値は使わない。
- 採取コマンド (`export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP`):
  1. `bash tools/m11/ldfix/ldfix_e2e.sh` (rc 0・72 秒・判定 PASS・survey ok 136 / miss 14 / trap 9)
  2. `bash tools/m11/ldfix/prod_order_3608.sh h_nor8b fix ld108,ld115,src412770,qstore,alloca,guard699,guard4fa210` (872 / 47 / 22・trap 集合は §1-3 の S22 と一致)
  3. `python3 tools/m11/ldfix/trap144_probe_3608.py work/p3608/h_nor8b/prod.ll work/t144/probe.ll work/t144/sites.json` (store 54,043 件に計装・3 秒)
  4. `bash tools/m11/ldfix/stage4.sh work/t144/probe.ll t144` (rc 0・units_run 109・init 111・icall_ok 435・dllmain_done True・threw なし)
  5. `S4_NAME=t144 S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap144_read_3608.mjs > work/t144/read.txt` (26 秒)
- 採取件数 (`911cd33b2` の reader・OOB のみ採取の版): probe 版の trap は 14 件 (全て OOB)。prod fix の OOB 14 件 (144・149・275・280・477・484・492・513・520・659・745・830・880・923) と一致。halt0 8 件は `911cd33b2` の reader の対象外で、`77ead008e` で reader に枝を入れた後の再採取は本 run では未実施 (§8-3)。
- 出力: `tools/m11/ldfix/work/t144/read.txt`・`work/t144/sites.json` (gitignore)。site 番号は `work/t144/sites.json` の `stores[sid-1]` (元 IR の関数名・行番号)。

### 8-1 unit 144 (OOB・最内 `function_44aeb0`)

- 採取値: `function_44aeb0` の entry arg1 = `0x5f007000730064`・arg2 = `0x418b4820`。
- 上流: `function_44f040` (arg1 = `0x10aa13f0`・arg2 = `0x2539c8`・arg3 = 0) ← `function_653660` (arg1 = `0x10aa1400`・arg2 = `0x2572dc`・arg3 = 1・arg4 = 0) ← `function_6539e0` (arg1 = `0x2572dc`・arg2 = 1・arg3 = 0)。
- `911cd33b2` の再採取で、entry 引数と書込み元は上の値と一致した (hit 1 回)。
- `[0x10aa13f0]` の最後の書込み: `function_653660` の IR 219682 行 `store i64 %13, ptr %stack_var_-32`。`%13` は `%13 = load [stack_var_-56]` (219681 行) で、その前の `call function_439550(&stack_var_-56, arg2 = 0x2572dc)` が書いた値。
- `function_439550` は arg2 から 16bit ずつ読み、A-Z の範囲だけ小文字化 (`|0x20`) して arg1 へ書く (IR 134964 行〜・store は 135001 行)。よって `0x2572dc` の文字列 `"dsp_ippv2.dll"` (UTF-16LE・image 内の実値) を小文字化したものが `0x5f007000730064` (`"d\0s\0p\0_\0"` の 8 byte) になる。
- 書込み元の要約: unit 144 の a1 は、`function_6539e0` が渡す定数文字列 `0x2572dc` (`dsp_ippv2.dll`) を `function_439550` が小文字化してコピーしたもの。値の選択 (なぜ `dsp_ippv2.dll` を渡すか) は未追跡。

### 8-2 unit 149 (OOB・最内 `function_412e40`)

- 採取値: `function_412e40` の entry (4 回 hit): arg1 = `0x10aa1418`・arg2 = `0x2`。上流: `function_653660` (arg1 = `0x10aa1430`・arg2 = `0x264208`・arg3 = 0・arg4 = 0) ← `function_6539e0` (arg1 = `0x264208`・arg2 = 0・arg3 = 0)。
- `[0x10aa1418]` の最後の書込み: `function_4136a0` の IR 119304 行 `store i64 %9, ptr %15` (%9 = `call function_412c20(len)` の戻り値。採取値は 0)。
- 未特定: `function_412c20` の戻り値 0 の由来。`0x264208` は `"Blend2D.dll"` (UTF-16LE・image 内の実値) で、`function_6539e0` の定数文字列。
- 注: `function_412e40` の entry は 4 回 hit で、最後の 1 回の arg1 が `0x10aa1418`。記録は最後の entry のものを読んでいる。`911cd33b2` の再採取でも 4 回・同じ値。
- 挿入位置 (`911cd33b2` で確認): 5 関数 (44aeb0・44f040・653660・412e40・6539e0) の entry 基本ブロックは全て名前付きラベル (`dec_label_pc_<VA>:`) で始まる (`work/boot_final3.ll` の define 直後)。計装はそのラベル直後に入る (`work/t144/probe.ll` で確認)。よって hit 回数は entry 1 回ごとの数で、上の 4 回・1 回は暫定値ではない。

### 8-3 unit 114 (halt0・Halt 呼出し元)

- reader に halt0 の枝を入れた (`trap144_read_3608.mjs`・halt0 は kind `halt0->longjmp` で採取。枝の追加は commit `77ead008e`)。`77ead008e` の reader の出力では halt0 8 件 (114・245・279・314・368・509・647・895) と OOB 14 件を採取した、と前 run で記録された。(#5280 の run で、素材 (`work-m11`・`toolchain-emsdk`・`fl-win64`) を展開して再採取した。halt0 8 件・OOB 14 件の unit 番号と kind は §1-3 の S22 と一致。)
- wasm 位置 → IR 名 (`m11_wasmnames.py` で `m11_boot.cjs.wasm` から解決): 114 の最内は `function_412770` (`0x806d16`)、その呼出し元は `function_4128b0__lifted` (`0x2d7a94`) ← `function_4128b0` ← `function_412a40` ← `function_4096b0` ← `function_4096d0`。245・279・509・647 は `function_412a60` ← `function_411d20` の鎖。
- `function_412770` は `arg1` の領域へ 37 要素を書く関数 (IR 117827 行)。`function_4128b0__lifted` の 2 つの call site (IR 117917 行・118017 行) のうち、どちらが 114 を引いたかは**未確定**。`function_412770` の entry 計数を probe に入れて試したが全 unit で 0 になり、計装の正しさを確認できなかったため撤回した (probe は元の 5 entry に戻した)。
- 確定 (#5280・本 run・測定 commit は下の §8-5): call site を計装 (`trap114_probe_5280.py`・`trap114_read_5280.mjs`) で採った。halt0 の 8 件 (114・245・279・314・368・509・647・895) はすべて **call site B** (IR 118017 相当・`function_412770(18787456)`) を 1 回通り、call site A (IR 117917 相当・`18787752`) は 0 回。entry 時の global は全 8 件で 18787760=0・18787504=`0x100000002`・18768032=0 (いずれも entry 時点の値。B の直前の分岐 (`dec_label_pc_4129be` の `18787504` の i8 読み) の値は未採取)。18787760=0 のため `dec_label_pc_4128e0` の A 側の枝には入らない (IR 117917 を経由しない)。
- 注 (対照の弱さ): 計装版では `function_4128b0__lifted` の entry が halt0 の 8 件以外の unit で 1 回も立たなかった。したがって「A が 0 回」は halt0 unit の中での観測で、A が他の unit で走るかは未測定。

### 8-5 unit 114 の call site 計装 (#5280・受入 1 の call site 部分)

- 手順: `ldfix_e2e.sh` (rc 0・PASS) → `prod_order_3608.sh h_nor8b fix ld108,ld115,src412770,qstore,alloca,guard699,guard4fa210` (872/47/22・halt0 8・OOB 14) → `python3 trap114_probe_5280.py work/p3608/h_nor8b/prod.ll work/t114/probe.ll` → `bash stage4.sh work/t114/probe.ll t114` (rc 0・units_run 109・dllmain_done True) → `S4_NAME=t114 node trap114_read_5280.mjs`。
- 結果: halt0 8 件すべてで call site B (IR 118017 相当) 1 回・call site A 0 回。OOB 14 件は A・B とも 0 回 (`function_4128b0__lifted` を通らない)。
- 対照の制約: 計装版で entry が立ったのは halt0 の 8 件だけ (正常 unit は 0)。A の 0 回は halt0 の中での観測。
- 未確定: B の分岐条件 (`18787504` の i8 の trap 時の値)。受入 1 の残りは、この値と B 直前の分岐の確認。

### 8-6 unit 114 ほか halt0 の B 分岐値 (#5280・受入 1 の残り)

- 計装: `trap114_probe_5280.py` に 3 箇所 (`dec_label_pc_4129be`・`dec_label_pc_412904`・`dec_label_pc_412978`) で `18787504` の i8 を読む枠を足した (枠 +56〜+80)。reader は `trap114_read_5280.mjs`。
- IR の分岐 (prod.ll 118013〜118014 行): `%51 = icmp eq i8 %.pr, 0` → 偽のとき call site B (`function_412770(18787456)`・118017 行)。つまり i8 ≠ 0 で B に入る。
- 実測 (halt0 8 件・全件): entry 1 回・B 1 回・A 0 回。`4129be` 通過時の i8 = 2 (7 件)。368 だけ `4129be` を通らず、`412904`・`412978` の i8 = 2 で B に入っている (`.thread` 経路)。
- 結論: halt0 8 件はすべて `18787504` の i8 = 2 (≠ 0) で call site B に入り、Halt 側へ進む。受入 1 の「どの call site が引くか」は B で確定。「分岐の trap 時値」も 2 で確定。
- 未確定: `18787504` (= 18787456 + 48・引数領域の 6 番目 qword) の値 `0x100000002` の出所。entry 時点 (4128b0) で既に入っており、読み出し (`4129be`・B より前) も 2 。prod.ll 全体で `18787504` を直接指定する store は無く、読み出しは 4 箇所だけ (117921・117975・118011・118033 行)。118032 行の memcpy (37 qword) は B の後 (`412a12`) なので値の出所ではない。前段 (4128b0 の呼出し元 `function_412a40` ← `function_4096b0` の鎖) で入る値として未追跡。
- 対照の制約: OOB 14 件は entry 0 回 (`function_4128b0__lifted` を通らない)。

### 8-7 `18787504` (0x100000002) の書込み時点 (#5280・受入 1 の残り・診断)

- 計装: `trap114_g_read_5280.mjs` (boot 前後と各 unit の前後で `18787504` を読む)・`trap114_src_5280.py` + `trap114_src_read_5280.mjs` (memcpy 直前の源を読む)。測定 base は origin/main `0c0984281`。計装 3 ファイルは測定時には未 commit で置き、`a90515146` で commit した。**測定 commit は `a90515146`** (計装を含む最後の code commit)。`ldfix_e2e.sh` rc 0・64 秒・PASS、`prod_order_3608.sh h_nor8b fix` rc 0・41 秒・872/47/22。
- 同一性: **未確認**。測定時の計装ファイルのバイト列は残していないため、`a90515146` の 3 ファイルが測定に使ったものと同一かは照合できない。以後 HEAD まで 3 ファイルは変更していない (下の差分)。
- 測定経路の差分 (`git diff a90515146 HEAD`): 測定が実行したファイル (`ldfix_e2e.sh`・`prod_order_3608.sh`・`stage4.sh`・`ldfix.py`・`fix_*.py`・`survey_stage4.mjs`・`m11_postjs.py` と計装 3 ファイル) の差分は 0 行。`tools/m11/ldfix/` の残りの差分は `trap114_w_*` (8-8 の計装) と REPORT だけで、8-7 の測定は実行していない。
- `tools/m11/m11_passes.py` と `m11_setother_ptr_class.py` は `0c0984281..9ee36afa3` で main 側が変えたが、8-7 の測定経路からは呼ばれない。`m11_passes.py` を呼ぶのは `m11_gen_ir2.sh` だけで、測定は素材 `work-m11` の `tools/m11/work/boot_final3.ll` を読み、`m11_gen_ir2.sh` を再実行していない (`ldfix_e2e.sh` 1/5 の入力)。
- 実測: boot 前 `0x0` → `entry_point` 後 `0x100000002`。942 unit の各呼出しの前後では変化 0 (halt0 8・OOB 14 の全件で pre = post = `0x100000002`)。書込みは `m11_boot_enter` の中。
- memcpy 直前の源の計装は 0 件。B の `function_412770` (117995 行) は `412a12` (memcpy) より前で halt0 し、halt0 の unit は memcpy に届かない。
- 結論: 受入 1 の残りの「出所」は boot (`entry_point`) 内の書込みで、unit 側の経路ではない。boot 内の書込み元 (動的ポインタ経由の store) は未特定。

### 8-8 `18787504` の書込み元: IR store では捕まらない (#5280・受入 1 の残り・負の結果)

- 計装: `trap114_w_probe_5280.py` (prod fix の全 54,043 store に、宛先が `[G-7, G+7]` (G = 18787504) に入ったら回数と格納値を記録する判定を入れる)・`trap114_w_read_5280.mjs` (boot 中と各 unit の前後で回数を読む)。stage4 は `work/stage4/t114w` で rc 0・units_run 109・dllmain_done True・threw なし。
- 実測: boot 後の G は `0x100000002` (計装なしと同じ) だが、計装の回数 (`0x11FFA000`) は boot 前後・全 unit で 0。計装の SCRATCH 側には `0x336e` が入っており、判定の経路は走っている。つまり **G へ書く IR の store は 1 件も無い**。
- IR 上の確認: `prod.ll` には `atomicrmw`・`cmpxchg`・`llvm.mem*`・vector store が 0 件。G を直接指す store は 0 件 (G の読みは 4 箇所: 117921・117975・118011・118033 行)。
- C 側の候補: `m11_ov.c` の `D()`・`Q()` (volatile) と `memcpy`・`memset`。`D(0x11eac98)`・`D(0x11eac90)` 系は InitCount で G と無関係。`__asm_*` (`m11_simd.c`) は SSE の register 演算で、guest memory へ書かない。
- 候補 (未検証): `G = r13 + 0x30` (`r13 = 0x11eac80`・`m11_InitLib` が使う global)。`m11_InitLib` の `memcpy(ctx, r13, 296)` は `ctx` の範囲に G が入れば G を書く。`ctx` は引数で、本 run では値を採っていないため棄却できない。`memcpy(r13 + 0x38, tmp, 240)` は 0x11EACB8 から始まり G を含まない。`Q(r13+0x10/0x20/0)` は G に当たらない。boot 後の `r13+0x30` (= G) は `0x100000002` で、boot 前は 0。
- 結論: G への書込みは IR store でも `m11_InitLib` の memcpy でもない。残る候補は C 側の `memcpy`/`memset` (`m11_ov.c` 566・1565 行など) か、boot 中に呼ばれる C helper の volatile 書込み。未特定。次の手は、C 側の書込みに G の範囲判定を入れて stage4 を再ビルドすること (C の `D()`・`Q()` と `memcpy` の宛先を `m11_cwatch` で見る。`M11_WATCH_C5695` の仕組みが流用できる)。

