# STARTUP.md — FL Studio 26.1.7 起動シーケンス再構成 (win64 / macOS)

結論: 起動は **「薄いホスト (FL64.exe / OsxFL) が `THostInstance` を作り、エンジンの唯一のエントリ `CreateFruityInstance` を 1 回呼ぶ」だけ**。
以降の初期化 (パス解決・設定ロード・フォーム生成・メッセージループ) は全て FLEngine 内にある。ブラウザ版ではホスト側 (FL64.exe の約 24 ステップ中 11) を
**glue に置換**し、エンジン側 13 ステップは lift してそのまま動かす (差し替えは shim の戻り値で行う → `stub_plan.md`)。
根拠はすべて実バイナリ (Ghidra decompile / capstone 逆アセンブル / 文字列)。再現: `bash tools/startup/startup.sh` (verify.py 92 項目 OK)。
VA は FL64.exe=ImageBase 0x140000000、FLEngine_x64.dll=ImageBase 0x400000 の絶対 VA (Ghidra 表記)。

## 0. 構成の要点 (実測)

| 項目 | win64 | macOS |
|---|---|---|
| ホスト | `FL64.exe` 597,064 B, MSVC C++ x64, WinMain=`0x140007560`, CRT entry=`0x140030ed4`。IAT: KERNEL32/USER32(MessageBoxA のみ)/ADVAPI32(Reg* 3)/SHELL32(ShellExecuteA のみ)/WINTRUST/CRYPT32。**CreateProcess 無し** | `OsxFL` universal2 (x86_64 slice 2,537,520 B), **Free Pascal 3.2.3** 製。main=`0x100001de0`。Cocoa(NSApplication/NSScreen/NSAlert/NSWorkspace)+dlopen |
| エンジン | `FLEngine_x64.dll` 22.2 MB (Delphi)。export は `CreateFruityInstance`(0x1375990) / `__dbk_fcall_wrapper` / `dbkFCallWrapperAddr` の 3 本のみ。PE entry RVA 0xf76820 (=VA 0x1376820, Delphi `_InitLib` → 全 unit initialization) | `FLEngine_x64.dylib` (x86_64 slice 31.6 MB)。export `_CreateFruityInstance`(0x3740 → jmp 0x3240) 1 本のみ |
| ホスト⇄エンジン契約 | `CreateFruityInstance(0xC0, 0xEDE95A, THostInstance*, void** iface)` (戻り値 int。**0xC0 / 0xEDE95A はハンドシェイク定数**: `mov edx,0xede95a; mov ecx,0xc0` @0x140006f2d) | `CreateFruityInstance(THostInstance*, void** iface)` (2 引数) |
| THostInstance | 0x38 B, vtable `0x140069d00` (3 slot: 0x140007520 forward / 0x140007530 `ret` / 0x140007540)。`+8`=1 (host version, エンジンが `!=1` で「engine がアプリと不一致」)、`+0xc`=flags (0)、`+0x10`=親 HWND (plugin 時)、`+0x18`="FL Studio"、`+0x30`=cmdline バッファ (`0x1400752f0`, 0x8000 B) | 同型 (FPC class `DAT_1000e8490`): `+8`=1, `+0xc`=0, `+0x18`="FL Studio" |
| flags (+0xc) | bit0=プラグイン(ラッパ)モード (cmdline 解析・署名確認をスキップ)、bit1=不明 (`DAT_015e01b0` に格納)、bit2=スプラッシュ抑止 (0x11b3810 を呼ばない)、bit3=起動音抑止 | 同じ読み方 (`DAT_01d8bc1c` = flags&1) |
| 戻る iface | `PTR_DAT_015e25b8` のオブジェクト (VMT 0x1253d48)。slot0 = `0x12541b0` = **Destroy/Free** (VMT-0x20 スロットを引数 1 で呼ぶ; 推定。ホストが最後に 1 回呼ぶ) | 同オブジェクト型。**ホストが `vtbl+200` (slot25) を呼ぶ = Run** |
| メッセージループの位置 | **CreateFruityInstance の内部** (`0x1375950` → `TApplication.Run` 0x86a660: `do HandleMessage while(!Terminated)`)。戻った時点でアプリ終了 | CreateFruityInstance は初期化後に戻り、ホスト (`OsxFL`) が iface slot25 で Run |

## 1. シーケンス図 (win64)

```
 OS loader      FL64.exe (host)                         FLEngine_x64.dll                      Win32/外部
    │  entry 0x140030ed4 → WinMain 0x140007560
    ├───────────►│ S02 LoadLibraryW(Mfplat.dll); MFStartup(0x20070,1) ≠ E_NOTIMPL ──────────────► [Media Foundation]
    │            │ S03 new THostInstance{ver=1,flags=0,"FL Studio",&cmdbuf}
    │            │ S04 lpCmdLine(ANSI) → UTF-16
    │            │ S05 enginePath = <exeDir>\FLEngine_x64.dll ──(無/ディレクトリ)──► HKCU→HKLM[32] "Software\Image-Line\Shared\Paths"\"FL Studio engine"; SetCurrentDirectoryW
    │            │ S06/S07 (cmdline が空のときだけ) Shared dir 解決(+SetCurrentDirectoryW) / <exeDir>\Builds\ があれば ShowEngineChoice()
    │            │ S08 WinVerifyTrust(engine) + 署名者 CN == "Image Line NV" ── 不一致 → -2 → MessageBox "Verification error"
    │            │ S09 LoadLibraryW(engine) ───────────────► DllMain: entry 0x1376820 = Delphi _InitLib → unit initialization 群
    │            │ S10 strcpy_s(g_cmdline[0x8000], cmdline)
    │            │ S11 GetProcAddress("CreateFruityInstance")(0xC0,0xEDE95A,host,&iface) ──►│
    │            │                                            │ S12 timeGetTime; g_host=host; 旧版設定の移行 (0x13752f0)
    │            │                                            │ S13 ログ ON; "HostVersion=%d Flags=%.8x", "Init module"
    │            │                                            │ S14 自己署名検証 (WinVerifyTrust+CN) [+ flags&1==0 なら host EXE も]
    │            │                                            │ S15 "Init core paths" 0x1264050: ユーザデータ dir 解決/作成/書込テスト, env FLStudioData 等
    │            │                                            │ S16 0x13754b0: ユーザデータ配下オブジェクト初期化
    │            │                                            │ S17 0x13755b0: host.ver==1 / CPUID(CMOV) / 多重起動カウンタ
    │            │                                            │ S18 BasicInitialization 0x11b32a0: /PluginSetup /Reset, 単一インスタンス, 約 21 シングルトン, AppKey="Software\Image-Line\FL Studio 26"
    │            │                                            │ S19 TApplication: Title, MAINICON, RegisterClassW("TApplication"), 不可視 app ウィンドウ, 優先度 ABOVE_NORMAL
    │            │                                            │ S20 0x13751e0: cmdline 解析 0x10e5320, スプラッシュ判定 0x11b3810, **BeforeRunning 0x11be0a0** (設定ロード 0x11a57c0, 11 フォーム生成 0x11c8950, テーマ, 登録状態ログ)
    │            │                                            │ S21 *iface = PTR_DAT_015e25b8
    │            │                                            │ S22 0x1375950 → TApplication.Run: 主フォーム表示, ProcessFirstTimeStuff 0x11ef180, HandleMessage ループ ◄── ブロック (アプリ寿命)
    │            │                                            │ S23 終了: 戻り値=[app+8]+0x40; vtbl[11]≠0 なら 0x125d370 "restartfl"
    │            │◄──────────────────────────────── return code
    │            │ S24 iface vtbl[0] (Destroy) → FreeLibrary(engine) → delete host → exit(0)
```

## 2. 起動ステップ表 (win64: 24 ステップ)

「ブラウザ版」列: **置換**=glue/shim で差し替え、**そのまま**=lift した FL コードを動かす、**不要**=呼ばない。

| # | 担当 | 関数/VA | 内容 (実測) | 失敗時の挙動 | ブラウザ版 |
|---|---|---|---|---|---|
| S01 | host | CRT entry `0x140030ed4` → `__scrt_common_main_seh` → WinMain `0x140007560` (呼出 @0x140030e61) | `WinMain(hInst, hPrev, lpCmdLine, nShow)` | — | 不要 |
| S02 | host | `0x140007560` | `LoadLibraryW(L"Mfplat.dll")`, `GetProcAddress("MFStartup")(0x20070,1)`; 戻りが `E_NOTIMPL(0x80004001)` なら NG | MessageBox "Media Feature Pack is missing" + OK で `ShellExecuteA(https://support.image-line.com/redirect/kb_windows_n)` → exit | 不要 (ゲート G01) |
| S03 | host | `0x140007560` | `THostInstance` (0x38 B) 生成: vtable `0x140069d00`, `+8=1`, `+0x18="FL Studio"`, `+0x30=&g_cmdline` | — | **置換** (glue が同 layout の構造体を wasm メモリに作る) |
| S04 | host | `0x140002bc0`, `0x140001bc0` | lpCmdLine を `std::string`→`std::wstring` | — | 不要 |
| S05 | host | `0x1400062a0` → `0x1400014f0`,`0x140005000` | エンジン絶対パス = `<exeDir>\FLEngine_x64.dll`。`GetFileAttributesW` で「存在しない or ディレクトリ」なら `0x140005000`: **HKCU 次いで HKLM(KEY_WOW64_32KEY)** の `Software\Image-Line\Shared\Paths` → 値 `FL Studio engine` (REG_SZ, 0x10000 B バッファ。**値はインストール先内の「ファイルパス」**: `0x140001330` = 最後の `\` か `/` までで切る parent_path。mac の OsxFL も `.../FLEngine_x64.dylib` のファイルパスを書く) を読み、親ディレクトリへ `SetCurrentDirectoryW`、親 + `FLEngine_x64.dll` をエンジンパスにする | 空文字 → 戻り値 -3 (無言終了) | 不要 (パス解決は VFS 側) |
| S06 | host | `0x140005480` | **cmdline が空のときのみ**。`<exeDir>\Shared\` に `ILTools_x64.dll` が在るか確認、無ければ `Software\Image-Line\Shared\Paths\Shared DLLs` (HKCU/HKLM) → `SetCurrentDirectoryW(Shared)` | — | 不要 |
| S07 | host | `0x140005d80` | **cmdline が空のときのみ**。`<exeDir>\Builds\` ディレクトリがある場合、選択 DLL を `LoadLibraryW` し `ShowEngineChoice(cmdline)` (export) を呼んでエンジンパスを差し替える (複数ビルド併存用)。無ければ素通し | — | 不要 (Builds\ 無し) |
| S08 | host | `0x1400062a0` 後半 | `WinVerifyTrust(WINTRUST_ACTION_GENERIC_VERIFY_V2 {00AAC56B-CD44-11D0-8CC2-00C04FC295EE})` → `CryptQueryObject`/`CryptMsgGetParam(6)`/`CryptDecodeObject("1.3.6.1.4.1.311.2.1.12")`/`CertGetNameStringA(4)` で署名者名 == **"Image Line NV"** | 不一致 → 戻り -2 → MessageBox "Verification error: The validity of the program could not be verified…" | 不要 (ゲート G03; エンジン側 S14 は shim で通す) |
| S09 | host | `0x140004b60` | `GetModuleHandleW(path)` が非 NULL (既ロード) なら名前に `_Copy` を挿入した別ファイルを選ぶ。`LoadLibraryW(path)` → **DllMain** (entry `0x1376820`: `0x412760` 初期化済判定 → `0x41d8f0` InitLib → `0x4128b0`) が Delphi unit initialization を全実行 | 失敗 → `*hmod==0` で無言終了 | **そのまま** (`tools/m11` の DllMain closure 担当) |
| S10 | host | `0x1400062a0` | `strcpy_s(&g_cmdline(0x1400752f0), 0x8000, cmdline_ansi)` | — | 置換 (glue が `+0x30` バッファに URL パラメータ由来の引数を書く) |
| S11 | host | `0x140006f1b` | `GetProcAddress(engine,"CreateFruityInstance")(0xC0,0xEDE95A,host,&iface)` | NULL → 戻り -3 以外ならそのまま | **置換** (glue から直接 wasm 関数を呼ぶ) |
| S12 | engine | `0x1375990` 冒頭, `0x13752f0`→`0x1105350/0x11054c0` | `timeGetTime`→起動時刻、`g_host`=param3、**旧バージョン設定の移行**: `Software\Image-Line\FL Studio <旧ver>` を検出して現行キーへコピー (ログ "Migrated settings from FL Studio %d") | 失敗はログのみ | そのまま (空レジストリでは no-op) |
| S13 | engine | `0x12658c0(1)`, `0x1265690` | ログ有効化。"HostVersion=%d Flags=%.8x", "Init module"。起動ログは `<パス表 id 0x3eb (Support\Logs と推定)>\Startup\<yyyy-mm-dd_hhmmss>.log` (`0x12652c0`/`0x1265390`) | — | そのまま |
| S14 | engine | `0x1375990` 中盤 | `GetModuleFileNameW(hEngine)` に対し WinVerifyTrust+署名者 == "Image Line NV"。`host.flags&1==0` なら `GetModuleFileNameW(NULL)` (=ホスト EXE) にも同検査 | 不一致 → 戻り **-2** | 置換 (shim が `WinVerifyTrust`=0 / `CertGetNameStringW`="Image Line NV" を返す) |
| S15 | engine | `0x1264050` | **ユーザデータ dir**: `Shared data` (HKCU Paths) → 無ければ SHGetFolderPath(CSIDL_PERSONAL=5 → 0x1a APPDATA)+`\Image-Line\` (`0x653100/0x653130`)。作成+`testpermissions.tmp` 書込テスト (`0x1263d50`)。失敗時は「User data folder could not be created…Controlled folder access」ダイアログ (Learn how to fix / Reset folder location / Quit|Continue) のループ。成功後 env 変数 `FLStudio<k>Data`, `FLStudio<k>CommonConfig`, `FLStudio<k>Config` (k=3 種のフォルダ区分 × `0x1264e40`) を `SetEnvironmentVariableW` (`0x1264d10`、同時に内部 path リストへも登録) | 3 択ダイアログ。Quit=`TerminateProcess` | そのまま (VFS が常に書込可) |
| S16 | engine | `0x13754b0` | ユーザデータ配下 (`[app+0x30]`) からロケール/設定オブジェクトを初期化 | — | そのまま |
| S17 | engine | `0x13755b0` | (a) `host.ver(+8)!=1` → ログ "engine doesn't match the application executable"。(b) `cpuinfo.flags(+0x12)&0x10` == **CPUID.1:EDX bit15 (CMOV)** 無し → MessageBox "This computer's CPU won't run FL Studio" → 戻り 1。(c) `*(int*)PTR_DAT_015e0fa8>0` (他インスタンス数) → "Another instance of %s is open" → 戻り 3 | 戻り値≠0 で CreateFruityInstance 終了 | そのまま (cpuid shim が CMOV ビットを立てる) |
| S18 | engine | `0x11b32a0` (BasicInitialization) | `0x11b2450`: アートワーク dir, **一時 dir `%TEMP%\Image-Line\<pid>-<id>\`** (+`zip` サブ dir) 作成。`/PluginSetup` `/Reset` 検査。`0x117b930` 単一インスタンス: `FindWindowW("TFruityLoopsMainForm")`→ 在れば `SendMessageW(WM_COPYDATA)` でファイルを転送 → 戻り 3。約 21 個のグローバルシングルトン (`PTR_DAT_015e....`) を生成。`AppKey = "Software\Image-Line\FL Studio 26"` | 戻り 1/3 | そのまま (`FindWindowW`=NULL) |
| S19 | engine | `0x869c10`,`0x867e10`,`0x86ccd0`,`0x86a440`, `SetPriorityClass(0x8000)` | standalone (`g_isPlugin==0`): `TApplication.Title="FL Studio"`, `LoadIconW(hInst,"MAINICON")`, `RegisterClassW("TApplication")` + 不可視 `CreateWindowExW(WS_EX_TOOLWINDOW)`, `WTSRegisterSessionNotification`, `BufferedPaintInit`、app ウィンドウを `WS_EX_TOOLWINDOW` 化 (`0x86ccd0`: タスクバーには主フォームだけ出す)、優先度 ABOVE_NORMAL。plugin モードは `Application.Handle = host+0x10` | — | そのまま (GUI shim) |
| S20 | engine | `0x13751e0` → `0x10e5320`, `0x11b3810`, `0x11be0a0` | (flags&1==0) **cmdline 解析** (§4)。(flags&4==0) `General\MIDIForm\SplashBox`(既定 1) でスプラッシュ。**BeforeRunning**: 環境 `FLStudioData`/`ILSharedData`、`General\Theme\ThemeFilename`→`__current.flstheme`、PPI 設定、**LoadSettings `0x11a57c0`** (§5)、フォーム/ウィンドウ生成 `0x11c8950` ×11 (うち 1 つが window class `TFruityLoopsMainForm` と推定)、`0x10c7530` 登録情報、ログ "FL Studio 2026 <ver> Registered to: … / Please remember to register"、`PostMessageW(WM_USER+0x163)` | 例外は SEH ハンドラが捕捉 (G12) | そのまま |
| S21 | engine | `0x13751e0` 末尾 | `*iface = PTR_DAT_015e25b8`; `[[app+8]+0x40]=0` | — | そのまま |
| S22 | engine | `0x1375950` → `0x86a660` | standalone: `Application.Run`: 主フォーム表示、`do { 0x86a250 (HandleMessage: PeekMessage→Dispatch / 無ければ Idle→MsgWaitForMultipleObjects) } while(!Terminated)`。初回表示フック (`0x11be0a0` が app+0x250 に `0x11efbf0` を登録) で `0x11ef180` **ProcessFirstTimeStuff** (§6)。plugin モード: `0x11efbf0` を呼んで即戻る | — | **置換**: ループを専用 Worker で実行し `GetMessage`/`MsgWait*` を `Atomics.wait` に (stub_plan §3) |
| S23 | engine | `0x1375990` 末尾 | 戻り値 = `[[g_app+8]+0x40]`。`vtbl[0x58/8](obj)`≠0 なら `0x125d370` = `ShellExecuteW(fldiagnostic "/restartfl \"<exe>\"")` | — | 置換 (restartfl = ページ再ロード) |
| S24 | host | `0x140007560` 末尾 | 戻り値 ∈ {0,2} なら `iface->vtbl[0]()` (= `0x12541b0` Destroy)。`FreeLibrary(engine)`、`delete host` | — | 置換 (終了 = Worker 停止/ページ側 UI) |

ステップ数: **win64 = 24** (host 11 [S01–S11] + engine 13 [S12–S24])。ブラウザ版で実際に lift コードとして走るのは S09 (DllMain) と S12–S22。

## 3. シーケンス (macOS: OsxFL, 10 ステップ)

| # | 関数 | 内容 (実測) |
|---|---|---|
| M01 | dyld → `OsxFL` main `0x100001de0` (FPC) | FPC RTL 初期化 |
| M02 | `0x100001de0` | `argc==1 && argv[1]=="-setenginepath"` の特別モード: `0x100001c20` が libwinbridge の `RegWriteStringValue(2,"Software\Image-Line\Shared\Paths","FL Studio engine",<bundle>/Contents/Libs/FLEngine_x64.dylib)` と `CFPreferences com.image-line.shared / FL Studio engine` を書いて終了 (通常起動では通らない) |
| M03 | `0x100001de0` | `NSScreen.screens`; `NSApplication.sharedApplication`; コールバック (`0x100001a50`,`0x100001ba0`) 登録; 動的ライブラリ拡張子 `.dylib` 設定 |
| M04 | `0x100001de0` | `THostInstance` 生成 (`+8=1`, `+0xc=0`, `+0x18="FL Studio"`) |
| M05 | `0x100001de0` | `enginePath = [[NSBundle mainBundle] bundlePath] + "/Contents/Libs/FLEngine_" + "x64" + ".dylib"` |
| M06 | `0x100086ff0` | libwinbridge 解決: `dladdr` から自バンドル → `Resources/FL/Shared/libwinbridge_x64.dylib`、無ければ `CFPreferencesCopyAppValue("FL Studio engine","com.image-line.shared")` 経由。見つからなければ NSAlert "Could not locate: libwinbridge_x64" → exit |
| M07 | `0x100081110` | `dlopen(engine)` + `dlsym("CreateFruityInstance")(host,&iface)` (win と違い署名検証/ハンドシェイク定数なし) |
| M08 | engine `0x3240` | win S12–S21 と同型 (HostVersion ログ, Init core paths, BasicInitialization `0x2e3320`, `TApplication` 初期化 `0x4ae90` = Title "FL Studio")。**ここでは Run せず戻る** (`0x31a0` が OnIdle/OnShow コールバックを登録) |
| M09 | `0x100001de0` | 戻り 0 なら `(**(code**)(iface->vtbl+200))(iface)` = **Run** (Cocoa run loop)。非 0 は `dlerror()` を NSAlert 表示 |
| M10 | `0x100001de0` | `0x1000812c0` free; host->vtbl[+0x60](1) = destroy |

mac の registry は **`~/Library/Preferences/Image-Line/reg.xml`** (libwinbridge `TXmlRegistry`, NSLibraryDirectory(5)/user + `/Preferences/Image-Line/reg.xml`、`Key%d` ノード、`0x1a250` が存在確認・初期化)。
`Reg*` 34 export の実体であり、`tools/shim` の仮想レジストリ (stub_plan §2) が担う面と一致。

## 4. 引数・環境変数

**FL64.exe**: 引数は `lpCmdLine` をそのままエンジンへ転送するのみ (ホスト自身は解釈しない)。空のときだけ S06/S07 を実行。環境変数は使わない (CRT の `_putenv` のみ)。
**エンジン cmdline** (`0x10e5320`, プレフィクス `/`、`FUN_010e3bd0` で登録): `R` `E` `F` `O` `M` `Z` `B` `BMP` `PPI<n>` `D`、`TESTMODE`/`TEST`、`GENPREVIEWS` `PLUGIN=`、`NOERRORMSG`、`NOSPLASH`、秘匿スイッチ 1 (文字列が -3 シフトで難読化: `FFWHVW`→`CCTEST`)。位置引数 = 開くファイル (`.flp`→mode2, `.fsc`/`.mid`→mode1 等、mode byte=`[host_cfg+8]`: 4=既定, 0=`/R`, 1=`/M`, 2=ファイル, 3=`/Z`, 5=`GENPREVIEWS`)。
BasicInitialization が別に `/PluginSetup` `/Reset` を検査 (どちらかが在れば「DoFail」で起動中断 = 1)。
**環境変数**: 読む=`LANG` (gettext, `0x8de4f0`)。書く=`FLStudio<k>Data`, `FLStudio<k>CommonConfig`, `FLStudio<k>Config` (0x1264e40, 3 区分), `FLStudioData`, `ILSharedData` (0x11be0a0) (`0x1264d10` → `SetEnvironmentVariableW`; プラグイン/Python が参照)。
ブラウザ版: 引数は URL クエリ (`?open=<opfs path>`) → glue が `+0x30` バッファへ。環境変数は Emscripten `ENV` で提供 (`LANG=en`)。

## 5. 設定ロード (LoadSettings 0x11a57c0 / SaveSettings 0x11af7e0)

全設定は **TRegistry 経由 (HKCU, REG_SZ 文字列。Int/Bool も文字列 "0"/"1"/数値文字列)**。`HKCU\Software\Image-Line\FL Studio 26\{General,Search paths,MRU,Environment,Envelope editor,…}` と `…\Shared\{General,Language,Paths,Browser}`。
初回 (空レジストリ) の既定値は `ReadInt/ReadBool` の第 3 引数 (REGISTRY.csv `default` 列): 例 `Sample rate=44100 (0xac44)`, `Buffer length (DS)=4096 (0x1000)`, `Run counter=0`, `Scope Mode=1`, `AlwaysAskProjectFolder=4`, `LastExportedFormats=8`, `BackColor=0x6c645e`, `BackMode=2`, `Browser FL CLOUD displayed=0`, `Disable FL CLOUD search=0`, `Browser search folders=1`。詳細は REGISTRY.csv。

## 6. 初回アイドル (ProcessFirstTimeStuff 0x11ef180) で起きること

起動後最初の表示で 1 回: `ProcessFirstTimeStuff` ログ → 他インスタンス確認 → **遅延ジョブのカウンタ設定** (`Random(10)+5`, `Random(30)+50` に 3600 を乗じた値を `DAT_016bcf0c/10` へ。単位は秒と推定 = 約 5–15 h / 50–80 h 後に更新確認・ニュース取得が走る。**セッション内ではまず発火しない**)、`0x11578d0` FL Cloud 最終取得日確認、起動プロジェクト決定 (既定は空プロジェクト; `Data\System\Empty.flp` の参照あり。`General\CrashLoadingStartupProject`=1 なら「前回クラッシュしたので初期化」ダイアログ)、起動音 (`flags&8==0`)、"Startup took %d seconds and %d milliseconds." ログ。
通常のネットワーク通信は **この時点では発生しない** (G09/G10 参照)。

## 7. ファイルシステム参照 (起動経路で実際に触れるもの)

| 論理名 | win 実体 | ブラウザ版 VFS 案 (詳細 stub_plan §4) |
|---|---|---|
| Program dir | `<install>\` (FL64.exe, FLEngine_x64.dll, `Shared\`, `System\`, `Data\`, `Artwork\`, `Plugins\`) | `/app` (読取専用 asset bundle, 遅延 fetch) |
| 起動時に必須の読取 | `System\Languages\*.moe`, `System\Config\**`, `Artwork\**`, `Data\System\Empty.flp`, `Shared\ILTools_x64.dll` ほか | `/app/...` |
| ユーザデータ (`Shared data`) | `%USERPROFILE%\Documents\Image-Line\` (+ `FL Studio\` サブ: `Settings`, `Support\Logs\Startup`, `Crash`, `Projects\Backup`, `Audio\Recorded` …) | `/home/user/Image-Line/` (OPFS / IDBFS) |
| 一時 | `%TEMP%\Image-Line\<pid>-<id>\` | `/tmp/Image-Line/…` (MEMFS) |
| レジストリ | HKCU/HKLM (REGISTRY.csv) | 仮想レジストリ (JSON, IndexedDB 永続) |
