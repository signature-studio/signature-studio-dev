# PY-26 (#1137): channels / playlist の flapi を mock と差分検査

親: #941 (PY-21)。`patterns` は mock に意味論が無いため実装対象外 (下記)。

## 結論

- mock に意味論がある `channels` (20) と `playlist` (4) は C provider に既に全て実装済み。新規ハンドラは 0。
- 差分検査 `tests/channels_diff.mjs` (新規、53 呼出し) を追加。初回実行で mock と C の 6 件の差分を検出。
  mock 側が C の引数検査 (型 code 5・範囲 code 4) を省いていたため。`host/fl_mock.mjs` を C に揃えて差分 0。
- 検出力: `channelCount` に +1 を仕込むと 1 件の差分で exit 1 (FAIL)。仕込みを戻すと PASS。

## 測定

- 測定 commit: `dcdf96f0` (コードを変えた最後の commit)。worktree `ws-1137` の HEAD で計測。
- 環境: runner 4 core、node 22.23.3、emsdk 6.0.12。素材: fl-win64 (block25159/24429/24430/24618)・toolchain-emsdk。
- `bash provider/build.sh`: exit 0、ハンドラ 70 / 表 435。
- `build_cpython_wasm.sh`: exit 0、wall 4 分 47 秒 (287.9 秒)。`FLPY_SKIP_TABLE=1 build_flpy.sh`: exit 0。

| コマンド | 結果 | wall (ms) |
|---|---|---|
| `node tests/channels_diff.mjs` | calls 53、diffs 0、PASS | 49 |
| `node tests/transport_diff.mjs` | calls 7、diffs 0、PASS | 49 |
| `node tests/provider_check.mjs` | functions 435、implemented 70、unimplemented 365、PASS | 360 |
| `node tests/midi_script.mjs` | checks 29、failed [] | 892 |
| `node tests/ilmcp_diff.mjs` | calls 32、state_checks 9、diffs 0、PASS | 63 |
| `node tests/device_diff.mjs` | calls 7、rejects 4、diffs 0、PASS | 52 |
| `node tests/midi_path_diff.mjs` | cases 30、diffs 0、PASS | 56 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425 | 2114 |
| `node tests/all_tools.mjs` (mock) | 48/48 ok、host_calls 37,425 | 2210 |

計測時の load average: 0.46 (1 分)。

## 差分 (測定 commit 以降のコード差分)

`git diff dcdf96f0 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (コード差分 0)。HEAD 側の追加は `REPORT_PY26.md` のみ (commit `8d057b65`)。

## 受入条件の判定

- [x] mock に意味論がある channels / playlist の関数は C に実装済み (新規ハンドラ 0)。mock に意味論が無い `patterns` (31) ほかは #1336 へ分割。
- [x] `tests/channels_diff.mjs` が mock と diffs 0。
- [x] `node tests/provider_check.mjs` PASS (実装数 70 は変化なし)。
- [x] `FL_ENGINE=wasm node tests/all_tools.mjs` が 48/48 ok。

## 未解決

- mock に意味論が無い未実装が計 103 件 (channels 34・playlist 38・patterns 31)。実機の意味論を先に決める必要があるため本 issue の範囲外。起票先: #1336 (PY-32、親 #1137)。
