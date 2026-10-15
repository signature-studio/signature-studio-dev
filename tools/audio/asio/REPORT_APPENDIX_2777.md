# tools/audio/asio — #2777 (#998 残件) com_ramp_b256_d2 underrun: 初期目標充填 T の実測 (付録)

> **正本**: `tools/audio/asio/REPORT.md` §12 (結論・未解決)。本付録は #2777 の追加実測のみを持つ。
> 測定はすべて headless Chrome・Linux runner (4 コア)・単独実行 (負荷の掛けなし)。実オーディオデバイスでは測っていない。

## 1. 結論

- **原因 (部分特定)**: 初期の目標充填 T (ring の目標 fill) は `fla_open` で決まる。
  `need = (burst + burst/4 + 2B − 1) / B` (B = buffer_frames)。`burst` は `src/runtime/audio-shim.ts` の
  `cmdOpen` が `res[0] = max(round(baseLatency × sr), probed)` で返す。`probed` は `fl-burst-probe` が最大 3 秒で観測した値で、
  **実行ごとに変わる**。`need` の式から、probed ≤ 512 で depth 4 (T0 = 1024 frames = 21.3 ms)、probed ≥ 769 で depth 6 (T0 = 1536) になる。
  probe の値は harness に記録していないので、ここは depth からの逆算 (推定)。
- **depth 4 で underrun が 1 回出た**: 既定 (探査あり) の 1 回目 (r1) で depth 4・underrun 1 (silence 5888)。
  depth 4 の 7 回中の 1 回だけの観測で、母数が足りず、初回 run とも一致する。残り 6 回 (探査を無効にして初期 depth 4 に固定した回) は underrun 0 だったが、min_fill が 384〜896 まで落ち、余裕が小さい。
- **depth 6 では出なかった**: 既定で depth 6 (T0 = 1536 frames) になった 9 回は underrun 0・min_fill 896 (全 9 回)。0/9 回も母数が小さく、頻度の差を示すものではない。
- **未特定**: producer が約 19 ms 書き込みを止める直接の経路 (§3-1)。futex 起床の遅延は 16 回すべてで 4 ms 以上 0 件・
  `wait_timeouts` 0 件 (§12-5 と同傾向)。残る候補は `do_buffer` の外 (未計測)。
- **対処 (main に merge 済み)**: 初期 T の下限を探査に依らず depth 6 相当 (1536 frames) にする `FLA_F_T_FLOOR`。`lat_out` +512 frames (約 10.7 ms) の採否は PM 判断で採用 (2026-10-15)。子 issue **#2934** (`[AU-26]`) → PR #2995・#3583。床の適用後の再測定と残存する失敗は §7。
- **ゲートは無変更**: `com_ramp_b256_d2` の判定基準 (underrun 0・silence 0・ramp bit-exact) は変えていない。

## 2. 仕組み (コード参照)

| 項目 | 場所 | 内容 |
|---|---|---|
| 初期 depth | `tools/audio/src/flaudio.c` `fla_open` | `need` は burst から算出。`depth = max(設定値, need)` |
| burst | `src/runtime/audio-shim.ts` `cmdOpen` | `max(round(baseLatency×sr), probed)`。`probed` は `probeBurst` (3 秒上限) |
| T の動的調整 | `tools/audio/src/flasio.c` thread_fn | `T = max(need_from_burst_obs, T0) + esc`。underrun ごとに +B、3 秒無 underrun で −B |
| 作成時の遅延 | `flasio.c` (`lat_out0`) | 2 点からの当てはめ `lat_out0 = depth × 256 + 2049` (depth 4 → 3073、depth 6 → 3585)。表に対応する列はなく、3 点目では検証していない |

`T0` は作成時の depth で決まり、以後 T の下限として残る。失敗回は T0 = 1024 で、latency_changes 2 (推定: underrun で 1280 → 3 秒無 underrun で 1024 へ戻す) の記録と整合する。
`probed` の値は未記録 (上記は depth からの逆算)。次回の測定では `cmdOpen` のログ `probed_burst=` (`src/runtime/audio-shim.ts`) を表に加える。

## 3. 実測 (16 回 + 全 e2e 1 行)

- 既定 (探査あり): HEAD `6b095da2` で 10 回。r1 は build 直後の 1 回目。r2〜r10 は連続実行。その後 `e137c4a8` で harness に `probe0` ノブが入ったが、既定経路では無効 (§5-1)。
- 探査無効 (`--probe0`): HEAD `e137c4a8` で 6 回。
- 全 e2e: HEAD `e137c4a8` の `bash tools/audio/asio/e2e.sh` 内の `com_ramp_b256_d2` (1 行のみ。他列は未記録)。

| 実行 | 初期 depth | underrun / silence | min_fill | avg_fill | latency_changes | T 終値 | cb_max (µs) | cb_late | wait_timeouts | wake ≥4 ms | worklet 呼出間隔 max (ms) | ramp mismatch (mismatch / checked) | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 既定 r1 (初回) | 4 | **1 / 5888** | **0** | 814 | 2 | 1024 | 80 | 1 | 0 | 0 | 16 | **195328 / 240896** | **FAIL** |
| 既定 r2 | 6 | 0 / 0 | 896 | 1161 | 0 | 1536 | 54 | 0 | 0 | 0 | 12 | 0 / — | PASS |
| 既定 r3 | 6 | 0 / 0 | 896 | 1161 | 0 | 1536 | 60 | 0 | 0 | 0 | 12 | 0 / — | PASS |
| 既定 r4 | 6 | 0 / 0 | 896 | 1145 | 0 | 1536 | 50 | 0 | 0 | 0 | 12 | 0 / — | PASS |
| 既定 r5 | 6 | 0 / 0 | 896 | 1161 | 0 | 1536 | 370 | 0 | 0 | 0 | 15 | 0 / — | PASS |
| 既定 r6 | 6 | 0 / 0 | 896 | 1158 | 0 | 1536 | 70 | 0 | 0 | 0 | 12 | 0 / — | PASS |
| 既定 r7 | 6 | 0 / 0 | 896 | 1164 | 0 | 1536 | 140 | 0 | 0 | 0 | 13 | 0 / — | PASS |
| 既定 r8 | 6 | 0 / 0 | 896 | 1177 | 0 | 1536 | 50 | 0 | 0 | 0 | 14 | 0 / — | PASS |
| 既定 r9 | 6 | 0 / 0 | 896 | 1168 | 0 | 1536 | 114 | 0 | 0 | 0 | 13 | 0 / — | PASS |
| 既定 r10 | 6 | 0 / 0 | 896 | 1164 | 0 | 1536 | 54 | 0 | 0 | 0 | 17 | 0 / — | PASS |
| 探査無効 P0-1 | 4 | 0 / 0 | 640 | 1179 | 2 | 1536 | 149 | 0 | 0 | 0 | 13 | 0 / — | PASS |
| 探査無効 P0-2 | 4 | 0 / 0 | 512 | 1182 | 1 | 1536 | 44 | 0 | 0 | 0 | 13 | 0 / — | PASS |
| 探査無効 P0-3 | 4 | 0 / 0 | 384 | 672 | 0 | 1024 | 104 | 0 | 0 | 0 | 13 | 0 / — | PASS |
| 探査無効 P0-4 | 4 | 0 / 0 | 512 | 1170 | 1 | 1536 | 399 | 0 | 0 | 0 | 13 | 0 / — | PASS |
| 探査無効 P0-5 | 4 | 0 / 0 | 896 | 1161 | 1 | 1536 | 94 | 0 | 0 | 0 | 13 | 0 / — | PASS |
| 探査無効 P0-6 | 4 | 0 / 0 | 384 | 678 | 0 | 1024 | 685 | 0 | 0 | 0 | 14 | 0 / — | PASS |
| 全 e2e (`e137c4a8`) | 未記録 | 0 / 0 | 未記録 | 未記録 | 未記録 | 未記録 | 未記録 | 未記録 | 未記録 | 未記録 | 未記録 | 未記録 | PASS (e2e 4/4) |

- 判定は表に記録した列 (underrun 0・silence 0・ramp mismatch 0) で付けた。`—` は checked の未記録 (r1 のみ記録)。COM 面・timeinfo など表外の gate 条件は、本付録の判定に含めていない。
- 初期 depth と underrun の対応: depth 4 = 7 回中 1 回 (r1)、depth 6 = 9 回中 0 回。母数が小さく、有意とは言えない。
- 探査無効 (初期 depth 4 に固定) の 6 回は min_fill が 384〜896 まで下がった (depth 6 の 9 回はすべて 896)。初期 depth 4 は余裕が小さい、という傾向と整合するが、母数は小さい。
- 探査無効の P0-3・P0-6 は T が 1024 のまま終わり、P0-1・P0-2・P0-4・P0-5 は途中で T を 1536 に上げた (latency_changes 1〜2)。underrun 0 の回でも T が上がっているのは、`flasio.c` の `Tn = max(need, T0) + esc` で need (worklet が観測した最長バースト由来) が T0 を超えたため、と推定 (未検証)。

### 3-1. 失敗回 r1 の trace (`underrun_trace`)

- **r1 は gate FAIL** (判定基準: underrun 0・silence 0・ramp bit-exact)。ramp 不一致 195328 は初回 underrun 以降の全フレーム: 195328 = (1882 − 356) × 128 = 240896 − 45568。1882 = 240896 ÷ 128 (quantum 数)、356 = 初回 underrun の quantum。
- 初回 underrun は quantum 356 (約 0.95 秒)。直前 64 quantum の fill は `…1024, 896, 768, 640, 512, 384, 256, 128, 0`。
- 終端の 7 quantum (896 → 0) は producer の書き込みなしで単調に減っている (896 frames ÷ 48 kHz ≈ 18.7 ms、約 19 ms)。`cb_max` 80 µs・`cb_late` 1 で、bufferSwitch 本体の時間ではない。
- 同じ実行の `callback_gap` 最大は 16 ms (worklet 呼出間隔)。worklet が止まったのではない。

## 4. 測定の経緯 (棄却した方法)

- 初期 depth の強制指定 (`depth=4`): `fla_open` で `need` (burst 由来) が優先されるため 6 のまま。6 回とも `lat_out0 = 3585` で、無効だった (コードは残していない)。
  - 説明: `fla_open` は `need > depth` のとき `depth = need` とする (`tools/audio/src/flaudio.c` L108)。depth 6 になったことから、この試行では burst が 896 frames 以上 (128 単位の切り上げ後。probed ≥ 769 相当) だったと逆算される。行データ (probed 値を含む) は本付録に残していない。
- 採用した方法: `com_page.mjs` で `FlAudioShim.prototype.probeBurst` を 0 に固定 (`probe0=1` の query のみ)。
  `res[0] = round(baseLatency × sr) = 481 → 512`、`need = 4` になる。

## 5. 実行の記録

| 項目 | 値 |
|---|---|
| 既定の 10 回 | HEAD `6b095da2`・各回約 38 秒・`node tools/audio/asio/harness/run_com.mjs --only com_ramp_b256_d2` |
| 探査無効の 6 回 | HEAD `e137c4a8`・同コマンドに `--probe0` |
| 全 e2e (測定 commit `e137c4a8`) | `bash tools/audio/asio/e2e.sh` (soak 120 s 込み) **exit 0・4/4 PASS・203 秒**。load 1 分 0.19 (開始) → 0.05 (終了) |
| 全 e2e の内訳 | `com_ramp_b256_d2` underrun 0・silence 0 / `com_ramp_b1024_d2` 0 / `com_sine_b256_d2` 0 / `com_soak120_b256` 0 (soak ramp 0/5762816) |
| 測定 commit から HEAD までのコード差分 | 本 PR で `tools/audio/asio/harness/` に `probe0` 診断ノブを追加 (既定は無効)。`git diff 6b095da2 e137c4a8 -- tools/audio` は harness 2 ファイル (+5/−1) のみ。`e137c4a8` から HEAD は REPORT・付録のみ |

### 5-1. 既定 10 回の鮮度

既定 10 回は HEAD `6b095da2` で測った。その後 `e137c4a8` で harness に `probe0` ノブが入ったため、既定経路が変わっていないことを確認した (コード読みによる。実機での再測定はしていない)。

```
git diff --numstat 6b095da2 3a687abd -- tools/audio
1	0	tools/audio/asio/REPORT.md
92	0	tools/audio/asio/REPORT_APPENDIX_2777.md
2	0	tools/audio/asio/harness/com_page.mjs
3	1	tools/audio/asio/harness/run_com.mjs
```

- `harness/com_page.mjs`: `probe0: q.get("probe0") === "1"` と `if (cfg.probe0) FlAudioShim.prototype.probeBurst = ...`。query に `probe0=1` が無いとき `cfg.probe0` は偽で、`probeBurst` は上書きされない。
- `harness/run_com.mjs`: `probe0 = args.includes("--probe0")` が偽のとき `.map` は `s` をそのまま返し、`sel` は変更前と同じ (`s.q` は不変)。
- よって既定経路 (`run_com.mjs --only com_ramp_b256_d2`) は `6b095da2` と `3a687abd` で同一。§3 の「同一」は tools/audio の全ファイルの同一ではなく、既定経路の同一を指す。

## 6. 範囲外・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| producer が約 24 ms 以上書き込みを止める直接経路 (`do_buffer` の外の待ち。JS 側か wasm 側かも未切り分け) | 直接経路が未特定。床 (`FLA_F_T_FLOOR`) の下でも §7 で 1 回 FAIL | **[AU-40]** (親 #2777 から起票) |
| 床の適用後の失敗の頻度 (§7: 本 HEAD 15 回で 1 FAIL) | 母数が小さく、頻度の確定ができない | **[AU-40]** (同上) |
| `probed` 値の未記録 (次回は `probed_burst=` ログを表に加える) | depth 4/6 の振り分けを直接確かめられない | **[AU-40]** (同上) |
| 探査無効 6 回・既定 10 回の母数 (depth 4 は 7 回中 1 回) | 対処前の頻度は本付録 §3 の母数のまま | 追加測定はしない (対処前の比較は母数不足と明記) |

- 範囲外: 実オーディオデバイス・Windows/mac・Firefox/Safari。負荷下の測定は §7 の 5 回のみ。B=512・1024 の実測は本 issue の受入条件に無く未実施。

## 7. 2026-10-15 再測定: 床 (`FLA_F_T_FLOOR`) 適用後の失敗の残存

- 測定 commit: `c0fb6e074` (origin/main。`tools/audio` のコードは変えていない。本 PR は REPORT と付録のみ)。worktree は `ws-2777` (branch `2777-asio-com-underrun-load`)。
- 手順: `bash tools/audio/asio/build.sh` (emsdk は環境変数 `EMSDK_ENV` で指定。素材 `toolchain-emsdk`・ビルド 9 秒) の後、`node harness/run_com.mjs --quick --only com_ramp_b256_d2 --out <json>` を 1 回ずつ foreground で実行。負荷下は `yes > /dev/null` を 4 本 (4 コア) 掛け、実行後に PID 指定で停止。判定基準 (underrun 0・silence 0・ramp bit-exact) は変えていない。
- 実行: 負荷なし 10 回・負荷下 (yes×4) 5 回。すべて単独の `--only` 実行で、実行前 load は負荷なし 0.03〜1.15・負荷下 0.30〜5.89。

| 区分 | 結果 | underrun / silence | min_fill | T (lat_out) | latency_changes | ramp 不一致 | cb_max (µs) | callback_gap max (ms) |
|---|---|---|---|---|---|---|---|---|
| 負荷なし 1 (初回) | **FAIL** | **1 / 4480** | 0 | 1792 (3841) | 1 | 110208/144768 | 49 | 12 |
| 負荷なし 2〜10 | PASS ×9 | 0 / 0 | 896 | 1536 (3585) | 0 | 0/144768 | 69〜429 | 11〜16 |
| 負荷 yes×4 1〜5 | PASS ×5 | 0 / 0 | 896 | 1536 (3585) | 0 | 0/144128〜144896 | 44〜2315 | 16〜18 |

- 負荷なし 10 回のうち 1 回 (初回) のみ FAIL。負荷下 5 回はすべて PASS。成功 14 回はすべて min_fill 896・T 1536 (lat_out 3585) で揃った。
- 失敗 run の読み (§3-1 と同形):
  - 開始時 T は 1536 (depth 6・床どおり)。初回 underrun は quantum 270。
  - 直前 64 quantum の fill は 1152〜1536 frames。そこから 1 quantum (128 frames) ずつ 9 段 (1152 → 0) 落ちた。producer の書き込みが約 24 ms 以上 (1152 frames ÷ 48 kHz = 24.0 ms) 止まった形で、§3-1 の 24〜27 ms と整合する。
  - worklet 呼出間隔の最大は 12 ms、`cb_max` は 49 µs。worklet の停止ではない (§3-1 と同じ判定)。
  - 失敗の後に `latency_changes` 1 で T は 1536 → 1792 (lat_out 3841)。
- 判定 (ゲートは無変更): 判定基準に対して本 run は FAIL。判定の空振りでないことは、underrun 1・ramp 不一致 110208 が同じ run で検出されていることが示す。
- 読み (推定を含む):
  - 床は初期 T を 1536 に上げた (実測)。ただし成功 run の定常の fill の底は 896 frames (約 18.7 ms) で揃っており、底の決まり方は未確認。producer の停止が約 19 ms を超えると、底からも枯渇しうる (推定)。
  - 床の適用後の母数: 本 HEAD の 15 回で 1 FAIL。床の適用後の既存の実測 (`REPORT_APPENDIX_2934.md` §3-2・§6-2・§6-6-2 の計 60 回 PASS) を加えると、床の適用後は計 75 回で 1 FAIL。床の前後で同じ条件の対照は無いので、頻度が下がったとは言えない。
  - 結論: 床は初期 T を上げるが、producer の書き込み停止そのものを消してはいない。直接経路の特定は子 issue **[AU-40]** に移す。
- 再現手順 (`tools/audio/asio/` で実行): `bash build.sh` → `node harness/run_com.mjs --quick --only com_ramp_b256_d2 --out work/meas/x.json` (負荷下は事前に `yes > /dev/null` を 4 本起動し、終了後に `kill <PID>`)。`work/meas/` は gitignore 対象で、集計は JSON の `results[0].result` を読んだ。

- 全 e2e (HEAD `3800bf501`・コード差分 0): `bash tools/audio/asio/e2e.sh` (soak 120 s 込み) → **rc 0・node check 126/126・4/4 PASS・203.7 秒** (開始 load 0.02)。`com_ramp_b256_d2` は underrun 0・silence 0・ramp 0/241024。この 1 回の PASS は頻度の根拠にしない (§7 の表が根拠)。
- 検証 (規則 6): 測定 commit `c0fb6e074` から HEAD までのコード差分 `git diff c0fb6e074 HEAD -- tools/audio ':!*.md'` の出力は空 (本 PR は md のみ)。
