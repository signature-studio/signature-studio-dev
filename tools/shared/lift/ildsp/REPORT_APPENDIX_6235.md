# ildsp uselistorder の除去を IR 正規化段へ移す (T-SH-164 #6235)

REPORT_CI.md §9-5 の全文 (250 行上限のため分割移動)。結論と検証の要約は REPORT_CI.md §9-5。

結論: `uselistorder` は `ir_normalize.py --drop-uselistorder` (ci_lift.sh の正規化段) で除き、`ci_link.sh` の `grep -v` を外した。除去前後で `ci.emc.ll` はバイト一致・`ci.o` の未定義シンボル集合は一致・`ci_link.sh` の rc と未解決集合は一致。
測定 commit: `b1d019794` (コードを変えた最後の commit)。`git diff b1d019794 HEAD -- tools/shared/lift/ildsp tools/shared/lift/libkio` の出力は空。

- 除去しない IR は emcc で obj 化できない (`emcc -c -O1 ci.rs_norm.ll` → `wrong number of indexes, expected 5`・`uselistorder i64 %arg3, { 1, 0, 2, 3 }`)。`uselistorder` 120 件を除くと 2924 → 2804 行。`ci.emc.ll` は旧 `grep -v` の出力と `cmp` 一致。
- `ci.o` の未定義シンボル (`llvm-nm -u`・旧 f4b50f212 と新 b1d019794): 18 件で一致 (`diff` 出力なし)。
- 実測 (`b1d019794`・素材 fl-win64 / toolchain-retdec / toolchain-emsdk を `$RUNNER_TEMP` に展開・n=3):

  | 項目 | 値 |
  |---|---|
  | `ci_lift.sh` rc / 実行時間 (`date` で計測) | 0 / 3.49・3.12・3.42 s |
  | `ci_link.sh` rc / 実行時間 | 0 / 0.675・0.680・0.680 s |
  | `ci_link.sh` の出力 (3 回) | `cmp` で 3 回とも一致 |
  | 未解決 (wasm-ld rc 1 の期待内) | `function_1801aef40` 1 件 (#6231)。IAT 10 種は #6226 の stub で解決済み |
  | load (実行前の 1 分平均) | 0.36–0.41 (lift)・0.50 (link) |

- 基準 (旧): `origin/main` f4b50f212 の両スクリプトも rc 0・未解決は `function_1801aef40` 1 件で、新と一致。
- ネガティブコントロール: 除去前の IR を `ci_link.sh` に渡す → `uselistorder が残っている` で exit 1 (guard)。
- 範囲外: `function_1801aef40` (#6231)・`@0` の意味 (#3320)。
