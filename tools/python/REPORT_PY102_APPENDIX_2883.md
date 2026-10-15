# PY-102 REPORT の付録 (#2883): 旧 §9・§10 の全文

`REPORT_PY102.md` の旧 §9 (測定 commit `0e42e1ea`) と旧 §10 (測定 commit `14802840`) と、末尾の旧 §10 (測定 commit `3aa3a256`) を、250 行上限のため分割移動したもの (内容は削除していない)。本文中の『§10』『本節』は旧番号。現在の正本は `REPORT_PY102.md` §10 (測定 commit `3aa3a256`)。

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

以下は `REPORT_PY102.md` の旧 §10 (測定 commit `3aa3a256`)。現在の正本は `REPORT_PY102.md` §10 (測定 commit `e3b67424`)。

## 10. main 取り込み後の再測定 (測定 commit `3aa3a256`)

- 取り込み。`origin/main` `c98d2c99` を merge (`3aa3a256`)。競合は `tests/provider_check.mjs` の 1 箇所だけ。main 側は PY-152 の `pe152` (arrangement 6 関数) を追加し、本 PR 側は `pe102` (`playlist.muteTrackLock`) を追加した。両方を集合に入れ、件数は main の `impl 109・unimpl 326` に `pe102` の +1 を加えて `impl 110・unimpl 325` (合計 435 は不変)。`fl_engine.c`・`fl_mock.mjs`・`flapi_table.json`・`flapi_table.py`・`gen/fl_table.c` は自動マージで衝突なし。
- 測定 commit: `3aa3a256` (コードを変えた最後の commit)。`git diff 3aa3a256 HEAD -- tools/python ':!tools/python/REPORT_PY102.md' ':!tools/python/REPORT_PY102_APPENDIX_2883.md'` は 0 行 (本節の追記だけが差分)。
- 素材: `fl-win64` の 5 block (`block00031_PE`・`block24429_DATA`・`block24430_DATA`・`block25159_DATA`・`block24618_DATA`) を `$RUNNER_TEMP/fl-win64/extracted/` へ展開 (2.911 s)。`FL_WIN64_DIR` でこれを指した。`fetch_inputs.sh` で `work/` を作成 (stubs は git clone)。`toolchain-emsdk` 素材は本 run に無い。
- emsdk: 上流 `emsdk install 6.0.12` を導入して `activate` し、[EMSDK] の既定位置へ symlink した (`build_cpython_wasm.sh` が既定位置を直書きするため)。CPython wasm は本 run で作成 (22:26:30 → 22:31:05、4 分 34.650 秒、exit 0。CPython 側のソースは変えていない)。
- 環境: GitHub Actions runner (4 コア)。`uptime` の load average は 22:25:05 に `0.24 0.17 0.07`、検証の最後 (22:33:01) に `0.56 1.23 0.71`。

| 検証 | 実行 | 結果 | 所要 |
|---|---|---|---|
| provider wasm | `EMSDK_ENV=… bash provider/build.sh` | flprov.wasm 59,267 B。fl_table.c 435 関数・ハンドラ 110 | 1.322 s |
| flpy link (表の再生成を含む) | `FL_WIN64_DIR=… EMSDK_DIR=… bash build_flpy.sh` | flpy.wasm 5,924,680 B。再生成 3 ファイル差分 0 (`git status` が空) | 7.173 s |
| provider ABI | `node tests/provider_check.mjs` | functions 435・implemented 110・unimplemented 325・mcp_static 60・PASS | 0.387 s |
| playlist 差分 | `node tests/playlist_diff.mjs` | calls 23・diffs 0・mock 状態 8 段・PASS | 1 s 未満 |
| mixer 差分 | `node tests/mixer_diff.mjs` | calls 59・diffs 0・PASS | 1 s 未満 |
| channels 差分 | `node tests/channels_diff.mjs` | calls 161・diffs 0・PASS | 1 s 未満 |
| device 差分 | `node tests/device_diff.mjs` | calls 8・diffs 0 (rejects 4・midi_out 5)・PASS | 1 s 未満 |
| general 差分 (main 由来) | `node tests/general_diff.mjs` | calls 25・diffs 0・PASS | 1 s 未満 |
| 48 tools (mock) | `node tests/all_tools.mjs` | 48/48・soft_error 0・raised 0・host_calls 37,425 | 2 s |
| 48 tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48・host_calls 37,425・callback_roundtrip true | 3 s |
| 表の再生成・ネガコン | `FL_WIN64_DIR=… bash tests/flapi_table_check.sh` | 正常系の差分 0/3・win_pair 388・ネガコン 6/6 PASS・fail 0 | 2 s |
| kwsig 照合 | `python3 tests/kwsig_check.py` | OK | - |
| kwsig 束縛 | `python3 tests/kwsig_bind_check.py` | PASS (103 関数・6,122 ケース・misbind 0・mismatch 0) | - |
| 引数個数 (before = `origin/main` `c98d2c99` の表 / after = `analysis/flapi/flapi_table.json`) | `python3 analysis/flapi/sig_arity_check.py <main の表> analysis/flapi/flapi_table.json` | before 対象 274・一致 274・不一致 0 / after 対象 274・一致 274・不一致 0。引数個数が変わった関数 0 件 | - |
| 実害の実測 (§3-2) | `node tests/sig_arity_probe.mjs` | kwsig_targets 24・implemented 8・unimplemented 16・fails 0・PASS | - |

- 件数の差: handler 104 (`14802840`) → 110 は main の PY-152 `pe152` (arrangement 6 件) の取り込み分。
- 未解決 (§5) は不変: 準備判定 (#2959)・追加引数の意味論 (#2950)・kwlist 無しの名前と書式 (#2952)。

以下は `REPORT_PY102.md` の旧 §10 (測定 commit `e3b67424`)。現在の正本は `REPORT_PY102.md` §10 (測定 commit `8ceec7c9`)。

## 10. main 取り込み後の再測定 (測定 commit `e3b67424`)

- 取り込み。`origin/main` `4b81e78a` を merge (`e3b67424`)。競合は `tests/provider_check.mjs` の 1 箇所だけ。main 側は PY-121 (#2982) の `pe121_2982` (ui 表示・メニュー 6 関数) を追加した。両方を集合に入れ、件数は main の `impl 115・unimpl 320` に `pe102` の +1 を加えて `impl 116・unimpl 319` (合計 435 は不変)。`fl_engine.c`・`fl_mock.mjs`・`provider/build.sh` は自動マージで衝突なし。
- 前回の測定 (`3aa3a256`・`origin/main` `c98d2c99` の取り込み後) の全文は `REPORT_PY102_APPENDIX_2883.md` へ分割移動した (250 行上限)。
- 測定 commit: `e3b67424` (コードを変えた最後の commit)。`git diff e3b67424 HEAD -- tools/python ':!tools/python/REPORT_PY102.md' ':!tools/python/REPORT_PY102_APPENDIX_2883.md'` の範囲は、`origin/main` `79d5e7c8` を取り込んだ merge `201f70a1` の分 (main 由来の追加 3 件: `analysis/py99_*.py` 2 本と `REPORT_PY99_APPENDIX.md`・#2874) だけ。検証範囲 (`git diff e3b67424 HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis/flapi tools/python/analysis/flapi_table.py`) は 0 行。
- 素材・emsdk・CPython: `fl-win64` の 5 block を `$RUNNER_TEMP/fl-win64/extracted/` に展開 (`FL_WIN64_DIR`)。emsdk 6.0.12 は [EMSDK] の既定位置へ symlink した。CPython wasm は `3aa3a256` の run で作成した出力 (`work/`・gitignore) を使った。`c98d2c99`→`4b81e78a` の間に `tools/python/src`・`build_cpython_wasm.sh`・`fetch_inputs.sh` の変更は 0 件 (`git diff --stat`)。
- 環境: GitHub Actions runner (4 コア)。`uptime` の load average は 22:36:17 に `0.39 0.76 0.61`、22:36:33 に `0.78 0.83 0.64`。

| 検証 | 実行 | 結果 | 所要 |
|---|---|---|---|
| provider wasm | `EMSDK_ENV=… bash provider/build.sh` | flprov.wasm 59,830 B。fl_table.c 435 関数・ハンドラ 116 | 1.020 s |
| flpy link (表の再生成を含む) | `FL_WIN64_DIR=… EMSDK_DIR=… bash build_flpy.sh` | flpy.wasm 5,924,680 B。再生成 3 ファイル差分 0 (`git status` が空) | 7.361 s |
| provider ABI | `node tests/provider_check.mjs` | functions 435・implemented 116・unimplemented 319・mcp_static 60・PASS | 0.390 s |
| playlist 差分 | `node tests/playlist_diff.mjs` | calls 23・diffs 0・mock 状態 8 段・PASS | 0.051 s |
| mixer 差分 | `node tests/mixer_diff.mjs` | calls 59・diffs 0・PASS | 0.051 s |
| channels 差分 | `node tests/channels_diff.mjs` | calls 161・diffs 0・PASS | 0.055 s |
| device 差分 | `node tests/device_diff.mjs` | calls 8・diffs 0 (rejects 4・midi_out 5)・PASS | 0.050 s |
| general 差分 (main 由来) | `node tests/general_diff.mjs` | calls 25・diffs 0・PASS | 0.052 s |
| ui 表示・メニュー 差分 (main 由来・#2982) | `node tests/ui_display_diff.mjs` | ok_calls 12・bad_calls 11・diffs 0・PASS | - |
| 48 tools (mock) | `node tests/all_tools.mjs` | 48/48・soft_error 0・raised 0・host_calls 37,425 | 1.977 s |
| 48 tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48・host_calls 37,425・callback_roundtrip true | 2.265 s |
| 表の再生成・ネガコン | `FL_WIN64_DIR=… bash tests/flapi_table_check.sh` | 正常系の差分 0/3・win_pair 388・ネガコン 6/6 PASS・fail 0 | 2.339 s |
| kwsig 照合 | `python3 tests/kwsig_check.py` | OK | - |
| kwsig 束縛 | `python3 tests/kwsig_bind_check.py` | PASS (103 関数・6,122 ケース・misbind 0・mismatch 0) | 0.099 s |
| 引数個数 (before = `origin/main` `4b81e78a` の表 / after = `analysis/flapi/flapi_table.json`) | `python3 analysis/flapi/sig_arity_check.py <main の表> analysis/flapi/flapi_table.json` | before 対象 274・一致 274・不一致 0 / after 対象 274・一致 274・不一致 0。引数個数が変わった関数 0 件 | - |
| 実害の実測 (§3-2) | `node tests/sig_arity_probe.mjs` | kwsig_targets 24・implemented 8・unimplemented 16・fails 0・PASS | - |

- 件数の差: handler 110 (`3aa3a256`) → 116 は main の PY-121 `pe121_2982` (6 件) の取り込み分。
- 未解決 (§5) は不変: 準備判定 (#2959)・追加引数の意味論 (#2950)・kwlist 無しの名前と書式 (#2952)。

以下は `REPORT_PY102.md` の旧 §10 (測定 commit `8ceec7c9`)。現在の正本は `REPORT_PY102.md` §10 (測定 commit `ac73210e`)。

## 10. main 取り込み後の再測定 (測定 commit `8ceec7c9`)

- 取り込み。`origin/main` `91610209` を merge (`8ceec7c9`)。競合は `tests/provider_check.mjs` の 1 箇所だけ。main 側は PY-96 (#2832) の `pe96` (arrangement の選択範囲 4 関数) を追加した。両方を集合に入れ、件数は main の `impl 119・unimpl 316` に `pe102` の +1 を加えて `impl 120・unimpl 315` (合計 435 は不変)。`fl_engine.c`・`fl_mock.mjs`・`flapi_table.py`・`gen/fl_table.c` は自動マージで衝突なし。
- 測定 commit: `8ceec7c9` (コードを変えた最後の commit)。本節の追記だけを後続の commit で加える。`git diff 8ceec7c9 HEAD -- tools/python ':!tools/python/REPORT_PY102.md' ':!tools/python/REPORT_PY102_APPENDIX_2883.md'` は 0 行。
- 前回の測定 (`e3b67424`) の全文は `REPORT_PY102_APPENDIX_2883.md` へ移した。
- 素材: `fl-win64` の 5 block (`block00031_PE`・`block24429_DATA`・`block24430_DATA`・`block25159_DATA`・`block24618_DATA`) を `$RUNNER_TEMP/fl-win64/extracted/` へ展開 (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 extracted/<上の 5 件>`)。`FL_WIN64_DIR` でこれを指した。`fetch_inputs.sh` で `work/` を作成。emsdk は上流 `emsdk install 6.0.12` を [EMSDK] の既定位置に導入して `activate` した (`toolchain-emsdk` 素材は本 run に無い)。
- CPython wasm: `build_cpython_wasm.sh` で作成 (exit 0・4m24.633s。本 run で作成。CPython 側のソースは変えていない)。
- 環境: GitHub Actions runner (4 コア)。開始時の `uptime` の load average は `0.21 0.20 0.09` (22:52)、検証後は `0.71 1.33 0.77` (22:59)。並列 1 本。

| 検証 | 実行 | 結果 | 所要 |
|---|---|---|---|
| provider wasm | `bash provider/build.sh` | flprov.wasm 60,001 B。fl_table.c 435 関数・ハンドラ 120 | 1.318 s |
| flpy link (表の再生成を含む) | `FL_WIN64_DIR=… EMSDK_DIR=… bash build_flpy.sh` | flpy.wasm 5,924,680 B。再生成 3 ファイル差分 0 (`git status` が空) | 7.059 s |
| flpy static (fulltext 用) | `bash build_flpy_static.sh` | flpy_static.wasm 5,972,552 B | 6.539 s |
| provider ABI | `node tests/provider_check.mjs` | functions 435・implemented 120・unimplemented 315・mcp_static 60・PASS | - |
| playlist 差分 | `node tests/playlist_diff.mjs` | calls 23・diffs 0・mock 状態 8 段・PASS | - |
| mixer 差分 | `node tests/mixer_diff.mjs` | calls 59・diffs 0・PASS | - |
| channels 差分 | `node tests/channels_diff.mjs` | calls 161・diffs 0・PASS | - |
| device 差分 | `node tests/device_diff.mjs` | calls 8・diffs 0 (rejects 4・midi_out 5)・PASS | - |
| general 差分 (main 由来) | `node tests/general_diff.mjs` | calls 25・diffs 0・PASS | - |
| arrangement 差分 (main 由来) | `node tests/arrangement_diff.mjs` | calls 25・diffs 0・PASS | - |
| arrangement 選択範囲 (main 由来・#2832) | `node tests/arrangement_selection_diff.mjs` | calls 8・diffs 0・PASS | - |
| screen 差分 (main 由来) | `node tests/screen_diff.mjs` | calls 32・diffs 0・PASS | - |
| ui 状態 / 表示・メニュー (main 由来) | `node tests/ui_state_diff.mjs`・`node tests/ui_display_diff.mjs` | calls 12・diffs 0・PASS / ok_calls 12・bad_calls 11・diffs 0・PASS | - |
| transport / ui / ilmcp / midi path | `node tests/transport_diff.mjs`・`ui_diff.mjs`・`ilmcp_diff.mjs`・`midi_path_diff.mjs` | calls 7・diffs 0 / calls 17・diffs 0 / calls 32・diffs 0 / cases 30・diffs 0 | - |
| 48 tools (mock) | `node tests/all_tools.mjs` | 48/48・soft_error 0・raised 0・host_calls 37,425 | - |
| 48 tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48・soft_error 0・raised 0・host_calls 37,425・callback_roundtrip true | - |
| 静的経路 | `node tests/static_check.mjs` | tool 別差 0/48・STATIC CHECK OK | - |
| 全文 3 経路 | `node tests/fulltext_parity.mjs` | FULLTEXT PARITY OK (ネガコン: 全文比較が検出・先頭 160 字ゲートは非検出) | - |
| 表の再生成・ネガコン | `FL_WIN64_DIR=… bash tests/flapi_table_check.sh` | 正常系の差分 0/3・fail 0 | - |
| kwsig 照合 | `python3 tests/kwsig_check.py` | OK | - |
| kwsig 束縛 | `python3 tests/kwsig_bind_check.py` | PASS | - |
| 引数個数 (before = `origin/main` `91610209` の表 / after = `analysis/flapi/flapi_table.json`) | `python3 analysis/flapi/sig_arity_check.py <main の表> analysis/flapi/flapi_table.json` | before 対象 274・一致 274・不一致 0 / after 対象 274・一致 274・不一致 0。引数個数が変わった関数 0 件 | - |
| 実害の実測 (§3-2) | `node tests/sig_arity_probe.mjs` | kwsig_targets 24・fails 0・PASS | - |

- 件数の差: handler 116 (`e3b67424`) → 120 は main の PY-96 `pe96` (4 件) の取り込み分。`pe102` (1 件) は前回と今回の両方に含まれる。
- 未解決 (§5) は不変: 準備判定 (#2959)・追加引数の意味論 (#2950)・kwlist 無しの名前と書式 (#2952)。
