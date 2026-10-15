# REPORT_APPENDIX_779 — KH-16 (#779) 第 2 弾: ymm 語彙 vaddps / vsubps / vmulps の検証

`REPORT.md` §12-1 の全文を分割移動 (250 行上限のため・内容は無変更)。要約と判定は REPORT.md §12-1 が見る。

- **生成形 (実測)**: `retdec-decompiler -m raw -a x86-64 -e little` に `c5 f4 58 c2` (vaddps ymm0,ymm1,ymm2) を通すと `call i256 @__asm_vaddps(i256 src1, i256 src2)`。`gen_simd.py` は i256 宣言を `OUT.c.i256.ll` の LLVM IR 定義 (bitcast i256→`<8 x float>`・fadd/fsub/fmul・bitcast 戻し) で出す。C に i256 の正体型が無いため IR で定義し、呼出側と ABI を揃える。`build.py` は `.i256.ll` がある時だけ emcc 入力に加える。未対応の i256 宣言は `undefined` に報告し、`abort()` スタブを出す (SSE の未対応と同じ扱い。呼ばれたら abort)。vsubps / vmulps の ymm 生成形は未実測で、引数順 (src1 = 第 1 引数 → `a0 - a1`) は xmm 版の前提を継承する。
- **本検証** `python3 snapins/scripts/ymm_vocab_check.py 20000 1` (測定 commit `428eef1a`・oracle = ホスト AVX2 `_mm256_*_ps`・32B 全 bit 比較・NaN 含む): vaddps / vsubps / vmulps 各 20,000 call・160,000 lane **mismatch 0**。数え方は REPORT §12 の census (ymm 計 40 件)。wall 1.26 秒・load 0.21 0.24 0.11 (nproc=4)。
- **ネガコン**: (a) 語彙定義を外す → リンク失敗 (FAIL)。(b) vaddps の fadd を fsub に変える → mismatch **19,971 / 20,000** (FAIL)。(c) 未対応 `declare i256 @__asm_vfmadd231ps(i256, i256, i256)` → `undefined(abort stub) 1`・呼出で abort (rc=-6・FAIL)。
- **回帰**: i256 を含まない 8 宣言 (SSE 系) の入力で、main と新 `gen_simd.py` の C 出力・標準出力が `cmp` 一致。HEAD で build が通る 14 本は i256 宣言を含まない (旧版は i256 宣言で `KeyError` して落ちるため。推論)。**14 snap-in のハッシュ照合 (`run_all.sh`) は未実施**: run で取得したのは `fl-win64` のみ (`plugins-kilohearts` / `toolchain-emsdk` / `toolchain-retdec` は無い)。
- **測定 commit `428eef1a` → HEAD のコード差分** (`git diff 428eef1a HEAD -- tools/targets/kilohearts/snapins/lift tools/targets/kilohearts/snapins/harness tools/targets/kilohearts/snapins/scripts`): 0 行 (`git diff --stat 428eef1a HEAD` は REPORT.md のみ)。
