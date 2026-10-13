自動生成: node tools/perf/p7/tables.mjs > tools/perf/p7/results/TABLES.md (入力 results/p7.jsonl)

## 環境

| cfg | version | CPU | nproc | loadavg(開始時) | wall s | crossOriginIsolated | SIMD |
|---|---|---|--:|--:|--:|---|---|
| chrome-headless | Google Chrome 154.0.8037.97 | AMD EPYC 7763 64-Core Processor | 4 | 0.57 | 25.2 | false | true |
| chrome-headful | Google Chrome 154.0.8037.97 | AMD EPYC 7763 64-Core Processor | 4 | 1.29 | 22.2 | false | true |
| firefox-headless | Mozilla Firefox 157.0 | AMD EPYC 7763 64-Core Processor | 4 | 1.11 | 45.5 | false | true |

## Worker compile / 初回呼出 / 定常 (各サイズ 3 反復の中央値; 反復ごとに別 salt)

| cfg | size | bytes | compile ms | instantiate ms | 初回 ws_process ms | 定常 µs/128f (区間平均 p50) | 区間平均 max µs |
|---|---|--:|--:|--:|--:|--:|--:|
| chrome-headless | small | 4788 | 0.4 | 0.10 | 0.40 | 37.50 | 59.4 |
| chrome-headless | mid | 941574 | 4.6 | 0.10 | 2.60 | 296.88 | 303.1 |
| chrome-headless | large | 33554442 | 16.2 | 0.70 | 6.00 | 596.87 | 603.1 |
| chrome-headful | small | 4788 | 0.4 | 0.10 | 0.50 | 37.50 | 90.6 |
| chrome-headful | mid | 941574 | 4.5 | 0.10 | 2.60 | 300.00 | 306.2 |
| chrome-headful | large | 33554442 | 16.4 | 0.80 | 5.90 | 596.87 | 606.2 |
| firefox-headless | small | 4788 | 1.0 | 0.00 | 0.00 | 31.25 | 93.8 |
| firefox-headless | mid | 941574 | 43.0 | 1.00 | 1.00 | 593.75 | 1031.3 |
| firefox-headless | large | 33554442 | 57.0 | 1.00 | 1.00 | 968.75 | 1156.3 |

## メインスレッド compile / 同期 compile 上限

| cfg | size | bytes | compileStreaming ms | compile(bytes) ms | 同期 new Module (main) |
|---|---|--:|--:|--:|---|
| chrome-headless | mid | 941574 | 115.8 | 4.6 | OK 5.4 ms |
| chrome-headless | large | 33554442 | 374.6 | 32.0 | NG RangeError: WebAssembly.Compile is disallowed on the main thread, if the buffer size is larger than 8MB. Use WebAssembly.compile, compile on a worker thread, or |
| chrome-headful | mid | 941574 | 11.0 | 4.7 | OK 4.7 ms |
| chrome-headful | large | 33554442 | 69.3 | 50.7 | NG RangeError: WebAssembly.Compile is disallowed on the main thread, if the buffer size is larger than 8MB. Use WebAssembly.compile, compile on a worker thread, or |
| firefox-headless | mid | 941574 | 21.0 | 17.0 | OK 19.0 ms |
| firefox-headless | large | 33554442 | 134.0 | 56.0 | OK 48.0 ms |

## 上限

| cfg | 関数 1,000,000 | 関数 1,000,001 | Memory 256p(16MiB)×≤400 | Memory 12288p(768MiB)×≤400 | module 1GiB | module 1GiB+1 |
|---|---|---|---|---|---|---|
| chrome-headless | OK 108.7 ms | NG CompileError: WebAssembly.compile(): functions count of 1000001 exceeds internal limit of  | 125 本 で失敗 | 125 本 で失敗 | OK 1501.5 ms | NG CompileError: WebAssembly.compile(): buffer source exceeds maximum size of 1073741824 (is  |
| chrome-headful | OK 118.0 ms | NG CompileError: WebAssembly.compile(): functions count of 1000001 exceeds internal limit of  | 125 本 で失敗 | 125 本 で失敗 | OK 1474.8 ms | NG CompileError: WebAssembly.compile(): buffer source exceeds maximum size of 1073741824 (is  |
| firefox-headless | OK 486.0 ms | NG CompileError: wasm validation error: at offset 29: too many functions | 400 本 (CAP 到達) | 400 本 (CAP 到達) | OK 3437.0 ms | NG CompileError: wasm validation error: at offset 0: module too big |

## Module の structuredClone / IndexedDB

| cfg | structuredClone(Module) | IndexedDB put(Module) |
|---|---|---|
| chrome-headless | true | false (DataCloneError: Failed to execute 'put' on 'IDBObjectStore': A WebAssembly.Module can not be serialized for storage.) |
| chrome-headful | true | false (DataCloneError: Failed to execute 'put' on 'IDBObjectStore': A WebAssembly.Module can not be serialized for storage.) |
| firefox-headless | true | false (DataCloneError: WebAssembly.Module object could not be cloned.) |

## 同一 URL (immutable) 再ロードの compileStreaming ms と code cache ディレクトリ

| cfg | round0 | round1 | round2 | 終了後 `Code Cache/wasm` or cache2 |
|---|--:|--:|--:|---|
| chrome-headless | 202.1 | 11.1 | 9.9 | index 24; index-dir/the-real-index 48 |
| chrome-headful | 11.2 | 8.3 | 9.7 | index 24; index-dir/the-real-index 48 |
| firefox-headless | 22.0 | 49.0 | 40.0 | entries/C5C0146E5424532DC13DB48F872E13D9E84FA393 13970; entries/C7F5AA44F61B5E3DB095096E80D00E5C32E7B840 17890; entries/C951348898EF27CAE1BD72C86918D034DA8C37D1 242798; entries/C99AC429851C6C93E48CB0807B7203E591F32AA6 105442; entries/C9E67F04255253DF82F32FBADCC1527BA1440A0C 68088; entries/CB54568336E96A7F6C7F3087A67A6A7BCDB9079B 13968 … |

## AudioWorklet (実 AudioContext 48 kHz, 約 2 s 駆動)

| cfg | 状態 | baseLatency ms | process() 回数 / 期待 | wall ms | 最大呼出間隔 ms | >10ms 間隔数 | >20ms 間隔数 | worklet 内 compile ms | Module 直 postMessage 例外 |
|---|---|--:|--:|--:|--:|--:|--:|--:|---|
| chrome-headless | ctx running | 10.02 | 748 / 750 | 2002 | 10 | 0 | 0 | 0 | false |
| chrome-headful | ctx running | 10.02 | 753 / 750 | 2002 | 14 | 3 | 0 | 2 | false |
| firefox-headless | ctx suspended | 0.00 | - / - | - | - | - | - | 10 | false |
