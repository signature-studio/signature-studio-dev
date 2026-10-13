# REPORT — shimx × gui 共存と Web 実装接続 (#172 [SHX-T5])

検証起点: コミット済み HEAD `96f95dc` (base `64e617f`)。クリーンな detached worktree で `coexist.sh` を実行して取得 (§4)。
既知類型との関係: `docs/DEFECTS.md` 該当なし (lift の silent miscompile ではなくリンク境界の問題)。ただし §2 の「gui の fail-fast stub が shimx の機能実装を黙って上書きする」は境界リスクとして記録する。

## 1. 結論 (先出し)

- **weak/強定義の重複警告 0**: m11 の `boot_final3.ll` (GUI declare 177 名) から生成した adapter 付き gui 全 obj と shimx 全 obj を `-Wl,--fatal-warnings` で同一 wasm にリンクして duplicate symbol **0** / warning **0** / undefined symbol **0**。
  修正前は `WTSRegisterSessionNotification` が gui adapter と shimx の両方で強定義され duplicate symbol になっていた (旧 `tools/startup/winstubs` の `coexist_gui.sh` が既知記録していた 1 件の正体)。shimx 側を weak 化し gui に強定義を足して解消した。
- **gui の強定義が shimx の weak 実装を下回らない**: IR が宣言する 5 本の `Char*` と `MsgWaitForMultipleObjects` は実行時に gui adapter 経由 (到達計数) で動く。`MsgWaitForMultipleObjects[Ex]` は kernel handle 待ち + メッセージ待ちを 1 本の futex で実装した (shimx の weak は「メッセージが来ない」ため UI を止める)。
- **Web 実装接続**: ShellExecute→`window.open`、GetOpenFileNameW/GetSaveFileNameW→File System Access、Drag&Drop→`WM_DROPFILES` (HDROP) を、同期 host 呼出路 `gui_hostcall` (main thread 専用 API を wasm の GUI スレッドから同期で呼ぶ) で実装。node 上で wasm を実行し mock の window / picker で検証した (C 側 58 項目 + host 側 13 項目すべて PASS)。
- **未達 (受入条件の「動く」は node+mock まで)**: 実ブラウザ (Chrome) での File System Access / `window.open` の実機 e2e、`IDropTarget` 経路の guest COM 呼出、save の反映契機の結線は未実施。§6 に起票先付きで記す。よって `Closes` ではなく `Refs`。

## 2. 境界表 — shimx の weak と gui の強定義

shimx の `SHIMX_WEAK` 定義 39 本 (`llvm-nm -g --defined-only` で W の本数)。うち gui が公開名を強定義するのは 7 本。公開名は `integ/gen_adapt.py` が **IR の declare** から生成する adapter (`gui_adapt_w32.o`) だけが出す。

| 名前 | gui 側 (修正前 → 後) | IR 宣言 | リンク後に勝つ定義 |
|---|---|---|---|
| CharUpperW / CharUpperBuffW / CharLowerBuffW / CharNextW | IMPL → IMPL | あり | gui adapter |
| CharLowerW | **STUB(fail-fast) → IMPL** | あり | gui adapter |
| MsgWaitForMultipleObjects | IMPL (nCount==0 のみ) → IMPL (kernel handle 対応) | あり | gui adapter |
| MsgWaitForMultipleObjectsEx | IMPL (nCount==0 のみ) → IMPL (kernel handle 対応) | なし | shimx weak (shimx の Ex は `MsgWaitForMultipleObjects` へ委譲するので、その先は gui adapter) |
| CharNextExA / CharToOemBuffW | **STUB → IMPL** | なし | shimx weak |
| WTSRegisterSessionNotification | STUB と shimx 強で**重複** → IMPL (shimx を weak 化) | あり | gui adapter |
| WTSUnRegisterSessionNotification | STUB と shimx 強 (IR 宣言なしで顕在化せず) → IMPL (shimx を weak 化) | なし | shimx weak |

- `CharLowerW` は IR が宣言しているのに gui 側が fail-fast stub で、adapter が公開名を強定義するため、リンクすると shimx の動く weak 実装を**黙って fail-fast で上書き**していた (修正前 `IMPORTS.md` で STUB、fixture に declare あり)。今回 IMPL 化した。
- adapter が出さない 3 本 (`CharNextExA` / `CharToOemBuffW` / `MsgWaitForMultipleObjectsEx`) は、将来 IR が declare した時点で adapter が強定義を出す。そのとき gui 側が stub のままだと同じ上書きが起きるため、gui 側を先に IMPL にしてある。
- `CharToOemBuffW` の OEM 変換表は shimx の `WideCharToMultiByte(CP_OEMCP)` を弱参照で借りる (shimx の OEM は Latin-1 近似: é=0xE9、α/CJK は `?`)。shimx 無しの単体ビルドは ASCII のみ。

## 3. 設計

### 3.1 MsgWaitForMultipleObjects[Ex] (`src/gui_core.c`)
`WaitForMultipleObjects` (shimx) を弱参照し、`WaitForMultipleObjects(n, hs, all, 0)` で handle を非ブロッキング確認 → メッセージを peek → どちらも無ければ `doorbell` で futex 待ち。
kernel object の状態変化は shimx の `shx_notify()` から `shimx_set_notify_hook` (新設) 経由で `gui_doorbell()` を鳴らすため 1 本の futex で両方を待てる (`gui_shimx_attach()` が接続)。hook 未接続で n>0 のときは 5 ms 刻みの poll に縮退。
戻り値: `WAIT_OBJECT_0+i` (低 index 優先) / `WAIT_OBJECT_0+n` (メッセージ) / `WAIT_TIMEOUT` / `WAIT_FAILED`。`MWMO_WAITALL` は「入力あり かつ 全 object signaled」(入力を先に確認し、handle の取得だけが先走らない)。
shimx 未リンクで n>0 は従来どおり fail-fast。メッセージ到着は #103 ST-T6 の message-pump と同じ `doorbell` (契約は不変)。

### 3.2 host 呼出路 `gui_hostcall` (`include/gui_hostcall.h` ↔ `src/runtime/gui_hostcall.ts`)
`GuiShared` (`gui_proto.h`) とは独立の静的 1 領域 (6,208 B)。wasm が `req_seq++` して `resp_seq==req_seq` まで futex 待ち、host は `Atomics.waitAsync(req_seq)` で起床して処理し `resp_seq` を書く。
GuiShared のレイアウトを変えないので GUI-4 (#180, PR #491) と衝突しない。host 未接続 (`host_ready==0`) は待たずに失敗を返す (ダイアログは FALSE + `CommDlgExtendedError`=2)。

### 3.3 ShellExecute → window.open
`shimx_set_shell_execute_hook` に接続。許可は verb が空/`open`、かつ `http:` / `https:` / `mailto:` のみ (C 側と host 側の二重検査)。`javascript:` / `file:` / ローカル exe / `print` は拒否 (ShellExecute は SE_ERR≤32 を返す)。ポップアップブロックで開けなければ失敗。
旧式の `ShellExecute("iexplore", url)` 形 (URL が params) も拾う。

### 3.4 GetOpenFileNameW / GetSaveFileNameW → File System Access
Win64 `OPENFILENAMEW` (NT4 版 136 B / 2000 版 152 B) を解釈し、title / 初期ディレクトリ / defExt / フィルタ (`WAV (*.wav)\0*.wav\0…` → `types`) / `OFN_ALLOWMULTISELECT` を host へ渡す。
選択ファイルは host が Emscripten FS の**ステージング** `C:\Users\webstudio\Documents\WebImport` (= POSIX `/c/Users/webstudio/Documents/WebImport`、`shimx_path_to_posix` で算出) へ書き出し、FL へは Win パスで返す (単一=フルパス、複数=`dir\0name\0…\0\0`、`nFileOffset`/`nFileExtension`/`lpstrFileTitle` 設定、バッファ不足は先頭 WORD に必要数 + `FNERR_BUFFERTOOSMALL`)。
save は FL が書き終えた POSIX ファイルを `HostCallBridge.flushSaves()` が選択済み handle へ反映する (反映契機の自動結線は未実装 → §6)。

### 3.5 Drag&Drop
shimx に実体を追加: `DragAcceptFiles` (受付窓表) / `DragQueryFileW` / `DragQueryPoint` / `DragFinish` / HDROP (`DROPFILES` ブロック) 生成 `shimx_hdrop_create`。
host (`deliverDrop` / `installDropTarget`) が DataTransfer のファイルをステージングへ書き出して `gui_drop_files()` を呼ぶ。ウィンドウ木は GUI スレッド専有なので、`gui_drop_files` は要求を積んで doorbell を鳴らすだけで、hit test・HDROP 生成・`WM_DROPFILES` 投函は GUI スレッドの `pump_drops` (`try_get` 入口) が行う。
受け手は「ポインタ下の窓から親へ辿って最初の `DragAcceptFiles` 済みの窓」。`RegisterDragDrop` 済み (`shimx_get_drop_target`) の窓には `gui_set_drop_target_invoker` の口を用意した (実体は §6)。

## 4. 検証 (全て実測。`bash tools/gui/shimx_coexist/coexist.sh`)

環境: ubuntu-24.04 runner、emcc 6.0.12、node v22.23.3、並列数 1。IR = `tools/m11/work/boot_final3.ll` (sha1 先頭 10 桁 `4a4a5fa01e`、`work-m11` 素材)。

| 検査 | 結果 |
|---|---|
| クリーン detached worktree (HEAD `96f95dc`) で `coexist.sh` 3 回 | 全て ALL PASS。所要 **12.03 / 12.07 / 12.09 s** (load average 1 分値 0.54–0.63) |
| リンク (`--fatal-warnings`) | duplicate symbol **0** / warning **0** / undefined symbol **0** |
| shimx 強 × gui 定義の重複 (llvm-nm 突合) | **0** 本 (修正前は `WTSRegisterSessionNotification` 1 本) |
| wasm 側 C 検査 (Char* 全種・MsgWait・ShellExecute・ダイアログ・Drop・shimx Drag*) | **58 PASS / 0 FAIL** |
| node 側 host 検査 (`HostCallBridge`・FS ステージング・save 反映・`deliverDrop`・`installDropTarget`) | **13 PASS / 0 FAIL** |
| `bash tools/gui/test/selftest.sh` (native ASan/UBSan) | 314 passed / 0 failed (変更前と同数) |
| `bash tools/gui/e2e.sh` (gui 単体 wasm・headless Chrome・golden 完全一致・sigprobe) | **ALL PASS**、所要 45.652 s (HEAD 相当の作業ツリー) |
| `bash tools/shimx/test.sh --quick` | exit 0 (MT/ST PASS・fail-fast 9 モード・M4 互換 PASS・`verify_sig` m11 / m11_3 の signature mismatch 0) |
| `tsc --noEmit` | exit 0 |

数え方: 「shimx weak 39 本」= `llvm-nm -g --defined-only` の W 件数。「gui が公開名で強定義 7 本」= `gui_adapt_w32.o` の T と shimx W の積集合。「C 側 58」= `t_main.c` の `CHK` 成功数。
`gui e2e.sh` が shimx 無しの単体 wasm リンクで通ることは、`WaitForMultipleObjects` 等の弱参照が未解決でも壊れないことの回帰確認を兼ねる。

### 4.1 ネガティブコントロール
| 壊し方 | 期待 | 実測 |
|---|---|---|
| NC1: shimx から `SHIMX_WEAK` を外したコピーをリンク | duplicate symbol を検出して失敗 | rc=1、duplicate symbol **7** (= gui 公開名 ∩ shimx weak の 7 本と一致) |
| NC2: host (`HostCallBridge`) を起動しない | ShellExecute / ダイアログ検査が落ちる | C 側 **14** 項目 FAIL、exit 1 |

## 5. 変更ファイル

`tools/gui/src/{gui_core.c, gui_core_ext.inc, gui_platform.c}`・`tools/gui/include/gui_hostcall.h`・`src/runtime/gui_hostcall.ts`・`tools/shimx/src/{shell.c, handles.c, shimx.h}`・`tools/gui/gen_api.py` (生成物ヘッダを出力に含める。手編集されていた `IMPORTS.md` 先頭と一致させ、再生成で差分が出ない)・`tools/gui/{IMPORTS.md, exports.txt}` (再生成: 実装済み 270→277。`IMPORTS.md` は fail-fast stub 159→152 で、差分 7 は §2 で IMPL 化した 7 名と一致)・`tools/gui/shimx_coexist/`。
shimx の生成物 (`BACKLOG.md` / `inventory.md` / `data/*` / `exports.txt`) は再生成しなかった: `test.sh --quick` は OTT 素材が無いと OTT 列と `ott_api_resolved` を落とす (実測: 24→0)。新設の 3 公開関数 (`shimx_set_notify_hook` / `shimx_drag_accepts` / `shimx_hdrop_create`) は次回のフル `test.sh` 再生成で反映される。

## 6. 未解決・範囲外

検証範囲: node + mock の window / picker、m11 IR 由来の adapter、合成テスト。範囲外: 実 FL guest・実ブラウザ。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実ブラウザ (Chrome) での `showOpenFilePicker` / `showSaveFilePicker` / `window.open` e2e が未実施。これらは transient user activation (約 5 秒) を要し、FL の操作が入力イベントから遅れると picker が SecurityError → FALSE (`CDERR_INITIALIZATION`) になり得る | 受入条件「Web 実装経由で動く」の実機確認 | 新規子チケット [GUI-9] (`tools/gui/e2e` の CDP ドライバでユーザ操作付き e2e) — 親 #13 / M-Integration |
| `RegisterDragDrop` 経路: `gui_set_drop_target_invoker` の口のみ。guest の `IDropTarget` vtable 呼出 (m11_icall / `shimx_cbtrans_set_invoke` 経由) と CF_HDROP を返す `IDataObject` が未実装 | FL が OLE D&D のみ使う場合ファイルドロップ不可 | 新規子チケット [SHX-T12] |
| save の反映契機: `flushSaves()` は手動呼出。FL の `CloseHandle` 等への自動結線が無い | 保存したファイルが実ファイルへ出ない | 新規子チケット [SHX-T13] (pathreg の flush 契機 #169 と整合) |
| `gui_shimx_attach()` と `HostCallBridge.start()` を呼ぶ起動 glue が未結線 (`tools/m11/shimx_link` / 起動 glue 側) | 実 FL 結線ビルドで MsgWait の handle 待ちが 5 ms poll 縮退、ダイアログが host 未接続で FALSE | #177 [SHX-T9] (実機検証) にコメント |
| 実 FL guest との結合は未実施。MsgWait の `HANDLE` 配列の要素幅は、shimx が `HANDLE = size_t` (wasm32 で 4 B)、lift 側が 8 B 要素で組む可能性があり**整合は未検証** | handle 配列の読み違い (未確認) | #177 [SHX-T9] にコメント (実 guest でのみ検証可能) |
| OFN の `lpfnHook` / `OFN_ENABLETEMPLATE` / フォルダ選択 (`SHBrowseForFolder` / `IFileDialog`) は未対応 | 該当 FL 機能 (使用有無は未調査) | [SHX-T12] に含める (使用有無を先に `SHIMX_TRACE` で確認) |
| shimx の生成物 (BACKLOG / inventory / data / exports) が未再生成 (§5) | 新設 3 関数が一覧に無い | 次回のフル `bash tools/shimx/test.sh` (OTT 素材付き) |

## 7. 再現

```
bash tools/gui/shimx_coexist/coexist.sh      # 約 12 秒。env: M11_IR=<boot_final3.ll> (無ければ integ/fixtures の GUI declare 抜粋)
bash tools/gui/test/selftest.sh              # native 回帰
bash tools/gui/e2e.sh                        # gui 単体 wasm 回帰
```
前提: emsdk (`toolchain-emsdk`)、node 22 以上、`x86_64-w64-mingw32-gcc` (`gen_api.py` が arity 表に使う)。M11 IR は `work-m11`。
