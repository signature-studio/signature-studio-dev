# PY-4846 (#4846・#3839 の子 B): getLinkedValue・getLinkedInfo・getLinkedParamName・getLinkedValueString の index == -1 経路を PE 確定して実装 (index ≥ 0 は未確定)

親: #3839 (子 A #4845 とは独立に進めた。index ≥ 0 の残りは子 #4865)
既知類型との関係: 該当なし (lift 作業ではない)
製品 KPI: 対象外 (起動・GUI に関わらない)

## 結論

- 4 関数の `index == -1` の経路を PE (`block00031_PE.bin`) で確定し、C provider と mock に実装した。
  - `getLinkedValue` (0xd75bc0): -1 → `-1.0`
  - `getLinkedInfo` (0xd75ed0): -1 → `-1`
  - `getLinkedParamName` (0xd75de0): -1 → status `-8` (Plugin not valid)
  - `getLinkedValueString` (0xd75c40): -1 → status `-8` (Plugin not valid)
- **index ≥ 0 は未確定のまま**。`0x1046a30`・`0x104d2b0`・`0x104f580`・`0x1051170`・`0x1050f90` は大きな switch または表の参照で、この run 内では全分岐を確定できなかった。推測で C に書かず、`device.getLinkedValue` 等は index ≥ 0 で `Unspecified error (not implemented: ...)` (code 2) を返す。
- index ≥ 0 の経路の PE 確定は本 issue の範囲外に縮小し、子 #4865 (親: #4846) に移した。issue 本文の受入は縮めた範囲で `Closes #4846`。

## 1. VA 表 (index == -1 の経路を確定した分。REPORT_PY215 §1 と同じ読み方)

| 関数 (fl_table 行) | 本体 VA | index == -1 の経路 (PE) | 実装の戻り値 |
|---|---|---|---|
| getLinkedValue (341・`f`) | 0xd75bc0 | 0xd75c08 で `-1.0` の定数へ (0xd75c28 を読んで -1.0 を確認 — REPORT_PY215 §1) | `fl_ret_d(-1.0)` |
| getLinkedInfo (339・`i`) | 0xd75ed0 | 0xd75f1c で -1 (REPORT_PY215 §1) | `fl_ret_i(-1)` |
| getLinkedParamName (340・`s`) | 0xd75de0 | 0xd75e25 `cmp [rbp+0x4c],-1` → 0xd75e6b `mov rax,-8` → 0xd75e72 → 0xd82c20 (逆アセンブルで再確認) | `fl_err(FL_E_PLUGIN)` |
| getLinkedValueString (342・`s`) | 0xd75c40 | 0xd75cca `mov rax,-8` → 0xd75cd1 → 0xd82c20 (逆アセンブルで再確認) | `fl_err(FL_E_PLUGIN)` |

index ≥ 0 の先 (未確定):

| 関数 | index ≥ 0 の先 | 状態 |
|---|---|---|
| getLinkedValue | 0x1051170 (index, 0x7fffffff, 1) → PyFloat | 0x1051170 未読 |
| getLinkedInfo | 0x1050f90 (index, &o1, &o2) の bool | 0x1050f90 の not-found 戻り未読 (二分探索表) |
| getLinkedParamName | 0x104f580 → 0x41c420 → 0x414000 → 文字列 | 0x104f580 は `switch` (cmp 0x40000001・0x80000000 ...) で未読 |
| getLinkedValueString | 0x1046a30 (index, 0, 2) → 0x104d2b0 → 0x41c420 → 0x414000 → PyUnicode | 0x1046a30 は frame 0x590 の大きな関数、0x104d2b0 は switch で未読 |

## 2. 実装

- `provider/fl_engine.c`: 4 関数を追加 (`LINK_UNIMPL` マクロで index ≥ 0 は未実装 error)。
- `host/fl_mock.mjs`: 同じ意味論 (-1 の戻り・status、index ≥ 0 は code 2 の未実装 error)。
- `tests/device_diff.mjs`: 4 関数 × index {-1, 0} の mock/C 照合。期待値 (`-1`・`code 8`・`code 2`) を明記。
- `tests/provider_expect/pe4846.json`: 新規タグ。`provider_check` の implemented 件数に 4 件を加える。

## 3. 未確定事項と仮置き

| 項目 | 扱い |
|---|---|
| index ≥ 0 の 4 関数全部 | 未実装 error (code 2)。確定した PE の経路として書いていない |
| 連動表の供給元・初期状態 | 未確定。REPORT_PY215 §3 の仮置き (空) と整合させるため、index ≥ 0 は何も返さない |
| getLinkedChannel (PY-215) の表 | 変更なし |

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| getLinkedValue・getLinkedInfo・getLinkedParamName・getLinkedValueString の index ≥ 0 経路 (0x1051170・0x1050f90・0x104f580・0x1046a30/0x104d2b0) | 4 関数の index ≥ 0 が未実装 (code 2) | 子 #4865 (親: #4846) |

## 5. 検証

測定 commit (コードを変えた最後の commit): `7dd729f03`。`git diff 7dd729f03 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本節の commit は REPORT と DOC_MAP だけ)。

素材: `fl-win64` を `tar --zstd -xf` で `$RUNNER_TEMP/py4846` に展開 (9.6 秒)、`toolchain-emsdk` を同じ先に展開 (2.7 秒)。`FL_WIN64_DIR=$RUNNER_TEMP/py4846`・`EMSDK_ENV=$RUNNER_TEMP/py4846/emsdk/emsdk_env.sh`。

| 検査 | コマンド | rc | 所要 | 結果 |
|---|---|---|---|---|
| 入力取得 | `bash fetch_inputs.sh` | 0 | 0.9 秒 | work/ の入力 |
| CPython wasm | `bash build_cpython_wasm.sh` | 0 | 3 分 31 秒 | python.wasm |
| flpy | `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | 0 | 数秒 | flpy.js/wasm |
| provider ビルド | `bash provider/build.sh` | 0 | 1.3 秒 | flprov.js/wasm・警告 0 |
| provider_check | `node tests/provider_check.mjs` | 0 | 0.31 秒 | functions 435・**implemented 228**・unimplemented 207・mcp_static 60・PASS |
| device_diff | `node tests/device_diff.mjs` | 0 | 0.04 秒 | calls 21・link_calls 9・rejects 13・linked_channel `[-1,null,null,-1,null,null]`・**diffs 0**・PASS |
| all_tools (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 0 | 1.3 秒 | total 48・**ok 48**・soft_error 0・raised 0・host_calls 37,425 |
| all_tools (JS mock) | `node tests/all_tools.mjs` | 0 | 1.3 秒 | total 48・**ok 48**・soft_error 0・raised 0・host_calls 37,425 |

所要・load: 逐次実行。provider_check 開始時の load average (1 分) は 2.29 (4 core)。

ネガティブコントロール: `host/fl_mock.mjs` の `device.getLinkedValue` の -1 の戻り値を -2 に変更 → `node tests/device_diff.mjs` は **rc 1** (差分 1 件: mock -2 / wasm -1 を検出)。元に戻し、`diffs 0`・PASS を確認した。
