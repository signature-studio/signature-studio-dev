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

## 12. (付録) #1317 8 回目 run: git diff 731a232a HEAD -- tools/m11 の全文

```diff
diff --git a/tools/m11/m11_ov.c b/tools/m11/m11_ov.c
index de9d5907..becfc455 100644
--- a/tools/m11/m11_ov.c
+++ b/tools/m11/m11_ov.c
@@ -463,11 +463,12 @@ u64 function_40fb40(u64 self, u64 inst) {
     memset((void*)(uintptr_t)inst, 0, (size_t)(long long)(int)D(self - 0x80));
     Q(inst) = self;
 #if M11_INSTR_40F960
+    int chain_n = 0;
     fprintf(stderr, "[m11][40fb40] self=0x%llx inst=0x%llx size=%d\n", (unsigned long long)self, (unsigned long long)inst, (int)D(self - 0x80));
 #endif
     do {
 #if M11_INSTR_40F960
-        { static int chain_n = 0; if (++chain_n > 100000) { fprintf(stderr, "[m11][40fb40] chain>100000 cls=0x%llx\n", (unsigned long long)cls); abort(); } }
+        if (++chain_n > 100000) { fprintf(stderr, "[m11][40fb40] chain>100000 self=0x%llx cls=0x%llx\n", (unsigned long long)self, (unsigned long long)cls); abort(); }
 #endif
         u64 it = Q(cls - 0xc0);
         if (it) {
@@ -484,6 +485,9 @@ u64 function_40fb40(u64 self, u64 inst) {
         if (cls) cls = Q(cls);
     } while (cls);
     if (flag) ov_initinst_nested(self, inst);
+#if M11_INSTR_40F960
+    fprintf(stderr, "[m11][40fb40] chain_len=%d self=0x%llx\n", chain_n, (unsigned long long)self);
+#endif
     return inst;
 }
 
```
