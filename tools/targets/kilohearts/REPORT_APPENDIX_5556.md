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

## 6. 追加測定 (KH-169 第 2 run・commit は本 PR の HEAD)

前回 §5 の未解決「正しい引数の型」を、逆アセンブルと偽オブジェクトで切り分けた。

### 6.1 `ACFStartup` の引数の読み

- `0x1800211c0` (`ACFStartup`) は `call 0x1802606e0` の後に `call 0x180263130` を呼ぶ。引数 `rcx` は `rsi` に保持される。
- `0x180263130`: `rsi == NULL` なら `0x18026317c` へ進み何もせず戻る。非 NULL なら `0x180264b40(rcx=確保済み object, rdx=rsi)` を呼ぶ。
- `0x180264b40`: 引数 `rdx` の先頭 qword を vtable として `call [r9]` (`r9 = [rdx]`、`rdx` の 2 番目の引数は IID `0x181429538`、`r8` は出力先) を呼ぶ。`QueryInterface` の形。失敗 (`eax != 0`) なら `0x180264c9c`、成功なら出力を次段で使う。

よって引数は「`QueryInterface` を持つ COM 風オブジェクトへのポインタ」と読める。

### 6.2 偽オブジェクトによる実測

`runtime_wine/loader_com.c` (新規): vtable[0] に `QueryInterface` を立てた 3 slot の偽オブジェクトを渡す。

| 呼出し | 結果 | 備考 |
|---|---|---|
| `wine loader_com.exe HeartCore.core_64` | `QueryInterface called self=… iid=00006ffff5d59538` → 戻り値 `0` (`0x0`)・exit 0 | IID は rdata `0x181429538` の 16 byte。GUID に直すと `382B6A96-7FD0-11D6-BCFE-00306542A024` (バイト列から計算) |

- 偽 QI は `E_NOINTERFACE` (`0x80004002`) を返した。それでも `ACFStartup` は 0 で戻った。
- よって、戻り値 0 は「QI 成功で初期化した」ことを示さない。失敗経路 (`0x180264c9c`) で 0 を返す可能性がある。未確定。
- 初期化の判定に必要な「QI 成功時の後続」(`0x180264bb8` 以降の `ACFRegisterComponent` 相当) は未実測。

### 6.3 未解決 (本 run で残したもの)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| IID `0x181429538` (GUID 382B6A96-7FD0-11D6-BCFE-00306542A024) の名前を特定できていない。Web 検索は本 run で失敗 | QI 成功時に必要な interface の型が決まらない | #5556 (本 issue の残り) |
| QI 成功時の後続 (`0x180264bb8` 以降) の実測 | 受入 (1) の初期化成功の判定 | #5556 (本 issue の残り) |

## 7. 追加測定 (KH-169 第 3 run・QI 成功時の後続)

前回 §6.3 の未解決「QI 成功時の後続 (`0x180264bb8` 以降)」を、QI が S_OK を返す偽オブジェクトで実測した。

`runtime_wine/loader_qi_ok.c` (新規): `QueryInterface` が `S_OK` を返し、出力に 16 スロットの偽 vtable を渡す。各スロットは呼ばれた引数を記録して `0` を返す。

| 呼出し | 結果 |
|---|---|
| `wine loader_qi_ok.exe HeartCore.core_64` | `QI … -> S_OK` → slot[3] を **3 回** → slot[2] を 1 回 → `ACFStartup() = 0`・exit 0 |

**実測 (第 3 run・測定 commit は本ファイル末尾の検証情報を参照)**:

- slot[3] は **3 回**呼ばれる。3 回とも `a` は同じ `0x…9558` (`88882C2D-EBBC-42EF-C0AB-8981B0BD0CCA`)。変わるのは `c` (`0x…9568`・`0x…9578`・`0x…9588`)。
- slot[2] は 1 回 (`a`=`0x6fffff053120`・`b`=2)。
- `ACFStartup()` の戻り値は 0。

GUID の変換 (PE の `.rdata` を直接読んで変換):

| rdata アドレス (ImageBase 0x180000000) | GUID |
|---|---|
| `0x181429538` | `382B6A96-7FD0-11D6-BCFE-00306542A024` (QI の IID) |
| `0x181429558` | `88882C2D-EBBC-42EF-C0AB-8981B0BD0CCA` (slot[3] の `a`) |
| `0x181429568` | `96D42C2D-EBBC-41EF-B0AB-9991A0ED0CCA` (slot[3] の `c` の参照先) |
| `0x181429578` | `A207EE9E-B442-11E4-A71E-12E3F512A338` (同上) |
| `0x181429588` | `12BEA399-9A4F-4353-8098-3916FA71898D` (同上) |

**生ログ (実装 run の stdout 全行・`WINEDEBUG=-all`・stderr 空・exit 0)**。ASLR で handle・スタック由来の値は実行ごとに変わるが、件数と `a` は同じ:

```
LOAD OK handle=00006ffff4930000
QI self=00007ffffe2ffea0 iid=00006ffff5d59538 -> S_OK
slot[3] self=0000000140009080 a=00006ffff5d59558 b=0000000000000000 c=00006ffff5d59568
slot[3] self=0000000140009080 a=00006ffff5d59558 b=0000000000000000 c=00006ffff5d59578
slot[3] self=0000000140009080 a=00006ffff5d59558 b=0000000000000000 c=00006ffff5d59588
slot[2] self=0000000140009080 a=00006fffff053120 b=0000000000000002 c=00007ffffe8945f0
ACFStartup() = 0 (0x0)
```

(同じ commit で reviewer 側の実行 `handle=00006ffff49b0000` でも slot[3] 3 回・`a`=`…9558` の同一結果を得た。)

### 検証情報 (本 PR の時点)

- 素材: `plugins-kilohearts.tar.zst` → `Kilohearts Offline Installer.zip` → `inst/payload.dat` (zip・store) → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。`zstd -dc … | tar -x` と `unzip` で展開 (`tools/targets/kilohearts/work/rerun/`・gitignore)。
- `HeartCore.core_64` の sha256: `d55ce8b4c0ad7ebedf1a4a1f74443a91d255596be887a514e54269ec8751441e` (§2 と一致)。
- Wine: `wine-9.0 (Ubuntu 9.0~repack-4build3)` (apt `wine64`・`/usr/bin/wine`)。MinGW: `x86_64-w64-mingw32-gcc (GCC) 13-win32` (apt `gcc-mingw-w64-x86-64`)。
- ビルド: `cd tools/targets/kilohearts/runtime_wine && x86_64-w64-mingw32-gcc -O0 -o loader_qi_ok.exe loader_qi_ok.c` (`loader_qi_ok.exe` sha256 `d0ab08a7…`)。
- 実行: `WINEDEBUG=-all wine ./loader_qi_ok.exe "$PWD/HeartCore.core_64"`。exit 0・stderr 空。stdout は §7 の生ログと同じ 7 行。
- 検証起点 commit: `60c94d658`。`git diff 60c94d658 HEAD -- tools/targets/kilohearts/runtime_wine` は**空** (差分 0)。`tools/targets/kilohearts` 全体の差分は本 PR の REPORT のみ。
- QI の IID `0x181429538` は `382B6A96-7FD0-11D6-BCFE-00306542A024` (§6.2 と一致)。
- QI 成功時も `ACFStartup` は 0 で戻る。戻り値 0 は初期化成功の根拠にならない (§6.2 と同じ結論)。slot の戻り値を変えた場合の分岐は未測定。

### 未解決 (本 run の時点)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| IID を除く 4 つの GUID (`88882C2D…`・`96D42C2D…`・`A207EE9E…`・`12BEA399…`) の interface 名 (IID `382B6A96…` は §6.2 で同定済み) | slot の型が決まらず、受入 (1) の初期化判定に使う戻り値の意味が決まらない | #5556 (本 issue の残り) |
| slot の戻り値を変えたときの分岐 (`0x180264bb8` 以降の `ACFRegisterComponent` 相当の有無) | 受入 (1) の判定 | #5556 (本 issue の残り) |
| Web 検索 (GUID の名前引き) は本 run で失敗 | GUID の名前を外部から確定できない | #5556 (本 issue の残り) |

## 8. 追加測定 (KH-169 第 4 run・戻り値の分岐)

前回 §7 の未解決「slot の戻り値を変えたときの分岐」を、`runtime_wine/loader_branch.c` で測ろうとした。QI の戻り値 (argv[2]) と slot[2]・slot[3] の戻り値 (argv[3]) を変えられる。

測定 commit: `2909717fc` (`loader_branch.c` を追加した commit)。

**注意: 下表は未検証の記録 (生ログ無し)。** 第 4 run で得た値を記したもので、stdout の生ログも `loader_branch.exe` の照合も無い。本 run では wine・MinGW・`plugins-kilohearts` 素材が無く、再実行できていない。採取されるまで実測の裏付けとして扱わない。

| QI 戻り値 | slot 戻り値 | slot[3] 呼出し | slot[2] 呼出し | `ACFStartup()` (未検証) |
|---|---|---|---|---|
| `0` (S_OK) | `0` | 3 回 | 1 回 | 0・exit 0 |
| `0` (S_OK) | `1` | 3 回 | 1 回 | 0・exit 0 |
| `0` (S_OK) | `80004005` | 3 回 | 1 回 | 0・exit 0 |
| `80004002` (E_NOINTERFACE) | (呼ばれない) | 0 回 | 0 回 | 0・exit 0 |

- 未検証の記録の上では、slot の戻り値を変えても後続の呼出し回数は変わらず、QI 失敗時も 0 で戻る。
- 結論 (未検証): 記録が正しければ、`ACFStartup` の戻り値 0 は QI・slot の成否に依存しない。戻り値で初期化の成否を判定できない可能性がある。確定はしていない。受入 (1) の「初期化まで通ること」は未達のまま。

### 8.1 GUID の名前

- Web 検索 (`382B6A96…`・`88882C2D…`・`96D42C2D…` を含むクエリ) は本 run でも失敗 (`Web search cancelled`)。
- `strings` で `HeartCore.core_64` を検索したが、GUID と型名の対応は取れなかった (RTTI の型名のみ)。名前は未特定。

### 8.2 検証情報

- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` (zip) → 内の `HeartCore.core_64` (76,642,304 B)。sha256 `d55ce8b4…1441e` (§2 と一致)。
- 注意: `windows.zip/1ccb1df8c8f10745` 自体は `HeartCore.core_64` ではなく、プラグイン群の zip。そこから取り出す必要がある。
- `loader_qi_ok.c` の再現 (本 run): LOAD OK・QI S_OK・slot[3] 3 回・slot[2] 1 回・戻り値 0・exit 0 (§7 と一致)。これは §7 の生ログの再現で、`loader_branch` の結果ではない。

### 8.3 再現情報と未採取の範囲

- ビルド: `x86_64-w64-mingw32-gcc -O0 -o loader_branch.exe loader_branch.c` (`runtime_wine/` で実行)。第 4 run の `loader_branch.exe` sha256 `16ab2917…` は記録値。本 run では再ビルドしていないため照合していない。
- 実行: `WINEDEBUG=-all wine ./loader_branch.exe "$PWD/HeartCore.core_64" <QI の戻り値 16 進> <slot 戻り値 16 進>`。表の 4 条件は `(0 0)`・`(0 1)`・`(0 80004005)`・`(80004002 0)`。第 4 run では全条件 exit 0・stderr 空と記録されている (未検証)。
- 素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` (zip) → 内の `HeartCore.core_64` (76,642,304 B)。sha256 `d55ce8b4…1441e` (§2 と一致)。`windows.zip/1ccb1df8c8f10745` 自体は `HeartCore.core_64` ではなく、プラグイン群の zip。そこから取り出す必要がある。
- stdout の生ログ (各条件の全行): **未採取**。第 4 run の stdout は保存されていない。再採取の条件は素材 `plugins-kilohearts`・Wine 9.0・MinGW `x86_64-w64-mingw32-gcc`。採取後にここへ全行と `loader_branch.exe` の sha256 を追記する。
- 参考: `loader_qi_ok.exe` (QI S_OK・slot 戻り値 0) の §7 の生ログ (7 行) は残っている。`(0 0)` 条件の土台になるが、`loader_branch` 自体の生ログではない。
