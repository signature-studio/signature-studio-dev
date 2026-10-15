# M11 REPORT (#3142 / [M11-N174] / 親 #3134・#1154): set_other 非 imm のメモリ読込・lea 256 件の接続方式

結論: 台帳の非 imm 349 件のうち、メモリ読込・lea の 256 件を接続方式ごとに分類した (測定 commit `977bca62f`)。実測は **実値化 8 / 復元不能 0 / 未決 248 / 未分類 0** (§2)。実値化 8 件は、rip 相対で読み取り専用の `.text` から読む 1 バイトの定数 (`movzx … byte ptr [rip+d]`)。残り 248 件は IR の store・alloca・GEP への接続が要るため、子 #3906 (スタック slot・alloca 110 件) と #3907 (ポインタ経由・GEP・書込可能グローバル 138 件) に分けた (§5)。IR は変えていない。

## 1. 接続方式 (決めたこと)

分類器 `m11_setother_mem_class.py` が、各行の読込先と命令形から接続方式 (conn) を決める。

| 接続方式 (conn) | 命令形 (台帳 kind・理由) | 件数 | 区分 | IR で接続すべき対象 |
|---|---|---|---|---|
| const_read | `movzx r9, byte ptr [rip+d]` (mem_global・load_global) | 8 | **実値化** | (接続不要) 読込先が非書込セクション (.text)・Base Relocation に掛からない・PE バイトの値。movsx のみ符号拡張 |
| global_store | `mov r, qword ptr [rip+d]` で読込先が `.data` (mem_global・load_global) | 3 | 未決 | 呼出し元 CFG 上の最後のグローバル格納 (store) → #3907 |
| stack_slot | `mov rcx, qword ptr [rbp+d]` 等 (mem_stack・load_stack、chain>load_stack 1 件を含む) | 51 | 未決 | 同じ `[rbp/rsp+d]` slot への最後の格納 (CFG 到達定義) → #3906 |
| alloca | `lea rcx, [rbp+d]` (lea_stack) | 59 | 未決 | フレーム slot に対応する alloca → #3906 |
| ptr_mem | `mov rcx, qword ptr [rax+d]` 等 (mem_ptr 89・reg 由来 load_ptr 28・chain>load_ptr 1) | 118 | 未決 | ポインタ先のメモリ SSA (別名解析が要る) → #3907 |
| gep | `lea rcx, [rdi+d]` 等 (lea_ptr) | 17 | 未決 | 基底 reg の SSA 値に対する GEP → #3907 |
| reloc_global | (読込先が読取専用だが fixup に掛かる) | 0 | — | 該当なし |

- 実値化の条件: 読込先が `IMAGE_SCN_MEM_WRITE` の無いセクション・Base Relocation の fixup と範囲が重ならない・読込幅 (byte/word/dword/qword) の値が PE ファイルのバイトと一致する (§2)。
- 未決 `.data` 3 件は書込可能なので、初期値を使うと実行時の格納を見落とす。決めるには格納 (store) の接続が要る。
- 「復元不能」は本測定で 0 件。読込元が保証されないと判定できる件は無かった (未決に分類)。

## 2. 測定 (HEAD の実測)

- 入力 (REPORT_N171 §2 と同一): `work/boot_final.ll` (sha `69c774ded8aaf717`)・PE `fl-win64` の `extracted/block00031_PE.bin` (sha `b2c64da40921cf26`)。
- 中間物 (すべて rc 0・`tools/m11/work/sigfix_stats/`・gitignore 対象): `m11_post.py` の既定出力 sha `ecab191b13590dd0` (REPORT_N86 §4 と一致)・`m11_argrecover.py` の台帳 → `m11_setother_nonimm_class.py` が **未決 349 / 未分類 0** を再現 (REPORT_N171 §2 と一致)。
- 測定: `python3 m11_setother_mem_class.py work/sigfix_stats/nonimm_class_rows.json --pe PE` (HEAD `977bca62f`・rc 0・real 1.98 秒・load は 1 プロセス単独)。出力は `work/sigfix_stats/mem_class.out`。

```
[mem-class] 対象 256 件 (load_*/lea_*/chain>load_*)
  実値化   8
  復元不能 0
  未決     248
  未分類   0
[mem-class] 接続方式 × 区分 (件数)
  alloca           未決       59
  const_read       実値化      8
  gep              未決       17
  global_store     未決       3
  ptr_mem          未決       118
  stack_slot       未決       51
```

- 実値化 8 件 (全件 `movzx … byte`・幅 8・読込先 `.text`):

| 呼出し元 | 定義命令 | 値 |
|---|---|---|
| function_12e38e0 | `movzx r9, byte ptr [rip + 0x70]` | 0x1 |
| function_dcdde0 | `movzx rdx, byte ptr [rip + 0xc3]` | 0x0 |
| function_e599d0 | `movzx r9, byte ptr [rip + 0x1c]` | 0x0 |
| function_e7d8e0 | `movzx r9, byte ptr [rip + 0x322]` | 0x0 |
| function_e7d8e0 | `movzx r9, byte ptr [rip + 0x98]` | 0x0 |
| function_e7e290 | `movzx r9, byte ptr [rip + 0x17]` | 0x1 |
| function_e83850 | `movzx r9, byte ptr [rip + 0x84]` | 0x0 |
| function_ea6a40 | `movzx r9, byte ptr [rip + 0x24]` | 0x1 |

- 照合: 実値化 8 件の値は、ldmach (capstone 経由) で読んだバイトと、生の PE ファイルのオフセット読み (`raw_read`) が一致した。不一致は分類器が未決 `verify_mismatch` に落とす (本測定 0 件)。
- `m11_argrecover_verify.py` は set_const (mov imm・xor) 専用で、load 由来の値は対象外。よって同スクリプトは実行していない (0 件ではなく対象外)。代替照合は上記 `raw_read`。

## 3. 差分

- 測定 commit: `977bca62f` (`m11_setother_mem_class.py` を追加した commit。分類器を最後に変えた commit)。
- `git diff 977bca62f HEAD -- tools/m11 ':(exclude)*.md'` の出力: 0 行 (以後の commit は REPORT と DOC_MAP の md のみ)。
- IR (`m11_post.py`・`m11_argrecover.py`・`m11_setother_nonimm_class.py`) は変更していない。8 件の値は fixes へ反映していない。

## 4. 受入条件の判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. 256 件を 実値化 / 復元不能 / 未決 の 3 値で件数実測・未分類 0 | **達成** | §2 (8 / 0 / 248 / 0) |
| 2. 接続方式 (どの store・alloca を対象とするか) を REPORT に書く | **達成** | §1 |
| 3. 実値化した値を `m11_argrecover_verify.py` で一致 | **代替で達成** (`m11_argrecover_verify.py` は対象外のため、分類器内の `raw_read` 照合 8/8) | §2 |

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未決 110 件 (stack_slot 51・alloca 59) | 呼出し引数の値が未保証 (IR の slot 格納・alloca への接続が未実装) | #3906 ([M11-N196]) |
| 未決 138 件 (ptr_mem 118・gep 17・global_store 3) | 同上 (別名解析・GEP・グローバル格納の接続が未実装) | #3907 ([M11-N197]) |
| 実値化 8 件の fixes への反映 (IR 変更) と survey 退行 (`M11_SIGFIX_RECOVER=1`・ok ≥ 870) | IR は未変更。反映すると survey の影響は未測定 (`functions_dll.csv` が素材に無い) | #1154 |
