# PY-8 (#80): MIDI 1 イベント当りの flapi 呼出し数・所要時間と遅いモードの切り分け

既知類型との関係: 該当なし (lift / 逆アセの欠陥類型ではない。性能計測のみ)。flapi の実体は mock (`fl_mock.mjs`) で、実 FLEngine wasm ではない。

## 結論

1. **MIDI CC 1 件 = flapi 呼出し 1 回。中央値 230.0µs/イベント** (同梱 device script Forward CCs、`device.forwardMIDICC` 1 回)。flapi を呼ばない NoteOn の対照は中央値 149.3µs。差の約 80.7µs が flapi 1 回分で、残りは配送 (postMessage・Worker・Python 側の 3 callback 配送) の基礎コスト。値はすべて表の元計測 (load 0.56) のもの。
2. **遅いモードは RPC の wake 遅延では説明できない (Python・flapi を抜いた素の SAB 往復は単峰)**。素の往復の中央値は runner・load で変わる (元計測 34.0〜44.1µs、追試 17.8〜20.0µs / reviewer 追試 19.3〜21.0µs。条件は下表)。2 倍超の遅い側は元計測 0.2〜0.5%、追試 0.1〜1.7% (reviewer 0.2〜1.3%)。どの条件でも単峰で、bimodal (15µs / 100〜130µs) は再現しなかった。ただし呼出し間隔を入れると受け側が idle 後の wake で遅れ、遅い側の割合が増える (run 9、下の節)。遅さの大きさは計測時刻で数倍変わり、機構は部分的にしか切り分けられていない。
3. **Python 込みの往復は静的版で桁違いに速い**: 静的版の Python `channels.channelCount()` 中央値 0.53µs、Worker+SAB 版 約 39µs (約 74 倍)。PY-2 (静的リンク、§7d) は既に実装済みで、MIDI 1 件のコストは静的版では 1 µs 未満の桁に落ちると推定 (未計測。下の未解決)。

## 実測 (`tests/midi_event_bench.mjs`、`tests/sab_wake_diag.mjs`、`tests/static_bench.mjs`)

| 項目 | 値 (µs) | 条件 |
|---|---|---|
| MIDI CC 1 件 (flapi 1 回/件) | 中央値 230.0 (min 215.1 / max 268.9)、**flapi 呼出し 1.000/件** | 5000 件 × 5 試行、load 0.56 |
| MIDI NoteOn 1 件 (flapi 0 回/件、対照) | 中央値 149.3 (min 145.5 / max 156.9)、flapi 0 | 同上 |
| SAB 素往復 (Python なし、`host/rpc.mjs` そのまま) | 中央値 34.0〜44.1 (試行 5 回)、p90 37.7〜51.8、遅い側 (中央値の 2 倍超) 0.2〜0.5% | 20000 × 5、Actions runner・load 0.66 (元計測) |
| SAB 素往復 追試 (同コマンド、同 runner・load 0.68) | 中央値 17.8〜20.0 (試行 5 回)、p90 19.3〜21.9、遅い側 0.1〜1.7% | 20000 × 5、Actions runner、2026-10-13 再実行 (元計測と runner 差) |
| SAB 素往復 reviewer 追試 (同コマンド、別 runner・load 0.24) | 中央値 19.3〜21.0、遅い側 0.2〜1.3% | 20000 × 5、reviewer 報告値 (PR コメント) |
| 静的版 Python `channels.channelCount()` | 中央値 0.527 (min 0.514 / max 1.051) | `static_bench.mjs` 5 試行、load 0.51 |
| 静的版 C `fl_api_call` のみ | 中央値 0.017 | 同上 |
| Worker+SAB 版 `channelCount()` | 中央値 約 39 (min 39.06) | 同上 |

flapi 呼出し数は `flapiCalls.n` で、`engine.call` ラッパを数えた。MIDI 1 件は `OnMidiIn` → `OnMidiMsg` → `OnControlChange` の 3 callback を配送し、CC の中で `device.forwardMIDICC` が 1 回呼ばれる。

## 遅いモードの切り分け

- 仮説: 遅いモード (100〜130µs) は `Atomics.waitAsync` で眠った server が起きるまでの wake 遅延。
- 検証: `tests/sab_wake_diag.mjs` で Python・flapi を抜き、`host/rpc.mjs` の client/server だけを 20000 回 × 5 試行で計時。
- 結果: 単峰 (元計測の中央値 34〜44µs、表の追試・reviewer 追試では 17〜21µs)。遅い側は元計測 0.2〜0.5%、追試 0.1〜1.7%。bimodal は再現せず。**Python/flapi の処理量とは無関係に遅くなる経路は、素の RPC 単体では観測されなかった。**
- 判定: 既存 REPORT §5 の bimodal (15µs / 100〜130µs) は本 runner では再現しない。当時の負荷・環境の差によるものと推定。原因の確定には、負荷を変えた追試 (未実施) が必要。

## 負荷追試 (run 4 追記): 素の RPC と Python 込みの往復を負荷で比較

負荷は `while :; do :; done` を論理 4 コアの runner に載せて作る (4 本 = 1.0 相当、8 本 = 2 倍の過負荷)。負荷プロセスは各計測の後に終了させ、残留なしを確認した。

| 条件 | 計測 | 中央値 (µs) | 遅い側の比率 (中央値の 2 倍超) |
|---|---|---|---|
| 無負荷 (素の RPC) | `sab_wake_diag.mjs 20000 5` | 34.8〜36.1 | 0.3〜0.7% |
| 4 本負荷 (素の RPC) | 同上 | 27.4〜31.7 | 3.2〜10.6% |
| 8 本負荷 (素の RPC) | 同上 | 28.2〜30.3 | 6.2〜13.7% |
| 無負荷 (Python 込み) | `rtt_bench.mjs` | 36.1〜55.0 (n=500 のみ 55) | — |
| 8 本負荷 (Python 込み) 1 回目 | 同上 | 52.6〜113.4 | — |
| 8 本負荷 (Python 込み) 2 回目 | 同上 | 65.7〜100.4 | — |
| 無負荷 (Python 込み) 対照 | 同上 | 38.5〜53.9 | — |

- 数値は `rtt_bench.mjs` の 6 区間 (n=500・2000・2000・20000×3) のレンジ。素の RPC は 5 試行の中央値のレンジ。
- 負荷を上げると**素の RPC の遅い側の比率は増える (0.3〜0.7% → 3〜14%) が、中央値は 35µs → 28〜32µs と下がる (負荷で遅くならない)**。素の RPC 単体では 100µs 台の遅い峰は出ない。
- **Python 込みの往復は負荷で約 1.5〜2 倍になり、上側が 100µs 前後まで伸びる**。ただし 15µs 台の速い峰は今回も出ず、bimodal とは言い切れない (連続的に広がる分布)。
- 判定: 遅さは「負荷下で RPC の wake が遅れる」だけでは説明できない (素の RPC は負荷で遅くならない)。負荷で増えるのは Python 込み経路の方。原因の切り分け (Python 実行・flapi 処理・Worker のスケジューリングのどれか) は未了。
- 限界: 各条件は 1〜2 回。負荷の強さは 4 / 8 本の 2 段のみ。load average は前の負荷の減衰で無負荷の対照でも 6 前後が残り、「無負荷」は厳密には無負荷ではない。

## 静的版 (PY-2) の MIDI 1 件の配送時間 (run 3 追記、`tests/static_midi_bench.mjs`)

既知類型との関係: 該当なし (性能計測)。

| 項目 | 値 (µs/イベント) | 条件 |
|---|---|---|
| 静的版 MIDI CC 1 件 (device script 1 回実行) | 中央値 23.92 / 24.99 (2 回の実行、min 23.82〜24.48 / max 26.57〜27.10)、device 呼出し 1.000/件 | 20000 件 × 5 試行、flpy_static.wasm (node メインスレッド)、load 1.14 / 0.71 |
| 静的版 MIDI NoteOn 1 件 (対照、device 呼出し 0) | 中央値 24.54 / 25.27 (min 24.44〜25.18 / max 25.37〜25.59)、0 | 同上 |

受入 (1) の flapi 呼出し数: Python 計数のみ (`device.forwardMIDICC` 1.000/件)。C 経由の `fl_api_call` は未計測。所要時間は計測済み。

- 静的版 CC 1 件 24〜25µs は、Worker+SAB 版 CC 1 件 230.0µs (REPORT 上表、load 0.56) の約 1/9。
- CC と NoteOn の差 (CC − NoteOn) は両 run で同符号 (CC が小さい): run1 中央値 −0.62µs、run2 −0.28µs。ただし各 run の min–max 範囲が重なるため、device 呼出し 1 回の追加コストは本計測のノイズ以下で分離できない。
- **計測の限界 (重要)**: 静的版の C 側 (`provider/fl_engine.c`) には `device.*` の handler が無い。そのため本計測は `device.forwardMIDICC` を Python 側の計数スタブに差し替えた。よって (a) C の `fl_api_call` を経由しない、(b) 測っているのは「Python の配送 (`dispatch_script_midi`) + device script 実行」である。「flapi 1 回の C コスト」は `static_bench.mjs` の `c_only_us` (中央値 0.017µs) を参照。
- 比較時の注意: Worker+SAB 版 230µs は postMessage・Worker 往復を含み、静的版 23.9µs は含まない。両者の差はこの RPC 経路の分であり、flapi 呼出しそのものの差ではない。

再現: `cd tools/python && node tests/static_midi_bench.mjs 20000 5` (前提: `build_flpy_static.sh` 済み、`work/` に fetch_inputs.sh の出力)。

未解決 (本節): 静的版 C 側に `device.forwardMIDICC` を実装した上での計測 (provider handler 追加は `provider_check` の handler 数 60 を変えるため別 issue)。

## MIDI 1 件の内訳 (run 5 追記、`tests/midi_path_split.mjs`)

CC 1 件 (flapi 1.000/件) の所要時間を、mock engine ハンドラ内 (`handler_us`) と残り (`rest_us`) に分けて計測。

- 測定 1 (`tests/midi_path_split.mjs 5000 5`、1 run、JSON の `load` = 終了時 `/proc/loadavg` 2.19): 中央値 total 262.60µs / handler 0.84µs / rest 261.71µs、flapi 1.000/件。試行別 total: 288.78 / 262.60 / 274.19 / 254.59 / 218.78µs
- 測定 2 (`tests/midi_event_bench.mjs 5000 5`、測定 1 の直後の 1 run、JSON の `load` 1.64): CC 中央値 242.16µs (min 228.34 / max 278.98、flapi 1) / NoteOn 中央値 157.15µs (min 150.79 / max 158.05、flapi 0)
- 読み: flapi ハンドラ自体は 1µs 未満。測定 2 の CC と NoteOn の差 約 85.0µs が flapi 1 回の経路 (RPC 往復と呼出し側の Python 処理) に当たる。NoteOn 側の約 157µs は flapi を使わない Python 配送の基底。
- 比較の注意: 測定 1 と測定 2 は別プロセスで load (2.19 / 1.64) が揃っていない。比較できるのは測定 2 の CC と NoteOn の差 (同一 run) だけ。上の既存節の 230.0µs / 149.3µs (差 80.7µs) は load 0.56 の値で、本節とは load が違うため直接比べない。差がほぼ同程度 (80.7µs と 85.0µs) なのは偶然の一致で、1 run ずつのため誤差は未評価。
- 限界: 差分は NoteOn と配送経路が完全には同一でない前提の推定。素の RPC 往復は本節の計測対象外で、上の「素の SAB 往復」節の値 (中央値 34〜44µs、別 run) を参照する。bimodal は本 run では再現せず (測定 1 の試行の散らばりは 219〜289µs)。

## CC 1 件の RPC 往復 / flapi / Python の分離 (run 6 追記、`tests/midi_rpc_split.mjs`)

計測 HEAD: ebb1110b (計測スクリプト追加のみ。前後で `host/`・`src/` は変更なし)。
分け方: `rpc_rt` = 同一 Python プロセス内で `channels.channelCount()` loop と `_noop()` loop の 1 呼出し当り差分 (RPC 往復 1 回分)。`python` = CC total − flapi handler − rpc_rt (Python 配送 + device script 実行)。

| 項目 | 中央値 (µs) | 試行 (5 回) | 条件 |
|---|---|---|---|
| RPC 往復 1 回 (`rpc_rt`) | 29.58 | 29.32〜31.98 | 20000 呼出し × 5 試行 |
| CC 1 件 total (flapi 1.000/件) | 174.93 | 155.86〜197.76 | 5000 件 × 5 試行 |
| CC 1 件の flapi handler (mock engine) | 0.66 | — | `counted.call` 区間 |
| CC 1 件の Python 残り (`python`) | 143.79 | — | total − handler − rpc_rt |
| NoteOn 1 件 total (flapi 0、対照) | 106.31 | 104.35〜116.18 | 同上 |

- load: 終了時 `/proc/loadavg` 1.20 (計測前の run は 1.47)。
- commit 前の作業ツリー (同一コード) で先に 1 回計測 (load 1.47): rpc_rt 30.23 / CC total 178.39 / handler 0.59 / python 147.56 / NoteOn 118.59。傾向は HEAD と同じ。
- 読み: CC 1 件 (175µs) のうち RPC 往復は 1 回で約 30µs (約 17%)、flapi handler は 1µs 未満 (約 0.4%)。CC − NoteOn 差 約 69µs = RPC 往復 約 30µs + CC 固有の Python 処理 約 39µs (device script の CC 分岐と `device.forwardMIDICC` 前後の Python 処理)。
- 限界: (1) `rpc_rt` は `channelCount()` の関数本体 (channels モジュール内の Python 処理) を含む差分で、純粋な SAB 往復ではない。素の SAB 往復は上の「SAB 素往復」節 (34〜44µs / 17〜21µs、別 run) を参照。(2) bimodal (100µs 台の遅い峰) は本 run でも再現せず、単峰。(3) 実 FLEngine の flapi 処理時間は含まない。

## 呼出し間隔と idle 後の wake (run 9 追記、`tests/rpc_gap_diag.mjs`・`tests/rtt_gap_bench.mjs`)

計測 commit: 3753e1208 (計測スクリプト追加。以後のコード変更は無し。HEAD までのコード差分は下の「検証」の `git diff` 参照)。
連続呼出し (従来の計測) は受け側が常に起きている。実運用の MIDI は間隔をあけて届くため、呼出し間で受け側が idle になる条件を追加で計った。

- `rpc_gap_diag.mjs` (素の RPC): gap = 呼出し間の待ち。`sleep` は worker が `Atomics.wait` で眠る (worker も server も idle)、`spin` は worker が回し続ける (server だけ idle)。n=300 × 3 試行。
- `rtt_gap_bench.mjs` (Python 込み、flapi 1 回 = `channels.channelCount()`): gap = host の待ち。`sleep` は `setTimeout`、`spin` は host が回し続ける。1 呼出し = `py.run` 1 回 (postMessage 往復を含む基底 約 70µs)。

| 素の RPC 中央値 (µs、3 試行のレンジ) | 間隔 0 | 間隔 2ms | 間隔 5ms | 間隔 20ms |
|---|---|---|---|---|
| sleep (unpinned) | 18.9〜23.3 | 28.6〜38.0 | 38.4〜39.0 | 48.0〜64.8 |
| sleep の 60µs 超の割合 | 1〜2% | 2〜3% | 2〜5% | 9〜55% |
| spin (worker が回し続ける) | 19.0〜23.6 | 25.2〜26.8 | — | 42.9〜77.1 |
| spin の 60µs 超の割合 | 1〜1.3% | 1〜3% | — | 9〜75% |
| sleep・`taskset -c 0,1` | 19.2〜22.8 | 31.4〜37.7 | 38.2〜38.9 | 41.8〜62.0 |
| sleep・`taskset -c 0` (同一 CPU) | 13.8〜17.3 | 16.4〜21.5 | 23.9〜24.5 | 40.0〜90.2 (60µs 超 26〜96%) |

| Python 込み flapi 1 回 (µs、3 試行のレンジ) | 間隔 0 | 間隔 2ms | 間隔 20ms |
|---|---|---|---|
| sleep (host が待つ) | 113〜129 (150µs 超 9〜13%) | 110〜123 | 387〜427 (150µs 超 100%) |
| spin (host が回し続ける) | 66〜116 | — | 373〜389 (150µs 超 100%) |
| sleep の再測定 (n=200 × 2 試行) | 89〜91 | 115〜125 | 402〜405 |

連続呼出し (既存 `rtt_bench.mjs`、同じ HEAD): unpinned 20.2〜20.8 / `taskset -c 0` 16.0〜16.9 / `taskset -c 2` 15.9〜16.6 / `taskset -c 0,1` 21.4 (µs/呼出し、n=20000 区間)。

- **読み 1 (連続呼出しには遅い峰が出ない)**: 素の RPC の間隔 0 は全条件で中央値 13〜23µs、60µs 超は 1〜2%。従来の結論 (単峰) と一致する。
- **読み 2 (間隔で遅くなる)**: 間隔 20ms で中央値は連続時の約 2〜3 倍、60µs 超の割合は数〜数十%。この方向は別時刻の予備計測 (素の RPC 中央値 44〜53µs、Python 込み 129〜135µs、同じく間隔 20ms) を含め、全ての計測で一貫した。REPORT §5 の bimodal (速い 15µs / 遅い 100〜130µs) の遅い峰は、この「idle 後の wake」の条件と整合する。
- **読み 3 (大きさは時刻で変わる)**: 間隔 20ms の Python 込みは、同じ条件で 130µs (予備) と 400µs (本節) に分かれた。steal time (`/proc/stat` の steal 列) は計測中も 0 で、ホスト側の起床遅延かどうかは確認できない。**大きさの値は計測時刻に依存するので、絶対値として使わない。**
- **読み 4 (機構は部分的)**: worker を回し続けた対照 (spin) でも、間隔 20ms の遅れ (中央値 +20〜+60µs) は残る。このため、受け側 (main、`Atomics.waitAsync`) の idle 後の wake が寄与している。worker 側の寄与 (sleep と spin の差) は時刻によって符号が揃わず、確定できない。同一 CPU への固定は一貫して小さいとは言えない (本節の値は時刻で割れる)。
- **対策の候補 (未実施)**: 受け側の短時間 spin、または MIDI のバースト中だけ起きたままにする設計。本計測では有効性を確認していない。採否は PM 判断 (未解決表)。
- 検証 (run 9): 素材は `toolchain-emsdk` のみ (`/opt/emsdk` の emcc 6.0.12)。`build_cpython_wasm.sh` rc=0 (2 分 40 秒)、`FLPY_SKIP_TABLE=1 build_flpy.sh` rc=0 (4 秒)。runner は 4 core、node 22.23.3。
- 再現 (前提: `build_cpython_wasm.sh` と `FLPY_SKIP_TABLE=1 build_flpy.sh` 済み。fl-win64 は不要): `cd tools/python && node tests/rpc_gap_diag.mjs 300 3 0,2,5,20 sleep` / `node tests/rpc_gap_diag.mjs 300 3 0,2,20 spin` / `taskset -c 0,1 node tests/rpc_gap_diag.mjs 300 3 0,2,5,20 sleep` / `taskset -c 0 node tests/rpc_gap_diag.mjs 300 3 0,2,5,20 sleep` / `node tests/rtt_gap_bench.mjs 300 3 0,2,20 sleep` / `node tests/rtt_gap_bench.mjs 300 3 0,20 spin`。

## 検証範囲 / 範囲外

- 範囲内: Actions runner (4 core、node 22.23.3)、素材 `fl-win64` (MCPTools.pyc / midi.py / utils.py / device script は `fetch_inputs.sh` で配置)、CPython 3.12.1 wasm・flpy・provider・静的版をクリーンにビルド (`build_cpython_wasm.sh` 4 分 46 秒 (d36dbefe 時点の run)・4 分 03 秒 (HEAD 08c569ba の静的版検証 run)、`build_flpy.sh` rc=0、`build_flpy_static.sh` rc=0)。
- 範囲外: 実 FLEngine wasm への結線 (未実施)、headless Chrome、実 MIDI デバイス、実 FL の所要時間。所要時間は mock engine の JS 処理を含む。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| MIDI 1 件の静的版 (PY-2 リンク後) の所要時間は未計測 | 「1 µs 未満」は往復コストからの推定。配送経路の実測が必要 | #35 (親)。静的版の MIDI 配送計測は別 issue 候補 |
| bimodal (100〜130µs) の原因 | 連続呼出しでは 15µs 台の速い峰も 100µs 台の遅い峰も出ない。RPC 往復 (約 30µs)・flapi handler (1µs 未満)・Python 残り (約 144µs) の分離は run 6 で実施 (上の節)。呼出し間隔で遅い峰が出る方向は run 9 で確認 (機構は部分的) | #80 の後続 |
| idle 後の wake の機構 (受け側 main と worker のどちらが寄与するか、ホストの vCPU 起床か) | 対策 (受け側の短時間 spin 等) の採否が決まらない。spin 対照では受け側の寄与が残ったことまで | #80 の後続 (PM 判断。対策を入れるなら実装は別 issue) |
| idle 後の wake の大きさが計測時刻で数倍変わる | 絶対値は時刻依存。実 MIDI の呼出し間隔の分布も未計測 | #35 (親)。実 FLEngine 結線の計測に含める |
| 実 FLEngine wasm への結線 | 実エンジンの flapi 処理時間は含まれない | #35 (親)。FLEngine 起動 (MS5) 完了後 |
| SAB 素往復の中央値が runner・load で 2 倍ほど違う (元計測 34〜44µs / 追試 17〜21µs) | 絶対値は runner 依存。単峰の結論は両方で成立 | #80 の追試 (負荷を揃えた複数 runner 計測) |
