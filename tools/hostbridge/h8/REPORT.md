# H8 ブラウザ実機 probe — REPORT

対象: `[HB-H8]` (#101)。OTT 生成チェーンに依存しない最小 wasm (`add(i32,i32)->i32`, 手組み 41 B) で、
H8 の 3 機構を headless Chrome 154 (`tools/runtime/lib/chrome.mjs`) 上で実測する。

実行: `node tools/hostbridge/h8/run_h8.mjs --out <json>` (約 15 s)。

## 結果

実行 2 回 (コミット 26226a0f の HEAD 上)。いずれも RESULT PASS。

| 項目 | 内容 | 1 回目 | 2 回目 | 判定 |
|---|---|---|---|---|
| C1 | main thread で同期 `WebAssembly.Instance` 生成、`add(2,3)=5` | 生成 25.0 ms | 3.8 ms | PASS |
| C2 | Worker 内で同期 `WebAssembly.Instance`、`crossOriginIsolated=true`・SAB 利用可 | 0.125 ms | 0.125 ms | PASS |
| C3 | SAB + `Atomics.wait`/`notify` RPC で Worker の wasm を 1000 回呼び、全件一致 | 167.6 ms (168 µs/call) | 22.4 ms (22 µs/call) | PASS |
| C4 | AudioWorklet (`ring-reader`) 配置、Worker が SAB ring に 65536 sample を書き、worklet が消費 | consumed 65536/65536, sum 一致, process 517 | 同左 | PASS |

C3 の往復時間は実行間で約 7 倍ばらつく (headless 環境の負荷由来と推定。原因は未確定)。
予算判断には複数回の計測が必要。

## 範囲と未検証

- 検証したのは**機構**のみ。OTT (数 MiB の lift 済み wasm・864 MiB 予約・375 import) の
  同期 instance 生成は未検証 (`tools/hostbridge/lowbase/multi/run_chrome.mjs` の土台は、
  前提 artifact `ott_hb.cjs` / `bal_hb.cjs` が無く起動不可)。
- AudioWorklet は headless Chrome の既定 audio sink 上での実測。実デバイス出力は未検証。
- RPC のレイテンシは 1 呼出 168 µs (main ↔ worker)。リアルタイム音声 (128 frame @44.1k ≒ 2.9 ms) に対する
  実 plugin 呼出の予算評価は未実施 (OTT 実処理時間を含まない)。
