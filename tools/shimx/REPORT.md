# tools/shimx REPORT — Win32/CRT shim 拡張 (担当 Q)

> 正本: `tools/shimx/REPORT.md`。
> **行数**: 250 行以内 (`docs/DOC_MAP.md` §1)。超過分は Git 履歴に残る形で付録へ分割移動 (**内容は削除しない**)。
> 付録: SHX-T8 (#175) は `REPORT_SHX-T8.md` (§15)、SHX-T7 (#173) は `REPORT_SHX-T7.md` (§16)、R1〜R8・cbtrans (§9・§10) は `REPORT_R1-R8.md`、CAB-214 (§11・§12) は `REPORT_CAB-214.md` (いずれも分割移動)。

- 日付: 2026-10-10 (初版) / **2026-10-10 更新: CAB-211 — M11 リンク フィードバック R1〜R8 対応 (§9)** / **2026-10-10 更新: CAB-214 — vreg reg.c 本体取込 + username 統一 (§11)** / **2026-10-10 更新: CAB-214 follow-up — 後始末 3 件 (vreg 薄ラッパ化 / pathreg 予備 profile 退役 / winstubs wrap 5 API 退役, §12)** / 検証環境: emcc 6.0.12, node v24.19.0 (emsdk 同梱), llvm-nm
- 書込範囲: `tools/shimx/` のみ。`tools/shim` `tools/m2` `tools/m6` `tools/m8` `tools/m11` `tools/plugins` `tools/startup` `tools/targets` は読取のみ (改変 0 行)。
- 検収: `bash tools/shimx/test.sh` → **exit 0** (約 20 秒。`--quick` で OTT 再リンクを省略)

## 0. 結論

| 項目 | 実測 |
|---|---|
| shimx 公開 API | **610 本** (機能 444 + スタブ 166) + 運用フック 58 本 (`exports.txt` の 669 = これらに M4 互換 `shim_unimplemented` を加えた数)。実装 6,724 行 (C) + テスト アサーション 536 行 + R1〜R8 追加実装 (§9) + **R2/R3 実体接続 `src/cbtrans.c` (§10, CAB-177)** + **vreg reg.c 取込 11 シンボル (§11, CAB-214)** |
| FLEngine_x64.dll 静的 import **738** に対するカバレッジ | 実装 **358 = 48.5%** (機能 243 + スタブ 115)。libc 解決 `memset` 込み 48.6% |
| 担当範囲 (738 − 他担当 379 = 359) に対するカバレッジ | **100.0%** (未実装 **0**、序数 import 0)。内訳 = 実装 358 + libc 解決 `memset` 1。対象外 379 = user32/gdi32/comctl32/opengl32 (tools/gui) 377 + dsound (tools/audio) 2。実装 358 のうち 9 本は user32 の weak 実装 (Char*W/MsgWaitForMultipleObjects*; gui 側が強定義で上書き可)。**100% は「シンボル提供」の意味**で、うち 115 本はスタブ (常時エラー/0 台/fail-fast の `RtlUnwind*` 等)。機能実装は 243 本 |
| 呼出サイト加重 (静的 7,309 サイト) | shimx 4,050 サイト (55.4%) / 他担当 (GUI) 3,252 サイト (44.5%) / libc 7 |
| delay-load 57 | 実装 23 / 他担当 34 / 未実装 0 |
| プラグイン import (GUI/audio 除く) | OTT vst2 **147/147**, vst3 **151/151**, FreshAir 98/98, FL64.exe 111/111, Serum2 **238/238** (SHX-T8 #175 で達成 → `REPORT_SHX-T8.md` §15。分母 = `data/coverage.json` の `in_scope`) |
| **OTT undefined 47 種 (M8)** | shimx リンクで **47 → 23**。Win/CRT API **24 種は全て解決** (CloseHandle/CreateFileW/TlsGet・SetValue/WriteFile/GetProcAddress/LoadLibraryExW/`__readgsqword`/Rtl*/UnhandledExceptionFilter ほか)。残 23 は `function_18*` = lift 欠落で shim の対象外。t1 出力 SHA は baseline と bit 一致 (`b5a91b9b…`, 512 行)。signature mismatch 0 |
| M11 init closure (`boot_final2.ll`) 外部参照 557 | shimx 提供 **182** + shimx 重複 declare (`SHGetFolderPathW.1` = R6 の shimx_dup 分類) **1** / GUI・audio 担当 171 (user32 114 / gdi32 53 / shcore 2 / uxtheme 1 / dsound 1) / lift 由来 203。**非 GUI の Win/CRT は 100% 提供**、IR declare と wasm 署名の不一致 0 (後述 §4 の 5 件を修正済み) |
| **R2/R3 実体接続 (§10, CAB-177)** | `shimx_set_callback_translator` の**変換実体** `src/cbtrans.c` (VA→slot トランポリン→lift 側関数表) + R3 `shimx_lifttab_*` (IL* 10 本 + kernel32 UI言語 3 本を lift ABI トークン化)。M11 純リンクに接続済み: unit 18 の `EnumCalendarInfoW(0x4476d0)` が trampoline 経由で実呼出され **"table index is out of bounds" trap が消滅** (init_count 18・mismatch/undefined 0・survey 800/41/53 不変)。検証: `test/test_cbtrans.c` (MT/ST) + `tools/hostbridge/cb/cb_e2e.sh` (MT 15/ST 12 checks) |
| M4 の 53 API | **53/53 継承**。`tools/shim/test/test_main.c` を **無改変** で shimx 実装に対し MT/ST とも ALL PASS |
| テスト | MT(pthread) ALL PASS / ST ALL PASS / fail-fast 8 モード / M4 互換 MT・ST / 署名突合 3 本 (boot_final2・3 / OTT) / OTT 再リンク+実行回帰 / **R1〜R8 対応分 `test/test_link.c` (MT/ST)** / **R2・R3 実体接続分 `test/test_cbtrans.c` (MT/ST, §10)** / R6 検査 (構造体展開 + 正規化 IR の emcc 通過) / **vreg reg.c 取込分 §11 (vreg.sh + keyfix_e2e.sh + pathreg e2e + winstubs/gui 共存)** |

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
- **SEH**: 実巻き戻しランタイムは §14 (#171) で実装済み。ただし lift 側が `ShxSehFrame` を登録しない限り従来どおり fail-fast。lift 側の接続は未了 (§14.3)。
- **ブロッキング待ち**: 実装は futex。ブラウザのメインスレッドでは Atomics.wait 不可 → エンジンは Worker で動かす前提 (M4 同様)。ST ビルドの INFINITE 待ちは fail-fast。
- **コードページ**: 既定 ACP=1252。**932 (Shift-JIS) は SHX-T8 (#175) で対応 (`REPORT_SHX-T8.md` §15)**。936/949/950 等の他 DBCS は ERROR_INVALID_PARAMETER。ロケールデータは en-US 固定。
- **FileMapping**: マッピング毎の共有バッファ (書戻しは Unmap/Flush/Close)。別プロセスとの共有や巨大ファイルの遅延マップは不可。VirtualAlloc 予約は malloc (上限 512MB/回)。
- **GlobalUnlock** は M4 互換 (ロック済みなら TRUE)。HeapDestroy は配下ブロックを回収しない。SuspendThread は実停止しない。
- 序数 import: shell32 74 / 155 / 190・shlwapi 12 / 219 は同定・実装済み (R3 §9.1 + SHX-T8 `REPORT_SHX-T8.md` §15)。**d2d1 ord1 のみ未同定** (d2d1 は tools/gui 担当帯で本チケット範囲外 → `REPORT_SHX-T8.md` §15.5)。advapi32 Crypt* は MD5/SHA-1/SHA-256 を実装 (同 §15)。
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
| T4 | SEH 実巻き戻し | shimx 側ランタイムは §14 で完了 (#171)。残 = lift 側が .pdata/UHANDLER の scope table と try 関数を `ShxSehFrame` 登録形へ出力 (§14.3) | lift |
| T5 | GUI 側連携 | ShellExecute→`window.open`、GetOpen/SaveFileName→File System Access、Drag&Drop (`shimx_get_drop_target`)、user32 の Char*/MsgWait* は weak なので gui 側の強定義で置換可 (**#172 で実施**: `tools/gui/shimx_coexist/REPORT.md`) | gui |
| T6 | MIDI/タイマ | winmm `midi*` (weak, 0 台) を Web MIDI で強定義、`timeBeginPeriod` と AudioWorklet クロックの整合 | audio |
| T7 | 署名正規化 | RetDec の i64/ptr 揺れを吸収する IR パス (declare を shimx 署名へ正規化) または CI で `verify_sig.sh` を常時実行 | lift |
| T8 | 序数 import と追加 API | shell32 74/155/190・shlwapi 12/219 の同定、Crypt ハッシュ (Serum2)、CP932 テーブル (日本語 ACP) | plugins / shim — **実施済み (#175, `REPORT_SHX-T8.md` §15)** |
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

- 独立再計算 (pefile で `[WIN64]` の `extracted/block00031_PE.bin` を直接解析; 呼出サイトは E8/E9 rel32 を独自走査) で主要数値は一致。差異は M11 外部参照 553→557 (ir_undef の declare 正規表現が struct 戻り値 `__asm_cpuid*` 4 件を取りこぼし。lift 由来のみ・shimx/GUI 件数に影響なし) の 1 件のみで修正済み。

## 9. M11 リンク フィードバック対応 — R1〜R8 (CAB-211) / 10. R2/R3 実体接続 — cbtrans (CAB-177)

本文・測定値は付録 **`tools/shimx/REPORT_R1-R8.md`** (§9.1〜9.4・§10) に分割移動した (行数上限対応、内容は無変更)。以降の § 参照 (§9.x / §10) は同ファイルを指す。

- **結論 (R1〜R8)**: M11 リンク フィードバック 8 項目に対応 (R1 intptr 閾値 / R2 コールバック変換フック / R3 GetProcAddress 表追加 / R4 擬似 LoadLibrary / R5 BSTR 所有表 / R6 ir_undef 構造体展開・重複 declare 正規化 / R7 CS NULL 方針 / R8 検証手順整備)。既存検収は全て維持。
- **結論 (§10)**: `src/cbtrans.c` で R2/R3 の変換実体を接続し、M11 純リンクの "table index is out of bounds" trap が消滅 (init_count 18, mismatch/undefined/duplicate 0)。
- 再現: `bash tools/shimx/scripts/rem11_check.sh` (§9.2)・`bash tools/hostbridge/cb/cb_e2e.sh` (§10)。

## 11. vreg reg.c 本体取込 + username 統一 (CAB-214, SHX-T10) / 12. CAB-214 follow-up 後始末 3 件

本文・測定値は付録 **`tools/shimx/REPORT_CAB-214.md`** (§11.1〜11.7・§12.1〜12.4) に分割移動した (行数上限対応、内容は無変更)。以降の § 参照 (§11.x / §12.x) は同ファイルを指す。

- **結論 (§11)**: vreg `reg.c` の拡張を `src/reg.c` に取込 (公開シンボル 39→50, 欠落 0)。username を `C:\Users\webstudio` に統一。
- **結論 (§12)**: vreg 薄ラッパ化・pathreg 予備 profile `user2Profile` 退役・winstubs wrap 5 API 退役を全て実施。回帰は全て exit 0。

## 13. WinInet 常時オフライン化 (#111, ST-T4)

**結論**: wininet は #111 以前から `net.c` に fail-soft のオフライン実装があった (InternetOpenW/A=NULL, InternetGetConnectedState=FALSE, WSAStartup=10091)。差分だけ埋めた: 接続系の `GetLastError` を 12029 から stub_plan §5 C の **12163 (ERROR_INTERNET_DISCONNECTED)** に統一、未実装だった `HttpSendRequestW/A`・`InternetCheckConnectionW/A` を追加、接続系の呼出回数 `shimx_wininet_call_count()` を追加 (成功を返す経路は無いので boot 中の成功呼出は 0 回。起動検査はこのカウンタで差し引きできる)。

| 検証 | 結果 (2026-10-13 実測, Actions runner) |
|---|---|
| `bash tools/shimx/test.sh` | **exit 0**, 22 s: MT 5 グループ / ST PASS / fail-fast 8 / M4 互換 PASS / 未実装 0。`test_sys.c` に接続系 10 呼出が全て 12163 + 失敗値 / カウンタ +10 の検査を追加 |

- `verify_ott` と M11 closure の突合は `work-m11` / `work-m6-ott` 素材が無く SKIP。このため `test.sh` が再生成した inventory.md / BACKLOG.md / coverage.json / inventory.csv は m11 closure が空になるので**コミットしていない** (次回素材付き run で再生成)。`exports.txt` と `proctable.c` は差分 5 行のみ反映。
- `shimx_wininet_call_count` 以外の公開面変更は `shimx.h` の 4 宣言のみ。

## 14. SEH 実巻き戻しランタイム (#171, SHX-T4)

既知類型との関係 (DEFECTS.md): 該当なし (shim ランタイムの追加。lift/IR には触れない)。検証起点 = `origin/main` 80c7471。

### 14.1 結論

`RaiseException` / `RtlUnwind` / `RtlUnwindEx` の fail-fast を、**lift 側が登録した SEH frame がある場合に限り**実巻き戻しへ置換した (`src/seh.c`, 公開面は `shimx.h` の `ShxSehFrame` と `shimx_seh_*` 7 関数)。
frame が 1 つも無い場合・捕捉 scope が無い場合・`RtlUnwindEx` の targetFrame に一致する frame が無い場合は従来どおり fail-fast (名前を出して非 0 終了)。
**受入条件のうち「lift が UHANDLER 8,021 件を frame 登録形へ出力する」は未達** (lift 出力形式は #12 未確定。§14.3)。このため #171 は Closes ではなく Refs。

### 14.2 設計 (tools/icall/landing/REPORT.md §2/§6 の実測仕様に準拠)

- frame 鎖はスレッド毎 (`_Thread_local`)。`ShxSehFrame` = {establisher frame 識別子, scope table (`count + {begin,end,kind,target}` の RVA 4 組), 現在 pc (RVA), `jmp_buf`}。lift 側は try 関数入口で `shimx_seh_enter` + `setjmp(f.jb)`、call 前に `f.pc` を更新、出口で `shimx_seh_leave`。
- `RaiseException` の順序: raise hook → VEH → **frame 鎖 2 相** → UEF → fail-fast。
  - 検索相 (内側→外側): kind==2 (catch-all) で pc が範囲内なら捕捉。kind>2 は `shimx_seh_set_typed_matcher` (VMT 照合は lift 側) に委譲。
  - unwind 相: 捕捉 frame より内側を内側から外し、kind 0/1 scope に pc があれば `pad(&{rec,ctx}, frame)` を実行 (`ExceptionFlags` に EXCEPTION_UNWINDING)。その後 `longjmp(target->jb)`。再開先 RVA は `resume_ip`。pad 実行中は当該 frame を鎖から外すため、pad 内の再送出は外側 frame のみを見る。
- `RtlUnwind(Ex)`: targetFrame に一致する frame まで同様に巻き戻し、`resume_ip=targetIp` / `resume_ret=retval` で longjmp。targetFrame==NULL は全 frame の pad を実行して復帰 (EXIT_UNWIND)。
- pad の実体は `shimx_seh_set_pad_resolver` (scope target RVA → 関数) で解決。未設定/未解決は fail-fast。

### 14.3 範囲外・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| lift が try 関数を `ShxSehFrame` 登録形で出力する側 (.pdata UHANDLER 8,021 → scope table, pc 更新, setjmp) | 実バイナリでの巻き戻しは未到達。単体テスト (合成 scope) のみ | #12 (FLEngine 本番 lifting) の出力形式確定後に子チケット。ICALL-2c (tools/icall/landing §9) と統合 |
| typed except の VMT 照合 (0x4111d0 相当) | `shimx_seh_set_typed_matcher` は口のみ | 同上 |
| wasm ABI: `jmp_buf` 越しの longjmp は emscripten の SjLj (`-sSUPPORT_LONGJMP` 既定の emscripten 方式) に依存。wasm EH (exnref) 形は未検討 | lift 側が別方式を選ぶ場合は差替え | #12 / landing REPORT §6 |
| スレッド跨ぎ・非同期例外 (ハード例外 AV 等) は対象外 | 構造化例外のうち RaiseException 経由のみ | 新規起票なし (下流で必要になった時点) |
| 実機 FLEngine での通し実行 (RaiseException → pad 進入) | 未検証 | ICALL-2c |

### 14.4 検証 (2026-10-13, Actions runner, 起点 80c7471 + 本変更)

| 検証 | 結果 |
|---|---|
| `bash tools/shimx/test.sh --quick` (変更前) | exit 0, 22 s, load 0.45 (1 分値) |
| 同 (変更後) | exit 0, 22 s, load 0.42。MT 6 グループ (新規 `seh`: catch-all / 入れ子 pad 順序 + frame 引数 + UNWINDING / typed / RtlUnwindEx+RtlUnwind(NULL) / leave 冪等) / ST PASS / M4 互換 PASS / 公開関数 674→680 |
| fail-fast | 既存 `raise` `rtlunwind` に加え `sehnomatch` (frame あり捕捉 scope なし) `sehbadtarget` (targetFrame 不一致) を追加、いずれも exit=1 + 名前出力 |
| クリーン HEAD 再現 (4a61103 を detached worktree に展開) | exit 0, 21 s, load 0.76 (1 分値), `seh OK` 出力 1 件 |
| ネガティブコントロール | unwind 相の `pad()` 呼出を無効化 → `test_seh.c:73: g_pad_n == 2` で FAIL (MT テスト失敗, exit 1)。復元後 PASS |

`--quick` は `verify_ott` を省略 (m11/m8 の work 素材なし、署名突合 6b も素材なしで SKIP)。`inventory.md` / `BACKLOG.md` / `data/*` / `exports.txt` は m11 closure 無しで再生成すると壊れるため**コミットしていない** (§13 と同方針)。`gen_inventory.py` は `RtlUnwind*` を fail-fast 扱いから外したので、次回素材付き run の再生成で BACKLOG の該当行 (P1 `RtlUnwindEx` / `RtlUnwind`) が更新される。

## 15. SHX-T8 (#175): 序数 import の同定・Crypt ハッシュ・CP932

本文・測定値は付録 **`tools/shimx/REPORT_SHX-T8.md`** (§15.1〜15.5) に分割移動した (行数上限対応、内容は無変更)。以降の § 参照 (§15.x) は同ファイルを指す。

## 16. 署名正規化 IR pass + ゲート (#173, SHX-T7)

結論: 案A (IR pass `sig_normalize.py`) + 案B (ゲート `sig_gate.sh`) で、lift IR の declare 署名の揺れを shimx 定義署名へ正規化し、mismatch 0 を強制する。方式・検証・実 IR 実測は付録 **`tools/shimx/REPORT_SHX-T7.md`** (§16) に分割移動した (行数上限対応、内容は無変更)。以降の § 参照 (§16) は同ファイルを指す。

## 17. 不在パスのエラーコード・en-US UI 言語の検証 (#658, ST-T19)

- 検証対象: `tools/shimx/test/test_absent.c` (不在パスの `GetFileAttributesW` / `FindFirstFileW` / `FindFirstFileExW` が `INVALID_FILE_ATTRIBUTES` / `INVALID_HANDLE_VALUE` と `GetLastError` 2 (FILE_NOT_FOUND) または 3 (PATH_NOT_FOUND) を返すこと。実在パスは属性・cFileName を返すこと = ネガコン) と `test_sys.c` `test_ui_language` (`GetUserPreferredUILanguages` が en-US)。
- 写像は `pathreg` (`tools/shimx/pathreg`) 経由。`C:\Users\webstudio\...` → `/c/home/...`、`C:\Program Files\Image-Line\FL Studio 2026\...` → `/fl/...`。
- 実行環境: `toolchain-emsdk` 6.0.12 (`/opt/emsdk` に展開)・node v22.23.3・Actions runner (4 vCPU)。コミット `b834c83` の HEAD。

### 17.1 実測 (`bash tools/shimx/test.sh`、HEAD `b834c83`)

| run | 所要 (秒) | load1 (開始 → 終了) | MT ALL PASS | ST ALL PASS | absent MT/ST | M4 互換 |
|---|---|---|---|---|---|---|
| 1 | 16.35 | 0.45 → 0.69 | ✓ | ✓ | OK / OK | ✓ |
| 2 | 16.45 | 0.69 → 1.72 | ✓ | ✓ | OK / OK | ✓ |
| 3 | 16.53 | 1.72 → 1.56 | ✓ | ✓ | OK / OK | ✓ |

fail-fast 9 種 + ExitProcess(7) = 全 PASS、exit 0 ×3。`test.sh` は実行の副産物として `exports.txt` / `inventory.md` / `BACKLOG.md` / `data/*` を書き換えるが、m8/m11 素材なしでは closure が欠けるため**コミットしていない** (§13 と同方針。`git restore` で HEAD に戻した)。

### 17.2 ネガティブコントロール

`test_absent.c` の不在パス 1 件 (`C:\Users\webstudio\Languages\en.moe`) の期待エラーを `ERROR_FILE_NOT_FOUND` → `ERROR_PATH_NOT_FOUND` に書き換えて `test.sh` を実行 → **exit 1**、出力:

```
[absent-path] C:\Users\webstudio\Languages\en.moe: GetFileAttributesW attr=ffffffff err=2 / FindFirstFileW h=0xffffffff err=2 / FindFirstFileExW h=0xffffffff err=2 (want err=3)
[shimx-test] FAIL .../test_absent.c:39: a == INVALID_FILE_ATTRIBUTES && e1 == wantErr
```

書換えを戻した後 `test_absent.c` は HEAD と一致 (`cmp` で確認)。ネガコンが検出できることを確認した。

### 17.3 関連ハーネスの修正 (#658 差し戻し)

`test_absent.c` / `pathmap.c` が `pathreg` に依存したため、ワイルドカードで `test/*.c` を取り込んでいた 3 ハーネスが include・link で壊れていた。`-Isrc -Ipathreg/include` と `pathreg/src/pathmap.c` を足して修正:

- `tools/shimx/scripts/quick_test.sh` (MT ビルド + 実行)
- `tools/startup/vreg/build.sh shimx` (`shimx` 既存テスト一式): 実行 rc=0・ALL PASS (実測 8 秒)
- `tools/startup/winstubs/winstubs.sh` (8/8 完了): rc=0 (実測 10 秒)。`--wrap` 下の shimx 回帰で ST/MT とも ALL PASS

`quick_test.sh` は `test.sh --quick` でも ST/MT の absent-path OK を確認。
