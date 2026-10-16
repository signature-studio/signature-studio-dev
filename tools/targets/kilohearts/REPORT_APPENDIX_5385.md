# REPORT 付録 (#5385 KH-159): Delay の stereo ABI 族後半 callee の呼出し 4 件を機械語で確定し規則化

親 #4880 (KH-126) の分割 2。本 issue は後半 3 callee (呼出し 6 件) を扱う。前半 3 callee は #5384 (`REPORT_APPENDIX_5384.md` §10-7z)。

#### 10-7aa. #5385 (KH-159): `FUN_180fdc700`・`FUN_180fdc6d8` の呼出し 4 件を規則化 (`FUN_180fcd400` の 2 件は未確定)

- **結論**: 呼出し 6 件のうち **4 件を規則化** (`FUN_180fdc700` 2 件・`FUN_180fdc6d8` 2 件)。残り 2 件 (`FUN_180fcd400` ← `FUN_180fcce40`) は機械語の源が未確定のため規則にしない。受入 1 (6 件の源の確定) と受入 2 (規則 1 件 = 呼出し 1 件) は **部分達成**。
- **測定 (n=1・素材 `plugins-kilohearts` の `HeartCore.core_64` sha256 先頭 `d55ce8b4`・Ghidra 12.1.4 (公式 zip sha256 `ddac49f9…` 一致)・JDK 21・emcc 6.0.12)**:
  - 規則追加前 (`ghidra_to_c.py delay --fix bitcast,intload,stackpair,assoc,concat`・閉包 139 関数・FAIL 0): `emcc -c` error **343** (引数数不一致 **69**・合計 343)。
  - 規則追加後: error **339** (引数数不一致 **65**)。差分 −4 = 規則 4 件。
  - 生成 C の差分は 4 行のみ (4232・4295・4512・4545 の呼出しの引数追加。`diff` で確認)。
  - 件数 assert: 4 規則とも件数 1 で通過 (`ABI rule hit 1`)。
- **機械語の源 (capstone 逆アセンブル)**:

| 呼出元 (C 行 → 機械語の call) | 呼出先 | 引数の源 (呼出し直前の xmm0) | 根拠 |
|---|---|---|---|
| 4232 → `180fcd9e5` (`FUN_180fcd690` 内) | `FUN_180fdc700` | 入口 `param_1` | `180fcd9e5 call` の直前は `movq xmm0,rdx` (`rdx` = 入口 xmm0 の bit、`180fcd6a1` で保持) |
| 4295 → `180fcdbf0` (`FUN_180fcd690` 内) | `FUN_180fdc700` | 入口 `param_1` | `180fcdab7 jae 180fcdbf0` は `180fcdabd vmovq xmm0,r9` より前に分岐。`180fcd9f0` (flag≠0) 経路で xmm0 は入口のまま |
| 4512 → `180fce455` (`FUN_180fce0d0` 内) | `FUN_180fdc6d8` | 入口 `param_1` | `180fce450 movq xmm0,rdx` (`rdx` = 入口 xmm0、`180fce0e1` で保持) |
| 4545 → `180fce640` (`FUN_180fce0d0` 内・flag≠0) | `FUN_180fdc6d8` | 入口 `param_1` | `180fce460 vmovq r9,xmm0` (読むだけ)・`180fce515`〜 で xmm0 を書かない経路 |

- **未規則化 2 件 (`FUN_180fcd400` ← `FUN_180fcce40`)**:
  - 4048 (`180fccee6`): 直前の xmm0 は入口 `param_1` (`movq rdx,xmm0`・`movaps xmm6,xmm0` で保持)。ただし `FUN_180fcd400` は `double` 2 個 + `int` 1 個を取り、`180fccee0` で xmm1 = 0.0・r8 = 0 を設定する。C 側の 2 個目・3 個目の引数の書き方 (4048 では未指定) を機械語と合わせる作業が残るため、本件では規則にしない。
  - 4060 (`180fcd074`): 直前の xmm0 は reduction 後の値 (`180fcd042`〜`180fcd069` の `subsd` 群の結果。`movaps xmm1,xmm6` で xmm1 も設定)。C 4060 の `param_1 = FUN_180fcd400()` に対応する式が未確定。`FUN_180fcd040` 相当の C 本体は生成 C に無く、同じ経路の対応を確定できなかった。
- **規則の正規表現**: 生成 C は `func_0x000180fdc700()` の形と `FUN_180fdc700()` の形の両方を出すため、既存規則と同じく `(?:func_0x000|FUN_)` で受けた。
- **数値の扱い**: emcc 通過は値の正しさを示さない。delay の wasm は全体で未成立 (引数数不一致 65・型不一致 115 が残る) のため、1000 trial 突合は未実施 (#3073 [KH-41] が担当)。

**測定 commit** (コードを変えた最後の commit): 本 PR の commit。`git diff <測定 commit> HEAD -- tools/targets/kilohearts/ghidra_route` は 0 行 (測定後の変更は本付録のみ)。

**残件の起票先** (本 issue の受入 1・2 の残り):

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `FUN_180fcd400` ← `FUN_180fcce40` の 2 件 (4048・4060) | stereo 族の残件 (引数数不一致 65 の内 2) | 本 issue #5385 に残りとして記載 (親 #4880) |
| 引数数不一致の残り 65 件 | Delay の emcc 不通過 (wasm 不成立) | #3844 [KH-79]・#3847 [KH-73]・#4917 [KH-135] (既存・open) |
| Delay の数値未検証 | emcc 通過だけでは値の正しさは言えない | #3073 [KH-41] (既存・open) |
