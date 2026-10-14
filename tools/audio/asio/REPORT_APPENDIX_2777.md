# tools/audio/asio — #2777 (#998 残件) com_ramp_b256_d2 underrun: 初期目標充填 T の実測 (付録)

> **正本**: `tools/audio/asio/REPORT.md` §12 (結論・未解決)。本付録は #2777 の追加実測のみを持つ。
> 測定はすべて headless Chrome・Linux runner (4 コア)・単独実行 (負荷の掛けなし)。実オーディオデバイスでは測っていない。

## 1. 結論

- **原因 (部分特定)**: 初期の目標充填 T (ring の目標 fill) は `fla_open` で決まる。
  `need = (burst + burst/4 + 2B − 1) / B` (B = buffer_frames)。`burst` は `src/runtime/audio-shim.ts` の
  `cmdOpen` が `res[0] = max(round(baseLatency × sr), probed)` で返す。`probed` は `fl-burst-probe` が最大 3 秒で観測した値で、
  **実行ごとに変わる**。`need` の式から、probed ≤ 512 で depth 4 (T0 = 1024 frames = 21.3 ms)、probed ≥ 769 で depth 6 (T0 = 1536) になる。
  probe の値は harness に記録していないので、ここは depth からの逆算 (推定)。
- **depth 4 で underrun が出る**: 既定 (探査あり) の 1 回目で depth 4・underrun 1 (silence 5888)。
  探査を無効にして depth 4 に固定した 6 回では underrun 0 だったが、min_fill が 384〜896 まで落ち、余裕が小さい。
- **depth 6 では出ていない**: 既定で depth 6 (T0 = 1536 frames) になった 9 回は underrun 0・min_fill 896 (全 9 回)。
- **未特定**: producer が約 19 ms 書き込みを止める直接の経路 (§3-1)。futex 起床の遅延は 16 回すべてで 4 ms 以上 0 件・
  `wait_timeouts` 0 件 (§12-5 と同傾向)。残る候補は `do_buffer` の外 (未計測)。
- **対処 (未実装)**: 初期 T の下限を探査に依らず depth 6 相当 (1536 frames) にする案。
  ただし `lat_out` (FL へ報告する遅延) が +512 frames (約 10.7 ms) 増えるので製品判断が要る。子 issue **#2934** (`[AU-26]`) に起票。
- **ゲートは無変更**: `com_ramp_b256_d2` の判定基準 (underrun 0・silence 0・ramp bit-exact) は変えていない。

## 2. 仕組み (コード参照)

| 項目 | 場所 | 内容 |
|---|---|---|
| 初期 depth | `tools/audio/src/flaudio.c` `fla_open` | `need` は burst から算出。`depth = max(設定値, need)` |
| burst | `src/runtime/audio-shim.ts` `cmdOpen` | `max(round(baseLatency×sr), probed)`。`probed` は `probeBurst` (3 秒上限) |
| T の動的調整 | `tools/audio/src/flasio.c` thread_fn | `T = max(need_from_burst_obs, T0) + esc`。underrun ごとに +B、3 秒無 underrun で −B |
| 作成時の遅延 | `flasio.c` (`lat_out0`) | 実測の関係 `lat_out0 = depth × 256 + 2049` (depth 4 → 3073, depth 6 → 3585) |

`T0` は作成時の depth で決まり、以後 T の下限として残る。失敗回は T0 = 1024 で、latency_changes 2 (推定: underrun で 1280 → 3 秒無 underrun で 1024 へ戻す) の記録と整合する。

## 3. 実測 (16 回)

- 既定 (探査あり): HEAD `6b095da2` (本 PR の base。`tools/audio/asio` のコードは本 PR と同一) で 10 回。
  r1 は build 直後の 1 回目。r2〜r10 は連続実行。
- 探査無効 (`--probe0`): HEAD `e137c4a8` (測定 commit) で 6 回。

| 実行 | 初期 depth | underrun / silence | min_fill | avg_fill | latency_changes | T 終値 | cb_max (µs) | cb_late | wait_timeouts | wake ≥4 ms | worklet 呼出間隔 max (ms) | ramp mismatch |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 既定 r1 (初回) | 4 | **1 / 5888** | **0** | 814 | 2 | 1024 | 80 | 1 | 0 | 0 | 16 | 195328 / 240896 |
| 既定 r2 | 6 | 0 / 0 | 896 | 1161 | 0 | 1536 | 54 | 0 | 0 | 0 | 12 | 0 |
| 既定 r3 | 6 | 0 / 0 | 896 | 1161 | 0 | 1536 | 60 | 0 | 0 | 0 | 12 | 0 |
| 既定 r4 | 6 | 0 / 0 | 896 | 1145 | 0 | 1536 | 50 | 0 | 0 | 0 | 12 | 0 |
| 既定 r5 | 6 | 0 / 0 | 896 | 1161 | 0 | 1536 | 370 | 0 | 0 | 0 | 15 | 0 |
| 既定 r6 | 6 | 0 / 0 | 896 | 1158 | 0 | 1536 | 70 | 0 | 0 | 0 | 12 | 0 |
| 既定 r7 | 6 | 0 / 0 | 896 | 1164 | 0 | 1536 | 140 | 0 | 0 | 0 | 13 | 0 |
| 既定 r8 | 6 | 0 / 0 | 896 | 1177 | 0 | 1536 | 50 | 0 | 0 | 0 | 14 | 0 |
| 既定 r9 | 6 | 0 / 0 | 896 | 1168 | 0 | 1536 | 114 | 0 | 0 | 0 | 13 | 0 |
| 既定 r10 | 6 | 0 / 0 | 896 | 1164 | 0 | 1536 | 54 | 0 | 0 | 0 | 17 | 0 |
| 探査無効 P0-1 | 4 | 0 / 0 | 640 | 1179 | 2 | 1536 | 149 | 0 | 0 | 0 | 13 | 0 |
| 探査無効 P0-2 | 4 | 0 / 0 | 512 | 1182 | 1 | 1536 | 44 | 0 | 0 | 0 | 13 | 0 |
| 探査無効 P0-3 | 4 | 0 / 0 | 384 | 672 | 0 | 1024 | 104 | 0 | 0 | 0 | 13 | 0 |
| 探査無効 P0-4 | 4 | 0 / 0 | 512 | 1170 | 1 | 1536 | 399 | 0 | 0 | 0 | 13 | 0 |
| 探査無効 P0-5 | 4 | 0 / 0 | 896 | 1161 | 1 | 1536 | 94 | 0 | 0 | 0 | 13 | 0 |
| 探査無効 P0-6 | 4 | 0 / 0 | 384 | 678 | 0 | 1024 | 685 | 0 | 0 | 0 | 14 | 0 |

- 初期 depth と underrun の対応: depth 4 = 7 回中 1 回 (r1)、depth 6 = 9 回中 0 回。母数が小さく、有意とは言えない。
- 探査無効の 6 回は min_fill が 384〜896 まで下がった (depth 6 の 9 回はすべて 896)。depth 4 は余裕が小さい、という傾向の裏付け。
- 探査無効の P0-3・P0-6 は T が 1024 のまま終わり、P0-1・P0-2・P0-4・P0-5 は途中で T を 1536 に上げた (latency_changes 1〜2)。

### 3-1. 失敗回 r1 の trace (`underrun_trace`)

- 初回 underrun は quantum 356 (約 0.95 秒)。直前 64 quantum の fill は `…1024, 896, 768, 640, 512, 384, 256, 128, 0`。
- 終端の 7 quantum (896 → 0) は producer の書き込みなしで単調に減っている (約 19 ms)。`cb_max` 80 µs・`cb_late` 1 で、bufferSwitch 本体の時間ではない。
- 同じ実行の `callback_gap` 最大は 16 ms (worklet 呼出間隔)。worklet が止まったのではない。

## 4. 測定の経緯 (棄却した方法)

- 初期 depth の強制指定 (`depth=4`): `fla_open` で `need` (burst 由来) が優先されるため 6 のまま。6 回とも `lat_out0 = 3585` で、無効だった (コードは残していない)。
- 採用した方法: `com_page.mjs` で `FlAudioShim.prototype.probeBurst` を 0 に固定 (`probe0=1` の query のみ)。
  `res[0] = round(baseLatency × sr) = 481 → 512`、`need = 4` になる。

## 5. 実行の記録

| 項目 | 値 |
|---|---|
| 既定の 10 回 | HEAD `6b095da2`・各回約 38 秒・`node tools/audio/asio/harness/run_com.mjs --only com_ramp_b256_d2` |
| 探査無効の 6 回 | HEAD `e137c4a8`・同コマンドに `--probe0` |
| 全 e2e (測定 commit `e137c4a8`) | `bash tools/audio/asio/e2e.sh` (soak 120 s 込み) **exit 0・4/4 PASS・203 秒**。load 1 分 0.19 (開始) → 0.05 (終了) |
| 全 e2e の内訳 | `com_ramp_b256_d2` underrun 0・silence 0 / `com_ramp_b1024_d2` 0 / `com_sine_b256_d2` 0 / `com_soak120_b256` 0 (soak ramp 0/5762816) |
| 測定 commit から HEAD までのコード差分 | 本 PR で `tools/audio/asio/harness/` に `probe0` 診断ノブを追加 (既定は無効)。`git diff 6b095da2 e137c4a8 -- tools/audio` は harness 2 ファイル (+5/−1) のみ |

## 6. 範囲外・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 初期 T の下限を固定する対処 (lat_out +512 frames の採否を含む) | 受入条件 2 (原因と対処) が未達 | **#2934** (`[AU-26]`) |
| producer が約 24 ms 書き込みを止める直接経路 (`do_buffer` の外の待ち) | 原因の直接経路が未特定 | #2777 (本 PR で部分達成のまま) |
| 探査無効 6 回・既定 10 回の母数 (depth 4 は 7 回中 1 回) | 頻度の確定ができない | #2777 |

- 範囲外: 実オーディオデバイス・Windows/mac・Firefox/Safari・負荷を掛けた状態 (§12-3 の負荷試験は REPORT §12 と `REPORT_APPENDIX_998.md` を参照)。
