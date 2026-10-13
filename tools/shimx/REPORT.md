# tools/shimx REPORT — Win32/CRT shim 拡張 (担当 Q)

> 正本: `tools/shimx/REPORT.md`。
> **行数目安**: 本ファイルは 250 行を超過 (`docs/DOC_MAP.md` §1 の上限ルール参照)。
> 超過分は Git 履歴に残る形での分割移動を推奨 (**内容は削除しない**)。

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
| プラグイン import (GUI/audio 除く) | OTT vst2 **147/147**, vst3 **151/151**, FreshAir 98/98, FL64.exe 111/111, Serum2 **238/238** (SHX-T8 #175 で達成 → §15。分母 = `data/coverage.json` の `in_scope`) |
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
- **コードページ**: 既定 ACP=1252。**932 (Shift-JIS) は SHX-T8 (#175) で対応 (§15)**。936/949/950 等の他 DBCS は ERROR_INVALID_PARAMETER。ロケールデータは en-US 固定。
- **FileMapping**: マッピング毎の共有バッファ (書戻しは Unmap/Flush/Close)。別プロセスとの共有や巨大ファイルの遅延マップは不可。VirtualAlloc 予約は malloc (上限 512MB/回)。
- **GlobalUnlock** は M4 互換 (ロック済みなら TRUE)。HeapDestroy は配下ブロックを回収しない。SuspendThread は実停止しない。
- 序数 import: shell32 74 / 155 / 190・shlwapi 12 / 219 は同定・実装済み (R3 §9.1 + SHX-T8 §15)。**d2d1 ord1 のみ未同定** (d2d1 は tools/gui 担当帯で本チケット範囲外 → §15.5)。advapi32 Crypt* は MD5/SHA-1/SHA-256 を実装 (§15)。
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
| T5 | GUI 側連携 | ShellExecute→`window.open`、GetOpen/SaveFileName→File System Access、Drag&Drop (`shimx_get_drop_target`)、user32 の Char*/MsgWait* は weak なので gui 側の強定義で置換可 | gui |
| T6 | MIDI/タイマ | winmm `midi*` (weak, 0 台) を Web MIDI で強定義、`timeBeginPeriod` と AudioWorklet クロックの整合 | audio |
| T7 | 署名正規化 | RetDec の i64/ptr 揺れを吸収する IR パス (declare を shimx 署名へ正規化) または CI で `verify_sig.sh` を常時実行 | lift |
| T8 | 序数 import と追加 API | shell32 74/155/190・shlwapi 12/219 の同定、Crypt ハッシュ (Serum2)、CP932 テーブル (日本語 ACP) | plugins / shim — **実施済み (#175, §15)** |
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

### 9.2 「CAB-129 修正後、--fix なし純リンクで 17 unit 再測」の再現手順 (1 コマンド)

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

## 11. vreg reg.c 本体取込 + username 統一 (CAB-214, SHX-T10)

**結論**: `tools/startup/vreg/src/reg.c` (828 行, CAB-94/a5b44fe) の拡張全てを `src/reg.c` に取込した
(686→829 行, 公開シンボル **39→50**, 欠落 0 — 旧 39 シンボルは全て継承)。以後の改良は shimx 側が正本。
vreg 側との二重管理は解消 (vreg `build.sh symcheck`: shimx 50 シンボルを vreg reg.c が全包含 / **追加 0** =
両者はシンボル集合として同一)。username も CAB-213 の正規表記 `C:\Users\webstudio` に統一した。

### 11.1 取込差分 (vreg REPORT §2 の 4 項目 + 追加 6 API → 全て実装)

| # | 取込内容 | 実装 | shimx での改善点 |
|---|---|---|---|
| 1 | 変更世代 `vreg_generation()` + 通知 `vreg_set_notify(cb)` (set/delete/create で世代+1, **ロック解放後に呼出スレッドで同期通知**) | `reg_unlock()` / `touched()` (全 22 unlock site を経由) | 永続化トリガ (vreg JS の dirty→遅延 flush) が shimx 単体で利用可 |
| 2 | `RegEnum*` の `ERROR_MORE_DATA` で必要長を返す | `put_name()`: `*cch = n` を設定して返す | Delphi TRegistry 流の 2 段呼出 (長さ問合せ→再取得) が通る |
| 3 | import 拡張: UTF-8 BOM / `[-HKEY_..]` (サブツリー削除) / `"v"=-` / `@=-` | `shimx_reg_import_text()` | `.reg` 往復が vreg seed (236 エントリ) と同一経路に |
| 4 | `vreg_export_root(i)` / `vreg_clear_root(i)` / `vreg_clear_all()` | `export_key`/`clear_root_locked` を共用 (`shimx_reg_reset` も `clear_root_locked` に統合) | ルート単位 export/clear が shimx 公開面に |
| 5 | 追加 6 API: `RegGetValueA` `RegEnumKeyW` `RegDeleteTreeW` `RegSetKeyValueW` `RegDeleteKeyValueW` `RegQueryInfoKeyA` | `src/reg.c` + `shimx.h` 宣言 | **`proctable.c` にも自動登録** (advapi32, 532→538 エントリ) — vreg では未登録だった (vreg REPORT §7「必要になれば proctable 生成の対象に追加」を本取込で解消) |
| 6 | ヘルパ整理: `free_vals` / `mark_deleted` / `unlink_key` / `type_flags_ok` | vreg 版を verbatim 取用 | 重複コード削減 (`shimx_reg_reset` と `vreg_clear_*` の共通化) |

**exports.txt 差分 (+11)**: `RegDeleteKeyValueW` `RegDeleteTreeW` `RegEnumKeyW` `RegGetValueA` `RegQueryInfoKeyA` `RegSetKeyValueW` `vreg_clear_all` `vreg_clear_root` `vreg_export_root` `vreg_generation` `vreg_set_notify`。
運用フックは `shimx_*` 53 + `vreg_*` 5 = **58 本** (`gen_inventory.py` と `gen_proctable.py` に `vreg_` 接頭辞分類を追加 — proctable の GetProcAddress 組込み表には載せない。名前は vreg JS 側 `EXPORTED_FUNCTIONS` (`_vreg_generation` 等) との互換のため **`vreg_` 接頭辞を維持**)。

### 11.2 username 統一 (`C:\Users\user` → `C:\Users\webstudio`)

CAB-213 §3 の正規表記へ shimx 内蔵値を統一 (pathreg の alias mount 吸収は不要になる方向。**実効挙動は表記変更のみ**)。

| ファイル | 箇所 | 変更 |
|---|---|---|
| `src/env.c` | env 既定表: `USERPROFILE` `HOMEPATH` `APPDATA` `LOCALAPPDATA` `TEMP` `TMP` (6 パス) + `USERNAME` | `...\Users\user...` → `...\Users\webstudio...` / `USERNAME=user` → `webstudio` |
| `src/file.c` | `GetTempPathW/A` の既定 Temp (2 箇所) | 同上 |
| `src/shell.c` | `csidl_path()` 13 箇所 + KnownFolder GUID 表 6 箇所 (SHGetFolderPathW/SHGetKnownFolderPath/SHGetSpecialFolderPathW が返すパス) | 同上 (`C:\Users\Public` 系は不変) |
| `test/test_sys.c` | `PathUnExpandEnvStringsW` 入力 / `GetTempPathW` 期待値 (2 箇所) | 期待値を新正規表記に更新 |
| `test/test_ole_shell.c` | `SHGetFolderPathW`/`SHGetKnownFolderPath`/`SHGetSpecialFolderLocation` 期待値 (3 箇所) | 同上 |

**触っていないもの**: `tools/shimx/pathreg/` 全体 (V18 検収が読み中のため読取のみ) / `src/reg.c` の seed 内 `RegisteredOwner="user"` (Windows の登録所有者名でユーザ profile 路線でない。vreg seed 236 エントリにも含まれず影響 0)。

### 11.3 vreg 側の薄ラッパ化 / 退役方針 (別作業用 — 本チケットでは vreg 無改変) — **→ 実施済み (§12.1)**

vreg (`tools/startup/vreg/`) は **1 行も変更していない** (vreg.sh 再実行で data/seed.json 等バイト不変を実測済)。
現状の vreg `build.sh` は shimx `src/*.c` から `reg.c` を除外して自前 `src/reg.c` をリンクしているが、
取込後は**両者のシンボル集合が完全一致**したため、下記の退役が可能 (vreg 担当 or CAB-11 後続で実施):

1. `vreg/build.sh` の `SRCS` 除外工作 (12 行目の `[ reg.c ] || ...`) を削除 — shimx `reg.c` をそのまま使う
2. `VSRC` から `src/reg.c` を外す (`probe.c` はテスト/e2e 専用ヘルパとして継続)
3. `vreg/src/reg.c` を削除 (参照実装が shimx に一本化)。JS 側 (`js/vreg.mjs` 等) は `_vreg_generation` 等
   の名前が shimx 側でも不変のため **無変更で動作する**
4. 退役後も `build.sh symcheck` は「自前 vs shimx」の退化検査として残せる (追加 0 を維持)

### 11.4 pathreg 予備 profile (`user2Profile`) の退役手順 (別タスク用) — **→ 実施済み (§12.2)**

username 統一により shimx は `C:\Users\user` を**発行しなくなった**ため、pathreg 既定表の
`user2Profile = "C:\Users\user"` (pathmap.c 164 行, 予備 mount 4 本) は冗長。退役は pathreg 担当作業:

1. `src/pathmap.c` の `pathreg_paths_init` から `user2Profile` 設定と 197-198 行の条件追加 mount を削除
2. `test/e2e.mjs` の B グループ等、`C:\Users\user` 表記を使っている fixture があれば `webstudio` 表記へ
3. **`pathreg_unmap` の同長 tie-break (先勝ち)** は webstudio のみの mount になっても結果不変 (既に正規が先頭)
4. 削除後の検収: `bash tools/shimx/pathreg/scripts/e2e.sh` (6 groups) + `verify_consistency.py` の
   username 整合チェック (「+予備 user」の文言も更新)

### 11.5 検証実績 (全て 2026-10-10 実測)

| 検証 | 結果 |
|---|---|
| `bash tools/shimx/test.sh` | **exit 0**: MT PASS / ST PASS / fail-fast 8 モード / M4 互換 MT・ST (53/53) / 署名突合 3 IR (m11, m11_3, ott) mismatch **0** / OTT t1 SHA **b5a91b9b2ee8da1e 不変** (512 行) / 未実装 0 (担当範囲 100.0%) |
| シンボル突合 (llvm-nm) | 旧 shimx reg.c 39 → 新 50 (**+11**, 欠落 0)。`vreg build.sh symcheck` = shimx 50 シンボルを vreg reg.c が全包含 (**追加 0** = 同一集合) |
| `bash tools/startup/vreg/vreg.sh` | **ALL OK** (6/6 step: seed 再生成バイト不変 / C 単体 / shimx 結合 MT+ST+M4 / symcheck / wasm / node 22/22 / Chrome 実 IndexedDB PASS)。vreg dir の git 差分 **0** |
| `bash tools/startup/keyfix/keyfix_e2e.sh` | **ALL PASS** (entries=236 / apply=81 / key確定=113 / key=null=3 不変, `verify_consistency.py` 6 項目 PASS — username 整合含む) |
| `bash tools/shimx/pathreg/scripts/e2e.sh` | **ALL PASS** (C 単体 ST/MT + JS 4/4 + e2e 6 groups。module-b = **shimx reg.c のまま**の構成で新 reg.c を実行して無劣化) |
| winstubs/gui リンク共存 | `coexist_gui.sh`: 重複シンボル = **既知記録 1 件のみ** (`WTSRegisterSessionNotification`, shimx weak × gui 強定義の既存分)。winstubs 由来の重複 **0**。`verify_sig_ir.sh`: mismatch 0 + 陰性対照 1 検出。winstubs wrap 層経由の shimx 単体テスト ST/MT **ALL PASS** |

### 11.6 winstubs への影響 (後続タスク) — **→ 実施済み (§12.3)**

username 統一により、winstubs (CAB-96) が wrap していた **5 API が shimx 単体で期待値一致**になった
(`winstubs.sh` step 4 の「差分実装は不要」検査が FAIL 5 件: `SHGetFolderPathW` `SHGetSpecialFolderPathW`
`SHGetKnownFolderPath` `GetTempPathW` `ExpandEnvironmentStringsW` — shimx 単体ですでに全行 MATCH)。
これは wrap 層の退役機会であり、winstubs 担当が `wrap_list.txt` / api_matrix の impl 分類を更新すれば解消する
(winstubs は本チケットでは無改変。`data/diff_table.tsv` は検収スクリプトが毎回再生成する実測表ゆえ触らず)。

### 11.7 CAB-101 (実 FL 結線) への影響

1. **正の影響**: engine が env/SHGetFolderPath で受ける username 表記が seed (vreg 236 エントリ) と
   完全一致 (`webstudio`) になった → CAB-213 で吸収していた「user 表記と webstudio 表記の併存」が解消され、
   `SHIMX_TRACE` のパス観測が seed 期待値と直接突合できる。pathreg の alias mount 経由の解釈が不要に。
2. **レジストリ**: `Reg*` は shimx 正本 1 本に。CAB-101 の open ログ観測では vreg と shimx の差違を気にする
   必要がなくなり、`vreg_generation()`/`vreg_set_notify()` で Reg 呼出トレース拡張が shimx 直結で可能
   (vreg REPORT §10 の提案がそのまま shimx で実施可)。
3. **追加 6 API が GetProcAddress 組込み表に載った** (advapi32 532→538) — lift 側が動的解決しても解決する。

## 12. CAB-214 follow-up: 後始末 3 件 (§11.3 / §11.4 / §11.6) — 全て実施

**結論**: 3 件とも REPORT §11 の手順どおり実施し、回帰は全て exit 0 (§12.4)。shimx 本体 (`src/*.c`) は**コメント 1 箇所以外無変更** (挙動不変)。
退役の本質は「同名シンボル同時リンク不可」の正式解消 (vreg) と「username 差の吸収層」の撤去 (pathreg alias mount / winstubs wrap) で、いずれも §11.2 の統一で不要になったもの。

### 12.1 vreg 薄ラッパ化 (§11.3 の 4 手順)

| 手順 | 実施 |
|---|---|
| 1. `SRCS` 除外工作の削除 | `vreg/build.sh`: `SRCS=("$SHIMX"/src/*.c)` (reg.c 含む) |
| 2. `VSRC` から reg.c を外す | `VSRC=("$HERE/src/probe.c")` (probe.c はテスト/e2e 専用ヘルパとして継続) |
| 3. `vreg/src/reg.c` 削除 | `git rm` (828 行)。JS (`js/*.mjs`) は**無変更**で動作 (`vreg_generation` 等の名前不変)。`src/vreg.h` は probe 宣言のみに縮小 (運用フック/追加 6 API の宣言は shimx.h に既存) |
| 4. `symcheck` の継続 | 手順どおり「自前 vs shimx」比較は自前が無くなるため成立しない → **判断**: 「vreg が要求する公開面 (shimx.h 宣言の `Reg[A-Z]*` 全て + module の EXPORTED `vreg_*`/`shimx_reg_*`) を shimx reg.c が定義している」検査に差し替え (実測: 要求 38 シンボル / reg.c 公開 50 / 不足 0) |

**手順書に無かった波及 (判断)**: `pathreg/scripts/build.sh module-a` が `vreg/src/reg.c` をリンクしていたため同時に修正 — shimx 全 src + `vreg/src/probe.c` + pathreg に変更
(module-a = `vreg_*` フック export + probe 同梱の本番構成 / module-b = フック非 export の代替構成、として両方存続。regbridge の自動判別 (`_vreg_export_root` の有無) は不変)。

### 12.2 pathreg 予備 profile `user2Profile` 退役 (§11.4 の 4 手順)

| 手順 | 実施 |
|---|---|
| 1. `pathmap.c` | `pathreg_paths_init` の `user2Profile` 設定 + `pathreg_set_paths` の条件追加 mount を削除。構造体 `PathRegPaths.user2Profile` (pathreg.h) と JS ミラー (`js/pathmap.mjs` DEFAULT_PATHS + 2 profile ループ) も削除。既定表 **14→8 本** (install 1 + webstudio×6 + `C:` 1) |
| 2. fixture の webstudio 化 | `test_pathreg.c` / `pathmap.test.mjs` / `e2e.mjs` の `C:\Users\user` → `webstudio`。**追加 (判断)**: 表件数 8 の厳密化 (旧 `>= 9`)、退役 alias `C:\Users\user\...` が残余 `C:` 規則 (`/c/Users/user/...`) に落ちる陰性確認を C / JS / e2e クロスチェック (fixture 15→16) に追加 |
| 3. `pathreg_unmap` tie-break | コード無変更 (webstudio のみになり結果不変。e2e C グループの逆写像一致で確認) |
| 4. 検収 + `verify_consistency.py` | `keyfix/verify_consistency.py`: 「+予備 user」文言と `user2Profile = "...user"` 必須判定を撤去し、「webstudio のみ + `user2Profile` 不在 (C / JS 各 1 項目)」に更新 (6→7 項目)。keyfix は shimx 取込完了を待って予備退役する計画 (keyfix REPORT §4-4) だったため整合 |

### 12.3 winstubs wrap 5 API 退役 (§11.6)

| API | 実施 |
|---|---|
| `SHGetFolderPathW` `SHGetSpecialFolderPathW` `SHGetKnownFolderPath` `GetTempPathW` | `wrap_list.txt` から削除 (16→12 本)。`ws_sys.c` の `fix_user`/`is_default_user_prefix`/`__wrap_*` 4 本と `ws_internal.h` の `__real_*` 4 宣言を削除。`api_matrix.tsv` impl `wrap`→`shimx`。CREATE フラグ (`CSIDL_FLAG_CREATE`/`KF_FLAG_CREATE`/Temp 作成) は shimx 側 (`shell.c` `mk_win_dir` / `file.c` `mkdirs`) が webstudio を作るため wrap 不要 (boot e2e G07 `created=1 writable=1` 維持) |
| `ExpandEnvironmentStringsW` | wrap でなく `shimx+seed` 分類だった (§11.6 の 5 件目)。impl→`shimx` (既定環境表が webstudio で一致)。`winstubs_init` の env 上書きは `GetEnvironmentVariableW` (`LANG=en`) のため残置 |

**判断**: `WsConfig.user` は存続 (ABI 維持)。ただし既定以外にすると env (`USERNAME`/`USERPROFILE` 等) のみ追従し、`SHGetFolderPathW`/`GetTempPathW` は shimx 固定の webstudio になる (従来は wrap の `fix_user` が追従)。
使用箇所は現状ゼロ (テスト・下流とも既定値のみ) のため許容し、`ws_core.c` にコメントで明記。
再計測 (`winstubs.sh` step 4): impl 内訳 `shimx` 23→**28** / `shimx+seed` 2→**1** / `wrap` 14→**10**、baseline 差分 MATCH 60→**72** / DIFF 40→**28** / MISSING 31 (不変)。「差分実装は不要」検査 FAIL 5→**0**、checks=1133 ALL PASS。

### 12.4 回帰 (全て 2026-10-10 実測、exit 0)

| 検証 | 結果 |
|---|---|
| `bash tools/shimx/test.sh` | **exit 0**: MT/ST PASS / fail-fast 8 / M4 53/53 / 署名突合 3 IR mismatch **0** / OTT t1 SHA **b5a91b9b2ee8da1e 不変** / 未実装 0 (担当 100.0%) |
| `bash tools/startup/vreg/vreg.sh` | **ALL OK** (6/6 step: seed 再生成バイト不変 / C 単体 / shimx 結合 ST+MT+M4 / symcheck / wasm / node 22/22 / Chrome 実 IndexedDB) |
| `bash tools/startup/keyfix/keyfix_e2e.sh` | **ALL OK** (entries=236 / apply=81 / key確定=113 / key=null=3 不変、`verify_consistency.py` **7 項目** ALL PASS) |
| `bash tools/shimx/pathreg/scripts/e2e.sh` | **ALL PASS** (C 単体 ST/MT + JS 4/4 + e2e 6 groups, fixture 16) |
| `bash tools/startup/winstubs/winstubs.sh` | **exit 0** (8/8 step: 131/131 行一致 ST/MT / リンク 67/67 / boot 21/21 / IR 署名 mismatch 0 + 陰性対照 1 / shimx 回帰 ST/MT PASS / **gui 共存**: 重複は既知記録 `WTSRegisterSessionNotification` 1 件のみ・winstubs 由来 0・GetProcAddress 不整合 0・gui 強定義 6/8) |
| `bash tools/startup/pump/pump.sh` (波及確認; winstubs src を別 work で再ビルド) | **exit 0** (全 PASS) |


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

既知類型との関係 (`docs/DEFECTS.md`): 該当なし (lift/IR 変更なし。shimx 実装のみ)。検証起点 commit: `80c7471` (main)。

**結論**: OTT vst2/vst3 = 147/147・151/151、Serum2 = 238/238 (import カバレッジ, `data/coverage.json` の `covered`/`in_scope`)。
CP932 は MB→WC 全 DBCS 9,604 セルと WC→MB 往復が一致。Crypt は MD5/SHA-1/SHA-256 を実装し公開ベクトルと一致。

### 15.1 序数 → 名前 (根拠: Wine `shell32.spec` / `shlwapi.spec` = Windows の序数表。呼出箇所の引数での裏取りは §15.5)

| import | 同定 | 実装 | 備考 |
|---|---|---|---|
| shell32 #74 (OTT) | `SHCreateStdEnumFmtEtc(UINT, const FORMATETC*, IEnumFORMATETC**)` | `src/shord.c` | 深いコピーの IEnumFORMATETC (Next/Skip/Reset/Clone) |
| shlwapi #12 (Serum2) | `SHCreateMemStream(const BYTE*, UINT)` | `src/shord.c` | データをコピーした IStream (ole.c の HGLOBAL ストリームを再利用) |
| shlwapi #219 (Serum2) | `QISearch(void*, const QITAB*, REFIID, void**)` | `src/shord.c` | QITAB = {piid, offset} 16B (Win64)。一致オブジェクトを AddRef |
| shell32 #155 / #190 (Serum2) | `ILFree` / `ILCreateFromPathW` | R3 で実装済み | 本チケットで集計側 (`ORD_KNOWN`) に反映しカバー扱い (`K` 状態) |

登録先: `module.c` `shx_ordtable` (shlwapi を追加) / `cbtrans.c` `g_lifttab` (13 → 16 本。dll 名前空間を shell32/kernel32/shlwapi の 3 値化。shlwapi #16 が shell32 #16 のトークンを返さないことをテスト)。

### 15.2 Crypt (`src/crypt.c`)

`CryptAcquireContextA` / `CryptReleaseContext` / `CryptCreateHash` / `CryptHashData` / `CryptGetHashParam` (HP_ALGID/HP_HASHSIZE/HP_HASHVAL) / `CryptDestroyHash`。
CALG_MD5 / CALG_SHA1 / CALG_SHA_256。鍵付き (`key != 0`)・他アルゴリズムは NTE_BAD_KEY / NTE_BAD_ALGID。ハンドルは 256 スロット + 世代 (解放済みの再利用を NTE_BAD_HASH で検出)。
サイズ問合せ (`pbData == NULL`) は確定しない。確定後の追記は NTE_BAD_HASH_STATE。旧スタブ (reg.c, 常時失敗) は削除。

### 15.3 CP932 (`src/cp932_tab.c` 自動生成 + `str.c`)

表の出典 = Microsoft `WindowsBestFit/bestfit932.txt` (Unicode Consortium 配布)。`scripts/gen_cp932.py` が生成 (生成物 192 KB を commit, 入力は `work/` に取得)。
MultiByteToWideChar / WideCharToMultiByte / GetCPInfo(Ex) / IsValidCodePage / IsDBCSLeadByteEx / CharNextExA が 932 (および `shimx_set_acp(932)` 後の CP_ACP) で動作。
無効列 (孤立リード・無効トレイル・未割当) は U+30FB (CPINFO の UnicodeDefaultChar) か `MB_ERR_INVALID_CHARS` で ERROR_NO_UNICODE_TRANSLATION、無効トレイルは 1 バイトとして再解釈。
`WC_NO_BEST_FIT_CHARS` は往復一致する文字のみ変換。

### 15.4 検証 (2026-10-13 実測, GitHub Actions runner, emcc 6.0.12 / node 22.23.3)

| 検証 | 結果 |
|---|---|
| `bash tools/shimx/test.sh --quick` (クリーン worktree, 検証起点 HEAD `365f7fd`, n=3) | **3/3 exit 0**, 所要 23.6–24.1 s (load average 0.20–0.65 = 実行直前, 並列なし)。MT 5 グループ / ST PASS / fail-fast 8 / M4 互換 MT・ST PASS / 未実装 0 / 公開関数 678 (本 PR 前 674)。`--quick` なしは `verify_ott` が素材なしで SKIP のため同等 (作業ツリー n=1: 24.3 s) |
| CP932 全 DBCS セル | **9,604 セル**: MB→WC 不一致 **0**、WC→MB→WC 往復不一致 **0** (`test_shord.inc`)。オラクル = Python 標準 codec `cp932` (表の出典と独立実装)。生成表 `src/cp932_tab.c` も同 codec と 11,340 セル全件突合し差 **0** |
| Crypt | RFC 1321 / FIPS 180-4 の公開ベクトル 7 件 + 百万 `a` ×3 アルゴ + 境界長 (55/56/63/64/65 B) ×3 アルゴ全一致。1 バイトずつ流した場合も同値。期待値は Python `hashlib` で再検算 (手書き値との差 0) |
| 序数 | `GetProcAddress` 序数 (shell32 74 / shlwapi 12・219)・lift トークン往復・IEnumFORMATETC / IStream / QISearch の実呼出を `test_link.c` / `test_cbtrans.c` / `test_shord.inc` で確認 |
| ネガティブコントロール (n=11, 全て意図どおり FAIL = exit 1) | SHA-256 定数 1 語 / MD5 回転量 1 つ / SHA-1 K 定数 / CP932 表 1 セル / best-fit 判定除去 / リード範囲 -1 / ord74 登録削除 / ord219→218 / QISearch の AddRef 除去 / Clone の位置引継ぎ除去 / HASHVAL 再確定 |
| import カバレッジ (`data/coverage.json`) | OTT vst2 147/147, vst3 151/151, Serum2 238/238, FreshAir 98/98, FL64.exe 111/111 |

範囲外: 実 PE (OTT/Serum2) を実際にリンク・実行しての import 解決は未実施 (`plugins-*` 素材なしで、coverage は `data/imports.json` の既存スナップショット (import_scan.py 出力) と `shimx` 定義の突合)。
`verify_ott` / M11 closure 突合は `work-m11` / `work-m6-ott` が無く SKIP (§13 と同じ)。このため `test.sh` が再生成した `BACKLOG.md` / `inventory.md` / `data/inventory.csv` は M11・OTT 列が空になり劣化するので **main 版のまま (未更新)** にした。`data/coverage.json` は生成器 (`gen_inventory.py`) の出力のうち `plugins` / `shimx_*` / `ordinal` のみ反映し、`m11_closure` / `ott_api_resolved` は main 版を保持。
結果として `inventory.md` / `BACKLOG.md` は「ord74 等が未解決」と古いままで `coverage.json` と食い違う → 15.5 の未解決に計上 (素材 `work-m11 work-m6-ott` 付きで `bash tools/shimx/test.sh` を再実行すれば生成器が全て更新する。生成器側は本 PR で修正済み)。

### 15.5 序数の裏取りの限界と未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 序数 → 名前は Wine の `.spec` (Windows の序数表と同一規約) で同定したが、**呼出箇所の引数での裏取り (OTT/Serum2 の call site 逆アセ) は未実施**。素材 `plugins-ott` / `plugins-serum2` が本 run に無い | 序数表が実 Windows 10/11 と食い違う場合、誤実装が silent に通る | #175 にコメント (再起動時 `oc_artifacts: fl-win64 plugins-ott plugins-serum2`)。新規子チケット案: `[SHX-T8b] 序数 import 5 件の call site 引数裏取り` |
| d2d1 ord1 は同定対象外 (d2d1 = tools/gui 担当帯。分母 238 にも含まれない)。Wine `d2d1.spec` は序数を明示せず名前のみ列挙するため、序数 1 の根拠が取れていない | Serum2 GUI 経路のみ | tools/gui 担当 (issue #175 にコメントで引継ぎ) |
| shlwapi #219 を `QISearch` とした点は Wine の `-import` 属性 (`QISearch(ptr ptr ptr ptr)`) に依拠 | 同上 | 上と同じ |
