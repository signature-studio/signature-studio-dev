# KH-168 (#5546): HeartCore.core_64 の Wine 実行環境と PE ロードの実測

> **正本**: 本ファイル (KH-168 の測定値)。親は #5118 (KH-142)。実行 trace (CFG 経由 call 14 件) は #5118 の残り。

## 1. 結論

- Wine 9.0 (Ubuntu apt) で `HeartCore.core_64` の **LoadLibrary (PE ロード・import 解決) は成功**。全 144 export が解決できた。
- `ACFGetSDKVersion()` は 0 を返す。
- **初期化 `ACFStartup()` は未達**。HeartCore 内部で page fault (読み取り) し Wine が落ちる。受入の「初期化までが通る」は満たさず、残りは子 #5556 へ分離。

## 2. 素材と入力

- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64`。
- `HeartCore.core_64`: 76,642,304 B、sha256 `d55ce8b4c0ad7ebedf1a4a1f74443a91d255596be887a514e54269ec8751441e`、PE32+ DLL x64。
- export 一覧 144 名 (`exports.txt`。`GetPluginFactory_<id>`・`VSTPluginMain_<id>`・`ACF*`・`KHSUnlock` 等)。一覧の生成元 (コマンド) は本 PR で記録していない。各名は下記ローダーの `GetProcAddress` で解決済み (§4)。DLL の export 表そのものとの突合 (`objdump -p` 等) は未実施。
- import DLL 17 本 (KERNEL32・USER32・ole32・bcrypt 等)。すべて Wine 側で解決された。

## 3. 方式

- Wine: `apt install wine64` (9.0~repack-4build3)。`WINEPREFIX` は runner の temp に新規作成。
- ローダー `loader.c` (MinGW `x86_64-w64-mingw32-gcc` でビルド): `LoadLibraryExA` → `exports.txt` の全 export を `GetProcAddress` → `ACFGetSDKVersion` / `ACFStartup` / `ACFShutdown` を呼ぶ。
- 再現: `tools/targets/kilohearts/runtime_wine/` の `loader.c`・`exports.txt`。DLL を `HeartCore.core_64` として同じ作業dir に置き、`wine loader.exe HeartCore.core_64 exports.txt`。

## 4. 実測 (commit は本 PR の HEAD)

| 項目 | 結果 |
|---|---|
| LoadLibraryExA | OK (handle 取得) |
| import 解決 | OK (ロード成功に含まれる) |
| export 解決 | **144 / 144** (`MISSING` 0 件。`__ref__` を含む一覧の全名が `GetProcAddress` で解決) |
| `ACFGetSDKVersion()` | 0 |
| `ACFStartup()` | **page fault で Wine 落ち** (未達。ログ `run1.log`) |

`ACFStartup` の失敗箇所: `ACFStartup` の呼出 (loader +0x165b) → HeartCore の `0x1800211d7`〜の関数 → `call (%r9)` で読めないアドレスを参照 (`0x20601345598`)。
完全なログは `runtime_wine/run1.log`。
> **訂正 (KH-169 #5556)**: 上の「間接 call の宛先が未解決」は誤り。原因は loader が `ACFStartup()` を引数なしで呼んだこと。`ACFStartup(NULL)` は戻り、`ACFStartup(1)` で同じ fault が出る。詳細は `REPORT_APPENDIX_5556.md`。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ACFStartup` の page fault (HeartCore 内部の間接 call の解決) | 初期化を通せず、lift 前の実行 trace が取れない | #5556 (子) |
| 初期化後の trace (#5118 受入 1) | 14 件の確定が未了 | #5118 (親の残り) |
