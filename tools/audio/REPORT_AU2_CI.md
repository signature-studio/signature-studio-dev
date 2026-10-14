# AU-2 (#187) CI 代理指標の測定 (ubuntu runner)

親: `REPORT.md` §8。実機でしか測れない項目は [AU-22] (#2366) に分離済み。

## 1. 代理経路の検証 (PulseAudio null-sink) — 未検証 (fake と同一の値に留まった, n=1)

| 項目 | 値 |
|---|---|
| 環境 | ubuntu runner (4 vCPU, 15 GiB), `google-chrome 155.0.8059.39` (REPORT の 154 とは版が違う), PulseAudio 16.1 (apt 導入) |
| PulseAudio | `module-null-sink sink_name=ci_null` を起動 (`pactl info` の Default Sink = `ci_null`) |
| 比較 | `asio_sine_b256_d2` を同一ハーネス・同一 HEAD (`1ddc8512`) で 2 回 (fake シンク / PulseAudio 起動中) |

| 条件 | sampleRate | baseLatency | outputLatency | clock (Hz) | burst | T | 判定 |
|---|---|---|---|---|---|---|---|
| fake シンク (既定) | 48000 | 0.011625 s | 0.036 s | 47969.0 | 1152 | 1792 | PASS |
| PulseAudio null-sink 起動中 | 48000 | 0.011625 s | 0.036 s | 47971.0 | 1152 | 1792 | PASS |

**結論**: Chrome の `baseLatency` / `outputLatency` / `burst` / `T` は PulseAudio 起動の有無で変わらず、`clock` も 2 Hz の差に留まった (各条件 n=1)。ただし Chrome の sink-input が `ci_null` に接続したかは **未確認** (`pactl list sink-inputs` は未取得)。そのため「null-sink は代理にならない」とは結論できず、「fake と同一の値に留まった。接続先は未検証」とだけ書く。よって P1〜P4 を null-sink の代理として扱う前提は未検証のままである。Firefox は `tools/audio/harness` が Chrome CDP 専用のため、同じ方法では測れない。

## 2. ベースライン `e2e.sh --quick` (main `1ddc8512`, 測定 commit = `1ddc8512`)

- 実行: `bash tools/audio/e2e.sh --quick`, `EMSDK_ENV=$RUNNER_TEMP/emsdk/emsdk_env.sh`, `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`
- 結果: **43/44 PASS**, wall 266.9 s, load avg 開始 2.25 → 終了 0.42 (nproc 4)
- FAIL: `asio_ramp_b128_d2` — `underruns=1 silence=2688; ramp mismatches=162944/192384`。B=128 の ramp は本 run で再現。原因は未切り分け (負荷起因の疑い、未確認)。追跡先: #187 (§4)
- burst 分布 (quick, 48k): 512f 大半。96k は 1024f (`asio_sine_b256_96k`, `asio_sine_b512_96k`)。96k/B=256 の `burst_floor=4096` ネガコントロールは PASS (T=5376)

## 3. 未実施 (この run の時間内に収まらないため)

- フル `e2e.sh` (約 9 分 + ASIO COM 経路 約 3 分) と 30 分ソーク: 行列にすると 1 run の 58 分上限を超えるため未実施
- Firefox 行列: ハーネスが Chrome 専用
- Windows / macOS runner の仮想オーディオ workflow: 未着手 (権限・検証手段の確認が先)

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ~~Chrome が null-sink に接続したか未確認~~ → 解消 (§5: `sink-inputs` で ci_null 接続を確認。報告値・burst は fake と異なる) | — | — |
| Firefox 行列がハーネス未対応 | 行列 {Chrome, Firefox} × {48k, 96k} の片側が未測定 | #187 |
| `asio_ramp_b128_d2` の FAIL (quick, 負荷起因の疑い) | 回帰判定の不安定さ | #187 (要切り分け) |
| 30 分ソーク (AU-10 null-sink 版) | 長時間の underrun 0 が未確認 | #187 |
| 実機の outputLatency・総往復遅延・Safari | CI で測れない | [AU-22] (#2366) |

## 5. 行列の実測 (2 回目 run, 2026-10-14) — §1 の未確認事項を解消

測定 commit = `54bacdc0` (main)。測定に使った `tools/audio/{src,harness,test}`・`public/worklets` は同 commit と同一 (差分確認は §8)。
再現: `bash tools/audio/build.sh` → `bash tools/audio/au2_matrix.sh 3` → `node tools/audio/au2_summary.mjs`。
環境: ubuntu runner (4 vCPU), `google-chrome 154.0.8037.97`, PulseAudio 16.1 (apt 導入, `module-null-sink sink_name=ci_null` を既定 sink)。
生結果 `results/au2/{fake,null}_r{1,2,3}.json` (各 3 シナリオ)、`results/au2/null_soak600.json` (ソーク)。

**null-sink の接続を確認** (§1 の未確認事項の解消): 再生中の `pactl list sink-inputs` に `application.name = "Google Chrome"` が `Sink: 1 (ci_null)` で現れ、`ci_null` は RUNNING。Chrome は null-sink を使っている。
よって §1 の「fake と同一の値」は、接続を確認しないまま比べた結果だったと読む。接続を確認した今回の比較では、報告値も burst も fake と**一致しなかった** (下表)。

### 5-1. 行列 (P1〜P4, 各セル n=3。シナリオは `asio_sine_b256_d2` (48k) / `asio_sine_b256_96k` / `asio_sine_b512_96k`)

| 条件 | sr | シナリオ | n | PASS | underrun (合計) | burst max (f) | 実 T (f) | T_req (f) | T≥T_req | baseLatency (ms) | outputLatency (ms) | clock (Hz, 平均) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Chrome fake シンク | 48000 | asio_sine_b256_d2 | 3 | 3/3 | 0 | 512 | 1536 | 1024 | OK | 10.0 | 30.0 | 48000.0 |
| Chrome fake シンク | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 1024 | 2816 | 1536 | OK | 10.0 | 30.0 | 96000.4 |
| Chrome fake シンク | 96000 | asio_sine_b512_96k | 3 | 3/3 | 0 | 1024 | 3072 | 2048 | OK | 10.0 | 30.0 | 96000.1 |
| Chrome PulseAudio null-sink | 48000 | asio_sine_b256_d2 | 3 | 3/3 | 0 | 1152 | 1792 | 1792 | OK | 11.6 | 36.0 | 48008.5 |
| Chrome PulseAudio null-sink | 96000 | asio_sine_b256_96k | 3 | 3/3 | 0 | 3456〜4480 | 4608〜5888 | 5888 | OK | 11.6 | 71.0〜80.0 | 96002.2 |
| Chrome PulseAudio null-sink | 96000 | asio_sine_b512_96k | 3 | 3/3 | 0 | 4352〜4480 | 6144 | 6144 | OK | 11.6 | 68.0〜70.0 | 95987.8 |

- 表の値: burst = `stats.burst_obs` (連続 process の総フレーム数の**最大**)、T_req = `ceil((burst×1.25 + B)/B)×B` (各 run の burst で計算)。セル内の範囲は n=3 の min〜max。
- 18 シナリオ実行はすべて PASS (underrun 0・ramp/sine 誤差 1.49e-8)。load avg は各 run 開始 0.0〜0.6。
- P2 の p99 は **未計測**。worklet が公開するのは最大値 (`burst_obs`) だけで、分布は取れていない。

### 5-2. 30 分ソーク (P1) — 10 分のみ実施

| 条件 | シナリオ | 結果 |
|---|---|---|
| Chrome null-sink 48k B=256 ramp | `asio_ramp_b256_soak600` (`--soak 600`) | **PASS**: underrun 0・silence 0・ramp mismatch 0/28,803,328 f・wall 600.01 s。T=1792 (fixed), burst 1152 |

30 分 (1800 s) のソークは時間内に収まらなかったため未実施 (§8 未解決)。

### 5-3. T 下限と安全係数 (P4) の再評価

- **所見 1 (係数不足)**: null-sink の 96k では起動時の較正 T0 が実行中の burst を下回った。B=256 の 96k run では T0=4608 (較正 burst 3456 相当) に対し、run 中の burst は 4480 (3456 の 1.30 倍)。現行の安全係数 1.25 は、この揺れを覆えない。
  - B=512 96k は T0=5120 から実行中に `grows` 1〜2 回で 6144 へ拡張。B=256 96k は 1 run (r3) で `grows` 2 回で 5888 へ拡張。
  - **underrun は全 run で 0**。ただし拡張は実行中に行われるため、初回の揺れで underrun の余裕が少ない (実機で揺れがさらに大きい場合は未検証)。
- **所見 2 (fake の代理性)**: fake の burst 512 (48k)・1024 (96k) は、null-sink の 1152・3456〜4480 を代表しない。fake の値で T を決めると、96k で T が不足する。
- **係数の候補 (計算値, 未適用)**: 96k・B=256・burst 4480 → 係数 1.25 で T=5888 / 1.30 で 6144 / 1.50 で 7168。B=512 → 1.25 で 6144 / 1.50 で 7680。48k・B=256・burst 1152 → 1.25 で 1792 / 1.50 で 2048。
  係数の値は遅延とのトレードオフのため、PM 判断。係数は `tools/audio/src/flasio.c:225` の `need = (burst + burst/4 + 2B−1)/B·B` (実行中の拡張式。`grows` はこの式で増える) にある。本 PR では変更しない → 子 issue **[AU-24]** で実装する。

## 6. 未解決 (実測ではなく実装が必要なものは子 issue)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Firefox 行列 (PulseAudio null-sink × 48k/96k) | `tools/audio/harness` が Chrome CDP 専用。Firefox の行が未測定 | **[AU-23]** (子 issue, 実装) |
| OPEN 較正の安全係数 (1.25 → 候補 1.30〜1.50) の実装と e2e 再測定 | 96k の null-sink で、初回の T 不足を run 中の grows で補っている | **[AU-24]** (子 issue, 実装) |
| 30 分ソーク (null-sink, 48k B=256) | 10 分 PASS のみ。30 分の underrun 0 は未確認 | #187 (測定のみのため子にせず残す) |
| P2 burst の p99 | worklet が最大値しか公開しない。分布は未計測 | #187 (worklet 拡張が要るため次 run) |
| Windows / macOS runner (任意) | 未着手 (受入 4) | #187 |
| `asio_ramp_b128_d2` quick FAIL (§2) | 本 run では再実行していない。原因未切り分け | #187 |

## 7. 検証範囲 / 範囲外

- 範囲: ubuntu runner の Chrome 154 (fake / PulseAudio null-sink) の 48k・96k。null-sink は PulseAudio の出力経路で、実デバイス (実 IF の outputLatency) を代表しない (AU-22 #2366)。
- 範囲外: Firefox・Safari・Windows/macOS・実機の総往復遅延。

## 8. コード差分 (測定 commit `54bacdc0` → HEAD)

測定に使ったコード (`tools/audio/{src,harness,test}`・`public/worklets`) の差分は 0 (下記の出力が空であること)。
追加したのは測定スクリプト `tools/audio/au2_matrix.sh`・`tools/audio/au2_summary.mjs` と結果 `results/au2/` のみ。
