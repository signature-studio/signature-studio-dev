# M11 REPORT (#5392 / [M11-N242] / 親 #4890): set_other 非 imm のポインタ経由読込 (ptr_mem) の接続判定

結論: ポインタ経由の読込 122 件 (reason が `load_ptr` で終わる行。内訳は後述 §2) を、同じ関数内の同じ `[base+d]` への直線区間の格納で接続判定する分類器 `m11_setother_ptr_class.py` を追加した。実測は **実値化 0 / 復元不能 0 / 未決 122 / 未分類 0** (測定 commit `c988679dc`)。全件が未決で、接続先は理由別に残る。値を決められた件数は 0 のため、照合対象も 0 件 (該当なし)。IR は変えていない (分類のみ)。

## 1. 接続方式 (決めたこと)

分類器 `m11_setother_ptr_class.py` が、各行の読込 `mov r, <幅> ptr [base+d]` について、同じ関数内で**同じ `[base+d]` へ最後に格納した命令**を直線区間で後ろ向きに探す。

| 判定 (理由) | 条件 | 区分 |
|---|---|---|
| `ptr_imm` | 同じ基底・同じ幅・同じ disp の即値格納 | 実値化 |
| `ptr_reg_store` | 同じ `[base+d]` への reg 格納 | 未決 |
| `ptr_width_mismatch` | 同じ `[base+d]` への格納が読込と幅が違う | 未決 |
| `ptr_base_def` | 基底 reg の族を書き換える命令 (以後の `[base+d]` は別番地) | 未決 |
| `ptr_alias_write` | 基底が違う書込み (別名の可能性) | 未決 |
| `ptr_call` | 呼出し (別名の書込みが起きうる) | 未決 |
| `ptr_unknown_write` | メモリ書込みの可能性がある未知の命令・メモリ付き set* | 未決 |
| `ptr_overlap` / `ptr_index_write` / `ptr_abs_write` | 読込範囲と重なる別幅・index 付き・絶対番地の書込み | 未決 |
| `slot_merge` | 読込命令が分岐先 (合流点) | 未決 |
| `ptr_entry` | 区間が関数先頭まで届いた | 未決 |
| `frame_base` / `no_mem_operand` | 基底が rbp/rsp (別分類器の対象) / 定義命令にメモリ操作数が無い | 未決 |

- 基底の比較は 64bit 族で行う。8/16/32bit 名 (`eax`・`cl`・`r8d`・`r8b` など) はすべて対応する 64bit 族へ写す。部分書込みも基底の再定義として扱う (`mov cl, 5` や `mov r8d, 9` を挟んだ読込は `ptr_base_def`)。
- 判定の単体テストは `test_setother_ptr_class.py` (9 件・PASS)。負例 (別基底・reg 格納・幅違い・呼出し・基底再定義・先頭到達・部分レジスタによる基底再定義 2 件) と正例 (同基底の即値格納)。

## 2. 測定 (実測)

- 入力: `work-m11` の `boot_final.ll` (sha256 先頭 `69c774ded8aaf717`) と `fl-win64` の `extracted/block00031_PE.bin` (先頭 `b2c64da40921cf26`。REPORT_N174 と同一)。
- 中間物の生成 (`tools/m11/` で実行・すべて rc 0・gitignore 対象の `work/sigfix_stats/`):
  1. `python3 m11_post.py work/boot_final.ll work/sigfix_stats/final3_base.ll --pads work/sigfix_stats/pads.json`
  2. `python3 m11_argrecover.py work/sigfix_stats/pads.json --pe <PE> --out work/sigfix_stats/fixes.json`
  3. `python3 m11_setother_ledger_verify.py work/sigfix_stats/fixes.json --pe <PE>` → `match 410`
  4. `python3 m11_setother_nonimm_class.py work/sigfix_stats/fixes.json --pe <PE> --ir work/boot_final.ll` → `work/sigfix_stats/nonimm_class_rows.json` (`fixes.json` と同じ dir に出力される。`--out` は無い)・非 imm 349 件・`load_ptr` 行 122 件。
- 注記 (再現性): 手順 1 の出力 sha は `c029ada4…` で、REPORT_N86 / N174 の `ecab191b…` と一致しない。`cb45c284` 時点の `m11_post.py` で同じ入力から実行すると `ecab191b…` になるので、差は `m11_post.py` の `cb45c284` 以降の変更 (`eba68fdbe`・`622df694b` など、#3932 系) に由来する。ただし下流の件数 (`match 410`・非 imm 349・`load_ptr` 122) は REPORT_N174 と一致し、本 PR の 122 件の行単位の判定は旧版と同一だった。
- 測定 (修正 commit `c988679dc` で実行): `python3 m11_setother_ptr_class.py work/sigfix_stats/nonimm_class_rows.json --pe <PE> --out work/sigfix_stats/ptr_class_rows.json` (real 0.29 秒・load 1 プロセス単独・`nproc` 4・load average 0.56)。
- 対象 122 件の定義: `nonimm_class_rows.json` のうち、reason が `load_ptr` で終わる行 (`load_ptr` 117・`chain>load_ptr` 2・`stack_match>load_ptr` 2・`call_ret>ret>chain>load_ptr` 1)。この行の kind は set_other 120・stack_set_other 2。

```
[ptr-class] 対象 122 件 (load_ptr で終わる reason の行)
  実値化      0
  復元不能     0
  未決       122
  未分類   0
[ptr-class] 理由別
  未決       no_mem_operand         3
  未決       ptr_alias_write        2
  未決       ptr_base_def           82
  未決       ptr_call               17
  未決       ptr_unknown_write      2
  未決       slot_merge             16
```

- 対象 122 件の基底 reg は rax 71・rbx 33・rcx 11・rsi 6 (1 件はメモリ操作数なし)。50 関数に分布する。
- `ptr_base_def` 82 件の多くは、読込の直前で基底を別の値に書き換えている形 (`mov rcx, [rax+0xc0]` の連鎖)。同じ基底への格納が区間内に無いので未決。
- 実値化 0 件のため、`m11_argrecover_verify.py` の照合は対象 0 件 (該当なし)。

## 3. 差分

- 新規: `tools/m11/m11_setother_ptr_class.py`・`tools/m11/test_setother_ptr_class.py`・本 REPORT。既存の分類器・`ldmach.py` は変更していない。
- 測定 commit: `c988679dc` (分類器を最後に変えた commit)。`git diff 42b00e05e c988679dc -- tools/m11/m11_setother_ptr_class.py tools/m11/test_setother_ptr_class.py` の差分は本 PR の修正 (部分レジスタ対応)。

## 4. 受入条件の判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| 接続方式 (どの store・別名を対象とするか) を REPORT に書く | **達成** | §1 |
| 実値化した値を照合する (0 件なら該当なし) | **該当なし** (実値化 0 件) | §2 |

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ptr_mem 122 件の値 (実値化 0) | 呼出し引数の値が未保証。現方式 (同一基底の直線区間格納) では接続できない | #4890 (親) の残作業 |
| 基底 reg の再定義を跨ぐ接続 (`ptr_base_def` 82 件) | 基底の値を辿る別名解析 (reg の到達定義) が要る | #4890 (親) の残作業 |
| 呼出しを跨ぐ接続 (`ptr_call` 17 件) | 呼出し先の書込み範囲の解析が要る | #4890 (親) の残作業 |
| IR への注入 (実値化した値を `m11_post.py` に入れる経路) | 実値化 0 件のため未実施 | #4890 (親) の残作業 |

## 6. M11-N286 (#6123): 呼出しを跨ぐ接続 (ptr_call)

- 方式: 基底が非揮発 (rbx/rsi/rdi/rbp 等) の `call` は、呼出し先が **直接 call かつ再帰的に非スタック書込みを持たない** ときだけ区間を跨ぐ。判定は `callee_pure` (循環・間接 call・解決不能な先は不可)。書込みの判定は `insn_may_write_nonstack` (rsp 基底の格納・push・読取り専用命令以外を書込みありとする。文字列命令・rep・xchg 系も書込みあり)。
- 基底が揮発 (rax/rcx/rdx/r8〜r11) の `call` は、呼出しで値が変わるので `ptr_base_def` とする (跨がない)。
- **測定 commit: `c2541ca39` (現 HEAD の分類器・テストは `21265b1ed` 以降変わっていない)。** `git diff c2541ca39 HEAD -- tools/m11/m11_setother_ptr_class.py tools/m11/test_setother_ptr_class.py` は 0 行。下の内訳は、このコードで実行した実測値。
- 入力の再生成 (`work-m11` 素材 `$ARTIFACTS_DIR/work-m11.tar.zst` を `tools/m11/work/` に展開し、`fl-win64` の `extracted/block00031_PE.bin` を PE として使用。`work/sigfix_stats/` は gitignore 対象): `m11_post.py` → `m11_argrecover.py` → `m11_setother_ledger_verify.py` (`match 410`) → `m11_setother_nonimm_class.py` (非 imm 349・`load_ptr` 122)。入力 sha は `boot_final.ll` `69c774ded8aaf717`・PE `b2c64da40921cf26` (§2 と同一)。`m11_post.py` 出力 sha `c029ada4…` は §2 の記載と一致。
- 測定 (`python3 m11_setother_ptr_class.py work/sigfix_stats/nonimm_class_rows.json --pe <PE> --out work/sigfix_stats/ptr_class_rows.json`・real 0.29 秒・user 0.24 秒・load average 0.82 (1 プロセス単独)):

```
[ptr-class] 対象 122 件 (load_ptr・chain>load_ptr)
  実値化      0
  復元不能     0
  未決       122
  未分類   0
  未決       no_mem_operand         3
  未決       ptr_alias_write        3
  未決       ptr_base_def           85
  未決       ptr_call               10
  未決       ptr_unknown_write      3
  未決       slot_merge             18
```

- 前回 (`c988679dc`) からの差: `ptr_call` 17→10。`ptr_base_def` 82→85、`ptr_alias_write` 2→3、`ptr_unknown_write` 2→3、`slot_merge` 16→18 は、跨いだ先の後段判定の移動。実値化は 0 のまま。
- 残る `ptr_call` 10 件の呼出し先 (実測・`callee_pure` が偽): 呼出し先の本体に非スタック書込みがある (`mov qword ptr [rdx+r8*8], r9`・`movsd qword ptr [rbx+0x18], xmm0`・`movdqa xmmword ptr [rbp+0xc0], xmm9`・`movsd qword ptr [rbp+0x90], xmm2` など) 8 件、本体は直接書かないが呼出し先の先で書込みがある (推移) 2 件。間接 call の先は解決できないため、すべて未決のまま。
- 単体テスト: `test_setother_ptr_class.py` 現 HEAD (`c2541ca39`) で 13 件 OK (純粋な呼出し先を跨ぐ正例・書込みのある呼出し先の負例・揮発基底の負例・読取り専用接頭辞の負例を含む)。
- 受入条件: `ptr_call` 件数の 3 値実測は測定 commit `c2541ca39` で達成 (`ptr_call` 10 件は未決・未分類 0)。実値化 0 件のため `m11_argrecover_verify.py` の照合は該当なし。
- 未解決: 残る `ptr_call` 10 件は呼出し先の書込み範囲が非スタック領域に及ぶため、区間を跨げない (別名解析が要る)。起票先: #4890 (親)。
