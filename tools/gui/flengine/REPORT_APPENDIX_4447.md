# REPORT 付録 — #4447 (LD-219): gui flengine e2e に FLEngine 起動の dispatch 件数を出す

自動生成ではない。親 #4093 (LD-193) で「gui flengine e2e は dispatch 件数を出さない」ため前後比較できなかった項目を埋める。

## 1. 取得方法と定義

- **定義**: dispatch 数 = 「dispatch した unit 数」。`tools/flelift/boot/fle_boot.mjs:256` の定義 (`units_run`) と同じ。
- **取得元**: `m11_ov.c` の `g_units_run` (`m11_units_run()`)。gui の wasm は `m11_build.sh` の EXPORTS で `_m11_units_run` を既に export しているため、ビルド変更は無し。
- **出力**: `tools/gui/flengine/run.mjs` の結果 JSON に `units_dispatched` を追加 (`units_run` と同値の別名。flelift の語彙に合わせる)。測定 commit `9bfcc26a3`。
- **却下した候補**: `m11_disp_count()` は `m11_disp_n` (間接呼出テーブルの件数 = 8621) を返すだけで dispatch 件数ではない。`disp_entries` と同じ値のため使わない。

## 2. 前後比較 (受入 2)

**状態: 再測定は実施したが、基準環境を再現できていない。以下の値は同一環境内の前後比較であり、REPORT の基準値 (units_run 109) とは対応しない。**

測定条件 (本 run、runner の素材で実施):

- 素材: `$ARTIFACTS_DIR` の `work-m11.tar.zst` (→ `tools/m11/work/`)・`toolchain-emsdk.tar.zst` (→ `/tmp/opencode/tc/emsdk`)・`toolchain-retdec.tar.zst` (→ `/tmp/opencode/tc/retdec`)。
- **未入手**: `fl-win64` (`block00031_PE.bin`) が runner に無い。`find /` でも見つからず。そのため import thunk 表は空 (`build.sh` の WARNING 経路)。`boot_final.ll` からの `m11_gen_ir2.sh` / `m11_wndseed.sh` も本 run では回していない (素材の `work/boot_final*.ll` をそのまま使用)。
- HEAD: `d922d6fac` (コード差分は `run.mjs` 0。`git diff 9bfcc26a3 d922d6fac -- tools/gui/flengine/run.mjs tools/shim tools/m11` は空)。
- 差し替え: `tools/shim/src/heap.c` のみ。`git rev-parse` で blob を確認: `a4a620a9^` = `cde475fbc`、`a4a620a9` = `45ba1484e`、HEAD = `01bfe4b01`。
- 手順: 各側で `EMSDK_ENV=<emsdk_env.sh> PATH=<retdec/bin>:$PATH bash tools/gui/flengine/build.sh` → `node tools/gui/flengine/run.mjs --out <json>`。

結果 (同一 HEAD `d922d6fac`・同一 IR・PE 無し):

| 項目 | `a4a620a9^` (heap.c `cde475fbc`) | `a4a620a9` (heap.c `45ba1484e`) |
|---|---|---|
| build | rc 0 | rc 0 |
| run | rc 0 (11 s 込みの build+run ≒ 11 s) | rc 0 (同 11 s) |
| `boot_threw` | memory access out of bounds | memory access out of bounds |
| `units_dispatched` | 17 | 17 |
| `units_run` | 17 | 17 |
| `init_count` | 18 | 18 |
| `icall_miss` | 0 | 0 |
| GetMem / FreeMem | 16 / 6 | 16 / 6 |
| FastMM_GetMem(407a50) | 17 | 17 |

- 判定: 両側で `units_dispatched` 17 = 17 (差 0)。ただし両側とも boot が trap で止まるため、この前後比較は「PE 無し・IR 未再生成の環境での差 0」しか示さない。基準 (109) は再現していない。
- 旧表 (参考。受入根拠ではない): 旧 round 1 の表は `cde475fbc` と HEAD (`01bfe4b01`) の比較で、`a4a620a9` 側の heap.c が違っていた。今回は破棄。

## 3. boot.json の GetMem / FastMM の変化 (`22c914300`)

- `results/boot.json` の差分 (`9bfcc26a3` → `65844e9ef` 由来の値): `GetMem 761→760`・`FastMM_GetMem(407a50) 782→781`。
- 本 run の対応: **この変化は本 PR から戻した** (`results/boot.json` は `units_dispatched` 行の追加だけ)。
- 測定: `22c914300^` / `22c914300` の `tools/m11/m11_ov.c` を入れ替えて同一 HEAD で build → run (同じ PE 無し環境)。結果は両側とも `GetMem 16` / `FastMM_GetMem 17` で、差は 0。boot は両側とも trap で止まるため、この測定では基準の 761/782 → 760/781 の 1 件差を再現・否定できない。
- 結論: 原因は未確定。`22c914300` は候補だが、この環境では GetMem を動かさなかった。`function_40d210` 転記 (memset の n > 32 本体) が GetMem を 1 件減らすという根拠は本 run では得られていない。
- 再測定の条件: `fl-win64` (`block00031_PE.bin`) と `m11_gen_ir2.sh` / `m11_wndseed.sh` を含む完全な e2e 環境。これが揃うまで GetMem の原因は未測定のまま。

## 4. e2e 実測

- 測定 commit `9bfcc26a3` の e2e (`bash tools/gui/flengine/e2e.sh`) の記録: 所要 620 s、judge 14/15 (FAIL は B1 のみ: `GetMem 760 (base 761)`)。この run の commit 対応は、この head では再実行していないため記録のみ。
- 本 head (`d922d6fac`) では e2e 全体は未実行 (`fl-win64` 無し)。`build.sh` と `run.mjs` のみ §2・§3 の条件で実行。

## 5. 製品 KPI (前後)

- 起動 dispatch 数: 本 run の値は §2 の環境 (PE 無し・boot trap) のもので、基準 (109) の KPI とは別物。前後は 17 / 17 (差 0)。
- 通過 unit 数: 同上 (17 / 17)。
- 最初のウィンドウ: 本 run では未確認 (boot が trap で止まるため P4/P5 の probe は未実施)。前回 run の記録は `P4 hwnd=0x1100013`・`P5 hwnd=0x1100012` (測定 commit `9bfcc26a3` の run、本 head では未再実行)。
- `tools/flelift/boot` の 209 dispatch とは別の経路 (GUI shim 経路の値)。混同しない。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 基準環境 (`fl-win64` の PE・`m11_gen_ir2.sh`・`m11_wndseed.sh`) での前後比較。本 run は boot が trap で止まり、基準 109 を再現していない | 受入 2 の「前後比較」は同一環境で差 0 を示したのみ。基準値での前後は未確定 | 本 PR で追跡 (`oc_artifacts:` に `fl-win64` を足して再起動) |
| GetMem 761→760 の原因 (`22c914300` が候補) | 本 PR では `boot.json` の変化を戻した。候補の真偽は未確定 | 上と同じ基準環境での測定 |
