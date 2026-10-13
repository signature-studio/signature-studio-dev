# PY-8 (#80): MIDI 1 イベント当りの flapi 呼出し数・所要時間と遅いモードの切り分け

既知類型との関係: 該当なし (lift / 逆アセの欠陥類型ではない。性能計測のみ)。flapi の実体は mock (`fl_mock.mjs`) で、実 FLEngine wasm ではない。

## 結論

1. **MIDI CC 1 件 = flapi 呼出し 1 回。中央値 約 230〜245µs/イベント** (同梱 device script Forward CCs、`device.forwardMIDICC` 1 回)。flapi を呼ばない NoteOn の対照は中央値 約 149〜165µs。差の約 80〜100µs が flapi 1 回分で、残りは配送 (postMessage・Worker・Python 側の 3 callback 配送) の基礎コスト。
2. **遅いモードは RPC の wake 遅延では説明できない (Python・flapi を抜いた素の SAB 往復は単峰)**。素の往復は中央値 34〜44µs、2 倍超の遅い側は 0.2〜0.5%。bimodal (15µs / 100〜130µs) は本 runner では再現しなかった。
3. **Python 込みの往復は静的版で桁違いに速い**: 静的版の Python `channels.channelCount()` 中央値 0.53µs、Worker+SAB 版 約 39µs (約 74 倍)。PY-2 (静的リンク、§7d) は既に実装済みで、MIDI 1 件のコストは静的版では 1 µs 未満の桁に落ちると推定 (未計測。下の未解決)。

## 実測 (`tests/midi_event_bench.mjs`、`tests/sab_wake_diag.mjs`、`tests/static_bench.mjs`)

| 項目 | 値 (µs) | 条件 |
|---|---|---|
| MIDI CC 1 件 (flapi 1 回/件) | 中央値 230.0 (min 215.1 / max 268.9)、**flapi 呼出し 1.000/件** | 5000 件 × 5 試行、load 0.56 |
| MIDI NoteOn 1 件 (flapi 0 回/件、対照) | 中央値 149.3 (min 145.5 / max 156.9)、flapi 0 | 同上 |
| SAB 素往復 (Python なし、`host/rpc.mjs` そのまま) | 中央値 34.0〜44.1 (試行 5 回)、p90 37.7〜51.8、遅い側 (中央値の 2 倍超) 0.2〜0.5% | 20000 × 5、load 0.66 |
| 静的版 Python `channels.channelCount()` | 中央値 0.527 (min 0.514 / max 1.051) | `static_bench.mjs` 5 試行、load 0.51 |
| 静的版 C `fl_api_call` のみ | 中央値 0.017 | 同上 |
| Worker+SAB 版 `channelCount()` | 中央値 約 39 (min 39.06) | 同上 |

flapi 呼出し数は `flapiCalls.n` で、`engine.call` ラッパを数えた。MIDI 1 件は `OnMidiIn` → `OnMidiMsg` → `OnControlChange` の 3 callback を配送し、CC の中で `device.forwardMIDICC` が 1 回呼ばれる。

## 遅いモードの切り分け

- 仮説: 遅いモード (100〜130µs) は `Atomics.waitAsync` で眠った server が起きるまでの wake 遅延。
- 検証: `tests/sab_wake_diag.mjs` で Python・flapi を抜き、`host/rpc.mjs` の client/server だけを 20000 回 × 5 試行で計時。
- 結果: 単峰 (中央値 34〜44µs)。遅い側は 0.2〜0.5% で、bimodal は再現せず。**Python/flapi の処理量とは無関係に遅くなる経路は、素の RPC 単体では観測されなかった。**
- 判定: 既存 REPORT §5 の bimodal (15µs / 100〜130µs) は本 runner では再現しない。当時の負荷・環境の差によるものと推定。原因の確定には、負荷を変えた追試 (未実施) が必要。

## 検証範囲 / 範囲外

- 範囲内: Actions runner (4 core、node 22.23.3)、素材 `fl-win64` (MCPTools.pyc / midi.py / utils.py / device script は `fetch_inputs.sh` で配置)、CPython 3.12.1 wasm・flpy・provider・静的版をクリーンにビルド (`build_cpython_wasm.sh` 4 分 46 秒、`build_flpy.sh` rc=0、`build_flpy_static.sh` rc=0)。
- 範囲外: 実 FLEngine wasm への結線 (未実施)、headless Chrome、実 MIDI デバイス、実 FL の所要時間。所要時間は mock engine の JS 処理を含む。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| MIDI 1 件の静的版 (PY-2 リンク後) の所要時間は未計測 | 「1 µs 未満」は往復コストからの推定。配送経路の実測が必要 | #35 (親)。静的版の MIDI 配送計測は別 issue 候補 |
| bimodal (100〜130µs) の再現条件と原因 | 本 runner では出ない。負荷依存の可能性 | #80 の追試 (負荷を変えた複数回計測) |
| 実 FLEngine wasm への結線 | 実エンジンの flapi 処理時間は含まれない | #35 (親)。FLEngine 起動 (MS5) 完了後 |
