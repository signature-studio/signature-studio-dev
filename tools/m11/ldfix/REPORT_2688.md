# LD-123 (#2688): spill 宛 判定不能 9 site の IR 側再検証 (F3d 適用 IR)

既知類型との関係 (docs/DEFECTS.md): 該当なし。上流の入口タグ読みの `xor i64 0,0` は REPORT_2660・REPORT_2438 §3 の新類型候補 (登録は PM 判断)。45d610 の型タグ `trunc i64 %arg1` (メモリ読みの欠落の疑い) は F3d の対象外で、別の新類型候補 (§4)。

## 1. 結論

- 9 site を機械語と IR の両面で照合した (§2)。
- **上流 xor 0 の 4 site (45d570・45d581・45b1bf・45f938) は、F3d 適用 IR で OK_LOAD の候補**。F3d (LD-127・#2745) で型タグ読みを `load i16` に戻すと、死んだ辺の条件式が機械語と同じ型タグ由来になり、辺を含めた CFG で TARGET は到達可能になる。store の値 (2 段 deref) と消費者 (ret の読み元) も機械語と一致した (§3)。
- ただし **F3d は既定で無効 (`--passes f3d` の opt-in)** で、本番 IR (`boot_final3.ll`) には入っていない。そのため本番 results の status (判定不能) は変えていない。既定化は #2833 (LD-134)、判定の配線と results の再生成は #2834 (LD-135) で行う。
- 残り 5 site (41ba8a・41bfd1・41e513・45c6dd・45d754) は UNDETERMINED のまま。根拠は §4。45d754 の型タグ `trunc i64 %arg1` は新類型候補。
- 判定の根拠は `tools/m11/ldfix/results/candidate_verdicts_2688.jsonl` (9 行・`candidate_verdicts_1161.jsonl` と同じ形式・`ir` 欄で F3d 適用 IR か本番 IR かを示す)。spill_classify_1161.py には配線していない。
- `audit_lsf_ssa_e2e.sh` は 18acdd38 で rc=0・7/7 (§5)。spill178_1161.tsv と drops_510.tsv は不変。

## 2. 9 site の判定

判定の欄は、本番 IR の判定と F3d 適用 IR の判定を分けて書く。

| 関数 | site | 機械語の消費者 | IR 側の対応 | 判定 (ir) |
|---|---|---|---|---|
| 45d0a0 | 45d570 | 45d574 jmp → 45d5ea (ret の読み元 [rbp+0x38]) | dec_label_pc_45d565 (F3d 適用で到達可能) | OK_LOAD (f3d) / UNDETERMINED (base) |
| 45d0a0 | 45d581 | 45d585 jmp → 45d5ea | dec_label_pc_45d576 (F3d 適用で到達可能) | OK_LOAD (f3d) / UNDETERMINED (base) |
| 45b170 | 45b1bf | 45b1cd で [rbp+0x38] を読み、movzx word | dec_label_pc_45b1b8 (F3d 適用で到達可能) | OK_LOAD (f3d) / UNDETERMINED (base) |
| 45f560 | 45f938 | 45f93c jmp → 45fa50 | dec_label_pc_45f931 (F3d 適用で到達可能) | OK_LOAD (f3d) / UNDETERMINED (base) |
| 41ba50 | 41ba8a | 41ba9d mov rbx,[rbp] → lock cmpxchg16b | 複写の第 1 語の元が xadd 旧値 (`[arg1+16]`)。機械語は `[r8]` | UNDETERMINED |
| 41bfa0 | 41bfd1 | 41bfd5 mov rax,[rbp+8] → ret | cmpxchg の失敗経路が IR に無い | UNDETERMINED |
| 41e490 | 41e513 | 41e542 mov rsi,[rbp] (ループ後の再読込) | 大域は同一 (0x400000 差)。大域の内容の基準が未確認 | UNDETERMINED |
| 45c290 | 45c6dd | 45c6e0 jmp → 45c8c8 | 型タグが alloca `%rcx` 経由で、機械語の `[arg1]` 読みと対応しない | UNDETERMINED |
| 45d610 | 45d754 | 45d82a mov rax,[rbp+0x38] → ret | 型タグが `trunc i64 %arg1` (メモリ読みの欠落の疑い) | UNDETERMINED (新類型候補) |

TRUE_DROP と NO_CONSUMER はどの site にも付かなかった。

## 3. 上流 xor 0 の 4 site: F3d 適用 IR での照合

F3d 適用 IR は `ldfix.py --passes f3d --only 45b170,45d0a0,45f560` で作る (3 関数の型タグ読みを `load i16` に置き換え、F3d=3)。

### 3.1 到達性 (`ir_reach_2660.py`・`f3d_9site_2688.sh` の出力 `ir_reach.txt`)

| TARGET (site) | 辺 (作者の前提) | 本番 IR (base) | F3d 適用 IR |
|---|---|---|---|
| dec_label_pc_45d565 (45d570) | 45d381→45d38e | 辺を含めて reachable / 辺を除くと UNREACHABLE | 辺を含めて reachable / 辺を除くと UNREACHABLE |
| dec_label_pc_45d576 (45d581) | 45d381→45d38e | 同上 | 同上 |
| dec_label_pc_45b1b8 (45b1bf) | 45b1a1→45b1b1 | 同上 | 同上 |
| dec_label_pc_45f931 (45f938) | 45f84c→45f931 | 同上 | 同上 |

- 本番 IR では辺が到達の唯一の経路で、辺の条件は上流の定数 `xor i64 0,0` から決まる (base の `%3`・`%1`・`%122` が定数)。
- F3d 適用 IR では、その条件式が型タグの load 由来 (`%3 = zext i16 %ldfxt2`、`%1 = zext i16 %ldfxt1`、`%118 = trunc(and(%3,49151))`) になり、機械語の分岐 (`test cx,0x4000`・`and ax,0xfff; cmp ax,0xc`・`cmp eax,6`) と同じ条件式になった (`targets_f3d.txt`)。
- 本 REPORT が示すのは「F3d 適用 IR では辺が定数で死なない」ことまで。辺が実行時に取られるかは型タグの実値に依る (ツールは定数畳み込みを検査しない)。機械語も同じ条件で分岐するため、経路の対応は取れている。

### 3.2 store の値と消費者の照合

| site | 機械語 (store・消費者) | F3d 適用 IR (store・消費者) | 判定 |
|---|---|---|---|
| 45d570 | 45d565 mov rax,[rbp+0x50]→[rax+8]→[rax] の 2 段 deref → 45d570 mov [rbp+0x38],rax → 45d5ea (ret) | 218-222: `[arg1+8]`→load→load (2 段)、store `%222`→stack_var_-16・rax.1.reg2mem→45d5ea `%rax.1.reload`→ret | OK_LOAD (f3d) |
| 45d581 | 45d576 同形 → 45d581 mov [rbp+0x38],rax → 45d5ea | 223-227: 同形 (`%227`)、同じ join | OK_LOAD (f3d) |
| 45b1bf | 45b1b8 mov rax,[rbx+8]→[rax] の 2 段 → 45b1bf mov [rbp+0x38],rax → 45b1cd movzx word[rax] | 45b1b1 `%11=arg2+8`、45b1b8 `%13=load [%12]` (=P)、join 45b1cd の `storemerge.in=load [P]` (=V)→`%15 load i16`。V の計算位置は機械語と異なるが値は同じ | OK_LOAD (f3d) |
| 45f938 | 45f931 mov rax,[rbx+8]→[rax] の 2 段 → 45f938 mov [rbp+0x28],rax → 45f93c jmp 45fa50 | 156-160: `%156=arg1+8`→load→load (2 段)、store `%160`→stack_var_-32・.reg2mem→45fa50 | OK_LOAD (f3d) |

`[rbp+N]` と `stack_var_-M` の対応は、F = push 数×8 + `sub rsp` の値として `M = F - N` で決まる (`candidate_verdicts_1161.jsonl` の cf3790 行と同じ規則)。45d0a0 は push 1 本・sub 0x40 で F=72、[rbp+0x38]↔stack_var_-16。

### 3.3 本番 IR に対する意味

- 本番 IR では、この 4 store は到達不能なブロックにあり、IR に値が届かない (`results/` の status は判定不能)。
- F3d が既定化されれば、4 site は脱落ではなく OK_LOAD に変わる見込み。これは F3d 適用 IR での照合で、既定化後の再生成 (#2834) で確かめる。

## 4. 残り 5 site の所見 (UNDETERMINED)

- **41ba8a (41ba50)**: 機械語は 41ba7a・41ba7c の movsq×2 で `[r8]` の 16 バイトを `[rbp+0x10]` へ複写し、41ba87 `mov rax,[r9]` (r9=[rbp+0x10]) の値を 41ba8a で `[rbp]` へ格納する。IR の複写の第 1 語は `%4=load [arg1+16]` (xadd の旧値) を stack_var_-56 へ置いた `%.pr` で、機械語の複写元 `[r8]` (xadd の対象 +0x10 とは別語) と一致しない疑い。REPORT_2660 §3 の所見を再確認しただけで、語の対応は未確定。TRUE_DROP の定義 (store が IR に無い) には当たらない。
- **41bfd1 (41bfa0)**: 機械語は 41bfc9 lock cmpxchg の失敗時に 41bfce の再読込値を格納し、41bfbd のループで再試行する。IR は cmpxchg を成功時の `store %8` だけに落とす。単一スレッドで失敗しないことの根拠は素材に無い。
- **41e513 (41e490)**: 大域 (機械語 0x15ec2e0・IR inttoptr 18793184 = 0x11ec2e0) は 0x400000 差で同一。大域の内容 (pointer 値) の基準 (VA か image 相対) が IR で一致するかは未確認。
- **45c6dd (45c290)**: 型タグは機械語 45c2a5 の `movzx rax,[arg1]` だが、IR では `%rcx` (alloca) への store と `%4=bitcast %rcx`→`load i16` を経由する。F3d の対象パターン (arg1 直読み) に当たらず、2 段 deref の対応も確定しない。
- **45d754 (45d610)**: 機械語 45d63d `mov rax,[rbp+0x60]` (=arg1)→45d641 `movzx eax, word[rax]` が型タグ。IR の型タグは `%0 = trunc i64 %arg1 to i16` で、`switch i16 %0` の全分岐がこれに依る。メモリ読み `word[arg1]` が IR に無く、関数全体の型タグ分岐が機械語と合わない疑い。F3d は 45d610 を対象にしない (新類型候補。DEFECTS.md 登録は PM 判断)。

## 5. 測定

- **測定 commit: `18acdd38`** (コードを変えた最後の commit: `tools/m11/ldfix/f3d_9site_2688.sh` と `results/candidate_verdicts_2688.jsonl` の追加)。
- 基点 `e9881327` (origin/main 取得時) の `audit_lsf_ssa_e2e.sh`: rc=0・7/7・123.5 s (実行直前の uptime load 0.92・nproc 4)。
- `18acdd38` の `audit_lsf_ssa_e2e.sh` (前景): rc=0・7/7 完走・121.8 s (load 未採取)。`spill178_1161.tsv`・`drops_510.tsv` は results/ と一致 (cmp 2 件)。
- 7/7 の主要値 (`18acdd38`): 1/7 lsf 90・解決不能 370・169 関数 / 5/7 DROP 関数の和集合 69 (drops_510) / 7/7 spill 宛 unk 178 site・71 関数、status 確定 139・判定不能 30・未判定 9、spill 宛確定 TRUE_DROP 関数 26 (drops_510 に無いもの 8 関数)。
- `f3d_9site_2688.sh` (`18acdd38`・OUT は別ディレクトリ): rc=0・11.8 s。`ir_reach.txt` は 2 回の実行で一致 (`cmp`)。
- ネガティブコントロール: 本番 IR で辺を除くと 4 TARGET とも UNREACHABLE (`ir_reach.txt` の各 2 行目)。辺が本番での唯一の経路であることの確認。F3d 適用 IR で辺を除かない行は reachable (辺を含めても到達可能)。
- コード差分: `git diff e9881327 18acdd38 -- tools/m11/ldfix/results tools/m11/ldfix/*.py` は jsonl の 9 行 (`results/candidate_verdicts_2688.jsonl`) のみで、audit の経路 (`*.py`・spill178・drops) は 0 行。`f3d_9site_2688.sh` は audit の経路に入らない。

## 6. 再現手順

1. 素材: `work-m11`・`work-liftdiff` を展開 (`tools/m11/work/`・`tools/liftdiff/work/`)。`fl-win64` の `extracted/block00031_PE.bin` を `$RUNNER_TEMP/fl-win64/extracted/` に置く。
2. `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (7/7 が results/ と一致)。
3. `bash tools/m11/ldfix/f3d_9site_2688.sh` (`OUT` 既定 `$RUNNER_TEMP/f3d_9site_2688`。`ssa.json` は script が作る)。出力: `ir_reach.txt` (到達性)・`targets_f3d.txt` (対象ブロックの抜粋)・`base/` と `f3d/` (site ダンプ)。
4. 判定の根拠は `results/candidate_verdicts_2688.jsonl` を見る。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| F3d の既定化と本番 IR の再生成 (60 関数の IR 変更の build・e2e) | 本番 IR に 4 site の修復が入らない | #2833 (LD-134) |
| 4 site の判定を `spill_classify_1161.py` に配線し、spill178・drops を再生成 (`candidate_verdicts_2688.jsonl` の `ir=f3d` 行) | results/ の status は判定不能のまま | #2834 (LD-135) |
| 45d610 の型タグ `trunc i64 %arg1` (メモリ読みの欠落の疑い・F3d の対象外・新類型候補) | 関数 45d610 の型タグ分岐全体 (45d754 を含む) | PM 判断 (DEFECTS.md 登録と修復の起票)。本 run では起票しない |
| 41ba8a の複写元 (`[r8]` と IR の xadd 旧値) の語の対応 | 1 site の判定 | PM 判断 (親 #2660 の後続として起票するか) |
| 41bfd1 (cmpxchg 失敗経路)・41e513 (大域内容の基準)・45c6dd (型タグの alloca 経由) | 3 site の判定 | PM 判断 (親 #2660 の後続として起票するか) |

## 8. 注記

- 本 PR は起動・GUI に関わらないため、製品 KPI は書かない。launch (`infra/pm-worker/`) にも触れない。
- 既定経路は変えていない (F3d は opt-in のまま。`ldfix.py` と results/ は不変)。
- 本 run の素材は `$HOME/artifacts` の `work-m11`・`work-liftdiff`・`fl-win64` (展開先は §6)。
