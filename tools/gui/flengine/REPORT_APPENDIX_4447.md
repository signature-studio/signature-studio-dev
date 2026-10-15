# REPORT 付録 — #4447 (LD-219): gui flengine e2e に FLEngine 起動の dispatch 件数を出す

自動生成ではない。親 #4093 (LD-193) で「gui flengine e2e は dispatch 件数を出さない」ため前後比較できなかった項目を埋める。

## 1. 取得方法と定義

- **定義**: dispatch 数 = 「dispatch した unit 数」。`tools/flelift/boot/fle_boot.mjs:256` の定義 (`units_run`) と同じ。
- **取得元**: `m11_ov.c` の `g_units_run` (`m11_units_run()`)。gui の wasm は `m11_build.sh` の EXPORTS で `_m11_units_run` を既に export しているため、ビルド変更は無し。
- **出力**: `tools/gui/flengine/run.mjs` の結果 JSON に `units_dispatched` を追加 (`units_run` と同値の別名。flelift の語彙に合わせる)。測定 commit `9bfcc26a3`。
- **却下した候補**: `m11_disp_count()` は `m11_disp_n` (間接呼出テーブルの件数 = 8621) を返すだけで dispatch 件数ではない。`disp_entries` と同じ値のため使わない。

## 2. 前後比較 (受入 2)

**状態: 達成。** 基準環境 (`fl-win64` の PE あり・IR を再生成) で、`a4a620a9^` と `a4a620a9` の両側とも `units_dispatched` = 109 (基準 109 を再現)。前後の差は 0。

測定条件:

- 測定 code HEAD: `1adfc37aa`。`git diff 9bfcc26a3 1adfc37aa -- tools/gui/flengine/run.mjs tools/shim tools/m11` は空。
- 素材: [WIN64] の `extracted/block00031_PE.bin` (`fl-win64`)・[EMSDK] (`toolchain-emsdk`)・[RETDEC] (`toolchain-retdec`)・`work-m11` (`tools/m11/work/`、読取のみ)。
- 差し替え: `tools/shim/src/heap.c` のみ。blob は `a4a620a9^` = `cde475fbc`、`a4a620a9` = `45ba1484e`。HEAD の blob は `01bfe4b01` (`9bfcc26a3` と同じ)。
- 手順 (`e2e.sh` step 0 と同じ複製方式。`tools/m11` は読取のみ): 複製先 `tools/gui/work/flengine/tree/` に `m11`・`shim`・`shared`・`m2`・`m5`・`m6/ottlib.py` を複製 → 複製側で `m11_gen_ir2.sh` → `m11_wndseed.sh` → `m11_build.sh` → 各側で heap.c を差し替えて `FL_WIN64_DIR=<fl-win64> bash tools/gui/flengine/build.sh` → `node tools/gui/flengine/run.mjs`。
- 所要 (実測): `m11_gen_ir2.sh` 52 s、`m11_wndseed.sh` 3 min 30 s (WNDCLASS-CHECK PASS、instances 11、最終 IR 未定義 0)、`m11_build.sh` 32 s、`build.sh` 各 19〜23 s、`run.mjs` 各 0.5 s 程度。
- 検査: `m11_wndseed.sh` の WNDCLASS-CHECK PASS。build の signature mismatch / undefined / duplicate はどちらも 0。

結果 (同一 HEAD `1adfc37aa`・同一 IR・PE あり):

| 項目 | `a4a620a9^` (heap.c `cde475fbc`) | `a4a620a9` (heap.c `45ba1484e`) | 基準 (`9bfcc26a3` の boot.json) |
|---|---|---|---|
| build | rc 0 | rc 0 | - |
| run | rc 0 | rc 0 | - |
| `boot_threw` | なし | なし | - |
| `dllmain_done` | true | true | - |
| `units_total` | 942 | 942 | - |
| `units_run` | 109 | 109 | 109 |
| `units_dispatched` | 109 | 109 | 109 |
| `init_count` | 111 | 111 | - |
| `icall_miss` | 7 | 7 | - |
| `gui_icall_calls` | 6 | 6 | - |
| GetMem / FreeMem | 760 / 24 | 760 / 24 | 761 / 24 |
| FastMM_GetMem(407a50) | 781 | 781 | 782 |

- 判定: 両側 `units_dispatched` = 109、差 0。基準 109 を再現した。
- GetMem / FastMM は両側 760 / 781 で一致する。基準 (761 / 782) との 1 件差は §3。

## 3. boot.json の GetMem / FastMM の差 (`22c914300` 周辺)

- `results/boot.json` の GetMem / FastMM は `9bfcc26a3` の値 (761 / 782) のまま。本 PR では変えていない (`results/boot.json` の差分は `units_dispatched` 行だけ)。
- 今回の測定 (基準環境・IR 再生成) では、両側とも GetMem 760 / FastMM 781。`heap.c` の差し替え (`cde475fbc` ↔ `45ba1484e`) では GetMem は変わらないことが確定した。
- よって 761 → 760 は `heap.c` 以外の差。`m11_ov.c` 側の `22c914300` が原因かは、本付録では未測定 (`m11_ov.c` を差し替えた基準環境の測定は行っていない)。
- 761 と 760 のどちらが現 pipeline の正しい値かは未確定。judge の B1 基準 (761) との扱いは未解決表。

## 4. e2e 実測

- 測定 commit `9bfcc26a3` の e2e (`bash tools/gui/flengine/e2e.sh`) の記録: 所要 620 s、judge 14/15 (FAIL は B1 のみ: `GetMem 760 (base 761)`)。
- 本 head (`1adfc37aa`) では `e2e.sh` 全体 (judge・ネガコン・survey) は再実行していない。`9bfcc26a3` から code 差分は 0 (`run.mjs`・`tools/shim`・`tools/m11` の diff は空) なので、WORKFLOW §6 により再測定は不要とした。
- 本 head で実行したのは §2 の複製 pipeline と `build.sh` / `run.mjs` / `probe.mjs` のみ。

## 5. 製品 KPI (前後)

- 起動 dispatch 数: 両側 109 (基準 109 と一致)。前後の差は 0。
- 通過 unit 数: `units_run` 109 (両側)。
- 最初のウィンドウ: `probe.mjs` で `a4a620a9` 側のみ測定 (直後の build が `45ba1484e` だったため)。`TLightweightLayeredControl` = `0x1100012`、`TApplication` = `0x1100013` (いずれも非 0)。`a4a620a9^` 側の probe は未実行。
- `tools/flelift/boot` の 209 dispatch とは別の経路 (GUI shim 経路の値)。混同しない。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| GetMem 761 (`9bfcc26a3` の boot.json) と 760 (基準環境の現 pipeline・両側同値) の差の原因 | `boot.json` と judge B1 の基準値 (761) が現測定 (760) と一致しない。`heap.c` の差では説明できないことは確認済み | 本 PR 外。`m11_ov.c` (`22c914300`) の前後を基準環境で測る作業として次の run に回す |
| `a4a620a9^` 側の window probe (P4/P5 相当) 未測定 | KPI の「最初のウィンドウ」は `a4a620a9` 側のみ | 同上 (次の run で probe を両側で取る) |
