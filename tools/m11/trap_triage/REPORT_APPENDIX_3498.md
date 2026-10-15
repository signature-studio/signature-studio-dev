# REPORT_APPENDIX_3498 — #3498 の証拠表 行 4〜35 の件ごとの判定 (REPORT_718 §4h の正本)

> **正本**: 本付録。`tools/m11/trap_triage/REPORT_718.md` §4h は要約と参照のみ (250 行上限のため分割移動)。

## 4h. 証拠表の行 4〜35 (#3498・母数 32 件: 真陽性 27・偽陽性 0・保留 5)

- 母数: `strict_evidence.tsv` のデータ行 4〜35 (ヘッダ除く 1 始まり) の 32 件。
- 判定: **真陽性 27・偽陽性 0・保留 5** (保留は行 4・10・24・27・29)。保留の 5 件は子 issue に移す (§未解決)。
- 測定 commit: `1d04852b0` (作業ブランチの基点)。判定に使ったコードは本 PR で変えていない。
  `git diff 1d04852b0 HEAD -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_entry_check.py tools/m11/trap_triage/judge_ctx.py tools/m11/trap_triage/judge_dump.py` の出力は 0 行。
- 入力: `boot_final.ll` (19,787,837 B・sha256 `69c774de…`。`tools/m11/work/` の既存の展開物で、本 run で sha256 を再計算して一致を確認) と `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B。`$RUNNER_TEMP` に展開)。
- 再生成した証拠表: strict 288 件 (`scan_guard.py --report`・`strict_evidence.py`)。`judge_entry_check.py <IR> strict_evidence.tsv 4 35` は 32 行を出した。`judge_ctx.py 4 35` で行 4〜35 の文脈 (機械語・B・L・T・preds) を出し、L の icmp は `judge_dump.py 4 35` の出力で全件を確認した。
- 実測 (本 fix run・foreground・1 回ずつ): `scan_guard.py --report` 3.4 s・rc 0。`strict_evidence.py` 7.5 s・rc 0・TSV 288 行。`judge_entry_check.py 4 35` rc 0・32 行。`judge_ctx.py 4 35` rc 0・2,190 行 (96,627 B)。`judge_dump.py 4 35` rc 0・160 行。load average (1 分値) は終了時 0.06 (`/proc/loadavg`)。

### 判定規則 (件ごと。0978196e8 版の文言をそのまま使う。(a)〜(c) を真陽性の必要条件として明記する)

1. 機械語: jcc 直前の cmp の被演算子 (a) と条件コードを取る (`judge_dump.py` の MACH)。
2. 機械的な前提 (`judge_entry_check.py`): jcc ブロックの終端が無条件 `br` で loop head に入るか、脱出先ラベルの preds が何か。
3. 対応の確認: (a) に対応する alloca / SSA 値 (b) を IR で遡って結び、入口 (loop head に入る経路) に (b) の判定 (icmp) が無いこと (c) を示す。
4. 真陽性 = (c) が成り立ち、かつ入口から脱出先への直接の経路が IR に無い。偽陽性 = (b) と同じ値の同等判定が IR 側にある。保留 = (a)(b)(c) のどれかを REPORT に書けない。
  - 真陽性は (a)(b)(c) を REPORT に書けた行だけに付ける。

### 本 run での補足

- 差し戻し対応 (fix): 行 4・27・29 を真陽性から保留へ、行 18 を保留から真陽性へ変えた。行 17 は真陽性のまま、(b) と (c) を書き直した。行 17・18 の (b) は、機械語の store/load と IR の store/load の対応で確認した (下の注 2)。
- 「入口の (b) の判定」の数え方: ループ本体へ入るか脱出するかを、B→L の初回に決める判定 (test-first) を数える。(b) を引数に取る関数の戻り値の判定 (`function_fe8bb0`・`function_100bb30` の境界判定) も数える (下の注 4)。ループ本体の後で次回の要否を決める末尾判定 (do-while の末尾) は、初回の本体実行を止めないので数えない。
- 右辺 (境界) の同一性は (a)(b)(c) の要件に含めない (規則は左辺 (b) と入口の判定の有無で決まる)。右辺の段数・アドレスの食い違いは注 1・注 3 に書く。
- 判定は subagent 4 本 (行 4〜11・12〜19・20〜27・28〜35) の一次判定を、私が ctx で再確認して決めた。
- 注意: 真陽性は構造の判定。境界の値 (count ≤ 0) が実行時に到達するかは測っていない。`docs/DEFECTS.md` の類型への対応は PM 判断。

### 件ごとの判定

| 行 | 関数 | jcc → 脱出先 | 判定 | (a) 機械語の被演算子・条件 | (b) IR の対応値 | (c) 入口 (B→L) の同値判定 | 注 |
|---|---|---|---|---|---|---|---|
| 4 | function_100bb90 | 100bcf4 → 100bd4d | **保留** | ecx=0 (xor)。`cmp ecx, r14d`・jg | B: `store i32 0 → stack_var_-44.0`。L 先頭で reload し、`(stack_var_-44.0 * 65536) or %57` を `function_100bb30` に渡す | L の `%61 = icmp eq %60, 0` は (b) を含む引数で呼んだ `function_100bb30` の戻り値の判定。100bb30 は引数の上位 16 bit (= (b)) を件数と比べ、範囲外で 0 を返す (入口の (b) の境界判定)。機械語の右辺 r14d との同一性は未確認 | 注 4 |
| 5 | function_1017ca0 | 1017d39 → 1017df9 | 真陽性 | ebx=0 (xor→mov)。`cmp ebx, r13d`・jg | B: `store i64 0 → rbx.0` → L の添字 | B・L に添字との icmp 無し | |
| 6 | function_1018db0 | 1018e1a → 1018e68 | 真陽性 | eax=0 (ecx→eax)。`cmp eax, edx`・jg | B: `store i64 0 → rax.1` → L の添字 | B に icmp 無し。L の icmp は添字と無関係 | |
| 7 | function_1042d20 | 1042fe8 → 10431af | 真陽性 | ecx=0 (→[rbp+0x5c])。`cmp ecx, esi`・jg | B: `store i32 0 → stack_var_-204.0` → L の第 2 引数 | B に icmp 無し | 機械語 1042ffd の reload と対応 |
| 8 | function_1042d20 | 10431cf → 1043ef7 | 真陽性 | edx=0 (eax→edx)。`cmp edx, ecx`・jg | B: `store i32 0 → stack_var_-204.1` | B に icmp 無し。L の icmp は、`%257 = icmp slt stack_var_-224.0, 1` (−224.0 は B で 0 を store する別 slot で、(b) の −204.1 ではない)、`%255`・`%278`・`%337`・`%374` (`%254`・`%277`・`%336`・`%373` は `function_fe8bb0(…, −204.1)` の戻り値 `%251` を基点にした要素の byte。戻り値は null 判定されない)。(b) 自体との比較は無い | |
| 9 | function_1045410 | 104555b → 1045713 | 真陽性 | ecx=0 (→[rbp+0x44])。`cmp ecx, r14d`・jg | B: `store i32 0 → stack_var_-84.1` | B に (b) の判定無し (B の icmp `%61`・`%64`・`%66` は `%17` 系)。L の icmp は `%81 = icmp eq %80, 0` (`%80` は arg1 経由の番地の byte)・`%82`・`%or.cond10.not`・`%or.cond11` (i1 フラグどうし)。(b) の −84.1 は `function_fe8bb0` の引数になり、その戻り値由来の `%76` は icmp に入らない | |
| 10 | function_1046a30 | 104c70a → 104c744 | **保留** | [rbp+0x580]=0 (eax を store)。`cmp`・jg (0 > count−1) | B に 0 の store が無い。L は下向きの計数のみ (icmp 2 本) | — | (b) を特定できない。子 issue |
| 11 | function_1050f90 | 1050fc7 → 105103e | 真陽性 | r13d=0 (xor)。`cmp r13d, eax`・jg | B: `store i64 0 → r13.0` → L の mid 計算 | B に icmp 無し。L の `%24 = icmp ugt %22, arg1` の被演算子 `%22` は、添字 mid=(r13.0 + rax.0)/2 で読んだ要素の値。(b) の r13.0 は mid の添字としてのみ現れ、比較の被演算子ではない | call 0x4232e0 を挟む。callee-saved (SysV) を前提 |
| 12 | function_1050f90 | 10510cf → 105112e | 真陽性 | r13d=0。`cmp r13d, eax`・jg (右辺 [G+0x10]−1) | B: `store i64 0 → r13.2` → L の lo | B に icmp 無し。L の `icmp ugt %82, %arg1` は読んだ値との比較 | 注 1 |
| 13 | function_1060950 | 1060973 → 10609d8 | 真陽性 | r13d=0。`cmp r13d, r14d`・jg (r14d=[rbx+0x14]−1) | B: `store i64 0 → r13.0` | B の icmp `%6` は arg2 と arg3 の比較 (別値)。L に icmp 無し (L の br は `%6` を使う) | 右辺は latch の `%24` と対応する見込みだが未確定 |
| 14 | function_10609f0 | 1060a06 → 1060a25 | 真陽性 | esi=0 (eax→esi)。`cmp esi, edi`・jg (edi=[rbx+0x14]−1) | B: `store i64 0 → rsi.0` → L の添字 | L の icmp `%14` は本体後の計数判定 (`rdi−1 == 0`) | |
| 15 | function_1060d20 | 1060d3d → 1060d65 | 真陽性 | esi=0。`cmp esi, edi`・jg (edi=[rbx+0x14]−1) | B: `store i64 0 → rsi.0` | L の icmp は本体後 (subagent) | |
| 16 | function_10624d0 | 10624f1 → 106262a | 真陽性 | ebx=0。`cmp ebx, edi`・jg (edi=[rcx+0x14]−1) | B: `store i64 0 → rbx.0` | L の icmp は添字と無関係 (subagent) | T は rax.1 を読むが B は初期化しない |
| 17 | function_10c7cd0 | 10c8d17 → 10c8d6b | 真陽性 | [rbp+0x780]=0 (`mov [rbp+0x780], eax`・eax=0)。`cmp [rbp+0x780], esi`・jg (右 esi=[rbp+0x774]−1) | B: `store i32 0 → stack_var_-17800.1`。機械語の本体 10c8d55 `add [rbp+0x780], 1` ↔ IR L の `%127 = add -17800.1.reload, 1` と `store %127 → -17800.1` | B に icmp 無し。L の icmp は本体の後の末尾判定 `%exitcond184 = icmp eq %127, 64` (固定 64 回。count N は使わない)。L に呼び出しは無い | 注 2 |
| 18 | function_10c7cd0 | 10c8dc4 → 10c8e18 | 真陽性 | [rbp+0x780]=0 (`mov [rbp+0x780], eax`・eax=0 (10c8dad))。`cmp [rbp+0x780], ebx`・jg (右 ebx=[rbp+0x76c]−1) | B: `store i32 0 → stack_var_-17800.2`。機械語 10c8e02 `add [rbp+0x780], 1` ↔ IR L の `%146 = add -17800.2.reload, 1` と `store %146 → -17800.2` | B に icmp 無し。L の icmp は本体の後の末尾の count-down 判定 `%153 = icmp eq %152, 0` (`%150` = rbx.2 − 1)。(b) の判定は無い。B の前の判定 (preds の `icmp ult %106, 64`・`icmp eq %119, 0`) は count 側で (b) ではない | 注 2 |
| 19 | function_1185da0 | 1185dfe → 1185e7d | 真陽性 | ebx=0。`cmp ebx, r13d`・jg (右 r13d=[G2+0x10]−1) | B: `store i64 0 → rbx.0` | B に icmp 無し。L の icmp はバイト判定 | 注 1 |
| 20 | function_1185e90 | 1185eea → 1185fd6 | 真陽性 | ecx=0 (xor)。`cmp ecx, r14d`・jg (r14d=n−1) | B: `store i32 0 → stack_var_-44.0` → L の添字 (第 2 引数) | L の icmp `%40` はフィールド値どうしの比較 (本 run で確認) | 注 3 |
| 21 | function_11862e0 | 1186323 → 11863bd | 真陽性 | esi=0 (eax→esi)。`jg` | B: `store i64 0 → rsi.0` → L の添字 | B に icmp 無し。L の icmp は添字と無関係 (subagent) | |
| 22 | function_1189310 | 11893a0 → 11893dc | 真陽性 | ebx=0 (ecx→ebx)。`jg` | B: `store i64 0 → rbx.0` → L の添字 | L の icmp は本体後の末尾判定 (subagent) | |
| 23 | function_1192da0 | 1192dc9 → 1192e08 | 真陽性 | ebx=0 (eax→ebx)。`jg` | B: `store i64 0 → rbx.0` → L | B に icmp 無し。L の `%19 = icmp eq %18, 0` の被演算子 `%18` は、添字 rbx.0 で読んだ要素 (`%15`) のフィールド。(b) 自体との比較ではなく、範囲判定でもない (`function_fe8bb0` を経由しない) | |
| 24 | function_11c9930 | 11c99af → 11c9a17 | **保留** | ebx=0 (eax→ebx)。機械語の L 本体で ebx を添字に使う | B は添字 0 を store しない (n を rdi.0 に入れるだけ)。L は rdi の計数のみで添字の SSA が無い | 形式上は無し | (b) を結べない。子 issue |
| 25 | function_11e6e20 | 11e6e60 → 11e6ef5 | 真陽性 | ebx=0 (ecx→ebx)。`jg` | B: `store i64 0 → rbx.0` → L の添字 | B に icmp 無し。L の `%34 = icmp ugt %23, %33` の被演算子は、添字 b と b+1 の要素から読んだフィールドの和 (`%23`・`%33`)。(b) 自体の比較は無い | |
| 26 | function_11e7860 | 11e788b → 11e7907 | 真陽性 | esi=0 (eax→esi)。`jg` | B: `store i64 0 → rsi.0` → L の添字 | L の icmp は末尾の計数判定 (subagent) | |
| 27 | function_11e7fa0 | 11e7fbd → 11e802b | **保留** | ebx=0 (eax→ebx)。`cmp ebx, esi`・jg (右 esi=[[G]+0x10]−1、2 段 deref) | B: `store i64 0 → rbx.0` → L の添字 | 入口に (b) の境界判定がある。L の `%8 = icmp eq %7, 0` は `function_fe8bb0(%6, rbx.0)` の戻り値の判定で、fe8bb0 は (b) が `[arg1+16]−1` を超える・負のとき 0 を返す。IR の境界は 1 段 deref (`load i32 [G']`) の件数で、機械語の 2 段 deref と同じ境界かは未確認 | 注 4 |
| 28 | function_11e8280 | 11e82b1 → 11e82ec | 真陽性 | r13d=0 (eax→r13d)。`jg` (右辺 [[G]+0x10]−1) | B: `store i64 0 → r13.0` → L の添字 | L の icmp `%11 = eq i8 %10, 0` はバイト判定 (本 run で確認) | 注 1・注 3 |
| 29 | function_11e84a0 | 11e8505 → 11e8541 | **保留** | esi=0 (eax→esi)。`jg` (右辺 [[G]+0x10]−1) | B: `store i64 0 → rsi.0` → L の添字 | 入口に (b) の判定がある。L の `%24 = icmp eq i64 %rsi.0.reload, %9` (`%9 = zext i32 %arg1`) が `%29` を経て L の br を決める (本体に入るか脱出するかの test-first)。%9 が機械語の右辺 (`[[G]+0x10]−1`) と同じ値かは未確認 | 注 1・注 3・注 4 |
| 30 | function_1221840 | 122193e → 122196f | 真陽性 | ebx=0 (eax→ebx)。`jg` (右辺 [rcx+0x14]−1) | B: `store i64 0 → rbx.0` → L の添字 | L の icmp `slt %48, %49` は添字と無関係 (subagent) | |
| 31 | function_1221840 | 122199b → 1221a3f | 真陽性 | ebx=0。`jg` (右辺 [rcx+0x14]−1) | B: `store i64 0 → rbx.1` → L の添字 | L の icmp `%77` はポインタどうしの比較 (subagent) | |
| 32 | function_1221bc0 | 122251f → 122272f | 真陽性 | ecx=0 (eax から spill)。`jg` (右辺 r13d=[rsi+0x14]−1) | B: `store i32 0 → stack_var_-108.2` → L の添字 | B の icmp は arg3 のフラグ判定 (無関係)。L の icmp は本体判定 (subagent) | |
| 33 | function_1223020 | 12230df → 122330f | 真陽性 | ecx=0 (spill)。`jg` (右辺 r13d=[rcx+0x14]−1) | B: `store i32 0 → stack_var_-68.0` → L の添字 | L の icmp `ult %46, stack_var_-60.0` は添字と無関係 (subagent) | |
| 34 | function_1251590 | 1251621 → 12516a2 | 真陽性 | eax=0 (r10d=0)。`jg` (右辺 edi=ebx−1) | B: `store i64 0 → rax.1` → L の要素番地の添字 | L の icmp `%40 = eq %39, %.reload` は要素値と鍵の比較 (本 run で確認) | 右辺 ebx の供給元は未確認 |
| 35 | function_1251590 | 1251728 → 12517db | 真陽性 | ebx=0 (eax→ebx)。`jg` (右辺 esi=[X]−1) | B: `store i64 0 → rbx.1` → L の添字 | B に icmp 無し。P の icmp は別オブジェクトの件数 | 注 1・注 3 |

### 注

1. **右辺の段数・アドレスの食い違い** (行 12・19・28・29・35): 機械語は rip 相対グローバルを 2 段 deref し、IR は 1 段 (`load G`) で読んでいる。境界値の同一性は未確認。左辺 (b) と入口判定の有無で決めた真陽性であり、境界の食い違いは別件の欠陥の疑い (未検証)。
2. **行 17・18 の (b)**: 両行とも機械語の計数器が `[rbp+0x780]` で、同じ対応 (`-17800.1`・`-17800.2` は同じ stack 変数 `-17800` の別名)。0 の store は機械語 (行 17 は 10c8d0b、行 18 は 10c8db8) と IR の B が一致し、本体の +1 は機械語 (10c8d55・10c8e02) と IR の L (`%127`・`%146`) が一致し、L の末尾で同じ slot に store し直す。両行の入口 (B→L) に (b) の判定は無い。count 側は、行 17 が `[rbp+0x774]−1` (N−1)、行 18 が `[rbp+0x76c]−1` (機械語の内側ループ count は `[rbp+0x76c]`)。行 17 の IR の終了判定は固定 64 回 (`icmp eq %127, 64`) で、N は使わない。count 0 のとき機械語は本体を 0 回実行し、IR は 64 回 (行 17) または wrap した count-down 分 (行 18) を実行する。その実行到達性は未検証 (真陽性は構造の判定)。
3. **IR の定数アドレス** (行 20・28・29・35): 機械語の rip 相対先と IR の定数アドレスが 0x400000 ずれて見える (subagent の観察・未検証)。判定には使っていない。
4. **入口の (b) の境界判定を経由する保留** (行 4・27): 入口 (B→L) の test-first 判定が、(b) を引数にとる境界判定付きの関数 (`function_100bb30`・`function_fe8bb0`) の戻り値を見る。機械語の右辺と同じ境界かを確かめられず、偽陽性か真陽性かを決められないため保留にした。行 29 も、入口の `rsi.0 == %9` の同値判定を同じ理由で保留にした (`%9` と機械語の右辺の同一性は未確認)。

## 未解決 (起票先)

- 保留 5 件 (行 4・10・24・27・29): (b) の特定、または入口の判定が機械語の右辺と同じ値かの確認が要る。行 10 は B に 0 の store が無く、L が下向き計数だけなので、機械語の配列アクセスの対応を探す。行 24 は L の添字 SSA の出所を探す。行 4・27・29 は IR の境界・同値判定の対象 (`function_100bb30`・`function_fe8bb0` の件数、`%9`) と機械語の右辺の段数を揃えて確かめる。起票先: #3854 (`[M11-N195]`・親 #3498)。行 18 は本 PR で (b) を確定して真陽性にしたため #3854 の対象から外れる。行 4・27・29 は #3854 の本文に無いので、同 issue へのコメントで追加する。
- 真陽性 27 件の境界値の実行到達性 (count ≤ 0 が実行時に起きるか): 未検証。
- 注 1・注 3 の境界アドレス・段数の食い違い: 別件として要確認 (判定に使っていない)。
