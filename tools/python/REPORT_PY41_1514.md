# PY-41 追補 (#1514): channels.getChannelType の実装と残り 12 関数の分割

親: #1514 (PY-36)。本体は `REPORT_PY41.md`。前段の実装 (5 関数) は PR #2746 (`REPORT_PY41.md` の「追補 (#1514・実装)」節)。
本ファイルは 250 行上限のため、本 run の追補を `REPORT_PY41.md` から分けた (既存の節は無変更)。

## 結論

- `channels.getChannelType` (fn_va 0xd5abc0・書式 `i|i`) を C provider と mock に実装した。意味論は公開 stub の型定数だけで決めた。
- 実装数: 76 → 77 (provider_check)。`channels_diff` の呼出し 98 → 107 (diffs 0)。
- 残り 12 関数のうち 6 関数を子 issue 2 件 (#2805・#2808) に分けた。残り 6 関数は #1514 に残す (下の表)。

## 意味論の根拠 (公開 stub・commit `9b4c7fa`)

- `src/midi_controller_scripting/channels/__properties.py` :529 `getChannelType(index, useGlobalIndex)`: 「channel rack の instrument の型」を `midi.CT_*` の定数で返す。
- `src/midi_controller_scripting/midi/__channel_types.py`: `CT_Sampler = 0` (Sampler channel)・`CT_Hybrid = 1` (generator plugin feeding internal sampler)・`CT_GenPlug = 2` (Generator plugin)・`CT_Layer = 3`・`CT_AudioClip = 4`・`CT_AutoClip = 5`。

## 実装

| 関数 | 実装 (C と mock 同一) | 根拠 |
|---|---|---|
| getChannelType | `plugin == "Sampler"` なら 0 (CT_Sampler)、他は 2 (CT_GenPlug) | Sampler channel は CT_Sampler。mock の 3 channel は Sampler 2 本と native generator「3x Osc」1 本 |

- 未モデル: CT_Hybrid (1)・CT_Layer (3)・CT_AudioClip (4)・CT_AutoClip (5)。mock に Layer / Audio clip / Automation clip の channel 種別が無い。`plugin` 名だけで分けるため、generator plugin 以外の種別は 2 に寄る。
- 範囲外 code: `CH(0)` の code 4 (`Index out of range`)。他の channel getter と同じ仮置き。PE での確認は未了。
- `useGlobalIndex` は未モデル (グループ無し・既存関数と同じ扱い)。

## 測定

測定 commit: `aee3cdd4` (コードを変えた最後の commit)。素材は `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk` で取得し、`fl-win64` の DATA block 4 本と PE を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf` 2.9 秒)。`toolchain-emsdk` は `[EMSDK]` (`EMSDK_ENV` 既定) を使用。

| 検査 | コマンド | 結果 (実時間) |
|---|---|---|
| C provider の build | `bash tools/python/provider/build.sh` | 成功・`fl_table.c: 435 関数, ハンドラ 77` (0.964 秒) |
| 件数・ABI | `node tests/provider_check.mjs` | PASS (functions 435・implemented 77・unimplemented 358・mcp_static 60)、0.422 秒 |
| mock と C の差分 | `node tests/channels_diff.mjs` | PASS (calls 107・diffs 0)、0.054 秒 |
| 48 tool (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok (soft_error 0・raised 0・host_calls 37425)、2.190 秒 |

- 作業用ビルド (`dist/`・`work/` は gitignore): `build_cpython_wasm.sh` 4 分 15 秒、`FLPY_SKIP_TABLE=1 build_flpy.sh` 6.3 秒 (測定 commit の直前の実行)。
- 負荷: 測定開始 `uptime` で load average 0.18 / 1.00 / 0.70、測定終了で 0.24 / 1.00 / 0.70 (4 core)。

## 残り 12 関数の分割 (本 run 後)

| 関数 | 状態 | 起票先 |
|---|---|---|
| getChannelIndex・getChannelMidiInPort | stub の既定値・定義はあるが、mock / C に group・MIDI 入力の状態が無い | #2805 (PY-89) |
| getGridBitWithLoop・isGridBitAssigned・getStepParam・getCurrentStepParam | loop の定義・`HELP WANTED`・step parameter 状態が stub / mock に無い。setStepParameterByIndex の残りは #2581 | #2808 (PY-90) |
| isHighLighted | 表示中の矩形 (`ui.crDisplayRect`) の状態が mock / C に無い (`crDisplayRect` 自体が未実装) | #1514 |
| isGraphEditorVisible | グラフエディタの可視状態が mock に無い (PY-40 と同系統) | #1514 (関連: #1529) |
| getActivityLevel | stub に数値の範囲・減衰の規則が無い。mock に activity の状態が無い | #1514 |
| getChannelPitch | 3 overload・mock に pitch 状態が無い | #1514 |
| getRecEventId | REC event ID の値を PE で確定する必要がある | #1514 |
| getSwing | 戻り値の書込み元が未確定 (REPORT_PY41 の PY-54 節) | #1514 (関連: #1828・#1911・#1912) |
