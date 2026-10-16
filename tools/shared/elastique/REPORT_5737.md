# tools/shared/elastique REPORT — wrap 上位 5 関数の実引数の同定 (T-SH-150 / #5737)

親: #3386。素材 `fl-win64` (FL 本体 `block00031_PE.bin`、.text RVA 0x401000)。mac 版は対象外。所有者限定 tier (D20)。
前提: `REPORT_4396.md` (wrap 5 件の同定)。本 REPORT は、その 5 関数の呼出元で wrap に渡す引数を静的に読む。
export の呼出し・`run()` の差し替えは #3386 に残す。

## 0. 結論

| 項目 | 結果 |
|---|---|
| 受入 (上位 5 関数の呼出元で、export に渡す引数 rcx・rdx・r8・r9 を静的に読む) | **部分達成**。rcx・rdx は全呼出元で出どころを読めた (§2.1〜2.3 の表は export 側の引数)。r8 は wrap が export 直前に設定せず、wrap が呼ぶ loader (`0x677d10`) の後の値になるため **静的には確定しない** (§2.6)。r9 は ElPro (`0x677f60`) と ElProV3 (`0x677fb0`) が表経由で、表は両者で異なる。ElResampleSource・Auftakt は設定しない (§2.1〜2.3)。 |
| 同定の方式 | 静的。capstone で逆アセンブルし、`call`/`jmp` の直接呼出元を列挙 (`fl_wrap_disasm.py`)。動的実行は行っていない |
| 読み直しで見つかった REPORT_4396 の誤り | §4 |

## 1. 直接呼出元 (測定)

`python3 tools/shared/elastique/fl_wrap_disasm.py callers 677f60 678010 c67520 a97780 67d5a0 c67730 c69d10 c69d60`

| 関数 | 直接呼出元 |
|---|---|
| wrap `0x677f60` | `0xa977d1` (in `0xa97780`) |
| wrap `0x678010` | `0x67d60d` (in `0x67d5a0`) |
| wrap `0xc67520` | `0xc67789` (in `0xc67730`) |
| `0xa97780` (wrap 呼出し元) | `0xa9830d`・`0xc65a29`・`0xc65bb2`・`0xc7a2cf`・`0xc7be49` |
| `0x67d5a0` | `0x67d556` (in `0x67d520`) |
| `0xc67730` | `0xc6c533`・`0xce314f` |
| `0xc69d10` | `0xc69f63` (in `0xc69f30`) |
| `0xc69d60` | `0xc69f28` (in `0xc69ef0`) |

既知の 3 件 (`0xa977d1`・`0x67d60d`・`0xc67789`) は REPORT_4396 と一致する。

## 2. 呼出元ごとの実引数

表記: rcx・rdx・r8・r9 は呼出し時点の値。`[sp+N]` はスタック引数 (第 5 引数以降)。

### 2.1 `0xa97780` の 5 呼出元 (wrap → `0x677f60` = ElPro / `0x677fb0` = ElProV3)

`0xa97780` 自身の引数は `rcx`=obj (`rbx`)・`edx`=`esi`・`r8d`・`xmm3`・`[sp+0x60]`。obj (`rcx`) は ElPro への呼出しで `ecx` が上書きされるため export には渡らない。

ElPro (`0x677f60`) から export への引数は次の通り。wrap 内で `mov ecx,ebx`・`mov edx,esi`・`mov r9d,edi` (`0x677f86`〜`0x677f8d`) として渡し、r8 は設定しない。`ebx`=wrap の `ecx`=`0xa97780` の `esi`=`0xa97780` の `edx`、`esi`=wrap の `edx`=`0xa97780` の `r8d`、`edi`=wrap の `r9d` (`0xa977cc` で作った表値)。

| 呼出元 | export の rcx (= `0xa97780` の `edx`) | export の rdx (= `0xa97780` の `r8d`) | export の r8 | export の r9 (表。経路で分岐 §2.5) | 備考 |
|---|---|---|---|---|---|
| `0xa9830d` | `0x100` (`0xa982ee`) | `[rax+0x74]` の byte (`rax`=`[rbp+0x48]`、`0xa982f7`) | 未設定 (loader 後の値) | ElPro なら `0xa48a23[添字]`、ElProV3 なら `0xa489fd[添字]` (添字 = `[sp+0x60]` = `[rbp+0x60]` の dword) | 即値は `[sp+0x20]` = `[rbp+0x60]` の dword |
| `0xc65a29` | `0x100` (`0xc65a0a`) | `[rax+0x74]` の byte (`rax`=`[rbp+0x60]`、`0xc65a13`) | 同上 | 同上 | `[sp+0x20]` = 即値 1 |
| `0xc65bb2` | `ebx` (`min(rbx, 0x100)`、`0xc65b69`〜`0xc65b72`。§2.7) | `movzx r8, byte ptr [rax+0x74]` の値 (`rax`=`[rbp+0x60]`、`0xc65b9c`) | 同上 | 同上 | `[sp+0x20]` = 即値 1 |
| `0xc7a2cf` | `0x100` (`0xc7a2b1`) | `[rax+0x74]` の byte (`rax`=`[rbp+0x70]`、`0xc7a2ba`) | 同上 | 同上 | `[sp+0x20]` = `[rbp+0x5c]` の dword |
| `0xc7be49` | `0x100` (`0xc7be29`) | `[rax+0x74]` の byte (`rax`=`[rbp+0x58]`、`0xc7be32`) | 同上 | 同上 | `[sp+0x20]` = `ebx-1` |

r9 の表の添字は `0xa977c7` の `movsxd r8, dword ptr [rsp+0x60]` で、ElPro 経路 (`0xa977b6`) に入るのは添字 (`eax`) が 0〜15 かつ `1 << (eax & 0x7f)` と `[rip+0x98]` の word の `test` が成立するときだけ (`0xa9778f`〜`0xa977ab`)。それ以外は `al=0` (`0xa977b0`) になり、`je 0xa977dc` で **ElProV3 経路** に進む (§2.5)。ElPro 経路で `r9` を 0 にする分岐は無い。

ElProV3 (`0x677fb0`) の経路は、`0xa977dc`〜`0xa977f2` で `ecx=esi`・`edx=r8d`・`r9 = byte [0xa489fd + r8]` (添字は同じ `[rsp+0x60]`) を作るところまでを確認した。`0x677fb0` の export 呼出し部 (`0x677ff8` 以降) は本 fix では読んでいない。

### 2.2 `0x67d5a0` の呼出元 `0x67d556` (wrap `0x678010` = ElResampleSource)

| export の rcx | export の rdx | export の r8 | export の r9 | 備考 |
|---|---|---|---|---|
| `rbx` (obj。`0x67d607` の `mov rcx,rdx`、`0x67d5c8` で `rdx=rbx`) | `movzx r8, byte ptr [rbx+0xa0]` の値 (`0x67d60a` の `mov edx,r8d` で wrap の `edx` に入る) | 未設定 (loader 後の値) | 未設定 (`0x67d5a0` の呼出し時の値を継承。静的に確定しない) | `[sp+0x20]`=`eax` (`[rbx+0x38]==2` で 0 / それ以外 1)・`[sp+0x28]`=float 定数 (未確認)・`[sp+0x30]`=`0x2b2a`・`[sp+0x38]`=0 |

wrap `0x678010` は export 呼出し前に `r8`・`r9` を設定しない (`0x678067`〜`0x6780a2`)。export の第 5 引数以降は、wrap が `[sp+0xa0]`・`[sp+0xa8]`・`[sp+0xb0]`・`[sp+0xb8]` から `[sp+0x20]`・`[sp+0x28]`・`[sp+0x30]`・`[sp+0x38]` に再格納した値で、上位 `0x67d5a0` が設定した値そのものになる。

### 2.3 `0xc67730` の呼出元 (wrap `0xc67520` = Auftakt)

Auftakt (`0xc67520`) から export への引数 (wrap 内 `0xc67592`: `mov ecx,ebx`・`mov edx,esi` で呼ぶ slot)。

| 呼出元 (`0xc67730`) | export の rcx | export の rdx | export の r8 | export の r9 |
|---|---|---|---|---|
| `0xc6c533` | `eax` = `0x40c660([rbx+0x7c])` の戻り値 (`0xc67782`〜`0xc67789`) | `movzx rdx, byte ptr [rbx+0x74]` (`0xc67784`。`rbx`=`[rbp+0x60]`=`0xc67730` の `r8` 引数 = `[rax+0x11e8]`、`rax`=`[[rbp+0x30]+0x778]`、`0xc6c521`〜`0xc6c52c`) | 未設定 (loader 後の値) | 未設定 |
| `0xce314f` | 同上 | `movzx rdx, byte ptr [rbx+0x74]` (`rbx`=`[rax+0x11e8]`、`rax`=`[rbp+0x28]`) | 未設定 (loader 後の値) | 未設定 |

`0xc67730` の `dl` (`0xc67741` で `[rbp+0x58]` に保存) は、`0xc67748`〜`0xc67757` の `0x410320` を呼ぶ条件分岐にしか使われず、wrap の `edx` には入らない。wrap の `edx` は `0xc67784` の `movzx` で決まり、`rcx` は `0xc67782` の `ecx = eax` で決まる。wrap は `r8` を設定しない。

### 2.4 `0xc69d10` の呼出元 `0xc69f63` と `0xc69d60` の呼出元 `0xc69f28`

- `0xc69f63`: `rcx = [rbp+0x50]+0x10`・`xmm1 = [rax+0x7c]` (double→float)・`r8 = byte [rax+0x74]`。`0xc69d10` は `r8d` を `esi` に保存し、`call [0xa4eb50]` (`0x16b8890` 相当の SolPitchAn 経路) に `r8d` を渡す。
- `0xc69f28`: `0xc69d60` は `rcx` と `r8` を一切使わず、`0xc69c10` の戻り (`al`) が真のとき `call [0xa4eb22]` (`0x16b8898` = SolPitchAn_CreatePitchMarks) を呼ぶ。

### 2.5 r9 の出どころ (`0xa97780` 内の wrap 直前)

`0xa97780` の中で、wrap の直前に `r9` を作る命令は次の通り (`0xa977c0`〜`0xa977cc`、ElPro 経路)。

```
lea rax, [rip + 0xa48a23]      ; 表
movsxd r8, dword ptr [rsp+0x60] ; 添字 = 第 5 引数 (呼出元の [rbp+0x60] の dword)
movsx r9, byte ptr [rax + r8]  ; r9 = 表[添字] (符号拡張)
call 0x677f60
```

表 (`0xa48a23`) の先頭 16 byte は `ff 00 03 00 ff ff 00 02 04 05 00 01 02 06 07 08`。添字は呼出元の `[rbp+0x60]` の dword (即値ではない) なので、`r9` は実行時の値で決まる。`cmp eax,0xf; ja` (`0xa9778f`) は、添字 (`eax`) が 15 を超えるとき `0xa977b0` に飛んで `al=0` にする。その後 `test al,al` の結果で ElPro 経路 (`0xa977b6`) か ElProV3 経路 (`0xa977dc`〜) に分かれる。ElProV3 経路は表 `0xa489fd` を同じ形で使う。

### 2.6 r8 が確定しない理由 (ElPro・ElProV3 の wrap)

wrap `0x677f60`・`0x677fb0` は、`0x677d10` (loader) を呼んだ後に `call [slot]` を呼ぶ。`0x677f60` 内で `r8` を設定する命令は無い。`call 0x677d10` の中では `call 0x4235f0` と `call rax` が走るため、`r8` は loader の内部で書き換わりうる。`0x4235f0` の名前経路は `xor r8,r8` (`0x423631`) を含む。したがって export に渡る `r8` は、呼出元 `0xa97780` の `r8` (`[rax+0x74]` の byte) とは一致しない可能性があり、この読みでは確定できない。確定には loader 後の `r8` を動的に見る必要がある。

### 2.7 同定できなかった値

- `[rax+0x11e8]` (Auftakt 経路の `r8`) と `[rax+0xa0]` (ElResampleSource 経路の `r8`) は、FL 本体の実行時オブジェクトの値。静的には定数化できない。
- `0xc65bb2` の `edx` は `ebx` (`jle` 分岐で `0x100` か、別の値) であり、分岐条件 (`0xc65b70` の `jle`) を満たす経路で決まる。

## 3. 限界

- 静的解析である。`[rbp+*]`・`[rax+*]` の値は、呼び出された時点の実行時の値であり、ここでは確定しない。
- wrap の `r9` は表経由で決まるため、表の添字の範囲 (0〜15) が呼出元の全経路で成り立つかは確かめていない。
- 上位 5 関数の呼出元の 1 段上 (`0xa9830d`・`0x67d556` 等) の機能は未同定。
- `0xc65bb2` の `ebx` の経路 (`0xc65b70`〜) は、`jle` 分岐の先の値まで読んでいない。

## 4. REPORT_4396 の訂正

読み直しで、`REPORT_4396.md` §1 の 1 点が誤りと分かった。

- 4396 の記述: ローダ解決関数 `0x4235f0` は、`shr rax,0x10` の結果が非 0 のとき `GetProcAddress` 相当 `0x4235e0` を呼ぶ。
- 読み直し: `0x4235f0` で `shr rax,0x10` が **非 0 (名前)** のときは、`0x4139f0`・`0x414000` を経て、その結果を `0x4235e0` に渡す (`0x423629`〜`0x42364e`。`0x4139f0`・`0x414000` の役割は未確認)。`rdx` の上位 16 bit が 0 の **序数** の側 (`0x423614` の `jne` 不成立) は、`0x4235e0` を直接呼ぶ (`0x42361e`)。
- 影響: 4396 の表の結論 (ローダのスロット格納と wrap の対応) は変わらない。名前解決の段数の記述だけが不正確だった。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `[rbp+*]`・`[rax+*]` の実行時の値 (r8 の obj フィールド・`[sp+0x60]`) | 引数の値の確定 (受入 2 の入力) | 親 #3386 (実行時に読む) |
| 上位 5 関数の呼出元 1 段上の機能 | どの FL 機能が élastique を使うか | 親 #3386 |
| `0xc65bb2` の `ebx` 経路 | 1 呼出元の引数の完全な確定 | 親 #3386 |
| 動的確認 (ローダ・export の実呼出し) | 静的結論の裏付け | 親 #3386 |

## 6. 再現

- 素材: `oc_artifacts: fl-win64` → `$RUNNER_TEMP/fl-win64` (アーカイブを `tar --zstd -xf` で展開、6.2 s)
- 直接呼出元: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/shared/elastique/fl_wrap_disasm.py callers 677f60 678010 c67520 a97780 67d5a0 c67730 c69d10 c69d60` — 測定 commit `fc0f43f61`。同 HEAD で再実行: rc 0・28.0 s・load 0.32→0.67 (nproc 4)。出力は §1 の表と一致。
- 逆アセンブル: `python3 tools/shared/elastique/fl_wrap_disasm.py disasm <start> <end>`
- 測定 commit: `fc0f43f61` (`fl_wrap_disasm.py` と本 REPORT を含む)。
