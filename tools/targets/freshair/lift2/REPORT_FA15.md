# lift2 REPORT — FA-15 (#1105): ctrl closure の ymm (AVX2 256bit) lowering

- 親: #907 (FA-14) の受入 2。`REPORT_APPENDIX.md` §8 の未達 (`vpcmpeqw ymm`) の解消記録。
- 測定 commit: `1fa5a9a9` (mlift の最後のコード変更)。`git diff 1fa5a9a9 HEAD -- tools/targets/freshair/lift2/mlift` は本付録の commit 以降も 0 行 (下記)。

## 1. 原因

- `f_1810577ac` (制御層 closure の wchar 走査ループ, @181057857) が `vpcmpeqw ymm1, ymm1, ymmword ptr [r9]` で `non-xmm reg ymm1` により unsupported。
- mlift のレジスタは `XMM = <4 x i32>` 固定で、ymm の上位 128bit を保持できなかった。

## 2. 変更 (mlift のみ)

- `mlift.py`: 上位 128bit の退避先 `%Y_0..15` (`<4 x i32>`) を追加。関数入口でゼロ初期化する。
- `mlift_ops.py`:
  - `ymm_insn`: `vpcmpeqw ymm`・`vpxor ymm`・`vpmovmskb r32, ymm` を lowering する。上記以外の ymm 命令は `Unsupported` のまま (黙って誤変換しない)。
  - `vzeroupper`: 全 `Y_k` をゼロ化する。
  - VEX.128 の xmm 宛先命令 (比較系 `vcomi*`・`vucomi*`・`vptest`・`vtestp*` を除く): 上位 128bit をゼロ化する (ISA どおり)。レガシー SSE は上位を保持する。

## 3. 受入条件の実測

| 受入 | 結果 |
|---|---|
| 1. ymm の `vpcmpeqw` / `vpmovmskb` を lowering | 実施 (上記 §2) |
| 2. `build_ctrl.sh` の `failed(funcs with unsupported)` が 0 | 変更前: `failed 1` (`f_1810577ac`)。変更後: `mlift: lifted 1256 funcs / 536369 B / 114503 insns, failed(funcs with unsupported) 0`。`ctrl build ok` |
| 3. `lift2_e2e.sh` が ALL PASS | `RESULT: lift2_e2e ALL PASS`, exit 0, real **1m07.8s** (67.8 s)。load 0.10 → 0.73 (nproc 4, TMPDIR=`$RUNNER_TEMP`) |

`lift2_e2e.sh` の内訳 (測定 commit `1fa5a9a9`):
- comp BIT-EXACT 400/400 (non-grow 206/206・grow 194/194, fma0+fma1)
- filter BIT-EXACT 400/400 (fma0+fma1)
- fuzz 4 系統 (comp/filter × fma0/1): mismatch 0, ERR 0/0 (各 1200)
- ABI violations 0 (Compressor / Filter)・GPR check violations 0
- ctrl BIT-EXACT 15/15 (epf 8 + structured 2 + random 5, fma0+fma1, `ERR native/wasm 1/1 同一 scenario: yes`)
- ablation 5 種すべて検出 (comis_noflags 200/200, xmm_args_drop 200/200, xmm_ret_drop 200/200, icall_drop 80/200, cmov_drop 172/200)

## 4. 素材と環境

- 展開: `plugins-freshair` → `$RUNNER_TEMP/plugins-freshair`、`FA_DL=... bash tools/targets/freshair/fetch.sh` で factory `.epf` 8 本を確認。
- `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` は本 run で展開していない。`lift2_e2e.sh` は `SlateCore.core_64` (plugins-freshair 由来) と `/opt/emsdk`・`/opt/retdec` (既存) を使う。

## 5. 未解決・限界

- `f_1810577ac` の ymm 経路が実行時に到達するかは**未実測** (trace 未取得)。ctrl の 15 シナリオは全体の BIT-EXACT で検証したが、この経路だけを独立に検証していない。
- ymm の一般化 (`vmovdqu ymm`・`vpminub ymm` 等) は範囲外。現時点では上記 3 命令以外の ymm は unsupported のまま。
