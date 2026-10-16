# tools/plugins/p0c REPORT 付録 M2 — #5832 の鮮度の証跡 (付録 M §4 の差分全文)

測定 commit = `8e263e380` (emcc 版 `run.sh` の再実行。付録 M §1.2)。 本付録は `git diff ce3872372 8e263e380 -- tools/plugins/p0c ":!tools/plugins/p0c/REPORT*"` の出力 (コード・harness の差分のみ。REPORT 文書の差分は自己参照になるため除く)。 測定値は含まない。 差分中の repo 外絶対パス 1 箇所は `[EMSDK 参照]` に置換した (`docs/REFERENCES.md` の `[EMSDK]`)。

```diff
diff --git a/tools/plugins/p0c/f80_lower.py b/tools/plugins/p0c/f80_lower.py
index 16db8ab05..668fede35 100644
--- a/tools/plugins/p0c/f80_lower.py
+++ b/tools/plugins/p0c/f80_lower.py
@@ -1123,7 +1123,8 @@ def _f80b_to_image(ind, dst, src, p):
 
 def _f80b_from_image(ind, dst, src, p):
     """x87 80-bit 像 i80 src → double (dst)。 仮数 64 bit を 53 bit に最近接偶数丸め。
-    double の指数範囲外は inf / 0 に丸める (subnormal の結果は 0 に落とす: 精度の制限)。"""
+    subnormal の結果は 2^-1074 の格子に最近接偶数丸めする (丸め位置は carry 前の指数 E0 で決める)。
+    double の指数上限を超えるものは inf、下限を下回るものは 0 に丸める。"""
     L = []
 
     def o(name, rhs):
@@ -1153,12 +1154,12 @@ def _f80b_from_image(ind, dst, src, p):
     o(p + 'E0', 'sub i64 %sex, 15360' % p)
     o(p + 'E', 'add i64 %sE0, %scarz' % (p, p))
     o(p + 'inf', 'icmp sge i64 %sE, 2047' % p)
-    o(p + 'low', 'icmp sle i64 %sE, 0' % p)
+    o(p + 'low', 'icmp sle i64 %sE0, 0' % p)
     o(p + 'fb', 'shl i64 %sE, 52' % p)
     o(p + 'frac', 'and i64 %skeep3, 4503599627370495' % p)
     o(p + 'bn', 'or i64 %sfb, %sfrac' % (p, p))
     o(p + 'bi', 'select i1 %sinf, i64 9218868437227405312, i64 %sbn' % (p, p))
-    o(p + 'sn', 'sub i64 1, %sE' % p)
+    o(p + 'sn', 'sub i64 1, %sE0' % p)
     o(p + 'snok', 'icmp sle i64 %ssn, 52' % p)
     o(p + 'snc', 'select i1 %ssnok, i64 %ssn, i64 1' % (p, p))
     o(p + 'sh2', 'add i64 %ssnc, 11' % p)
diff --git a/tools/plugins/p0c/f80b_rt/gen_cases.c b/tools/plugins/p0c/f80b_rt/gen_cases.c
index 86f29fa20..23d31acc6 100644
--- a/tools/plugins/p0c/f80b_rt/gen_cases.c
+++ b/tools/plugins/p0c/f80b_rt/gen_cases.c
@@ -12,9 +12,9 @@ static uint64_t rnd64(void) {
 
 int main(void) {
   srand(12345);
-  enum { N = 200000 };
-  static uint64_t to_in[N], to_m[N], fr_m[N], fr_out[N];
-  static uint16_t to_se[N], fr_e[N];
+  enum { N = 200000, NFX = 3, NFT = N + NFX };
+  static uint64_t to_in[N], to_m[N], fr_m[NFT], fr_out[NFT];
+  static uint16_t to_se[N], fr_e[NFT];
   int nt = 0;
   while (nt < N) {
     uint64_t bits = rnd64();
@@ -47,6 +47,19 @@ int main(void) {
     fr_m[i] = m; fr_e[i] = (uint16_t)e;
     memcpy(&fr_out[i], &want, 8);
   }
+  /* 固定ベクタ: 丸めの carry が立ち、かつ結果が subnormal 域になる境界 (丸め位置は carry 前の指数で決まる) */
+  static const uint64_t fx_m[NFX] = {0xFFFFFFFFFFFFFFFFULL, 0xFFFFFFFFFFFFFFFFULL, 0xFFFFFFFFFFFFFD32ULL};
+  static const uint16_t fx_e[NFX] = {0x3BFD, 0x3BFE, 0x3BE5};
+  for (int j = 0; j < NFX; j++) {
+    unsigned char buf[16] = {0};
+    memcpy(buf, &fx_m[j], 8);
+    memcpy(buf + 8, &fx_e[j], 2);
+    long double ld;
+    memcpy(&ld, buf, 10);
+    double want = (double)ld;
+    fr_m[N + j] = fx_m[j]; fr_e[N + j] = fx_e[j];
+    memcpy(&fr_out[N + j], &want, 8);
+  }
   FILE *f = fopen("rt_cases.h", "w");
   if (!f) return 1;
   fprintf(f, "static const uint64_t TO_IN[%d] = {", N);
@@ -55,13 +68,13 @@ int main(void) {
   for (int i = 0; i < N; i++) fprintf(f, "%s0x%016llxULL", i ? "," : "", (unsigned long long)to_m[i]);
   fprintf(f, "};\nstatic const uint16_t TO_SE[%d] = {", N);
   for (int i = 0; i < N; i++) fprintf(f, "%s0x%04x", i ? "," : "", (unsigned)to_se[i]);
-  fprintf(f, "};\nstatic const uint64_t FR_M[%d] = {", N);
-  for (int i = 0; i < N; i++) fprintf(f, "%s0x%016llxULL", i ? "," : "", (unsigned long long)fr_m[i]);
-  fprintf(f, "};\nstatic const uint16_t FR_E[%d] = {", N);
-  for (int i = 0; i < N; i++) fprintf(f, "%s0x%04x", i ? "," : "", (unsigned)fr_e[i]);
-  fprintf(f, "};\nstatic const uint64_t FR_OUT[%d] = {", N);
-  for (int i = 0; i < N; i++) fprintf(f, "%s0x%016llxULL", i ? "," : "", (unsigned long long)fr_out[i]);
-  fprintf(f, "};\n#define NT %d\n#define NF %d\n", N, N);
+  fprintf(f, "};\nstatic const uint64_t FR_M[%d] = {", NFT);
+  for (int i = 0; i < NFT; i++) fprintf(f, "%s0x%016llxULL", i ? "," : "", (unsigned long long)fr_m[i]);
+  fprintf(f, "};\nstatic const uint16_t FR_E[%d] = {", NFT);
+  for (int i = 0; i < NFT; i++) fprintf(f, "%s0x%04x", i ? "," : "", (unsigned)fr_e[i]);
+  fprintf(f, "};\nstatic const uint64_t FR_OUT[%d] = {", NFT);
+  for (int i = 0; i < NFT; i++) fprintf(f, "%s0x%016llxULL", i ? "," : "", (unsigned long long)fr_out[i]);
+  fprintf(f, "};\n#define NT %d\n#define NF %d\n", N, NFT);
   fclose(f);
   return 0;
 }
diff --git a/tools/plugins/p0c/f80b_rt/run.sh b/tools/plugins/p0c/f80b_rt/run.sh
index 88f66f1b8..ad8183eab 100644
--- a/tools/plugins/p0c/f80b_rt/run.sh
+++ b/tools/plugins/p0c/f80b_rt/run.sh
@@ -7,7 +7,7 @@ HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
 P0C="$(cd "$HERE/.." && pwd)"
 ROOT="$(cd "$HERE/../../../.." && pwd)"
 W="$ROOT/work/f80b_rt"
-EMCC="${EMCC:-$(command -v emcc || echo [EMSDK 参照]/upstream/emscripten/emcc)}"
+EMCC="${EMCC:-$(command -v emcc || echo "${EMSDK:?EMSDK に emsdk のルートを指定する (docs/REFERENCES.md [EMSDK])}/upstream/emscripten/emcc")}"
 mkdir -p "$W"
 cd "$W"
 gcc -O1 -o gen_cases "$HERE/gen_cases.c" -lm
```
