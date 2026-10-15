# tools/audio/asio — #2934 [AU-26] 初期目標充填 T の下限 (FLA_F_T_FLOOR) と実測 (付録)

> 親: #2777 (根拠の実測付録は [REPORT_APPENDIX_2777.md](REPORT_APPENDIX_2777.md)。PR #2937 で main に merge 済み)。本付録は main の数値だけで読めるよう、変更前 baseline も本 issue で測り直した。
> 測定は headless Chrome・Linux runner (4 コア)・単独実行。実オーディオデバイスでは測っていない。

## 1. 結論

- ASIO の `fla_open` 呼出に、初期 T の下限 **1536 frames (B=256 で depth 6)** を `FLA_F_T_FLOOR` で適用した。burst 探査の結果には依らない。
- 測定 commit `35938a59`: `com_ramp_b256_d2` を同一 HEAD で連続 **20 回, 20/20 PASS** (underrun 0・silence 0・ramp mismatch 0)。
- 変更前 (main `853f1940`) の 5 回: depth 4 の 1 回で underrun 1 (silence 3328)、depth 6 の 4 回は underrun 0。
- `lat_out` (FL へ報告する遅延): 前 3073 (depth 4) / 3585 (depth 6) → 後 **3585 (常時)**。B=256 の増分 +512 frames (48 kHz で 10.7 ms) は depth 4 だった実行の分のみ。**採否は依頼者判断 U1** (§4)。
- main `3d37a190` 取り込み後の merge commit `69280d57` でも同一 HEAD で 20 回連続 **20/20 PASS** (§6)。
- 増分の式 (式からの計算。depth 引数 2 の場合): `max(0, D − max(2, need)) × B` frames、D = ceil(1536 / B)。到達可能な最大は B=128 で +1152 frames (24.0 ms)、B=256 で +1024 frames (21.3 ms)、B=512 で +512 frames、B=1024 で 0 (§2)。
- B=128 の親 e2e 系シナリオ `asio_ramp_b128_d2` は、PR HEAD と同じコードで 7 回中 2 回 FAIL。基点 `3d37a190` は 5 回 0 FAIL。**本 PR 由来かは切り分けられていない** (§5・§6-5)。

## 2. 実装

| 箇所 | 内容 |
|---|---|
| `tools/audio/src/flaudio.h` | `FLA_F_T_FLOOR = 1u << 2`・`FLA_T_FLOOR_FRAMES = 1536u` |
| `tools/audio/src/flaudio.c` `fla_open` | フラグが立つとき `depth >= ceil(1536 / B)` に上げる (`need` の後) |
| `tools/audio/src/flasio.c` `flasio_create_buffers` | `fla_open` 呼出に `FLA_F_T_FLOOR` を付与 |

DirectSound (`flds.c`)・WASAPI (`flwasapi.c`) はフラグを渡さないので挙動は変わらない。

floor は動的調整の下限にもなる。`flasio.c` の thread_fn は `Tn = max(need, T0) + esc` (T0 = open 時の T。floor 後の値) で T を決めるため、増分は初期だけでなくセッション中ずっと残る。run 中に burst が縮んでも T は T0 を下回らない。

増分の式 (式からの計算。測定値とは分けて読む):

- 増分 (frames) = `max(0, D − max(depth 引数, need)) × B`。D = ceil(1536 / B)。
- `need = (burst + burst/4 + 2B − 1) / B` (整数除算)。burst は `fla_open` 内で 128 の倍数に切り上げた値。burst の最小は 128 なので、B=128 の need は 3 以上 (need 2 は起きない)。
- depth 引数は `flasio.c` の既定 `A.depth = 2`。下表は depth 引数 2 の場合。`flasio_configure` で大きい depth が渡されると増分は減る。

| B | D | need → 増分 (frames、括弧は 48 kHz の ms) | 測定 |
|---|---|---|---|
| 128 | 12 | 3: +1152 (24.0) / 4: +1024 / 5: +896 / 6: +768 / 7: +640 / 8: +512 / 9: +384 / 10: +256 / 11: +128 / 12 以上: 0 | 測定は depth 11 → 12 の +128 のみ (§6-5) |
| 256 | 6 | 2: +1024 (21.3) / 3: +768 / 4: +512 / 5: +256 / 6 以上: 0 | 測定は depth 4 → 6 の +512 のみ (§3-1 r1) |
| 512 | 3 | 2: +512 (10.7) / 3 以上: 0 | 未測定 |
| 1024 | 2 | 常に 0 | 未測定 |

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

## 4. 増える遅延の採否 (依頼者判断 U1・needs-user-input)

- 判断者は依頼者。reviewer・PM は代行しない。`needs-user-input` は #2934 に付いている (質問文は #2934 の本文先頭)。
- 採用 = 本 PR を merge。不採用 = 本 PR を閉じる (または `flasio.c` の `FLA_F_T_FLOOR` 指定 1 行を戻す)。
- 既定案 (PM): 変えない (不採用で保留)。merge せず・閉じず open のまま残す。
- 判断材料 (depth 引数 2 の場合。増分は式からの計算。§2):
  - 典型値 (burst 512 と 1024 の 2 条件。REPORT_AU2_CI.md では 48 kHz の burst は 512f が大半):
    - B=128: burst 512 (need 6) で +768 frames (16.0 ms)、burst 1024 (need 11) で +128 frames (2.7 ms)。
    - B=256: burst 512 (need 4) で +512 frames (10.7 ms)、burst 1024 (need 6) で 0。
  - 最大: B=128 +1152 frames (24.0 ms、need 3)、B=256 +1024 frames (21.3 ms、need 2)。どちらも burst 128 の条件で、記録上の典型ではない。B=512 は burst 128〜384 の条件でのみ +512 (need 2)、それ以上は 0。B=1024: 常に 0。
  - 測定した増分: B=256 は +512 (depth 4 → 6、§3-1)。B=128 は +128 (基点 T 1408 → PR T 1536、§6-5)。
- **open 時 depth は run ごとに変わる (未確定の点あり)**: 基点 B=128 の T 1408 は stats から直接読める (`latency_changes` 0 のため T は run 中に変わらず、T = open 時の depth × B = 11 × 128)。ただし open 時の burst 値 (`fla_cmd` OPEN の `res[0]`) は未記録のため、「depth 11 = burst 1024」は式からの解釈で未確認。run 中の `burst_obs` (512) は open 時の値ではない。同じ B=128 でも、同日の main 実行 (`tools/audio/results/results.json`・2026-10-13) では `asio_ramp_b128_d2` が depth 6 (T 768)、`asio_loop_noise_b128` が depth 11 (T 1408) で、どちらも `burst_obs` 512・`latency_changes` 0。したがって B=128 の増分は +128 (depth 11 の run) 〜 +768 (depth 6 の run) の幅で、run ごとに決まる。open 時 burst を 1 回ログに出せば確定できる (未実施)。
- B=128 の FAIL 切り分け (§5) が出るまで、B=128 を含めた影響の判断は保留になる。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 増える遅延 (lat_out) の採否 (U1)。§4 | merge の可否。既定案は不採用で保留 | 依頼者判断 U1 (#2934 needs-user-input) |
| B=128 の `asio_ramp_b128_d2` FAIL の、本 PR 由来か否か。PR HEAD と同じコードで 7 回中 2 回 FAIL (underrun 1)、基点 `3d37a190` は 5 回 0 FAIL (§6-5)。母数が少なく有意差は言えず、本 PR 由来を否定できない。main 側にも同シナリオの「1 回目 FAIL・再実行 PASS」の記録が複数ある: `tools/audio/REPORT_DS.md` (1 回目 FAIL・再実行 PASS・一過性の負荷揺れ扱い)、`tools/audio/REPORT_AU5.md` (`b66c676` 回 2 FAIL・回 2' 単独 PASS)、`tools/audio/REPORT_AU2_CI.md` (quick FAIL・負荷起因の疑い、未確認)。原因は main 側でも未切り分け | 親 e2e の受入条件 3 (rc 0) は未達のまま。PR は B=128 の初期 T を 1408 → 1536 に変える | #187 |
| B=128 に下限を適用するか (範囲の選択。B≥256 に限れば B=128 の経路は基点と同じ)。本付録では変更していない | B=128 の FAIL 切り分けと、§4 の増分 (最大 +1152) に効く | PM (範囲の判断) |
| producer が約 19 ms 書き込みを止める直接経路は未特定 (#2777 §3-1 と同じ) | 本対処は初期 T の固定で症状を抑えるもので、原因の特定ではない | #2777 |
| B=512・1024 の実測と実オーディオデバイスでの測定 | §2 の増分は式からの計算のみ | #2777 |

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
- `git diff 69280d57 HEAD -- tools/audio/src tools/audio/asio ':!*.md'` の出力: 空。HEAD の後続 commit は付録と DOC_MAP の md のみで、`:!*.md` で除外しても差分は 0 行 (md を除かないと付録の追記が出るため、除外を付ける)。

### 6-4. 判定

- main 取り込みで `tools/audio/src` は変わっていない (本 PR の変更以外に差分なし)。`tools/audio/asio` の main 側変更は計測 harness のみで、本 HEAD での COM 20/20 PASS は §6-2 の実測が根拠。
- 親 e2e の B=128 FAIL の切り分けは §6-5 で行った (結果: 切り分け不能。§5)。

### 6-5. B=128 の単独再実行 5 回連続 (HEAD `ad8c1353`) と基点 `3d37a190` 5 回

- 手順: `cd tools/audio && node harness/run.mjs --quick --only asio_ramp_b128_d2`。`FL_WIN64_DIR` = fl-win64 の展開先・`EMSDK_ENV` = 上流 emsdk 6.0.12 (本 run で取得し `tools/audio/build.sh` でビルド)。
- 基点: detached worktree `3d37a190` で同じ手順 (変更は `tools/audio/src` の 3 ファイルのみが PR 側にあるため、基点はその変更を含まない)。
- 回数は同一 HEAD での連続実行。

| 実行 | HEAD | 結果 | underrun | silence | ramp 不一致 | T (lat_out) | lat_changes | dev_fill min |
|---|---|---|---|---|---|---|---|---|
| PR r1 | `ad8c1353` | **FAIL** | 1 | 13312 | 162432/192384 | 1536 (3585) | 2 | 0 |
| PR r2 | `ad8c1353` | PASS | 0 | 0 | 0/192384 | 1536 (3585) | 0 | 1152 |
| PR r3〜r5 | `ad8c1353` | PASS ×3 | 0 | 0 | 0/192896 | 1536 (3585) | 0 | 1152 |
| 基点 r1〜r5 | `3d37a190` | PASS ×5 | 0 | 0 | 0/192896 | 1408 (3457) | 0 | 1024 |

- PR 側の同一コードの記録: 69280d57 の親 e2e 1 回目 FAIL (§6-1。underrun 1・silence 6656) と、その単独再実行 PASS (§6-1)。ad8c1353 の 5 回 (上表) と合わせて、PR 側は 7 回中 2 回 FAIL。
- 基点 T 1408 は depth 11。stats の T と `latency_changes` 0 から、open 時の depth × B = 1408 と読める (run 中に T は変わっていない)。open 時の burst 値 (`res[0]`) は未記録のため、depth 11 ↔ burst 1024 (式からの逆算) は未確認。ログの `burst=512` は run 中の `burst_obs` で、open 時の値ではない (§4 の run ごとの幅を参照)。
- 判定: 基点 0/5 と PR 2/7 は母数が少なく有意差は言えない。FAIL run の機構 (ring の残量が 0 まで枯渇・lat_changes が 2) は未特定。
- **結論: 本 PR 由来かは切り分けられていない**。PR の変更で B=128 の初期 T が 1408 → 1536 になり、FAIL は変更後の経路で起きている。本 PR 由来を否定できない。親 e2e の受入条件 (rc 0) は未達のまま (§5)。
