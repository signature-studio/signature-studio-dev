# PY-357 (#4698): build_flpy.sh の EMSDK_DIR unbound (set -u) を直し flpy 経由の検査を通す

親: #4674。前段: `REPORT_PY226_4674.md` (commit `a64576793`。main 未取り込みのため本文は参照のみ)。既知類型との関係: 該当なし (ビルド script の不具合)。起動・GUI に関わらないため製品 KPI は対象外。

## 0. 結論

- 原因は `emsdk_env.sh` の副作用。`emsdk.py` (2833-2837 行) は、`EMSDK_*` で自分が設定しない export 済み変数を `unset` する。`EMSDK_DIR` がこれに当たり、source 直後に消えて `set -u` で落ちていた。
- 修正: source の前に `EMSDK_ROOT` へ退避し、source 後に `export EMSDK_DIR` し直す (`tools/python/build_flpy.sh`)。
- 受入条件 3 点を満たした (§2)。`EMSDK_ENV` 経由 (`build_cpython_wasm.sh` と同じ指定) と `EMSDK_DIR` 直指定の両方で動く (修正 commit `d139efec8`)。

## 1. 原因の実測

- 修正前: `EMSDK_DIR=<展開先> FLPY_SKIP_TABLE=1 bash build_flpy.sh` → `build_flpy.sh: line 23: EMSDK_DIR: unbound variable` rc=1。
- `bash -x` で `+ unset EMSDK_DIR;` が `eval` 内に出ることを確認 (`emsdk construct_env` の出力)。
- 単独の `bash -c 'set -u; EMSDK_DIR=...; source emsdk_env.sh'` が通ったのは、`EMSDK_DIR` を export せず shell 変数にしていたため。emsdk は環境変数だけを unset する。

## 2. 検証 (測定 commit: `d139efec8`)

測定環境: Actions runner (4 core・RAM 15 GiB)。素材は `fl-win64` と `toolchain-emsdk` (`[WIN64]`・`[EMSDK]` の展開元) を展開して使用。

| 段 | コマンド | 結果 | 所要 |
|---|---|---|---|
| CPython wasm | `EMSDK_ENV=<emsdk>/emsdk_env.sh bash build_cpython_wasm.sh` | rc 0 (`work/build-wasm` 生成) | real 3m25.138s (`time` 実測) |
| 受入 1 (EMSDK_ENV) | `env -u EMSDK_DIR EMSDK_ENV=<emsdk>/emsdk_env.sh FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 (`dist/flpy.{js,wasm,data}`) | real 4.629s |
| 受入 1 (EMSDK_DIR) | `env -u EMSDK_ENV EMSDK_DIR=<emsdk> FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 (`dist/flpy.{js,wasm,data}`) | real 4.644s |
| 受入 2 | 上の 2 行と同じ実行 (`FLPY_SKIP_TABLE=1 bash build_flpy.sh`) | rc 0 | 上と同じ |
| provider (前段) | `EMSDK_ENV=<emsdk>/emsdk_env.sh bash provider/build.sh` | rc 0 (`dist/flprov.{js,wasm}`) | 作業ツリー上で実行 (provider/build.sh は未変更) |
| 素材 | `FL_WIN64_DIR=<fl-win64 展開先> bash fetch_inputs.sh` | rc 0 (`work/MCPTools.pyc` 100674 B・`midi.py` 19275 B・`utils.py` 4977 B) | 時間未計測 |
| 受入 3 (a) | `node tests/provider_check.mjs` | rc 0: `{"functions":435,"implemented":224,"unimplemented":211,"mcp_static":60,"PASS":true}` | real 0.290s |
| 受入 3 (b) | `FL_ENGINE=wasm node tests/all_tools.mjs` | rc 0: `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}` | real 1.314s |

負荷: 測定時 load average 1.5〜1.8 (4 core)。`all_tools` の `FL_ENGINE=wasm` は測定 commit `d139efec8` 上で再実行 (rc 0)。

## 3. 差分 (測定 commit から HEAD まで)

`git diff d139efec8 HEAD -- tools/python/` は本 REPORT の追加のみ (コード差分 0)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `REPORT_PY226_4674.md` (commit `a64576793`) が origin/main に未取り込み | issue 本文の参照先が main に無い | 起票先 未定 (PM 判断) |

解消済み: `build_flpy.sh` は `EMSDK_ENV` (`build_cpython_wasm.sh` と同じ指定) も受け付けるようにした (§0・§2)。
