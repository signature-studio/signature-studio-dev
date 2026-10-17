# M11 REPORT (#6122 / [M11-N285] / 親 #4890): set_other 非 imm のポインタ経由読込 ptr_base_def 82 件の基底出所

結論: `ptr_base_def` 82 件の基底 reg の出所を直線区間で分類した。実測は **実値化 0 / 復元不能 0 / 未決 82 / 未分類 0** (測定 commit `ffc7f989e`)。基底の値を定数と決められた件は 0 のため、`m11_argrecover_verify.py` の照合は対象 0 件 (該当なし)。IR は変えていない (分類のみ)。

## 1. 方式 (決めたこと)

基底の出所は、読込 `mov r, <幅> ptr [base+d]` の直前で基底族を書き換えた命令 (`base_writer`) を直線区間で後ろ向きに探し、その命令の右辺で分ける (`base_origin`)。

| 基底の出所 | 判定 | 区分 | 理由 |
|---|---|---|---|
| 即値 `mov base, imm` | `base_const_imm` | 未決 | 定数だが、今回の出所は 0 件 |
| `[rbp+d]` (spill 経由) を読む | 同じ `[rbp+d]` への直線区間の最後の格納を探す | 下表 | 格納元が reg なら復元不能、即値なら未決 |
| 書込可能グローバル `[rip+x]` | `base_global` | 未決 | 別の書込みで値が変わりうる |
| 別のポインタ `[reg+d]` | `base_ptr_load` | 未決 | 再帰が要る (今回は止める) |
| reg 複写 | `base_copy_or_other` | 未決 | 今回は止める |

spill 経由の基底は、同じ `[rbp+d]` への格納を、呼出し・合流点を越えずに探す。呼出し (`call`) と分岐の合流点 (`merge`) を越えたら打ち切る。

- 判定の単体テストは既存の `test_setother_ptr_class.py` (9 件・PASS)。新しい分類は既存の reason 分類を変えない。

## 2. 測定 (実測)

- 入力: `work-m11` の `boot_final.ll` (sha256 先頭 `69c774ded8aaf717`) と `fl-win64` の `extracted/block00031_PE.bin` (先頭 `b2c64da40921cf26`)。REPORT_N242 と同一。
- 中間物 (gitignore・`tools/m11/work/sigfix_stats/`): `m11_post.py` → `m11_argrecover.py` → `m11_setother_nonimm_class.py` → `m11_setother_ptr_class.py`。
- 測定: `python3 m11_setother_ptr_class.py work/sigfix_stats/nonimm_class_rows.json --pe <PE> --out work/sigfix_stats/ptr_class_rows.json` (real 0.28 秒・load 0.17・`nproc` 4)。

```
[ptr-class] 対象 122 件 (load_ptr・chain>load_ptr)
  実値化      0
  復元不能     0
  未決       122
  未分類   0
[ptr-class] 理由別 (N242 と同じ)
  未決       ptr_base_def           82
[ptr-class] ptr_base_def の基底出所 (82 件)
  未決       base_slot_call         29
  未決       base_slot_merge        19
  未決       base_ptr_load          18
  未決       base_global            13
  未決       base_copy_or_other      3
```

- 82 件の基底の出所は、spill 経由 48 件 (`[rbp+d]` 読込: 呼出しを越える 29 件・合流を越える 19 件)、別ポインタ経由 18 件、書込可能グローバル 13 件、reg 複写 3 件に分かれる。
- spill 経由 48 件は、直線区間で同じ `[rbp+d]` への格納に届く前に呼出し・合流で打ち切られた。格納元の reg・即値は 1 件も見えていない。このため復元不能・未決の内訳 (`base_slot_const`・`base_slot_reg`・`base_slot_other`) は 0 件。
- `base_slot_reg` (格納元が reg なら復元不能) の分岐は実装したが、今回の 82 件では到達していない。
- 実値化 0 件のため、`m11_argrecover_verify.py` の照合は対象 0 件 (該当なし)。

## 3. 差分

- 変更: `tools/m11/m11_setother_ptr_class.py` (基底出所の分類 `base_writer`・`base_origin` と出力列 `base_class`・`base_reason` の追加。既存の reason は不変)。
- 測定 commit: `ffc7f989e`。`git diff ffc7f989e HEAD -- tools/m11/m11_setother_ptr_class.py` は本 PR の範囲で差分 0 (測定後に変えていない)。

## 4. 受入条件の判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| `ptr_base_def` 82 件が 実値化 / 復元不能 / 未決 の 3 値で件数を実測し、未分類 0 として REPORT に残る | **達成** | §2 (実値化 0・復元不能 0・未決 82・未分類 0) |
| 実値化した値を `m11_argrecover_verify.py` で照合する (0 件なら該当なし) | **該当なし** | 実値化 0 件 (§2) |

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼出しを越える spill 基底 29 件 | 呼出し先が slot を書く可能性があり、値を決められない | #4890 (親) の残作業 |
| 合流を越える spill 基底 19 件 | 分岐ごとに値が違う可能性があり、値を決められない | #4890 (親) の残作業 |
| 別ポインタ経由の基底 18 件・グローバル 13 件・複写 3 件 | 再帰の辿り (別名解析) が要る。今回は止めている | #4890 (親) の残作業 |
| 実値化した値の IR 注入 (`m11_post.py` 経路) | 実値化 0 件のため未実施 | #4890 (親) の残作業 |
