# REPORT — CAB-96 win-stubs-startup: 起動 critical Win32 API の fail-soft stub (shimx 突合 + 差分実装)

日付: 2026-10-10 / 書込範囲: `tools/startup/winstubs/`(成果物) と `tools/startup/work/winstubs/`(gitignore) のみ。`tools/shimx` `tools/gui` `tools/m11` `tools/runtime` は読取のみ(改変 0 行)。
再現: `bash tools/startup/winstubs/winstubs.sh` (約 10 秒 / `FORCE=1` で全再ビルド, exit 0 = 全 PASS)。

## 0. 結論 (数値は全て実測)

1. 起動 critical は **52 API** (stub_plan §5 の A 32 / B 9 / D 11) を `data/api_matrix.tsv` に確定。ほかに user32 ポンプ 10 と Reg* 5 (突合のみ) を載せて計 67 行。WinInet(C) は T4 (ネットワーク) の担当で対象外、Reg* は §5。
2. shimx 突合結果 (52 本): **shimx 既存で足りる 27** (純 23 / 計数のみ `--wrap` 2 / 環境 seed 投入 2)、**shimx のフックへ方針を接続 2** (ShellExecuteW/A)、**差分実装 `--wrap` 14**、**新規 8** (RtlGetVersion + 7 本は weak: FindWindow(Ex)W / BufferedPaintInit・UnInit / LoadIconW / GetSystemMetrics / SystemParametersInfoW)、**lift 側 intrinsic 1** (cpuid)。
3. 期待戻り値表 `data/retval_table.tsv` **131 行**を ST / MT 双方で **131/131 一致**。shimx 単体 (baseline) との差分は実測で **MATCH 60 / DIFF 40 / MISSING 31** (`data/diff_table.tsv`, 自動生成)。
4. 受入: boot e2e で **CreateProcessW 成功 0 回** (試行 1)、**未解決 import trap 0 回**。リンクテスト **67/67** (ST/MT)、GetProcAddress と リンク時アドレスの一致 (`--wrap` 経由) 全件。
5. 既存資産への影響なし: winstubs 層 (未 init) を挟んで **shimx 単体テストが ST/MT とも ALL PASS**。tools/gui の強定義とは重複なく共存 (§7)。
6. lift IR との署名突合 (`tools/m11/work/boot_final2.ll` の declare 42/67 本): **signature mismatch 0 / undefined 0** (故意の i64 署名を入れた陰性対照は 1 件検出)。

## 1. 方針: 再実装せず「薄い委譲 / alias」で接続

- shimx のソースは無改変。差分は 3 種の接続で足す:
  - **`ld --wrap=<api>`** (`wrap_list.txt` の 16 本): 呼出側 (lift IR / shimx の GetProcAddress 表) は `__wrap_<api>` に束縛され、不要な箇所は `__real_<api>` (= shimx 実装) へ即委譲。下流は `-Wl,--wrap=...` を渡す必要がある (`scripts/build.sh` の `wrap` モード参照)。
  - **shimx 運用フック**: `shimx_set_trust_ok(1)` / `shimx_set_shell_execute_hook` / `shimx_set_version` / `shimx_setenv_utf8` / `shimx_module_register` / `shimx_proc_register`。`winstubs_init()` が一括設定。
  - **新規 (weak) 定義**: shimx 範囲外 (user32/uxtheme/ntdll)。tools/gui の強定義があればそちらが勝つ。
- 戻り値表の根拠は stub_plan.md §5 / GATES.md。表の各行に `plan_ref` 列で出典 (§5-A 等) か「Win32 仕様」を明記。
- **fail-soft の原則**: 未知 action・未登録 DLL・不正サイズは FALSE/NULL/エラーコードを返し trap しない (`SystemParametersInfoW` の未知 action 等)。未知 API の fail-fast は shimx のまま。

## 2. 差分表 (52 API)

| 区分 | API | 内容 |
|---|---|---|
| shimx 既存 (23) | CertFreeCertificateContext CertCloseStore CryptMsgClose GetModuleFileNameW GetVersion GetVersionExW GetComputerNameW/ExW GetProcAddress timeGetTime QPC QPF GetTickCount LocalAlloc LocalFree CoCreateInstance SetEnvironmentVariableW SetErrorMode SetPriorityClass GetCurrentProcess TerminateProcess WTS(Un)RegisterSessionNotification | 戻り値表と一致 (baseline 全行 MATCH)。GetModuleFileNameW は engine を `shimx_module_register` 済みであること |
| shimx + 計数 (2) | WinVerifyTrust, CreateProcessW | 挙動は shimx 同一。`--wrap` で呼出回数だけ計数 (受入「CreateProcessW 成功 0」の根拠) |
| shimx + seed (2) | ExpandEnvironmentStringsW, GetEnvironmentVariableW | API は shimx。環境表を vreg_seed.json の `_env` (webstudio ユーザ, `LANG=en`) で上書き |
| フック接続 (2) | ShellExecuteW/A | shimx 既定は常に 2。分類方針 (§5-B) を hook に接続: `open http(s)://` `explore` notepad `.htm`→33 / `.exe` ツール→2 / `fldiagnostic /restartfl`→2 + 再起動要求フラグ |
| 差分実装 `--wrap` (14) | CryptQueryObject CryptMsgGetParam CertFindCertificateInStore CertGetNameStringW/A | shimx は常に失敗/空 → G03 チェーン (CN=`Image Line NV`, signer info 0x88B ゼロ埋め)。`cfg.trust=0` なら shimx 既定へ委譲 |
| | SHGetFolderPathW SHGetSpecialFolderPathW SHGetKnownFolderPath GetTempPathW | shimx 既定ユーザ `user` → seed の `webstudio`。`CSIDL_FLAG_CREATE` は webstudio 側に作成 |
| | ShellExecuteExW/A | `runas`/`properties`/LilyPond は FALSE + `GetLastError=1223` (hook では表現不可) |
| | LoadLibraryW/A/ExW | `WebView2Loader.dll` は load hook (将来 hostbridge) が何でも解決する状況でも NULL/126 に固定。失敗名をログ (`winstubs_loadlib_miss`) |
| 新規 (8) | RtlGetVersion | ntdll。`GetVersionExW` と同値 (10.0.19045)、不正サイズは `0xC000000D` |
| | FindWindowW/ExW (weak) | NULL (`1407`)。G06 |
| | BufferedPaintInit/UnInit, LoadIconW, GetSystemMetrics, SystemParametersInfoW (weak) | S_OK / 非 NULL ダミー / キャンバス寸法 1920x1080 + Win10 100%DPI 近似 / WORKAREA・NONCLIENTMETRICS ほか |
| lift 側 (1) | cpuid | `winstubs_cpuid(leaf,sub,out[4])`。leaf1.EDX に CMOV/FXSR/MMX/SSE/SSE2/TSC、leaf7 の AVX2 は常に 0。プロファイル `SSE2`(既定, m11 helper 到達範囲) / `PLAN`(stub_plan: SSE3〜4.2/POPCNT) |

意図的未実装: WinInet C 群 (InternetOpenW 等 — T4 ネットワーク担当) と Reg* 5 本 (§5)。user32 ポンプ 10 本は stub レベルのみ (§4)。

## 3. G01〜G08 通過マップ (boot e2e 21/21 一致の根拠。数値は実測)

| ゲート | winstubs が面を見る API | 実測 (boot_expect の行) | 判定 |
|---|---|---|---|
| G01 Media Foundation | 対象 API 無し (engine は呼ばない — GATES)。万一 `LoadLibraryW("Mfplat.dll")` が来ても NULL/126 の fail-soft | (対象行無し) | 通す (構造上不要) |
| G02 エンジン所在 | `GetModuleFileNameW(engine)`=`C:\Program Files\...\FLEngine_x64.dll` (`winstubs_init` が登録)。レジストリ経由は cross-ref (vreg) | S00 前提 | glue が直接呼ぶため回避 |
| G03 署名 | `WinVerifyTrust`→0 / `CryptQueryObject`→TRUE / `CryptMsgGetParam(6,0)`→0x88B / `CertFindCertificateInStore`→非NULL / `CertGetNameStringW(…,4,…)`→`Image Line NV` / 3 close→TRUE | `G03.engine_self_1/2`, `G03.host_exe` とも signer_match=1, `G03.result pass=1` | 通す (§6) |
| G04 登録/ライセンス | `GetComputerNameW/ExW`=`WEBSTUDIO`、`SHGetFolderPathW`/`SHGetKnownFolderPath`/`GetTempPathW`→`webstudio`、`GetProcAddress("SHFolder.dll"!SHGetFolderPathW)` 解決。MachineGuid は vreg | `G04.machine_inputs` guid_len=36 computer=WEBSTUDIO shfolder_hr=0 | 既定値 (vreg 側) + 本層で識別値供給 |
| G05 CPU | `winstubs_cpuid`: leaf1.EDX=`0x078bfbff` (bit15 CMOV=1) | `G05.cpu cmov=1` | 通す |
| G06 単一インスタンス | `FindWindowW/ExW`→NULL + `SetLastError(1407)` | `G06.single_instance existing_window=0` | 通す |
| G07 ユーザデータ dir | `SHGetFolderPathW(CSIDL_FLAG_CREATE)` が `C:\Users\webstudio\Documents\Image-Line` を実作成 (VFS) | `G07.userdata created=1 writable=1` | 通す |
| G08 初回フラグ | Reg* は cross-ref (seed: `CrashLoadingStartupProject=0` ほか) + 環境 `LANG=en` | `G08.flags`, `S08.env lang=en` | 既定値 (vreg seed) |
| (参考) G16 OS ver | `GetVersion`/`GetVersionExW`/`RtlGetVersion` = 10.0.19045 で一貫 | `G16.os consistent=1` | 通す |
| (副次) G12/G13 | `CreateProcessW` 試行1/成功0、`fldiagnostic /restartfl`→再起動要求フラグ、`WebView2Loader.dll`→NULL/126 | `G12.process create_process=0 webview2=0 err=126`, 受入行 3 本 | 失敗経路の fail-soft |

## 4. user32 ポンプ系: stub レベルに留める (RING ABI 結線は CAB-102)

10 本 (`PeekMessageW` `GetMessageW` `TranslateMessage` `DispatchMessageW` `PostMessageW` `SendMessageW` `PostQuitMessage` `SetTimer` `KillTimer` `WaitMessage`) は weak 定義で**呼出カウント (`g_ws.pump_calls`) のみ**を取る。
戻り値は未結線ビルドでも起動を止めない最小値 (`GetMessageW`=0 = WM_QUIT → ループ即終了, `PeekMessageW`=FALSE, `SetTimer`→id)。
`tools/runtime/worker_pump.ts` の RING ABI への結線 (実メッセージ配信) は **CAB-102 が強定義で置換する**前提であり、winstubs 側では結線しない。置換後も `WS_INC(pump_calls)` の計数署名を踏襲すれば統計は継続利用できる。boot e2e: `S11.pump_stub loop_exit=1 spins=0`。

## 5. Reg* は一切定義しない (CAB-94 vreg と shimx の衝突回避)

`RegOpenKeyExW/A` `RegQueryValueExW/A` `RegCloseKey` の 5 本は `cross-ref` として api_matrix に掲載するのみで、**winstubs はシンボルを定義せずテストでもリンクしない**。
理由: vreg の `reg.c` と shimx の `reg.c` が同名シンボルを既に持ち、winstubs が 3 番目の定義を置くと duplicate symbol / 置換不明確化になる。boot e2e の seed 投入も shimx の `shimx_reg_set_*` を直接使う (vreg 実装への依存なし)。

## 6. ライセンス/アクティベーション無効化方針 (ユーザ確定方針の適用根拠)

ユーザ確定方針: 「全てのライセンス機構は無力化。アクティベーションは無条件で通過。必要なら cracked リソース配置可」。

- 起動 critical 52 本のうちライセンス/アクティベーション系に該当するのは **G03 署名検証チェーンのみ** (実測: api_matrix 67 行に SLC/ActivationContext 等の OS ライセンス API 無し)。→ `WsConfig.trust` 既定 1 で**無条件成功** (「検証しない shim」): VERIFY=0、CN=`Image Line NV`、CLOSE=0 を呼出順どおり返す。
- cracked リソース (偽署名バイナリ等) は**不使用**: wasm 再ビルド物では Authenticode 署名自体が成立しないため、署名物を配置せず「検証しない」で足りる (EULA 上の評価は行わない — 事実整理のみ)。
- G04 登録状態の判定は engine 内部が vreg のレジストリ値を読んで行うものであり、winstubs は関与しない。ILRegKey 無し = Trial モードで**起動は継続**する (GATES G04 失敗時欄)。レジストリ値の制御 (`.reg` 取込入口 T9) は CAB-94/下流の担当。
- `trust=0` に下げると shimx 既定 (TRUST_E_NOSIGNATURE 0x800B0100) に委譲する経路も実測済み (retval_table `G03.20`) — 無効化「ON/OFF」が設定 1 つで切替可能。

## 7. 制限

- `--wrap` はリンクオプション: 下流 (lift closure 等) は `wrap_list.txt` 16 本を `-Wl,--wrap=` で渡す必要 (`scripts/build.sh` の wrap モード参照)。未指定なら shimx 既定挙動 (G03 失敗 / WebView2Loader も解決許可) になる。
- 新規 8 本のうち user32/uxtheme 系 7 本は **weak**: tools/gui (CAB-8) の強定義があればそちらが優先 (検収再実測 2026-10-10: gui 強定義 6/8、winstubs 由来の重複 0、GetProcAddress 不整合 0。強定義数は gui 側の実装進行で増減する — 本層は weak のため影響なし)。
- `GetSystemMetrics`/`SystemParametersInfoW` は 1920x1080 / Win10 100%DPI の固定近似。実 DPI への追従は gui 担当側の強定義で置換。
- `ShellExecuteExW/A` の wrap は Win64 構造体レイアウト決め打ち (`cbSize=112`, verb/file/params を +16/+24/+32 から読む)。
- `cpuid` は lift 側 `__asm_cpuid` が `winstubs_cpuid` を呼ぶ前提の返値表提供。IR 突合は `boot_final2.ll` の declare 42 本のみ (実結線は lift 側タスク)。
- 統計は 32bit カウンタの relaxed 加算 (MT で厳密な順序は保証しない。デバッグ用)。

## 8. 次タスク提案 (下流)

1. **CAB-102**: user32 ポンプの RING ABI 結線 — winstubs weak 10 本を強定義で置換 (`g_ws.pump_calls` 踏襲推奨)。
2. **lift 側 (m11 系)**: `__asm_cpuid` → `winstubs_cpuid` の実結線 + closure リンクへの `-Wl,--wrap=` 16 本適用 + `winstubs_init(0)` を boot glue に追加。
3. **T9 (G04)**: ILRegKey 等の `.reg` 取込入口 (vreg seed) — 正規ライセンス所持者が自分のキーで Registered 状態にできる入口。
4. **T11**: lift 後に "Registered to:" ログと Trial 制限の全容を実観察 (GATES 補足)。
5. **実起動観察**: ブラウザ実機で G03 チェーンの呼出順 (VERIFY→CLOSE) と `winstubs_loadlib_miss` ログを確認し、retval_table を実測で校正。

