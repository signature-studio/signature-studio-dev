# RT-9 (#127) 付録: 音声込みの Firefox 測定

本文は [`REPORT.md`](REPORT.md) の RT-9 節。検証起点 `c846e5c5` (wrapper を追加したコミット)。probe 本体 (`tools/runtime/probe/run_features_firefox.mjs`・`features.js`) は `26f90ada` から変更なし。

## 手順
`bash tools/runtime/probe/run_features_firefox_audio.sh` → `tools/runtime/work/features_result_firefox.json`。
- 既存の pulse が無いときだけ、仮想 PulseAudio null sink (`module-null-sink`) を起動する。終了時は、自分が起動した pulse だけを pidfile の PID で止める。
- 非 headless を `xvfb-run -a` で動かす (Worker 内 WebGL2 は headless では判定できないため)。
- 要件: `pulseaudio` `pulseaudio-utils` `xvfb-run`。runner では `sudo apt-get install -y pulseaudio pulseaudio-utils` で導入した (pulseaudio 16.1, 2026-10-14)。

## 実測 (runner 4 vCPU、Firefox 157.0、コミット `c846e5c5` を wrapper 経由で実行)

| 項目 | run1 | run2 | 参照: sink 無し (同一 session の negative control、`run_features_firefox.mjs` を Xvfb で実行) |
|---|---|---|---|
| wall / 開始時 loadavg | 33.5 s / 0.55 | 42.6 s / 0.94 | 47.2 s / 1.94 |
| `audio.context` | running | running | `ERR: step timeout 20s (hang)` |
| AudioWorklet (hello / waitOk / process 呼出) | true / allowed / 201 | true / allowed / 201 | 到達せず (AudioContext の step で停止) |
| 200 block の時間 (ms) | 584 | 589 | — |
| Worker 内 WebGL2 | WebGL 2.0 | WebGL 2.0 | WebGL 2.0 |
| 4 worker atomic add | 4,000,000 一致 (60.4 ms) | 4,000,000 一致 (69.9 ms) | 4,000,000 一致 |
| exit | 0 | 0 | 0 |

- 結果 JSON に step の hang・想定外の ERR は無し。唯一の `ERR` は既知の IDB `DataCloneError` (`WebAssembly.Module` は IDB に保存できない。前回までと同じ)。
- **headless 参考 (1 回)**: sink を立てた状態で `node tools/runtime/probe/run_features_firefox.mjs` (headless 既定)。`audio.context` running、AudioWorklet process 呼出 207、200 block 596 ms、Worker WebGL2 は null (headless に GL 無し)、atomic 4,000,000 一致 (67.2 ms)。probe は `c846e5c5` と同一内容。

## 判定
- Firefox の AudioContext・AudioWorklet が止まる原因は音声バックエンドの不在と切り分けた。sink を与えれば headless でも Xvfb でも動く。前回の ALSA null PCM 設定 (`ALSA_CONFIG_PATH`) では解決しなかった。
- 未測定: 実音声デバイス (ハードウェア) での挙動。仮想 sink は遅延・underrun の実機特性を再現しない。
- Safari は変わらず未測定。

## WebKit 参考値 (Playwright 同梱 WebKit 26.0・Linux)

**Safari 実機ではない**。Playwright 同梱の WebKit (build 2215、WebKit 26.0) を Linux runner で動かした参考値。Safari の機能フラグ・UA と同一とは限らないため、Safari の可否の判定には使わない。検証起点 `d010b5d7` (probe を追加したコミット。以後 `tools/runtime/probe` と `tools/runtime/lib` は変更なし)。

手順:
- `playwright-core@1.56.1` を repo 外の作業ディレクトリに入れる (repo の `package.json` は変更しない)。
- `npx playwright@1.56.1 install --with-deps webkit` で WebKit 26.0 を取得し、依存を `sudo apt` で導入 (2026-10-14 の runner で成功)。PR #433 では依存不足で導入できなかったが、今回は `--with-deps` で導入できた (前回と同じ手順かは未確認)。
- `PLAYWRIGHT_CORE=<作業dir>/node_modules/playwright-core/index.mjs node tools/runtime/probe/run_features_webkit.mjs` → `tools/runtime/work/features_result_webkit.json`。

実測 (`d010b5d7`、3 回、全て exit 0、wall 2.35〜2.36 s、開始時 load 0.13〜0.15)。3 回で同値。

| 項目 | Chromium 154 / Firefox 157 (REPORT.md RT-9 本文) | WebKit 26.0 (Linux・参考) |
|---|---|---|
| wasm validate: memory64 / multi_memory / relaxed_simd | true (両者) | false / false / false |
| wasm validate: simd・threads・bulk・ref types・tail_call・extended_const・eh・gc・shared_everything | true | true |
| JSPI (`WebAssembly.promising` / `Suspending`) | function | undefined |
| `new WebAssembly.Memory({address:"i64"})` と mem64 系 5 項目 | 生成可 | 未対応 (BigInt 変換エラー) |
| 4 worker atomic add (期待 4,000,000) | 一致 (Firefox 86.5〜96 ms / Chromium 146 ms) | 一致 (61.7〜68.6 ms) |
| AudioContext / AudioWorklet | Firefox は仮想 sink があるときのみ running | running・hello・process 201 回 (sink 無しで動作) |
| WebGPU / File System Access / WebHID | Firefox は undefined | undefined |
| Worker OffscreenCanvas 2D | 可 | 可 (255) |
| Worker WebGL2 | Firefox は Xvfb 非 headless で可 | null (headless では判定不能。未解決) |
| OPFS (`navigator.storage.getDirectory`) | 可 | `navigator.storage` 自体が無い (ERR) |
| `ArrayBuffer(8GiB)` | Firefox 可 / Chromium 失敗 | ERR length too large |

判定 (Safari 入力としての読み方):
- Playwright WebKit 26.0 では **memory64 と JSPI が無い**。Chromium / Firefox と違い、フォールバック設計 (`DESIGN.md §4.1`) では JSPI 無しの経路 (`Atomics.wait` + SAB ring) と wasm32 (4GiB 上限) だけで成立させる必要がある可能性が高い。ただし Safari 実機が同じかは未確認。
- AudioWorklet は WebKit では仮想 sink なしで動いた。Firefox の sink 依存は Firefox 固有の事情と見られる。

未解決 (起票先: #127 を open のまま維持。実機依頼):
- Safari 実機の `window.__result` (未達)。
- WebKit の Worker 内 WebGL2 (headless では null。Xvfb 非 headless での再測定は未実施)。
- `DESIGN.md §4.1` の確定 (Safari 実機結果が入力)。
