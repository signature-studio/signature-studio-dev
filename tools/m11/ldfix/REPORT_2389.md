# REPORT #2389 — cf3790 の判定 3 件 (cf3c7a・cf3cbb・cf3d20) の reg2mem 結線確認 (LD-110)

親: #2312 (LD-105) / #2287 (LD-103) / #1161 (LD-35)。**結論: 3 site とも TRUE_DROP を確定 (類推 → 結線による確定。判定は覆らない)**。
副産物: #2312 で作った突合表 `ld105_reg2mem_map.tsv` の slot 名 `stack_var_-(disp+8)` は **frame 位置の仮定が誤り**で、cf3790 では `stack_var_-(472-disp)` が正しい。表を直して再生成した (§4)。

既知類型との関係: REPORT_510 §2/§7 の「D17 案」(rip 相対ポインタセルの 2 段 deref が 1 段に潰れる) の spill 宛。`docs/DEFECTS.md` の D17 行は qstore の 4B store で別物 (番号が衝突している。REPORT_510 §7 の行案は未反映で、DEFECTS.md の編集は PM 判断)。新規類型なし。

## 1. 結線の取り方

1. frame: `function_cf3790` のプロローグは `push×4` (32 B) + `sub rsp, 0x1b8` (440 B) + `mov rbp, rsp`。F = 472。`[rbp+disp]` ↔ `stack_var_-(F-disp)`。
2. 検証 (`ld110_reg2mem_link.py`): プロローグの `mov qword ptr [rbp+d], 0` 8 本が、IR 入口の `store .. 0|null, ptr %stack_var_-(F-d)` と **8/8** 対応 (旧式 `-(d+8)` は **2/8**)。関数全体の即値 store 16 本では新式 **12/16** (不一致 4 本は `[rbp+0x191]`・`[rbp+0x193]` の byte flag で、IR では SSA 化され store が無い) / 旧式 **2/16**。
3. site ごとに機械語の `mov rA,[rip+X]` → `mov rD,[rA]` → `mov [rbp+d],rD` を取り、IR 側で cell K = X − 0x400000 を読む `load` (%Q) を同じ基本ブロックから探して deref 段数 (機械語 2 / IR 1) を比べる。%Q の消費者連鎖 (`icmp eq %Q,0` / `add %Q,-8` → `load`) が `%stack_var_-(F-d).*.reg2mem` へ store され、reload が機械語の後続 READ と同じ使われ方をするかを見る。

## 2. 結線表 (`results/ld110_reg2mem_link.tsv`、判定根拠の行は `results/candidate_verdicts_1161.jsonl` に site ごと)

| site | 機械語 slot | IR slot | 機械語の連鎖 | IR の %Q (boot_final3.ll) | reg2mem の store → reload → 使用 | 判定 |
|---|---|---|---|---|---|---|
| cf3c7a | `[rbp+0x140]` | `stack_var_-152` | cf3c70 `[rip+0x8ec499]` → cf3c77 `[rax]` → cf3c7a store | 401984 `%128 = load i64, ptr inttoptr (18743568)` (cell 0x11e0110 自身) | 401986 `0` / 401993 `%132` (= `load (%128-8)`) → 401997 → 401999 `icmp sgt` (機械語 cf3ca4 `cmp rax,[rbp+0x140]`) | TRUE_DROP |
| cf3cbb | `[rbp+0xd8]` | `stack_var_-256` | cf3cb1 `[rip+0x8eca40]` → cf3cb8 `[rax]` → cf3cbb store | 402003 `%135 = load i64, ptr inttoptr (18745080)` (cell 0x11e06f8 自身) | 402005 `0` / 402012 `%139` → 402016 → 402018 `call @function_43a820(.., %stack_var_-256.0.reload, ..)` (機械語 cf3ce2 `mov rdx,[rbp+0xd8]`) | TRUE_DROP |
| cf3d20 | `[rbp+0xd0]` | `stack_var_-264` | cf3d16 `[rip+0x8ec9db]` → cf3d1d `[rax]` → cf3d20 store | 402025 `%145 = load i64, ptr inttoptr (18745080)` (cell 0x11e06f8 自身) | 402027 `0` / 402035 `%phitmp` (= trunc `load (%145-8)`) → 402039 → 402048 `store .. %stack_var_-404.0.reg2mem` (機械語 cf3d45–cf3d50 `[rbp+0xd0]` → `[rbp+0x44]`) | TRUE_DROP |

- 機械語は cell を読んで (1 段) さらに `[rax]` で変数を読む (2 段)。IR の %Q は cell を 1 段読むだけで、2 段目の load が無い。%Q は変数のアドレス値 (image の cell 内容 0x153f8c0 / 0x153fab8) になり、`icmp eq %Q,0` と `add %Q,-8` が変数でなくアドレス値に掛かる。
- 機械語が slot に最初に書く値 (cf3c7a ほかの store 自体) は SSA 化されて IR に store として残らない。slot に残るのは、2 回目の書込み (Length) の reg2mem 化したもの (`0` / `load(%Q-8)` の phi) だけで、これが上の結線に当たる。
- 既判定 cf387f / cf38be / cf390f と同じ型。cf3c7a の %128 は cf3875 側のループ本体 (401734 `%25 = add %128,-8` → `stack_var_-160`、cf387f の slot) とも共有される。
- `spill178_1161.tsv` の oracle 列が 3 site とも `CELL_DEEP` なのは、spill 宛 (`frame=true`) の site では alg3 が `FRAME` (判定対象外。`ssa.json` の 3 site で確認) になり、幅 64 の cell 読みが `cell_check` の `alg3 == 'SHALLOW'` を満たさず CELL_COLLAPSED に入らないため。IR に 2 段の連鎖がある、の意味ではない (本 run の結線では IR 段数 1)。幅 64 の spill 宛 site の `CELL_DEEP` は、他の site でも判定の根拠にならない。

## 3. 測定

- 測定 commit (コードを変えた最後の commit): `d0a7f2db`。それ以降は REPORT_2389.md と DOC_MAP の追加だけ (`git diff d0a7f2db HEAD -- tools/m11/ldfix` は REPORT 追加前の HEAD で出力 0 行)。
- `ld110_reg2mem_link.py` (1 コマンド再現: `M11_WORK=<work-m11> python3 tools/m11/ldfix/ld110_reg2mem_link.py`): 3 回とも rc=0・real 0.32〜0.35 s・load average 0.56・出力 TSV は `results/ld110_reg2mem_link.tsv` と cmp 一致。`ld105_reg2mem_map.py` の再生成も `results/ld105_reg2mem_map.tsv` と cmp 一致。
- `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (`M11_WORK`・`LD_WORK` は main の work を指定): rc=0・real 1m50.035s・開始時 load average 0.11・7/7 完了。status 未判定 **117** / 確定 **54** / 判定不能 **7** (REPORT_2287 の測定と同一。判定は TRUE_DROP のまま、根拠文の書換えだけ)。`drops_510.tsv`・`spill178_1161.tsv` は results/ と cmp 一致。
- ネガティブコントロール (`ld110_reg2mem_link.py` 内):

| NC | 内容 | 結果 |
|---|---|---|
| NC1 | 旧式 `-(d+8)` で同じ照合をする | プロローグ 2/8・関数全体 2/16 (新式は 8/8・12/16) で FAIL を検出。cf3c7a は slot `-328` を指し、これは `[rbp+0x90]` (cf3fe1) の slot で store 値 `%219 = load [%217]` は 2 段。この取り違えが「cf3c7a の 2 段 deref の同一性が未確認」の原因 |
| NC2 | %Q の load を cell → 変数の 2 段 load に直した IR (メモリ上の写し) | 3 site とも IR 段数 1 → 2 で OK_LOAD に動く (3/3) |
| NC3 | site a の %Q 連鎖の store 先に、site b の slot が入るか | 3 組とも a 自身の slot にだけ入り、b の slot には入らない (取り違えを区別) |

## 4. ld105 突合表の修正 (#2388 への影響)

- `ld105_reg2mem_map.py` は slot 名を `frame_size()` (プロローグから求めた F) で作るようにし、`results/ld105_reg2mem_map.tsv` を再生成した。15 行すべての `slot` 列と、それに連動する `alloca`・`ir_stores`・`ir_reload_use`・`ir_store_value_def` が変わる (例: cf3b62 `-264` → `-216`、cf3fe1 `-152` → `-328`)。
- 旧 TSV の slot 名で #2388 (LD-109) の 15 site を判定すると、別 site の slot を読むことになる。#2388 は再生成後の表を使う。

## 5. 範囲外・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残り 15 site (cf3b03〜cf3fe1) の IR 消費者追跡と判定。本 run で表の slot 名は修正済み | cf3790 の spill 宛が未確定のまま | #2388 (LD-109) |
| 検証範囲は cf3790 の 3 site の静的結線のみ。wasm 実行での値の確認 (liftdiff の動的差分) はしていない | 静的判定のため、実行時の値は未確認 | 起票しない (REPORT_510 §3.1 のとおり動的差分は被覆と感度が足りない) |
| `docs/DEFECTS.md` の D17 行 (qstore) と REPORT_510 §7 の「D17 案」(cell 2 段 deref 潰れ) の番号衝突 | 参照時に取り違える | PM 判断 (DEFECTS.md の編集は PM) |
