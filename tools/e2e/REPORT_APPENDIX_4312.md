# tools/e2e REPORT 付録 — gui-guest-boot の独立オラクル (#4312 / WIN-46)

親: `REPORT.md` の gui=wasm 節。#3495 受入 1 (`gui-guest-boot` の画素を独立オラクルと完全一致で判定) の実装。

## オラクルの作り方と独立性

- 期待画像: `tools/gui/golden/gen_golden_text8.py` (320x120 RGB)。`text_wasm_app.c` の `text_scene.inc` の 6 描画 (TextOutW・DrawTextW・TA_CENTER/TA_BASELINE/TA_RIGHT・OPAQUE 背景・複数行の DT_LEFT) を、Windows GDI の公開仕様と 8x8 フォントの寸法 (advance 8・高さ 8・ascent 7) だけから計算する。
- 独立性: shim の C (`src/gui_gdi.c` の 8x8 経路・`draw_text_run`) は読まない。従来ビルドとの比較はしない (従来ビルドとの一致では独立にならない)。
- 共有するのは `src/gui_font8x8.h` の公開ドメインのビットマップだけ (`gen_golden.py` と同じ)。シーンの値は `text_scene.inc` から手で写した。
- `tools/e2e/suite/checks.mjs` は `execFileSync` で生成スクリプトを呼び、base64 で `readback()` の結果と突き合わせる。判定は差 0 px。`lit > 0 && colors >= 2` は併用のまま残す。

## 判定の検出力 (ネガコン)

- 期待画像の 1 点 (`text_scene` 6 の色 `(180,220,255)` の B を 254 にずらす) を壊すと `gui-guest-boot` が FAIL (差 228 px、(44,80) で got=(180,220,255) want=(180,220,254))。`--driver puppeteer --targets preview` の実行で確認し (rc 1・SUMMARY PASS=10 FAIL=1 SKIP=2)、スクリプトは元に戻した (`cmp` で一致)。

## 実測 (commit は本 PR の HEAD)

- `bash tools/e2e/run.sh --driver both --targets preview,edge-sim` (`EMSDK_ENV` = 展開した emsdk・`TMPDIR=$RUNNER_TEMP`): **PASS 46 / FAIL 0 / SKIP 6**、rc 0、wall 57 s (ビルド・ゲスト emcc を含む)。基準 46 を下回らない。
- `gui-guest-boot` は 4 組とも PASS (実測 231〜725 ms・`frames=1`・`guest=test`・320x120)。
- 素材: `toolchain-emsdk` (emcc 6.0.12) を `$HOME/artifacts` から展開して使用。`fl-win64` は本検証では不要。mingw (`x86_64-w64-mingw32-gcc`) は `build_guest.sh` が apt で導入する。
