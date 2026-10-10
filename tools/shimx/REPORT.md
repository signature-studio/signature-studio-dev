# tools/shimx REPORT — Win32/CRT shim 拡張 (担当 Q)

- 日付: 2026-10-10 / 検証環境: emcc 6.0.12, node v24.19.0 (emsdk 同梱; 再起動後の PATH に node v26 が無かったため), llvm-nm
- 書込範囲: `tools/shimx/` のみ。`tools/shim` `tools/m2` `tools/m6` `tools/m8` `tools/m11` `tools/plugins` `tools/startup` `tools/targets` は読取のみ (改変 0 行)。
- 検収: `bash tools/shimx/test.sh` → **exit 0** (約 20 秒。`--quick` で OTT 再リンクを省略)

## 0. 結論

| 項目 | 実測 |
|---|---|
| shimx 公開 API | **593 本** (機能 427 + スタブ 166) + 運用フック 33 本。実装 6,724 行 (C) + テスト アサーション 536 行 |
| FLEngine_x64.dll 静的 import **738** に対するカバレッジ | 実装 **358 = 48.5%** (機能 243 + スタブ 115)。libc 解決 `memset` 込み 48.6% |
| 担当範囲 (他担当 DLL を除く 359) に対するカバレッジ | **100.0%** (未実装 **0**、序数 import 0)。対象外 379 = user32/gdi32/comctl32/opengl32 (tools/gui) + dsound (tools/audio) |
| 呼出サイト加重 (静的 7,309 サイト) | shimx 4,050 サイト (55.4%) / 他担当 (GUI) 3,252 サイト (44.5%) / libc 7 |
| delay-load 57 | 実装 23 / 他担当 34 / 未実装 0 |
| プラグイン import (GUI/audio 除く) | OTT vst2 146/147, vst3 150/151 (残 = shell32 序数 74), FreshAir 98/98, FL64.exe 111/111, Serum2 234/238 (残 = 序数 4) |
| **OTT undefined 47 種 (M8)** | shimx リンクで **47 → 23**。Win/CRT API **24 種は全て解決** (CloseHandle/CreateFileW/TlsGet・SetValue/WriteFile/GetProcAddress/LoadLibraryExW/`__readgsqword`/Rtl*/UnhandledExceptionFilter ほか)。残 23 は `function_18*` = lift 欠落で shim の対象外。t1 出力 SHA は baseline と bit 一致 (`b5a91b9b…`, 512 行)。signature mismatch 0 |
| M11 init closure (`boot_final2.ll`) 外部参照 553 | shimx 提供 **183** / GUI・audio 担当 171 / lift 由来 199。**非 GUI の Win/CRT は 100% 提供**、IR declare と wasm 署名の不一致 0 (後述 §4 の 5 件を修正済み) |
| M4 の 53 API | **53/53 継承**。`tools/shim/test/test_main.c` を **無改変** で shimx 実装に対し MT/ST とも ALL PASS |
| テスト | MT(pthread) ALL PASS / ST ALL PASS (6 回連続実行で安定) / fail-fast 6 モード / M4 互換 MT・ST / 署名突合 2 本 / OTT 再リンク+実行回帰 |

## 1. バックログ (優先度付け, `BACKLOG.md` 全表)

使用頻度 = FLEngine の `jmp [IAT]` thunk への静的 call/jmp/lea 参照数 (`scripts/import_scan.py`; 832 thunk → 7,309 サイト)。
必須性 = M11 closure が declare / OTT undefined に載るか。優先度は P0 (必須) > P1 (サイト ≥10 or 3 プラグイン以上) > P2 > P3 (delay・プラグイン専用)。

| 優先 | API 数 | 機能 | スタブ | libc | 序数 | 未実装 |
|---|---|---|---|---|---|---|
| P0 (M11 closure ∪ OTT 24) | 194 | 176 | 18 | 0 | 0 | 0 |
| P1 | 38 | 34 | 4 | 0 | 0 | 0 |
| P2 | 165 | 64 | 100 | 1 | 0 | 0 |
| P3 | 111 | 58 | 39 | 8 | 6 | 0 |
| X (他担当, 544 件) | — | — | — | — | — | 対象外 |

上位使用 API: LeaveCriticalSection 799 / EnterCriticalSection 699 / MulDiv 164 / IsEqualGUID 114 / FreeLibrary 106 / RegCloseKey 99 / timeGetTime 79 / CloseHandle 73 /
Init・DeleteCriticalSection 65 / GetLastError 61 / GetCurrentThreadId 51 / VariantInit 48 / LoadLibraryW 48 / RegQueryValueExW 46。
→ CS・COM・レジストリ・ローダが頻度上位。いずれも機能実装済み (スタブではない)。

## 2. 実装した領域 (依頼項目との対応)

| 依頼 | 実装 |
|---|---|
| メモリ内レジストリ | Reg{Open,Create,Query,Set,Delete,Enum,QueryInfo,Get}Key/Value (W/A), 5 ルート, 名前順/作成順列挙, ERROR_MORE_DATA/KEY_DELETED, `OpenProcessToken/GetTokenInformation`。**既定シード** (Windows NT CurrentVersion, CodePage, International 等) + `.reg` 風 `import_text`/`export_text` (往復テスト済) + `shimx_reg_set*` |
| wide-string/ロケール | MultiByteToWideChar/WideCharToMultiByte (UTF-8/1252/Latin-1/ASCII, サロゲート, usedDefault), lstr*, CompareString{A,W,Ex} (小文字<大文字の二次差), LCMapString, GetStringTypeW, Char{Upper,Lower,Next}* (weak), GetLocaleInfoW (en-US 固定データ+LCID 名数種), Enum{SystemLocales,CalendarInfo}, GetDate/TimeFormatW, FormatMessage{A,W} (8B 引数配列), NormalizeString, CPInfo |
| GetLastError スレッドローカル化 | 擬似 TEB の +0x68 に格納。**`__readgsqword/dword` で同値が見える** (lifted MSVC CRT 用)。TlsAlloc 1088 スロット (TEB+0x1480 / 拡張 +0x1780), FlsAlloc 256 + 終了時コールバック |
| module/Proc フック口 | モジュール表 (主 exe + 擬似システム DLL = 最小 PE ヘッダ 4KB), GetModuleHandle{A,W,ExW}/FileName/LoadLibrary{A,W,ExW}/FreeLibrary/GetProcAddress (名前/序数), `shimx_module_register` `shimx_proc_register` `shimx_set_proc_resolver` `shimx_set_load_hook`, **組込み GetProcAddress 表 521 エントリ** (実装済み API を DLL 別に返す), IMAGEHLP (ImageNtHeader 等), FindResource/LoadResource の provider フック |
| 環境/システム | 環境変数 (大小無視, 展開, ブロック取得), コマンドライン (A/W), GetStartupInfoW (Win64 104B), GetSystemInfo (48B), GetVersion/ExW/VerifyVersionInfoW/VerSetConditionMask, GlobalMemoryStatus(Ex), QPC, ComputerName, IsProcessorFeaturePresent (FASTFAIL/AVX は FALSE), SetErrorMode, ExitProcess/TerminateProcess (exit フック), CreateProcessW (常に FILE_NOT_FOUND), アトム |
| named event/mutex/semaphore | 共通名前空間 (`Local\`/`Global\` 同一視), Create/Open/Release/Set/Reset/Pulse, ERROR_ALREADY_EXISTS, 型違い同名は INVALID_HANDLE, **WaitForMultiple (any/all, 64 本)**, SignalObjectAndWait |
| FindFirstFile / VFS | `C:\x`→`/c/x`, UNC, `\\?\`, `.`/`..` 畳込み, POSIX 絶対パス素通し, FS 未発見時の **大小無視再探索**, Find{First,FirstEx,Next,Close} (ワイルドカード/ソート/`.`,`..`), `shimx_set_path_mapper`。GetFullPathName/Temp*/CurrentDirectory/Drive/Volume/MoveFile/CopyFile/属性, **FileMapping (名前付き無名共有+ファイル書戻し)**, INI (GetPrivateProfile*/Write…) |
| SEH 第一手 | AddVectoredExceptionHandler/Remove, RaiseException (VEH→UEF→fail-fast; 継続可能例外は復帰), RtlUnwind(Ex) は fail-fast, RtlCaptureContext/LookupFunctionEntry/VirtualUnwind/PcToFileHeader/UnhandledExceptionFilter/SetUnhandledExceptionFilter (MSVC CRT 致命経路を通す最小実装), `shimx_set_raise_hook` |
| CRT lock 群 | `_lock/_unlock/_mlock/_munlock/_lock_file/_unlock_file/__acrt_lock/__acrt_unlock/_amsg_exit` (64 本の Win64 CS) |
| 統一ハンドル表 | 16384 スロット, HANDLE=(idx+1)*4, 参照カウント, DuplicateHandle (擬似ハンドル -1/-2 対応, CLOSE_SOURCE), Get/SetHandleInformation, CloseHandle 全種共通 (file/event/thread/mutex/sem/mapping/find/key/token) |
| スレッド拡張 | CREATE_SUSPENDED+ResumeThread, **CreateThread が返す threadId を新スレッド自身の ID に修正**, GetExitCodeThread/Process, Priority/Affinity, SuspendThread (カウントのみ)/TerminateThread (状態のみ), タイマキュー (専用ワーカー), スレッドプール Work, SRWLock/CondVar/InitOnce/SList |
| その他 | BSTR/VARIANT(24B)/SAFEARRAY(Win64)/GUID/IStream(HGLOBAL)/IMalloc/Drag&Drop 登録, shell32 (SHGetFolderPathW, KnownFolder, PIDL, SHFileOperationW, ShellExecute* フック), version.dll 合成版情報, wininet/mpr/crypt32/wintrust/ws2_32 固有名/msacm32/winspool/comdlg32/MIDI の常時エラー・0 台スタブ |

## 3. M4 からの差分 (バグ修正を含む)

| M4 | shimx |
|---|---|
| ハンドル 256 スロット固定, file/event/thread のみ | 16384, 参照カウント, 9 種のオブジェクト, 名前付き |
| CRITICAL_SECTION: ポインタ→mutex 表 (128 件上限, 溢れで fail-fast) | クライアントメモリ上の Win64 40B 構造体を直接実装 (5000 個同時 OK / ゼロ初期化も未ロック扱い) |
| GetLastError プロセス単位 | スレッドローカル (TEB+0x68) |
| CreateThread の threadId = 作成側 ID (誤り) | 新スレッドの ID |
| ヒープ: ユーザポインタ 4B 整列 | 16B 整列 (Win64 HeapAlloc 相当), HeapSize/Validate/Destroy/GetProcessHeap 追加 |
| WaitForSingleObject のみ | + Multiple/any-all/mutex/semaphore/timeout/INFINITE (ST では deadlock を fail-fast) |
| TLS 64 スロット (pthread key) | 1088 スロット + FLS (thread-local 配列) |

## 4. 検証で見つけた問題と対処 (記録)

1. `collapse()` (パス畳込み) が終端 NUL を潰し直後のスタック残骸を連結 → 別バッファへ書く方式に修正 (M4 テストの日本語名で露呈)。
2. 静的データが低アドレスにあると `GetProcAddress` の序数判定 (<0x10000) が文字列を序数と誤認 → ビルドは `GLOBAL_BASE` ≥ 64KB (flags.sh)。lifted 系 (0x10000000) は問題なし。
3. `__lock/__unlock` が musl 内部名 (ST の library_pthread_stub.o) と衝突 → 定義しない。BSD ソケット名も libc 衝突のため定義しない。
4. M11 IR との署名突合で 5 件不一致 (RetDec が HANDLE/enum/REFCLSID を **i64** で declare): acmMetrics / CoCreateInstance / GetComputerNameExW / GetFileAttributesExW / midiOutShortMsg → 定義側を i64 に合わせた。`verify_sig.sh` を test.sh に組込み (M11・OTT とも 0)。
5. 下流既存スタブとの重複: `m6_stubs_hand` の GetLastError / SetLastError / RaiseException が shimx と衝突 (verify_ott は `--allow-multiple-definition` で shimx 優先として測定)。採用時はそれらの退役が必要。

## 5. 制限・リスク

- **関数ポインタ/COM**: IStream/IMalloc の vtable は Win64 の 8B スロットだが中身は wasm 関数テーブル index。lifted コードからの間接呼出し (署名 i64↔i32) は hostbridge の呼出規約ブリッジが必要。`GetProcAddress` の戻りも同様。
- **SEH**: RtlUnwind/RaiseException(非継続) は fail-fast。Delphi `raise`/try-finally の実行時巻き戻しは lift 側 (M2: UHANDLER 8,021) の課題。
- **ブロッキング待ち**: 実装は futex。ブラウザのメインスレッドでは Atomics.wait 不可 → エンジンは Worker で動かす前提 (M4 同様)。ST ビルドの INFINITE 待ちは fail-fast。
- **コードページ**: 既定 ACP=1252。932 等 DBCS は ERROR_INVALID_PARAMETER (日本語 ACP が要るなら表実装が必要)。ロケールデータは en-US 固定。
- **FileMapping**: マッピング毎の共有バッファ (書戻しは Unmap/Flush/Close)。別プロセスとの共有や巨大ファイルの遅延マップは不可。VirtualAlloc 予約は malloc (上限 512MB/回)。
- **GlobalUnlock** は M4 互換 (ロック済みなら TRUE)。HeapDestroy は配下ブロックを回収しない。SuspendThread は実停止しない。
- 序数 import (shell32 74/155/190, shlwapi 12/219): 名前未特定で未実装。Serum2 の advapi32 Crypt* は常に失敗 (FL 本体は使わない)。
- 実機 FL の実行ではまだ検証していない (M11 の closure と OTT のリンク・署名・t1 回帰まで)。

## 6. 下流チケット案

| # | 案 | 内容 | 担当候補 |
|---|---|---|---|
| T1 | M11 の shim 差替え | `m11_genstubs.py` の SHIM_BIND を廃し `tools/shimx/src/*.c` をリンク、`ir_undef.py --emit-stubs` で残 (GUI 171 件) の fail-fast スタブを生成。重複定義 (m6_stubs_hand 等) 退役、`verify_sig.sh` を M11 ビルドに組込み | M11 |
| T2 | hostbridge 接続 | LoadLibrary/GetProcAddress 実体 (wasm モジュール連結) を `shimx_set_load_hook/proc_register/resolver` へ。COM vtable・コールバックの間接呼出し規約ブリッジ (i64↔i32) | hostbridge |
| T3 | VFS/レジストリ運用 | Win パス写像規約 (`C:`→`/c`) と Emscripten FS マウント構成の確定、`shimx_set_path_mapper` 実装、レジストリの IndexedDB 永続化 (`export_text/import_text`)、tools/startup が列挙したキー集合のシード投入 | runtime / startup |
| T4 | SEH 実巻き戻し | .pdata/UHANDLER を setjmp 系/例外タグに lift、`shimx_set_raise_hook` に接続。RtlUnwindEx の fail-fast 解除 | lift |
| T5 | GUI 側連携 | ShellExecute→`window.open`、GetOpen/SaveFileName→File System Access、Drag&Drop (`shimx_get_drop_target`)、user32 の Char*/MsgWait* は weak なので gui 側の強定義で置換可 | gui |
| T6 | MIDI/タイマ | winmm `midi*` (weak, 0 台) を Web MIDI で強定義、`timeBeginPeriod` と AudioWorklet クロックの整合 | audio |
| T7 | 署名正規化 | RetDec の i64/ptr 揺れを吸収する IR パス (declare を shimx 署名へ正規化) または CI で `verify_sig.sh` を常時実行 | lift |
| T8 | 序数 import と追加 API | shell32 74/155/190・shlwapi 12/219 の同定、Crypt ハッシュ (Serum2)、CP932 テーブル (日本語 ACP) | plugins / shim |
| T9 | 実機検証 | FL 起動 closure (DllMain→初期化) を shimx で通し、`SHIMX_TRACE=1` で GetProcAddress miss/LoadLibrary 失敗/CreateProcess 拒否を収集 → バックログ更新 | M11 |

## 7. 再現

```
bash tools/shimx/test.sh                           # 全検収 (exit 0)
python3 tools/shimx/scripts/import_scan.py         # data/imports.json 再生成 (FLEngine/プラグイン PE 走査)
python3 tools/shimx/scripts/ir_undef.py <ir.ll>    # lift IR の外部参照を shimx/libc/lifter/GUI に分類 (+ fail-fast スタブ生成)
bash tools/shimx/scripts/verify_sig.sh <ir.ll> m11 # IR declare ↔ shimx 署名の突合
bash tools/shimx/scripts/verify_ott.sh             # OTT undefined 47→23 と t1 回帰
```

ユーザ依頼事項: なし (素材は既存。node v26 が PATH に無い環境のため emsdk 同梱 node 24.19 を使用)。
