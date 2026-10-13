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
- `com_ramp_b256_d2`: **FAIL**。underrun 1 / silence 640 f。ramp mismatch 195,328/240,384 は underrun 後の出力ずれと思われるが**原因は未調査**。REPORT §12 (#998 [AU-16]) と同じ負荷依存 underrun の同形事象。
- 同一 run の 30 分ソーク自体は underrun 0 で PASS。短シナリオの FAIL とは別に扱い、再現の有無は次回 e2e で確認する (未確定)。
- **e2e 全体の終了コード**: 本 run は exit 1 (`com_ramp_b256_d2` の上記 FAIL による)。ソーク単体 (`com_soak1800_b256`) は PASS。#1102 受入条件 1 の文言 (`e2e.sh --soak 1800` が PASS) は**未達**のまま。e2e 全体 exit 0 の記録は、head での再測定を別途行うまで未達のまま残す (本 fix run では実施せず。§6 参照)。

## 4. 未達 (子 issue へ分割)

- 受入条件 1 (キャプチャ SAB 約 661 MiB を一括保持せず分割照合): **未実装**。現行 `com_page.mjs` は `captureFactory` で frames 全量の SAB を一括確保する。分割照合の設計変更は子 issue **#1358 [AU-19]** に分割 (範囲は分割照合のみ)。
- `com_ramp_b256_d2` の underrun 1 / silence 640 f の追跡先は **#998 [AU-16]** (負荷依存 underrun の正本。WORKFLOW §12)。#1358 では扱わない。
- #1102 は本 PR で Close しない (`Refs #1102`)。受入条件 1 の未達が残るため。

## 5. 測定 commit と差分 0 の証跡 (WORKFLOW §6)

- 測定 commit: `35c6fa15d18c3de624e821503365bf3a4754ea5b` (§3 の e2e 実測の対象コード)。
- 差分 (コード部分。`*.md` を除く。`git diff 35c6fa15 HEAD -- tools/audio/asio ':!*.md'`): 出力 0 行。
- 本節を追記した commit (文書のみ) の後、`git diff --stat 35c6fa15 HEAD -- tools/audio/asio` の対象は `*.md` のみ。コード・harness・test への差分 0。

## 6. 未実施 (次回の検証として残す)

- head での `bash tools/audio/asio/e2e.sh --soak=1800` の再実行: 次節 §7 に記録 (実施済み)。
- 追跡: exit 0 の記録は #1102 (受入条件 1) の未達として #1102 側で扱う。
