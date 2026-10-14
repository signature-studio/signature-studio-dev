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
