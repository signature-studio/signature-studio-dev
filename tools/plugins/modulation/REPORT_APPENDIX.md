# tools/plugins/modulation/REPORT_APPENDIX.md — PLG-F5-2 (#527) f80 段の追補

> **正本**: `tools/plugins/modulation/REPORT.md`。測定値 (表・lift 秒・`emcc -c` の結果) の正本は本体 §4 だけで、本付録には再掲しない。

REPORT 本体 §4 から分割移動した経緯と実行条件 (内容は削除していない)。

## A. 変更内容

- `engine_lift.sh` に、fixcmp 後の `emcc -c` (erc2) が失敗し、かつ `final.ll` に `x86_fp80` を含む define があるときだけ、`p0c/f80_lower.py` (x86_fp80 → f64、#197 の既存 pass) を適用して `emcc -c` を再試行する段を追加した。
- 出力 `summary.csv` の最終列 `erc3` に再試行の結果を出す。f80 が無い、または erc2 が 0 の場合は `erc3 = erc2`。
- 失敗時は `first_errors.txt` に `[f80.ll]` の最初のエラー行を追記する。

## B. 19266・19268 の失敗内容

- fixcmp 後の `emcc -c` の最初のエラーは `fp_extend` (soften) で、f80 型の演算の legalize 失敗。
- f80 関数 1 本ずつ (19266 は `function_18001c320`、19268 は `function_1800218a0`) を lowering すると rc 0 になった。
- f80→f64 は bit-exact ではない (#197 で未検証)。未実装 helper (VEX 含む) は残るため、`emcc -c` の通過は stub を含む通過で、正しさは未確認。

## C. 未実装 helper と `emcc -c` の経緯

- 未実装 helper は main の m11_simd2 変更 (a824a1d / 9b5ea38、#535 / #538) で変わった。8603db1 の値は 86 (60) / 75 (57) / 64 (53) / 104 (77) (括弧は VEX)。648383c 以降は本体 §4 の値。
- `emcc -c` は 8603db1・648383c では 0/4 本だったが、main の lift 鎖変更 (`fix_icmp_ptr.py` P-E1 / `ir5_patch.py` P-F1・P-F2、`PLUG_F80_LOWER` は既定 0) を取り込んだ b9fe1d8 で 2/4 本になった。

## D. 実行条件 (35d8f3d5 の f80 段)

- 実行: `bash tools/plugins/modulation/engine_lift.sh <block> 300` を 4 本 (18977・19143・19266・19268) 順次実行。実測値は本体 §4 の表と直下の段落に記録した。
- 上記は emsdk 入りの環境で行われた。修正 run の runner には `emcc` と `/opt/emsdk` が無いため、再実行していない。
- #527 レビュー差し戻し対応 (fix run): `work/modulation/engine<N>/` (lift 出力・`ranges.txt`・`summary.csv`) が無く、`$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ。4 本の `engine_name_gap.py` stdout と `ranges.txt` 件数は**取得不可**で、本付録にも REPORT にも実機値を載せない。`engine_name_gap.py` の検証は合成入力のみ (注釈 1 件・関数名 `helper_x`/`lookup` の 2 件照合、件数不一致で exit 1)。

## E. 受入条件の状態 (PR #804 本文より)

1. 4 本の `emcc -c` rc 0: 達成 (f80 段を含む)。`judge.py` 相当の exit code 化と NC は未実装。
2. E1/E2 の共有鎖修復: 対象外 (本 PR は engine 側の段のみ。共有 `lift/passes/` は未変更)。
3. VEX helper の SSE 固定判定と実装: 判定は完了 (§F)。SSE 固定は静的に不成立。実装は未達で、起票先は #534 (VEX helper) と #779 (VEX-256 語彙)。
4. define 無し range (各 2 件) の原因特定: 未達 (未調査)。起票先 #527。
5. 殻との結合方式 (LoadLibrary 経路・`VSTPluginMain` 呼出) の解析: 未達。起票先 #527。
6. f80 2 関数の #197 `f80_lower.py` 適用可否: 達成 (適用可、`emcc -c` は通過。bit-exact は未検証 → #197)。

## F. VEX helper の SSE 固定判定 (受入 3、HEAD 70385178)

- 方法: `sampler/vex_guard.py <block>` (.pdata 関数ごとに v 始まり mnemonic・cpuid・xgetbv を数え、VEX 関数の直接 caller を深さ 3 まで遡って cpuid/xgetbv 関数に届くかを見る)。
- 結果:

| block | pdata 関数 | VEX 関数 | VEX 命令 | cpuid 関数 | xgetbv 関数 | caller 深さ 3 に guard あり |
|--:|--:|--:|--:|--:|--:|--:|
| 18977 | 418 | 8 | 635 | 2 | 2 | 0 |
| 19143 | 445 | 8 | 658 | 2 | 2 | 0 |
| 19266 | 542 | 9 | 588 | 2 | 2 | 0 |
| 19268 | 626 | 13 | 916 | 3 | 2 | 0 |

- 判定: VEX 関数は 4 本とも CPUID / xgetbv 分岐の下に無い。よって「CPUID を SSE に固定して VEX 側を呼ばない」は静的には成立しない (sampler/REPORT_ENGINE_LINK.md §5 と同じ結論)。動的な分岐の実測は未実施。
- 未実装 helper (`engine_lift.sh` 実行、`e.simd.log` の `unimplemented:` 行、fix_avx256 適用後。HEAD 70385178): 18977 = 70、19143 = 64、19266 = 60、19268 = 92。このうち VEX は distinct で 55 / 52 / 50 / 71。
- 代表例 (4 本共通): `__asm_vfmadd132sd`・`__asm_vfmadd213sd`・`__asm_vfmadd231sd`・`__asm_vcvtpd2dq`・`__asm_vcvttpd2dq`・`__asm_vmovsd`・`__asm_vmulsd`・`__asm_vaddsd`・`__asm_vdivsd`・`__asm_vcomisd`・`__asm_vucomisd`・`__asm_vldmxcsr`・`__asm_vstmxcsr`・`__asm_vpxor`・`__asm_vpshufd`・`__asm_vcvtss2si`・`__asm_vroundsd`。スカラー FMA と double 変換が中心。
- 実装は helper ごとに SSE/AVX の意味論 (丸め・例外フラグ・MXCSR) を合わせる必要があり、1 run に収まらない。既存の追跡先 #534 (9 本の C++ DLL の VEX helper) と #779 (VEX-256 の lift 語彙拡張) に統合する。新規起票はしない (重複回避)。
- 再現: `cd tools/plugins && source modulation/env.sh && python3 sampler/vex_guard.py <block> --list`、`bash modulation/engine_lift.sh <block> 300` の `work/modulation/engine<block>/e.simd.log`。
- 注記: 未実装 helper の数は main の m11_simd2 / fix_avx256 の変更で変わる (§C)。上表は HEAD 70385178 の実測。
