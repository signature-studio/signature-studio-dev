# 付録: icall #2197 (ICALL-62) — encoded slot 表 T1/T2 の到達範囲と既知 12 slot の判定

> 親: #2170 (ICALL-61)。前付録: `REPORT_APPENDIX_2170.md`。本 run は受入条件 2 (既知 12 slot の判定) と、
> 表の範囲の上限・起点の再確認まで。受入条件 1 (終点・entry 数の確定) と受入条件 4 (OTT api-set 表との形式比較) は未達。

## 1. 結論

- 受入条件 1 (T1・T2 の終点・entry 数の確定): **未達**。静的参照は両表とも 3 箇所ずつ (計 6 箇所・全てディスパッチャ内)。
  表が `.data` 内に収まると仮定すると上限は `0x18130a000` (T1 1504・T2 1484 entry)。仮定であり、終点の確定ではない。
- 受入条件 2 (既知 12 slot が確定した表に含まれるか): **部分達成**。判定は §2.2。12 件中 7 件は T1/T2 の index 域内に入る。
  残り 5 件 (`0x1813068d0`・`0x1813068f8`・`0x181306900`・`0x181306908`・`0x181306910`) は T1/T2 の起点より下で、
  **どちらの表からも読めない**。別表の可能性が高いが、未確定。
- 受入条件 3 (fatal RIP): 本 run の対象外 (#2198 へ移管済み)。
- 受入条件 4 (OTT api-set 表 `0x18026c9f0` との形式比較): **未達**。OTT 側の事実のみ §3 に記録。

## 2. 実測

### 2.1 ベースライン再現

`SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (closure 131 関数):

- 測定 commit: `ce200f95` (コードを変えた commit。変更は `tools/icall/diff/slot_table_reach.py` の追加のみ)。
- 所要 12.997 s (real) / user 11.026 s / sys 1.817 s。load average 0.64 (10:18, 開始時)。
- 結果: funcs 131 / exit rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8 / zero-fill VA 7 個 / 既知 12 中 hit 3・miss 9。
- #2170 (REPORT_APPENDIX_2170 §2.1) のベースラインと一致。
- 鮮度の根拠: 直前の `origin/main` の `f5d2aa3b` から測定 commit `ce200f95` までの測定対象範囲の差分は 0 行。

```
$ git diff f5d2aa3b ce200f95 -- tools/icall/diff/slot_trace.sh tools/icall/diff/slot_trace.c tools/ott tools/targets/freshair tools/icall/work
(出力なし・0 行)
```

### 2.2 既知 12 slot と T1/T2 の index 域

T1 起点 `0x181307100`・T2 起点 `0x1813071a0` (ディスパッチャ `0x18105de80` の参照形 `[r14+rsi*8+0x1307100]`・`[r14+r15*8+0x13071a0]`、
`r14 = 0x180000000`)。index は 32bit 無符号で zero-extend されるため、表から読める最小 VA は各起点。

| 既知 slot | T1 | T2 |
|---|---|---|
| `0x1813068d0`・`0x1813068f8`・`0x181306900`・`0x181306908`・`0x181306910` | 不可 (起点未満) | 不可 (起点未満) |
| `0x1813072b0` | index 54 | index 34 |
| `0x1813073f0`・`0x1813073f8`・`0x181307400`・`0x181307408`・`0x181307410`・`0x181307418` | index 94–99 | index 74–79 |

判定の出所: `tools/icall/diff/slot_table_reach.py` (入力は `objdump -d -M intel` の出力を `tools/icall/work/core64_dis.txt` に置いたもの。gitignore 対象)。
ディスパッチャ内の `r14`-indexed 参照は全 6 箇所 (T1 ×3・T2 ×3) で、他の関数からは同じ形の参照が無い。

### 2.3 表の上限

`.data` (VA `0x18125c000`・VirtualSize `0xae000`) の末尾は `0x18130a000`。ここまでの最大 entry 数は
T1 `(0x18130a000 - 0x181307100) / 8 = 1504`・T2 `(0x18130a000 - 0x1813071a0) / 8 = 1484`。
これは上限で、実際の終点ではない。`0x181306000`〜`0x18130a000` の RIP 相対参照先は 913 種あるが、どの参照がどの表に属するかは静的には決まらない (ディスパッチャ外からの参照は T1/T2 の形では無い)。

### 2.4 fatal 行の観察 (参考)

`fatal_base.txt` の `0x18105de80` (ディスパッチャ) 由来の 1 件は `rip=0x18105deaf` (`mov rcx,[r14+r15*8+0x13071a0]`)・`addr=0x401307220`。
`r15` が呼び出し側の `ecx` から来るため、この fault は表の範囲を示さない (`addr - r14 - disp = 0x280000080`、すなわち `r15 = 0x50000010` で、表の外を指している)。
これは #2198 (ICALL-63) の範囲として扱う。

## 3. OTT 側の事実 (比較の材料・未比較)

`tools/ott/crtinit/REPORT.md` より: api-set 表 `0x18026c9f0` は 32 entry・256 バイト、静的には全 0。
decode は `ror(entry ^ cookie, cookie & 0x3f)`。cookie は `0x180260ce0`・静的既定 `0x2b992ddfa232`。
SlateCore の cookie は `0x18125eaa8` で、rot は 50 (`0x32`)。形式 (cookie で encode・zero-fill) は同じだが、
SlateCore 側の entry 数・slot 配置はまだ比較していない (未達)。

## 4. 再現

```
bash tools/ott/native/build.sh   # 初回のみ (ott_native)
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
objdump -d -M intel "tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64" > tools/icall/work/core64_dis.txt
python3 tools/icall/diff/slot_table_reach.py tools/icall/work/core64_dis.txt
```

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| T1・T2 の終点と entry 数の確定。動的に読まれた最大 index の採取 (`slot_trace` の ACC を index 付きで記録) | 受入条件 1 | #2226 (ICALL-66) |
| 既知 12 中 5 件 (`0x1813068d0`〜`0x181306910`) が読まれる表の特定 (T1/T2 以外の表) | 受入条件 2 | #2224 (ICALL-64) |
| OTT api-set 表 `0x18026c9f0` との形式比較 (entry 数・slot 配置) | 受入条件 4 | #2225 (ICALL-65) |
