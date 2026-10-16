# tools/plugins/p0c REPORT 付録 M2 — #5832 の鮮度の証跡 (付録 M §4 の差分全文)

測定 commit = `ce3872372`。 差分は `git diff ce3872372 HEAD -- tools/plugins/p0c` を HEAD `5f7d24dbb` で取った出力 (全文)。 本付録は測定値を含まない。

```diff
diff --git a/tools/plugins/p0c/REPORT.md b/tools/plugins/p0c/REPORT.md
index d2164e4f4..cda6328d3 100644
--- a/tools/plugins/p0c/REPORT.md
+++ b/tools/plugins/p0c/REPORT.md
@@ -150,6 +150,12 @@ bash tools/plugins/p0c/p0c_e2e.sh      # 初回実測 355 秒 (work/ 無し・HE
 | §23 | #3280: 0x5dffc0 の 10000 case 残差 (x87 fsincos の 66-bit π 縮約) の解消 (測定 commit `9e49eb950`・buf_diff 3 → 0) | `REPORT_APPENDIX_J.md` |
 | §24 | #3281: GLOBAL_INITS を PE の .data から読む pass に置換 (測定 commit `74ae2bbf2`) | `REPORT_APPENDIX_K.md` |
 | §25 | #3951: 0x5e1280 の buf_diff=3996 の原因は k80_diff の 64bit xmm 引数の渡し方 (driver)。修復 `73409179c` で buf_diff=0 (2000/10000) | `REPORT_APPENDIX_L.md` |
+| §26 | #5832 (E7): x86_fp80 ↔ i80 bitcast の展開。bit 一致 (`f80b_rt/run.sh`)・subnormal carry の修正・19165 の測定 | `REPORT_APPENDIX_M.md` |
+
+## 26. #5832 (E7): x86_fp80 ↔ i80 bitcast の展開
+
+- **結論**: `bitcast x86_fp80 ↔ i80` を整数のビット演算へ展開する (`expand_f80_bitcasts`)。 `f80b_rt/run.sh` で double → x87 像 200,000 件・x87 像 → double 200,003 件 (固定ベクタ 3 件込み) が emcc 版で 0 不一致。 subnormal の carry の誤りは `842bc5ac3` で直した。 19165 は E7 が消え、次の類型 (`fp_extend` の libcall) で止まる (受入 1 未達)。
+- 詳細・測定値・未解決: `REPORT_APPENDIX_M.md`。
 
 ## 17. #1366 (CI-26): lift 段の alloca 並び正規化と before/after 一致
 
diff --git a/tools/plugins/p0c/REPORT_APPENDIX_M.md b/tools/plugins/p0c/REPORT_APPENDIX_M.md
new file mode 100644
index 000000000..68943b8de
--- /dev/null
+++ b/tools/plugins/p0c/REPORT_APPENDIX_M.md
@@ -0,0 +1,65 @@
+# tools/plugins/p0c REPORT 付録 M — #5832 (E7: x86_fp80 ↔ i80 bitcast の展開)
+
+> 本体の索引は `tools/plugins/p0c/REPORT.md` §26。 PR #5858 の本文から、測定値・表をここへ移した (`docs/WORKFLOW.md` §5)。
+
+## 1. 変換 bit 一致 (`f80b_rt/run.sh`)
+
+方式: `expand_f80_bitcasts` (`f80_lower.py`) が出した IR を emcc (wasm32) でビルドし、host (x86-64) の `long double` (x87) を期待値として照合する。`gen_cases.c` が期待値を作る。
+
+| 方向 | 件数 | 不一致 | 測定 commit |
+|---|--:|--:|---|
+| double → x87 像 | 200,000 | 0 | `ce3872372` |
+| x87 像 → double (subnormal・tie 含む) | 200,000 | 0 | `ce3872372` |
+
+### 1.1 修正 (指摘 #5858 round 1)
+
+`_f80b_from_image` の carry かつ subnormal 結果の誤りを直した。`sn` と `low` が carry 後の指数 `E` を使っていたため、subnormal の丸め位置が 1 桁ずれた。`E0` (carry 前の指数) で計算するよう変えた。
+
+固定ベクタ 3 件 (`gen_cases.c` の `fx_m` / `fx_e`) を追加した。`run.sh` が必ず検査する。
+
+| 入力 (m, se) | 修正前 (`9418e1050`) | 修正後 (`842bc5ac3`) | native (x87→double) |
+|---|---|---|---|
+| `0xFFFFFFFFFFFFFFFF`, `0x3BFD` | `0x0.4p-1022` | `0x0.2p-1022` | `0x0.2p-1022` |
+| `0xFFFFFFFFFFFFFFFF`, `0x3BFE` | `0x0.8p-1022` | `0x0.4p-1022` | `0x0.4p-1022` |
+| `0xFFFFFFFFFFFFFD32`, `0x3BE5` | `0x0.0000004p-1022` | `0x0.0000002p-1022` | `0x0.0000002p-1022` |
+
+修正前の `f80_lower.py` で同じ検査 (固定ベクタ込み) を実行すると `from: n=200003 fail=3` で rc 1。修正後は `from: n=200003 fail=0` で rc 0。
+
+### 1.2 修正後の検査 (emcc 版)
+
+emsdk を導入し (`emsdk install latest`・`activate latest`)、`EMSDK` を設定して `run.sh` を実行した。
+
+- `to: n=200000 fail=0`
+- `from: n=200003 fail=0`
+- rc 0・所要 1.37 s (`time`)
+
+## 2. 共有鎖の退行 (T0 / T1, `batch_lift.sh --tier T0/T1`)
+
+測定 commit `ce3872372` (修正前) の値。
+
+- T0: 41 blocks。 `lift_rc` 0・`emcc_c_rc` 0 が 41/41。 closure 関数 781 (REPORT と一致)。 所要: 実測ログ未保存 (PR 本文の記載のみ。時間の数値は採らない)。
+- T1: 45 blocks。 `emcc_c_rc` 0 が 44/45。 唯一の不通過は 24161 ReWired (f80 2 関数)。 REPORT §4.3 の既存の結果と同じで、本 PR による変化は無い。 closure 関数 2,835。 所要: 実測ログ未保存 (同上)。
+- 退行 0。 本 PR は T0/T1 の f80 関数を 0 〜 2 しか持たないブロックにしか効かないため、差は出ない。
+
+注: 測定 commit 以降に `f80_lower.py` の `_f80b_from_image` (subnormal の丸め位置) を変えた (`842bc5ac3`)。 この修正後の T0/T1 は**未再測定**。 `batch_lift.sh` の実行基盤 (`shared/env.sh`・RetDec・plugin 素材) が本 runner に無いため。 再測定は未実施として PR 本文の未解決に書く。
+
+## 3. 19165 engine (`engine_lift.sh 19165 900` → `engine_f80_subset.sh`)
+
+測定 commit `ce3872372` (修正前) の値。
+
+| 項目 | 本 PR 前 (REPORT §17) | 本 PR 後 |
+|---|---|---|
+| `emcc -c` (`e.final.ll`) の最初の error | `invalid cast opcode ... 'double' to 'i80'` (E7) | `do not know how to soften fp_extend` |
+| `emcc -c` (`e.final.ll`) rc | 139 (segfault) | 139 (segfault) |
+| 部分集合 (f80 関数 5 件を除外) の `emcc -c` rc | 0 | 0 (gate PASS) |
+| lift rc / define / f80 関数 (本体) | 0 / 2,608 / 5 | 0 / 2,608 / 5 |
+
+- 測定条件 (PR 本文の記載): `ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges <78 件>" ENGINE_TAG=_noipp_nobad engine_lift.sh 19165 900`。 wall 625 s・実行直後の 1 分平均 load 1.15 (4 core) は PR 本文の記載値で、 ログは保存されていない。
+- 注: `engine_lift.sh` は本 worktree (`tools/plugins/lift/`) に無い。 `engine_f80_subset.sh` の所在は `tools/plugins/reverb_delay/`。 本 runner では再測定していない。 修正後 (`842bc5ac3`) の 19165 も未再測定。
+
+## 4. 鮮度: `ce3872372` から HEAD までの差分
+
+`git diff ce3872372 HEAD -- tools/plugins/p0c` (PR 本文作成時点の HEAD `9418e1050`):
+
+- `f80b_rt/run.sh` の 1 行 (`EMCC` の解決を `$EMSDK` 必須にする変更)。 `EMCC` 変数は `command -v emcc` が先なので、 測定値は影響を受けない (`run.sh` の検査内容は変わらない)。 harness の変更であり、 測定対象の変換は変わらない。
+- 続けて `842bc5ac3` の修正 (`f80_lower.py` の `sn` / `low` と `gen_cases.c` の固定ベクタ)。 これは測定対象の変換を変える。 §1.1 の再検査で置換後の値を取った。 §2・§3 は未再測定。
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
-EMCC="${EMCC:-$(command -v emcc || echo /opt/emsdk/upstream/emscripten/emcc)}"
+EMCC="${EMCC:-$(command -v emcc || echo "${EMSDK:?EMSDK に emsdk のルートを指定する (docs/REFERENCES.md [EMSDK])}/upstream/emscripten/emcc")}"
 mkdir -p "$W"
 cd "$W"
 gcc -O1 -o gen_cases "$HERE/gen_cases.c" -lm
```
