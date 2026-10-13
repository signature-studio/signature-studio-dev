# H8 ブラウザ実機 probe — REPORT

対象: `[HB-H8]` (#101)。OTT 生成チェーンに依存しない最小 wasm (`add(i32,i32)->i32`, 手組み 41 B) で、
H8 の 3 機構を headless Chrome 154 (`tools/runtime/lib/chrome.mjs`) 上で実測する。

実行: `node tools/hostbridge/h8/run_h8.mjs --out <json>` (約 15 s)。

## 結果 (commit HEAD で再現)

| 項目 | 内容 | 判定 |
|---|---|---|
| C1 | main thread で同期 `WebAssembly.Instance` 生成、`add(2,3)=5` | PASS (生成 25.0 ms, 初回のモジュール解決込み) |
| C2 | Worker 内で同期 `WebAssembly.Instance` 生成、`crossOriginIsolated=true`・`SharedArrayBuffer` 利用可 | PASS (生成 0.125 ms, 同じ小 module) |
| C3 | SAB + `Atomics.wait`/`notify` の RPC で Worker の wasm を 1000 回呼び、全件一致 | PASS (167.6 ms, 約 168 µs/call, `waitAsync` 経由) |
| C4 | AudioWorklet (`ring-reader`) を配置、Worker が SAB ring に 65536 sample を書き、worklet が消費 | PASS (consumed 65536/65536, 総和一致 2147450880, process 517 回, sampleRate 44100, state running) |

## 範囲と未検証

- 検証したのは**機構**のみ。OTT (数 MiB の lift 済み wasm・864 MiB 予約・375 import) の
  同期 instance 生成は未検証 (`tools/hostbridge/lowbase/multi/run_chrome.mjs` の土台は、
  前提 artifact `ott_hb.cjs` / `bal_hb.cjs` が無く起動不可)。
- AudioWorklet は headless Chrome の既定 audio sink 上での実測。実デバイス出力は未検証。
- RPC のレイテンシは 1 呼出 168 µs (main ↔ worker)。リアルタイム音声 (128 frame @44.1k ≒ 2.9 ms) に対する
  実 plugin 呼出の予算評価は未実施 (OTT 実処理時間を含まない)。
