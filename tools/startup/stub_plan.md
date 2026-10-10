# stub_plan.md — ブラウザ版の起動スタブ計画 (FL コードは変更しない / shim の戻り値と glue だけで起動する)

結論: 起動に必要な差し替えは **(1) 20 行程度の host glue (`THostInstance` + `CreateFruityInstance` 呼出)、(2) 仮想レジストリ 1 個 + seed 18 値、
(3) Win32 スタブ約 60 API (ゲート通過 / プロセス・シェル / WinInet オフライン / システム情報)、(4) Win32 メッセージポンプ (専用 Worker 上でブロック)** の 4 面。
FL 側のコードは 1 行も変えない (README の第一目標)。ホスト FL64.exe (24 ステップ中 11) は**使わない**。シェル/外部通信は**失敗を返す** (fail-soft)。
未知の API だけは従来どおり fail-fast (`tools/shim`)。スタブ表は下記 §5。seed は `data/vreg_seed.json`。

## 1. ブート順 (ブラウザ)

```
 main thread (JS)                                engine Worker (pthread + OffscreenCanvas)
 ───────────────                                 ───────────────────────────────────────
 1 asset manifest 取得, VFS mount (/c = OPFS+MEMFS)
 2 vreg seed 読込 (data/vreg_seed.json + IndexedDB 永続分)  ───────────►  3 wasm instantiate (lift 済 FLEngine + tools/shim)
                                                                          4 DllMain closure 実行 (Delphi unit initialization; tools/m11)
                                                                          5 host glue: THostInstance 構築 (§2)
                                                                          6 CreateFruityInstance(0xC0,0xEDE95A,&host,&iface)   ← ブロック (TApplication.Run)
 7 DOM イベント → SAB ring (msg queue) ────────────────────────────────►  8 GetMessage/PeekMessage/MsgWait が ring を消費
 9 描画: OffscreenCanvas フレーム → 画面 (M7)                              
10 終了: WM_QUIT → 6 が return → iface->vtbl[0]() → "closed" UI
```

## 2. host glue (S03/S10/S11/S24 の置換)

C 構造体 (wasm メモリに 1 つ。layout は FL64.exe が作るものと同一):

```c
typedef struct THostInstance {     // size 0x38, 8 byte align
  void **vtbl;      // +0x00  3 slot (FL64.exe 実装 0x140007520/530/540 の逐語仕様は下記)
  int32_t  version; // +0x08  = 1   (エンジンが !=1 で不一致ログ)
  uint32_t flags;   // +0x0c  = 0   (bit0=plugin, bit2=no splash, bit3=no startup sound)
  void *hwnd_parent;// +0x10  = 0   (plugin モード時の親)
  const char *title;// +0x18  = "FL Studio"
  void *p20, *p28;  // +0x20/+0x28 = &zero_page (FL64.exe は 0x140069820 を指す)
  char *cmdline;    // +0x30  → char buf[0x8000] (起動引数; URL クエリ ?open=… を ANSI/UTF-8 で格納)
} THostInstance;
int rc = CreateFruityInstance(0xC0, 0xEDE95A, &host, &iface);   // win calling convention (rcx,rdx,r8,r9)
```
vtbl の 3 slot は host 側コールバック (逐語、FL64.exe 逆アセンブル済):
- slot0 `0x140007520(this,a,b,c)`: `a,b,c` を int32→int64 符号拡張して `this->vtbl[2]` (slot2) へ tail-call (別名/アダプタ)。
- slot1 `0x140007530(this)`: `ret` (何もしない)。
- slot2 `0x140007540(this,a,b,c)`: `a-=2; return (a==1 && (uint64)b<=1) ? 1 : 0;` すなわち **a==3 && b∈{0,1} のとき 1**、それ以外 0 (機能照会型)。
glue は上記 3 関数を C で同じく実装する (20 行)。engine が呼ぶ頻度/引数は lift 後に trace して確定 (T1)。
`rc ∈ {0,2}` なら `iface->vtbl[0]()` (Destroy) を呼ぶ。`rc==-2` = 署名検証失敗 (G03 が通れば出ない)。

## 3. Win32 メッセージポンプとスレッド (S22 の置換)

- エンジンは `CreateFruityInstance` 内で `TApplication.Run` (`0x86a660` → `HandleMessage` ループ) に入り**戻らない**。→ **専用 Worker でブロックさせる** (native と同じ構造を保つ; Asyncify/JSPI 不要)。
- `0x86a0f0 ProcessMessage` が呼ぶ `PeekMessageW`/`GetMessageW`/`TranslateMessage`/`DispatchMessageW`、`0x86b440 Idle` の `MsgWaitForMultipleObjects(Ex)` を **SAB ring の消費 + `Atomics.wait`** で実装。
  メインスレッドの DOM イベント (pointer/keyboard/wheel/resize/focus/clipboard/drop) を `WM_*` に変換して ring へ。`SetTimer/KillTimer/WM_TIMER`、`PostMessageW`、`SendMessageW`(同一スレッドは直接 WndProc 呼出)、
  `WM_COPYDATA`(G06 では不要)、`RegisterClassW`/`CreateWindowExW`/`SetWindowLongPtrW` の最低限 (S19: `TApplication` の不可視ウィンドウ + 主フォーム `TFruityLoopsMainForm`) は M7 (GUI) 担当と共通。
- 起動時に追加で必要な Win32: `WTSRegisterSessionNotification`→TRUE、`BufferedPaintInit`→S_OK (§5-E)。
- 終了: `PostQuitMessage` → ループ終了 → `CreateFruityInstance` が `[[g_app+8]+0x40]` を返す。

## 4. 仮想ファイルシステム / パス

FL は `\` 区切りとドライブレターで文字列処理する (`ExtractFilePath`, `IncludeTrailingPathDelimiter` 等) ため、**Windows 風名前空間を提示し file shim で写像**する (`C:\` → `/c/`)。

| Windows 風パス (シム提示) | 実体 (VFS) | 備考 |
|---|---|---|
| `C:\Program Files\Image-Line\FL Studio 2026\` (+`Shared\`, `System\`, `Data\`, `Artwork\`, `Plugins\`, `Help\`) | `/c/app/` : **読取専用** asset bundle, HTTP range + OPFS キャッシュで遅延取得 | 全展開 2.3 GB (win)。起動必須分は **未計測** → T5 で boot 中の `open()` trace から最小 manifest を自動生成 |
| `C:\Users\webstudio\Documents\Image-Line\` (= `Shared data`) | `/c/home/Documents/Image-Line/` : OPFS (永続) | `FL Studio\{Settings,Projects,…}`, `Support\Logs\Startup`, `Crash` 等がここに作られる (`0x9db5b0` のフォルダ表 ≈ 60 サブフォルダ) |
| `C:\Users\webstudio\AppData\Local\Temp\Image-Line\<pid>-<id>\` | `/c/tmp/…` : MEMFS | S18 で作成 (+`zip` サブ dir) |
| `%APPDATA%`, `%LOCALAPPDATA%` | `/c/home/AppData/{Roaming,Local}` : OPFS | `SHGetFolderPathW` の戻り (seed `_known_folders`) |
| Python (`Shared\Python`) / ffmpeg (`Shared\ffmpeg`) | `/c/app/Shared/…` | T7 |

mac 版との対応 (参考): `~/Library/Preferences/Image-Line/reg.xml` (レジストリ), `~/Documents/Image-Line/` (Shared data)。

## 5. スタブ表 (shim が返すべき値)

**A. ゲート通過 (G01–G08, G16)** — 全て「成功を返す」。FL 側の比較ロジックはそのまま動く。

| API / 命令 | 呼出元 (VA) | 戻り値 / 動作 |
|---|---|---|
| `WinVerifyTrust` | engine `0x1375990` ×2 (状態 VERIFY→CLOSE) | 0 (成功) |
| `CryptQueryObject(1, path, 0x400, 2, …)` | 同 | TRUE; `*hStore`,`*hMsg` = 非 NULL ダミー |
| `CryptMsgGetParam(msg, 6, 0, buf, &len)` | 同 | 1 回目 len=`sizeof(CMSG_SIGNER_INFO)`(≥0x80)、2 回目ゼロ埋め構造 (Issuer/SerialNumber ブロブ長 0)。`LocalAlloc/LocalFree` 実装 |
| `CertFindCertificateInStore(…, 0xb0000 CERT_FIND_SUBJECT_CERT, …)` | 同 | 非 NULL ダミー `PCCERT_CONTEXT` |
| `CertGetNameStringW(ctx, 4, 0, NULL, buf, n)` | 同 | 長さ照会時=14、本取得時 `L"Image Line NV"` を書く → engine の `==` 比較が成立 |
| `CertFreeCertificateContext`, `CertCloseStore`, `CryptMsgClose` | 同 | TRUE |
| `cpuid` (命令; `0x639900` ラッパ) | `0x639a20/0x639c70/0x63a330` | leaf0:最大 leaf 0x16/"GenuineIntel"; leaf1.EDX に CMOV(bit15)・FXSR(24)・MMX(23)・SSE(25)・SSE2(26)・TSC(4)、ECX に SSE3/SSSE3/SSE4.1/4.2/POPCNT; leaf7 は AVX2 を**立てない** (wasm SIMD128 経路に合わせる); 0x80000001 は LM/LAHF |
| `FindWindowW("TFruityLoopsMainForm")`, `FindWindowExW` | `0x117b930` ほか | NULL |
| `GetModuleFileNameW(h, buf, n)` | `0x1375990` | h==engine → `C:\Program Files\Image-Line\FL Studio 2026\FLEngine_x64.dll`、h==NULL → `…\FL64.exe` |
| `GetVersionExW` / `RtlGetVersion` | Delphi RTL, `0x454090` | 10.0 build 19045 (seed のレジストリ値と一致させる) |
| `GetComputerNameW/ExW` | inline HWID コード | `WEBSTUDIO` |
| `RegOpenKeyExA/W(HKLM,"SOFTWARE\Microsoft\Cryptography")` → `MachineGuid` | inline HWID ×24 | seed `${MACHINE_GUID}` (プロファイル毎に 1 回生成して永続) |
| `SHGetFolderPathW` (`SHFolder.dll` を `LoadLibrary`+`GetProcAddress`、`0x81bca0` 他) | `0x653130`, inline HWID | seed `_known_folders`。`LoadLibraryW("SHFolder.dll")` は成功させ `GetProcAddress("SHGetFolderPathW")` を解決 |
| `SHGetKnownFolderPath` | `0x5a0c90` | 同 |
| `ExpandEnvironmentStringsW` / `GetEnvironmentVariableW("LANG")` | `0x652e60`, `0x8d9ee0` | ENV テーブル (seed `_env`) |
| `SetEnvironmentVariableW` | `0x63b0f0` | ENV テーブルへ書込 |
| `timeGetTime`, `QueryPerformanceCounter/Frequency`, `GetTickCount` | 全般 | `performance.now()` |

**B. プロセス / シェル (G12 ほか, PROCESSES.csv)**

| API | 戻り値 | 理由 |
|---|---|---|
| `CreateProcessW` (`0x94a6d0` CloudBounce, `0xc836a0` ilbridge) | FALSE, `GetLastError`=2 (ERROR_FILE_NOT_FOUND) | 両者とも失敗経路あり。`AssignProcessToJobObject` は到達しない |
| `ShellExecuteW/A` `"open"` + `http(s)://…` | 33 (成功扱い)。実際の遷移は**ユーザ操作中のみ** `window.open` (既定 OFF = no-op) | FL は `>32` で成功判定 (`0xed6780`) |
| `ShellExecuteW` で `*.exe` ツール (ControlCreator / fldiagnostic / PluginManager / FL Cloud Plugins / CopyLicense…) | 2 (ERROR_FILE_NOT_FOUND) | FL 自身の「アプリが開けない」ダイアログ経路を使う |
| `ShellExecuteW "explore"/notepad/`.htm` | 33 + no-op (ログのみ) | |
| `ShellExecuteExW` (`properties`/`runas`/LilyPond) | FALSE, `GetLastError`=1223 (ERROR_CANCELLED) | UAC キャンセル扱いで FL が通常処理 |
| `0x125d370 restartfl` (`ShellExecuteW fldiagnostic /restartfl`) | 上記 2 を返すが、**glue が `/restartfl` を検知してページ再ロード** | クラッシュ後再起動の代替 (G12) |
| `LoadLibraryW("WebView2Loader.dll")` | NULL, `GetLastError`=126 | G13: WebView 経路を作らせない |
| `LoadLibraryW/A` その他未登録名 | NULL (126) — **trap しない** | 起動経路の未知 DLL は fail-soft、ログに記録 |
| `CoCreateInstance` (ASIO CLSID 等) | `REGDB_E_CLASSNOTREG` (0x80040154) | オーディオは Web Audio shim 側 (W16) |

**C. WinInet (G09–G11)** — 常時オフライン

| API | 戻り値 |
|---|---|
| `InternetOpenW` / `InternetOpenUrlW` / `InternetConnectW` / `HttpOpenRequestW` / `HttpSendRequest*` | NULL / FALSE, `GetLastError`=12163 (ERROR_INTERNET_DISCONNECTED) |
| `InternetGetConnectedState` / `InternetCheckConnection` | FALSE |
| `WSAStartup` (`0xc07ef0` 付近; 動的束縛) | `WSASYSNOTREADY`(10091) |

**D. UI/OS 付随 (S19)**: `WTSRegisterSessionNotification` TRUE / `WTSUnRegisterSessionNotification` TRUE、`BufferedPaintInit` S_OK、`SetPriorityClass`/`SetErrorMode`/`GetCurrentProcess` no-op、
`LoadIconW(hInst,"MAINICON")` ダミー HICON (リソースは lift 後の `.rsrc` から。無ければ 1x1)、`GetSystemMetrics`/`SystemParametersInfo` はキャンバス寸法/DPI、`TerminateProcess(self)` = Worker 終了。

**E. レジストリ**: §6。**F. 既知の「起動時に呼ばれない」もの**: `ShowEngineChoice`, `MFStartup`, ILWASAPI2ASIO COM 登録は不要。

## 6. 仮想レジストリ (vreg)

- 面 (engine が使う Reg API 全て): `RegOpenKeyExW/A`, `RegCreateKeyExW`, `RegCloseKey`, `RegQueryValueExW`, `RegSetValueExW`, `RegDeleteKeyW/ExW`, `RegDeleteValueW`,
  `RegEnumKeyExW`, `RegEnumValueW`, `RegFlushKey`, `RegQueryInfoKeyW` (= `tools/m2/SHIM_INVENTORY.md` の mac libwinbridge export 面と同一集合 → mac の `reg.xml` 実装が仕様の手本)。
- 意味論 (実測): Delphi TRegistry。ルート既定 HKCU、アクセス mask `0xf003f` (`& 0x300` で WOW64 ビット保持)、**値は REG_SZ の文字列で保存** (Int/Bool も `"123"`/`"0"`/`"1"`)。例外: OS キーの `CurrentMajorVersionNumber/CurrentMinorVersionNumber` は DWORD 直読み。
  HKLM は別ハイブ (書込可だがセッション内のみ)。`HKCU\Software\Image-Line\FL Studio <旧版>` が無ければ移行処理 (S12) は no-op。
- 永続: IndexedDB に JSON (`{hive:{key:{value:{t,v}}}}`)。エクスポートは Windows `.reg` と mac `reg.xml` の両形式 (後日; ユーザが手持ち設定を持ち込める)。
- seed (`data/vreg_seed.json`, 18 値): Paths 3 値 ×(HKCU,HKLM 一部)、`FL Studio 26\General` の 3 値 (FL Cloud 無効・クラッシュ復帰フラグ)、OS の `CurrentVersion` 8 値、`MachineGuid`、`FontSubstitutes`。
  **seed しないもの**: `Registrations\*` (ILRegKey 等 = ライセンス/トークン)。→ 未登録 (Trial 仮定) で起動 (G04)。
- 既定値: REGISTRY.csv の `default` 列に `ReadInt/ReadBool` の既定を抽出済み (例 `Sample rate=44100`)。エンジン側が既定を持つので seed 不要。

## 7. 検証計画 (lift 後に実施する受入テスト)

1. boot ログ (`Startup\*.log` と `01265690` 出力) に **"HostVersion=1 Flags=00000000" → "Init module" → "Init core paths" → "BeforeRunning" → "BeforeRunning - end" → "FL Studio 2026 <ver> Registered to:"/"Please remember to register" → "Startup took …"** が順に出ること。
2. `byte[0x14f84a8]` の値を観測 (G04 の bit0/Trial 仮説の確定。T11)。
3. 禁止事項の自動検査: boot 中に (a) WinInet 呼出が 0 回成功、(b) `CreateProcessW` 成功 0 回、(c) 未解決 import の trap 0 回。
4. `?open=` 付き URL でファイル引数が `+0x30` バッファ経由でエンジンに届き `.flp` が開くこと (S20 の cmdline 解析)。

## 8. 下流チケット案

| ID | 題 | 内容 / 受入 | 依存 |
|---|---|---|---|
| T1 | startup-glue | §2 `THostInstance` + `CreateFruityInstance` 呼出、`iface->vtbl[0]` 終了処理、URL クエリ→cmdline。受入 §7-1 | m11 (DllMain closure), T2, T3 |
| T2 | vreg | §6 の仮想レジストリ shim (`tools/shim` に registry モジュール)、seed 読込、IndexedDB 永続、Reg* 11 API 単体テスト、REGISTRY.csv の全 literal キー往復 | M4 shim |
| T3 | win-stubs-startup | §5 A/B/D の約 60 API を fail-soft で実装 (表の戻り値通り)。node テスト: 各 API の戻り値表との一致 | M4 shim |
| T4 | wininet-offline | §5 C。`GetLastError=12163`、`InternetGetConnectedState=0` | T3 |
| T5 | vfs-layout + asset trace | §4 の名前空間、`open()` trace → 起動必須 asset の最小 manifest 自動生成、遅延 fetch+OPFS キャッシュ | T1 |
| T6 | message-pump | §3 の SAB ring + `GetMessage/PeekMessage/MsgWait/SetTimer/PostMessage`、DOM→`WM_*` 変換 | M7 (GUI) |
| T7 | cpython-wasm (任意) | upstream CPython 3.12 の wasm 再ビルド + `python312.dll` 面 (`Py_*` 動的束縛 `0xc395a0`) | strategy (OSS 再ビルド方針) |
| T8 | help-viewer (任意) | `Help/index_offline.html` を iframe で表示、`error-offline.html` 差替 | T5 |
| T9 | license-import (任意・ユーザ起点) | ユーザ自身のライセンス (`.reg`/ILRegKey) を vreg に取り込む UI。生成・改変はしない | T2 |
| T10 | crash-restart | G12: クラッシュログを OPFS 保存→ダウンロード提示、`/restartfl` 検知でページ再ロード | T1 |
| T11 | license-observation | lift 後に `0x14f84a8` と Trial 制限を観測・文書化 (G04 の推定確定) | T1 |
