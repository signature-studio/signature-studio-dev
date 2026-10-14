# LD-119 (#2660): spill 宛 判定不能 9 site の IR 側再検証 (#1161 残)

## 1. 結論

- 9 site のうち **4 site を TRUE_DROP に確定** (45d570・45d581・45b1bf・45f938)。根拠は機械語の消費者と、IR の保存ブロックが entry から到達不能であること (`ir_reach_2660.py`)。
- 残る **5 site は UNDETERMINED のまま** (41ba8a・41bfd1・41e513・45c6dd・45d754)。新しい所見を §3 に残し、子 issue LD-123 (#2688) に移した。
- 脱落関数の和集合は **未確定**。暫定値は 75 関数 (§4)。最終化は子 issue LD-124 (#2689・他 4 issue と LD-123 の完了後)。
- 監査 7/7 は測定 commit `3e9a7419` で rc=0・149.87 s。`spill178_1161.tsv` と `drops_510.tsv` は results/ と一致 (§5)。

## 2. 9 site の判定

機械語は `site_dump.py` の降下 (`descend`)、IR は `boot_final3.ll` の関数本体。到達性は `ir_reach_2660.py` で、定数畳み込みで死んだ辺を除いた CFG から判定した。除外前は到達可能であることも確認した (sanity)。

| 関数 | site | 機械語の消費者 | IR 側の対応 | 判定 |
|---|---|---|---|---|
| 45d0a0 | 45d570 | 45d574 jmp → 45d5ea `mov rax,[rbp+0x38]` → ret (間に call 無し) | `dec_label_pc_45d565` は entry 到達不能。死んだ辺 `45d381→45d38e` (`%3` = xor 0 由来の `%122`/`%123` が定数) | **TRUE_DROP** |
| 45d0a0 | 45d581 | 45d585 jmp → 45d5ea (同上) | `dec_label_pc_45d576` は entry 到達不能 (同じ死んだ辺) | **TRUE_DROP** |
| 45b170 | 45b1bf | 45b1c3 jmp → 45b1cd `mov rax,[rbp+0x38]` (間に call 無し) | `dec_label_pc_45b1b8` は entry 到達不能。死んだ辺 `45b1a1→45b1b1` (`%8` 定数真) | **TRUE_DROP** |
| 45f560 | 45f938 | 45f93c jmp → 45fa50 `mov rax,[rbp+0x28]` | `dec_label_pc_45f931` は entry 到達不能。死んだ辺 `45f84c→45f931` (`%122` 定数偽) | **TRUE_DROP** |
| 41ba50 | 41ba8a | 41ba9d `mov rbx,[rbp]` → 41baa1 `lock cmpxchg16b` の新値 | 「対応する store」が無い。値 `%15` は `%.pr` (= `%4` = `load [arg1+16]` の xadd 旧値) を指す。機械語 41ba7a の movsq は `[arg1]` を複写 | UNDETERMINED |
| 41bfa0 | 41bfd1 | 41bfd5 `mov rax,[rbp+8]` → ret | crit-edge の `%8` (成功時の書込値) と一致。cmpxchg 失敗経路 (41bfce 再読込・41bfbd ループ) は IR に無い | UNDETERMINED |
| 41e490 | 41e513 | 41e542 `mov rsi,[rbp]` (ループ後の再読込) | `%16 = load (%15 = r15)` と構造一致。大域は機械語 0x15ec2e0 と IR `inttoptr 18793184` (0x11ec2e0) で 0x400000 差 (同一大域) | UNDETERMINED |
| 45c290 | 45c6dd | 45c6e0 jmp → 45c8c8 `mov eax,[rbp+0x3c]` → ret | tag の読み元が `load i16 %4` (`%4 = bitcast %rcx`) で、機械語の `[arg1]` 読みと一致しない | UNDETERMINED |
| 45d610 | 45d754 | 45d82a `mov rax,[rbp+0x38]` → ret | tag が `%0 = trunc i64 %arg1 to i16` で、機械語は `word[arg1]` をメモリ読みする | UNDETERMINED |

## 3. UNDETERMINED 5 site の所見 (LD-123 へ)

- **41ba8a (41ba50)**: IR 61〜64 行の `%4 = load [arg1+16]` (xadd の対象) を `stack_var_-56` (= `[rbp+0x10]`) へ格納している。機械語 41ba7a の `movsq` は `[r8]` (= arg1) を `[rbp+0x10]` へ複写する。第 1 語の複写元が不一致で、IR の `%15` (`%.pr` 経由の間接参照) は機械語と別の値。「脱落」ではなく「誤った元の値」なので TRUE_DROP の定義に当てはまらない。
- **41bfd1 (41bfa0)**: IR は `lock cmpxchg` を成功時の `store %8` だけに落とす。機械語 41bfc9 の失敗時は 41bfce の再読込値を格納し、41bfbd のループで再試行する。単一スレッドで cmpxchg が失敗しないことの根拠は素材に無い。
- **41e513 (41e490)**: 大域の基準 (機械語 VA と IR の 0x400000 差) は一致するが、大域の内容である pointer 値の基準 (VA か image 相対) が IR で一致するかは未確認。
- **45c6dd (45c290)**: IR の tag 読みは `%4 = bitcast ptr %rcx` (alloca) からの `load i16`。機械語は `[arg1]` を読む。分岐条件の対応を確定できない。
- **45d754 (45d610)**: IR の tag は `trunc i64 %arg1 to i16` (引数値そのもの) で、機械語のメモリ読み (`word[arg1]`) と一致しない。経路条件の対応を確定できない。

## 4. 脱落関数の和集合 (暫定・未確定)

- 今回の変更で spill 宛 TRUE_DROP 関数は 21 → 24 (新規 3: 45b170・45d0a0・45f560)。
- 和集合 = store 宛 DROP 51 ∪ spill 宛 frame 22 (drops_510.tsv) ∪ spill 宛 TRUE_DROP 24 = **75 関数** (旧暫定 72 相当)。
- 未確定の要素: UNDETERMINED 5 site (LD-123)・未判定 65 site (#2245・#2288・#2583 の対象)・#2253 の判定不能 7 site。最終化は LD-121。

## 5. 監査 (測定 commit `3e9a7419`)

- コマンド: `M11_WORK=<main>/tools/m11/work LD_WORK=<main>/tools/liftdiff/work bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (worktree `ws-2660`)。
- 結果: rc=0・149.87 s・load 0.01 (開始時)。7/7 完走。`[drops_510.tsv] results/ と一致`、`[spill178_1161.tsv] results/ と一致`。
- 集計 (step 7): 確定 101 / 判定不能 12 / 未判定 65 (前 97 / 16 / 65)。
- ベースライン (main 73f8b502・判定変更前): rc=0・148.96 s・同じく 7/7 一致。

## 6. 再現手順

1. `python3 tools/m11/ldfix/site_dump.py <IR> <image.bin> '<cfg glob>' <ssa.json> <OUT> 45d0a0,45b170,45f560` (ssa.json は `audit_lsf_ssa.py --json`)
2. `python3 tools/m11/ldfix/ir_reach_2660.py <OUT>/45d0a0.txt dec_label_pc_45d565 dec_label_pc_45d381:dec_label_pc_45d38e` → `UNREACHABLE` (除外無しは `reachable`)
3. 同様に `dec_label_pc_45d576` (45d581)、`dec_label_pc_45b1b8` (45b1bf・辺 `dec_label_pc_45b1a1:dec_label_pc_45b1b1`)、`dec_label_pc_45f931` (45f938・辺 `dec_label_pc_45f84c:dec_label_pc_45f931`)。

## 7. コード差分

- 測定 commit `3e9a7419` 以降のコード差分 (`git diff 3e9a7419 HEAD -- tools/m11/ldfix/results tools/m11/ldfix/*.py`) は、本 REPORT と DOC_MAP の追記のみで 0 行。

## 8. 注記

- 前回値の参照先 `REPORT_1161.md` は PR #2661 (未 merge) にあり、本 run は main 基点の TSV/JSONL から値を取り直した。
- 実施順の注記 (#2245・#2288・#2583・#2253) について: 本 issue の 9 site は、いずれの対象 site・関数とも重ならないことを確認した。
