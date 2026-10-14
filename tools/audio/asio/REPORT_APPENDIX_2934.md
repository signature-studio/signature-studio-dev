# tools/audio/asio — #2934 [AU-26] 初期目標充填 T の下限 (FLA_F_T_FLOOR) と実測 (付録)

> 親: #2777 (根拠の実測付録は PR #2937 にあり未 merge)。本付録は main の数値だけで読めるよう、変更前 baseline も本 issue で測り直した。
> 測定は headless Chrome・Linux runner (4 コア)・単独実行。実オーディオデバイスでは測っていない。

## 1. 結論

- ASIO の `fla_open` 呼出に、初期 T の下限 **1536 frames (B=256 で depth 6)** を `FLA_F_T_FLOOR` で適用した。burst 探査の結果には依らない。
- 測定 commit `35938a59`: `com_ramp_b256_d2` を同一 HEAD で連続 **20 回, 20/20 PASS** (underrun 0・silence 0・ramp mismatch 0)。
- 変更前 (main `853f1940`) の 5 回: depth 4 の 1 回で underrun 1 (silence 3328)、depth 6 の 4 回は underrun 0。
- `lat_out` (FL へ報告する遅延): 前 3073 (depth 4) / 3585 (depth 6) → 後 **3585 (常時)**。増分 +512 frames (48 kHz で 10.7 ms) は depth 4 だった実行の分のみ。**採否は PM 判断** (§4)。
- main `3d37a190` 取り込み後の merge commit `69280d57` でも同一 HEAD で 20 回連続 **20/20 PASS** (§6)。

## 2. 実装

| 箇所 | 内容 |
|---|---|
| `tools/audio/src/flaudio.h` | `FLA_F_T_FLOOR = 1u << 2`・`FLA_T_FLOOR_FRAMES = 1536u` |
| `tools/audio/src/flaudio.c` `fla_open` | フラグが立つとき `depth >= ceil(1536 / B)` に上げる (`need` の後) |
| `tools/audio/src/flasio.c` `flasio_create_buffers` | `fla_open` 呼出に `FLA_F_T_FLOOR` を付与 |

DirectSound (`flds.c`)・WASAPI (`flwasapi.c`) はフラグを渡さないので挙動は変わらない。

下限が効く条件 (式からの計算。測定は B=256 のみ):

| B | 下限 depth | 増える条件 | 測定 |
|---|---|---|---|
| 256 | 6 | `need <= 5` (probe 由来の `res[0] <= 768`) のとき +512 frames | 測定済み (§3) |
| 512 | 3 | `need = 2` (burst <= 384) のときのみ +512 frames | 未測定 |
| 1024 以上 | 2 以下 | 変化なし | 未測定 |

## 3. 実測

### 3-1. 変更前 (main `853f1940`・5 回・既定の burst 探査)

| 実行 | 初期 depth | T | lat_out | underrun / silence | 判定 |
|---|---|---|---|---|---|
| r1 | 4 | 1024 | 3073 | 1 / 3328 | FAIL |
| r2〜r5 | 6 | 1536 | 3585 | 0 / 0 | PASS (4 回) |

### 3-2. 変更後 (測定 commit `35938a59`・同一 HEAD で 20 回連続)

- 20 回すべて: PASS・underrun 0・silence 0・lat_out 3585・T 1536・ramp 0 mismatch (240512 frames。1 回は 241024)。
- 判定基準 (underrun 0・silence 0・ramp bit-exact) は変えていない。
- 変更前は depth が probe で変わったが、変更後は depth 6 に固定され、lat_out が 3585 で揃った。

### 3-3. 親 e2e (測定 commit `35938a59`)

- `FL_WIN64_DIR` に `fl-win64` を展開して `bash tools/audio/e2e.sh --quick` を実行 → **rc 0・所要 5 分 43 秒**。
- 内訳: harness 44/44 PASS (`tools/audio/results/results.json`)・asio node check 126/126 PASS・asio COM 3/3 PASS (`com_ramp_b256_d2` は underrun 0・lat_out 3585)。

## 4. 増える遅延の採否 (PM 判断)

- 採用 = 本 PR を merge。不採用 = 本 PR を閉じる (または `flasio.c` の `FLA_F_T_FLOOR` 指定 1 行を戻す)。
- 増分は B=256 で最大 +512 frames (+10.7 ms @48 kHz)。depth 6 の機では増分 0。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| lat_out +512 frames の採否 | merge の可否。増分は §4 | PM (merge 判断) |
| producer が約 19 ms 書き込みを止める直接経路は未特定 (#2777 §3-1 と同じ) | 本対処は初期 T の固定で症状を抑えるもので、原因の特定ではない | #2777 |
| B=512・1024 の実測と実オーディオデバイスでの測定 | §2 の増分は式からの計算のみ | #2777 |
| B=128 の下限 (depth 12) の影響が未測定。`asio_ramp_b128_d2` は §6-1 の親 e2e で 1 回 FAIL (単独再実行は PASS)。main でも同シナリオは過去に揺れており、本 PR との切り分けは未了 | 初期 T の変化が B=128 にも及ぶ (§2 の表に行が無い) | #187 |

## 6. main 取り込み後の再測定 (merge commit `69280d57`)

main `3d37a190` を取り込んだ。競合は `docs/DOC_MAP.md` と `tools/audio/asio/REPORT.md` の追記行 2 件で、両側の行を残した (REPORT は 250 行上限のため #2934 と #2777 のポインタを 1 行に連結)。main 側の変更のうち検証経路に入るのは `tools/audio/asio/harness/run_com.mjs`・`com_page.mjs` (#2777 の計測 harness) だけで、`35938a59` の測定は本 HEAD の証拠にならないため、同一 HEAD `69280d57` で測り直した。

### 6-1. 親 e2e `bash tools/audio/e2e.sh --quick` (HEAD `69280d57`)

- 環境: `FL_WIN64_DIR` = fl-win64 の展開先 (`$RUNNER_TEMP`)・`EMSDK_ENV` = 上流 emsdk 6.0.12 (`$RUNNER_TEMP/emsdk`)。`toolchain-emsdk` 素材は本 run の `$ARTIFACTS_DIR` に無かった。
- 1 回目: harness **43/44 PASS**、wall 261.0 s、load 0.82→0.85。FAIL は `asio_ramp_b128_d2` (underrun 1・silence 6656・ramp 不一致 163456/192384)。harness が非 0 で終了したため、同じ呼出では ASIO 検収まで進まなかった。
- FAIL の単独再実行 `node harness/run.mjs --quick --only asio_ramp_b128_d2` (同 HEAD・同ビルド): **1/1 PASS**、underrun 0・silence 0・ramp 不一致 0/192896、57.5 s。
- ASIO 検収 `bash tools/audio/asio/e2e.sh --quick`: **rc 0**。node check 126/126 PASS。COM 3/3 PASS (`com_ramp_b256_d2`: underrun 0・silence 0・ramp 0/144768・lat_out 3585)。

### 6-2. `com_ramp_b256_d2` の同一 HEAD 連続 20 回

`node harness/run_com.mjs --quick --only com_ramp_b256_d2` を 20 回連続。**20/20 PASS**。全回 underrun 0・silence 0・lat_out 3585・ramp 0 mismatch (144256〜144896 frames)。1 回あたり約 57 s。

### 6-3. 測定 commit と差分

- 測定 commit: `69280d57` (コードを変えた最後の commit。main 取り込みの merge)。
- `git diff 69280d57 HEAD -- tools/audio/src tools/audio/asio` の出力: 空 (HEAD は本付録の追記 commit のみ)。

### 6-4. 判定

- main 取り込みで `tools/audio/src` は変わっていない (本 PR の変更以外に差分なし)。`tools/audio/asio` の main 側変更は計測 harness のみで、本 HEAD での COM 20/20 PASS は §6-2 の実測が根拠。
- 親 e2e の B=128 FAIL は一過性か既存の揺れかを本 run では切り分けていない (§5 の最終行)。
