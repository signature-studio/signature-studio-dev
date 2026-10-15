# REPORT 付録 — #4447 (LD-219): gui flengine e2e に FLEngine 起動の dispatch 件数を出す

自動生成ではない。親 #4093 (LD-193) で「gui flengine e2e は dispatch 件数を出さない」ため前後比較できなかった項目を埋める。

## 1. 取得方法と定義

- **定義**: dispatch 数 = 「dispatch した unit 数」。`tools/flelift/boot/fle_boot.mjs:256` の定義 (`units_run`) と同じ。
- **取得元**: `m11_ov.c` の `g_units_run` (`m11_units_run()`)。gui の wasm は `m11_build.sh` の EXPORTS で `_m11_units_run` を既に export しているため、ビルド変更は無し。
- **出力**: `tools/gui/flengine/run.mjs` の結果 JSON に `units_dispatched` を追加 (`units_run` と同値の別名。flelift の語彙に合わせる)。
- **却下した候補**: `m11_disp_count()` は `m11_disp_n` (間接呼出テーブルの件数 = 8621) を返すだけで dispatch 件数ではない。`disp_entries` と同じ値のため使わない。

## 2. 前後比較 (再測定は未実施)

**状態: 未解決。下表は受入の根拠にしない。** 差し戻し (oc-review round 1) の指摘 1 を、この run では再測定できなかった。

- 測定 commit: `9bfcc26a3` (`feat(gui): report units_dispatched`)。コード差分は `tools/gui/flengine/run.mjs` の 1 行だけ。
- 旧表の問題: 「`a4a620a9` (HEAD `9bfcc26a3`)」側は HEAD の `tools/shim/src/heap.c` (blob `01bfe4b01`) をそのまま使った。`a4a620a9` の blob は `45ba1484e` で、`01bfe4b01` には後続の `7278e8571` (fix(shim): report HeapFree like the native reference, #2821) が入る。つまり旧表の比較は `cde475fbc` と `01bfe4b01` の比較で、issue #4447 の受入 (`a4a620a9^` と `a4a620a9`) とは一致しない。
- 必要な再測定: `a4a620a9^` 側は `cde475fbc`、`a4a620a9` 側は `45ba1484e` を `tools/shim/src/heap.c` に入れ、同一 HEAD で `build.sh` → `run.mjs` を実行する。
- 再測定を止めた理由: `tools/m11/work` (work-m11) が無く、`emcc`・`retdec-decompiler`・`x86_64-w64-mingw32-gcc` が PATH に無い。`$HOME/artifacts` は `fl-win64.tar.zst` のみ。必要な素材は `work-m11 toolchain-emsdk toolchain-retdec apt-mingw` (PR 本文の `oc_artifacts:` 行で指定)。

旧表 (参考。受入根拠ではない):

| 項目 | `cde475fbc` (`a4a620a9^` の heap.c) | `01bfe4b01` (HEAD の heap.c) |
|---|---|---|
| `units_dispatched` | 109 | 109 |
| `units_run` | 109 | 109 |
| `init_count` | 111 | 111 |
| `icall_miss` | 7 | 7 |
| GetMem / FreeMem | 760 / 24 | 760 / 24 |

- 前回 `65844e9ef` の実測の出典は `tools/liftdiff/REPORT_APPENDIX_LD136.md` §7 (B1 boot parity 行: `52 (base 52) · 560 · 20 · 5`)。この行には units_run 109・GetMem 760 の値は無い。`65844e9ef:tools/gui/flengine/results/boot.json` は `units_run` 109・`GetMem` 761・`FastMM_GetMem(407a50)` 782 (同 commit の結果 JSON から直接確認)。

## 3. boot.json の GetMem / FastMM の変化

- `results/boot.json` の差分 (`9bfcc26a3` → `HEAD`): `GetMem 761→760`・`FastMM_GetMem(407a50) 782→781`。`units_run` 109 と `FreeMem` 24 は変わらない。
- 結果 JSON を生成した run の番号・素材・commit は確認できなかった (旧 run のログが無い)。したがって「この変化の原因」は実測では確定していない。
- 候補 (未測定): `65844e9ef` → `9bfcc26a3` の間に入った `tools/m11/m11_ov.c` の変更 `22c914300` (`fix(m11): transcribe function_40d210 (FillChar memset) n>32 body`, #3921)。`function_40d210` は `m11_ov.c` 内の GetMem 周辺 (行 966・982・993) から呼ばれるため、GetMem 件数を 1 減らす経路として妥当な候補。ただし、この変更を外して測って確かめるまでは原因とは言えない。
- `run.mjs` の変更 (`33585cb01`・`7f54678a7` 系の survey 隔離) は survey モードの処理で、通常起動の boot 経路には入らない (`git diff 65844e9ef 9bfcc26a3 -- tools/gui/flengine/run.mjs` で確認)。
- 結論: `units_dispatched` の追加自体は GetMem を変えない。GetMem の 1 件減は上記の m11 側変更に由来する可能性が高い。確定には `22c914300` の前後を同一 HEAD で測り直す必要があり、この run では未実施。

## 4. e2e 実測 (測定 commit `9bfcc26a3`)

- 実行: `bash tools/gui/flengine/e2e.sh` を foreground で 1 回 (前回 run の記録)。所要 620 s。load 開始 0.23 / 終了 1.17。nproc 4。
- judge 14/15 (exit 1)。FAIL は B1 のみ。`units_run 109 (base 109)` `dllmain True` `GetMem 760 (base 761)` `FreeMem 24` `icall_miss 7`。`65844e9ef` と同じ FAIL 形。
- native selftest・pe_image parity・pe_image e2e・ネガコン N1〜N10 は期待どおり。
- `units_dispatched` は JSON 上で 109。

## 5. 製品 KPI (前後)

- 起動 dispatch 数: 前 109 / 後 109 (差 0)。ただし前側は上記 §2 の再測定未実施のため、比較としては未確定。
- 通過 unit 数: 前 109 / 後 109 (同上)。
- 最初のウィンドウ: P4 `hwnd=0x1100013`・P5 `hwnd=0x1100012` (ともに PASS)。
- `tools/flelift/boot` の 209 dispatch とは別の経路 (GUI shim 経路の値)。混同しない。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `a4a620a9^` / `a4a620a9` の heap.c を正しく差し替えた再測定 (指摘 1) | 受入「前後を REPORT に書く」が未達。KPI の前後比較は確定していない | 本 PR で追跡 (素材 `work-m11 toolchain-emsdk toolchain-retdec apt-mingw` を指定して再実行) |
| GetMem 760 対 761 の原因 (`22c914300` が候補) | judge B1 の 1 件差 (本 PR 前から同じ FAIL) | 起票なし (受入条件の外。原因の切り分けは未実施) |
