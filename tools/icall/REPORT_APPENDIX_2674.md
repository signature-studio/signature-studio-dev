# 付録: icall #2674 (ICALL-79) — frame slot 残件: 0x18105d9fc のオラクル修正・0x180da4030 の xmm0 脱落の説明

> 親: #2508 (ICALL-78・付録 `REPORT_APPENDIX_2508.md`)。子: #2695 (ICALL-81: harness 初期化と 0x180da6e60 の 6 件の分類)・#2696 (ICALL-82: data 区分の脱落の修復)。
> 測定 commit: `3127f774` (`fix(icall): compare user-space pointers as PTR in fa_cmp and add xmm0 origin tools (ICALL-79)`。コードを変えた最後の commit)。以降のコード差分は §8。
> 既知類型との関係: 新類型 (DEFECTS.md に該当なし。§5 の行案)。

## 1. 結論

- **受入 3 (0x18105d9fc の比較オラクル): 達成。** `fa_cmp.py` で x86-64 ユーザ空間の値 (`0 < v < 2^47`) を bit 比較せず `PTR` に畳む。0x18105d9fc は **0/8 → 8/8** (旧オラクルは native `0x50400010` と wasm `0x104af418` を別物として数えていた)。`FA_PTR_NORM=0` で旧挙動に戻る (負の対照)。
- **受入 2 の 0x180da4030: 達成 (説明)。** native の 0 は、0x180da4030 の分岐先 (fall-through の実コード) が `movups xmm0,[rdi]`・`movups xmm0,[rdi+0x20]` で heap の 0 を読むため。wasm 側の IR はその分岐を `ret` で打ち切り、xmm0 は入力のまま残る。native の heap に既知パターンを書くと native xmm0 がそのパターンになり、読み出しを確認した (§4.3)。修復は子 #2696。
- **受入 2 の 0x1803dee20: 未了。** 本 run の HEAD では native・wasm とも入力素通しで **8/8 一致**。付録 2508 §3.5 の「native 0」は再現しなかった。揺れの原因は未特定 (子 #2695)。
- **受入 1 (0x180da6e60 の 6 件の分類): 未達。** native は起動直後に SIGSEGV し、動的判定ができない。harness の修正が前提 (子 #2695)。
- **sweep (fixed route・131 関数): 旧オラクル 55/66/8/2 → 新オラクル 56/66/8/1** (bit 一致 / native crash・timeout / wasm のみ err / 値の不一致)。値の不一致は 0x180da4030 の 1 件だけ。
- **訂正**: 付録 2508 §4.3 の「native の SIGSEGV は `[rax+8]` の仮想呼出し・harness が初期化しない global 参照」は誤り。実際の命令は `inc dword ptr [rax+0x19a4]` で、`rax = [rcx+0x10] = 0` (rcx は harness が渡す heap 領域)。global ではなく、引数の構造体を harness が用意していないこと。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit | `3127f774` (作業ツリー = HEAD で測定。測定経路の差分は §8) |
| 素材 | `work-icall` (`tools/icall/work/`・`tar --zstd -xf` 25.7 s)。`toolchain-retdec` (`/opt/retdec`)・`toolchain-emsdk` (`/opt/emsdk`) は agent-setup 展開済み。`fl-win64` は未使用 (解析は dsm・IR のみ)。`plugins-freshair` は無いので `FA_CORE=rw.dll` |
| route | `FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh` (fixed)。build 所要 約 6 s (実測) |
| sweep | `bash tools/icall/diff/fa_sweep.sh 8 60` (131 関数・1 並列)。新オラクル 69.8 s、旧オラクル 69.5 s (`FA_PTR_NORM=0`)。load (1 分平均) は 4 core 機で sweep 後 0.88 / 0.72 |
| 比較 | `fa_cmp.py` の判定 (xmm0 の 64bit、同一入力 8 点、seed 3)。ptr 正規化は §3 |

## 3. 0x18105d9fc: 比較オラクル (受入 3)

- 原因: callee が確保した領域のポインタを xmm0 に返す。native (`ott_heap_alloc`) と wasm (`_malloc`) はヒープの基底が違うため、bit 比較は必ず不一致になる。native `0x50400010`・`0x50401050` と wasm `0x104af418`・`0x104b0438` (先頭 2 入力)。
- 修正: `tools/icall/diff/fa_cmp.py` の `ptr_norm()`。両側の値が `0 < v < 2^47` なら `PTR` に畳んでから比較する。
- 結果 (同一入力 8 点):

| 条件 | match | mismatch |
|---|--:|--:|
| `FA_PTR_NORM=0` (旧) | 0 | 8 |
| 既定 (新) | **8** | 0 |

- 限界: `PTR` は値を畳むので、ポインタのオフセットの差は検出しない。正規化された double の上位 16bit は 0 にならないため、この範囲はポインタ由来と見なせる。ただし subnormal は誤って `PTR` になりうる。
- 負の対照: 値が double の 0x180da4030 は正規化で変わらず 0/8 のまま (不一致を隠していない)。

## 4. 0x180da4030: xmm0 の出所 (受入 2)

### 4.1 機械語 (`tools/icall/diff/xmm0_origin.py 180da4030 --end 180da41a0`)

```
0x180da404a [fn  ] call     0x180da3f80                      (rdi = rdx は 0x180da4047 で設定。Win64 の非揮発 rdi を callee が保存)
0x180da4066 [fn  ] ret                                       (ax == 0x4001 の経路。xmm0 は入力のまま)
0x180da4088 [data] movups   xmm0, xmmword ptr [rdi]          WRITE xmm0
0x180da4097 [data] movups   xmm0, xmmword ptr [rdi + 0x20]   WRITE xmm0
0x180da4176 [data] ret
```

- `0x180da407f` の `xor eax, eax` (2 B) の直後の `0x180da4081` は、dsm では `; data inside code section` (0x180da4081–0x180da41a0)。`jne 0x180da4067` の経路は fall-through でここへ到達する実コード (CFG 全体は未追跡)。
- 0x180da4088 と 0x180da4097 の xmm0 書込みは、dsm の `function` 区分の外にあるため、dsm の関数範囲だけを見ると「xmm0 の書込みが無い」ように見える。

### 4.2 wasm 側 IR (`work/rt_freshair-core/after.0.restored.ll`, `function_180da4030`)

- `br i1 %23` の偽側 `dec_label_pc_182320686` は `store` の後に `ret i64 %24` で終わり、0x180da4081 以降の命令を含まない。
- xmm0 の出力は `%20 = __asm_movsd(load BLK+0x…)`、つまり入力の値をそのまま書き戻す。
- 結論: lift は data 区分の境界で後続を切り、wasm では xmm0 が入力素通しになる (silent miscompile)。

### 4.3 動的確認 (`tools/icall/diff/xmm0_probe.py 1803dee20,180da4030 --n 4`)

| VA | native (先頭 4 入力) | wasm (先頭 4 入力) | heap probe (`[rdx+0x20]` にパターンを書く) |
|---|---|---|---|
| 0x180da4030 | `0000000000000000` ×4 | `c000c5300342457c`・`3fd6a5368858d8d0`・`bff0a54f21584a44`・`3fea9a80ef2b7250` | native xmm0 = `4142434445464748` (パターンの下位 8B) |

- native が 0 を返すのは、`[rdx+0x20]` の heap が 0 のまま読まれるため。パターンを書くと出力が変わる (xmm0 は heap のメモリ由来)。
- wasm は入力素通し。第 2 の (`movups [rdi+0x20]`) 命令が IR に無いことと整合する。
- 判定: **lift の脱落** (機械語を data と誤分類した後続の欠落)。修復の対象は子 #2696。

## 5. 新類型の行案 (`docs/DEFECTS.md` 形式。番号と採否は PM 判断)

| 類型 | 分類 | 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|
| D24 (案) | fe (RetDec の dsm 段) | wasm の出力が入力を素通し、native は heap 由来の値 | RetDec が実コードを `; data inside code section` と誤分類し、fall-through の後続 (`movups xmm0`・`ret`) が IR から消え、分岐先が `ret` で打ち切られる | 0x180da4030 (data 区分 0x180da4081–0x180da41a0)。dsm の data 区分は 307 件 | `data inside code section` の区分内に xmm 書込み・`ret` がある関数 | 子 #2696 |

- D3 (メモリ宛 store の消失) や D1b (jcc 先の dead code 削除) とは、脱落の単位が「命令列 (区分) 全体」である点で異なる。

## 6. 0x1803dee20 (受入 2 の残り)

- 本 run の HEAD: native・wasm とも入力素通し、8/8 一致 (`xmm0_probe.py`)。heap probe でも出力は変わらない。
- 関数本体 0x1803dee20–0x1803def2b に xmm0 の書込みは無い (`xmm0_origin.py 1803dee20 --end 1803def2b`)。呼出しは `0x180ca3260` (xmm 命令なし)・`0x18100c760` ×2 (`jmp 0x18100be74`)。
- `0x18100be74` は `0x1810553d0` (中で間接 call `[rip+0x6f43c]`) と `0x18104c764` (`jmp 0x1810580f0`) を呼ぶ。xmm0 の最終書込み元は未特定。
- 付録 2508 §3.5 の「native 0」は再現しなかった。揺れの候補 (間接 call の先の harness 状態) は未確認。子 #2695 で扱う。

## 7. 分類の結果 (fixed route・131 関数)

| 条件 | bit 一致 | native crash/timeout | wasm のみ err | 値の不一致 | 値の不一致の関数 |
|---|--:|--:|--:|--:|---|
| 旧オラクル (`FA_PTR_NORM=0`) | 55 | 66 | 8 | 2 | 0x18105d9fc・0x180da4030 |
| **新オラクル (既定)** | **56** | 66 | 8 | **1** | 0x180da4030 |

- 付録 2508 §3.5 の HEAD 値 (54/66/8/3) との差は 0x1803dee20 の 1 件だけ (旧オラクルの本 run では一致。2508 §3.5 と同じ揺れ)。
- 集計定義: `fa_sweep.sh` の判定。native crash/timeout は native_err>0 または status (timeout)、wasm のみ err は wasm_err>0、値の不一致は mismatch>0 かつ両側 err 無し。

## 8. 0x180da6e60 (受入 1 の残り) と測定 commit からの差分

- 0x180da6e60 (`function_180da6e60` 0x180da6e60–0x180da73b5): `fa_cmp.py 180da6e60 --n 1` は rc=95 で SIGSEGV (`rip=0x180da6e99` `addr=0x19a4` `rax=0`)。命令は `mov rax,[rcx+0x10]` → `inc dword ptr [rax+0x19a4]` (§1 の訂正)。
- 誤り疑い 6 件 (2508 §4.2 の No 1・2・6・7・9・10) は、いずれも関数範囲 (dsm の function 区分) の中にあり、data 区分の脱落ではない。分類は子 #2695。
- 測定経路 (route 構築・sweep・native・data 敷設・IR 後処理の各スクリプト) の 2508 測定 commit `05194cdc` からの差分は 0 行: `git diff --stat 05194cdc 3127f774 -- tools/icall/fa_route_build.sh tools/icall/frame_slot_restore.py tools/icall/diff/fa_sweep.sh tools/icall/ir_flatten.py tools/icall/ir_fix_mask.py tools/icall/ir_fix_vstore.py tools/icall/ir_override.py tools/icall/rt tools/ott/native tools/ott/lift/data_gen.py tools/m2/ir_normalize.py tools/m5/ir5_patch.py tools/m11/m11_simd2.py tools/icall/vex_gen.py tools/icall/simd_merge.py` の出力は空。本 run で変えたのは `fa_cmp.py` (§3) と 2 つの診断スクリプトだけ。

## 9. 再現

```sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .          # tools/icall/work/ へ (展開 25.7 s)
bash tools/ott/native/build.sh                                    # fa_cmp / xmm0_probe に必要
export FA_CORE="$PWD/tools/icall/work/rt_freshair-core/rw.dll"
export TMPDIR="$RUNNER_TEMP"
FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh                # fixed route
python3 tools/icall/diff/fa_cmp.py 18105d9fc --n 8                # 期待: match 8 / mismatch 0
FA_PTR_NORM=0 python3 tools/icall/diff/fa_cmp.py 18105d9fc --n 8  # 負の対照: match 0 / mismatch 8
python3 tools/icall/diff/xmm0_origin.py 180da4030 --end 180da41a0 # data 区分の movups xmm0 2 件
python3 tools/icall/diff/xmm0_probe.py 1803dee20,180da4030 --n 4  # native / wasm の値と heap probe
bash tools/icall/diff/fa_sweep.sh 8 60 | tail -1                  # 期待: bit一致 56 / 66 / 8 / 1
```

- 測定 commit からの差分 (`git diff 3127f774 HEAD -- tools/icall ':!tools/icall/REPORT_APPENDIX_2674.md'`): 本付録の commit 時点で出力は空 (測定に使ったコードは `3127f774` のみ)。

## 10. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x180da6e60 の「誤り疑い」6 件 (2508 §4.2 の No 1・2・6・7・9・10) の分類 (受入 1 の残り) | 6 件は未判定。native は rcx の構造体を用意しないと実行できない | #2695 (ICALL-81) |
| 0x1803dee20 の native 0 (付録 2508 §3.5) の再現と原因 (§6) | 1 関数の揺れ。本 run では再現せず | #2695 (ICALL-81) |
| 0x180da4030 の後続 (data 区分の脱落) の修復 | 値の不一致 1 件 (silent miscompile) | #2696 (ICALL-82) |
| data 区分に実コードを持つ他の closure 関数の有無 | 同型の脱落の範囲が未確認 | #2696 (ICALL-82) |
| 新類型 D24 (案) の `docs/DEFECTS.md` 追記 | 横断正本への反映 | PM 判断 (`docs/WORKFLOW.md` §5) |
| 2508 の残件 (受入 3 の sha256 照合は #2675、受入 4 の merge 規則、lift の ABI 仮想化 `BLK+0x88 := BLK+0x28` の欠落) | — | #2508・#2675 |
| 付録 2508 §4.3 の SIGSEGV 説明の訂正 (本付録 §1 で訂正済み) | 誤った前提で次の作業が進むのを防ぐ | 本 PR で訂正 (2508 付録は変更しない) |
