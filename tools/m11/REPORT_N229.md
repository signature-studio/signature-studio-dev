# M11 REPORT (#4906 / [M11-N229] / 親 #4891): set_other 非 imm の書込可能グローバル 3 件 (VA 0x15e3a70) の格納元探索

結論: 3 件 (`global_store`) は 3 件とも VA `0x15e3a70` を読む。IR 全体と PE 全関数の直接経路 (rip 相対 store・lea・即値・絶対ポインタ) で、このアドレスへの格納は **0 件**。計算で作ったポインタ経由の格納は見えないため、格納値は決まらず区分は **未決 3** のまま。実測 **実値化 0・未決 3・未分類 0** (gep 17 は対象外・#4905)。測定 commit `9c26acf68`。

## 1. 入力と手順

- 素材 `work-m11` (`tools/m11/work/boot_final.ll` sha `69c774ded8aaf717`) と `fl-win64` の `block00031_PE.bin` (sha `b2c64da40921cf26`) は REPORT_N227 と一致。
- 中間物は素材に無いため作り直した (`tools/m11/work/sigfix_stats/`・gitignore): `m11_post.py` → `m11_argrecover.py` → `m11_setother_nonimm_class.py` → `m11_setother_mem_class.py` (REPORT_N174 と一致: 実値化 8・未決 248・gep 17・global_store 3)。
- 測定: `python3 ../m11_setother_gep_global.py sigfix_stats/mem_class_rows.json --ir boot_final.ll --out sigfix_stats/gep_global_rows.json --pe $PE` (HEAD `9c26acf68`・rc 0・real 38.2 秒・1 プロセス単独)。

## 2. 測定結果

```
[gep-global] 対象 20 件 (gep 17・global_store 3)
  実値化   0
  復元不能 0
  未決     20
  未分類   0
  gep            base_ssa_unmapped        17
  global_store   no_store_in_ir           3
  global_store function_1014ff0 va=0x15e3a70 stores=0 []
  global_store function_11ff040 va=0x15e3a70 stores=0 []
  global_store function_12b4e30 va=0x15e3a70 stores=0 []
```

- 3 件の VA は `def + 7 + disp` で `0x15e3a70` (3 件とも一致)。VA は `.data` (MEM_WRITE) の `0x23ea70` に当たる。
- 初期値 (PE の `.data` 上のバイト): `0x15ec3b0`。
- IR (`boot_final.ll`): VA 直接参照は `function_6520b0` の `inttoptr i64 22952560` の load 1 箇所のみ。store 0 件。定数ポインタの store は全 IR で 1 件 (VA 無関係)。計算ポインタ経由の store 50,093 件は別名解析が無く判定できない。
- PE (`--pe`・分類器の `pe_direct_stores`): 全 57,816 関数を走査し、対象 VA への経路を数えた。`rip_store` 0・`lea` 0・`imm` 0・`abs_ptr` 0。
  - 対照: 同じ走査で PE 内の rip 相対 store `dword ptr [rip+0x11df651], eax` (VA `0x15e6bbc`) を検出し `rip_store` 7 件。検出経路が働くことを確認した。
  - 対象 VA への rip 相対 load は 351 件あった (`function_…` の `mov r8, qword ptr [rip+…]` 等)。読込みだけで、格納は無い。

## 3. 限界

- 「格納 0 件」は直接経路の 0 件であって、計算で作ったポインタによる格納が無いという証明ではない。`store_value_unchecked` 区分の値を決めるには、到達定義・別名解析が要る (未実装)。
- 実値化 0 は分類規則から決まる値で、実測ではない。`pe_hits` の 0 も同様に走査の結果。
- `pe_direct_stores` の `lea` 検出は `rip +` の形だけを見る。`[rip - d]` の形は数えていない (今回の対象 3 件は `rip +` の形)。
- `target_va` は `def + 7 + disp` の固定長前提。REPORT_N227 §4 のとおり、本 run でも命令長は確認していない (3 件は qword で 7 バイト)。
- `m11_argrecover_verify.py` は set_const 専用のため照合対象が無い (実値化 0 件)。

## 4. 差分

- 測定 commit `9c26acf68` (`m11_setother_gep_global.py` の `--pe` 経路を追加)。
- 測定後に変えたのは REPORT のみ (コード差分 0)。`git diff 9c26acf68 HEAD -- tools/m11/m11_setother_gep_global.py` の出力は、本 PR の commit 時点で 0 行。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 計算ポインタ経由の格納 (IR 50,093 件のうち VA 到達を持つもの) の別名解析と、格納値の到達定義 | global_store 3 件の値が未決 | #4891 (親) のチェックリストに追記 |
| gep 17 件の基底 SSA 対応付け | 同上 (gep) | #4905 (M11-N228) |
