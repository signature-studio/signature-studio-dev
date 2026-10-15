# m11 area: FL_WIN64_DIR の既定値を tools/shared 経由へ (#294)

結論: m11 area の `/home/ubuntu` 既定値は `tools/shared/paths.py` / `env.sh` の単一定義に置換済み。before (`706147914`) と after (`256a869d1`) で生成物・gate の出力は一致した。`m11_e2e.sh --full` の before/after は未実施 (子 #4245)。

## 測定

- 測定 commit (コード差分の最終 commit): `a2ed45cf7` (`refactor(m11): take FL_WIN64_DIR from shared paths`)
- 実測の HEAD: `256a869d1` (`chore(m11): drop repo-external path note in reloc gate`)
- before: `706147914` (origin/main の取り込み時点)。detach worktree で実行。
- 入力: `$ARTIFACTS_DIR/fl-win64.tar.zst` を展開した `extracted/block00031_PE.bin` (sha256 `b2c64da4…9496d`)。`FL_WIN64_DIR` で指定。
- 実行環境: 07:31 時点 `load average: 0.49, 0.36, 0.16`。

| 検証 | before (706147914) | after (256a869d1) | 結果 |
|---|---|---|---|
| `m11_data_gen.py` → `m11_data.c` | sha256 `c042314a…65025`・rc=0・0.506 s | 同・rc=0・0.501 s | 一致 |
| `m11_image_gen.py` → `m11_image.bin` | sha256 `2d10d692…feeb`・rc=0・0.258 s | 同・rc=0・0.271 s | 一致 |
| `m11_reloc_gate.sh` | ALL PASS・3.718 s | ALL PASS・3.629 s | PASS (negctl: 補正漏れ 1 検出) |
| `tools/shared/test_paths.sh` | — | PASS (default / analysis_dir_only / individual_override / negctl) | PASS |
| `py_compile` (m11 の Python 6 本) | — | OK | OK |

## 既定値の挙動

- `ANALYSIS_DIR` 未設定: `FL_WIN64_DIR` = `/home/ubuntu/work/analysis/win64` (従来と同一)。
- `ANALYSIS_DIR` 設定時: `FL_WIN64_DIR` = `$ANALYSIS_DIR/win64` に追従する。従来の固定値とは異なるので、既定値の同一性は「未設定時」のみ成り立つ。

## 測定の鮮度 (#1268)

`git diff a2ed45cf7 HEAD -- tools/m11 tools/shared` の出力:

```
diff --git a/tools/m11/m11_reloc_gate.sh b/tools/m11/m11_reloc_gate.sh
-source ../shared/env.sh   # FL_WIN64_DIR (既定は従来どおり /home/ubuntu/work/analysis/win64)
+source ../shared/env.sh   # FL_WIN64_DIR (既定値は tools/shared/env.sh が正本)
```

差分は shell コメント 1 行のみ。実行行 (`source` 本体・`PE=` 以降) は同一。コメント以外に差分が無いので、実測値は HEAD にそのまま当てはまる。

## 未実施

- `tools/m11/m11_e2e.sh --full` の before/after (scan・bounds・tail・icall_audit の出力比較): `work/` が無く RetDec lift 約 22 分 + Ghidra 12.1.4 の取得が必要で、run の時間内に完走できない。子 #4245 で実施する。
- `m11_bounds.py`・`m11_scan.py`・`m11_tail.py`・`m11_icall_audit.py` の出力バイト比較: 変更は import と既定パスのみ。#4245 で確認する。

## 残り area (#294)

| area | 追跡先 |
|---|---|
| `tools/m6` (OTT 解析 11 本) | #4217 |
| `tools/m7`・`tools/m8`・`tools/targets/serum2` (e2e 系 4 本) | #4218 |
| `tools/shared` (`env.sh`・`paths.mjs`・`paths.py` は既定値の正本として残る) | 正本のため対象外 |
| m11 の代表 e2e before/after | #4245 |
