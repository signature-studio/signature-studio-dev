# AU-2 (#187) CI 代理指標の測定 (ubuntu runner)

親: `REPORT.md` §8。実機でしか測れない項目は [AU-22] (#2366) に分離済み。

## 1. 代理経路の検証 (PulseAudio null-sink) — 不成立

| 項目 | 値 |
|---|---|
| 環境 | ubuntu runner (4 vCPU, 15 GiB), `google-chrome 155.0.8059.39` (REPORT の 154 とは版が違う), PulseAudio 16.1 (apt 導入) |
| PulseAudio | `module-null-sink sink_name=ci_null` を起動 (`pactl info` の Default Sink = `ci_null`) |
| 比較 | `asio_sine_b256_d2` を同一ハーネス・同一 HEAD (`1ddc8512`) で 2 回 (fake シンク / PulseAudio 起動中) |

| 条件 | sampleRate | baseLatency | outputLatency | clock (Hz) | burst | T | 判定 |
|---|---|---|---|---|---|---|---|
| fake シンク (既定) | 48000 | 0.011625 s | 0.036 s | 47969.0 | 1152 | 1792 | PASS |
| PulseAudio null-sink 起動中 | 48000 | 0.011625 s | 0.036 s | 47971.0 | 1152 | 1792 | PASS |

**結論**: Chrome の `baseLatency` / `outputLatency` / `clock` は PulseAudio 起動の有無で変わらなかった (1 回ずつの比較)。報告値が fake シンクと同一のため、null-sink が Chrome の出力経路として使われたとは確認できない (原因は未切り分け)。よって P1〜P4 を null-sink の代理として扱う前提は成立していない。Firefox は `tools/audio/harness` が Chrome CDP 専用のため、同じ方法では測れない。

## 2. ベースライン `e2e.sh --quick` (main `1ddc8512`, 測定 commit = `1ddc8512`)

- 実行: `bash tools/audio/e2e.sh --quick`, `EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh`, `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`
- 結果: **43/44 PASS**, wall 266.9 s, load avg 開始 2.25 → 終了 0.42 (nproc 4)
- FAIL: `asio_ramp_b128_d2` — `underruns=1 silence=2688; ramp mismatches=162944/192384`。B=128 の ramp は本 run で再現。原因は未切り分け (負荷起因の疑い、未確認)。追跡先: 未起票 (§4)
- burst 分布 (quick, 48k): 512f 大半。96k は 1024f (`asio_sine_b256_96k`, `asio_sine_b512_96k`)。96k/B=256 の `burst_floor=4096` ネガコントロールは PASS (T=5376)

## 3. 未実施 (この run の時間内に収まらないため)

- フル `e2e.sh` (約 9 分 + ASIO COM 経路 約 3 分) と 30 分ソーク: 行列にすると 1 run の 58 分上限を超えるため未実施
- Firefox 行列: ハーネスが Chrome 専用
- Windows / macOS runner の仮想オーディオ workflow: 未着手 (権限・検証手段の確認が先)

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| null-sink 経由で Chrome の報告値が変わらない (§1) | CI で OS 経路を測る代理指標が成立しない | #187 (AU-2) 内で代替手段を再検討 |
| Firefox 行列がハーネス未対応 | 行列 {Chrome, Firefox} × {48k, 96k} の片側が未測定 | #187 |
| `asio_ramp_b128_d2` の FAIL (quick, 負荷起因の疑い) | 回帰判定の不安定さ | 未起票 (要切り分け) |
| 30 分ソーク (AU-10 null-sink 版) | 長時間の underrun 0 が未確認 | #187 |
| 実機の outputLatency・総往復遅延・Safari | CI で測れない | [AU-22] (#2366) |
