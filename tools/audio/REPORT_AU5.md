# audio: AU-5 (#192) 付録 — 入力デバイス選択・controlPanel・入力喪失リセット

本体 `REPORT.md` §14 の全文 (250 行上限のため分割移動。内容は無変更)。

既知類型との関係: 該当なし (lift 欠陥ではなくランタイム shim)。

| 追加 | 内容 |
|---|---|
| `src/runtime/audio-input.ts` (`FlAudioInput`) | 権限の取得/要求 (`permission()`/`requestPermission()`)、audioinput 列挙、`select(deviceId)` (接続中はライブ切替、選択は storage に永続化)、MediaStreamSource を worklet node へ接続。選択 device が消えたら既定へフォールバック。track ended / device 消失は `lost` イベント |
| `FlAudioShimOptions.input` | in_ch>0 の ATTACH 毎に接続 (失敗しても出力は継続)。`lost` → `dev_events` に `FLA_EV_INPUT_CHANGED` (=16) → producer が `kAsioResetRequest` を発行 (`ctx.suspend` と同経路) |
| `FLA_CMD_CONTROL_PANEL` (=8) / `FlAudioShimOptions.controlPanel` | `flasio_control_panel()` が main の UI 代替を呼ぶ。UI 未登録なら `ASE_NotPresent` (FL 側は "Could not open ASIO control panel" 経路) |

検証 (`inventory.sh` 以外の e2e.sh 手順 = tsc → build.sh → `node harness/run.mjs` フル、headless Chrome 154 の fake device/UI、`inventory.sh` は固定ホームパス参照のため未実行):

| 回 | コミット | 結果 | 所要 | 開始時 load |
|---|---|---|---|---|
| 1 (pre-merge) | `1809e67` | 30/30 PASS (新規 5 + 既存 25) | 485 s | 0.04 |
| 2 (merged, 修正前) | `b66c676` | 32/33 PASS。`asio_ramp_b128_d2` のみ FAIL (underrun 1, silence 640) | 518 s | 0.45 |
| 2' (2 の単独再実行) | `b66c676` | `--only asio_ramp_b128_d2` 1/1 PASS (underrun 0, mismatch 0/961024) | 73 s | 0.13 |
| 3 (最終) | `a6212bc` | **33/33 PASS** (main 側 3 件を含む全 33 件), exit 0 | 498 s | 0.20 |

回 2 の FAIL は B=128 のランプ試験の揺れ (入力を使わないシナリオ・同一コードで回 2' は PASS)。再現性の確認は回 3 の PASS と回 2' による。`results/results.json` は回 3 の生成物。

| 新規シナリオ | 結果 |
|---|---|
| `asio_input_ui_connect_b256` | FlAudioInput 経由で RMS 0.141・相関 1.000・lag 1536f (従来の gum 直結と同値)・resets 0 |
| `asio_input_ui_controlpanel_switch` | `controlPanel` code=0、UI 代替が列挙 3 デバイス (Fake Default / Fake Audio Input 1 / 2) → `Fake Default Audio Input` から `Fake Audio Input 1` へライブ切替、切替後もループバック継続 (RMS 0.141) |
| `asio_controlpanel_no_ui` | UI 未登録 → `-1000` (ASE_NotPresent)、abort なし |
| `asio_input_lost_reset` | 合成 `ended` (`track.dispatchEvent(new Event("ended"))`。実デバイスの取り外しではない) → `kAsioResetRequest` 1 回受信、underruns 0 |
| `asio_input_denied_output_ok` | getUserMedia が NotAllowedError でも `permission: denied` イベント、出力は継続 (underruns 0, cb 1125) |

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FL 本体側の kAsioResetRequest 再初期化確認 | shim は ASIO コールバックまで発行を確認済み。FL がそれで再初期化するかは FL ブートが必要で未検証 | #192 (Refs) |
| 入力遅延の実機実測 | fake device の lag (1536f) までしか出ない | #187 (AU-2) |
| 製品 UI (パネル画面・ユーザジェスチャ導線) | 本 PR は部品と UI 代替フックまで | #184 (AU-9) |
