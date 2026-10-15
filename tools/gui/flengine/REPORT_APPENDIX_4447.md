# REPORT 付録 — #4447 (LD-219): gui flengine e2e に FLEngine 起動の dispatch 件数を出す

自動生成ではない。親 #4093 (LD-193) で「gui flengine e2e は dispatch 件数を出さない」ため前後比較できなかった項目を埋める。

## 1. 取得方法と定義

- **定義**: dispatch 数 = 「dispatch した unit 数」。`tools/flelift/boot/fle_boot.mjs:256` の定義 (`units_run`) と同じ。
- **取得元**: `m11_ov.c` の `g_units_run` (`m11_units_run()`)。gui の wasm は `m11_build.sh` の EXPORTS で `_m11_units_run` を既に export しているため、ビルド変更は無し。
- **出力**: `tools/gui/flengine/run.mjs` の結果 JSON に `units_dispatched` を追加 (`units_run` と同値の別名。flelift の語彙に合わせる)。
- **却下した候補**: `m11_disp_count()` は `m11_disp_n` (間接呼出テーブルの件数 = 8621) を返すだけで dispatch 件数ではない。`disp_entries` と同じ値のため使わない。

## 2. 前後比較 (同一 HEAD・shim の heap.c だけ差し替え)

- 測定 commit: `9bfcc26a3` (`feat(gui): report units_dispatched`)。コード差分は `tools/gui/flengine/run.mjs` の 1 行だけ。
- `a4a620a9^` 側: 同 HEAD の `tools/shim/src/heap.c` を `git show a4a620a9^:tools/shim/src/heap.c` に差し替え、`build.sh` → `run.mjs` (通常起動)。
- `a4a620a9` 側: 差し替えなし (HEAD の heap.c)。e2e の boot 結果 `results/boot.json`。

| 項目 | `a4a620a9^` | `a4a620a9` (HEAD `9bfcc26a3`) |
|---|---|---|
| `units_dispatched` (dispatch 件数) | 109 | 109 |
| `units_run` | 109 | 109 |
| `init_count` | 111 | 111 |
| `dllmain_done` | true | true |
| `icall_miss` | 7 | 7 |
| GetMem / FreeMem | 760 / 24 | 760 / 24 |

- 差は 0 件。`a4a620a9` の heap.c 修正 (範囲外ポインタの拒否) は、通常起動の unit 進行 (dispatch 数) を変えない。
- 前回 `65844e9ef` の実測 (`REPORT_APPENDIX_LD136.md` §7) でも units_run 109・GetMem 760 だった。今回と一致する。

## 3. e2e 実測 (測定 commit `9bfcc26a3`)

- 実行: `bash tools/gui/flengine/e2e.sh` を foreground で 1 回。素材 `fl-win64` `toolchain-emsdk` `toolchain-retdec` `work-m11` を展開。`apt-mingw` 相当の `x86_64-w64-mingw32-gcc` は runner に存在。
- 所要 620 s。load 開始 0.23 / 終了 1.17。nproc 4。
- judge 14/15 (exit 1)。FAIL は B1 のみ。`units_run 109 (base 109)` `dllmain True` `GetMem 760 (base 761)` `FreeMem 24` `icall_miss 7`。前回 head (`65844e9ef`) と同じ FAIL 形。
- native selftest・pe_image parity・pe_image e2e・ネガコン N1〜N10 は期待どおり。
- `units_dispatched` は JSON 上で 109。

## 4. 製品 KPI (前後)

- 起動 dispatch 数: 前 109 / 後 109 (差 0)。
- 通過 unit 数: 前 109 / 後 109。
- 最初のウィンドウ: P4 `hwnd=0x1100013`・P5 `hwnd=0x1100012` (ともに PASS)。
- `tools/flelift/boot` の 209 dispatch とは別の経路 (GUI shim 経路の値)。混同しない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| B1 の GetMem 760 対 761 (1 件差) | e2e judge が 14/15 のまま | #4093 系の既存追跡 (本 PR の範囲外) |
