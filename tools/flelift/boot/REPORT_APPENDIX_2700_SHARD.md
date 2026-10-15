# tools/flelift/boot 付録 (#4855)

> 正本: `tools/flelift/boot/REPORT.md`。REPORT §9 (FLE-9 #2700 の shard 化の実測) を行数上限 (250 行) のため分割移動した (内容は削除していない)。

## 9. FLE-9 (#2700): lifted C を 8 本に分けて clang・link・boot を実測 (2026-10-14)

- **結論**: 単一 TU の clang は cap 11000MB 超で打ち切られていた (FLE-8・付録 E-1)。8 shard (`FLE_SHARDS=8`・`xargs -P3`・各 cap 5000MB) では全て cap 内で完走 (各ピーク 2,202〜2,666MB・clang 段 89 s)。link は mismatch/undefined/duplicate 0・wasm 127,078,695 B。**boot は両 variant とも unit 209 で停止**。shim 有の IPP 判定は NG (`ptr_15F34A0=0x0`)。最初のウィンドウは未到達。
- 測定 commit: `a741a0ca` (コードを変えた最後の commit。検証起点 `origin/main` `26f90ada`)。差分 0 の証跡: `git diff --stat a741a0ca HEAD -- tools/flelift/x64c.py tools/flelift/boot/build.sh tools/flelift/boot/fle6_measure.sh tools/flelift/boot/rss_cap.py` が空 (本節の commit は REPORT・付録のみ)。
- 出力同一性: `--shards 1` は旧 `x64c.py` (origin/main) と小入力 (roots 先頭 400・closure 2・386 関数) で `fle_lifted.c` / `lift_meta.json` が sha256 一致。N=8 は関数本体の集合が N=1 と一致し、`ott_dispatch`・`imp_tab` は shard 0 のみ。既知類型: 該当なし (`docs/DEFECTS.md` D1a〜D23)。
- 再現: `FL_WIN64_DIR=<fl-win64 展開先> bash tools/flelift/boot/fle6_measure.sh` (既定 `FLE_SHARDS=8`)。素材 `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff`。

### 9-1. 工程の実測 (HEAD `a741a0ca`・`fle6_measure.sh` 1 回。同内容の前回実行は lift 67 s / clang 105 s で、boot の数値は同一)

| 工程 | 結果 | 秒 | ピーク RSS |
|---|---|---|---|
| gen-A | rc 0 | 8 | - |
| lift (closure 2・root 0x6a7b70・cap 13800MB) | rc 0・29,908 関数・1,557,903 insn | 88 | 610MB |
| clang shard ×8 (-O0・-P3・cap 5000MB) | 8/8 OK・cap 超過 0 件 | 89 (工程計) | s0 2,666 / s1 2,243 / s2 2,406 / s3 2,345 / s4 2,202 / s5 2,363 / s6 2,387 / s7 2,487 MB |
| shard 別の秒 (s0〜s7) | 46 / 31 / 32 / 20 / 23 / 27 / 26 / 22 | - | - |
| link | mismatch 0・undefined 0・duplicate 0・wasm 127,078,695 B | - | - |
| boot shim (`FLE_IPP=1`) | units 209・stopped 209・IPP check NG | 24 | - |
| boot ネガコン (`FLE_IPP=0`) | units 209・stopped 209・IPP check OK | 25 | - |

### 9-2. 起動指標 (前後)

- **units_run**: 前 209 (FLE-5/6・§2) → 後 **209 のまま** (停止点=209)。shim 有・ネガコンとも同じ。
- shim 有の確保 `GetMem` 2,314 / `FreeMem` 1,199 (ネガコン 1,891 / 776)。`ipp.called` 全件は `ippsZero_8u` ×2 のみ。`ptr_15F34A0` は shim 有でも `0x0`。
- 停止: 両方とも unit 209 の後に `MessageBoxA` (text 空・自動 IDOK) → `exit(0)` (call site `0x412a12`)。最初のウィンドウは未達 (生成は未確認)。既定経路 (root 無し) は未測定。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| shim 有で `0x15F34A0` が 0 のまま (`ippsZero_8u` は 2 回呼ばれる)。登録経路が未解明 | FLE-6 の IPP 判定 NG・units 209 据え置き | 既存 #2702 [FLE-10] (`blockedBy: #2700`)。本 PR で事実を追記 |
| unit 209 の後の `MessageBoxA` → `exit(0)` の原因 | 次の blocker (最初のウィンドウ未達) | 既存 #2702 (同上) |
| 既定経路 (root 0x6a7b70 無し) の boot 未測定 | 209 据え置きの確認が未了 | 既存 #2702 作業 1 |
