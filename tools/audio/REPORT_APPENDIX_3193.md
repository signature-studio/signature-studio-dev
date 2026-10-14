# AU-35 (#3193) Safari の P1〜P4 を safaridriver 経由で測る経路 (付録)

> **正本**: `tools/audio/REPORT_AU2_CI.md` §10 (要約)。本付録は経路の設計・WebDriver BiDi の確認・検証・未解決の詳細。

## A. 結論

- Safari の harness 経路 (`harness/safari.mjs`・`run.mjs --browser safari`) を追加した。Linux runner では Safari を起動できず、Safari の P1〜P4 は**未測定**。
- Safari の WebDriver BiDi 対応は**未確定** (この run では一次情報を確定できなかった)。確かめ方は §B。
- 測定 commit = `7fdf2074` (コードを変えた最後の commit)。

## B. WebDriver BiDi 対応の確認 (受入 2)

- 確認に使った一次情報: WebKit のブログ索引 (`https://webkit.org/blog/`) と MDN の WebDriver BiDi reference (2026-03-12 更新)。どちらにも Safari の BiDi 対応の記載は無かった。**判定は未確定**。
- 確かめ方 (macOS): `node tools/audio/harness/safari_probe.mjs`。新規セッションで `webSocketUrl: true` を要求し、返った capabilities の `webSocketUrl` (文字列) の有無を 1 行の JSON で出す。終了コード 0 = あり / 1 = なし・エラー。
- BiDi が無くても経路は成り立つ。harness は classic WebDriver (`safaridriver`) だけを使う。BiDi は Firefox (`harness/bidi.mjs`) と同じ仕組みで、必要になったときの選択肢。

## C. 経路の設計

- `harness/safari.mjs`: `safaridriver -p <port>` を起動し、WebDriver classic を直叩きする (`POST /session` (`browserName: Safari`)・`/timeouts` (script 600 s)・`/url`・`/execute/async`・`DELETE`)。`{navigate, eval}` は `chrome.mjs` と同じ形で、`window.__done` の取り方は共通。
- `harness/run.mjs --browser chrome|edge|safari`: 既定は chrome (従来どおり)。`safari` で `withSafari` を使う。macOS では既定出力 (`SwitchAudioSource -t output -c`) が `BlackHole 2ch` でなければ終了コード 2 で止める (測らない)。Linux は `pactl get-default-sink` を結果 JSON の `default_output` に記録するだけで、判定はしない。
- `harness/safari_probe.mjs`: §B の確認用。
- `tools/audio/ci/audio-matrix.yaml` (草案・未適用): `macos-latest` × `safari` 行を追加。Safari 行だけ `sudo safaridriver --enable` を実行する。適用は #3192 (AU-34) の作業で PM が行う。
- 未検証 (macOS でしか確かめられない): Safari は headless でないため GUI セッションが要る。`safaridriver --enable` の要否と権限、Safari の AudioWorklet・SharedArrayBuffer・`crossOriginIsolated`、`SwitchAudioSource` による BlackHole 2ch への切替。

## D. 検証 (Linux・ブラウザ無し / Chrome)

| 検証 | 手順 | 結果 |
|---|---|---|
| 構文 | `node --check` (`run.mjs`・`safari.mjs`・`safari_probe.mjs`) | rc 0 |
| safaridriver の HTTP 手順 (mock) | `SAFARIDRIVER=$PWD/tools/audio/test/safaridriver_mock.mjs node tools/audio/test/safari_mock_test.mjs` | 4/4 PASS (JSON 戻り値・初回 URL・script timeout 600000・ページ例外の伝播) |
| probe の経路 (mock) | `SAFARIDRIVER=$PWD/tools/audio/test/safaridriver_mock.mjs node tools/audio/harness/safari_probe.mjs` | rc 1・`webSocketUrl` = null (mock は BiDi を返さない。経路の確認のみ) |
| Chrome 回帰 (`run.mjs` の変更の影響) | `node tools/audio/harness/run.mjs --only asio_sine_b256_d2,asio_sine_b256_96k,asio_sine_b512_96k` | 測定 commit `7fdf2074` で **3/3 PASS** (underrun 0・silence 0・sine maxErr 1.49e-8・wall 89.1 s・load avg 0.18 → 0.06) |

- Chrome の P1〜P3 の値 (参考・1 回・Linux の fake 出力): `asio_sine_b256_d2` burst 512・T 1536 (48000 Hz) / `asio_sine_b256_96k` burst 1024・T 2816 / `asio_sine_b512_96k` burst 1024・T 3072。REPORT_AU2_CI.md §5-1 の fake 行と同じ傾向。
- 測定 commit `7fdf2074` 以後のコード差分: `git diff 7fdf2074 HEAD -- tools/audio/src tools/audio/harness tools/audio/test tools/audio/ci tools/audio/build.sh` の出力は 0 行 (本付録の追記は `tools/audio/REPORT*` だけ)。

## E. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| macOS で Safari の P1〜P4 (n=3) を実測し、`safari_probe.mjs` で BiDi 対応を確かめる (受入 3 と §B) | Safari の値・BiDi 対応は未確定。macOS の既定出力の切替も未確認 | [AU-36] (子 #3193) |
| 草案 yaml (Safari 行) の `.github/workflows/` への適用と macOS での初回 dispatch | 未適用では Safari 行を実行できない | #3192 (AU-34) |
