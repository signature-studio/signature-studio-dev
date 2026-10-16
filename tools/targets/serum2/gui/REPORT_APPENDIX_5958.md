# REPORT 付録 — SR-99 (#5958) slot `0x1817bf760` の runtime 観測

- 親: #5957 (SR-98)。前段: `REPORT_APPENDIX_5935.md` §2.1・§4 (slot 由来 5 箇所・PE 上 WRITE 0 件・READ 289 件)。
- 日付: 2026-10-16 / 測定 commit (コードを変えた最後の commit): `b32db38c6`。
- 入力: `Serum2_win64.vst3` (sha256 `501e7bb3…5283` / 19,236,864 B、`ref_content.sh` で展開し sha256 一致を確認)。`Serum2_win64.authstub.vst3` は `license/authstub/mpatch.py` で作成 (原 bytes 照合 6/6 OK)。
- 観測手段: `host/vst3host.cpp` (wine64 9.0 / mingw-w64 上の最小 VST3 host、SR-1 資産)。`S2HOST_SLOT=1` で DR0 に slot の 8 byte 書込 watch を張る (DR7 LEN=10b。slot は 8 byte の関数ポインタで、`0x17bf760` は 8 byte 境界)。`[slot]` 行は watch と同じ 8 byte (`long long`) で読む。`S2HOST_WATCH` の controller +0x10c watch は従来どおり 4 byte (LEN=11)。
- **測定の範囲**: §2 の表は測定 commit `b32db38c6` (watch 8 byte・DR7 LEN=10b) の値。修正前の `71c51d3d5` (4 byte watch) の値は残していない。
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

- seed 行の実測 (`S2HOST_SLOT=1` 付き・無改変 DLL・state なし・4 block。測定 commit `b32db38c6`、測定時の HEAD `4554feee6` は host コード差分 0): `[slot] 0x1817bf760 before createView = 0` / `after createView = 0` / `before process = 0`、`[watch] hit` 0 件、`[audio] blocks=4 frames=512 nonzero_cells=1020/1024 peak=0.548306`。コマンド: `S2HOST_SLOT=1 wine64 work/build/vst3host.exe 'Z:…\work\Serum2_win64.vst3' - 'Z:…\host\work\out_seed_slot' 4 'Z:…\work\content_full'` (`Z:…` はリポジトリ絶対パス。`WINEPREFIX=work/wineprefix WINEDEBUG=-all`)。
- 書込 watch は 8 byte 幅 (`0x17bf760`〜`+7`、DR7 LEN=10b) の結果。
- 再実行の手順: `ref_content.sh` (素材 `plugins-serum2`) → `build.sh` → `mpatch.py` (authstub、原 bytes 6/6 OK) → `synth_state.py` → seed run (`S2HOST_SLOT=1`・`-`・4 block) → `make_cases.py work/state work/out_seed work/cases` → licensed・demo (`S2HOST_SLOT=1`・64 block)。
- 3 条件とも process は完走 (licensed: `blocks=64 frames=8192 nonzero_cells=16380/16384 peak=0.691102`、demo: 同値)。
- demo と licensed が同値になることの扱い: demo と licensed は同じ authstub DLL・同じ 64 block・同じ host 経路で、差は state (`cases/demo` / `cases/licensed`) のみ。出力が 6 桁まで一致したことは、この 16384 cell の集計では state の差が音に現れていないことを示すが、「同一音声」の証明ではない。ログは host の `<out>/log.txt` (`gLogFile`) に出力され、`<out>` は実行時の出力先 (`work/` 配下・gitignore)。本 REPORT には行を残していない。
- slot は 3 条件・全段階で 0 のまま。書込 watch は 0 件。

## 2b. GUI 経路の観測 (S2HOST_ATTACH / S2HOST_CLICKS)

`host/vst3host.cpp` に opt-in を追加 (既定経路は無変更)。

- `S2HOST_ATTACH=1`: `createView('editor')` で取った view に対し、不可視の親 HWND を作って `isPlatformTypeSupported(kPlatformTypeHWND)` と `attached` を呼ぶ。`attached` 後・30 回の message pump 後に slot を読み、`removed` で閉じる。
- `S2HOST_CLICKS=1` (`S2HOST_ATTACH` 併用): 親の client 領域を 64px 格子 (15×15 = 225 点) で `WM_LBUTTONDOWN`/`UP` を送り、点ごとに slot が 0 以外になったら出す。

実測 (無改変 DLL・既定 state・4 block・`xvfb-run -a`・wine64 9.0。測定 commit `6fc5b4cc7` (HEAD で再現・7 秒・load 0.21)。`git diff 42fad4a17 6fc5b4cc7 -- tools/targets/serum2/host` は本節の opt-in 差分のみ):

| 条件 | slot (createView 後 / attached 後 / pump 後 / 格子クリック後 / process 前) | 書込 watch hit | 子ウィンドウ数 (attached 後) |
|---|---|---|---|
| attach + 格子 225 点 (`S2HOST_ATTACH=1 S2HOST_CLICKS=1`) | 0 / 0 / 0 / 0 / 0 | 0 件 | 1 |

- attach のみ (格子なし) の行は、測定 commit のログで再取得していないため削除した (素材 `plugins-serum2` が無く、測定 commit 由来の値を示せない)。
- `attached` は `kResultTrue`。子ウィンドウ 1 件が生成されており、editor は実際に開いている。
- 格子クリックは 225 回すべて送信。非 0 になった点は無し。
- 完走: `blocks=4 frames=512 nonzero_cells=1020/1024 peak=0.548306` (§2 の seed と同値)。

## 3. 判定と未達

- 観測の範囲: §2 の 3 条件 (GUI 非操作) と §2b の 2 条件 (editor を attach し格子クリック) で、slot `0x1817bf760` は**全て 0・書込 0 件**。
- 未達: 格子クリックは XferOnOffButton の座標を特定していない (掃引)。ボタンの位置を指定した操作は未実施。したがって「XferOnOffButton 操作で slot が書かれない」の確定は、ボタンを狙った操作の観測が要る。
- 受入の「slot 由来 5 箇所の呼出し先の確定」は未達。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| GUI (editor open・XferOnOffButton 操作) 経路での slot 観測 | slot 由来 5 箇所の確定 | #5958 (本 issue の残件・Refs のまま open) |
| `0x1809ca77c` の CFG 経由 vtable 呼出し先 | 閉包 1 箇所 | #5934 (SR-96) の結果待ち |

## 5. 再測定の前提

- 8 byte 幅 watch の build は `host/build.sh` で通ること (本 commit で確認。`x86_64-w64-mingw32-g++`)。
- 3 条件の再実行には素材 `plugins-serum2` (`Install_Xfer_Serum2_2.1.5.exe` 入り) が要る。`fl-win64` には Serum の DLL が無い (`tar --zstd -tf fl-win64.tar.zst` で確認)。§2 の再実行手順はこの素材で完了済み。
- 実行依存: `wine64` (apt `wine64`)・`g++-mingw-w64-x86-64` (apt)・`7z`。
