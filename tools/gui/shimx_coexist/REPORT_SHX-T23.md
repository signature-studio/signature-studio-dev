# REPORT — SHX-T23 (#1388): RegisterDragDrop 経路の guest 呼出し橋

本体 `REPORT.md` §6 の「RegisterDragDrop 経路」未達 (→ #1178 [SHX-T21]) の、guest 側呼出し橋の設計と実装。
検証起点: commit `fb563fbb` (`feat(shimx): SHX-T23 ...`、base `9877e3ad` = origin/main)。

## 1. 結論

- 設計: **lifttab トークン方式** (既存の R3 機構を流用)。guest→C は vtable スロットをトークンにして `__wrap_m11_icall` → `shimx_lifttab_trampoline` で C 実体へ落とす。C→guest は `shimx_cbtrans_get_invoke()` (= lift 側 `m11_icall`) で guest の VA を呼ぶ。
- 実装: `IDataObject` (QueryInterface / AddRef / Release / GetData / QueryGetData) を shimx に実装。`GetData` は CF_HDROP + HGLOBAL の STGMEDIUM で DROPFILES ブロックをコピーして返す。
- 結線: `gui_set_drop_target_invoker` ← `shimx_drop_invoke` (`gui_shimx_attach` の戻り bit2)。drop で `DragEnter` → `DragOver` → `Drop` を vtable 経由で呼ぶ。
- 検証範囲: node + mock (C 側の偽 guest)。**実 FL guest の vtable 呼出しの正しさは実機でのみ検証可能** (#177 [SHX-T9] と同じ制約。§4)。

## 2. 設計の選択肢と採否

| 案 | 内容 | 採否 |
|---|---|---|
| A. lifttab トークン (採用) | guest に渡す vtable スロットを `SHX_LIFTTAB_TOKEN_BASE+i` にする。guest の間接呼出しは `m11_icall` 経由でトークンを捕まえ、`shimx_lifttab_trampoline` が C 実体へ落とす | 既存の R3 (IL* / UI言語) と同じ経路。新しい呼出規約を増やさない |
| B. 新しい呼出規約ブリッジ | u64×8 以外の専用 thunk を新設 | 不要。`IDataObject` のメソッドは全て u64 引数に収まる |

- vtable の解決: guest の `IDropTarget` は `RegisterDragDrop` に渡された `LPVOID` (guest メモリ上の 8B スロット vtable)。`drop_invoke` は `*(u64*)target` で vtable を読み、各スロットの VA (`vt[3]`=DragEnter / `vt[4]`=DragOver / `vt[5]`=DragLeave / `vt[6]`=Drop) を `shimx_cbtrans_get_invoke()` で呼ぶ。
- メソッド番号: IDropTarget (`QueryInterface`=0, `AddRef`=1, `Release`=2, `DragEnter`=3, `DragOver`=4, `DragLeave`=5, `Drop`=6) は COM の固定順。
- wasm メモリ配置: `IDataObject` の vtable (`g_ido_vt[12]`) と `ShxDataObj` は shimx の C 側ヒープ・静的領域。guest からは lifttab トークン経由でしか呼ばれないので、guest の wasm メモリ範囲を指さない。`pdwEffect` と `pt` は guest の VA で渡す (`a4` / `a3`)。**ただし `pdwEffect` の書込み先アドレスは guest の wasm メモリ内 (u32)** であることを前提にしている。実 guest で VA→wasm アドレスの変換が要るかは未検証 (§4)。

## 3. 実装の要点

- `tools/shimx/src/ole.c`: `ShxDataObj` (vtable ポインタ + refs + HDROP)。`shimx_ido_*` は guest→C の受け口。`shimx_drop_invoke` は C→guest。`GetData` は `shimx_hdrop_bytes` (新設、shell.c) で DROPFILES 全体を取り、HGLOBAL にコピーして返す。`QueryGetData` / `GetData` は `CF_HDROP`・`DVASPECT_CONTENT`・`lindex=-1`・`TYMED_HGLOBAL` 以外を `DV_E_*` で拒否。
- `tools/shimx/src/cbtrans.c`: `SHX_LIFTTAB_N` 16→22。`IDataObject.*` 6 行を lifttab に追加 (dll=3 = 内部 COM。GetProcAddress からは引けないよう `lifttab_find` の dll 指定から外れる)。
- `tools/shimx/src/shell.c`: HDROP の大きさを記録 (`sz`)。`shimx_hdrop_bytes` を追加。
- `tools/gui/src/gui_core_ext.inc`: `shimx_drop_invoke` を weak 宣言し、`gui_shimx_attach` で `gui_set_drop_target_invoker` に結線 (bit2)。
- `tools/shimx/data/sigs.json` / `exports.txt`: `gen_sigs.py` の再生成 (追加 9 関数、削除 0)。

## 4. 検証 (全て実測。測定 commit `fb563fbb`)

| 検査 | 結果 |
|---|---|
| `bash tools/gui/shimx_coexist/coexist.sh` (node + mock) | rc=0 / **11.22 s** / load 1 分値 開始 0.93 → 終了 1.59 / link duplicate 0・warning 0・undefined 0 / C 側 **68 PASS / 0 FAIL** (うち新規 10 件) / host 側 **13 PASS / 0 FAIL** / NC1 duplicate 7 / NC2 C 側 fail 14 / **ALL PASS** |
| 新規 10 件 (`test_idt`) | RegisterDragDrop 済み窓への drop → IDropTarget が処理 (配送結果 2)・DragEnter/DragOver/Drop が 1 回ずつ・DragLeave は受理時に呼ばれない・pdwEffect が guest に書かれる・QueryGetData で CF_HDROP は S_OK / 他 cf は DV_E_FORMATETC・GetData の DROPFILES ブロック (pFiles=20, fWide=1)・HDROP 由来の 2 件のファイル名・RevokeDragDrop 後は配送 0 |
| `bash tools/shimx/test.sh --quick` | rc=0 / **37.18 s** / MT PASS (8 グループ) / ST PASS / fail-fast 9 モード exit 1 ✓ / M4 互換 PASS / sig_test ALL PASS |
| `bash tools/gui/e2e.sh` | rc=0 / **167.90 s** / load 1 分値 開始 1.24 → 終了 1.70 / bpp・text・nc・simd・present・input・stress 各 ALL PASS / **gui-e2e ALL PASS** |

注記:
- `tools/shimx/test.sh --quick` は生成物 (`BACKLOG.md` / `inventory.*` / `data/coverage.json` / `data/inventory.csv`) を OTT 素材無しの値で書き換える (REPORT §5 と同じ)。今回は commit 前に `git restore` で戻し、commit には含めていない。
- `gui/e2e.sh` は worktree に `node_modules` が無いと tsc 段で rc=127 になる。`pnpm install --frozen-lockfile` 後に通った。
- IR は `work-m11` が無いため `integ/fixtures/boot_final_gui_declares.ll` (fixture) を使用。REPORT §4 の `boot_final3.ll` (sha1 `4a4a5fa01e`) とは別物。

## 5. 差分 (測定 commit 以降のコード差分は 0)

測定 commit = `fb563fbb` (コードを変えた最後の commit)。以降に変えたのは本ファイル (REPORT) のみ。

```
git diff fb563fbb HEAD -- tools/gui tools/shimx/src   → 本 commit で REPORT_SHX-T23.md / REPORT.md の導線のみ (コード差分 0)
```

## 6. 未解決・範囲外 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FL guest での `IDropTarget` vtable 呼出し・`IDataObject` のトークン経由呼出し (`m11_icall` が実際にトークンを捕まえるか) | FL が OLE D&D を使う場合のファイルドロップの実機可否 | #177 [SHX-T9] にコメント (実機のみ検証可能) |
| `pdwEffect` / `pt` の guest VA → wasm アドレス変換の要否 | 実 guest で書込み先がずれると効果値が化ける | #177 [SHX-T9] |
| `m11` route での検証 (`work-m11` 素材) | fixture IR で検証。m11 IR 由来の adapter 構成では未確認 | #1388 の補足どおり、`work-m11` 展開後に `coexist.sh` を再実行 |
| `IDataObject` の残りのメソッド (`EnumFormatEtc` 等) は `E_NOTIMPL` | FL が使う場合は未対応 | 必要が出た時点で追加 (現時点で FL の実呼出は未確認) |
