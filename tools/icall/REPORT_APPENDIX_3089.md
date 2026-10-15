# 付録: icall #3089 (ICALL-85) — 添字上限の残件 (範囲縮小後の受入 1〜3 達成。元の動的採取と値域の残りは子へ)

> 親: #2900 (ICALL-84)。前付録: `REPORT_APPENDIX_2900.md`・`REPORT_APPENDIX_2224.md`。
> 再現スクリプト: `tools/icall/diff/index_table_scan.py` (表の dword 走査)・`tools/icall/diff/index_table_scan_selftest.sh` (合成 PE の負の対照)・`tools/icall/diff/index_reach.py` (届く添字の算術)。
> 残件の起票先: #3089 の範囲縮小後に子 2 件 (本付録 §6)。

既知類型との関係: 該当なし (DEFECTS.md の lift 欠陥の類型には一致しない。encoded 関数ポインタ表の添字を静的に走査する解析)。

## 1. 結論

- **受入 1 (baseline 再現): 達成。** `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` は funcs 131・exit `{rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8}`・既知 12 中 hit 3 (`0x1813068f8`・`0x1813073f0`・`0x181307418`)。§5 の測定 (n=1)。
- **受入 2 (float の `rbx` 上限): 達成。** round 2 (`REPORT_APPENDIX_2900.md` §2.2) の結論を objdump で再照合した。mode==2 では `ebp = 2 + 0x1e = 32`・`r12d = 33` で、`rbx = 4k`・`k ∈ [0, 32]`。x に依らない定数。float 入力 `x` の値域は不要。
- **受入 3 (表 `0x1810df738` の走査・範囲縮小後): 達成 (範囲縮小後。残件は #3941)。** 表の値 (dword) を PE の全 section で走査した。5 slot に届く添字 (`180703b7c`: 87,069・87,074〜87,077、`180703913`: 87,075・87,080〜87,083) と一致する値は、`.rdata`〜`.reloc` の file 上の dword に **0 件**。`.text` に 46 件 (a < −28,494) あるが、表の位置としては負側の遠方。残りは §6 (#3941)。
- **元の受入 1 (4 命令の動的最大添字): 移管 (#3940)。** baseline (closure 131) に 4 命令を含む関数は無く、4 命令の RIP による zero-fill 域アクセスは 0 件。直接 entry の 3 関数も到達しなかった (§5)。動的採取は未実施で、§6 の子へ移す。

## 2. 表の走査 (受入 3)

`python3 tools/icall/diff/index_table_scan.py <SlateCore.core_64>` の出力 (`a` は表の添字 `(p − 0x1810df738) / 4`、符号付き)。

| section | VA | 一致 | a の範囲 | 備考 |
|---|---|---|---|---|
| `.text` | `0x180001000`〜`0x1810c3a00` | 46 | [−4,422,094, −28,494) | 全件が負の添字。`p` は関数の機械語のバイト列 |
| `.rdata` | `0x1810c4000`〜`0x18125be00` | 0 | [−28,110, 389,554) | 表の所在 (読取専用) |
| `.data` | `0x18125c000`〜`0x18128f400` | 0 | [389,682, 442,162) | 書込み可。実行時の値は file と違い得る |
| (gap) | `0x18128f400`〜`0x18130a000` | 未走査 | [442,162, 567,858) | zero-fill (ZLO〜ZHI)。実行時の値は file に無い |
| `.pdata`・`_RDATA`・`.rsrc`・`.reloc` | `0x18130a000`〜`0x182318600` | 0 | [567,858, 4,776,882) | |

- 読取専用の `.rdata` と、その後ろの `.pdata`〜`.reloc` では、5 slot に届く値は 1 つも無い。表の全長を決めなくても、この区間の添字からは届かない。
- `.data` の一致 0 件は file 上の初期値の話で、実行時の書込みは未確認。gap (zero-fill) は file に値が無いので、実行時の値に依る。

### 2.1 ネガティブコントロール (合成 PE・実機ではない)

実機の `SlateCore.core_64` は本 run で使えない (§6 の未解決)。代わりに `bash tools/icall/diff/index_table_scan_selftest.sh` が、表の a=3 (p=`0x1810df744`) に値を置いた合成 PE (`.rdata` 1 section) を走査する。rc=0・4 件 PASS。

| 件 | a=3 に置いた値 | 結果 (`.rdata` の行) |
|---|---|---|
| 正 1 | 87,069 | 一致=1・`p=0x1810df744 v=87,069 a=3 site=180703b7c` |
| 正 2 | 87,075 | 一致=1 (dword 1 個に site 2 件)・`site=180703b7c,180703913` |
| 負 1 | 87,070 (どの site にも届かない) | 一致=0 |
| 負 2 | 全 dword 0 | 一致=0 |

- 壊したときに FAIL することの確認: `SITES` の `disp` を 8 ずらす (`0x125C7E8` → `0x125C7E0`) と、正 1 が一致=0 で FAIL、負 1 が一致=1 で FAIL となり rc=1 (数値)。対照は走査の検出の変化を捉える。
- 本 PR の修正 (未使用変数 `disp_site` の削除) の前後で、合成 PE の出力は `cmp` 一致 (差 0 行)。

## 3. 経路の前提 (受入 3 の補足)

- `180703b7c` の添字 `rcx` は `180703b74` `movsxd rcx,[rbx+rax*4+0x10df738]` の表値だけが源 (`rbx = 0x180000000`、`180703b6d` の `lea` は `jne` が取られた経路でだけ通る)。`180703913` も `18070390b` の表値だけが源。
- `180703913` の到達判定の前提は `180cbb930` が `r13` を保存すること。`180cbb930` の本体 76 行 (`ret` まで) に `r13` を書く命令は無い (`push rdi` と `sub rsp,0x30` だけ)。ただし直接の呼出し先 (`180cbcd90`・`180cb9890`) と間接の呼出し (`call [rax+0x8]`・`call [rax+0x10]`) の保存は未確認。
- `0x180702f50` は out 引数 `[rsp+0x24]` を返す (`180703a47` で呼出し)。その値の範囲は未確定 (#3941)。

## 4. 届く添字 (参照)

`index_reach.py` の値 (基底 `0x180000000`): `180703913` は 87,075・87,080〜87,083 (5 件のうち 5)、`180703b7c` は 87,069・87,074〜87,077。float 2 件は k ∈ [0, 32] の範囲に届かない (§1 受入 2)。表の走査 (§2) で、これらの値が表の file 上の値として現れないことを確認した。

## 5. 動的 (元の受入 1 の試行と、受入 1 の baseline)

- baseline (受入 1): `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh`。測定 commit `512b09ff` (`origin/main`)。結果は §1 のとおり (n=1)。所要時間と load average は n=1 のため書かない (WORKFLOW §5。再測定は素材が無く不可)。`tools/icall/work/slot_trace_enc.txt` の ACC 35 件のうち、4 命令 (`180703913`・`180703b7c`・`1806dbe61`・`1806f7431`) の RIP は 0 件。既知 12 のうち hit 3 は `0x1813068f8`・`0x1813073f0`・`0x181307418` で、前付録と一致。
- 直接 entry (`tools/icall/work/slot_trace <FA> <fn>`): `180703880` は `180cbb940` で fatal (`addr=0x4c`・引数 struct が無い)。`1806dbc10`・`1806f71e0` は rc 0 で ACC 0 件 (既定の heap 引数では `[rsi+0xb58]` が mode==2 にならず、float の分岐に入らない)。3 関数とも closure 131 の `map.json` には無い。
- 結論: 動的に 4 命令の添字を採取した事実は無い。0 件は「到達しない」の証明ではない。引数を与えた直接 entry と、int3 を使わない採取方法が要る (§6 の #3940)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 4 命令の動的最大添字 (元の受入 1)。int3 は closure の挙動を変えるため不採用。直接 entry には引数 struct が要る | 届く添字との差が未記録 | #3940 (ICALL-91) |
| `0x180702f50` の返す dword の値域 (`[rsp+0x24]` の書込み元)。表の `.text` 一致 46 件 (a < −28,494) と zero-fill gap (a ∈ [442,162, 567,858)) の判定 | `180703b7c` の届き判定が gap と負側で未確定 | #3941 (ICALL-92) |
| `180cbb930` の直接・間接呼出し先が `r13` を保存すること | `180703913` の到達判定の前提 | #3941 (ICALL-92) |
| 実機 `SlateCore.core_64` での再実行 (走査・objdump・baseline) と、実機のネガティブコントロール (`.rdata` の 1 dword を a の範囲内の 87,069 に書き換えて 一致=1、元に戻して 一致=0)。§2.1 は合成 PE での代替 | 実機の検出力と、§2 の実機値の再現が本 run では未確認 (素材 `plugins-freshair`・`work-icall` が本 run に無い) | #3941 (ICALL-92)。同じ素材で実施 |

## 7. 検証

- 測定 commit: `512b09ff` (`origin/main`)。baseline (§1 受入 1) の測定対象の差分: `git diff 512b09ff HEAD -- tools/icall/diff/slot_trace.sh tools/icall/diff/slot_trace.c tools/ott tools/targets/freshair` は 0 行。
- `index_table_scan.py`: 実機の走査 (§2 の表・9,071,232 dword) は PR 作成時の版 (`0c8c2b289`) で得た値。その後の変更は未使用変数の削除のみで、合成 PE の出力は一致 (§2.1)。実機での再実行は本 run で不可 (§6)。
- 合成 PE の負の対照: `bash tools/icall/diff/index_table_scan_selftest.sh` rc=0 (4 件 PASS・§2.1)。
- `objdump -d -M intel`: 4,553,159 行 (前付録と一致)。本 run では再実行していない (素材不足)。

## 8. 再現

```
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
objdump -d -M intel "tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64" > tools/icall/work/core64_dis.txt
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
python3 tools/icall/diff/index_reach.py tools/icall/work/core64_dis.txt
python3 tools/icall/diff/index_table_scan.py "tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
bash tools/icall/diff/index_table_scan_selftest.sh
```
