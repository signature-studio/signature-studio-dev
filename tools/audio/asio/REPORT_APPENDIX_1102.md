# tools/audio/asio — AU-17 (#1102) COM 経由ソーク実測

親: #191 / #271。本節は `REPORT.md` 250 行上限のため分割移動した付録。

## 1. 修正

- `harness/com_page.mjs`: ramp 照合の期待値を `p + 1` から `(p & 0xFFFFFF) + 1` へ変更。生成元 `test/com_test.c` の `(n & 0xFFFFFFu) + 1` (2^24 f = 349.5 s @48k で巻き戻る) と一致させた。

## 2. 修正前の FAIL 再現 (旧 `p+1`, `bash tools/audio/asio/e2e.sh --soak=360`, 実測)

- 所要 442 秒 (21:03:46 → 21:11:08), load 1 分 1.87〜2.11。
- `com_soak360_b256`: **FAIL**。ramp 不一致 **487,296 / 17,264,512 f**。underrun 0 / silence 0 / bufferSwitchTimeInfo bad 0。
- 不一致数 487,296 = 17,264,512 − 2^24 (16,777,216) と一致する。2^24 f 以降の巻き戻しを `p+1` 照合が不一致として数えたことを示す (先頭不一致フレームは未記録)。

## 3. 修正後 (`bash tools/audio/asio/e2e.sh --soak=1800`, 実測)

- 所要 1,841 秒 (20:32:31 → 21:03:12 = 30 分 41 秒), load 1 分 1.95〜2.09。
- node check 126/126 PASS。
- `com_soak1800_b256`: **PASS**。underrun 0 / silence 0 / ramp **0 / 86,385,664 f** (bit-exact) / bufferSwitchTimeInfo **337,475 calls bad=0** / 実フレーム 86,385,664 f ≥ 公称 1800 s の 99% (85,536,000 f) / COM 面一致 (sellog・QI 1・alive 0)。
- `com_ramp_b1024_d2`: PASS (ramp 0/240,896, underrun 0)。
- `com_sine_b256_d2`: PASS (maxErr 1.49e-8, underrun 0)。
- `com_ramp_b256_d2`: **FAIL**。underrun 1 / silence 640 f。ramp mismatch 195,328/240,384 は underrun 後の出力ずれと思われるが**原因は未調査**。REPORT §3-1 の負荷依存事象と同形。
- 同一 run の 30 分ソーク自体は underrun 0 で PASS。短シナリオの FAIL とは別に扱い、再現の有無は次回 e2e で確認する (未確定)。

## 4. 未達 (子 issue へ分割)

- 受入条件 1 (キャプチャ SAB 約 661 MiB を一括保持せず分割照合): **未実装**。現行 `com_page.mjs` は `captureFactory` で frames 全量の SAB を一括確保する。分割照合の設計変更は別 issue に分離した (下記)。
