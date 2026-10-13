# tools/plugins/p0c REPORT 付録 G (§17)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。本節は #916 (親 #346) で新規追加。

## 17. #916: nsis_blockmap.json を素材から再生成する手順の正式化 (f2/mk_blockmap.py)

### 17.1 変更

- `p0c_e2e.sh` に `[1b]` を追加: `work/nsis_blockmap.json` が無ければ `f2/mk_blockmap.py` で `PLUGIN_MATRIX.json` の win modules から生成する。`[2]` (kernel_matrix.py) の前に置く。`kernel_matrix.json` が有る場合でも blockmap の有無は独立に判定する。
- 生成物 (`tools/plugins/work/nsis_blockmap.json`) は gitignore 対象 (`**/work/`)。commit しない。
- 出力: `rows 182` (PE 一意 DLL 181 件、`kernel_matrix.py` の `dll_ids()` と一致)。sha256 `9dfb5958458e…`。

### 17.2 検証条件

- 検証 HEAD: `4f93cb76` (`origin/main` 863f3d3c 起点の branch `916-p0c-blockmap-regen`)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR`)、`block18983_PE.bin` の存在を確認。`toolchain-retdec` は展開せず、runner 既存の `[RETDEC]` (`/opt/retdec`, v5.0) を使った。`retdec-decompiler` は素材 tarball 内のものと sha256 一致 (`9d49ffcf106f…`) を確認済み。llvm-as は `/usr/lib/llvm-18/bin`。`toolchain-emsdk` は本 e2e (`[1]`〜`[6]`) では使われないため展開していない。
- 生成物なし: `tools/plugins/work/` と `tools/plugins/p0c/work/` を空にして開始 (`kernel_matrix.json`・`k80.lift.ll` 等すべて無し)。
- 依存: pefile・capstone・numpy を repo 外 venv (`$RUNNER_TEMP/p0cvenv`) に導入。
- n=1・直列・4 コア runner。

### 17.3 実測

| 検証 | rc | 所要 | 開始 load (1 分値) | 終了 load (1 分値) | 注記 |
|---|---|---|---|---|---|
| `p0c_e2e.sh` (生成物なし・HEAD `4f93cb76`) | 0 | 501 s | 0.16 | 8.39 | `[1b]` rows 182・`[2]` kernel_matrix 込み・`== e2e OK ==` |

stdout の確認: `[1b] nsis_blockmap.json を PLUGIN_MATRIX.json から生成` → `rows 182` → `[2]` 実行 → `[4]` `ranges written: 80 kernels` → `[6]` 完了。

### 17.4 未検証・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 2 つの生成器が並存: `f2/mk_blockmap.py` (182 行) と `inventory/blockmap_from_matrix.py` (181 行・block で dedupe)。差分は 5 行: (a) `outdir` に `subdir` を含むか (f2 は含む: `Effects\Distructor\module` 等 4 件)、(b) `idx=24302` (Wasp XT) が f2 では 2 行 (dedupe なし) | 本 e2e の `dll_ids()` は `idx` の集合のみ使うため結果は不変。2 生成器の統一は本 issue 外 | 起票は不要 (影響なし・既存挙動は不変)。統一が必要になった時点で起票 |
