# liftlib #294 (親 CI-4) — dir64_boundary_gate.sh の FL_WIN64_DIR を tools/shared/env.sh 経由に置換 (付録)

親: #294 (`tools/` 配下の絶対パス直書きの環境変数化)。本付録は範囲 `tools/liftlib/dir64_boundary_gate.sh` 1 本の実測。
既知類型との関係 (DEFECTS.md): 該当なし (パス既定値の置換のみ)。

## 0. 結論

- 置換: `dir64_boundary_gate.sh` の `${FL_WIN64_DIR:-<固定の作業用 VM パス>}` を `source ../shared/env.sh` + `$FL_WIN64_DIR` に変えた。既定値は env.sh 経由で従来と同一 (`$ANALYSIS_DIR/win64` の既定値 = 従来の固定パス。[WIN64] 参照)。
- 変更前後で gate の出力は一致 (パス差のみ)。終了コードも一致 (rc=1)。
- **gate は変更前 (origin/main `ffb17f14d`) から `[1] 列挙` で FAIL している** (本変更とは無関係)。原因は `tools/gui/flengine/pe_image_parity.py` の旧境界 2 箇所 → 子 [CI-180] で扱う。

## 1. 測定条件

- 測定 commit (コードを変えた最後の commit): `1aa0500ba` (変更前 base = `ffb17f14d`、origin/main は測定時点の HEAD)。
- 素材: `fl-win64` (`~/artifacts/fl-win64.tar.zst`) から `extracted/block00031_PE.bin` (22,227,016 B) のみを `tar --zstd -xf ... --wildcards` で `$RUNNER_TEMP/fl-win64/` へ展開。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/liftlib/dir64_boundary_gate.sh` (runner, `pefile` 2024.8.26)。
- 変更前は detached worktree `ffb17f14d` で実行、変更後は `294-liftlib-dir64-env` の worktree で実行。

## 2. 結果

| 測定 | 変更前 (ffb17f14d) | 変更後 (1aa0500ba・HEAD で再測定) |
|---|---|---|
| `FL_WIN64_DIR` 指定 (gate 全体) | rc=1、30 s | rc=1、31 s |
| 出力の差分 (パス部を正規化) | — | 0 行 (一致) |
| `[1] 列挙` | FAIL | FAIL (同一) |
| `[2] m6 実バイト` | PASS (補正漏れ=0、末尾slot補正=1) | PASS (同一) |
| `[2] liftlib 実バイト` | PASS (補正漏れ=0、末尾slot補正=1) | PASS (同一) |
| `[3]` ネガコン 4 件 | PASS (4/4) | PASS (4/4) |
| 既定値 (`env -u FL_WIN64_DIR -u ANALYSIS_DIR`) | rc=2、`PE 無し: <既定の win64 解決先>/extracted/block00031_PE.bin` | rc=2、同一 (diff 0 行) |
| `source tools/shared/env.sh` の `FL_WIN64_DIR` 解決 | — | 既定の win64 解決先 (従来値と同一。`[WIN64]`) |

`[1]` の内訳 (変更前後で同一):

```
[enum] 意図的な旧式 (許可): m11/m11_reloc_audit.py:83  式 OLD: 旧条件との選択差を測る監査用 (#572)
[enum] root=.../tools grep=10 ast=11 和集合=11 不一致=1 OLD=2
```

不一致 1 件 = `tools/gui/flengine/pe_image_parity.py` の 2 行 (`--json` の rows で確認):

- L97 `if lo - lb <= r < lo - lb + len(sd) - 8:` — AST 系のみ OLD (grep 系は `- lb +` の形を取りこぼす)。
- L119 `any(lo <= r < lo + vs - 8 ...)` — grep 系・AST 系とも OLD (末尾 8B slot が落ちる #593 と同型)。

この 2 行は GUI-12 (commit `6e5ff48ac`、#174) で入った。#593 (M11-N22) は m6・liftlib・test_unit を直したが、この複製は直していない。→ 子 [CI-180]。

## 3. 差分確認

測定 commit 以降のコード差分 (`git diff 1aa0500ba HEAD -- tools/liftlib/*.sh tools/liftlib/*.py tools/liftlib/liftlib tools/liftlib/tests`) は本付録の追加のみ (REPORT 系の .md)。コード差分 0 件。

## 4. 残り (起票先)

| 未解決 | 起票先 |
|---|---|
| `pe_image_parity.py` の旧境界 2 箇所 (gate `[1]` FAIL) | [CI-180] |
| `tools/ipp`・`tools/startup`・`tools/m2` の絶対パス直書き | [CI-178] |
| `tools/assets`・`tools/audio`・`tools/hostbridge`・`tools/perf`・`tools/ott/f7eval`・`tools/shared` の直書き | [CI-179] |
| `tools/m6`〜`tools/m8`・`tools/m11` の直書き、代表 e2e (ott / m11) の before/after | #294 (親) |
