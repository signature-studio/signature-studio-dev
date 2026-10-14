# 付録 2: icall #2695 (ICALL-81・第 2 報) — 0x180da6e60 の state 2・8 の harness と実行確認、0x1803dee20 の再測定

> 親: #2674。前報: `REPORT_APPENDIX_2695.md` (§10.6 の残件: state 2・8 の harness)。
> 測定 commit: wasm 系 (`fa_route_build.sh`・`fa_cmp`・`fa_sweep`) は `43b8a780` (`hit_180da6e60.py` に opt-in を追加した commit)。native trace (§4・§6) は `06c46b21` (`hit_180da6e60.py` の docstring と見出しだけを変えた commit。trace の値は `43b8a780` と同じ)。差分の出力は §7。
> 既知類型との関係: 該当なし (前報と同じ)。

## 1. 結論

- state 2・8 の harness で、件数 >0 の経路を native で実行できた。A の vtable を image 内の ret 系機械語で作り、要素ごとに state と pair を置く (§3)。**6 件の候補 (No 1・2・6・7・9・10) の store がすべて 1 hit 以上で実行された** (§4)。前報の「0 hit (未実行)」は解消した。
- **判定は依然 0 件**。候補 store の後段は、仮想 callee がその値を読むかで決まる。その callee は stub (`ret`) で、実物ではない。実物の vtable (A1 = `[this+0x370]`・A2 = `[this+0x480]`) は起動後の object graph の中にあり、静的には確定できない (§5)。
- 受入 1 (SIGSEGV の解消): 前報のまま部分。state 1・2・3・7・8 も stub で戻るようになった (件数 1 の各 state・件数 3 の複合)。ただし callee は stub。
- 受入 3 (0x1803dee20): 測定 (Intel Xeon 6973P-C) では 8/8 (入力素通し)。関数本体は xmm0 を書かず、出力は呼び出し先が残した xmm0 だった (§6)。0/8 と 8/8 の差の条件は未特定。

受入の状況: 受入 1 = 部分 (件数 0・1・3 の trace は実行。callee は stub) / 受入 2 = 部分 (6 件すべて実行を確認。判定は 0 件で、判定できない理由は §5) / 受入 3 = 部分 (xmm0 の出所は関数本体の外と説明できた。0/8 と 8/8 の差は §9 の未解決)。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| runner (wasm 系・`43b8a780` の測定) | Intel Xeon 6973P-C (4 vCPU・Ubuntu 24.04・gcc 13.3.0・glibc 2.39)。sweep 前 load 0.17・sweep 後 0.74 |
| runner (native trace・`06c46b21` の再測定) | AMD EPYC 9V74 (4 vCPU・load 0.40)。素材は `work-icall` の `tools/icall/work/rt_freshair-core` だけを展開 (6.7 s)。emcc が無い (`/opt/emsdk` 無し) ため wasm 側は再実行していない (§7) |
| 素材 (`43b8a780`) | `work-icall` のみ展開 (`tools/icall/work/`・`tar --zstd -xf` で 19.8 s)。`FA_CORE` = `tools/icall/work/rt_freshair-core/rw.dll`。emsdk は runner 既存の `[EMSDK]` (Emscripten 6.0.12 pin) を使用 |
| libottnative | `bash tools/ott/native/build.sh` で作成 |
| fixed route (`43b8a780`) | `FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh`: OK (6.9 s) |

## 3. harness (state 2・8 の実行)

`tools/icall/diff/hit_180da6e60.py` に opt-in を追加した。既定の `fa_cmp.py`・`fa_sweep.sh` は変えていない。

- A の vtable `VT` (0x100 B) を確保し、`A+0` = VT とする。`VT+0x08`・`VT+0x30` = `0x1803b3d2d` (`mov rax, rcx; ret`。rax に A を返す)。`VT+0x10` = `0x1803ba143` (`ret`。仮想 callee は何もしない)。
- 要素 i (stride `0x100138`) ごとに、64 B 節点 `node[0] = (E+0xbf)&~63` を nil (`0x4001`) にし、state (`+0x100108`) を spec の値にする。state 2 は `+0x100120` に 16 B の pair を置く。state 8 は、接尾辞 `n` が無ければ `+0x100130` に 16 B の pair を置く (`n` なら 0 のまま)。
- 環境変数 `FA_ELEM_SPEC` (要素ごとの state を `,` 区切り。`n` 接尾辞は pair を 0 にする)。要素数は `FA_LOOP_N` と一致させる。

判定に効く制限:

- 仮想 callee は `ret` のみで、値を読まない。実物の vtable ではないため、callee が pair や local struct を読むかは確定できない。
- O1 (state 2 の `[A+8]` の戻り) と X (state 8 の `[A+0x30]` の戻り) は A 自身になる。実物では別のオブジェクトである。
- wasm 側は stub の VA が lift 対象外のため使わない。hit は native 専用。

## 4. 結果 (trace・測定 commit `06c46b21`・件数 1 は要素 1 個)

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
- 件数 0 の経路は前報と同じ。候補 store は No 1 の 1 件だけが実行され、inc 点・出口も各 1 hit。
- `06c46b21` で 5 条件 (件数 0・spec `2`・`8`・`8n`・`2,8,8n`) を再実行し、上の表の全 VA の hit 数と trace records が一致した (xmm0 は `3ff8000000000000`)。
- No 2・6・7・9・10 は、前報 (0 hit) から 1 hit 以上へ変わった。No 6・7 は state 8 (pair あり)、No 9・10 は state 8 (pair なし) の分岐にある。

## 5. 判定に必要な残件 (実物の仮想 callee)

- 呼び出し元 `function_180ca2450` は `0x180da6e60` を 2 回呼ぶ (`objdump -d` の `rw.dll`・`0x180ca2450`–`0x180ca2493`)。引数 S (rcx) は 2 つある。
  - S1 = `this+0x360`: `0x180ca2466` で無条件に呼ぶ (直前の `add rcx, 0x360` at `0x180ca245f`)。A1 = `[S1+0x10]` = `[this+0x370]`。
  - S2 = `this+0x470`: `0x180ca2484` で条件付きに呼ぶ (直前の `lea rcx,[rbx+0x470]` at `0x180ca247b`)。条件は `cmp [this+0x2d0],[this+0x328]` (at `0x180ca2472`) が不一致のときで、一致なら `je 0x180ca2489` で飛ばす。A2 = `[S2+0x10]` = `[this+0x480]`。
- 呼び出し元の経路 (`function_1803dfc10` → `function_180ca2450`、`call 0x180ca2450` at `0x1803dfee3`) は前報のとおり。
- 判定に必要な情報は S ごとに違う。
  - S1 (常に呼ばれる): (a1) A1 の vtable 値、(b1) state 2 の `[A1+8]` と `[VT+0x10]`、state 8 の `[A1+0x30]` と `[VT'+0x10]` の実体、(c1) それらの callee が、渡された pair・local struct の +0x08 や +0x10 を読むか。
  - S2 (条件付き): (d2) `[this+0x2d0]` と `[this+0x328]` の値 (この呼び出しが実行されるか)、(a2) A2 の vtable 値、(b2)・(c2) は S1 と同じ形。
- 候補 store の値 (harness の状態で確定したもの): No 2 は pair の +8 (harness では 0)、No 7 は pair のポインタ、No 9・10 は定数 0 (`xor ecx,ecx`)。No 6 の `r15` は loop 内で書き換わる値である (`0x180da6ed4` の `lea` で設定され、state 1 の経路 `0x180da7072`・`0x180da70f9` で A や別の値に変わる)。
- したがって A1・A2 の vtable と各 slot の実体は、起動後に構築される object graph の値で、静的な dsm や `.data` からは確定できない。
- 前報の `2508` §4.2 の判定保留 (No 1・2・6・7・9・10 の読み先が静的に確定しない) は、このまま有効である。

## 6. 0x1803dee20 (受入 3) の再測定

- 関数本体 (`0x1803dee20`–`0x1803def2a`) は、`rax = this` (rdi) を返す初期化関数である。xmm0 を書く命令は本体に無い。呼び出し先 (`0x180ca3260`・`0x18100c760` の 2 回) が残した xmm0 が、native の出力になる。
- 測定 (6973P-C・`43b8a780`): 既定 8/8 (入力素通し)、`FA_HEAP_FILL=0xcc` 8/8。`GLIBC_TUNABLES=glibc.cpu.hwcaps=-AVX2_Usable,-AVX512F_Usable,-AVX512VL_Usable,-AVX512BW_Usable,-ERMS,-AVX_Fast_Unaligned_Load` でも 8/8 (libc の ifunc 選択の仮説は支持されなかった)。
- 0/8 (native `0000…`) になった環境 (7763・9V74、前報) の条件は未特定。heap の埋め値が出力に入る経路 (どの load が xmm0 に残るか) も未確認。
- この関数の xmm0 比較は機能の検査にならない (戻り値は rax)。受入 3 の「揺れ」は、残り値の揺れとして扱うのが妥当。harness の変更で消えるかは未確認。

## 7. 既定経路の測定と差分

| 測定 | 結果 (`43b8a780`・6973P-C) |
|---|---|
| `FA_LOOP_N=0 fa_cmp 180da6e60 --n 8` | match 8 / mismatch 0 / err 0 |
| `FA_LOOP_N=1 fa_cmp 180da6e60 --n 8` | match 8 / mismatch 0 / err 0 |
| `fa_cmp 1803dee20 --n 8` (既定・`FA_HEAP_FILL=0xcc`・tunable) | 8/8 (各条件) |
| `bash tools/icall/diff/fa_sweep.sh 8 60` | 71.7 s (wall)。bit 一致 57 / crash・timeout 65 / wasm のみ err 8 / 値の不一致 1 (件数のみ記録。本 run では VA を特定していない。内訳は前報の追補 `9edd60a5` では 0x180da4030) |
| `python3 tools/icall/diff/xmm0_probe.py 180da6e60,1803dee20 --n 8` (#2695 の検証方法) | 未実行。`xmm0_probe.py` は wasm 側 (`F.wasm_run`) を呼び、本 run は emcc が無いため動かせない。1803dee20 の判定は上の `fa_cmp 1803dee20` (`43b8a780`) で代替した |

差分確認 (コード差分の出力):

- wasm 系の測定 commit `43b8a780` から native trace の測定 commit `06c46b21` まで。`hit_180da6e60` を参照するのは `hit_180da6e60.py` と付録だけ (`grep -rln hit_180da6e60 tools docs .github`)。`fa_cmp.py`・`fa_sweep.sh`・`fa_route_build.sh` は読まないため、wasm 系の値は `43b8a780` のまま有効。

```diff
diff --git a/tools/icall/diff/hit_180da6e60.py b/tools/icall/diff/hit_180da6e60.py
index 6de505b2..502384e5 100644
--- a/tools/icall/diff/hit_180da6e60.py
+++ b/tools/icall/diff/hit_180da6e60.py
@@ -2,9 +2,11 @@
 """hit_180da6e60.py [FN_VA] — native 1 回実行で、候補命令 (CANDS) が実行されたかを int3 トレース (ott_trace_install) で記録して表示する。
 初期化は fa_cmp.init_native (件数は FA_LOOP_N)。判定は候補 VA の hit の有無のみ (値は見ない)。
 FA_ELEM_STATE=S (件数 >0 のとき) は要素 0 の state (+0x100108) を S にする。state 0 は 0x180da41a0 を呼ぶ。
+FA_ELEM_SPEC=S0,S1,... (件数と同数。接尾辞 n は state 8 の pair を 0 にする) は要素ごとの state と pair を置く (setup_elems)。
 ott_call_cov の単歩 coverage は窓 (IMG_BASE + 0x308000) 外の VA を記録しないため使わない。
 用法: FA_CORE=... FA_LOOP_N=0 python3 tools/icall/diff/hit_180da6e60.py [180da6e60]
-      FA_CORE=... FA_LOOP_N=1 FA_ELEM_STATE=2 python3 tools/icall/diff/hit_180da6e60.py [180da6e60]"""
+      FA_CORE=... FA_LOOP_N=1 FA_ELEM_STATE=2 python3 tools/icall/diff/hit_180da6e60.py [180da6e60]
+      FA_CORE=... FA_LOOP_N=3 FA_ELEM_SPEC=2,8,8n python3 tools/icall/diff/hit_180da6e60.py [180da6e60]"""
 import sys, os, ctypes, struct
 HERE = os.path.dirname(os.path.abspath(__file__))
 sys.path.insert(0, HERE)
@@ -42,13 +44,16 @@ def main():
     va = int(sys.argv[1] if len(sys.argv) > 1 else '180da6e60', 16)
     N.load(F.FA)
     gpr = F.init_native(va)
+    st0 = 'zero'
     if os.environ.get('FA_ELEM_SPEC') and F.LOOP_CNT > 0:
         spec = os.environ['FA_ELEM_SPEC'].split(',')
         assert len(spec) == F.LOOP_CNT, 'FA_ELEM_SPEC の要素数は FA_LOOP_N と一致させる'
         setup_elems(gpr, spec)
+        st0 = spec[0]
     if os.environ.get('FA_ELEM_STATE') and F.LOOP_CNT > 0:
         B = N.u64(gpr[0] + 0xb8)
         N.wr(B + 0x100108, struct.pack('<I', int(os.environ['FA_ELEM_STATE'])))
+        st0 = os.environ['FA_ELEM_STATE']
     vas = [a for a, _ in CANDS]
     N._lib.ott_trace_install(ctypes.cast((ctypes.c_uint64 * len(vas))(*vas), ctypes.c_void_p), len(vas))
     N._lib.ott_trace_enable(1)
@@ -62,7 +67,7 @@ def main():
         rec = struct.unpack_from('<11Q', buf, i * 88)
         hits[rec[0]] = hits.get(rec[0], 0) + 1
     print('fn %#x xmm0 %016x (件数 FA_LOOP_N=%d・要素 0 state=%s・FA_ELEM_SPEC=%s) trace records %d' % (
-        va, x0, F.LOOP_CNT, os.environ.get('FA_ELEM_STATE', 'zero'), os.environ.get('FA_ELEM_SPEC', '-'), n))
+        va, x0, F.LOOP_CNT, st0, os.environ.get('FA_ELEM_SPEC', '-'), n))
     for a, name in CANDS:
         print('%#x %-20s hits %d' % (a, name, hits.get(a, 0)))
 
```

- `git diff 06c46b21 HEAD -- tools/icall/diff tools/icall/fa_route_build.sh tools/ott/native` の出力は 0 行 (本付録の commit は `tools/icall/REPORT_APPENDIX_2695B.md` と `docs/DOC_MAP.md` だけ)。

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
| 0x180da6e60 の 6 件 (No 1・2・6・7・9・10) の判定: 仮想 callee (S1・S2 それぞれの A の vtable と state 2・8 の callee の実体、S2 の条件値) が runtime の object graph に依存する | 判定 0 件。実行は確認済み (§4) | #2695 (分析と harness の残件のため子 issue は起票しない) |
| No 1 (cookie store) の検査が wasm で通る理由 | 前報から継続 | #2695 |
| 0x1803dee20: native の出力が 0/8 になる環境の条件 (残り xmm0 の出所) | 受入 3 の残件。測定 (6973P-C) は 8/8 | #2695 |
| sweep の値の不一致 1 件の VA (本 run の sweep は件数のみ記録し、VA は特定していない。前報追補 `9edd60a5` の内訳は 0x180da4030) | 本 issue の範囲外 | #2708 (ICALL-83・0x180da4030 の xmm0 脱落) |
