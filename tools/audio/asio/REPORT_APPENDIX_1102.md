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
- **e2e 全体の終了コード**: 本 run は exit 1 (`com_ramp_b256_d2` の上記 FAIL による)。ソーク単体 (`com_soak1800_b256`) は PASS。#1102 受入条件 1 の文言 (`e2e.sh --soak 1800` が PASS) は**未達**のまま。head での再測定 (§7) も exit 1 で、e2e 全体 exit 0 は未達のまま残す。

## 4. 未達 (子 issue へ分割)

- 受入条件 1 (キャプチャ SAB 約 661 MiB を一括保持せず分割照合): **未実装**。現行 `com_page.mjs` は `captureFactory` で frames 全量の SAB を一括確保する。分割照合の設計変更は子 issue **#1358 [AU-19]** に分割 (範囲は分割照合のみ)。
- `com_ramp_b256_d2` の underrun 1 / silence 640 f の追跡先は **#998 [AU-16]** (負荷依存 underrun の正本。WORKFLOW §12)。#1358 では扱わない。
- #1102 は本 PR で Close しない (`Refs #1102`)。受入条件 1 の未達が残るため。

## 5. 測定 commit と差分 0 の証跡 (WORKFLOW §6)

- 測定 commit: `35c6fa15d18c3de624e821503365bf3a4754ea5b` (§3 の e2e 実測の対象コード)。
- 差分 (コード部分。`*.md` を除く。`git diff 35c6fa15 HEAD -- tools/audio/asio ':!*.md'`): 出力 0 行。
- コード検証 HEAD `289fb00c` (付録のみの commit): `git diff 35c6fa15 289fb00c -- tools/audio/asio ':!*.md'` = 0 行。`git diff --stat 35c6fa15 289fb00c -- tools/audio/asio` の対象は `REPORT_APPENDIX_1102.md` のみ。
- `289fb00c` より後の commit は付録 (`*.md`) のみで、その差分も `git diff 35c6fa15 HEAD -- tools/audio/asio ':!*.md'` = 0 行で確認する。

## 6. head での再実行 (実施済み・§7 参照)

- head での `bash tools/audio/asio/e2e.sh --soak=1800` の再実行: 実施済み (§7)。exit 1 で、受入条件 1 は未達。
- 追跡: exit 0 の記録は #1102 (受入条件 1) の未達として #1102 側で扱う。

## 7. head 再測定 (`bash tools/audio/asio/e2e.sh --soak=1800`, 実測)

- 測定 commit: `23dc1754` (`*.md` のみの変更。コード差分は `35c6fa15` と同一)。`git diff 35c6fa15 23dc1754 -- tools/audio/asio ':!*.md'` = 0 行。
- 素材: `$ARTIFACTS_DIR` に `fl-win64.tar.zst` / `toolchain-emsdk.tar.zst` が実在。emcc は `[EMSDK]` (docs/REFERENCES.md) を `build.sh` が読んで解決。
- 前提: worktree に `node_modules` が無く `tsc` 欠落で一度 exit 127 → `pnpm install --frozen-lockfile` 後に再実行。以下は再実行の結果。
- 所要 1,851 秒 (21:59:21 → 22:30:12 = 30 分 51 秒)。開始時 load 1 分 0.28 (4 コア)。実行中の load は未採取。
- 結果: **exit 1**。
  - node check 126/126 PASS。
  - `com_ramp_b1024_d2` PASS (ramp 0/240,896 / underrun 0)。
  - `com_sine_b256_d2` PASS (maxErr 1.49e-8 / underrun 0)。
  - `com_soak1800_b256` PASS (underrun 0 / silence 0 / ramp 0 / 86,403,968 f / bufferSwitchTimeInfo 337,520 calls bad=0)。
  - `com_ramp_b256_d2` **FAIL**: underrun 1 / silence 128 f / ramp 195,456 / 240,512 不一致。
- 同形の FAIL を 3 回記録 (測定 run `35c6fa15`: silence 640 f / reviewer 再現 `5837d1f7`: silence 384 f / 本回 `23dc1754`: silence 128 f)。silence 量は run ごとに変動する。ramp 不一致は毎回 `com_ramp_b256_d2` のみ。
- 判定: 受入条件 1 (exit 0) は head でも未達。#1102 は Close しない。
