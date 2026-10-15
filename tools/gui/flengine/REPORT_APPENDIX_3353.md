# REPORT_APPENDIX_3353 (WIN-22 #3353)

親 #3245 の子。(1) boot を `function_1266a60` → `function_423940` (= `InitializeCriticalSection(0x12bd390)`) まで計装で実測する。(2) CreateFruityInstance の閉包 (boot7) を IR に取り込み、`cfi_probe.mjs` が `EnterCriticalSection` を越えるかを記録する。
既知類型との関係: 該当なし (新規の lift 欠陥類型は観測していない)。停止点 `function_412e40` の OOB の原因は未特定 (既知類型との対応は未確認)。

## 1. 結論

- boot は init 111 (`units_run` 109) で、shim の `LoadImageW` (STUB・fail-fast) に当たって止まる。`init_count` が 111 のため、init 列の 1675 行目 (`function_1266a60` → `function_423940`) には届かない。
- `LoadImageW` の実装 (commit `ad5b4da3`) は PR #3354 (OPEN・未 merge・base main) にあり、main には無い。init 1675 への到達は #3354 の merge に依存する。
- boot7 を取り込むと `_CreateFruityInstance` が export される。`cfi_probe` は `EnterCriticalSection` に届かず、`CreateFruityInstance` → `function_13752f0` → `function_1105350` → `function_412e40` で `memory access out of bounds` (OOB) になる。次の停止点は `function_412e40`。

## 2. 受入条件の状態 (#3353)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1 boot の 1675 到達を計装で実測。届かなければ trap 位置を REPORT に書く | 達成 (未到達を実測。trap 位置を記録) | §3-1 の boot の停止と §3-2 のスタック。`init_count` 111 < 1675 |
| 2 boot7 閉包を素材から取り込み、`cfi_probe` が `EnterCriticalSection` を越えるか記録。越えなければ次の停止点を記録 | 達成 (越えない。次の停止点 `function_412e40` を記録) | §3-3・§3-4 |

## 3. 実測 (測定 commit `fe3dcd114`)

### 3-0. 再現

`EMSDK_ENV=<[EMSDK] の emsdk_env.sh> RETDEC=<[RETDEC] の bin/retdec-decompiler> FL_WIN64_DIR=<fl-win64 展開先> bash tools/gui/flengine/cfi_boot7.sh`

手順: boot7 を消した IR を作る (`m11_gen_ir2.sh` → `m11_build.sh`) → 閉包 (`gf_seed_closure.py`) → RetDec で boot7 を lift (`m11_lift.sh`) → boot7 込みの IR を作る → `-g2` の診断 build → `run.mjs` と `cfi_probe.mjs`。

- 壁時計 258 秒 (`date` 01:03:23 → 01:07:41 UTC・測定版は stack 8 行。最終版 `fe3dcd114` の再実行は 01:12:32 UTC に完了)。load は測定時に記録していない。
- `m11_wndseed.sh` は実行していない (`work/boot6.lift.ll` が既存のため)。worktree の素材 (`work-m11`) からは IR を作り直すので `m11_wndseed.sh` の再実行は要る (初回のみ約 3 分)。

### 3-1. boot の停止 (`run.mjs`・`cfi_probe.mjs` の boot 部)

| 項目 | boot7 無し | boot7 あり |
|---|---|---|
| `boot_failfast` | `LoadImageW` | `LoadImageW` |
| `dllmain_done` | False | False |
| `units_run` / `init_count` | 109 / 111 | 109 / 111 |
| GUI-REACH | 12 (IMPL 11・STUB 1 = `LoadImageW`) | 同左 |
| `icall_miss` | 6 | 同左 |

素材 IR を m11 pass に通さずに使った場合 (negative control): `units_run` 17・`init_count` 18・`boot_threw` = `memory access out of bounds` (§5-1)。

### 3-2. boot の trap の呼出し鎖 (`-g2` 診断 build・`cfi_b7.json` の `boot.stack`)

`m11_tr_function_623840` → `function_623840` → `function_620cd0` → `function_8651a0` → `function_8659f0` → `function_425100` → `LoadImageW` → `gui_impl_LoadImageW` → `__wrap_gui_failfast` (fail-fast)。

`REPORT_APPENDIX_3077.md` §5 の呼出し鎖と一致する (修正後の boot の停止点も同じ)。

### 3-3. boot7 の取込

| 項目 | 結果 |
|---|---|
| 閉包 (`gf_seed_closure.py`・seed `0x1375990`) | 閉包外の新規 1,133 関数 (現 IR 基準。`cfi_closure.json` の `new_functions`) |
| `boot7.lift.ll` | 115,206 行・`define i64 @CreateFruityInstance` 1 件 |
| `m11_gen_ir2.sh` / `m11_build.sh` | 両方 rc 0・signature mismatch 0・undefined 0 |
| 診断 build (`build.sh` と同じ flags・`-g2`) | rc 0・duplicate 0・`_CreateFruityInstance` が export される |

`REPORT_APPENDIX_2880.md` §9-2 の boot7 は 2,071 関数・222,014 行だった。今回は素材の IR が既に持つ閉包分を除くため小さくなる (基準が違うので数値は直接比べない)。

### 3-4. CreateFruityInstance の呼出し (`cfi_probe.mjs`)

| 項目 | boot7 無し | boot7 あり |
|---|---|---|
| `CreateFruityInstance(0xC0, 0xEDE95A, host, &iface)` | `mod._CreateFruityInstance is not a function` | `memory access out of bounds` |
| JS スタック (wasm 関数名・`-g2`) | (呼べない) | `function_412e40` ← `function_1105350` ← `function_13752f0` ← `CreateFruityInstance` |
| `EnterCriticalSection` (`CS-MISS`) | 到達しない | 到達しない (OOB が先) |

判定: `EnterCriticalSection` を越えない。次の停止点は `function_412e40` (wasm func[85]・`0x86a5f`) の OOB。`CS-MISS` の行が出ないのは、OOB が `EnterCriticalSection` より前に起きるため。

## 4. 考察 (推定を含む)

- 1675 が届かないのは、LoadImageW の fail-fast が init 111 で先に起きるため。#3354 の LoadImageW を入れた後の次の停止点は、main 上では未測定 (#3354 の本文の KPI は変更前 `c6eca3e1` の値のみ)。
- CFI の OOB は、boot が 111 で止まった後の部分的な状態で起きている可能性が高い (推定)。boot を通さずに CFI を呼ぶと heap が未初期化で `function_407a50` (FastMM_GetMem) で OOB になり、別の経路に入る (推定の根拠は §5-2)。

## 5. ネガティブコントロール

- 5-1 (IR の m11 pass 未通過): 素材の `boot_final3.ll` をそのまま build して boot を走らせると `units_run` 17・`boot_threw` = `memory access out of bounds`。IR は `m11_gen_ir2.sh` と `m11_build.sh` を通す必要がある (`docs/WORKFLOW.md` §11 の #680)。
- 5-2 (boot を通さない CFI 呼出し): `cfi_noboot` (boot を外した診断コピー) は `function_407a50` で OOB (heap 未初期化)。boot 後の OOB とは経路が違う。
- 5-3 (boot7 無し): `_CreateFruityInstance` が export されず呼べない (`is not a function`)。`build.sh` の export 条件 (`@CreateFruityInstance` の定義の有無) が働くことを確認した。

## 6. 製品 KPI (起動・ウィンドウ)

- FLEngine 起動の通過 unit 数: 前 `units_run 109` / `init_count 111` → 後 `109` / `111` (boot7 の有無で変わらない)。
- 最初のウィンドウ: 製品起動では無し (前後とも。boot は窓作成の前の `LoadImageW` で停止)。
- 動かしていないもの: 実 FL の製品起動。`LoadImageW` 実装 (#3354) を入れた後の boot の完走。

## 7. 検証範囲・範囲外

- 検証範囲: `cfi_boot7.sh` の 1 回の完走 (commit `fe3dcd114`)。`run.mjs`・`cfi_probe.mjs` の出力。
- e2e (`e2e.sh`) は未実行。`e2e.sh` は `cfi_probe.mjs` を参照せず (`grep -n cfi_probe tools/gui/flengine/e2e.sh` は 0 件)、本 PR の変更 (新規の `cfi_boot7.sh`・`cfi_probe.mjs` の出力項目の追加) は e2e の入力に入らない。時間上限 (58 分) のため再実行していない。
- 範囲外: `LoadImageW` の実装 (#3354)・init 1675 の到達・CFI の OOB の原因。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| init 1675 (`function_423940` = `InitializeCriticalSection(0x12bd390)`) が未到達 | `LoadImageW` fail-fast (main)。受入 1 の到達は未達 | PR #3354 (`3245-loadimagew-shim`・未 merge)。merge 後に `cfi_boot7.sh` を再実行して再測定 (子 issue は起票しない) |
| CFI の OOB 停止点 `function_412e40` (boot 後の部分状態) | `EnterCriticalSection` に届かない | PM 判断 (親 #3245 の次の子。原因は未特定) |
| boot7 込みの e2e (JUDGE 値・S1) は未測定 | 既定の CI は boot7 を含まない (素材に無い)。boot7 込みの結果は `REPORT_APPENDIX.md` §7-6 の旧記録のみ | PM 判断 (再測定の要否) |
