# REPORT_1317 付録 (分割移動)

`REPORT_1317.md` の 250 行上限のため、§10 (#1786 run) を無変更で移動した。

## 10. 追補 (2026-10-14・#1786 run): `0x40fb40` 計装の試行と判明事項

- 測定 commit: `381dd7c2` (origin/main)。コード差分は無し (計装は試行後に破棄)。
- 素材: fl-win64 (`$RUNNER_TEMP/extracted`)・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff を展開。capstone / pefile を pip で補った。
- IR (ON, `M11_M2P=1`): `m11_gen_ir2.sh` 51 s rc=0 (`F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=36 errors=0`)。build 25 s rc=0 (`wasm-ld signature mismatch: 0, undefined symbol: 0`)。load 0.5 前後。
- 再現 (上限 60 s): `0..829`+880 = rc=0 / 1.74 s。`0..830`+880 = rc=124 / 60.02 s。境界は §6〜8 と一致。

### 判明事項 (停止候補 `0x40fb40` は build に存在しない)

- `boot_final.ll` / `boot_final3.ll` に `function_40fb40`・`function_40f960` の定義・呼出しが無い。間接 call 表 `m11_disp_tab` にも `4258624` (`0x40fb40`)・`4258144` (`0x40f960`) の登録が無い。
- そのため、§4a・§6 の「`0xf960` → `0x40f960` → `0x40fb40` の連鎖」は、IR 上では辿れる経路ではない。`0xf960` の icall 値 (変換前) も IR から解決できていない。
- 入口 hook (`M11_INSTR_40FB40` 相当、`m11_post.py` の wrapper) を試したが、wrapper を入れる対象が IR に無いため 1 回も発火しなかった (`0..830`+880 の stderr は 0 行)。計装は測定対象に届かないので、コードは残さず破棄した。
- 従って、§6 の「`0x40fb40` の連鎖走査の循環」は**仮説のまま**。循環の有無は未計測。

### 次の一手 (起票先: 本 issue #1317)

- `0xf960` (icall 値) が IR のどの関数に解決されるかを、`m11_icall` の `tkey` 変換 (`target + 0x400000 - M11_LB_BASE`) と `m11_disp_tab` の突合で特定する。`0x40f960` が表に無い理由 (lift 漏れ・別 VA への写像) を先に確定する。
- 解決先が確定するまで、#1786 の計装 (連鎖の循環検出) は着手しない。

## 12. (付録) #1317 8 回目 run: git diff b36d3b5f e7c5c062 -- tools/m11/m11_ov.c tools/m11/m11_post.py tools/m11/m11_build.sh tools/m11/m11_rt.c tools/m11/shimx_link/probe_trace_unit.mjs tools/m11/shimx_link/probe_unit23.mjs の全文

diff の範囲: `b36d3b5f..e7c5c062` (`b36d3b5f` の後の main 取り込み HEAD。測定 commit は `58e0126d`。`e7c5c062..58e0126d` の差分は REPORT_1317.md §12 に記載)。

```diff
diff --git a/tools/m11/m11_build.sh b/tools/m11/m11_build.sh
index 4dc5ef12..e3fde08a 100755
--- a/tools/m11/m11_build.sh
+++ b/tools/m11/m11_build.sh
@@ -25,7 +25,7 @@ M11_OV_INSTR="${M11_OV_INSTR:-$M11_INSTR_413060}"   # #1701: ov.o をコンパ
 M11_LINK_INSTR="${M11_LINK_INSTR:-$M11_INSTR_413060}"   # #1701: リンク時の EXPORTS (_m11_dest_obs_* 等) を足すか。既定は M11_INSTR_413060 と同じ
 M11_DEST_READ="${M11_DEST_READ:-1}"   # #944: 0 = 413060 後の dest 読出し (指紋) を止める。読出しが挙動を変えるかの切り分け用。既定 1
 M11_FIX_535BF2="${M11_FIX_535BF2:-0}"   # #714: 1 = m11_ov.c の function_535c11/535bf2 転記 (IR 未定義 535c2e・境界 535c11 の再現); 0 = lift 版 (既定)
-CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=$M11_LB_BASE -DM11_OV_CLASSCREATE=$M11_OV_CLASSCREATE -DM11_OV_414AD0=$M11_OV_414AD0 -DM11_FIX_652500=$M11_FIX_652500 -DM11_OV_413060=$M11_OV_413060 -DM11_NEG_413060=$M11_NEG_413060 -DM11_DEST_READ=$M11_DEST_READ -DM11_INSTR_413060=$M11_INSTR_413060 -DM11_FIX_535BF2=$M11_FIX_535BF2 -DM11_INSTR_K12=${M11_INSTR_K12:-0} -DM11_INSTR_40FF70=${M11_INSTR_40FF70:-0} -DM11_INSTR_40F960=${M11_INSTR_40F960:-0} -DM11_TRACE_ISOLATE=${M11_TRACE_ISOLATE:-1} -DM11_ENTRY_PROBE=${M11_ENTRY_PROBE:-0} -DM11_NOVCALL=${M11_NOVCALL:-0}"
+CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=$M11_LB_BASE -DM11_OV_CLASSCREATE=$M11_OV_CLASSCREATE -DM11_OV_414AD0=$M11_OV_414AD0 -DM11_FIX_652500=$M11_FIX_652500 -DM11_OV_413060=$M11_OV_413060 -DM11_NEG_413060=$M11_NEG_413060 -DM11_DEST_READ=$M11_DEST_READ -DM11_INSTR_413060=$M11_INSTR_413060 -DM11_FIX_535BF2=$M11_FIX_535BF2 -DM11_INSTR_K12=${M11_INSTR_K12:-0} -DM11_INSTR_40FF70=${M11_INSTR_40FF70:-0} -DM11_INSTR_40F960=${M11_INSTR_40F960:-0} -DM11_INSTR_40FFE0=${M11_INSTR_40FFE0:-0} -DM11_TRACE_ISOLATE=${M11_TRACE_ISOLATE:-1} -DM11_ENTRY_PROBE=${M11_ENTRY_PROBE:-0} -DM11_NOVCALL=${M11_NOVCALL:-0} -DM11_RT_PADPRE=${M11_RT_PADPRE:-0} -DM11_RT_PADPOST=${M11_RT_PADPOST:-0} -DM11_RT_EMPTY=${M11_RT_EMPTY:-0}"
 # image 終端 (SizeOfImage 0x18c0000) + LB_BASE が GLOBAL_BASE (0x10000000) 以内であること
 python3 - <<PYEOF
 import sys
@@ -106,8 +106,9 @@ S_INSTR="$M11_INSTR_413060${M11_PROBE_VARIANT:+:$M11_PROBE_VARIANT}"   # #1542:
 if [ "$(cat work/instr_413060.stamp 2>/dev/null || echo none)" != "$S_INSTR" ]; then rm -f work/boot_final3.ll; fi
 echo "$S_INSTR" > work/instr_413060.stamp
 # #882: 40ff70 観測 probe の有無が変わったら post 結果を無効化 (stamp)
-if [ "$(cat work/instr_40ff70.stamp 2>/dev/null || echo none)" != "${M11_INSTR_40FF70:-0}" ]; then rm -f work/boot_final3.ll; fi
-echo "${M11_INSTR_40FF70:-0}" > work/instr_40ff70.stamp
+S_INSTR40="${M11_INSTR_40FF70:-0}:${M11_INSTR_40FFE0:-0}"
+if [ "$(cat work/instr_40ff70.stamp 2>/dev/null || echo none)" != "$S_INSTR40" ]; then rm -f work/boot_final3.ll; fi
+echo "$S_INSTR40" > work/instr_40ff70.stamp
 echo "${M11_SIGFIX_RECOVER:-0}" > work/sigfix_recover.stamp
 if [ ! -f work/boot_final3.ll ] || [ work/boot_final.ll -nt work/boot_final3.ll ] || [ m11_post.py -nt work/boot_final3.ll ] || [ m11_argrecover.py -nt work/boot_final3.ll ]; then
   # M11_SIGFIX_RECOVER=1 (#131): sigfix の 0 詰め site を機械語突合し、定数代入が確定する引数だけ復元 (m11_argrecover.py)
@@ -142,7 +143,7 @@ cc() { # cc <src> <obj> [extra deps...]
 }
 # 別 TU (tools/shim, m11_rt/ov/win) が定義する Win32 API は winstubs から除外 (duplicate symbol 回避)
 for f in heap failfast file timer sync; do cc ../shim/src/$f.c work/obj/shim_$f.o; done
-S_NEG="$M11_NEG_413060-$M11_DEST_READ-$M11_INSTR_413060-rt$M11_RT_INSTR"
+S_NEG="$M11_NEG_413060-$M11_DEST_READ-$M11_INSTR_413060-rt$M11_RT_INSTR$( [ "${M11_RT_PADPRE:-0}${M11_RT_PADPOST:-0}${M11_RT_EMPTY:-0}" = 000 ] || echo "-pre${M11_RT_PADPRE:-0}-post${M11_RT_PADPOST:-0}-empty${M11_RT_EMPTY:-0}" )"   # #1952: 対照 knob (既定 0 のときは従来の stamp と同一)
 if [ "$(cat work/neg_413060.stamp 2>/dev/null || echo none)" != "$S_NEG" ]; then rm -f work/obj/rt.o; fi
 echo "$S_NEG" > work/neg_413060.stamp
 # #1176: work-m11 同梱の rt.o/win.o は古い snapshot のことがある (mtime だけでは判定できない: 同梱 obj が source より新しく見える)。
@@ -184,11 +185,11 @@ echo "${M11_INSTR_K12:-0}" > work/ov_instr_k12.stamp
 if [ "$(cat work/ov_trace_isolate.stamp 2>/dev/null || echo 1)" != "${M11_TRACE_ISOLATE:-1}" ]; then rm -f work/obj/ov.o; fi
 echo "${M11_TRACE_ISOLATE:-1}" > work/ov_trace_isolate.stamp
 # #882: 40ff70 観測 probe の ON/OFF で古い ov.o を再リンクしない
-if [ "$(cat work/ov_instr_40ff70.stamp 2>/dev/null || echo none)" != "${M11_INSTR_40FF70:-0}" ]; then rm -f work/obj/ov.o; fi
+if [ "$(cat work/ov_instr_40ff70.stamp 2>/dev/null || echo none)" != "$S_INSTR40" ]; then rm -f work/obj/ov.o; fi
 # #1894: entry probe (417b70 の ov 版) の ON/OFF で古い ov.o を再リンクしない
 if [ "$(cat work/ov_entry_probe.stamp 2>/dev/null || echo 0)" != "${M11_ENTRY_PROBE:-0}" ]; then rm -f work/obj/ov.o; fi
 echo "${M11_ENTRY_PROBE:-0}" > work/ov_entry_probe.stamp
-echo "${M11_INSTR_40FF70:-0}" > work/ov_instr_40ff70.stamp
+echo "$S_INSTR40" > work/ov_instr_40ff70.stamp
 if [ "$(cat work/ov_instr_40f960.stamp 2>/dev/null || echo none)" != "${M11_INSTR_40F960:-0}" ]; then rm -f work/obj/ov.o; fi
 echo "${M11_INSTR_40F960:-0}" > work/ov_instr_40f960.stamp
 echo "$M11_FIX_535BF2" > work/ov_535bf2.stamp
diff --git a/tools/m11/m11_ov.c b/tools/m11/m11_ov.c
index becfc455..20295e91 100644
--- a/tools/m11/m11_ov.c
+++ b/tools/m11/m11_ov.c
@@ -988,6 +988,23 @@ void m11_p144_obs(unsigned long long p) {
 }
 #endif
 
+/* #882 計測専用 (M11_INSTR_40FFE0=1 のときだけ有効): function_40ffe0 の入口で arg1 と、40ff70 へ渡る値 v = [arg1]、
+ * v-0x90 (p-144) の値を stderr に出す。線形メモリ外は読まない (address 0 は線形メモリ内なので読む)。既定 0 では何も入らない。 */
+#ifndef M11_INSTR_40FFE0
+#define M11_INSTR_40FFE0 0
+#endif
+#if M11_INSTR_40FFE0
+static int g_ffe0_n;
+void m11_ffe0_obs(unsigned long long a) {
+    unsigned long long heap = (unsigned long long)__builtin_wasm_memory_size(0) * 65536ULL;
+    unsigned long long v = 0, p144 = 0;
+    if (a + 8 <= heap) v = *(volatile unsigned long long*)(uintptr_t)a;
+    if (v >= 0x90 && v - 0x90 + 8 <= heap) p144 = *(volatile unsigned long long*)(uintptr_t)(v - 0x90);
+    if (g_ffe0_n++ < 16)
+        fprintf(stderr, "[m11][ffe0] #%d arg1=0x%llx v=[arg1]=0x%llx p-144=0x%llx\n", g_ffe0_n, a, v, p144);
+}
+#endif
+
 /* ---- #483: TDictionary<K,V> (Generics.Collections) の Add/GetItem が全て「重複キー」と誤判定される原因 3 点の C 転記 ----
  * 8cc190 (Add) は FComparer = TEqualityComparer<K>.Default (53df80 → 479b40 _LookupVtableInfo) の GetHashCode/Equals を使う.
  *   479b40  `movzx rcx,byte [rbx]` (TypeInfo.Kind) の deref 脱落 (D4) で Kind=0 固定, `test cl,2; call rax` (getter 呼出し) 脱落 (D15)
diff --git a/tools/m11/m11_post.py b/tools/m11/m11_post.py
index 0bf86ad8..c1a86ca7 100644
--- a/tools/m11/m11_post.py
+++ b/tools/m11/m11_post.py
@@ -226,9 +226,12 @@ if os.environ.get('M11_INSTR_413060') == '1':   # #944: 計測専用。既定 0
     PROBES[0x413060] = 'function_413060'   # index 8 (末尾追加; 既存 index 不変)
 if os.environ.get('M11_INSTR_40FF70') == '1':   # #882: 計測専用。wrapper で m11_p144_obs を呼ぶ (PROBES には入れず、index を変えない)
     PROBES[0x40ff70] = 'function_40ff70'
+if os.environ.get('M11_INSTR_40FFE0') == '1':   # #882: 計測専用。40ff70 の caller (arg1 の出所) を観測する
+    PROBES[0x40ffe0] = 'function_40ffe0'
 probe_wrappers = []
 # #882 計測専用: function_40ff70 の入口で p-144 (arg1-0x90) と先頭ノードを観測する (既定 0 では入れない)
 M11_INSTR_40FF70 = os.environ.get('M11_INSTR_40FF70') == '1'
+M11_INSTR_40FFE0 = os.environ.get('M11_INSTR_40FFE0') == '1'
 
 
 # #1542 計測専用: 413060 の計測 hook を 3 点に分けて単発で切り分ける (既定 '' は従来どおり)
@@ -258,6 +261,8 @@ def weaken(m):
             w += ['  call void @m11_probe(i32 %d)' % idx]
         if va == 0x40ff70 and M11_INSTR_40FF70:
             w += ['  call void @m11_p144_obs(i64 %p0)']
+        if va == 0x40ffe0 and M11_INSTR_40FFE0:
+            w += ['  call void @m11_ffe0_obs(i64 %p0)']
         if rt == 'void':
             w += ['  call void @%s__lifted(%s)' % (nm, clist), '  ret void']
         else:
@@ -357,7 +362,7 @@ for (nm, ret, args) in fns:
 open(dst.replace('.ll', '_sigs.h'), 'w').write('\n'.join(hdr) + '\n')
 ent = ', '.join('{ i32, ptr } { i32 %d, ptr @m11_tr_%s }' % (va, nm) for va, nm in tab)
 # 計測時 (M11_INSTR_413060=1) のみ PROBES に 0x413060 が入り、dest 観測の宣言が出る
-tail = ['', 'declare void @m11_probe(i32)'] + (['declare void @m11_dest_obs(i64)'] if 0x413060 in PROBES and M11_PROBE_VARIANT not in ('nodecl', 'noren') else []) + (['declare void @m11_p144_obs(i64)'] if M11_INSTR_40FF70 else []) + probe_wrappers + ['', '; ---- m11_post.py: 間接 call トランポリン + VA 表 ----']
+tail = ['', 'declare void @m11_probe(i32)'] + (['declare void @m11_dest_obs(i64)'] if 0x413060 in PROBES and M11_PROBE_VARIANT not in ('nodecl', 'noren') else []) + (['declare void @m11_p144_obs(i64)'] if M11_INSTR_40FF70 else []) + (['declare void @m11_ffe0_obs(i64)'] if M11_INSTR_40FFE0 else []) + probe_wrappers + ['', '; ---- m11_post.py: 間接 call トランポリン + VA 表 ----']
 tail.extend(tr)
 tail.append('@m11_disp_n = constant i32 %d' % len(tab))
 tail.append('@m11_disp_tab = constant [%d x { i32, ptr }] [%s]' % (len(tab), ent))
diff --git a/tools/m11/m11_rt.c b/tools/m11/m11_rt.c
index 14857ce4..9928b03a 100644
--- a/tools/m11/m11_rt.c
+++ b/tools/m11/m11_rt.c
@@ -246,9 +246,26 @@ EMSCRIPTEN_KEEPALIVE double m11_probe_count(int i) { return (i >= 0 && i < PROBE
 #define M11_INSTR_413060 0
 #endif
 #if M11_INSTR_413060
+/* #1952 対照用 (既定 0 = 無効): PADPRE は g_dest_h より前の静的領域 (配置と量が変わる)・PADPOST は後ろ (量だけ変わる)。
+ * EMPTY=1 は m11_dest_obs の本体だけ空にする (関数と静的データは残す)。 */
+#ifndef M11_RT_PADPRE
+#define M11_RT_PADPRE 0
+#endif
+#ifndef M11_RT_PADPOST
+#define M11_RT_PADPOST 0
+#endif
+#ifndef M11_RT_EMPTY
+#define M11_RT_EMPTY 0
+#endif
+#if M11_RT_PADPRE
+static unsigned char g_pad_pre[M11_RT_PADPRE] __attribute__((used));
+#endif
 static unsigned long long g_dest_h = 1469598103934665603ULL, g_dest_n;
 #define M11_DEST_REC_MAX 512
 static unsigned long long g_rec_st[M11_DEST_REC_MAX], g_rec_len[M11_DEST_REC_MAX], g_rec_rc[M11_DEST_REC_MAX], g_rec_h[M11_DEST_REC_MAX];
+#if M11_RT_PADPOST
+static unsigned char g_pad_post[M11_RT_PADPOST] __attribute__((used));
+#endif
 #ifndef M11_NEG_413060
 #define M11_NEG_413060 0
 #endif
@@ -256,6 +273,9 @@ static unsigned long long g_rec_st[M11_DEST_REC_MAX], g_rec_len[M11_DEST_REC_MAX
 #define M11_DEST_READ 1
 #endif
 void m11_dest_obs(unsigned long long dest) {
+#if M11_RT_EMPTY
+    (void)dest; return;
+#endif
 #if M11_NEG_413060
     *(volatile unsigned long long*)(uintptr_t)dest += 0x40;
 #endif
diff --git a/tools/m11/shimx_link/probe_trace_unit.mjs b/tools/m11/shimx_link/probe_trace_unit.mjs
new file mode 100644
index 00000000..e46fa92e
--- /dev/null
+++ b/tools/m11/shimx_link/probe_trace_unit.mjs
@@ -0,0 +1,24 @@
+// unit idx (0 始まり) の直前まで unit 1..idx を順に実行し、その unit の trace (m11 icall / UStrAsg / Halt0 と shimx icall-miss) を出す (SHX-T9f #1985)。
+//   SHIMX_TRACE=1 node probe_trace_unit.mjs <m11_sx_*.cjs | m11_boot.cjs 絶対パス> [unit_index 既定 22]
+//   M11 の素材は tools/m11/work/ (絶対パスは M11 の位置から解決)。
+import fs from 'fs';
+const cjs = process.argv[2];
+const idx = Number(process.argv[3] ?? 22);
+const M11 = new URL('../', import.meta.url).pathname;
+const m2 = await import(cjs);
+const image = fs.readFileSync(M11 + 'work/m11_image.bin');
+const errs = [];
+const mod = await (m2.default || m2)({ printErr: (s) => { errs.push(String(s)); } });
+mod.HEAPU8.set(image, 0);
+mod._m11_set_survey(1);
+const sp = mod._emscripten_stack_get_current();
+try { mod._m11_boot_enter(0n, 1n); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) throw e; mod.__emscripten_stack_restore(sp); }
+const sp0 = mod._emscripten_stack_get_current();
+for (let i = 0; i < idx; i++) { try { mod._m11_call_unit(i); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) { try { mod.__emscripten_stack_restore(sp0); } catch (_) {} } } }
+mod._m11_set_trace(1); if (mod._shimx_set_trace) mod._shimx_set_trace(1);
+const e0 = errs.length;
+let res;
+try { res = 'ret=' + mod._m11_call_unit(idx); }
+catch (e) { res = 'exc=' + (e && e.m11_dllmain_done !== undefined ? 'halt0' : String((e && e.message) || e).split('\n')[0]); }
+console.log(res);
+for (const l of errs.slice(e0)) console.log(l.slice(0, 300));
diff --git a/tools/m11/shimx_link/probe_unit23.mjs b/tools/m11/shimx_link/probe_unit23.mjs
index b323c877..fbea2a01 100644
--- a/tools/m11/shimx_link/probe_unit23.mjs
+++ b/tools/m11/shimx_link/probe_unit23.mjs
@@ -1,4 +1,4 @@
-// unit 23 (index 22) の icall miss・slot (0x15f10e0)・GetProcAddress 呼出し数を、前処理 unit 1..idx-1 の後で 1 回実測する probe (SHX-T9e #1607).
+// unit 23 (index 22) の icall miss・slot (LVA 0x11f10e0 = VA 0x15f10e0)・GetProcAddress 呼出し数を、前処理 unit 1..idx-1 の後で 1 回実測する probe (SHX-T9e #1607).
 //   node probe_unit23.mjs <m11_sx_*.cjs | m11_boot.cjs> <unit_index (0 始まり, 既定 22)>
 //   素材: tools/m11/work/ (work-m11) と tools/m11/work/shimx_link/m11_sx_trace_soft_fix.cjs (build.sh --trace --soft --fix)
 import fs from 'fs';
@@ -18,7 +18,7 @@ const sp = mod._emscripten_stack_get_current();
 try { mod._m11_boot_enter(0n, 1n); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) throw e; mod.__emscripten_stack_restore(sp); }
 const sp0 = mod._emscripten_stack_get_current();
 // survey_trace.mjs と同じく、対象 unit の前の unit 0..idx-1 を先に順に実行する (状態を揃えるため)
-const slotPre = () => { const dv = new DataView(mod.HEAPU8.buffer); return dv.getBigUint64(0x15f10e0, true); };
+const slotPre = () => { const dv = new DataView(mod.HEAPU8.buffer); return dv.getBigUint64(0x11f10e0, true); };
 const pre = (typeof mod._sxt_n === 'function') ? mod._sxt_n() : 0;
 const gpIdx = []; for (let i = 0; i < pre; i++) { const nm = mod.UTF8ToString(mod._sxt_name(i)); if (nm === 'GetProcAddress' || nm === 'GetModuleHandleW') gpIdx.push([nm, i]); }
 const gpc = () => gpIdx.map(([nm, i]) => nm + '=' + mod._sxt_count(i)).join(' ');
@@ -28,8 +28,8 @@ for (let i = 0; i < idx; i++) {
   const s1 = slotPre();
   if (s0 !== s1 || i >= idx - 3) console.log('PRE|unit', i + 1, 'slot', '0x' + s1.toString(16), 'gp', gpc());
 }
-// .bss slot 0x15f10e0 (LVA = RVA, M11_LB_BASE=0)。0 なら fallback 0x457860 に流れる
-const slotVal = () => { const dv = new DataView(mod.HEAPU8.buffer); return Number(dv.getBigUint64(0x15f10e0, true)).toString(16); };
+// .bss slot: LVA 0x11f10e0 (= VA 0x15f10e0, LVA = VA - 0x400000)。0 なら fallback 0x457860 に流れる
+const slotVal = () => { const dv = new DataView(mod.HEAPU8.buffer); return Number(dv.getBigUint64(0x11f10e0, true)).toString(16); };
 console.log('SLOT_BEFORE_UNIT|0x' + slotVal());
 const e0 = errs.length;
 const HAS = typeof mod._sxt_n === 'function';
```
