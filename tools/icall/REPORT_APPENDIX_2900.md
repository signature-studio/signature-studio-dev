# 付録: icall #2900 (ICALL-84) — 4 命令の添字上限の確定 (部分達成)

> 親: #2224 (ICALL-64)。前付録: `REPORT_APPENDIX_2224.md`。残件の起票先: #3089 (ICALL-85・子 issue・本付録 §5)。
> 再現スクリプト: `tools/icall/diff/index_reach.py` (届く添字の算術と 4 命令の objdump 行)。

既知類型との関係: 該当 ID なし (DEFECTS.md D10 と形が近い)。D10 は ImageBase 基底の `lea` + 大 disp の表参照で固定値を返す症状。本件も ImageBase 基底の大 disp だが、症状は未観測で、本付録は届く添字の算術と静的経路だけを扱う。

## 1. 結論

- **受入 3 (baseline 再現): 達成。** `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` は rc=95 が 53、既知 12 中 hit 3 を再現した (§3)。
- **受入 2 (基底と表の全長): 一部。** 4 命令の基底は全て画像基底 `0x180000000` と確定した (`lea` で直接入る。§2.1・§2.2)。dword 表 `0x1810df738` の全長は未確定 (添字の値が実行時の値で、静的な上限が決まらない)。
- **受入 1 (動的に読まれた添字の最大値): 未達。** int3 で採取する試作は、harness 自体が closure の挙動を変えたため採用しなかった (§4)。
- **静的に確定したこと:**
  - `1806dbe61`・`1806f7431` (float) は mode==2 の経路で添字 k が `[0, 32]` に限られる (`ebp = 2 + 0x1e`・`r12d = 33`。x に依らない定数)。5 件の slot には届かない (§2.2・§3)。
  - `180703913` は `18070390b` の fall-through でのみ入り、その経路は届かない。前提は呼出し先 `180cbb930` が `r13` を保存すること (§2.1)。
  - `180703b7c` は表の値 (dword) が添字になる。届き得る 5 件は列挙できたが、表の全長と値域が未確定のため上限は未確定 (§2.1・§3)。

## 2. 静的結果 (`SlateCore.core_64` の objdump)

本 run で objdump 全文 `tools/icall/work/core64_dis.txt` (4,553,159 行) を取得し、以下の番地を照合した。

### 2.1 `180703913`・`180703b7c` (関数 `180703880`、1,434 bytes)

- `180703880` の直接の呼出し元は `1807037c7` (関数 `1807030b0`) の 1 箇所だけ。`1807030b0` は closure 131 に含まれない。`180703880` を指すポインタはデータ中に無い。
- `180703913` (`mov rbx,[r8+rcx*8+0x125c7b8]`) の基底 `r8` は `1807038f3` `lea r8,[rip+...] # 0x180000000` で設定される。添字 `rcx` は `18070390b` `movsxd rcx,DWORD PTR [r8+rax*4+0x10df738]` で代入される (表の値)。
  - `18070390b` へ入るのは `180703908` の fall-through だけ。`180703908` へ入る直接の参照は `1807038fd` `jne 0x180703908` の 1 件だけ (objdump 全文の textual 検索)。
  - `1807038fd` の `jne` は `edx != -1` のとき取られる。`edx` は `1807038dd` `lea edx,[r13-0x1]` で作られ、`r13d` は `1807038b5` `xor r13d,r13d` で 0 になる。その間の `1807038d0` `call 0x180cbb930` の後、`1807038fa` `cmp edx,0xffffffff` までに `r13`・`edx` の書き換えは無い。よって `edx = -1` となり `jne` は取られない。`1807038ff` の fall-through は `180703906` `jmp 0x18070391b` で `180703908` を迂回する。
  - 前提: `r13` は呼出し先 `180cbb930` が保存する (MS x64 ABI の callee 保存レジスタ)。`180cbb930` の中身は確認していない。
  - 直接の jump/jcc の照合: `0x180703913`・`0x18070390b` を target または RIP 参照にする命令は objdump 全文で 0 件。PE (`SlateCore.core_64`) 全体で、`0x180703913`・`0x18070390b`・`0x180703908`・`0x180703880` を指す 8 バイト LE のポインタは 0 件。関数内に間接ジャンプ (`jmp QWORD`・`jmp reg`) は無い。
  - **結論 (前提付き): `180703913` は `18070390b` からの fall-through でだけ入り、その経路は `1807038fd` の `jne` が取られないため開かない。** よって届く添字 87,075〜87,083 の参照はこの経路では起きない。
- `180703b7c` (`mov rbx,[rbx+rcx*8+0x125c7e8]`) の添字 `rcx` は `180703b74` `movsxd rcx,DWORD PTR [rbx+rax*4+0x10df738]` で代入される (表の値)。基底 `rbx` は `180703b6d` `lea rbx,[rip+...] # 0x180000000` で設定され、`180703b74` へそのまま fall-through する。`180703b6d` へ入る直接の参照は `180703b62` `jne 0x180703b6d` の 1 件だけ。添字 `rax` は `180703b5a` `movsxd rax,DWORD PTR [rsp+0x24]`。
  - `180703b7c` は `180703b5f` `cmp eax,0xffffffff` の結果、`[rsp+0x24]` が `-1` でないときだけ到達する (`180703b62 jne`)。
  - `[rsp+0x24]` は `1807038d5` で `-1` に初期化され、`1807038e6` でそのアドレスを `[rsp+0x40]` に入れる。`180703a47` `call 0x180702f50` が out 引数経由で書く。
  - `0x180702f50` の返す値は、グローバル `0x18125d5ac` の dword か、仮想呼出し (`call [rax+0x8]`・`call [rax+0x18]`) の先で読んだ dword。**実行時の値で、静的な上限は決まらない。**
  - 表 `0x1810df738` の全長: 添字の値域が決まらないため**未確定**。REPORT_APPENDIX_2224 §2.3 の「先頭 160 dword に 87,069〜87,083 が無い」は、先頭の範囲の事実として残る。

### 2.2 `1806dbe61`・`1806f7431` (関数 `1806dbc10`・`1806f71e0`、各 929 bytes)

- 両関数は closure 131 の外。直接の呼出しは無く、データ中の関数ポインタ (file offset `0x10dcad0`・`0x10ddb90`、仮想呼出しの表) からだけ参照される。
- 基底 `rax` (`[rbx+rax*1+disp]` の `rax`) は次の `lea` で直接確定する。
  - `1806dbe5a` `lea rax,[rip+0xffffffffff92419f] # 0x180000000` の直後が `1806dbe61` `movss xmm1,DWORD PTR [rbx+rax*1+0x125c440]`。
  - `1806f742a` `lea rax,[rip+0xffffffffff908bcf] # 0x180000000` の直後が `1806f7431` `movss xmm1,DWORD PTR [rbx+rax*1+0x125c600]`。
  - どちらも mode==2 の分岐内で、直前の `call 0x181048180` (`1806dbe4e`・`1806f741e`) の戻り値は使わない。両命令へ入る直接の参照は objdump 全文で 0 件。
- 添字 `rbx` は **rbx = 4k** (k はループ変数 `r15d`)。
  - `1806dbd92` `xor r15d,r15d` で k = 0。`1806dbdc8` `mov ebx,r15d` でループ前に rbx = 0。
  - ループ末尾で `1806dbf0b` `inc r15d` と `1806dbf24` `add rbx,0x4` が 1 回ずつ実行され、`1806dbf28` `cmp r15d,r12d`・`1806dbf2b` `jl 0x1806dbe20` で後方に戻る。よって反復 k の先頭で rbx = 4k。
  - `1806f71e0` 側も同じ構造 (`1806f7398` `mov ebx,r15d`、`1806f74f4` `add rbx,0x4`、`1806f74f8` `cmp r15d,r12d`、`1806f74fb` `jl 0x1806f73f0`)。
  - 前版 (round 1) の『x / d が約 697,000 以上』は rbx をそのまま添字と読んだ誤り。添字 k = rbx / 4 で読む。
- 上限 `r12d` (ループ回数): `r12d = ebp + 1` (`1806dbd25` `lea r12d,[rbp+0x1]`、`1806f72f5` 同形)。`ebp` の値は eax (モード) で分岐する。
  - `1806dbc9b` `mov eax,[rsi+0xb58]` でモードを読む。`1806dbce5` `cmp eax,0x3` → `1806dbcea` `lea ebp,[rax+0x8]`。`1806dbcef` `cmp eax,0x2` → `1806dbcf4` `lea ebp,[rax+0x1e]`。
  - **mode==2 の経路では `ebp = 2 + 0x1e = 32`、`r12d = 33`、k ∈ [0, 32]。** x には依らない定数。`1806f71e0` 側も `1806f72bf` `cmp eax,0x2` → `1806f72c4` `lea ebp,[rax+0x1e]` で同じ。
  - mode==2 以外 (ebp = `[rsi+0xb54]` か `trunc(x / [rsi+0xb50])`) の経路は、この 2 命令 (float 読出し) へは入らない (`1806dbe20` 以降で `eax==2` の分岐だけが `1806dbe5a` へ行く)。
- 届く添字: rbx = 4k で、k ∈ [0, 32] の範囲を超える。5 件の slot への整除は k = 174,372〜174,388 (`1806dbe61`) と 174,260〜174,276 (`1806f7431`) で、いずれも範囲外。**mode==2 の経路では 5 件の slot に届かない。**

## 3. 測定 (受入 3)

- 測定 commit: `718e90fb` (main)。`slot_trace.c`・`slot_trace.sh` は本付録の PR で変えない。`git diff 718e90fb HEAD -- tools/icall/diff/slot_trace.sh tools/icall/diff/slot_trace.c tools/ott tools/targets/freshair` は 0 行 (§6)。
- 素材: `work-icall` を repo 直下で展開 (`tools/icall/work/`)、`plugins-freshair` を `$RUNNER_TEMP/plugins-freshair` に展開して `FA_DL=... bash tools/targets/freshair/fetch.sh` (出力 `win: 17 files, factory .epf: 8, mac: 0 files`)。
- 実行: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh`。
  - 測定 (measurement commit `718e90fb`): real 12.6 s / user 11.1 s / sys 1.8 s。load average (uptime 1 分値) 0.73 (測定直後の値)。
  - 再実行 (fix run・HEAD): real 12.6 s / user 11.0 s / sys 1.9 s。load average 0.38 → 0.48。
  - 結果 (両回で同じ): funcs 131・exit `{rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8}`・zero-fill VA 10 個・既知 12 中 hit 3 (`0x1813068f8`・`0x1813073f0`・`0x181307418`)・miss 9。REPORT_APPENDIX_2224 §2.1 と一致。
- 届く添字の算術: `python3 tools/icall/diff/index_reach.py tools/icall/work/core64_dis.txt` (基底 0x180000000)。

| 命令 | 形 | 届く添字 n (5 slot のうち整除できた値) | 採取での最大 |
|---|---|---|---|
| `180703913` | `[r8+rcx*8+0x125c7b8]` | 87,075・87,080・87,081・87,082・87,083 | 未採取 (§4) |
| `180703b7c` | `[rbx+rcx*8+0x125c7e8]` | 87,069・87,074・87,075・87,076・87,077 | 未採取 (§4) |
| `1806dbe61` | `[rbx+rax*1+0x125c440]` (rbx=4k、mode==2) | なし (範囲なしでは k = 174,372・174,382・174,384・174,386・174,388 だが、k ∈ [0,32] の外) | 未採取 |
| `1806f7431` | `[rbx+rax*1+0x125c600]` (rbx=4k、mode==2) | なし (範囲なしでは k = 174,260・174,270・174,272・174,274・174,276 だが、k ∈ [0,32] の外) | 未採取 |

- 列挙値は範囲ではない。範囲表記 (min〜max) では 87,076〜87,079 なども届くように読めるが、届くのは列挙の値だけ。

### 3.2 負の対照 (基底を 8 バイトずらす)

- `python3 tools/icall/diff/index_reach.py --base 0x180000008 tools/icall/work/core64_dis.txt` の結果。
  - `180703913`: 87,074・87,079・87,080・87,081・87,082 (各 −1)。`180703b7c`: 87,068・87,073・87,074・87,075・87,076 (各 −1)。
  - float 2 件: 範囲外のまま (なし)。
- よって、scale 8 の列挙値は基底 `0x180000000` の値に依る。基底を 1 バイトずらすと、scale 8 の 2 件は 0 件になる (整除できない)。

## 4. 動的採取の試行 (不採用)

- 方法: `slot_trace.c` に `SLOT_BP=<番地,...>` を足し、番地へ int3 を置いて、実行ごとの `rcx`・`rbx` の最小・最大を記録する。closure 131 の各関数と、4 命令を含む 3 関数 (`180703880`・`1806dbc10`・`1806f71e0`) を直接 entry で走らせる。
- 結果: 試作版は、**`SLOT_BP` を指定しなくても**、closure の 2 関数 (`18105bb90`・`18105bea0`) の rc が 95 から 97 に変わった (`ott_native` の `RaiseException` fail-fast)。
  - SIGTRAP ハンドラに bp 照合の分岐を足すだけで同じ変化になり、その分岐を外すと元の rc に戻る。
  - 原因は未特定。`ott_native` の SIGTRAP 機構との干渉を疑うが確認していない。
  - 4 番地のそれぞれを単独で置いても、`18105bb90` は同じく `RaiseException` になった (番地ごとに確認)。
- 試作版の採取 (参考): closure 131 では 4 命令とも 0 回 (ただし 2 関数は rc 97 で採取できず)。直接 entry の 3 関数も 0 回 (`180703880` は fatal (rc 95)、`1806dbc10`・`1806f71e0` は既定の heap 引数で mode≠2 のため分岐に入らず rc 0)。
- **0 回は観測値であり、届かないことの証明ではない。** 試作のコードは harness の挙動を変えるので残さない。`slot_trace.c`・`slot_trace.sh` は HEAD のまま。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 4 命令の動的最大添字 (受入 1)。int3 採取は closure の挙動を変えるため不採用。非侵襲の採取方法が要る | 届く添字との差が未記録 | #3089 (ICALL-85) |
| `0x180702f50` の返す dword の値域 (`180703b7c` の添字上限)、表 `0x1810df738` の全長 (受入 2 の残り) | `180703b7c` が 5 件に届くかの判定 | #3089 (ICALL-85) |
| `180cbb930` が `r13` を保存すること (`180703913` の到達判定の前提。ABI 上の前提で、中身は未確認) | `180703913` の到達判定 | #3089 (ICALL-85) |
| #3089 の受入 4 (baseline 再現) は親で達成済みの再測定 (回帰確認) | 子の範囲 (WORKFLOW §3) | PM 判断 (#3089 にコメント) |

## 6. 検証

- 測定 commit `718e90fb` から HEAD までの、測定対象の差分: `git diff 718e90fb HEAD -- tools/icall/diff/slot_trace.sh tools/icall/diff/slot_trace.c tools/ott tools/targets/freshair` は 0 行 (fix run の HEAD で確認)。
- 本付録の追加: `tools/icall/REPORT_APPENDIX_2900.md`・`tools/icall/diff/index_reach.py`・`docs/DOC_MAP.md` の登録行。
- 修正 (round 2 の差し戻し対応): 素材 (`plugins-freshair`・`work-icall`) が揃っていたため、§2 の番地を objdump 全文で再照合した。float 2 件の基底 `rax` (`lea` で確定)、`180703913` の直接参照 (0 件)、`rcx` の代入元 (`180703b74`・`rbx` 基底)、float 添字の `rbx = 4k`、mode==2 の上限 `k ∈ [0, 32]` (`ebp = 2 + 0x1e`) を確定した。`index_reach.py` は float の添字を k にし、範囲を `[0, 32]` にした。
- e2e (§3) は fix run の HEAD で再実行し、測定時と同じ結果 (funcs 131・exit 同一・既知 hit 3)。

## 7. 再現

```
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
mkdir -p tools/icall/work
objdump -d -M intel "tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64" > tools/icall/work/core64_dis.txt
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
python3 tools/icall/diff/index_reach.py tools/icall/work/core64_dis.txt
```
