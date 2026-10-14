# 付録: icall #2900 (ICALL-84) — 4 命令の添字上限の確定 (部分達成)

> 親: #2224 (ICALL-64)。前付録: `REPORT_APPENDIX_2224.md`。残件の起票先: #3089 (ICALL-85・子 issue・本付録 §5)。
> 再現スクリプト: `tools/icall/diff/index_reach.py` (届く添字の算術と 4 命令の objdump 行)。

## 1. 結論

- **受入 3 (baseline 再現): 達成。** `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` は rc=95 が 53、既知 12 中 hit 3 を再現した (§3)。
- **受入 2 (基底と表の全長): 一部。** `180703913`・`180703b7c` の基底 (`r8`・`rbx`) は両方とも画像基底 `0x180000000` と確定した (`lea` で直接入る)。dword 表 `0x1810df738` の全長は未確定 (添字の値が実行時の値で、静的な上限が決まらない)。
- **受入 1 (動的に読まれた添字の最大値): 未達。** int3 で採取する試作は、harness 自体が closure の挙動を変えたため採用しなかった (§4)。
- **静的に確定したこと:** `180703913` は関数 `180703880` の中で到達しない (§2.1)。`180703b7c` と float 2 件は到達し得るが、添字の上限は実行時の値に依る。

## 2. 静的結果 (`SlateCore.core_64` の objdump)

### 2.1 `180703913`・`180703b7c` (関数 `180703880`、1,434 bytes)

- `180703880` の直接の呼出し元は `1807037c7` (関数 `1807030b0`) の 1 箇所だけ。`1807030b0` は closure 131 に含まれない。`180703880` を指すポインタはデータ中に無い。
- `180703913` (`mov rbx,[r8+rcx*8+0x125c7b8]`) は `18070390b` (`movsxd rcx,[r8+rax*4+0x10df738]`) の後ろにある。`18070390b` へ入る経路は `1807038fd` の `jne 180703908` だけ。
  - その条件は `edx == -1`。`edx` は `1807038dd` の `lea edx,[r13-0x1]` で作られ、`r13d` は `1807038b5` で 0 にされ、`1807038fa` までに書き換えが無い。よって `edx = -1` が常に成立し、`jne` は取られない。
  - 関数内に間接ジャンプ (`jmp QWORD`・jump table) は無い (`1807038xx`〜`180703e1a` を確認)。
  - 前提: `r13` は呼出し先 `180cbb930` が保存する (MS x64 ABI の callee 保存レジスタ)。
  - **結論: `180703913` は `180703880` の入口からは到達しない (静的)。** 届く添字 87,075〜87,083 の参照は、この経路では起きない。
- `180703b7c` (`mov rbx,[rbx+rcx*8+0x125c7e8]`) は `180703b5a` の `movsxd rax,[rsp+0x24]` が `-1` でないときだけ到達する (`180703b62 jne 180703b6d`)。
  - `[rsp+0x24]` は `1807038d5` で `-1` に初期化され、`1807038e6` でそのアドレスを `[rsp+0x40]` に入れる。`180703a47` の `call 0x180702f50` が out 引数経由で書く。
  - `0x180702f50` の返す値は、グローバル `0x18125d5ac` の dword か、仮想呼出し (`call [rax+0x8]`・`call [rax+0x18]`) の先で読んだ dword。**実行時の値で、静的な上限は決まらない。**
  - 基底: `180703b6d` の `lea rbx,[rip+...] # 0x180000000` で `rbx = 0x180000000`。
  - 表 `0x1810df738` の全長: 添字の値域が決まらないため**未確定**。REPORT_APPENDIX_2224 §2.3 の「先頭 160 dword に 87,069〜87,083 が無い」は、先頭の範囲の事実として残る。

### 2.2 `1806dbe61`・`1806f7431` (関数 `1806dbc10`・`1806f71e0`、各 929 bytes)

- 両関数は closure 131 の外。直接の呼出しは無く、データ中の関数ポインタ (file offset `0x10dcad0`・`0x10ddb90`、仮想呼出しの表) からだけ参照される。
- 両方とも `cmp eax,0x2` (`eax = [rsi+0xb58]` = モード) の mode==2 側にある。`call 0x181048180` の後で `[rbx+rax+0x125c440]` (または `0x125c600`) を読む。
- 添字 `rbx` の設定: `1806dbd29` `movsxd rbx,r12d` (`r12d = trunc(x / [rsi+0xb50]) + 1`、`x` は `1806dbd15` で読む float) と、`1806dbdc8` `mov ebx,r15d`。
  - float の入力 `x` に依存する 32 bit 値で、静的には上限が決まらない。
- 届く添字 697,040〜697,104・697,488〜697,552 に届くには、`x / d` が約 697,000 以上になる入力が要る。

## 3. 測定 (受入 3)

- 測定 commit: `718e90fb` (main)。`slot_trace.c`・`slot_trace.sh` は本付録の PR で変えない。`git diff 718e90fb HEAD -- tools/icall/diff/slot_trace.sh tools/icall/diff/slot_trace.c tools/ott tools/targets/freshair` は 0 行 (§6)。
- 素材: `work-icall` を repo 直下で展開 (`tools/icall/work/`)、`plugins-freshair` を `$RUNNER_TEMP/plugins-freshair` に展開して `FA_DL=... bash tools/targets/freshair/fetch.sh` (出力 `win: 17 files, factory .epf: 8, mac: 0 files`)。
- 実行: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh`。
  - real 12.6 s / user 11.1 s / sys 1.8 s。load average (uptime 1 分値) 0.73 (測定直後の値)。
  - 結果: funcs 131・exit `{rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8}`・zero-fill VA 10 個・既知 12 中 hit 3 (`0x1813068f8`・`0x1813073f0`・`0x181307418`)・miss 9。REPORT_APPENDIX_2224 §2.1 と一致。
- 届く添字の算術 (`python3 tools/icall/diff/index_reach.py tools/icall/work/core64_dis.txt`):

| 命令 | 形 | 届く添字 (5 件) | 採取での最大 |
|---|---|---|---|
| `180703913` | `[r8+rcx*8+0x125c7b8]` | 87,075〜87,083 | 未採取 (§4) |
| `180703b7c` | `[rbx+rcx*8+0x125c7e8]` | 87,069〜87,077 | 未採取 (§4) |
| `1806dbe61` | `[rbx+rax*1+0x125c440]` (float) | 697,488〜697,552 | 未採取 (§4) |
| `1806f7431` | `[rbx+rax*1+0x125c600]` (float) | 697,040〜697,104 | 未採取 (§4) |

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
| `0x180702f50` の返す dword の値域 (`180703b7c` の添字上限) と、表 `0x1810df738` の全長 (受入 2 の残り) | 5 件に届くかの判定 | #3089 (ICALL-85) |
| `1806dbe61`・`1806f7431` の float 入力 `x` の値域 (`rbx` の上限) | 同上 | #3089 (ICALL-85) |
| `180703913` の到達不能を動的にも確かめる (現在は静的のみ) | 静的判定の裏取り | #3089 (ICALL-85) |

## 6. 検証

- 測定 commit `718e90fb` から HEAD までの、測定対象の差分: `git diff 718e90fb HEAD -- tools/icall/diff/slot_trace.sh tools/icall/diff/slot_trace.c tools/ott tools/targets/freshair` は 0 行。
- 本付録の追加: `tools/icall/REPORT_APPENDIX_2900.md`・`tools/icall/diff/index_reach.py`・`docs/DOC_MAP.md` の登録行。

## 7. 再現

```
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
mkdir -p tools/icall/work
objdump -d -M intel "tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64" > tools/icall/work/core64_dis.txt
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
python3 tools/icall/diff/index_reach.py tools/icall/work/core64_dis.txt
```
