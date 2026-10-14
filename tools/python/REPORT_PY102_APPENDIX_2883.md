# PY-102 REPORT の付録 (#2883): 旧 §9・§10 の全文

`REPORT_PY102.md` の旧 §9 (測定 commit `0e42e1ea`) と旧 §10 (測定 commit `14802840`) を、250 行上限のため分割移動したもの (内容は削除していない)。本文中の『§10』『本節』は旧番号。現在の正本は `REPORT_PY102.md` §10 (測定 commit `3aa3a256`)。

## 9. main 取り込み後の再測定 (測定 commit `0e42e1ea`)

- 取り込み (2 回)。(1) `origin/main` (`f0c00334`) を merge (`c46fdf72`)。(2) その後 `origin/main` が `875eba29` へ進んだため、再度 merge (`0e42e1ea`)。どちらも競合は `tests/provider_check.mjs` の 1 箇所だけ。
  - (1): main の `pe100` (`channels.getStepParam`・`channels.getCurrentStepParam`) と本 PR の `pe102` (`playlist.muteTrackLock`) を両方の集合に入れた。件数は main の `impl 86・unimpl 349` に +1 で `impl 87・unimpl 348`。
  - (2): main の `pe119` (PY-119・6 関数) と本 PR の `pe102` を両方の集合に入れた。件数は main の `impl 92・unimpl 343` に +1 で `impl 93・unimpl 342` (合計 435 は不変)。
  - `fl_engine.c`・`fl_mock.mjs`・`flapi_table.json`・`flapi_table.py`・`fl_table.c` は自動マージで衝突なし (両側の変更が残ることを diff で確認)。
- 測定 commit: `0e42e1ea` (コードを変えた最後の commit)。`git diff 0e42e1ea HEAD -- tools/python ':!tools/python/REPORT_PY102.md'` は 0 行 (本節の追記だけが差分)。
- CPython wasm は `c46fdf72` で作成 (exit 0・4m30.556s)。`c46fdf72` から `0e42e1ea` までに `build_cpython_wasm.sh`・`build_flpy.sh`・`src/`・`analysis/flapi_table.py` は変わっていない (`git diff --stat c46fdf72 0e42e1ea -- <同範囲>` は 0 件)。そのため出力 (`work/`、gitignore) を流用した。
- 検証 (`0e42e1ea`)。emsdk は上流 `emsdk install 6.0.12` を [EMSDK] の既定位置へ symlink して使った (リポジトリ外。`build_cpython_wasm.sh` が既定位置を直書きするため)。素材は `fl-win64` の 5 block を `FL_WIN64_DIR` 配下の `extracted/` へ展開 (2.932 s)。`fetch_inputs.sh` で `work/` を作成。

| 検証 | 実行 | 結果 | 所要 |
|---|---|---|---|
| provider wasm | `EMSDK_ENV=… bash provider/build.sh` | flprov.wasm 58,154 B。fl_table.c 435 関数・ハンドラ 93 | 0.980 s |
| flpy link (表の再生成を含む) | `FL_WIN64_DIR=… EMSDK_DIR=… bash build_flpy.sh` | flpy.wasm 5,924,680 B。再生成 3 ファイル差分 0 (`git status` が空) | 6.870 s |
| provider ABI | `node tests/provider_check.mjs` | functions 435・implemented 93・unimplemented 342・mcp_static 60・PASS | - |
| playlist 差分 | `node tests/playlist_diff.mjs` | calls 23・diffs 0・mock 状態 8 段・PASS | - |
| mixer 差分 | `node tests/mixer_diff.mjs` | calls 59・diffs 0・PASS | - |
| channels 差分 | `node tests/channels_diff.mjs` | calls 161・diffs 0・PASS | - |
| device 差分 | `node tests/device_diff.mjs` | calls 8・diffs 0 (rejects 4・midi_out 5)・PASS | - |
| 48 tools (mock) | `node tests/all_tools.mjs` | 48/48・soft_error 0・raised 0・host_calls 37,425 | - |
| 48 tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48・soft_error 0・raised 0・host_calls 37,425・callback_roundtrip true | - |
| 表の再生成・ネガコン | `FL_WIN64_DIR=… bash tests/flapi_table_check.sh` | 正常系の差分 0/3・win_pair 照合 388・ネガコン 6/6 PASS・fail 0 | - |
| kwsig 照合 | `python3 tests/kwsig_check.py` | OK | - |
| kwsig 束縛 | `python3 tests/kwsig_bind_check.py` | exit 0 (成功時は出力なし) | - |
| 引数個数 (before = `origin/main` (`875eba29`) の表 / after = 本 PR の表) | `python3 analysis/flapi/sig_arity_check.py <main の表> analysis/flapi/flapi_table.json` | 両方とも 対象 274・一致 274・不一致 0 | - |
| 実害の実測 (§3-2) | `node tests/sig_arity_probe.mjs` | kwsig_targets 24・implemented 6・unimplemented 18・fails 0・PASS | - |

- NC1 (差分検査): `host/fl_mock.mjs` の `playlist.muteTrackLock` を `arity(a, 1, 1)` に戻すと、`tests/playlist_diff.mjs` は `playlist 差分 12 件` で FAIL (exit 1)。`git show HEAD:` で復元すると PASS (calls 23・diffs 0)。
- 環境: GitHub Actions runner (4 コア)。`uptime` の load average (21:42:58) は `0.86 0.92 0.68`。
- 本節の値は測定 commit `0e42e1ea` の履歴。正本は §10 (測定 commit `14802840`)。§8 の表は測定 commit `4f621cad` の値 (履歴)。

## 10. main 取り込み後の再測定 (測定 commit `14802840`)

- 取り込み。`origin/main` (`585d0318`) を merge (`14802840`)。競合は `tests/provider_check.mjs` の 1 箇所だけ。main 側は PY-119 の `pe119set` (`general.setRecPPQ` ほか 6 関数) を追加。両方を集合に入れ、件数は main の `impl 103・unimpl 332` に `pe102` の +1 を加えて `impl 104・unimpl 331` (合計 435 は不変)。`fl_engine.c`・`fl_mock.mjs`・`flapi_table.json`・`flapi_table.py`・`gen/fl_table.c` は自動マージで衝突なし。
- 直前の取り込み (`5b35c23b`・`origin/main` `8fd940bb`) の実測値は Git 履歴 (`45b0c912` の REPORT) に残る。本節が正本。
- 測定 commit: `14802840` (コードを変えた最後の commit)。`git diff 14802840 HEAD -- tools/python ':!tools/python/REPORT_PY102.md'` は 0 行 (本節の追記だけが差分)。
- 素材: `fl-win64` の 5 block (`block00031_PE`・`block24429_DATA`・`block24430_DATA`・`block25159_DATA`・`block24618_DATA`) を `$RUNNER_TEMP/fl-win64/extracted/` へ展開 (2.804 s)。`FL_WIN64_DIR` でこれを指した。`fetch_inputs.sh` で `work/` を作成 (stubs は git clone)。`toolchain-emsdk` は本 run の素材に無い。
- emsdk: 上流 `emsdk install 6.0.12` を導入して `activate` し、[EMSDK] の既定位置へ symlink した (`build_cpython_wasm.sh` が既定位置を直書きするため)。CPython wasm は本 run で作成 (21:59:55 → 22:04:34、exit 0。CPython 側のソースは変えていない)。

| 検証 | 実行 | 結果 | 所要 |
|---|---|---|---|
| provider wasm | `bash provider/build.sh` | flprov.wasm 58,876 B。fl_table.c 435 関数・ハンドラ 104 | 0.928 s |
| flpy link (表の再生成を含む) | `FL_WIN64_DIR=… EMSDK_DIR=… bash build_flpy.sh` | flpy.wasm 5,924,680 B。再生成 3 ファイル差分 0 (`git status` が空) | 6.855 s |
| provider ABI | `node tests/provider_check.mjs` | functions 435・implemented 104・unimplemented 331・mcp_static 60・PASS | - |
| playlist 差分 | `node tests/playlist_diff.mjs` | calls 23・diffs 0・mock 状態 8 段・PASS | - |
| mixer 差分 | `node tests/mixer_diff.mjs` | calls 59・diffs 0・PASS | - |
| channels 差分 | `node tests/channels_diff.mjs` | calls 161・diffs 0・PASS | - |
| device 差分 | `node tests/device_diff.mjs` | calls 8・diffs 0 (rejects 4・midi_out 5)・PASS | - |
| general 差分 (main 由来) | `node tests/general_diff.mjs` | calls 25・diffs 0・PASS | - |
| 48 tools (mock) | `node tests/all_tools.mjs` | 48/48・soft_error 0・raised 0・host_calls 37,425 | - |
| 48 tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48・host_calls 37,425・callback_roundtrip true | - |
| 表の再生成・ネガコン | `FL_WIN64_DIR=… bash tests/flapi_table_check.sh` | 正常系の差分 0/3・win_pair 388・ネガコン 6/6 PASS・fail 0 | - |
| kwsig 照合 | `python3 tests/kwsig_check.py` | OK | - |
| kwsig 束縛 | `python3 tests/kwsig_bind_check.py` | PASS (103 関数・6,122 ケース・misbind 0・mismatch 0) | - |
| 引数個数 (before = `origin/main` (`585d0318`) の表 / after = 本 PR の表) | `python3 analysis/flapi/sig_arity_check.py <main の表> analysis/flapi/flapi_table.json` | before 対象 274・一致 274・不一致 0 / after 対象 274・一致 274・不一致 0。引数個数が変わった関数 0 件 | - |
| 実害の実測 (§3-2) | `node tests/sig_arity_probe.mjs` | kwsig_targets 24・implemented 8・unimplemented 16・fails 0・PASS | - |

- NC1 (差分検査): `host/fl_mock.mjs` の `arity(a, 1, 2)` を `arity(a, 1, 1)` に戻すと、`tests/playlist_diff.mjs` は `playlist 差分 12 件` で FAIL (exit 1)。元に戻した後の `git diff HEAD -- tools/python/host/fl_mock.mjs` は 0 行。
- 件数の差: handler 98 (`5b35c23b`) → 104 は main の PY-119 `pe119set` の 6 件。`implemented` 8 は main の PY-121 (`screen.*`) を含む。
- 環境: GitHub Actions runner (4 コア)。`uptime` の load average (22:09:19) は `0.62 1.00 0.78`。
- 未解決 (§5) は不変: 準備判定 (#2959)・追加引数の意味論 (#2950)・kwlist 無しの名前と書式 (#2952)。
