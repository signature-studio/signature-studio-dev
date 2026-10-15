# REPORT — shimx × gui 共存と Web 実装接続 (#172 [SHX-T5])

検証起点: コミット済み HEAD `96f95dc` (base `64e617f`)。クリーンな detached worktree で `coexist.sh` を実行して取得 (§4)。
レビュー差し戻し対応 (§3.4 複数選択の境界修正) の再検証起点: コミット済み HEAD `eb09329` (§4.2・§4.3)。
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
複数選択の組立 (`file_dialog()`): 作業バッファ `w[]` は `GUI_HC_OUT + 700` 要素 (dir ≤ 600 + host 応答 < `GUI_HC_OUT` B。UTF-16 の単位数は UTF-8 のバイト数を超えない)。`fd_put()` は `u8_to_u16x` の打ち切り報告を見て、収まらなければ**切り詰めた断片を返さず** FALSE + `CDERR_INITIALIZATION` (`GetLastError`=111) にする。
名前は最大 64 件 (`FD_NAMES_MAX`): 65 件目以降を黙って捨てず、同じく FALSE + `CDERR_INITIALIZATION` を返す (撤廃は §6)。
save は FL が閉じた POSIX ファイル (書込み handle の CloseHandle) を `HostCallBridge` が選択済み handle へ反映する (#958 で自動化。手動の `flushSaves()` も残す。§11)。

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

### 4.2 レビュー差し戻し対応後の再検証 (HEAD `eb09329`、クリーン detached worktree、並列 1)

| 検査 | 結果 |
|---|---|
| `coexist.sh` 3 回 | 全て ALL PASS。所要 **9.387 / 8.572 / 8.787 s** (開始時 load average 1 分値 0.51 / 0.50 / 0.54)。リンク duplicate symbol 0 / warning 0 / undefined symbol 0、C 側 **58 PASS / 0 FAIL**、host 側 **13 PASS / 0 FAIL**、NC1 duplicate symbol 7・NC2 C 側 14 FAIL (§4.1 と同値) |
| `bash tools/gui/test/selftest.sh` (native ASan/UBSan) | **342 passed / 0 failed** (= 314 + 新規境界テスト 28)。所要 6.000 s (コンパイル込み) |
| `bash tools/gui/e2e.sh` | **ALL PASS**、所要 41.864 s (終了時 load average 1 分値 1.18)。golden EXACT MATCH 0 px 差 (固定メモリ / MEMORY_GROWTH / reach の 3 構成)、sigprobe `mismatch=0 unresolved-imports=0`、陰性対照 177 |

境界テスト (`tools/gui/test/selftest_fd.inc`、`selftest.c` から include): host 役スレッドが `gui_hostcall_native()` 経由で N 件 × nlen 文字の名前列を返し、`GetOpenFileNameW` (`OFN_EXPLORER|OFN_ALLOWMULTISELECT`) の `lpstrFile` を `nMaxFile` 要素ちょうどの heap にして ASan で境界外 R/W を、`w[]` を UBSan で添字境界を検出する。
- 成功系 12 組 (件数 × 名前長 × narrow/wide): N = 3 / 50 / 52 / 56 / 58 / 60 / 63 / 64 (18 文字) と (64 × 60 文字)・(40 × 100 文字)・(60 / 64 × U+3042 を 15 個含む名前)。うち総文字数が 1020 を超える組は 10 (**1028–4080**、旧実装の `1020 - wl` 上限を超える領域)。各組で ① `nMaxFile` = 必要数ちょうどで TRUE かつ全 N 名が完全一致 (dir・各名・終端・`nFileOffset`) ② `nMaxFile` = 必要数 − 1 で FALSE・`FNERR_BUFFERTOOSMALL`・先頭 WORD = 必要数、を検査 (12 × 2 = 24 項目)。
- 失敗系 4 組: 65 / 70 (18 文字)・65 / 200 (5 文字) 件 → FALSE・`CDERR_INITIALIZATION`・`lpstrFile` 不変 (4 項目)。

数え方: 「総文字数」= `dir\0` + Σ(名前長 + 1) + 終端 `\0` の UTF-16 単位数 (= `nMaxFile` に要る要素数、テスト内 `fd_need()`)。

`selftest` には本 PR と無関係の**既存の flake**がある: headless host の描画スレッド `gui_headless.c:33 blit_surf` が `surf_free` 済みの面を読む ASan heap-use-after-free (発生した実行は `P1/*` セクションまたは `SendMessage / cross-thread` で止まり、追加した境界テストより前)。base `8953540` と HEAD `eb09329` を交互に各 100 回実行して **10 / 9 回**発生 (同率)。発生しなかった実行は常に 342 / 0 で、本 PR のコードパスは含まれない。§6 に起票依頼。

### 4.3 境界テストのネガティブコントロール

| 壊し方 | 期待 | 実測 |
|---|---|---|
| NC-A: 旧実装 (`8953540` の `src/`) に新テストを当てる (`selftest.sh` 既定構成) | 旧実装で FAIL | n = 52 / 56 で 4 項目 FAIL (TRUE を返すが名前数・内容が不一致 = 断片名)、n = 58 で UBSan abort `gui_core_ext.inc:481:83: index 1024 out of bounds for type 'uint16_t [1024]'` (exit ≠ 0) |
| NC-B: NC-A に `-fsanitize-recover=address,undefined` + `ASAN_OPTIONS=halt_on_error=0` を足して最後まで流す | 該当項目が全て FAIL | **318 passed / 24 failed** (成功系 10 組 × 2 + 65 件以上 4)。ASan stack-buffer-overflow 2 件 (L481 の WRITE of size 2、`memcpy(file, w, wl*2)` の READ of size 2050)、UBSan 2 件 |
| NC-C: 修正後の実装から 65 件目以降の失敗判定 1 行を削除 | 失敗系 4 組が FAIL | **338 passed / 4 failed** |
| NC-D: 修正後の実装で `FD_W_CAP` を 1024 に戻す (`fd_put` の打ち切り判定は残す) | 断片を TRUE で返さず FALSE にする | **322 passed / 20 failed**。失敗は全て FALSE + `CDERR_INITIALIZATION` (`ret=0 cderr=2`)。`file_dialog` 由来の ASan / UBSan 報告 0 |

`tools/gui/src/{gui_core.c, gui_core_ext.inc, gui_platform.c}`・`tools/gui/test/{selftest.c, selftest_fd.inc}`・`tools/gui/include/gui_hostcall.h`・`src/runtime/gui_hostcall.ts`・`tools/shimx/src/{shell.c, handles.c, shimx.h}`・`tools/gui/gen_api.py` (生成物ヘッダを出力に含める。手編集されていた `IMPORTS.md` 先頭と一致させ、再生成で差分が出ない)・`tools/gui/{IMPORTS.md, exports.txt}` (再生成: 実装済み 270→277、fail-fast stub 159→152。STUB→IMPL の 7 名 = `CharLowerW` / `CharNextExA` / `CharToOemBuffW` / `GetOpenFileNameW` / `GetSaveFileNameW` / `WTSRegisterSessionNotification` / `WTSUnRegisterSessionNotification`)・`tools/gui/shimx_coexist/`。
shimx の生成物 (`BACKLOG.md` / `inventory.md` / `data/*` / `exports.txt`) は再生成しなかった: `test.sh --quick` は OTT 素材が無いと OTT 列と `ott_api_resolved` を落とす (実測: 24→0)。新設の 3 公開関数 (`shimx_set_notify_hook` / `shimx_drag_accepts` / `shimx_hdrop_create`) は次回のフル `test.sh` 再生成で反映される。

## 6. 未解決・範囲外

検証範囲: node + mock の window / picker、m11 IR 由来の adapter、合成テスト。範囲外: 実 FL guest・実ブラウザ。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実ブラウザ (Chrome) での `showOpenFilePicker` / `showSaveFilePicker` / `window.open` e2e が未実施。これらは transient user activation (約 5 秒) を要し、FL の操作が入力イベントから遅れると picker が SecurityError → FALSE (`CDERR_INITIALIZATION`) になり得る | 受入条件「Web 実装経由で動く」の実機確認 | 新規子チケット [GUI-9] (`tools/gui/e2e` の CDP ドライバでユーザ操作付き e2e) — 親 #13 / M-Integration |
| `RegisterDragDrop` 経路: guest の `IDropTarget` 呼出し橋と CF_HDROP の `IDataObject` は #1388 [SHX-T23] で実装 (node + mock まで。実 FL guest は未検証、詳細 `REPORT_SHX-T23.md`) | FL が OLE D&D のみ使う場合の実機可否は未確認 | #1178 [SHX-T21] / #177 [SHX-T9] |
| save の反映契機: CloseHandle 契機の自動化は #958 で完了 (node harness のみ)。本番起動 glue への結線と再読み込み後の復元は未了 | 実機で保存が反映されない | #134 (前提) → [SHX-T38] #3131 |
| `gui_shimx_attach()` と `HostCallBridge.start()` を呼ぶ起動 glue が未結線 (`tools/m11/shimx_link` / 起動 glue 側) | 実 FL 結線ビルドで MsgWait の handle 待ちが 5 ms poll 縮退、ダイアログが host 未接続で FALSE | #177 [SHX-T9] (実機検証) にコメント |
| 実 FL guest との結合は未実施。MsgWait の `HANDLE` 配列の要素幅は、shimx が `HANDLE = size_t` (wasm32 で 4 B)、lift 側が 8 B 要素で組む可能性があり**整合は未検証** | handle 配列の読み違い (未確認) | #177 [SHX-T9] にコメント (実 guest でのみ検証可能) |
| OFN の `lpfnHook` / `lpTemplateName` (`OFN_ENABLEHOOK` / `OFN_ENABLETEMPLATE` / `OFN_ENABLETEMPLATEHANDLE`) は **fail-fast で明示** (`file_dialog()` 入口。`selftest_fd.inc` で検査、§8) | hook 付き呼出しは abort する (黙って無視しない) | 対応は必要時に別 issue |
| フォルダ選択 (`SHBrowseForFolder` / `IFileDialog`) は shimx・gui とも実体無し (IMPORTS.md で未登録)。FL 本体は `SHBrowseForFolderA` を静的 import (呼出の有無は未確認) | 該当 FL 機能 (呼出の有無は未確認) | #1179 [SHX-T22] (調査: `REPORT_APPENDIX.md`) |
| 複数選択は最大 64 件 (`FD_NAMES_MAX`): 65 件以上は FALSE + `CDERR_INITIALIZATION`。名前の列を `names[]` 配列に載せず 2 パスで走査すれば撤廃できる (host 応答は 4,094 B 以内なので 1 文字名で最大 2,047 件) | FL で 65 件超を一括選択する操作 (有無は未調査) | 新規子チケット (PM 起票依頼; FL の実操作で要否を判断) |
| `selftest.sh` の既存 flake: `gui_headless.c:33 blit_surf` が解放済み面を読む ASan heap-use-after-free (base・HEAD とも 100 回中 10 / 9 回、§4.2) | `selftest.sh` と、それを `pipefail` 下で呼ぶ `e2e.sh` step 1 が同率で落ちる (本 PR の変更とは無関係) | 新規子チケット [GUI-*] (PM 起票依頼。headless host の render thread と `surf_free` の同期) |
| shimx の生成物 (BACKLOG / inventory / data / exports) が未再生成 (§5) | 新設 3 関数が一覧に無い | 次回のフル `bash tools/shimx/test.sh` (OTT 素材付き) |

## 7. 再現

```
bash tools/gui/shimx_coexist/coexist.sh      # 実測 8.6–12.1 s (§4・§4.2)。env: M11_IR=<boot_final3.ll> (無ければ integ/fixtures の GUI declare 抜粋)
bash tools/gui/test/selftest.sh              # native 回帰
bash tools/gui/e2e.sh                        # gui 単体 wasm 回帰
```
前提: emsdk (`toolchain-emsdk`)、node 22 以上、`x86_64-w64-mingw32-gcc` (`gen_api.py` が arity 表に使う)、`wasm-objdump` (wabt; `sigprobe.sh` の `unresolved-imports` 判定。無いと 0 を空振りで出す)。Ubuntu runner では `apt-get install gcc-mingw-w64-x86-64 wabt`。`e2e.sh` は repo 直下の `node_modules` (tsc) も要る。M11 IR は `work-m11`。

## 8. SHX-T14 (#957): OFN hook / テンプレートの fail-fast 明示

検証起点: コミット済み HEAD `bb57ca34` (base `fedbcbbf`、worktree `ws-957`)。IR は `work-m11` 由来 (`boot_final3.ll` sha1 `4a4a5fa01e`)。

変更: `file_dialog()` の入口で `OFN_ENABLEHOOK` / `OFN_ENABLETEMPLATE` / `OFN_ENABLETEMPLATEHANDLE` が立つ呼出しを `gui_failfast` で落とす。黙って無視して通常ダイアログとして動くことを防ぐ。

| 検査 | 結果 |
|---|---|
| `bash tools/gui/test/selftest.sh` (HEAD `bb57ca34`) | **506 passed / 0 failed**、rc 0、所要 **14.464 s** (新規: hook / テンプレートの fail-fast 2 件 = `expect_failfast` で子プロセス abort を検査) |
| `bash tools/gui/shimx_coexist/coexist.sh` (HEAD `bb57ca34`) | **ALL PASS**、所要 **14.660 s**。link duplicate 0 / warning 0 / undefined 0、C 側 **58 PASS / 0 FAIL**、host 側 **13 PASS / 0 FAIL**、NC1 duplicate 7・NC2 C 側 14 FAIL (§4.1 と同値) |
| `bash tools/gui/e2e.sh` (main 作業ツリーで実行。変更は未 commit の同一 diff を当てた状態。HEAD `bb57ca34` 上では未実行) | **ALL PASS**、所要 **4 分 53.758 s** (load average 1 分値 0.57 開始時)。stress 固定メモリ 50000 frames EXACT MATCH 0 px 差・memory.grow 経路 EXACT MATCH・ネガコン 2 件 exit 1 |

注: e2e は HEAD `bb57ca34` ではなく、同一 diff を当てた main 作業ツリーで実行した。変更は gui の OFN 入口のみで描画経路を通らないが、コミット済み HEAD での再実行は未実施。

### 8.1 受入条件の達成状況 (#957)

| 受入条件 | 状態 |
|---|---|
| RegisterDragDrop で登録された guest の IDropTarget が drop から呼ばれ、CF_HDROP の IDataObject が渡る | **未達** → #1178 [SHX-T21] |
| OFN hook / テンプレートの扱いを決め、未対応なら fail-fast で明示 | **達成** (本 PR) |
| フォルダ選択 (BIF 系) の扱いを決め、未対応なら明示 | **未達** → #1179 [SHX-T22] |
| node + mock と REPORT 実測 | 本 PR 分は達成 (上の表)。子 issue 分は各 issue で |

## 9. 実ブラウザ確認 (SHX-T19 #1159、HEAD `7f5807c7`)

方式: `bash tools/gui/shimx_coexist/browser_e2e.sh`。`coexist.sh` の objects から `ENVIRONMENT=web,worker` の wasm を link (`coexistWeb`、INVOKE_RUN=0)し、`src/runtime/gui_hostcall.ts` を ES モジュール化して page から読む。headless Chrome (CDP) で page を開き、wasm の hostcall 要求 (`gui_hostcall.h` と同じ手順) を **`browserEnv` (実 `window.open` / 実 `showOpenFilePicker` / `showSaveFilePicker`)** に処理させる。Chrome 154.0.8037.97。

- user activation: CDP `Runtime.evaluate` の `userGesture:true` で与える。activation 無しの試験は、前の gesture の失効 (`navigator.userActivation.isActive` が false) を待ってから行う。
- picker の UI だけ差し替え: headless では native picker を操作できないため、**activation 下の呼出のみ** mock handle (`getFile` / `createWritable`) を返す。呼出時点の `navigator.userActivation.isActive` を記録し、activation 下で呼ばれたことを検査する。activation 無しの呼出は差し替えず、実 API が返す拒否を見る。
- 含めないもの: 実 native picker の選択操作、実 FL guest の CALL 経路 (guest 側の呼出は coexist の C 側 58 項目で確認済み)。

| 検査 | 結果 |
|---|---|
| web build wasm が実 Chrome の page で起動 (`crossOriginIsolated` / SharedArrayBuffer) | PASS |
| ShellExecute https → `window.open` (user activation 下) | PASS (result=1) |
| ShellExecute http → `window.open` (user activation 下) | PASS (result=1) |
| ShellExecute mailto → `window.open` (user activation 下) | PASS (result=1) |
| `window.open` を activation 無しで呼ぶ → Chrome のポップアップブロックで失敗 | PASS (result=0 → SE_ERR) |
| `javascript:` は host 側で拒否 (window.open 未呼出) | PASS |
| GetOpenFileNameW → `showOpenFilePicker`: activation 無しは実 API が「user gesture 要求」で失敗 (result=-16) | PASS |
| 同: activation 下で呼ばれ、選択結果 `kick.wav` が guest の応答 buffer に反映 | PASS (`calls` の active=true) |
| 選択ファイルの内容がステージング FS へ書き出される `[1,2,3]` | PASS |
| GetSaveFileNameW → `showSaveFilePicker`: activation 無しは失敗 (result=-16) / 下で呼ばれ `song.flp` が返る | PASS |
| save: FL が書いた内容 `[70,76,80]` が選択 handle の `createWritable` へ反映 | PASS |
| host log は想定内 4 件 (activation 無し blocked 1 / javascript 拒否 1 / picker 失敗 2) のみ・page 例外 0 | PASS |

- 実測: `browser_e2e.sh` HEAD `7f5807c7` で **14 PASS / 0 FAIL** × 2 回 (所要 **11.751 s / 11.806 s**、単独実行)。HEAD `cfd3f7b2` (コード同一) で再実行 **14 PASS / 0 FAIL** (所要 **19.538 s**、coexist 直後の単独実行)。
- 回帰 `coexist.sh` HEAD `7f5807c7`: ALL PASS、所要 **14.430 s / 14.557 s**。HEAD `cfd3f7b2`: ALL PASS、所要 **17 s** (1 回)。C 側 58 / 0、host 側 13 / 0、link duplicate 0 / warning 0 / undefined 0、NC1 duplicate 7、NC2 C 側 fail 14。
- 同時実行は不可: browser と coexist は `work/` を共有するため、並行すると browser が rc=1 で落ちる (単独再実行で PASS を確認)。
- 環境: emsdk 6.0.12 (PATH 経由。`EMSDK_ENV` 未指定時は PATH の emcc を使う)、`llvm-nm` (llvm-18)、gcc-mingw-w64-x86-64、wabt。
- ネガコントロール: activation を常時付与 (`withoutActivation` を gesture 付きに置換) すると **4 FAIL / 10 PASS** (14 検査中 4 FAIL、exit 1、所要 11.175 s、HEAD `cfd3f7b2`・`browser_e2e.mjs` は `7f5807c7` と同一)。activation 無しの検査と想定内 log の件数検査が、activation の有無を実際に区別していることを確認した。

未解決 (起票先): 実 native picker の操作 (headless 不可。手動採取または GUI-9 の入力注入で扱う)・実 FL guest 結合での `window.open` / picker 呼出 (#177 SHX-T9)。

## 10. 実ブラウザ e2e (SHX-T13 #956 の別実装: `browser_e2e_t13.sh`)

`bash tools/gui/shimx_coexist/browser_e2e_t13.sh` (前提: 先に `coexist.sh` で `work/` の obj を作る)。同じ obj を `ENVIRONMENT=web,worker` でリンクし、`src/runtime/gui_hostcall.ts` を bun で browser 向けに bundle、headless Chrome で走らせる。

- 注: main の #1159 版 (`browser_e2e.sh`、§9) と並存する本 PR の版。同名ファイルの競合を避けるため `_t13` 名に退避した。
- **確認方式**: user activation が要る host 呼出 (`window.open` / picker) の直前に、ページの `#gate` ボタンを CDP `Input.dispatchMouseEvent` の実マウスで押させる (10 回 = window.open 4 + open 5 + save 1)。`navigator.userActivation.isActive` を各呼出で記録し、全件 true を検査。
- **picker**: headless で native ダイアログは操作できないため、`showOpenFilePicker` / `showSaveFilePicker` だけ差し替え。`browserEnv()` の本体経路 (types 変換・Abort→null・File 読込・createWritable) は通る。
- **window.open**: 実 API を呼ぶが遷移先は `about:blank` (外部通信なし)。URL に `blocked` を含む場合のみ null を返してポップアップブロックを模擬。
- 変更: `HostCallEnv.openWindow` を `boolean | Promise<boolean>` にし、`openUrl` を async 化 (ブラウザ側の戻り値を await する)。node 側の挙動は不変。

### 実測 (code HEAD `862b4967` = main `c4e93550` 取り込み後の merge commit。測定 HEAD `862b4967`。runner、Chrome 154.0.8037.97、直列・前景実行、開始時 load average 1 分値)

測定順: `coexist.sh` → `browser_e2e_t13.sh` → `browser_e2e.sh` (main 版、確認用)。各 run は単独 (並行なし)。

| 項目 | 結果 |
|---|---|
| `coexist.sh` (node + mock) | rc=0 / 10.528 s / 開始時 load 0.46 / link duplicate 0・warning 0・undefined 0 / ALL PASS (件数は §4 を参照。host 13 PASS 0 FAIL) |
| `browser_e2e_t13.sh` (本 PR の版、web build + CDP) | rc=0 / 108.567 s / 開始時 load 0.53 / web link rc=0 / **BROWSER RESULT pass=13 fail=0** / Chrome 154.0.8037.97 |
| `browser_e2e.sh` (main #1159 版、確認用) | rc=0 / 11.341 s / 開始時 load 0.11 / **BROWSER RESULT pass=14 fail=0** / Chrome 154.0.8037.97 |
| wasm 側 C テスト (web build、`browser_e2e_t13.sh` 内) | RESULT pass=58 fail=0 |
| window.open 実行時の user activation | 4 件すべて active |
| picker 実行時の user activation | open 5 件・save 1 件すべて active |

- 測定環境の補足: runner に mingw (`gcc-mingw-w64-x86-64`) と `wabt` が無かったため apt で導入。worktree で `pnpm install --frozen-lockfile` を実行 (main 版 `browser_e2e.sh` が `node_modules/.bin/tsc` を使うため)。
- 本 PR の code 変更: `src/runtime/gui_hostcall.ts` ほか `tools/gui/shimx_coexist/browser_e2e_t13.{sh,mjs}`・`browser_page.js`・`browser_index.html` (`origin/main` 比の差分)。

### 旧 commit の参考値 (code commit `fdc95bf2`、測定 HEAD `fe406aa5`。現 HEAD の実測ではない)

`browser_e2e_t13.sh` 導入前の版で測ったもの。`browser_e2e.sh` の旧版 (main 取り込み前) の値で、現在の `browser_e2e.sh` (main 版) とは別物。

| 項目 | 結果 |
|---|---|
| `coexist.sh` | rc=0 / 14.72 s / ALL PASS |
| `browser_e2e.sh` (旧版) | rc=0 / 108.25 s / web link rc=0 / BROWSER RESULT pass=13 fail=0 |

判定項目: window.open の URL 一致 (C 側で拒否した 4 件は host に来ない)、picker types・multi フラグ、buffer 反映 (kick.wav / a.wav / b.wav / c.mid の内容)、save の実 handle 反映 (`flushSaves` = 1)、host log の想定外エラー無し、ページの未捕捉例外無し。

### 未解決

- 実 FL guest との結合は未実施 (§6 の既存項目)。
- browser_e2e.mjs には negative control を入れていない (node 版の NC1/NC2 相当は未実装)。
- 実 FL の `ShellExecute` / `GetOpenFileName` 呼出の順序・タイミングは未検証 (§6 の SHX-T9 / SHX-T12 側)。

## 11. save 反映契機の自動結線 (SHX-T15 #958)

書込み file の CloseHandle を契機に、保存待ちの先を host が実体へ反映する (node harness で検証)。検証表・設計・限界は `REPORT_SHX-T15.md`。本番起動経路への結線と再読み込み後の復元は未了 → [SHX-T38] #3131。
