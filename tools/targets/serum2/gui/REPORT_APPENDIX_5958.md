# REPORT 付録 — SR-99 (#5958) slot `0x1817bf760` の runtime 観測

- 親: #5957 (SR-98)。前段: `REPORT_APPENDIX_5935.md` §2.1・§4 (slot 由来 5 箇所・PE 上 WRITE 0 件・READ 289 件)。
- 日付: 2026-10-16 / 測定 commit (コードを変えた最後の commit): `71c51d3d5`。
- 入力: `Serum2_win64.vst3` (sha256 `501e7bb3…5283` / 19,236,864 B、`ref_content.sh` で展開し sha256 一致を確認)。`Serum2_win64.authstub.vst3` は `license/authstub/mpatch.py` で作成 (原 bytes 照合 6/6 OK)。
- 観測手段: `host/vst3host.cpp` (wine64 9.0 / mingw-w64 上の最小 VST3 host、SR-1 資産)。`S2HOST_SLOT=1` で DR0 に slot の 4 byte 書込 watch を張る (`S2HOST_WATCH` と同じ仕組み)。`[slot]` 行で createView 前後・process 前の値を記録する。
- 環境: Ubuntu runner, 4 core, wine 9.0 (`apt install wine64`, `/usr/lib/wine/wine64`)。

## 1. 陽性対照 (watch が効くこと)

`S2HOST_WATCH=1` (既存の controller +0x10c 書込 watch) を licensed・4 block で実行。

- `[watch] hit#1 RIP=… value=2` が 1 件出た (実測)。DR0 による書込 watch は wine 上で機能する。

## 2. slot の観測 (3 条件)

| 条件 | DLL | state | 処理 | slot 値 (createView 前 / 後 / process 前) | 書込 watch hit |
|---|---|---|---|---|---|
| seed (既定) | 無改変 | なし (既定) | createView のみ・4 block | 0 / 0 / 0 | 0 件 |
| licensed | authstub | `cases/licensed` | createView のみ・64 block | 0 / 0 / 0 | 0 件 |
| demo | authstub | `cases/demo` | createView のみ・64 block | 0 / 0 / 0 | 0 件 |

- 3 条件とも process は完走 (licensed: `blocks=64 nonzero_cells=16380/16384 peak=0.691102`、demo: 同値)。
- slot は 3 条件・全段階で 0 のまま。書込 watch は 0 件。

## 3. 判定と未達

- 観測の範囲: **GUI を開かず** (`IPlugView::attached` を呼ばず)、`createView` と process のみ。slot 由来 5 箇所 (`0x180136bf0` 3 箇所・`0x180138180`・`0x180142540`) の呼出し経路は、XferOnOffButton 操作 (= editor open + 入力) で通る可能性があり、本観測には入っていない。
- したがって「slot は runtime でも 0 」は、**GUI 非操作の 3 条件では確認できた**が、受入の「slot 由来 5 箇所の呼出し先の確定」は未達。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| GUI (editor open・XferOnOffButton 操作) 経路での slot 観測 | slot 由来 5 箇所の確定 | #5957 (既存の子) |
| `0x1809ca77c` の CFG 経由 vtable 呼出し先 | 閉包 1 箇所 | #5934 (SR-96) の結果待ち |
