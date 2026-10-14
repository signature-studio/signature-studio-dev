# tools/audio/asio — AU-19 (#1358) COM キャプチャの分割照合

親: #1102 (AU-17)。本節は `REPORT.md` 250 行上限のため分割移動した付録。

## 1. 変更

- キャプチャ SAB を全長 (secs×sr) で確保せず、固定容量 `CAP_RING_FRAMES` = 2^21 frame の ring として書く (`fl-audio-worklet.js` の `capPut`: 絶対フレーム p は p % N へ書く)。`ring` 指定の無い経路は従来どおり。
- 照合は `harness/chunk_verify.mjs` の `ChunkVerifier` が担当。ポーリングの待機ごとに未照合区間を畳み込み、最後に `finish()`。未照合が N/2 を超えたら `fail` (照合遅延の検出)。
- `harness/com_page.mjs` の旧 `verify()` を置換。`build.sh` が `chunk_verify.mjs` をブラウザ側へコピー。

## 2. SAB サイズ (定義: 64 + frames×(outCh+inCh)×4 + (frames/128)×4 B, outCh=2, inCh=0)

| 方式 | frames | bytes | MiB |
|---|---|---|---|
| 旧 (1800 s 全長) | 86,408,192 | 693,965,856 | **661.8** |
| 新 (ring 2^21) | 2,097,152 | 16,842,816 | **16.1** |

## 3. 分割照合 = 一括照合 (`node tools/audio/asio/harness/chunk_selftest.mjs`, 実測)

同一の合成 ramp (512,000 f) を「一括 (N ≥ 総フレーム)」と「分割 (N = 4096, 8 quantum ごとに畳み込み)」で照合。

- clean ramp: 一括 mm=0 / 分割 mm=0 (n=512,000)
- 不一致 1 件 (frame 100000): 一括 mm=1 first=100000 / 分割 同一
- 不一致 3 件 (周回境界またぎ): 一括 mm=3 first=4095 / 分割 同一
- 無音 quantum 4 件: 一括 mm=512 first=896 / 分割 同一

**4/4 PASS** (mm・first_mismatch_frame・n が全件一致)。sine モードの分割照合は selftest 未実施 (ramp のみ検証)。

## 4. 実測 e2e

- 測定 commit: `6468686f` (コード変更の最後の commit)。以後のコード差分 0 (`git diff 6468686f HEAD -- tools/audio/asio public/worklets src/runtime` = 0 行)。
- 短シナリオ `bash tools/audio/asio/e2e.sh --quick` (soak なし): node 126/126 PASS / Chrome 3/3 PASS / 所要 1 分 25 秒。
  - com_ramp_b256_d2: ramp 0/144,768 / underruns 0 / silence 0 / bufferSwitchTimeInfo 568 calls bad=0。
  - com_ramp_b1024_d2: ramp 0/144,768 / underruns 0。
  - com_sine_b256_d2: maxErr 1.49e-8 / underruns 0。
- ソーク `bash tools/audio/asio/e2e.sh --soak=1800` (foreground, timeout 2280 s): **exit 0**。
  - 所要 1,828.8 秒 (30 分 28.8 秒、23:21:57 → 23:52:26)。load 1 分値は開始 0.09 / 終了 0.04 (4 コア以上。実行中の load は未採取)。
  - node check 126/126 PASS。
  - com_ramp_b256_d2: PASS (underruns 0 / silence 0 / ramp 0/240,512 / bufferSwitchTimeInfo 944 calls bad=0)。
  - com_ramp_b1024_d2: PASS (underruns 0 / ramp 0/240,896)。
  - com_sine_b256_d2: PASS (maxErr 1.49e-8 / underruns 0)。
  - **com_soak1800_b256: PASS** (underruns 0 / silence 0 / ramp **0 / 86,411,136 f** bit-exact / bufferSwitchTimeInfo 337,548 calls bad=0 / 実フレーム ≥ 公称の 99% (85,536,000 f))。
  - `4/4 PASS`。

## 5. 受入条件の判定

1. キャプチャ SAB の一括確保なし (661.8 MiB → 16.1 MiB、分割照合): **達成** (§2・§3)。
2. 分割照合 = 一括照合 (同一 ramp で不一致 0 / 一致): **達成** (§3 は合成データでの一致確認。実 ramp ソークは分割照合で 0 件)。
3. `e2e.sh --soak=1800` PASS・所要・load・PASS/FAIL を REPORT: **達成** (§4)。
4. 短シナリオ `com_ramp_b256_d2` の underrun 1 の再現有無: 今回の 2 回 (quick 1 回・soak 付き 1 回) はいずれも underrun 0。AU-17 で観測された underrun 1 は再現せず (1 回の再現有無のみ、確率的事象のため再現しないことは根拠にならない)。追跡は #998 [AU-16] に残す。

## 6. 未解決

- `com_ramp_b256_d2` の負荷依存 underrun (AU-17 で FAIL を 1 回観測) の根本原因: #998 [AU-16]。
- sine モードの分割照合の selftest: 未実施。
