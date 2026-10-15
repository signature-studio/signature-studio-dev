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
| getChannelIndex・getChannelMidiInPort | 実装済み (下の「追補 (#2805・実装)」)。未解決 2 件も同節 | #2805 (PY-89) |
| getGridBitWithLoop・isGridBitAssigned・getStepParam・getCurrentStepParam | loop の定義・`HELP WANTED`・step parameter 状態が stub / mock に無い。setStepParameterByIndex の残りは #2581 | #2808 (PY-90) |
| isHighLighted | 表示中の矩形 (`ui.crDisplayRect`) の状態が mock / C に無い (`crDisplayRect` 自体が未実装) | #1514 |
| isGraphEditorVisible | グラフエディタの可視状態が mock に無い (PY-40 と同系統) | #1514 (関連: #1529) |
| getActivityLevel | stub に数値の範囲・減衰の規則が無い。mock に activity の状態が無い | #1514 |
| getChannelPitch | 3 overload・mock に pitch 状態が無い | #1514 |
| getRecEventId | REC event ID の値を PE で確定する必要がある | #1514 |
| getSwing | 戻り値の書込み元が未確定 (REPORT_PY41 の PY-54 節) | #1514 (関連: #1828・#1911・#1912) |

## 追補 (#2805・実装): getChannelIndex・getChannelMidiInPort (PY-89)

親: #1514 (PY-36)。子: #2805。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift / IR 変換は行っていない)。

## 結論

- `channels.getChannelIndex` と `channels.getChannelMidiInPort` を C provider と mock に実装した。意味論は公開 stub と PE (fl-win64 `block00031_PE.bin`) の読解で決めた。
- 実装数: 77 → 79 (provider_check)。`channels_diff` の呼出し 107 → 122 (diffs 0)。
- 残る不確かさは 2 件 (下の未解決表)。どちらも mock の出力を変えうる。

## 意味論の根拠

- stub (IL-Group/FL-Studio-API-Stubs・commit `9b4c7fa`): `src/midi_controller_scripting/channels/__properties.py` :689 `getChannelIndex` (「group の index → global index」)、:649 `getChannelMidiInPort` (既定は未割当・-3 touch keyboard・-2 未割当・-1 typing keyboard・他は MIDI port)。stub に MIDI-in port の設定 API は無い (`channels/__init__.py` の export は getter 2 件のみ)。

| 関数 | fn_va | 引数 (fmt) | 範囲内の戻り値 | 範囲外 code | 既定値 |
|---|---|---|---|---|---|
| getChannelIndex | 0xd5bd60 | `i` (flags 1) | channel レコードの `+0x794` | -4 | なし |
| getChannelMidiInPort | 0xd5bcd0 | `i\|i` (index, useGlobalIndex 既定 0) | channel レコードの `+0x2f8` | -4 | -2 |

PE の読解 (`tools/python/analysis/py41_disasm.py` で逆アセンブル):

- getChannelIndex: `0 <= index <= nch-1` を検査 (nch は `[[0x88439a]+0x10]`)。範囲外は `mov rax, -4` の後に `0xd82c20` (エラー生成) へ進み、`cmp eax,-4 / je 0xd82d3c` で文字列を設定して NULL を返す。文字列は VA `0xd82e8c` の `Index out of range`。範囲内は `0xfe8bb0` で channel レコードを引き、`+0x794` を整数で返す。
- getChannelMidiInPort: index と useGlobalIndex を受け、`useGlobalIndex > 0` を flag として `0x1005730` を呼ぶ (flag 真は global 側の list、偽は group 側の list)。`0x1005730` が偽を返したら -4、真なら `+0x2f8` を返す。
- 既定値 -2: channel レコードの初期化と読める `0xfe976e` (前後で他の field を確保・既定値で埋める並び) が `mov dword ptr [rax+0x2f8], 0xfffffffe` (-2) と `+0x2fc = -1` を書く。stub の「channel は既定で未割当」と一致する。
- `0x123ce3a` も `+0x2f8 = -2` を書く (`0xfe8bb0` で channel を引いた後の書戻し。呼出し元は未特定)。
- `+0x2f8` と `+0x794` の書込み元の線形走査: `tools/python/analysis/py89_channel_fields.py` (capstone・`.text` 0xfa34b0 bytes・12.2 秒)。宛先が `[reg+0x2f8]` / `[reg+0x794]` の命令は 84 件で、スタック局所の同 offset を含む。channel レコードの書込みと同定できたのは上の 2 箇所 (`0xfe976e`・`0x123ce3a`) だけ。`+0x794` の書込み元は同定できていない (`0xffe370`・`0xec60ae` は setter らしいが未確定)。

## 実装 (C と mock 同一)

| 関数 | C (`provider/fl_engine.c`) | mock (`host/fl_mock.mjs`) | 根拠 |
|---|---|---|---|
| getChannelIndex | `CH(0)` の範囲検査の後 `_i` を返す (identity) | `arity(1,1)`・`ix`・`ch(i)`・`i` を返す | 全 channel が 1 グループに入る前提 (下の未解決 1) |
| getChannelMidiInPort | `CH(0)`・`A_INT(1,0)` で型検査・`-2` を返す | `arity(1,2)`・`ch(a[0])`・`argI(1)`・`-2` を返す | 公開 API に設定経路が無く、状態を持たない (下の未解決 2) |

- `useGlobalIndex` は未モデル (グループ無し・既存関数と同じ扱い)。範囲外は `CH` マクロの `Index out of range` (code 4) で、PE の -4 と一致。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `+0x794` が group→global の対応そのものかを PE で確定していない (書込み元を同定していない) | 2 グループ以上の project で getChannelIndex の結果が identity と違う可能性。mock は identity 固定 | #1514 (親・PY-36 の残り 6 関数と併せて扱う) |
| `0x123ce3a` の呼出し元が script から到達できるかが未確認 | 到達できるなら MIDI-in port は状態を持つ必要があり、定数 -2 の mock は誤り | #1514 (同上) |

## 測定

測定 commit: `8a2c1d27` (コードを変えた最後の commit。`git diff 8a2c1d27 HEAD -- tools/python/provider tools/python/host tools/python/tests` は本節の追記後も空)。素材は `oc_artifacts: fl-win64 toolchain-emsdk` で取得し、`fl-win64` の `block00031_PE.bin` と DATA block 4 本 (`block24429/24430/25159/24618`) を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf` 2.9 秒)。`toolchain-emsdk` は `[EMSDK]` (`EMSDK_ENV` 既定) を使用。`bash tools/python/fetch_inputs.sh` で `work/` の midi.py・utils.py 等を配置。

| 検査 | コマンド | 結果 (実時間) |
|---|---|---|
| C provider の build | `bash tools/python/provider/build.sh` | 成功・`fl_table.c: 435 関数, ハンドラ 79` (0.822 秒) |
| 件数・ABI | `node tests/provider_check.mjs` | PASS (functions 435・implemented 79・unimplemented 356・mcp_static 60)、0.341 秒 |
| mock と C の差分 | `node tests/channels_diff.mjs` | PASS (calls 122・diffs 0)、0.051 秒 |
| 48 tool (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok (soft_error 0・raised 0・host_calls 37425)、1.663 秒 |
| ネガティブコントロール | mock の getChannelMidiInPort の既定を -2 から -1 に変えて channels_diff | diffs 3 (in-range の 3 呼出し) で AssertionError (FAIL)。元に戻して PASS (calls 122・diffs 0) |
| 解析の再現 | `python3 tools/python/analysis/py89_channel_fields.py <PE.bin> 0x2f8 0x794` | 84 件 (12.2 秒) |

- 作業用ビルド (`dist/`・`work/` は gitignore): `tools/python/build_cpython_wasm.sh` 3 分 44 秒 (rc 0)、`FLPY_SKIP_TABLE=1 build_flpy.sh` 5.8 秒 (rc 0)。
- 負荷: 測定開始 `uptime` で load average 1.02 / 1.52 / 0.87 (4 core)。ビルド中は 2.69 / 1.81 / 0.90。
- 検証範囲: 2 関数の C / mock の値 (identity・-2・-4 と引数の型検査)。範囲外: 2 グループ以上の project、MIDI-in port の設定経路 (未解決 1・2)。
