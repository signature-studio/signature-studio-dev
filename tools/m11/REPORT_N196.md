# M11 REPORT (#3906 / [M11-N196] / 親 #3142): set_other 非 imm のスタック slot 読込・frame lea 110 件の接続

結論: 非 imm 台帳のうち、スタック slot 読込 (load_stack 50・chain>load_stack 1) と frame 内 lea (lea_stack 59) の 110 件を、呼出し元の機械語と frame 定数 C から IR の stack_var (alloca) に接続して分類した。測定 commit `fe41cc75` の実測は **実値化 25 / 復元不能 0 / 未決 85 / 未分類 0** (§2)。実値化は全て lea の接続 (alloca の番地)。スロット読込 51 件は同じ slot への格納を直線区間で見つけられず、実値化 0 件だった。接続の IR への注入と未決 85 件は子 issue #3932 (N201)・#3933 (N202) に移した。

## 1. 接続方式 (決めたこと)

- 入力: `m11_setother_nonimm_class.py` の出力 `nonimm_class_rows.json` のうち、理由が `load_stack`・`chain>load_stack`・`lea_stack` の行 (110 件)。
- スクリプト: `tools/m11/m11_setother_mem_class.py` (IR は変更しない・分類のみ)。
- **frame 定数 C**: 呼出し元の prologue で、entry rsp から `mov rbp, rsp` までの減算量 (push 1 つ 8・`sub rsp, imm`)。例: `function_10c7cd0` は `push` ×3 (24) + `sub rsp, 0x4cf0` で C = 0x4d08 = 19720。
- **IR 名の対応**: retdec の `stack_var_X` は X = d − C (機械語の `[rbp+d]`)。`function_10c7cd0` で確認: `[rbp+0x4be0]` → `stack_var_-296`、`[rbp+0x2e0]` → `stack_var_-18984` (IR の既存の参照と一致)。
- **lea_stack (59)**: `lea r, [rbp+d]` を、呼出し元 IR の `%stack_var_(d−C) = alloca` (接尾辞なしの定義) に接続する。定義があれば実値化 (値 = その alloca の番地)。定義が無ければ `lea_alloca_absent` (未決)。接尾辞付き (`.reg2mem` 等) の定義だけなら `lea_alloca_suffixed` (未決)。
- **load_stack (51)**: `[rbp+d]` の読込 (`mov r, qword ptr [rbp+d]`) の直前で、同じ slot への最後の格納を直線区間で後ろ向きに探す。区間の打ち切り条件は次のとおり。
  - 分岐先 (直接分岐の飛び先) を越える: `slot_merge`
  - call を越える: `slot_call` (slot のアドレスが漏れているかを判定せず、保守的に止める)
  - ret・jmp: `slot_branch`
  - rsp・rbp の変更: `slot_base`、別の基底レジスタの書込み: `slot_alias_base`、ポインタ経由の書込み: `slot_ptr_write`、slot に重なる別幅の書込み: `slot_overlap`
  - 格納が見つかった場合: `mov qword ptr [rbp+d], imm` なら実値化 (`slot_imm`)、reg 格納は未決 (`slot_reg`・未追跡)
  - 区間の先頭まで格納が無ければ `slot_entry`
  - frame 定数が求まらない (rsp で先に動かす prologue 等): `no_frame`

## 2. 測定 (測定 commit `fe41cc75`)

- 入力: `work-m11` の `tools/m11/work/boot_final.ll` (`m11_post.py` の既定出力 sha `ecab191b…`・REPORT_N86 と一致)、PE は `fl-win64` の `extracted/block00031_PE.bin` (sha `b2c64da4…`)。
- 手順: `m11_post.py` → `m11_argrecover.py` (台帳 410 件・非 imm 349 件。REPORT_N171 と一致) → `m11_setother_nonimm_class.py` (349 件・未決 349。REPORT_N171 と一致) → `m11_setother_mem_class.py nonimm_class_rows.json --pe PE --ir boot_final.ll`。
- 結果 (stdout): 対象 110 件、実値化 25・復元不能 0・未決 85。

| 台帳 kind | 理由 | 件数 | 区分 |
|---|---|---|---|
| lea_stack | lea_alloca (alloca に接続) | 25 | 実値化 |
| lea_stack | lea_alloca_absent (alloca 不在) | 34 | 未決 |
| mem_stack | slot_merge (分岐先越え) | 23 | 未決 |
| mem_stack | slot_call (call 越え) | 18 | 未決 |
| mem_stack | no_frame (frame 定数が求まらない) | 5 | 未決 |
| mem_stack | slot_ptr_write | 2 | 未決 |
| mem_stack | slot_alias_base | 1 | 未決 |
| mem_stack | slot_reg (reg 格納・未追跡) | 1 | 未決 |
| reg (chain>load_stack) | slot_call | 1 | 未決 |
| **合計** | | **110** | **実値化 25 / 復元不能 0 / 未決 85 / 未分類 0** |

- 実値化した 25 件の値は alloca の番地 (ポインタ)。例: `function_1014ff0` → `function_443f90` の pos 0 は `&%stack_var_-16` (`lea rcx, [rbp+0x48]`)。
- load_stack の実値化は 0 件。同じ slot への格納が直線区間にある件が無かった。最多は分岐先越え (23)・call 越え (18)。

## 3. 検証と限界 (受入 3 の判定を含む)

- **C の検証**: 呼出し元 IR に `stack_var_(d−C)` の定義があるのは 110 件中 36 件 (`C 検証: 在 36 / 無 69`)。ここから「C 規則がずれている」か「alloca が無い (配列の内部など)」かは切り分けていない。lea の 25 件は、定義の存在を確認した件だけ。名前の存在だけでは誤った C でも偶然当たりうるため、IR の既存の参照との突合は未実施 (#3933 で行う)。
- **受入 3 (照合)**: 実値化 25 件の値は alloca の番地で、定数 (`fixes.json` の `const`) ではない。`m11_argrecover_verify.py` の照合対象外のため、**該当なし** (定数の実値化は 0 件)。
- IR への注入は行っていない。接続の値は `tools/m11/work/sigfix_stats/mem_class_rows.json` にだけ書いた (gitignore 対象)。注入と survey の前後比較は #3932 (N201)。

## 4. 測定 commit と差分

- 測定 commit: `fe41cc75` (`m11_setother_mem_class.py` の追加。コードを変えた最後の commit)。以後の commit は REPORT (md) のみ。
- 測定 commit から HEAD までのコード差分 (`git diff fe41cc75 HEAD -- tools/m11 ':(exclude)*.md'`) は、この REPORT の commit 時点で 0 行。
- 再測定: コミット済みの `fe41cc75` の script で同じ入力を流し、件数が一致 (実値化 25・未決 85。出力 `mem_class_rows_head.json` の sha `b73f8515…`)。

## 5. 受入条件の判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. 110 件を 実値化 / 復元不能 / 未決 で件数実測・未分類 0 | **達成** | §2 (25 / 0 / 85 / 0) |
| 2. 接続方式 (どの store・alloca を対象とするか) を REPORT に書く | **達成** | §1 |
| 3. 実値化した値を `m11_argrecover_verify.py` で照合 | **該当なし** | 実値化の値は alloca の番地で定数ではない (§3) |

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 接続 25 件 (lea_alloca) を IR の 0 詰め call 引数に入れていない・survey 未測定 | IR の値が未決のまま | #3932 ([M11-N201]) |
| 未決 85 件 (slot_merge 23・slot_call 18+1・lea_alloca_absent 34・no_frame 5・その他 4) | 接続先が無い | #3933 ([M11-N202]) |
| C 規則の IR 突合 (定義あり 36/110) | 接続 25 件の正しさが名前の存在だけで確認されている | #3933 ([M11-N202]) |
