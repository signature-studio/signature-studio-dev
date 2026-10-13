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

## E. 受入条件の状態 (PR #804 本文より)

1. 4 本の `emcc -c` rc 0: 達成 (f80 段を含む)。`judge.py` 相当の exit code 化と NC は未実装。
2. E1/E2 の共有鎖修復: 対象外 (本 PR は engine 側の段のみ。共有 `lift/passes/` は未変更)。
3. VEX helper の SSE 固定判定と実装: 未達・未着手。起票先 #527。
4. define 無し range (各 2 件) の原因特定: 未達 (未調査)。起票先 #527。
5. 殻との結合方式 (LoadLibrary 経路・`VSTPluginMain` 呼出) の解析: 未達。起票先 #527。
6. f80 2 関数の #197 `f80_lower.py` 適用可否: 達成 (適用可、`emcc -c` は通過。bit-exact は未検証 → #197)。
