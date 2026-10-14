# 付録 2: icall #2695 (ICALL-81・第 2 報) — 0x180da6e60 の state 2・8 の harness と実行確認、0x1803dee20 の再測定

> 親: #2674。前報: `REPORT_APPENDIX_2695.md` (§10.6 の残件: state 2・8 の harness)。
> 測定 commit: `43b8a780` (コードを変えた最後の commit。`hit_180da6e60.py` に opt-in を追加)。`git diff 43b8a780 HEAD -- tools/icall/diff tools/icall/fa_route_build.sh tools/ott/native` は 0 行 (§7)。
> 既知類型との関係: 該当なし (前報と同じ)。

## 1. 結論

- state 2・8 の harness で、件数 >0 の経路を native で実行できた。A の vtable を image 内の ret 系機械語で作り、要素ごとに state と pair を置く (§3)。**6 件の候補 (No 2・6・7・9・10、および No 1) の store がすべて 1 hit 以上で実行された** (§4)。前報の「0 hit (未実行)」は解消した。
- **判定は依然 0 件**。候補 store の後段は、仮想 callee がその値を読むかで決まる。その callee は stub (`ret`) で、実物ではない。実物の vtable (A = `this+0x370`) は起動後の object graph の中にあり、静的には確定できない (§5)。
- 受入 1 (SIGSEGV の解消): 前報のまま部分。state 1・2・3・7・8 も stub で戻るようになった (件数 1 の各 state・件数 3 の複合)。ただし callee は stub。
- 受入 3 (0x1803dee20): 本 runner (Intel Xeon 6973P-C) では 8/8 (入力素通し)。関数本体は xmm0 を書かず、比較値は呼び出し先の残り値だった (§6)。0/8 になる条件は未特定。

受入の状況: 受入 1 = 部分 / 受入 2 = 未達 (実行確認 6/6・判定 0 件) / 受入 3 = 未達 (本 runner は 8/8、0/8 の条件は未確定)。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| runner | Intel Xeon 6973P-C (4 vCPU・Ubuntu 24.04・gcc 13.3.0・glibc 2.39)。sweep 前 load 0.17・sweep 後 0.74 |
| 素材 | `work-icall` のみ展開 (`tools/icall/work/`・`tar --zstd -xf` で 19.8 s)。`FA_CORE` = `tools/icall/work/rt_freshair-core/rw.dll`。emsdk は runner 既存の `[EMSDK]` (Emscripten 6.0.12 pin) を使用 |
| libottnative | `bash tools/ott/native/build.sh` で作成 |
| fixed route | `FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh`: OK (6.9 s) |

## 3. harness (state 2・8 の実行)

`tools/icall/diff/hit_180da6e60.py` に opt-in を追加した。既定の `fa_cmp.py`・`fa_sweep.sh` は変えていない。

- A の vtable `VT` (0x100 B) を確保し、`A+0` = VT とする。`VT+0x08`・`VT+0x30` = `0x1803b3d2d` (`mov rax, rcx; ret`。rax に A を返す)。`VT+0x10` = `0x1803ba143` (`ret`。仮想 callee は何もしない)。
- 要素 i (stride `0x100138`) ごとに、64 B 節点 `node[0] = (E+0xbf)&~63` を nil (`0x4001`) にし、state (`+0x100108`) を spec の値にする。state 2 は `+0x100120` に 16 B の pair を置く。state 8 は、接尾辞 `n` が無ければ `+0x100130` に 16 B の pair を置く (`n` なら 0 のまま)。
- 環境変数 `FA_ELEM_SPEC` (要素ごとの state を `,` 区切り。`n` 接尾辞は pair を 0 にする)。要素数は `FA_LOOP_N` と一致させる。

判定に効く制限:

- 仮想 callee は `ret` のみで、値を読まない。実物の vtable ではないため、callee が pair や local struct を読むかは確定できない。
- O1 (state 2 の `[A+8]` の戻り) と X (state 8 の `[A+0x30]` の戻り) は A 自身になる。実物では別のオブジェクトである。
- wasm 側は stub の VA が lift 対象外のため使わない。hit は native 専用。

## 4. 結果 (trace・測定 commit `43b8a780`・件数 1 は要素 1 個)

各 VA の hit 数。`SIGSEGV 点` は `inc dword ptr [A+0x19a4]` の VA で、ここは実行されて戻る (落ちない)。

| VA (候補) | 件数 0 (spec なし) | spec `2` | spec `8` | spec `8n` | spec `2,8,8n` (件数 3) |
|---|--:|--:|--:|--:|--:|
| `0x180da6e8e` No 1 (cookie store) | 1 | 1 | 1 | 1 | 1 |
| `0x180da6f4d` No 2 (state 2 の pair+8) | 0 | **1** | 0 | 0 | 1 |
| `0x180da7278` No 3 (state 8・pair あり) | 0 | 0 | 1 | 0 | 1 |
| `0x180da7280` No 4 (state 8・pair あり) | 0 | 0 | 1 | 0 | 1 |
| `0x180da7293` No 5 (IR 有) | 0 | 0 | 1 | 0 | 1 |
| `0x180da7297` No 6 (`[rbp-0x19]=r15`) | 0 | 0 | **1** | 0 | 1 |
| `0x180da729b` No 7 (`[rbp-0x11]=rcx`) | 0 | 0 | **1** | 0 | 1 |
| `0x180da7308` No 8 (IR 有・pair なし) | 0 | 0 | 0 | 1 | 1 |
| `0x180da730c` No 9 (`[rbp-1]=0`・pair なし) | 0 | 0 | 0 | **1** | 1 |
| `0x180da7310` No 10 (`[rbp+7]=0`・pair なし) | 0 | 0 | 0 | **1** | 1 |
| `0x180da6e99` inc 点 | 1 | 1 | 1 | 1 | 1 |
| `0x180da6ece` loop 先頭 | 0 | 1 | 1 | 1 | 1 |
| `0x180da7373` 出口 (cookie 検査) | 1 | 1 | 1 | 1 | 1 |
| `0x180da41a0` 41a0 (state 0 の呼び出し) | 0 | 1 | 1 | 1 | 3 |
| trace records | 3 | 6 | 10 | 8 | 16 |

- 全 spec で xmm0 は入力 `3ff8000000000000` (1.5) の素通しで、関数は戻った (SIGSEGV なし)。
- 件数 0 の経路は前報と同じ (No 1 だけが実行される)。
- No 2・6・7・9・10 は、前報 (0 hit) から 1 hit 以上へ変わった。No 6・7 は state 8 (pair あり)、No 9・10 は state 8 (pair なし) の分岐にある。

## 5. 判定に必要な残件 (実物の仮想 callee)

- S は `this+0x360`。呼び出し元 `function_180ca2450` の rcx が `this` で、`call 0x180da6e60` の直前に `add rcx, 0x360` を行う (dsm `0x180ca2450`–`0x180ca2484`)。A = `[S+0x10]` = `[this+0x370]`。
- `function_180ca2450` の呼び出し元は `function_1803dfc10` (`call 0x180ca2450` at `0x1803dfee3`)。`this` は `[rdi+0x90]+0xa080` の容器から `call 0x180c8b9f0` で取り出した要素である。
- したがって A の vtable と各 slot の実体は、起動後に構築される object graph の値で、静的な dsm や `.data` からは確定できない。
- 判定に必要な最小の追加情報は次の 3 つ。(a) A の vtable 値、(b) state 2 の `[A+8]` と `[VT+0x10]`、state 8 の `[A+0x30]` と `[VT'+0x10]` の実体、(c) それらの callee が、渡された pair・local struct の +0x08 や +0x10 を読むか。
- 候補 store の値 (harness の状態で確定したもの): No 2 は pair の +8 (harness では 0)、No 7 は pair のポインタ、No 9・10 は定数 0 (`xor ecx,ecx`)。No 6 の `r15` は loop 内で書き換わる値である (`0x180da6ed4` の `lea` で設定され、state 1 の経路 `0x180da7072`・`0x180da70f9` で A や別の値に変わる)。
- 前報の `2508` §4 の判定 (No 2・6・7・9・10 の読み先が静的に確定しない) は、このまま有効である。

## 6. 0x1803dee20 (受入 3) の再測定

- 関数本体 (`0x1803dee20`–`0x1803def2a`) は、`rax = this` (rdi) を返す初期化関数である。xmm0 を書く命令は本体に無い。呼び出し先 (`0x180ca3260`・`0x18100c760` の 2 回) が残した xmm0 が、native の出力になる。
- 本 runner (6973P-C・`43b8a780`): 既定 8/8 (入力素通し)、`FA_HEAP_FILL=0xcc` 8/8。`GLIBC_TUNABLES=glibc.cpu.hwcaps=-AVX2_Usable,-AVX512F_Usable,-AVX512VL_Usable,-AVX512BW_Usable,-ERMS,-AVX_Fast_Unaligned_Load` でも 8/8 (libc の ifunc 選択の仮説は支持されなかった)。
- 0/8 (native `0000…`) になった環境 (7763・9V74、前報) の条件は未特定。heap の埋め値が出力に入る経路 (どの load が xmm0 に残るか) も未確認。
- この関数の xmm0 比較は機能の検査にならない (戻り値は rax)。受入 3 の「揺れ」は、残り値の揺れとして扱うのが妥当。harness の変更で消えるかは未確認。

## 7. 既定経路の測定と差分

| 測定 | 結果 (`43b8a780`・6973P-C) |
|---|---|
| `FA_LOOP_N=0 fa_cmp 180da6e60 --n 8` | match 8 / mismatch 0 / err 0 |
| `FA_LOOP_N=1 fa_cmp 180da6e60 --n 8` | match 8 / mismatch 0 / err 0 |
| `fa_cmp 1803dee20 --n 8` (既定・`FA_HEAP_FILL=0xcc`・tunable) | 8/8 (各条件) |
| `bash tools/icall/diff/fa_sweep.sh 8 60` | 71.7 s (wall)。bit 一致 57 / crash・timeout 65 / wasm のみ err 8 / 値の不一致 1 (件数のみ記録。内訳は前報の追補 `9edd60a5` では 0x180da4030) |

差分確認: `git diff 43b8a780 HEAD -- tools/icall/diff tools/icall/fa_route_build.sh tools/ott/native` の出力は 0 行 (本付録の commit は `tools/icall/REPORT_APPENDIX_2695B.md` と `docs/DOC_MAP.md` だけ)。

## 8. 再現

```sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .            # tools/icall/work/ へ
bash tools/ott/native/build.sh                                       # libottnative.so
export FA_CORE="$PWD/tools/icall/work/rt_freshair-core/rw.dll"
FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh                   # fixed route
FA_LOOP_N=0 python3 tools/icall/diff/hit_180da6e60.py 180da6e60     # 件数 0: No 1・inc 点・出口が各 1
FA_LOOP_N=1 FA_ELEM_SPEC=2 python3 tools/icall/diff/hit_180da6e60.py 180da6e60     # No 2 が 1
FA_LOOP_N=1 FA_ELEM_SPEC=8 python3 tools/icall/diff/hit_180da6e60.py 180da6e60     # No 3・4・5・6・7 が各 1
FA_LOOP_N=1 FA_ELEM_SPEC=8n python3 tools/icall/diff/hit_180da6e60.py 180da6e60    # No 8・9・10 が各 1
FA_LOOP_N=3 FA_ELEM_SPEC=2,8,8n python3 tools/icall/diff/hit_180da6e60.py 180da6e60 # 全候補が 1 以上
python3 tools/icall/diff/fa_cmp.py 180da6e60 --n 8                   # 既定 (件数 0): 8/8
bash tools/icall/diff/fa_sweep.sh 8 60 | tail -1
```

## 9. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x180da6e60 の 6 件 (No 2・6・7・9・10) の判定: 仮想 callee (A の vtable と state 2・8 の callee の実体) が runtime の object graph に依存する | 判定 0 件。実行は確認済み (§4) | #2695 (分析と harness の残件のため子 issue は起票しない) |
| No 1 (cookie store) の検査が wasm で通る理由 | 前報から継続 | #2695 |
| 0x1803dee20: native の出力が 0/8 になる環境の条件 (残り xmm0 の出所) | 受入 3 未達。本 runner は 8/8 | #2695 |
| sweep の値の不一致 1 件の内訳 (本 run では件数のみ記録) | 本 issue の範囲外 | #2508 (既存の残件として引き継ぎ) |
