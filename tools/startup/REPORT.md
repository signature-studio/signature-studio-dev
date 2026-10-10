# REPORT — H startup-process: FL 起動シーケンス / 子プロセス / ゲート / レジストリ / スタブ計画

日付: 2026-10-10 / 担当: H startup-process / 書込範囲: `tools/startup/` のみ / 再現: `bash tools/startup/startup.sh` (約 3 分, exit 0, `verify.py` 92/92 OK)

## 0. 結論 (数値は全て実測。推定は「推定」と明記)

1. **起動はホスト 11 ステップ + エンジン 13 ステップ = win 24 ステップ、mac 10 ステップ**。ホスト (FL64.exe 597,064 B / OsxFL 5.0 MB) は
   `THostInstance` (0x38 B, host version=1) を作り、エンジン唯一のエントリ **`CreateFruityInstance`** を 1 回呼ぶだけ。win は
   `CreateFruityInstance(0xC0, 0xEDE95A, host, &iface)` (定数ハンドシェイク)、mac は `(host, &iface)`。**メッセージループは win ではこの関数の内部** (`TApplication.Run` 0x86a660) にあり、mac では戻ってからホストが `iface->vtbl+200` (vtable オフセット 200 = slot25) を呼ぶ。→ STARTUP.md
2. **ブラウザ版で置換するのはホスト側のみ** (glue 約 20 行 + 仮想レジストリ + Win32 スタブ約 60 API + 専用 Worker 上のメッセージポンプ)。エンジンの 13 ステップは lift してそのまま動かす。**FL コードは無改変**。→ stub_plan.md
3. **外部起動点は PROCESSES.csv 30 行 (win 23 / mac 7)**。FL が自分で起動する外部実行体は win **11 種** (CreateProcessW 2 関数 / ShellExecuteA 1 / ShellExecuteExW 3 / ShellExecuteW 17 関数)。
   判定: 必要 0 / 不要 8 / 代替 15 / 対象外 4 / 後回し 3。**ブラウザ版で「プロセスとして必要」なものは無い**。FL64.exe 自身は CreateProcess を一切呼ばない (IAT で確認)。
4. **ゲートは 16 件 (GATES.md)**。起動をブロックし得るのは 8 件 (G01–G08) で、全て shim の戻り値か仮想レジストリ既定で通る。ネットワーク/認証/更新/WebView 系 (G09–G13) は **起動時には発火しない** (遅延タイマー or ユーザ操作起点)。
5. **レジストリ**: REGISTRY.csv 457 行。win のキー 46 本 (HKCU/HKLM; 内訳: コード上でリテラル確認 31 / ベース名からの推定 5 / インストーラ(NSIS)報告ベース 10)、エンジンが参照する値名 222 種 (FL の `TRegistry` 経由・全て REG_SZ 文字列; 例外は OS の `CurrentMajor/MinorVersionNumber` DWORD 2 値のみ)、`default` 列に ReadInt/ReadBool の既定値を抽出。
   mac は `~/Library/Preferences/Image-Line/reg.xml` (libwinbridge `TXmlRegistry`) + CFPreferences `com.image-line.shared`。seed は最小 18 値 (`data/vreg_seed.json`)。

## 1. 成果物

| ファイル | 内容 |
|---|---|
| `STARTUP.md` | 起動シーケンス (図+24 ステップ表+mac 10 ステップ)、host 構造体、引数/環境変数、設定ロード、初回アイドル、FS 参照 |
| `GATES.md` | G01–G16 (条件/VA/失敗時/ブラウザ方針) |
| `stub_plan.md` | ブート順、host glue 仕様、メッセージポンプ、VFS、スタブ表 (戻り値付き)、vreg、受入テスト、下流チケット T1–T11 |
| `PROCESSES.csv` | 30 行: 起動点/API/VA/トリガ/引数/判定/代替/確度 |
| `REGISTRY.csv` | 457 行: platform/hive/key/value/type/default/access/category/source/confidence |
| `data/vreg_seed.json` | 仮想レジストリ初期値 (18 値) |
| `startup.sh`, `scripts/*.py`, `ghidra_scripts/*.java` | 1 コマンド再現 (Ghidra decompile / 全関数 index / TRegistry 呼出点抽出 / CSV 生成 / 実バイナリ検証) |

## 2. 方法 (再現可能)

- **FL64.exe**: Ghidra 12.1.4 headless で WinMain と 8 関数を decompile (`fl64_decomp.c`)、`scripts/pedis.py` (capstone+pefile, RIP 相対の文字列/IAT 注釈) で逆アセンブル確認。
- **FLEngine_x64.dll**: `tools/m2` の Ghidra プロジェクト (59,009 関数) を**複製**して読取専用で処理 (元は無改変)。`CallTree.java` で全関数の callee/文字列/import を索引化 (`func_index.tsv`, 59,009 行)、
  `CallSiteStrings.java` で `TRegistry` メソッド (`0x5ae000–0x5b4000`) への全 call site 1,395 箇所から直前の `lea/mov/xor` で積まれた文字列・即値引数を抽出 → 在庫化 (呼出元 147 関数)。
- **mac**: OsxFL / libwinbridge / FLEngine の x86_64 slice を Ghidra で decompile (`fat_slice.py`)。
- **検証**: `scripts/verify.py` が Ghidra 無しで実バイナリから 92 項目を独立照合 (IAT・文字列・vtable・ハンドシェイク定数の機械語・ツール表 `0x15342a0`・CSV 整合)。`FORCE=1 startup.sh` で全工程再計算 → 92/92。

## 3. 主要な実測事実 (抜粋; 詳細は各 md)

| 項目 | 値 |
|---|---|
| FL64.exe | MSVC C++、`main`=`0x140007560` (WinMain)、Media Foundation 検査 → `THostInstance`(vtbl `0x140069d00`, 3 slot) → `0x1400062a0` (パス解決/署名検証/LoadLibrary) |
| エンジン export | win: `CreateFruityInstance`(VA 0x1375990)/`__dbk_fcall_wrapper`/`dbkFCallWrapperAddr` の **3 本のみ**。mac: 1 本のみ |
| 署名ゲート | 3 箇所 (host→engine `0x1400062a0`、engine 自己検査 ×2 `0x1375990`)。署名者名 == "Image Line NV" → 不一致 -2 |
| エンジン所在 | `<exeDir>\FLEngine_x64.dll` → 無ければ `HKCU/HKLM(WOW64_32)\Software\Image-Line\Shared\Paths\FL Studio engine` (値=ファイルパス)。`Builds\` があれば `ShowEngineChoice` |
| 登録情報 | `…\Registrations\FL Studio 26.1\ILRegKey` (HKCU→HKLM)。マシン識別コード (`MachineGuid`+`GetComputerNameExW`+`SHGetFolderPathW`) が **24 関数にインライン展開** |
| フラグ | `byte[0x14f84a8]` は `0x10c7cd0` だけが書込。読み側: bit0=0→"Registered to: <name>"、1→"Please remember to register"。bit1→Fire edition |
| ユーザデータ | `Shared data`(HKCU Paths) → 無ければ `SHGetFolderPath(CSIDL_PERSONAL)\Image-Line\`。書込テスト `testpermissions.tmp`。env `FLStudio<k>Data` 等を設定 |
| 単一インスタンス | `FindWindowW("TFruityLoopsMainForm")` + WM_COPYDATA |
| ツール表 (engine `0x15342a0`) | id0 ControlCreator / id1 fldiagnostic / 1000 CopyLicenseToAllUsers / 1001 CloudBounceConsole / 1002 RemoveLicenses |
| WebView2 | engine が `LoadLibraryW("WebView2Loader.dll")` を**動的**に行う (`0xbe3520`)。`flHelper` JS コールバック 23 種。画面= FL CLOUD Sounds / Gopher+MCP / Help(index_offline.html)。FL64.exe は WebView2 を使わない |
| Edge 201 MB | `MicrosoftEdgeUpdateSetup.exe` = WebView2 Runtime を入れるインストーラ同梱物。実行時には使われず、ブラウザ版では不要 |
| MCP | `MCPTools.pyc` を組込 Python が実行する**プロセス内ツール** (`tools/call` JSON)。待受ポート無し。外部 AI (Gopher) とセットで対象外 |
| クラッシュレポータ | プロセス内 (`0x11f0540`)。ログ `<UserData>\Crash\`、Send=HTTP upload、再起動=`fldiagnostic /restartfl`。Breakpad/Crashpad/MiniDumpWriteDump の文字列・import は無し |

## 4. 未解決・ブロッカー (正直に)

1. **ライセンス: Trial 判定の実体と制限範囲は未確定**。`0x14f84a8` のビット意味は読み側から bit0/bit1 のみ確定、bit0=Trial は**推定**。ILRegKey 無しの挙動は lift 後の観察でしか確定できない (T11)。
   さらに、ILRegKey の検証は MachineGuid 等を含むマシン識別コードに依存すると**推定** (インライン24 関数。未解読)。
2. **起動必須アセットの最小集合は未計測** (win 全展開 2.3 GB)。`open()` トレース待ち (T5, FLEngine が動いてから)。
3. 表のうち `[+0x20/+0x28] = 0x140069820` (host の 2 ポインタ) と host vtbl の呼ばれ方は、静的には用途を確定できず lift 後 trace が必要 (T1)。
4. 「section via wrapper」型の設定値 (REGISTRY.csv で `key` が `(section via wrapper…)`) は親キー名を静的に確定できず**候補表示**に留めた (値名 113 種)。実キーは lift 後に vreg の open ログで確定できる。
5. `PluginManager` の win 版引数・`ilbridge` のコマンドライン、`CloudBounceConsole` を呼ぶ側のパス導出は mac 文字列/静的推論による (W03/W09 の `evidence` は `v/s`)。
6. 他担当の `tools/m11` (DllMain closure lift) は進行中で、本タスクの S09/S12–S22 はその完了待ち。M11 の成果物には触れていない。

## 5. ユーザ依頼事項

1. **(任意) 正規ライセンス所持なら、Image-Line アカウントからエクスポートした登録ファイル (`.reg`) を `~/ダウンロード` に配置** — T9/T11 で Trial 以外の挙動を観測するための入力。無ければ Trial 前提で進める (偽造・生成はしない)。
2. 外部通信が必要な機能 (FL Cloud / Gopher AI / 認証 / 更新) を「完全に無効のまま」で良いか確認 (現計画は WinInet 常時オフライン)。
3. ブラウザ版の Help (`Help/index_offline.html`) を優先度どこに置くか (T8 は任意扱い)。

## 6. 次タスク提案 (下流チケット)

T1 startup-glue (THostInstance+CreateFruityInstance+終了処理) / T2 vreg (仮想レジストリ shim, seed, IndexedDB) / T3 win-stubs-startup (約 60 API の fail-soft) /
T4 wininet-offline / T5 vfs-layout+asset-trace / T6 message-pump (SAB ring, Worker ブロック) / T7 cpython-wasm (任意) / T8 help-viewer (任意) /
T9 license-import (任意・ユーザ起点) / T10 crash-restart / T11 license-observation。内容と依存は `stub_plan.md` §8。
推奨順: **T2 → T3 → T1 (m11 の DllMain closure 後) → T6 → T5 → T11**。

## 7. 参照した既存資産 (読取のみ)

`analysis/win64/REPORT.md`, `analysis/mac/REPORT.md` (記述のうち「FL64.exe が WebView2 を使う」は**誤り**で、WebView2 はエンジン側に動的束縛される。「Electron/CEF 無し」は正しい),
`tools/m2/{REPORT.md,SHIM_INVENTORY.md,work/ghidra_dll}`, `tools/m11/` (存在確認のみ)。既存 REPORT の「registry/ファイル関連付けは Web では memory/cookie」は、本調査で
**エンジンの全設定が REG_SZ の TRegistry 経由**と判明したため、cookie ではなく **vreg (IndexedDB)** を推奨に修正。
