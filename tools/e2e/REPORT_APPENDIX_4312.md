# tools/e2e REPORT 付録 — gui-guest-boot の独立オラクル (#4312 / WIN-46)

親: `REPORT.md` の gui=wasm 節。#3495 受入 1 (`gui-guest-boot` の画素を独立オラクルと完全一致で判定) の実装。

## オラクルの作り方と独立性

- 期待画像: `tools/gui/golden/gen_golden_text8.py` (320x120 RGB)。`text_wasm_app.c` の `text_scene.inc` の 6 描画 (TextOutW・DrawTextW・TA_CENTER/TA_BASELINE/TA_RIGHT・OPAQUE 背景・複数行の DT_LEFT) を、Windows GDI の公開仕様と 8x8 フォントの寸法 (advance 8・高さ 8・ascent 7) だけから計算する。
- 独立性: shim の C (`src/gui_gdi.c` の 8x8 経路・`draw_text_run`) は読まない。従来ビルドとの比較はしない (従来ビルドとの一致では独立にならない)。
- 共有するのは `src/gui_font8x8.h` の公開ドメインのビットマップだけ (`gen_golden.py` と同じ)。シーンの値は `text_scene.inc` から手で写した。
- `tools/e2e/suite/checks.mjs` は `execFileSync` で生成スクリプトを呼び、base64 で `readback()` の結果と突き合わせる。判定は差 0 px。`lit > 0 && colors >= 2` は併用のまま残す。

## 判定の検出力 (ネガコン)

- 期待画像の 1 点 (`text_scene` 6 の色 `(180,220,255)` の B を 254 にずらす) を壊すと `gui-guest-boot` が FAIL (差 228 px、(44,80) で got=(180,220,255) want=(180,220,254))。
- 測定 commit `ead0f325e` (現 HEAD) で再実行: `--driver puppeteer --targets preview` = **rc 1・SUMMARY PASS=11 FAIL=1 SKIP=2**。FAIL は `gui-guest-boot` のみ (差 228 px、(44,80) で got=(180,220,255) want=(180,220,254))。ログ `$RUNNER_TEMP/negctl_head.log`。スクリプトは元に戻し、`cmp` で HEAD と一致を確認した。

## 実測 (測定 commit `ead0f325e` = main `6c53e1dc7` 取り込み後の現 HEAD)

- `bash tools/e2e/run.sh --driver both --targets preview,edge-sim` (`EMSDK_ENV` = `$RUNNER_TEMP/emsdk/emsdk_env.sh` (emsdk 6.0.12、`e2e.yaml` と同手順で導入)・`TMPDIR=$RUNNER_TEMP`): **PASS 50 / FAIL 0 / SKIP 6**、rc 0、wall 47 s (ビルド・ゲスト emcc を含む)、開始時 load average 0.51 / 1 分。ログ `$RUNNER_TEMP/e2e_head.log`。
- 内訳: `gui-guest-boot` 4 組 PASS (所要 393/211/357/201 ms。組の対応は未記録。`state==='running'`・`frames=1`・`guest=test`・canvas 320x120・lit 38400 px・色 ≥7・reach 25 行 `CreateWindowExA=1 BeginPaint=1 BitBlt=1 WM_PAINT=1`)。`gui-guest-tamper` 4 組 PASS (`part の sha256 不一致`)。`fl-boot-negctrl` 4 組 PASS (テストゲスト `guest:"test"` に対し `期待 "fl" / 実際 "test"` で FAIL を確認)。SKIP 6 = `fl-boot` × 4 (`E2E_REQUIRE_FL` 未設定) + `edge-policy` の preview 側 × 2。
- 比較: 以前の基準 (旧 HEAD `0e00e39d7`・main 取り込み前) は PASS 46。増分 4 は main 側で入った `fl-boot-negctrl` × 4 組 (`git diff 0e00e39d7 ae5d13696 -- tools/e2e/suite` で追加を確認)。`ae5d13696` から `ead0f325e` までは `tools/e2e/suite` に差分が無い (`git diff ae5d13696 ead0f325e -- tools/e2e/suite` = 0 行)。
- 素材: `toolchain-emsdk` (emcc 6.0.12) を `e2e.yaml` と同じ手順で `$RUNNER_TEMP` に導入。`fl-win64` は本検証では不要。mingw (`x86_64-w64-mingw32-gcc`) は `build_guest.sh` が apt で導入する。
- 独立性の境界: 仕様から導いたもの = TA_* による基点配置・OPAQUE の背景矩形・DT_* の配置と行分割 (Windows GDI の公開仕様)。8x8 経路の約束事 = 文字幅 advance 8・高さ 8・ascent 7 (shim の 8x8 経路が採る寸法。GDI の公開仕様からは導けない)。

## 依存

- `tools/e2e/suite/checks.mjs` は import 時に `python3` を `execFileSync` で同期実行する (`gen_golden_text8.py -`)。python3 が無い環境では e2e スイートの全 check が止まる。`e2e.yaml` の runner と本 run は python3 3.14 を使用。
