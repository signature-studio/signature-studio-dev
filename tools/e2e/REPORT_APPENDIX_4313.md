# tools/e2e REPORT 付録 — gui-guest-boot のネガコン (a)(b)(c) (#4313 / WIN-47)

親: `REPORT.md` の gui=wasm 節。#3495 受入 2 (`gui=wasm` の検査にネガコン (a)(b)(c) を入れる) の実装。前提の #4312 (オラクル) は PR #4341 で merge 済み。

## 実装

- (c) `gui-guest-oracle-negctrl` (常設・`suite/checks.mjs`): 独立オラクル (`gen_golden_text8.py`) の画素 (44,80) の B を 1 改竄し、`gui-guest-boot` と同じ比較 (`guiOracleJs`) に当てる。期待は **差 1 px・位置 (44,80)**。比較が効いていれば PASS (= 検出した)、効いていなければ FAIL。`fl-boot-negctrl` と同じ形。
- (a)(b) は常設の check にせず、製品側に一時的なミュータントを当てて測り、ソースを元に戻した (`git diff --stat` 空を確認)。

## 測定

測定 commit = `2c5bf630a` (コードを変えた最後の commit: `tools/e2e/suite/checks.mjs` の (c) 追加)。`git diff 2c5bf630a HEAD -- tools/e2e/suite tools/gui src` は本付録の commit 後も 0 行。

| 条件 | ドライバ | 結果 | 所要 (wall) | rc |
|---|---|---|---|---|
| 基準 main `25fa426cf` (検査追加前) | 両方 × preview,edge-sim | **PASS 50 / FAIL 0 / SKIP 6** | 74.5 s | 0 |
| HEAD `2c5bf630a` (通常) | 両方 × preview,edge-sim | **PASS 54 / FAIL 0 / SKIP 6** | 25 s | 0 |
| HEAD + (b) 描画しない | 両方 × preview | **PASS 22 / FAIL 4 / SKIP 4**、`gui-guest-boot` FAIL ×2 + `gui-guest-oracle-negctrl` FAIL ×2 | 17 s | 1 |
| HEAD + (a) GuiHost を付けない | 両方 × preview | **PASS 22 / FAIL 4 / SKIP 4**、`gui-guest-boot` FAIL ×2 + `gui-guest-oracle-negctrl` FAIL ×2 | 198 s (14:22:22 → 14:25:40。state=error で 30 s 待ち × 4 組) | 1 |

- (c) 4 組 PASS (HEAD 通常): `1 画素改竄 (44,80) を比較で検出: diff=1 got=[180,220,255] want=[180,220,254]`。
- (b) の FAIL 理由 (両ドライバ): `lit=0`・`diff=38400` (320x120 の全画素)・先頭 (0,0) で `got=[0,0,0] want=[32,32,48]`。フレームは届く (`frames` は進む) が画素が空。`gui-guest-oracle-negctrl` も同様に全画素差で FAIL するのは、比較が 1 画素ではなく全体を見ていることの確認になる。
- (a) の FAIL 理由: `state=error`・`error=[object ErrorEvent]` (GuiHost が無いので `window.__guiGuest.readback` が例外になる)。**画素の差分による FAIL ではない**。`state==='running'` の検査で止まる。「縞だけ」の画素状態を直接は測っていない。
- 順序: (a)(b) は最初に作業ツリー (未コミットの (c) 追加を含む) で測って同じ結果を得た。その後 HEAD `2c5bf630a` で測り直したものを表に載せた。製品ソースは各測定の後に元に戻し、`git diff --stat` が空であることを確認した。

## 独立性

オラクルの作り方と独立性は REPORT_APPENDIX_4312.md の通り (変更なし)。本付録は比較の検出力だけを測る。

## 再現

```sh
EMSDK_ENV=<emsdk_env.sh> bash tools/e2e/run.sh --driver both --targets preview,edge-sim   # 通常 (PASS 54 / FAIL 0 / SKIP 6)
# (b): tools/gui/test/text_wasm_app.c の WM_PAINT で text_scene_draw(g_memdc, 0); を消す → FAIL (lit=0)
# (a): src/runtime/gui_guest.ts で GuiHost.attach の前に return する → FAIL (state=error)
# 後で必ず元に戻し git diff --stat が空であることを確認する
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `text_wasm_e2e.sh` の回帰 (FreeType の wasm32 build と font 取得が要る) | 本 run では未実行 | #3495 (WIN-27) |
