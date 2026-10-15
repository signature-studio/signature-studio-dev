# PLG-P0b-36 (#3652) — Dispatcher 格納元 call 先の実値 (受入 1〜4)

親 #2945。前身は `REPORT_DISPATCHER_APPENDIX_2886.md` §2 (格納元 19 ID) と §3.4 (callee 戻り値 0 への依存)。
本付録は新規ファイルで、分割移動ではない。`REPORT_DISPATCHER_APPENDIX_2886.md` の本文は変えない。
既知類型 (`docs/DEFECTS.md`): 該当なし。ただし emulator が呼出先を stub (戻り値 0) にする制限は
`REPORT_DISPATCHER.md` §3.4 の既知の限界 (本件の多くの値はこの制限の内側でしか測れない)。

- 解析 VA はすべて block00031 (ImageBase 0x400000 系。`hs_callee_disasm.py` / `hs_val_probe.py` が読む写像と同じ)。
- 機械語は `capstone` で読み直した (本付録の VA はすべて `hs_callee_disasm.py` の出力か `dis` の直読)。

## 0. 結論

本付録の値は、emulator の harness の仮定 (zero-page の HostTag・第 5 引数の既定値・stub の戻り値 0) の上で得たものを含む。
受入 1・3・4 は部分で、残りの未確定は §7 に起票先付きで列挙する。

| 受入 | 結果 | 状態 |
|---|---|---|
| 1 | `0x1318e3e` の `call 0x11ffde0` の引数は ecx=`[rbp+0x1880]`、r8d=`[rbp+0x119c]`=`0x8000`+`[HostTag+0x9c]`+Index (HostTag = rdx)。`[rbp+0x1880]` は Dispatcher の第 5 引数 (呼出元 `[rsp+0x20]`、§2.1)。Dispatcher の 256 ID 実行で `0x1318e3e` に達したのは **ID 0x01 のみ**。ecx=0 と ecx=-1 (0xffffffff) では、r8d≠-1 のとき status=0 (既定 arm 0x12000d8)。ecx の他の値は callee 戻り値に依存 (§2.2) | 部分 (第 5 引数・callee の実値は未確定。ecx が 0 か -1 (かつ r8d≠-1) なら 0) |
| 2 | `0x9636a0` の戻り値 = `0x9635d0` 末尾 (0x963684) の vcall `call [rax+0x398]` (rax=`[r13]`) の戻り値。`0x963640` の別の vcall は戻り値を捨てる (`xor eax,eax`)。受け手 r13 は `0x741e20` の戻り値 (2 段の vcall を経る実行時オブジェクト) | 構造は確定。値・受け手の型は未確定 |
| 3 | `0xe4e970` (bool) の成否 (flags=1): `[obj+0xa78]≠5 ∧ [obj+0xa18]≠5 ∧ [obj+0xd78]≥0`。flags=1 の 12 組で予測と照合し mismatch 0 (flags=2・4 の 24 組は al と出力を表示するだけで、mismatch の集計対象外)。`0xed6780` (bool) の条件は列挙。`+0x6f` は object のフィールドではなく `0xed6780` の frame 内バイト (`[rbp+0x6f]`) | 部分 (obj の実値・callee 戻り値は未確定) |
| 4 | 出力 word `[rbp+0x111c]`: 0x11d06e0 単独では最終値は入力 word か 0 (callee は 0 しか書かない)。0x1321a1b に入る時点の入力 word = `([rbp+0x1878] >> 16) & 0xffff`。経路 A (Index の bit0=0 かつ `[[HostTag+0xb8]+8]==0`) では word を書く呼出しが無いので、Index < 0x10000 なら入力 0 → 最終 0 → 判定 (sete) = 1 → ID 0x41 の応答 1。経路 B (`[[HostTag+0xb8]+8]≠0`) は 0xf5b190 の word への書込みに依存 (§5.3) | 部分 (経路 A の条件付き。経路 B は未確定) |

## 1. 測定条件

- 測定 commit: `c95b7a770` (`hs_val_probe.py` 新規)。コードを変えた最後の commit。改訂 (r2) はコードを変えていない。
  `git diff c95b7a770 HEAD -- tools/plugins/framework/hostshim ':!*.md'` は空 (§6 の末尾で確認)。
- 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B) を `$RUNNER_TEMP/fl-win64` に展開
  (`tar --zstd -xf` で 2.97 秒)。`work-fw-stage1` は本件の解析では使わず、展開していない。
- Python (repo 外の `$RUNNER_TEMP/hsvenv`): `unicorn 2.1.4` / `pefile 2024.8.26` / `capstone 5.0.7`。
  issue は `capstone 5.0.9` を指すが、本件は 5.0.7 を導入した (差の有無は未確認。出力はすべて 5.0.7 のもの)。
- 所要と load (n=1): 256 ID の Dispatcher 実行 `hs_val_probe.py disp` 74 秒 (load 0.16 → 0.76)。`verify` 6 秒。`word41` 1 秒未満。

## 2. 受入 1: `0x1318e3e` の call 0x11ffde0 の戻り値

### 2.1 引数の供給元 (ID 0x01 の経路)

`hs_val_probe.py disp` (全 256 ID) で、観測点 `0x1318e3e` に到達したのは ID 0x01 だけ (§6 の表)。その経路:

| VA | 命令 (要約) | 意味 |
|---|---|---|
| 0x1318722・0x1318729 | `mov [rbp+0x1870], r8` / `mov [rbp+0x1878], r9` | ID と Index を保存 |
| 0x1318730・0x1318737 | `mov rax,[rbp+0x1880]` / `mov [rbp+0x1880], rax` | ecx の元になる slot の**自己コピー**。関数内で経路上に他の書込みは無い (`0x1318d26`・`0x1318e02` の `=0xa` は ID 0x01 の経路に現れない) |
| 0x1318df8・0x1318e00 | `cmp [rbp+0x1880], 3` / `jne 0x1318e0d` | slot==3 のとき 0x1318e02 で 0xa に置換される分岐 |
| 0x1318e0d・0x1318e14 | `mov rax,[rbp+0x1868]` / `mov eax,[rax+0x9c]` | `[rbp+0x1868]` は rdx (HostTag) の保存先 (0x131871b `mov [rbp+0x1868], rdx`)。eax = `[HostTag+0x9c]` |
| 0x1318e1a・0x1318e20 | `add eax,[rbp+0x1878]` / `add eax,0x8000` | eax = `[HostTag+0x9c]` + Index + 0x8000 |
| 0x1318e25・0x1318e37 | `mov [rbp+0x119c],eax` / `mov r8d,[rbp+0x119c]` | r8d = 上の値 |
| 0x1318e2b・0x1318e3e | `mov ecx,[rbp+0x1880]` / `call 0x11ffde0` | ecx = slot 値 |

- **`[rbp+0x1880]` の位置**: prologue (0x13173a0〜0x13173bb) は push rbp・rdi・rsi・rbx の後、`sub rsp,0x1838` と `mov rbp,rsp`。
  よって rbp = 呼出元 rsp − 0x28 − 0x1838 で、`[rbp+0x1880]` = **呼出元 `[rsp+0x20]`** (Win64 の第 5 引数 Value)。
  関数内で「未初期化」の slot ではなく、呼出元が決める引数である。実行時の値は未確定 (§7)。
- harness の値: `hs_disp_emu.py:145` は fill (84 行) の後にこの slot (`STACK_TOP+0x20`) を 0 にする。`hs_val_probe.py` は書かない (未書込みのスタックの 0、または `HS_DISP_STACK_FILL` の値)。
- この slot は ID 0x41 の `0x132178c` の分岐も決める (`cmp [rbp+0x1880],0`。0 なら 0x1321796 で `[global]` の bit 30 を落とし、非 0 なら 0x13217a5 で `[global]` = ecx)。

観測値 (`hs_val_probe.py disp`): 0x1318730 では全 ID で `[rbp+0x1880]`=0 (fill なし)。ID 0x01 の `0x1318e3e` では ecx=0x0、r8d=0x8000。`HS_DISP_STACK_FILL=0xff` の probe では ecx=0xffffffff、r8d=0x8000 (§6)。
emulator は HostTag に TAG (0x54534154) を渡す。これは非ポインタなので `[TAG+0x9c]` (0x545341f0) は未マップ領域への読みになり、zero-page の 0 が入る (ベースライン `hs_disp_emu.py` の unmapped top `0x54534000/read=3` と一致)。よって r8d=0x8000 は emulator の artifact で、実行時の HostTag の意味は未確定 (§7)。

### 2.2 0x11ffde0 の status (単独実行の ecx sweep、r8d=0x8000)

`hs_val_probe.py sweep11ffde0` は 0x11ffde0 を単独で実行し、戻り値 eax と末尾 3 VA を出す。
末尾は全 ecx で `0x1200106`・`0x1200108`・`0x1200109` (`pop` 後の `ret`)。status は `[rbp+0x28]` に格納され、`0x12000fa` で eax に読まれる。

| ecx | eax (stub) | arm の入口 VA | status の決まり方 (機械語の直読) | 呼出先 (stub で 0) |
|---|---|---|---|---|
| 0 | 0 | 0x12000d8 (既定) | 既定: status は初期値 0 のまま。r8d=-1 のときだけ `or 1` (0x12000e0) | (0x418190 のみ) |
| 0xffffffff | 0 | 0x12000d8 (既定) | 同上 | (0x418190 のみ) |
| 1 | 0 | 0x11ffe6f | `e34190(r8d)≠0` なら 2、そうでなければ 0 | e34190 |
| 2 | 1 | 0x11ffe8d | `[X+0x10] <= (*G2≠0)` なら 1 (X = `*[global]`、G2 = `[global]`)。そうでなければ `e34190(r8d)≠0` で 1、0 なら既定 0 | (e34190 は未呼出し) |
| 3 | 1 | 0x11ffecc | `*global==0` なら 1。そうでなければ `e34190(r8d)≠0` で 1 | (e34190 は未呼出し) |
| 4 | 0 | 0x1200094 | `105f7d0(...)≠0` なら 2、そうでなければ 0 | 105f7d0 |
| 5 | 1 | 0x12000b7 | `105f7d0(...)==0` なら 1、そうでなければ 0 | 105f7d0 |
| 8 | 1 | 0x11ffef7 | `0x11ffefc` で 1 を格納後、0x11fff01 以降の loop (`fe8bb0` 等) に入る。loop の後の上書きは未解析 | (fe8bb0 は未呼出し) |
| 10 | 0 | 0x11fffe0 | loop で `f826e0` を呼び、0x1200024 で格納。格納式は未解析 | f826e0 ×2 |
| 11 | 0 | 0x1200061 | `f783c0(r8d,&[rbp+0x4c])≠0` なら 2、そうでなければ 0 | f783c0 |
| 14 | 1 | 0x120007b | `670670(&[rbp+0x38],1)==0` なら 1、そうでなければ 0 | 670670 |
| 6, 7, 9, 12, 13, 15, 16, 0x7fff | 0 | 0x12000d8 (既定) | 既定 (cmp/sub の連鎖で既定 arm へ) | (0x418190 のみ) |

- `*global`・`[obj+0x10]`・`e34190`・`105f7d0`・`f783c0`・`670670`・`f826e0` の実値は stub のため未確定。表の eax は stub (戻り値 0) での値で、実行時の値ではない。
- ecx=0 と ecx=-1 の status は、r8d≠-1 なら callee 戻り値に依存せず 0 と確定する (既定 arm のみを通る)。

### 2.3 ID 0x01 の応答

経路上の ecx は、呼出元の第 5 引数 (実行時の値は未確定) である。harness の既定 (0) と fill 0xff (-1) は、どちらも既定 arm で status=0 になる (§6 の disp で rax=0 を両方で確認)。
よって ID 0x01 の応答は、「ecx が 0 か -1 で、かつ r8d≠-1 なら 0」に留める。r8d も §2.1 の通り emulator の artifact を含むので、この条件も未確定。
ecx が別の値 (上の表の他の arm に当たる値) なら、応答は §2.2 の callee 戻り値に依存する (未確定)。

## 3. 受入 2: 0x9636a0 → 0x9635d0 → vcall

### 3.1 呼出連鎖 (機械語)

- `0x9636a0` (`hs_callee_disasm.py`): `mov byte [rsp+0x20],3`・`mov [rsp+0x28],rax`・`call 0x9635d0`・`add rsp`・`ret`。戻り値 = `0x9635d0` の rax。
- `0x9635d0`: `0x963609 call 0x741e20` (rcx = `[rip-0x7bd]` = 静的 VA 0x962e40 の内容 0x962f08、dl=1、r8 = `[global]`) → `mov r13, rax` (0x96360e)。
- `0x963640 call [rbx+0x3a0]` (rbx = `[r13]`): 戻り値は直後の `xor eax, eax` (0x963640) で捨てられる。
- `0x963684 call [rax+0x398]` (rax = `[r13]`): 末尾の tail call。rax は変えられずに `ret` へ出るため、戻り値 = この vcall の戻り値。

**issue 本文の表記 `call [r13+0x398]` は誤り**。実際は `call [[r13]+0x398]` (vtable 経由)。本付録はこの表記で扱う。

### 3.2 受け手 (0x741e20) の正体

- `0x741e20` の戻り値は `[rbp+0x50]` (= rcx の受け取り後の値)。dl≠0 のとき `0x410320` と `0x410360` を経由する。
- `0x410320` (dl=1 のとき `test dl,dl; jl` が not-taken で `call [rax-0x30]` の vcall)、`0x410360` (`call [rbx-0x50]` の vcall)。すなわち受け手は 2 段の vcall の結果で、静的には決まらない。
- 静的 VA 0x962e40 の内容は 0x962f08。その先頭 qword は 0x619200 で、`[0x619200+0x398]` の内容はコードのバイト列 (0xff188b48000000b0)。
  静的ファイルの状態は実行時オブジェクトの vtable を与えない。

### 3.3 結論

- 0x9636a0 の戻り値は `[[r13]+0x398]` の戻り値。構造は確定した (vcall の戻り値が捨てられるのは 0x963640 の方)。
- 受け手の型・vtable・スロットの実体は**未確定** (実行時オブジェクト。§7)。
- emulator では 0x9636a0 は stub (0 を返す)。ID 0x13 の応答 0 は stub 由来で、測定値ではない。

## 4. 受入 3: 0x131c40c の call 0xe4e970 と 0x1321be8 の call 0xed6780

### 4.1 0xe4e970 (ID 0x26 の応答)

機械語 (`hs_callee_disasm.py 70 0xe4e970`) の要約。引数: rcx=obj、rdx=out1 (rsi)、r8=out2 (rdi)、r9d=flags。

- `0xe4e988 call 0xe4ed50(obj)`。`0xe4e98f sete al` で al = (e4ed50 の戻り値 == 0)。
- al=1 かつ `[obj+0xd78] >= 0` (符号付き、0xe4e996〜0xe4e99d) → `[rsi]=[obj+0xd74]`、`[rdi]=[obj+0xd78]`、戻り値 1 (0xe4e9af → 0xe4e9e5)。
- それ以外: flags&4 なら `[rsi]=0`・`[rdi]=[obj+0xb1c]`・戻り値 al (0xe4e9ca)。flags&2 (かつ flags&4 でない) なら `[rsi]=0`・`[rdi]=-1`・戻り値 al (0xe4e9e1)。どちらでもなければ戻り値 0 (`xor eax,eax`、0xe4e9e3) で出力は変えない。
- ID 0x26 の呼出しは r9d=1 (`0x131c406 mov r9d,1`) なので、戻り値 = `e4ed50(obj)==0 ∧ [obj+0xd78]>=0` (flags=1 の式)。

`0xe4ed50` (`hs_callee_disasm.py`): `cmp [rcx+0xa78],5; je` → 1、`cmp [rcx+0xa18],5; je` → 1、他は 0。
つまり `e4ed50(obj)==0` ⇔ `[obj+0xa78]≠5 ∧ [obj+0xa18]≠5`。

**成否条件 (flags=1)**: `bool = [obj+0xa78]≠5 ∧ [obj+0xa18]≠5 ∧ [obj+0xd78]≥0`。

検証 (`hs_val_probe.py verify`): obj を HOST 領域に置き、フィールド (a78, a18, d78) を 2×2×3 通り、flags を 1・2・4 で変え、0xe4e970 と 0xe4ed50 を**実行**して戻り値と出力を読んだ。
flags=1 の 12 行で予測との mismatch = 0。al=1 になるのは (a78,a18)=(0,0) かつ d78∈{0,1} の 2 行だけ。
負の対照: a78=5 または a18=5 の 9 行はすべて al=0。flags=2・4 の 24 行は al と出力を表示するだけで、mismatch の集計対象外 (集計は flags=1 のみ)。

- 呼出側 (0x131c3ee〜0x131c406): `mov rax,[rip+0x2c71d3]` (= 静的 VA 0x15e35c8 の内容 0x016ba808) → `mov rcx,[rax]` (= `[0x16ba808]`)。obj は**イメージ外の実行時オブジェクト**で、その実値は未確定。
- emulator の ID 0x26 は 0xe4e970 を stub にするので、応答 0 は stub 由来 (測定値ではない)。

### 4.2 0xed6780 (ID 0x46 の応答)

`0xed6780` の戻り値は `[rbp+0x6f]` (frame 内の 1 バイト)。`+0x6f` は object のフィールドではない (issue 本文の表記の訂正)。
経路 (機械語):

1. `0xed67bc call 0xed66c0(&[rbp+0x58], ecx=Index)` → `[rbp+0x58]` = obj。obj==0 → `[rbp+0x6f]=0` (0xed67c8)。
2. `0xed67d5 call 0x819110(obj)`。al==0 → `[rbp+0x6f]=0` (0xed67de)。
3. `[rbp+0x4f] = (r8b & 1) != 0` (0xed67f7〜0xed6804)。≠0 → `call 0x81d600` → `[rbp+0x6f]=1` (0xed683e)。
4. =0 → `call 0x5928b0(...)` → `[rbp+0x60]`、`[rbp+0x6f] = ([rbp+0x60] > 0x20)` (符号なし、0xed68b1〜0xed68b9)。

呼出側 (0x1321bd3〜0x1321be8): ecx=`[rbp+0x1878]` (Index)、rdx=`[rbp+0x390]`、r8b=`byte [rip+0x8786]` (VA 0x132a36e)。
`ed66c0`・`0x819110`・`0x5928b0`・`[rip+0x8786]` の実値は未確定。emulator は ID 0x46 の 0xed6780 を stub にするので応答 0 は stub 由来。

## 5. 受入 4: 0x1321a1b の call 0x11d06e0 の出力 word

### 5.1 初期値と経路の入口

- `0x13217b4 mov rax,[rbp+0x1878]` → `0x13217bb shr rax,0x10` → `0x13217bf and ax,0xffff` → `0x13217c3 mov [rbp+0x111c], ax`。
  よって入力 word = `(Index >> 16) & 0xffff`。
- 0x1321a1b の呼出し: r8 = `&[rbp+0x111c]` (out word)、r9 = `[rbp+0x111a]` (flags word)。
- 0x1321a1b に入るのは Index の bit0=0 の経路だけ。`0x13219c5 test [rbp+0x1878],1` が奇数なら 0x13219d4 → 0x13219f4 (`call 0x11cfa70`) へ行く。
- ID 0x41 (Index=0) の観測: `0x1321a1b` で `[rbp+0x111c]`=0 (§6)。

### 5.2 callee が書く範囲

`0x11d06e0` (`hs_callee_disasm.py 90 0x11d06e0`) の書込みは 2 箇所だけ:
`0x11d0710 mov word [rbx],0` (flag global ≠0 かつ word==0x60 の分岐、0x11d06f8〜0x11d0701) と `0x11d0730 mov word [rbx],0` (`0x11829e0` の戻り値≠0 の分岐、0x11d0715〜0x11d072e)。
よって、0x11d06e0 単独では最終 word は入力か 0 のどちらか。

`hs_val_probe.py word41` (callee は stub): 入力 0 → 0、入力 0x60 → 0 (flag 分岐で 0x11c8ba0 を経て 0)、入力 0x5 → 0x5 (変わらず、負の対照)。

### 5.3 判定と経路 (0x1321a20・0x1321a28)

判定は `cmp word [rbp+0x111c], 0; sete al` で、0x11d06e0 の後の最終 word==0 のとき応答 1。
入力 word がどこで決まるかは経路で変わる (`0x1321836` 以降の分岐):

- **経路 A** (Index の bit0=0 かつ `[[HostTag+0xb8]+8]==0`): 0x1321836 で `[rbp+0x11a0]=0`。0x132184f の `je 0x132196d` で、0xf5 系の call (0x1321918・0x1321952) と 0x1313220 を飛ばし、0x13219c5 の偶数判定で 0x1321a1b に行く。word の書込みは無いので入力 word = `(Index>>16)&0xffff` のまま。
  Index < 0x10000 → 入力 0 → 最終 0 → 判定 1。
- **経路 B** (Index の bit0=0 かつ `[[HostTag+0xb8]+8]≠0`): 0x13218c8 → 0x1321952 で `call 0xf5b190` (r8 = `&[rbp+0x111c]`)。その後の 0x1321957 `cmp word [rbp+0x111c],0` の結果 (`[rbp+0x11a0]` に入る) が 1 なら 0x13281af (0x13219bf の jne) へ、0 なら 0x1321a1b へ行く。callee の戻り値 (rax) はここで使われず、word の値で分岐が決まる。0xf5b190 が word を書けば分岐も最終 word も変わる。その書込みは未確定 (§7)。
- **ID 0x41 の emulator 応答 1 は経路 A (zero-page 前提) の結果**。経路 B の結果は測っていない。

## 6. 実測 (測定 commit `c95b7a770`、HEAD で再現)

| 測定 | コマンド | 結果 |
|---|---|---|
| 観測点の到達 (256 ID) | `hs_val_probe.py disp > m.txt` | 74 秒、256 行。`0x1318730` は全 ID で `[rbp+0x1880]`=0。`0x1318e3e` は ID 0x01 のみ (ecx=0, r8d=0x8000)。`0x1319f66`・`0x131c40c`・`0x1321be8`・`0x1321a1b` はそれぞれ ID 0x13・0x26・0x46・0x41 のみ |
| 既存ツールとの一致 | `hs_disp_emu.py 0x01 0x13 0x26 0x41 0x46` | rax = 0・0・0・1・0 (`hs_val_probe disp` と一致) |
| fill 0xff (probe) | `HS_DISP_STACK_FILL=0xff hs_val_probe.py disp 0x01 0x41` | ID 0x01: `[rbp+0x1880]`=-1、ecx=0xffffffff、rax=0。ID 0x41: `0x132178c` で `[rbp+0x1880]`=-1 (0x13217a5 側へ)、`0x1321a1b` で `[rbp+0x111c]`=0、rax=1 |
| fill 0xff (`hs_disp_emu.py`) | `HS_DISP_STACK_FILL=0xff hs_disp_emu.py 0x01 0x41` | rax は同じ (0・1)、path 長 879・912 も同じ。ただし `0x1318730` の `[rbp+0x1880]` は fill 0xff でも 0 (下の計測)。原因は `hs_disp_emu.py:145` (§7) |
| `hs_disp_emu.py` の slot 読出し (一回限り・未コミット) | repo 外のスクリプトで `hs_disp_emu.py` のソースに `0x1318730` の読出し 1 行を足して exec し、ID 0x01・0x41 で `main` を実行 | fill なし・fill 0xff のどちらでも `[rbp+0x1880]`=0x0。fill を入れても第 5 引数の slot は 0 に上書きされる |
| sweep 0x11ffde0 | `hs_val_probe.py sweep11ffde0` | §2.2 の表 (19 行、r8d=0x8000) |
| 0xe4e970 検証 | `hs_val_probe.py verify` | 36 行 (flags 1・2・4)。flags=1 の 12 行で mismatch 0。負の対照 9 行で al=0。flags 2・4 の 24 行は記録のみ |
| 0x11d06e0 単独 | `hs_val_probe.py word41` | 入力 0・0x60・0x5 → 出力 0・0・0x5 |

- 検証範囲: block00031 の機械語と unicorn 単独実行 (callee は stub)。範囲外: 実行時の HostTag・Index・第 5 引数・object・callee の実値、callee の実行 (0xe34190 ほか)。範囲外の主張は本付録では行わない。
- 到達表 (0x1318e3e・0x1321a1b など) は zero-page の HostTag (= TAG)、第 5 引数の既定値、stub の戻り値 0 の上で得た結果。経路 B の値は測っていない。
- 改訂 (r2) の再確認: コード差分は無い。`hs_val_probe.py verify` (flags=1 の 12 行 mismatch 0)・`word41`・`disp 0x01 0x41`・`HS_DISP_STACK_FILL=0xff` の probe を HEAD で再実行し、上の表と一致した。`git diff c95b7a770 HEAD -- tools/plugins/framework/hostshim ':!*.md'` の出力は空。
- 検収向けの別算法: 経路の逆追跡 (`path_dump`)・機械語の直読 (`hs_callee_disasm.py`) と、単独実行 (`fn`/`verify`/`word41`) の結果が一致することを確認した (§2.2 の arm と sweep の一致、§4.1 の式と verify の一致)。

## 7. 未解決 (起票先)

起票先は open の issue (#3652 は本 PR の Refs 先)。#3653 は受入 1 (格納元 6 ID のグローバル・フィールド) の範囲で、本表の項目は含まない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 第 5 引数 `[rbp+0x1880]` (= 呼出元 `[rsp+0x20]`) の実値。harness の値は 0 (`hs_disp_emu.py:145`)、または未書込みの 0 (`hs_val_probe.py`)、fill 0xff で -1 | 受入 1 の ecx、ID 0x01・0x41 の経路、`0x132178c` の分岐 | #3652 (Refs。残りを追う) |
| `HS_DISP_STACK_FILL` の不一致の原因は特定 (`hs_disp_emu.py:145` が fill (84 行) の後に第 5 引数 slot を 0 にする)。よって `hs_disp_emu.py` の fill 試験は第 5 引数を変えていない。`hs_val_probe.py` は -1 を読む。#2782 のスタック感度試験の解釈に影響する | #2782 のスタック感度試験の結論 | #2782 (受入 1) |
| HostTag`[+0x9c]` の実値 (emulator は TAG を渡して未マップを読み 0) と Index の実値 | 受入 1 の r8d、受入 4 (経路の条件・Index ≥ 0x10000) | #3652 |
| 経路 B: `[[HostTag+0xb8]+8]` の実値と、0xf5b190 (0x1321943・0x1321952)・0xf5ae50 (0x1321909・0x1321918)・0x11cfa70 (0x13219e5・0x13219f4) の `*r8` (= word) への書込み。0xf5b190 は `[rbx+0x78]==0` のとき同じ word ポインタで 0x11d06e0 を呼ぶ (0xf5b1bc) | 受入 4 (経路 B)。経路 A の条件付き結論の適用範囲 | #3652 |
| 0x11ffde0 の arm の callee 戻り値 (e34190・105f7d0・670670・f783c0・f826e0・fe8bb0) と `[global]`・`[obj+0x10]` | 受入 1 の ecx=1〜5・8・10・11・14 | #3652 (単独実行の stub を実値に置換する作業) |
| 0x9636a0 の受け手 (0x741e20 → 0x410320・0x410360 の 2 段 vcall の結果) の型・vtable・スロット 0x398 の実体 | 受入 2 の値 | #3652 |
| 0xe4e970 の obj の実値 (`[0x16ba808]` の実行時値) と `+0xa78`・`+0xa18`・`+0xd78` | 受入 3 の 0x26 の応答 | #3652 |
| 0xed6780 の `ed66c0`・`0x819110`・`0x5928b0` の戻り値と `[rip+0x8786]` | 受入 3 の 0x46 の応答 | #3652 |
| 0x11829e0 の戻り値と `[global dword]` の符号 (入力 word≠0) | 受入 4 (Index ≥ 0x10000) | #3652 |
| 応答表 (`hostshim.c`) の 0x26・0x46 の 0 は stub 由来 (0xe4e970・0xed6780 は emulator で未実行) | 応答表の根拠 | #3673 (応答表の更新) |
