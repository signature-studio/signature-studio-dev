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

## 2c. XferOnOffButton 座標の指定 (S2HOST_CLICK_AT・未達)

- 座標の出所: `work/uidesc.json` (`gui/extract_uidesc.py`・素材 `plugins-serum2` の DLL 由来。XferOnOffButton の定義は 43 件)。MainUI (1190×740) 配下を origin で積算できたのは 1 件のみ (`Header/CViewContainer/XferOnOffButton` = MainUI 基準 `985,1`・51×33、control-tag `UI::MainUI::kUIParamShowPresetBrowser`)。他のボタンは template 参照の積算が未完で、座標を確定していない。
- 観測手段: `S2HOST_CLICK_AT="x,y;…"` (opt-in) で指定点に `WM_LBUTTONDOWN/UP` を送り、点ごとに slot を読む。`S2HOST_SHOW=1` で親を表示。`attached` の前に `getSize` の寸法へ親を合わせる。
- 実測 (`S2HOST_ATTACH=1 S2HOST_CLICK_AT="1010,17"`・無改変 DLL・既定 state・4 block・`xvfb-run`・wine64 9.0。測定 commit は本節の commit):
  - `getSize` = 1190×740、`attached` = kResultTrue、子ウィンドウ 1 件 (VSTGUI のフレーム `VSTGUI00006…`)。
  - **子フレームの矩形は (0,0)-(0,0) のまま**、その下に孫ウィンドウは 0 件。親を `getSize` の寸法に合わせ `S2HOST_SHOW=1` で表示した run でも同じ (寸法合わせだけの run は測っていない)。
  - よって、クリックは VSTGUI の部品に届いていない (送信先はフレーム自身)。1 点 (1010,17) の slot は 0。
- 判定: この経路では XferOnOffButton の操作が成立しない。slot 0x1817bf760 の値は本節では確定していない。
- 次の一手 (未着手): VSTGUI フレームを実寸にする経路の特定 (`IPlugFrame` の `resizeView` 呼出しの有無、`onSize` の発火条件)。これが無いと、ボタン座標が正しくても操作は届かない。

## 2d. IPlugFrame を渡す経路 (S2HOST_FRAME・#5958 残件の原因切り分け)

- 原因の仮説: 従来の host は `view->setFrame()` を呼ばず、editor に `resizeView` / `onSize` が届かなかった。子フレームが `(0,0)-(0,0)` のままだったのはこれが理由と考えた。
- 変更: `host/vst3host.cpp` に `PlugFrame` (IPlugFrame 実装) を追加。`S2HOST_FRAME=1` のときだけ `attached` の前に `setFrame` を呼ぶ (既定経路は無変更)。commit `85f152ad6`。
- 実測 (無改変 DLL・既定 state・4 block・`xvfb-run -a`・wine64 9.0。測定 commit `85f152ad6`。ベースラインは同じ commit の `S2HOST_FRAME` 無し):

| 条件 | 子フレーム矩形 | 子フレーム可視 | slot (createView 後 / attached 後 / pump 後 / クリック後 / process 前) | 孫ウィンドウ |
|---|---|---|---|---|
| ベースライン (`S2HOST_ATTACH=1 S2HOST_CLICK_AT=1010,17`) | (0,0)-(0,0) | 0 | 0 / 0 / 0 / 0 / 0 | 0 |
| `S2HOST_FRAME=1` (`S2HOST_SHOW=1`・`CLICK_AT=1010,17`) | (0,0)-(1190,740) | 1 | 0 / 0 / 0 / 0 / 0 | 0 |
| `S2HOST_FRAME=1` (`S2HOST_SHOW=1`・`S2HOST_CLICKS=1` 格子 225 点) | (0,0)-(1190,740) | 1 | 0 / 0 / 0 / 0 (`slot_final=0`) / 0 | 0 |

- `setFrame` = kResultTrue、`resizeView (0,0)-(1190,740)` を受け `onSize` = kResultTrue。`resizeView` で親を実寸にした。
- 完走: `blocks=4 frames=512 nonzero_cells=1020/1024 peak=0.548306` (3 条件とも同値)。
- 格子 225 点・`(1010,17)`・`(985,10)` のいずれでも slot は 0。子フレームに孫ウィンドウは生成されず、クリックを受けた部品は確認できなかった (VSTGUI は HWND の子として部品を持たない)。
- 判定: `setFrame` を渡すとフレームは実寸・表示になるが、XferOnOffButton の操作は成立していない。slot 0x1817bf760 の値は本節でも確定していない。

## 2e. slot 参照関数の実行 breakpoint (S2HOST_BP・クリック注入なし)

- 目的: クリック注入 (§2b〜§2d) をやめ、slot を参照する関数そのものに実行 breakpoint を張って、呼出しの有無を見る (PM 判断の提案 1)。
- 変更: `host/vst3host.cpp` に `S2HOST_BP="rva,…"` (最大 4 件) を追加。DR0〜DR3 の execute 比較で関数先頭に張り、hit ごとに関数 RVA・戻り先・slot 値を出す。`S2HOST_SLOT`・`S2HOST_WATCH` と同時指定すると起動時に拒否する (DR レジスタを共用するため)。既定経路は無変更。
- 対象 RVA: `0x136bf0`・`0x138180` (slot 由来 call を持つ関数)・`0x142540` (slot 由来として並べる候補。`REPORT_APPENDIX_5935.md` §2 で「本 run で再確認していない」と注記された関数)・`0x622840` (XferOnOffButton の own vtable の候補 slot 0)。
- 測定 commit: `d1e3cab19` (HEAD で再現)。コマンド: `S2HOST_ATTACH=1 S2HOST_BP="136bf0,138180,142540,622840" xvfb-run -a wine64 vst3host.exe …`。無改変 DLL・既定 state・4 block・wine64 9.0・load 0.45。
- 測定範囲: DR レジスタはスレッド単位で、本 run の bp は attach 時の main thread だけに効く。他スレッドでの呼出しは見えていない。

| 関数 | hit 件数 | slot 値 (hit 時) |
|---|---|---|
| `0x138180` | 5 | 0 (全 hit) |
| `0x136bf0` | 9 | 0 (全 hit) |
| `0x142540` | 0 | — |
| `0x622840` | 0 | — |

- slot 値は全 hit で 0。`before process` も 0。完走 `blocks=4 frames=512 nonzero_cells=1020/1024 peak=0.548306`。
- 解釈 (入口の観測まで): 入口で slot=0 を観測した。`0x622840` は本 run では hit 0 (呼ばれなかった)。`0x136bf0` / `0x138180` は入口 hit あり・slot 由来 call の実行は未確定。slot 由来 call の直前には `test r10,r10; je` (§5935 の表) があるが、call 命令位置での slot 値は測っていないため、slot=0 で call が飛ばされたとは言えない。`0x142540` は hit 0 で、slot 由来かどうかも本 run では判定できない。
- 未確定の残件: call 命令位置への bp、または call 直前の slot 読みで、slot 由来 call の実行の有無を測る必要がある。
- 限界: 1 条件 (クリックなし・attach のみ) での観測。XferOnOffButton の操作 (クリック) を伴う条件では未測定。

## 2f. slot 由来 call 命令への bp (S2HOST_BPCALL)

- 目的: §2e の残件。slot 由来 call 命令の位置で実行の有無を見る。
- 変更: `host/vst3host.cpp` に `S2HOST_BPCALL="rva,…"` (最大 4 件・armBp と同じ DR 配列) を追加。`[bp]` 行に rax・r10 を追加。`S2HOST_BP`・`S2HOST_BPCALL`・`S2HOST_SLOT`・`S2HOST_WATCH` の同時指定は起動時に拒否する。
- 対象 RVA (逆アセンブルで確定。`call` 命令の先頭): `0x136ca7` (`call r10`)・`0x136ce8` (`call r10`)・`0x136d1d` (`call rax`)・`0x1381d8` (`call rax`)。各命令の直前は `mov reg,[0x17bf760]`・`test`・`je` (null チェック)。
- 測定: 無改変 DLL・既定 state・4 block・`S2HOST_ATTACH=1 S2HOST_BPCALL="136ca7,136ce8,136d1d,1381d8"`・xvfb-run・`/usr/lib/wine/wine64` (wine 9.0)。
  - 結果: `[bp] armed 4 execute breakpoints`。call 命令 4 箇所の hit は **0 件**。完走 `blocks=4 frames=512 nonzero_cells=1020/1024 peak=0.548306`。
- 対照 (同じ DLL・同じ run 条件): `S2HOST_BP="136bf0"` (関数入口) は 9 件 hit。hit 時の slot は全て 0 (rax・r10 も slot 由来でない値)。よって bp 機構は動いている。
- 解釈: slot=0 のとき `test; je` で call を飛ばす。入口 9 件はすべて slot=0 で、slot≠0 の hit は 0 件。call 命令 bp が 0 件なのは、この条件では slot 由来の call が**実行されていない**ことと整合する。ただし `je` の分岐先を直接見ていないため、「飛ばされた」の直接確認ではない。
- 残件: `je` 分岐先 (`0x136cae`・`0x136cef`・`0x1381ef` 等) への bp で「null で飛ばされた」を直接確定する。XferOnOffButton の操作を伴う条件は未測定。

## 3. 判定と未達

- 観測の範囲: §2 の 3 条件 (GUI 非操作) と §2b の 2 条件 (editor を attach し格子クリック) で、slot `0x1817bf760` は**全て 0・書込 0 件**。
- 未達: 格子クリックは XferOnOffButton の座標を特定していない (掃引)。§2d で `setFrame` により子フレームは実寸になったが、VSTGUI の部品へのクリックは届いていない。したがって「XferOnOffButton 操作で slot が書かれない」の確定は、部品のヒットテスト経路 (VSTGUI のマウス処理) を確定してから観測する要る。
- 受入の「slot 由来 5 箇所の呼出し先の確定」は未達。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| GUI (editor open・XferOnOffButton 操作) 経路での slot 観測 | slot 由来 5 箇所の確定 | #5958 (本 issue の残件・Refs のまま open) |
| slot 由来 call 命令の位置での slot 値・call 命令への bp (§2e) | `0x136bf0`・`0x138180` の slot 由来 call の実行の有無 | #5958 (同上) |
| `0x1809ca77c` の CFG 経由 vtable 呼出し先 | 閉包 1 箇所 | #5934 (SR-96) の結果待ち |

## 5. 再測定の前提

- 8 byte 幅 watch の build は `host/build.sh` で通ること (本 commit で確認。`x86_64-w64-mingw32-g++`)。
- 3 条件の再実行には素材 `plugins-serum2` (`Install_Xfer_Serum2_2.1.5.exe` 入り) が要る。`fl-win64` には Serum の DLL が無い (`tar --zstd -tf fl-win64.tar.zst` で確認)。§2 の再実行手順はこの素材で完了済み。
- 実行依存: `wine64` (apt `wine64`)・`g++-mingw-w64-x86-64` (apt)・`7z`。
