# KH-169 (#5556): HeartCore.core_64 の ACFStartup() page fault の原因切り分け

> **正本**: 本ファイル (KH-169 の測定値)。親は #5546 (KH-168 の測定は `REPORT_APPENDIX_5546.md`)。

## 1. 結論

- 前回 (`REPORT_APPENDIX_5546.md` §4) の「HeartCore 内部の間接 call の宛先が未解決」は**誤り**。fault の直接原因は、旧 loader が `ACFStartup()` を引数なしで呼び、未初期化の `rcx` を HeartCore に渡していること (実測は下記 §4)。
- 引数 `NULL` では `ACFStartup` が Wine 上で戻る (戻り値 0)。引数 `1` では同じ page fault が再現する (`0x1` を deref)。
- **受入 (1) 「初期化まで通ること」は未達**。`NULL` で戻ることは初期化の成功を示さない (null チェックで何もせず抜けた可能性がある)。正しい引数の型・仕様と、初期化完了の判定は未確定。
- 受入 (2) 原因の分類 (確定部分): 直接原因は**呼出側が引数を渡していないこと**。HeartCore 内部の間接 call の未解決ではない。正しい引数の仕様は未確定のため、「HeartCore の欠陥か」は判定していない。

## 2. 素材と入力

- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。
- sha256 `d55ce8b4c0ad7ebedf1a4a1f74443a91d255596be887a514e54269ec8751441e` (`REPORT_APPENDIX_5546.md` と一致)。
- 展開先は `tools/targets/kilohearts/work/` (gitignore)。Wine 9.0 (Ubuntu apt `wine64`)・MinGW `x86_64-w64-mingw32-gcc` (apt `gcc-mingw-w64-x86-64`)。

## 3. 方式

- `loader_arg.c` (本 PR で commit): `LoadLibraryExA` → `GetProcAddress("ACFStartup")` → 引数 `argv[2]` (16 進) を渡して呼ぶ。引数を指定しないときは `0`。
- 再現: `wine loader_arg.exe HeartCore.core_64 0` (NULL) と `... 1` (非 NULL)。`WINEDEBUG=-all`。

## 4. 実測 (commit は本 PR の HEAD)

| 呼出し | 結果 | 備考 |
|---|---|---|
| `ACFStartup(NULL)` | 戻る・戻り値 0・exit 0 | `run_arg0.log` 相当 |
| `ACFStartup(1)` | `page fault on read access to 0x1` (exit 5) | `0x180263130` が `rsi`(引数) を deref |
| `ACFStartup()` (loader 旧版・引数なし) | `page fault` で落ちる (`0x20601345598` 参照) | `REPORT_APPENDIX_5546.md` §4 の再現 |

### 逆アセンブル (HeartCore.core_64, ImageBase 0x180000000)

- `0x1800211c0` `ACFStartup` → `call 0x1802606e0` → `call 0x180263130` (引数 `rcx` を渡す)。
- `0x180263130`: `rsi = rcx`。`rsi == NULL` なら何もせず戻る (`test rsi,rsi; sete dl` → `jne 0x18026317c`)。非 NULL なら `0x180264b40(rcx=確保済み object, rdx=rsi)` を経て `call [r9]` (`r9 = [rdx]`)。
- fault 箇所 `0x180264bad` の `call QWORD PTR [r9]` は、非 NULL 引数の先頭 qword を vtable として呼ぶ。引数 `1` では `r9 = [1]` で read fault (`0x1`)。
- 旧 fault の `0x20601345598` は、旧 loader が引数なしで呼んだ際の残留 `rcx` 由来の値 (未初期化)。`0x180260710` (`movabs rax, 0x20601345598; mov [rcx], rax`) が書く定数で、image 内に再配置 (.reloc) の対象は無い。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ACFStartup` の正しい引数 (型・仕様) が未確定。`NULL` で戻ることは初期化完了を意味しない | 初期化後の trace (#5118 の受入 1) を取れない | 本 PR の後続 (次 run・#5556 の残り) |
| `ACFStartup(NULL)` の戻り値 0 が「初期化した」か「何もせず抜けた」か未検証 | 受入 (1) の判定 | 同上 |
| `ACFGetSDKVersion()` 以外の SDK 関数の呼出順 (`ACFRegisterComponent` 等) | 初期化の全体像が不明 | 同上 |
