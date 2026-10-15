# PY-357 (#4698): build_flpy.sh の EMSDK_DIR unbound (set -u) を直し flpy 経由の検査を通す

親: #4674。前段: `REPORT_PY226_4674.md` (commit `a64576793`。main 未取り込みのため本文は参照のみ)。既知類型との関係: 該当なし (ビルド script の不具合)。起動・GUI に関わらないため製品 KPI は対象外。

## 0. 結論

- 原因は `emsdk_env.sh` の副作用。`emsdk.py` (2833-2837 行) は、`EMSDK_*` で自分が設定しない export 済み変数を `unset` する。`EMSDK_DIR` がこれに当たり、source 直後に消えて `set -u` で落ちていた。
- 修正: source の前に `EMSDK_ROOT` へ退避し、source 後に `export EMSDK_DIR` し直す (`tools/python/build_flpy.sh`)。
- 受入条件 3 点を満たした (§2)。

## 1. 原因の実測

- 修正前: `EMSDK_DIR=<展開先> FLPY_SKIP_TABLE=1 bash build_flpy.sh` → `build_flpy.sh: line 23: EMSDK_DIR: unbound variable` rc=1。
- `bash -x` で `+ unset EMSDK_DIR;` が `eval` 内に出ることを確認 (`emsdk construct_env` の出力)。
- 単独の `bash -c 'set -u; EMSDK_DIR=...; source emsdk_env.sh'` が通ったのは、`EMSDK_DIR` を export せず shell 変数にしていたため。emsdk は環境変数だけを unset する。

## 2. 検証 (測定 commit: `b84c4f43e`)

測定環境: Actions runner (4 core・RAM 15 GiB)。素材は `fl-win64` と `toolchain-emsdk` (`[WIN64]`・`[EMSDK]` の展開元) を展開して使用。

| 段 | コマンド | 結果 | 所要 |
|---|---|---|---|
| CPython wasm | `EMSDK_ENV=<emsdk>/emsdk_env.sh bash build_cpython_wasm.sh` | rc 0 (`work/build-wasm` 生成) | 11:17:02 → 11:21:09 (約 4 分 07 秒) |
| 受入 1・2 | `EMSDK_DIR=<emsdk> FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 (`dist/flpy.{js,wasm,data}`) | 11:21:12 → 11:21:35 (23 秒) |
| provider | `EMSDK_ENV=<emsdk>/emsdk_env.sh bash provider/build.sh` | rc 0 (`dist/flprov.{js,wasm}`) | 11:21:48 → 11:21:55 を含む (個別計時なし) |
| 素材 | `FL_WIN64_DIR=<展開先> bash fetch_inputs.sh` | rc 0 (`work/MCPTools.pyc` 100674 B・`midi.py`・`utils.py`) | 数秒 |
| 受入 3 (a) | `node tests/provider_check.mjs` | rc 0・1 s: `{"functions":435,"implemented":224,"unimplemented":211,"mcp_static":60,"PASS":true}` | 1 s |
| 受入 3 (b) | `FL_ENGINE=wasm node tests/all_tools.mjs` | rc 0・2 s: `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}` | 2 s |

負荷: 測定時 load average 2.0〜2.2 (4 core)。

## 3. 差分 (測定 commit から HEAD まで)

`git diff b84c4f43e HEAD -- tools/python/` は本 REPORT の追加のみ (コード差分 0)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `REPORT_PY226_4674.md` (commit `a64576793`) が origin/main に未取り込み | issue 本文の参照先が main に無い | 起票先 未定 (PM 判断) |
| `build_cpython_wasm.sh` は `EMSDK_ENV`、`build_flpy.sh` は `EMSDK_DIR` で emsdk を指定する (変数名が別) | 両方を指定しないと一方が既定の `[EMSDK]` を見る | 起票先 未定 (PM 判断) |
