# tools/shimx REPORT — Win32/CRT shim 拡張 (担当 Q)

- 日付: 2026-10-10 (初版) / **2026-10-10 更新: CAB-211 — M11 リンク フィードバック R1〜R8 対応 (§9)** / 検証環境: emcc 6.0.12, node v24.19.0 (emsdk 同梱), llvm-nm
- 書込範囲: `tools/shimx/` のみ。`tools/shim` `tools/m2` `tools/m6` `tools/m8` `tools/m11` `tools/plugins` `tools/startup` `tools/targets` は読取のみ (改変 0 行)。
- 検収: `bash tools/shimx/test.sh` → **exit 0** (約 20 秒。`--quick` で OTT 再リンクを省略)

## 0. 結論

| 項目 | 実測 |
|---|---|
| shimx 公開 API | **604 本** (機能 438 + スタブ 166) + 運用フック 53 本 (`exports.txt` の 658 = これらに M4 互換 `shim_unimplemented` を加えた数)。実装 6,724 行 (C) + テスト アサーション 536 行 + R1〜R8 追加実装 (§9) + **R2/R3 実体接続 `src/cbtrans.c` (§10, CAB-177)** |
| FLEngine_x64.dll 静的 import **738** に対するカバレッジ | 実装 **358 = 48.5%** (機能 243 + スタブ 115)。libc 解決 `memset` 込み 48.6% |
| 担当範囲 (738 − 他担当 379 = 359) に対するカバレッジ | **100.0%** (未実装 **0**、序数 import 0)。内訳 = 実装 358 + libc 解決 `memset` 1。対象外 379 = user32/gdi32/comctl32/opengl32 (tools/gui) 377 + dsound (tools/audio) 2。実装 358 のうち 9 本は user32 の weak 実装 (Char*W/MsgWaitForMultipleObjects*; gui 側が強定義で上書き可)。**100% は「シンボル提供」の意味**で、うち 115 本はスタブ (常時エラー/0 台/fail-fast の `RtlUnwind*` 等)。機能実装は 243 本 |
| 呼出サイト加重 (静的 7,309 サイト) | shimx 4,050 サイト (55.4%) / 他担当 (GUI) 3,252 サイト (44.5%) / libc 7 |
| delay-load 57 | 実装 23 / 他担当 34 / 未実装 0 |
| プラグイン import (GUI/audio 除く) | OTT vst2 146/147, vst3 150/151 (残 = shell32 序数 74), FreshAir 98/98, FL64.exe 111/111, Serum2 234/238 (残 = 序数 4) |
| **OTT undefined 47 種 (M8)** | shimx リンクで **47 → 23**。Win/CRT API **24 種は全て解決** (CloseHandle/CreateFileW/TlsGet・SetValue/WriteFile/GetProcAddress/LoadLibraryExW/`__readgsqword`/Rtl*/UnhandledExceptionFilter ほか)。残 23 は `function_18*` = lift 欠落で shim の対象外。t1 出力 SHA は baseline と bit 一致 (`b5a91b9b…`, 512 行)。signature mismatch 0 |
| M11 init closure (`boot_final2.ll`) 外部参照 557 | shimx 提供 **182** + shimx 重複 declare (`SHGetFolderPathW.1` = R6 の shimx_dup 分類) **1** / GUI・audio 担当 171 (user32 114 / gdi32 53 / shcore 2 / uxtheme 1 / dsound 1) / lift 由来 203。**非 GUI の Win/CRT は 100% 提供**、IR declare と wasm 署名の不一致 0 (後述 §4 の 5 件を修正済み) |
| **R2/R3 実体接続 (§10, CAB-177)** | `shimx_set_callback_translator` の**変換実体** `src/cbtrans.c` (VA→slot トランポリン→lift 側関数表) + R3 `shimx_lifttab_*` (IL* 10 本 + kernel32 UI言語 3 本を lift ABI トークン化)。M11 純リンクに接続済み: unit 18 の `EnumCalendarInfoW(0x4476d0)` が trampoline 経由で実呼出され **"table index is out of bounds" trap が消滅** (init_count 18・mismatch/undefined 0・survey 800/41/53 不変)。検証: `test/test_cbtrans.c` (MT/ST) + `tools/hostbridge/cb/cb_e2e.sh` (MT 15/ST 12 checks) |
| M4 の 53 API | **53/53 継承**。`tools/shim/test/test_main.c` を **無改変** で shimx 実装に対し MT/ST とも ALL PASS |
| テスト | MT(pthread) ALL PASS / ST ALL PASS / fail-fast 8 モード / M4 互換 MT・ST / 署名突合 3 本 (boot_final2・3 / OTT) / OTT 再リンク+実行回帰 / **R1〜R8 対応分 `test/test_link.c` (MT/ST)** / **R2・R3 実体接続分 `test/test_cbtrans.c` (MT/ST, §10)** / R6 検査 (構造体展開 + 正規化 IR の emcc 通過) |

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
- 序数 import (shell32 74, shlwapi 12/219, d2d1 1): 名前未特定で未実装。shell32 155=ILFree / 190=ILCreateFromPathW は R3 で同定済み (§9.1, GetProcAddress 序数表で解決)。Serum2 の advapi32 Crypt* は常に失敗 (FL 本体は使わない)。
- **コールバック (R2)**: 翻訳フックは登録時に 1 回走り、戻り値 (実 call 可能な関数ポインタ) を保存して以後使う。**変換実体は `src/cbtrans.c` (§10, CAB-177)**: guest VA (≥intptr_limit) を slot トランポリン (寿命 = プロセス, 解放しない) に変換し lift 側関数表 (invoke 契約) へ落とす。未設定時は恒等なので挙動は不変。実 C 関数ポインタ (<intptr_limit) は恒等通過 (M4 互換テストを壊さない)。
- **BSTR (R5)**: 管理外ポインタの free は無視されるため、lift 側が FastMM 等の別確保元 BSTR を SysFreeString した場合はリークになる (abort しない優先)。所有表はピーク同時 BSTR 数 × 8B。
- **intptr 閾値 (R1)**: プロセス共通の 1 変数。image を <0x10000 に敷設する lift 系と MAKEINTRESOURCE 系の両立は敷設側 (lowbase LB_BASE≥0x10000) か閾値設定のいずれかで解決する。
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
python3 tools/shimx/scripts/ir_undef.py <ir.ll>    # lift IR の外部参照を shimx/libc/lifter/GUI に分類
python3 tools/shimx/scripts/ir_undef.py <ir.ll> --emit-stubs out.c        # fail-fast スタブ生成 (構造体 by-value 展開済み, R6)
python3 tools/shimx/scripts/ir_undef.py <ir.ll> --normalize-dup norm.ll   # NAME.1/NAME_D1 重複 declare を基名へ正規化 (R6)
bash tools/shimx/scripts/verify_sig.sh <ir.ll> m11 # IR declare ↔ shimx 署名の突合
bash tools/shimx/scripts/verify_ott.sh             # OTT undefined 47→23 と t1 回帰
bash tools/shimx/scripts/rem11_check.sh            # M11 純リンク (no --fix) 17unit 再測 + R8 進捗 (§9.2)
bash tools/hostbridge/cb/cb_e2e.sh                 # R2/R3 実体接続の往復ハーネス (§10, MT 15 + ST 12 checks)
```

ユーザ依頼事項: なし (素材は既存。node v26 が PATH に無い環境のため emsdk 同梱 node 24.19 を使用)。

## 8. 検収記録 (CAB-11)

- 独立再計算 (pefile で `analysis/win64/extracted/block00031_PE.bin` を直接解析; 呼出サイトは E8/E9 rel32 を独自走査) で主要数値は一致。差異は M11 外部参照 553→557 (ir_undef の declare 正規表現が struct 戻り値 `__asm_cpuid*` 4 件を取りこぼし。lift 由来のみ・shimx/GUI 件数に影響なし) の 1 件のみで修正済み。

## 9. M11 リンク フィードバック対応 — R1〜R8 (CAB-211)

出典: `tools/m11/shimx_link/REPORT.md` §6 (CAB-166, commit 8170eee)。テスト: `test/test_link.c` (`bash tools/shimx/test.sh` の MT/ST で実行)。既存検収 (M4 53/53, MT/ST, 署名突合 0, OTT t1 SHA 一致 `b5a91b9b…`) は **全て維持**。

### 9.1 対応表

| # | 要求 (M11 REPORT §6) | 対応 | 実装 |
|---|---|---|---|
| R1 | 「ポインタ < 0x10000 は序数/整数」判定の閾値設定 or image 敷設 ≥64KB | **実装** | `shimx_set_intptr_limit(lim)` / `shimx_get_intptr_limit()` (既定 0x10000)。判定箇所は 5 か所 (GetProcAddress 序数 / FindResourceA name,type / AddAtom・FindAtomW の MAKEINTATOM / CharUpper・LowerW 単一文字) を共通ヘルパ `shx_is_iptr()` に統一。**lowbase は LB_BASE=0x10000 敷設で既定値のままで整合** (guest ポインタ全て ≥ lim)。LVA=0 敷設 (M11 旧式) では `shimx_set_intptr_limit(0x4000)` 等に下げる — `kernel32.dll!#39682` (Delphi 文字列 LVA 0x9b02) は lim<0x9b02 で文字列扱いになり、序数 shell32 #16..155 (<0x4000) は引き続き有効。デフォルト不変のため M11 の miss 挙動自体は変わらない (harness 側の設定が必要) |
| R2 | 関数ポインタ引数の変換フック | **実装** | `shimx_set_callback_translator(fn)` (型: `void* (*fn)(const char* api, void* cb)`)。適用 API: EnumSystemLocalesW / EnumCalendarInfoW / CreateThread / FlsAlloc / CreateTimerQueueTimer / CreateThreadpoolWork / InitOnceExecuteOnce の **計 7 API** (同期 3 = Enum*・InitOnceExecuteOnce + 非同期 4 = CreateThread・FlsAlloc・タイマ・スレッドプール; REPORT 要求を網羅)。翻訳結果 NULL は元値にフォールバック (呼出側の NULL 判定を保護)。未設定時は恒等 → 既存挙動不変。**VA→トランポリン変換の実体は hostbridge (T2/CAB-177)** がこのフックに接続する |
| R3 | GetProcAddress 組込み表追加 (kernel32 UI言語 3 本, shell32 序数 9 個) | **実装** | kernel32: `GetThreadPreferredUILanguages` / `SetThreadPreferredUILanguages` / `GetThreadUILanguage` を機能実装 (en-US 固定, multi-sz "en-US\0\0", GetProcAddress 名前解決は自動生成 proctable に反映)。shell32 序数は Windows 10/11 の序数表と突合して **同定**: 16=ILFindLastID, 17=ILRemoveLastID, 18=ILClone, 19=ILCloneFirst, 21=ILIsEqual, 25=ILCombine, 152=ILGetSize, 153=ILGetNext, 155=ILFree (既知 190=ILCreateFromPathW も登録)。IL* 8 本を shimx 自前 PIDL 形式で実装し、序数直指定用の新表 `shx_ordtable` (src/module.c, 手書き) から解決。74 (SHCreateStdEnumFmtEtc) は未実装のまま miss |
| R4 | LoadLibrary 失敗方針 (Msctf.dll/avrt/PowrProf.dll を擬似 DLL 登録するか) | **実装** (選択式) | `shimx_set_pseudo_load(1)`: 未知 DLL 名を擬似モジュール (最小 PE ヘッダ画像, 組込み扱い) として登録し LoadLibrary を成功させる。**既定 0 = 従来どおり失敗** (M11 survey で失敗のまま起動が進む実績があるため既定は不変)。失敗/擬似登録は `SHX_TRACE` に出力 |
| R5 | SysFreeString が管理外ポインタを受けたときの挙動 | **実装** | SysAlloc* が確保したベースポインタの所有表 (オープンアドレス法ハッシュ, mutex 保護) を導入。`SysFreeString`: 所有済み→従来どおり free / 管理外→**strict=1 で fail-fast (`SysFreeString (管理外ポインタ)`), strict=0 (既定) で無視 + trace**。二重 free も同一経路で無害化。M11 REPORT §3-#1 の lift 誤り (`_WStrClr` がスタック番地を渡して free で abort) は **この変更だけで abort しなくなる** (--fix の `sx_liftfix.c` C 転記は論理修復として並行維持) |
| R6 | `ir_undef.py --emit-stubs` の構造体 by-value 展開 + `NAME.1` 重複 declare 正規化 | **実装** | (a) `--emit-stubs` が `%name = type {...}` 表から by-value 構造体引数を wasm32 規則で展開 (`WindowFromPoint(%tagPOINT)` → `(int, int)` — M11 REPORT §1 の signature mismatch 1 の再発防止)。(b) 新オプション `--normalize-dup out.ll`: `NAME.<d>` / `NAME_D<d>` (基名が shimx 定義) を基名 declare へ正規化 — 重複 declare 削除 + 呼出siteの引数 0/null 補間 + 戻り値型差の変換命令 (trunc/zext/inttoptr/ptrtoint/fpext/fptrunc)。実測: boot_final2/3 とも 1 名 1 site 正規化され **emcc 通過**。(c) 分類に `shimx_dup` を新設 (§9.3 の再計測参照) |
| R7 | EnterCriticalSection(NULL) の方針 | **実装** (方針決定 + 選択式) | **既定 = fail-fast のまま** (= Win32 実機のアクセス違反相当。survey unit 115 は旧 M4 shim でも同一 unit で abort する lift 側ポインタ不正であり、黙って成功させると lift 誤りを隠す)。許容モード `shimx_set_cs_null_ok(1)` を追加: Enter/Leave は no-op、TryEnter=FALSE、Initialize 何もしない、SleepConditionVariableCS=FALSE。null_ok モード自体も fail-fast モード (`node x.cjs csnull`) で検査 |
| R8 | 未検証 133 名の実機検証 | **手順整備** (実検証は unit 完走後) | `scripts/reach_check.py` (M11 `reach.json` の `static_reach_but_never_called` 133 名と実行トレースの差分集計) + `scripts/rem11_check.sh` (§9.2)。現時点の純リンク実行では 133 名の呼出 0 (起動経路は 17 unit まででレジストリ・ファイル系大半に未到達) — REPORT のとおり T9 (CAB-176) の unit 完走後の後続 |

### 9.2 「CAB-129 修正後、--fix なし純リンクで 17 unit 再測」の検証手順 (1 コマンド)

```
bash tools/shimx/scripts/rem11_check.sh
```

1. `tools/m11/shimx_link/build.sh --trace --soft` — **IR 無改変・--fix 一切無し** のトレース付き純リンク (signature mismatch 0 / undefined 0 / duplicate 0 を build ログで確認)
2. `run_trace.mjs` で起動実行 (`SHIMX_TRACE=1`) → `tools/shimx/work/rem11/m11_sx_trace_soft.run.json`
3. 判定基準 (M11 REPORT §0/§3-#2 の実測と対応):
   - **真の 17 unit 完走** = `init_count >= 18` (unit #18 に進入) かつ `longjmp_hit == 0` (unit #18 OOB で停止するのが期待値)
   - **偽の DllMain 完走** (CAB-129 未修正の現状) = `init_count == 17` かつ `longjmp_hit == 1` かつ `boot_rc == 1` — shadow stack 破壊による Halt0
   - **2026-10-10 実測 (CAB-129 未修正)**: `init_count=17, longjmp_hit=1, boot_rc=1, threw=null` = 偽の完走 (既知到達点どおり。shimx 呼出 17 種 / 27 回)。CAB-129 修正後に同コマンドを再実行し判定行が「真の 17 unit 完走」に変わることを確認する
4. 同スクリプトが `reach_check.py` で R8 進捗 (133 名のうち本実行で呼ばれた名) を `tools/shimx/work/rem11/reach_progress.md` に出力

前提: `bash tools/m11/m11_e2e.sh` 済みの M11 成果物 (`tools/m11/work/boot_final3.ll` 等)。`tools/m11/shimx_link/` の tracked ファイルは読取のみ (成果物は同 dir の work/ = gitignore)。

### 9.3 ir_undef.py 変更の M11 外部参照数への影響 (再計測)

| IR | 旧分類 (変更前実測) | 新分類 (本変更後) | 差分 |
|---|---|---|---|
| boot_final2.ll (557) | shimx 183 / lifter 203 / win_other 171 / unknown 0 | shimx **182** / **shimx_dup 1** (`SHGetFolderPathW.1`) / lifter 203 / win_other 171 / unknown 0 | shimx 183→182+dup1 (合計不変)。`NAME.1` が署名不一致の恐れがある別シンボルとして明示化され、`--emit-stubs` がスタブを吐く/`--normalize-dup` で正規化できるように |
| boot_final3.ll (570) | shimx 184 / lifter 214 / win_other 171 / unknown 1 (`SHGetFolderPathW_D1`) | shimx **184** / **shimx_dup 1** / lifter 214 / win_other 171 / unknown 0 | unknown 1→0 (同上の rename 後形式も同一扱い)。合計不変 |

外部参照総数 (557/570)・GUI 171・lift 由来は不変。`--emit-stubs` は `win_other + unknown + shimx_dup` を対象に変わったため、旧版で取りこぼしていた重複 declare 分のスタブが生成される (172 本 @boot_final3, 旧 171 本相当 + 1)。

### 9.4 CAB-166 `--fix` の取り込み状況

| --fix 構成要素 | 取り込み | 補足 |
|---|---|---|
| `cb_adapt.c` (列挙コールバック変換) | **置換完了 (CAB-177)** | R2 の `shimx_set_callback_translator` が恒常フック口。VA→トランポリン変換の実体は **`src/cbtrans.c` (§10)** として shimx 側に恒久実装し、link 側は `sx_cbboot.c` (constructor で invoke+translator+resolver を登録) だけになった。**tools/m11/shimx_link/cb_adapt.c は削除** (--wrap=Enum* も廃止)。M11 純リンクへの接続実測は §10 |
| `fix_alloca.py` (alloca 拡幅) | **意図的保留** | lift IR の縮退 alloca 修復で shim の担当外 (CAB-129 の本修正待ち)。`--emit-stubs`/`--normalize-dup` は IR を書くが構造体署名の正規化のみで alloca 構造には触れない |
| `sx_liftfix.c` (`_WStrClr` C 転記) | **部分取り込み (症状緩和)** | 論理修復 (2 段 deref) は lift 側のまま保留。ただし R5 の所有表により、誤ったポインタを `SysFreeString` に渡しても abort しなくなり、純リンク時の同症状は無害化される (次回 §9.2 の再測で確認) |

## 10. R2/R3 実体接続 — cbtrans (CAB-177 / SHX-T2 hostbridge 接続)

CAB-211 のフック口の**変換実体**を `src/cbtrans.c` として恒久実装し、M11 純リンク (CAB-129 ビルド) と
検証ハーネスへ接続した。**詳細 (設計/寿命契約/接続手順/実測/未対応・CAB-101 引継ぎ) は
`tools/hostbridge/cb/REPORT.md`** と `src/cbtrans.c` 冒頭コメント、往復検証は `test/test_cbtrans.c` (MT/ST)
+ `tools/hostbridge/cb/cb_e2e.sh` (MT 15 / ST 12 checks, exit 0)。

- **R2**: guest VA (≥intptr_limit) → 型付き slot トランポリン (6 形 × 64 slot) → **invoke 契約**
  `u64 invoke(u64 va, u64 a0..a7)` (= `m11_icall` 或いは `__icall_dispatch` 関数表+BLK 方式) で lift 側関数表へ。
  未知 va は 0 返し (closure 外でも trap しない)。`cb < intptr_limit` は実 C 関数ポインタの恒等通過 (M4 互換)。
  **寿命契約**: 翻訳は 7 API の登録時に 1 回 / slot は**プロセス寿命で解放しない** → 非同期系
  (CreateThread/FlsAlloc/タイマ/スレッドプール) も安全 (同一 VA = 常に同一トランポリン)。
- **R3**: shell32 IL* 10 本 + kernel32 UI言語 3 本を **lift ABI トークン** (0x7F000000+index) 化する
  `shimx_lifttab_*`。proc_resolver 接続で GetProcAddress がトークンを返し、lift dispatch 側は
  `shimx_lifttab_trampoline(token)` (u64×8 → 実 C 署名 thunk) で実体呼出 (M11 = `--wrap=m11_icall`)。
- **接続手順**: `shimx_cbtrans_set_invoke(<m11_icall 相当>)` → `shimx_cbtrans_install()` →
  `shimx_set_proc_resolver(shimx_lifttab_proc_resolver)`。実装例 = `tools/m11/shimx_link/sx_cbboot.c`。

**M11 純リンク実測**: init_count=18 / longjmp_hit=0 維持、threw が **"table index is out of bounds" →
"memory access out of bounds"** (CAB-231 既知 OOB に進行, 後退なし)。icall_ok/miss = 19/**1**。ビルド 5 variant
とも mismatch/undefined/duplicate **0**。survey 942 unit は **800/41/53 不変**。R3 の 13 名は survey で
**トークン解決** (GetProcAddress miss 消滅)。
