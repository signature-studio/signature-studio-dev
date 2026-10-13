# REPORT_704 — unit 415 の function_9b4b00 (closure 外 miss) の C 転記と ON 退行の再測定 (#704, 親 #595 / PR #657)

結論: `9b4b00` は ON の `410360` (`[vmt-0x50]` 経由) からだけ呼ばれる closure 外関数。`9b5450` と合わせて C 転記 (ON 時のみ) し、unit 415 の ok→miss を解消した。
ON の ok 退行は **4 件 (101 190 291 296)** に残る。これは本変更前から存在する別原因 (`0x41037d` の新規 hit による `VA-big` の oob) で、受入条件 2 は未達。

## 1. 基準 (本 run で再生成)

`work-m11` スナップショットの IR は qstore 以前のため、`m11_gen_ir2.sh` (`FL_WIN64_DIR`=fl-win64 展開先、capstone・pefile 導入後) で IR を作り直した。
REPORT_595 の表 (817 / 47 / 21 / 56) とは IR が違うため、数値は直接比較できない。

- `m11_gen_ir2.sh`: 32.1 s (rc=0)。ldfix=applied (F1=902 ほか、errors=0)。qstore=applied (build 時)。
- `m11_build.sh` (ON): 18.7 s、(OFF): 13.8 s (ともに rc=0、signature mismatch 0・undefined symbol 0)。
- `survey_units.mjs`: ON 8.8 s / OFF 9.2 s (単発、並列数 1、load average 0.55–0.63)。
- 再測定は指摘 1 (`function_481790` の prototype 追加) の commit 後の HEAD で行った。

## 2. 測定 (同一 IR・同一 build 系列)

| 構成 | コード | ok | oob | halt0 | miss | noproc | ok 退行 |
|---|---|--:|--:|--:|--:|--:|---|
| 既定 OFF (転記前) | `m11_ov.c` 本 run 開始時 | 869 | 17 | 8 | 47 | 1 | — |
| ON (転記前) | 同 | 866 | 19 | 8 | 48 | 1 | 5: 101 190 291 296 415 |
| 既定 OFF (転記後) | 本 PR | 869 | 17 | 8 | 47 | 1 | 対照と unit 単位で差 0 |
| ON (転記後) | 本 PR | 867 | 19 | 8 | 47 | 1 | 4: 101 190 291 296 |

- ON 転記後で 415 は `ok` (`icall` は `0x9b4b00`: ok 1)。転記前は `miss_new` = `0x5b4b00` (= `0x9b4b00` の VA 表記)。
- 転記後の ON は、転記前の ON と比べて ok→miss が 1 (415) 減り、他の kind 遷移は増えていない。
- OFF は転記前後で unit 単位の差 0 (`survey_diff.py`: kind 以外も含めて差分 unit 0)。
- ON と OFF の unit 単位差 (942 unit 中 6 件、`su_on.json` / `su_off.json` の kind 比較): 101 190 291 296 は ok→oob (ON 退行)。304 555 は oob→ok (ON で改善)。415 は ON/OFF とも ok。ON の oob 19 = OFF の 17 + 上記 4 − 2。

## 3. 9b4b00 の原因と転記

- 呼び出し: `410360` の `call [rbx-0x50]` (VA 0x41037d) の target が `9b4b00` (ON のみ)。closure 外 (`boot_fns.json` に無い、IR 定義なし)。
- 機械語 (`disasm_img.py`): `410070` (ret 実体) → `481790` → `9b5450` → `4133f0` → `412d60` ×2 を呼ぶ 103 byte。
- 転記: `function_9b4b00` / `function_9b5450` を `m11_ov.c` の `#if M11_OV_CLASSCREATE` ブロックに置いた (`410070` は ret のため省略、`rcx` 読込は `R(0x805a8)`)。`disp_find` に `0x9b4b00` を登録。
- 転記の不具合: 初版で `[rbx+0x34]` の byte 書込みを 4 byte で書いていたため、1 byte 書込みに直した。
- `481790` の prototype: 逆アセンブル (`extracted/block00031_PE.bin`, VA 0x481790) で rcx = ptr・dl = flag (1 byte)、rax = ptr 幅の戻り値 (`return [rbp+0x60]`、u64 で切り捨て無し) を確認し、`extern unsigned long long function_481790(void* rcx, unsigned long long dl);` を明示した (前は暗黙宣言)。prototype 追加後も数値は不変。

## 4. 残る ON 退行 (101 190 291 296)

- ON で `0x41037d` (410360 の VMT 間接 call) が各 unit で新規に 1 hit し、`VA-big` (`size=131399680`) 経由で oob になる。
- OFF では `0x41037d` は 0 hit。REPORT_679 (`0x41037d` の暴走) と同じ site だが、unit 101 以外の 190/291/296 も含むため、REPORT_679 の数値とは別の経路と見る。
- 原因は未特定。受入条件 2 の残件として子 issue に起票する。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ON の ok 退行 4 件 (101 190 291 296): `0x41037d` の新規 hit → `VA-big` oob の原因特定 | ON を既定にできない直接の理由 (受入条件 2) | #912 (`[M11-N49]`, 親 #704) |
| REPORT_595 の表 (817 / 47 / 21 / 56) は旧 IR。現 IR での基準の再測定と REPORT_595 の注記 | 基準の不一致 | 上記子 issue に含む |
