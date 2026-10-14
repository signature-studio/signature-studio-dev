# LD-119 (#2660): spill 宛 判定不能 9 site の IR 側再検証 (#1161 残)

## 1. 結論

- 9 site を機械語・IR の両面で再検証した。**9 site すべて UNDETERMINED (判定不能) のまま**で、判定は変えない。
- 4 site (45d570・45d581・45b1bf・45f938) は、機械語の消費者 (store 直後の load・間に call 無し) を確認できた。一方、IR の保存ブロックが entry から到達不能なのは、上流の `xor i64 0,0` (機械語 45b18b・45d0b5・45f56c の型タグ読みの置換) が作る死んだ辺による。上流が直ると辺は生き、store は IR で実行される。独立した脱落ではないため、TRUE_DROP への確定は取り下げた (§2)。
- 残る 5 site (41ba8a・41bfd1・41e513・45c6dd・45d754) も UNDETERMINED。所見は §3 に残し、子 issue LD-123 (#2688) に移した。
- 脱落関数の和集合は **72 関数** (main と同じ・`REPORT_2265.md` §3 の公表値)。9 site が未確定のため最終化は未了。最終化は子 issue LD-124 (#2689)。
- 測定: 測定 commit `abca9e53` (results を main の状態へ戻した commit)。全 7 step の `audit_lsf_ssa_e2e.sh` は素材不足で未実行。実行できたのは step 7 だけで、commit 済みの `results/audit_510_ssa.json` から分類表を再生成し `results/` と一致した (§5)。

## 2. 9 site の判定

機械語は `site_dump.py` の降下 (`descend`)、IR は `boot_final3.ll` の関数本体。到達性は `ir_reach_2660.py` で、定数畳み込みで死ぬと作者が判断した辺を除いた CFG から判定した。除外前は到達可能であることも確認した (sanity)。ツールは辺が本当に定数で死ぬかは検査しない。辺は作者の前提である。

| 関数 | site | 機械語の消費者 | IR 側の対応 | 判定 |
|---|---|---|---|---|
| 45d0a0 | 45d570 | 45d574 jmp → 45d5ea `mov rax,[rbp+0x38]` → ret (間に call 無し) | `dec_label_pc_45d565` は entry 到達不能。死んだ辺 `45d381→45d38e` (`%3` = 上流 45d0b5 の `xor i64 0,0` 由来の `%122`/`%123` が定数) | UNDETERMINED (上流 xor 0 の修復待ち) |
| 45d0a0 | 45d581 | 45d585 jmp → 45d5ea (同上) | `dec_label_pc_45d576` は entry 到達不能 (同じ死んだ辺・同じ上流) | UNDETERMINED (上流 xor 0 の修復待ち) |
| 45b170 | 45b1bf | 45b1c3 jmp → 45b1cd `mov rax,[rbp+0x38]` (間に call 無し) | `dec_label_pc_45b1b8` は entry 到達不能。死んだ辺 `45b1a1→45b1b1` (`%8` 定数真。上流 45b18b の `xor i64 0,0` 由来) | UNDETERMINED (上流 xor 0 の修復待ち) |
| 45f560 | 45f938 | 45f93c jmp → 45fa50 `mov rax,[rbp+0x28]` | `dec_label_pc_45f931` は entry 到達不能。死んだ辺 `45f84c→45f931` (`%122` 定数偽。上流 45f56c の `xor i64 0,0` 由来) | UNDETERMINED (上流 xor 0 の修復待ち) |
| 41ba50 | 41ba8a | 41ba9d `mov rbx,[rbp]` → 41baa1 `lock cmpxchg16b` の新値 | 「対応する store」が無い。値 `%15` は `%.pr` (= `%4` = `load [arg1+16]` の xadd 旧値) を指す。機械語 41ba7a の movsq は `[arg1]` を複写 | UNDETERMINED |
| 41bfa0 | 41bfd1 | 41bfd5 `mov rax,[rbp+8]` → ret | crit-edge の `%8` (成功時の書込値) と一致。cmpxchg 失敗経路 (41bfce 再読込・41bfbd ループ) は IR に無い | UNDETERMINED |
| 41e490 | 41e513 | 41e542 `mov rsi,[rbp]` (ループ後の再読込) | `%16 = load (%15 = r15)` と構造一致。大域は機械語 0x15ec2e0 と IR `inttoptr 18793184` (0x11ec2e0) で 0x400000 差 (同一大域) | UNDETERMINED |
| 45c290 | 45c6dd | 45c6e0 jmp → 45c8c8 `mov eax,[rbp+0x3c]` → ret | tag の読み元が `load i16 %4` (`%4 = bitcast %rcx`) で、機械語の `[arg1]` 読みと一致しない | UNDETERMINED |
| 45d610 | 45d754 | 45d82a `mov rax,[rbp+0x38]` → ret | tag が `%0 = trunc i64 %arg1 to i16` で、機械語は `word[arg1]` をメモリ読みする | UNDETERMINED |

### 2.1 4 site を TRUE_DROP にしなかった理由

- 4 site の store 元ブロックを entry から到達不能にしている死んだ辺は、上流の型タグ読みの置換 (`xor i64 0,0`) が作る。上流の置換が直れば、その辺は生き、store は IR で実行される。したがって「store が IR で実行されない」ことは上流の欠陥の結果であり、spill 宛の独立した脱落ではない。
- `REPORT_2265.md` §4 の基準 (「確認できない site は判定を外す」。xor 0 による定数置換の候補 12f9730 を未判定へ戻した扱い) と揃える。main の `candidate_verdicts_1161.jsonl` の 4 行も UNDETERMINED (上流の脱落が直るまで実行条件を確定できない) である。
- 前回 (`3e9a7419`) の TRUE_DROP 判定は、このレビューで取り下げた。`ir_reach_2660.py` の結果 (死んだ辺を除くと到達不能) は、上流修復後の再判定で使う検査として残す。

## 3. UNDETERMINED 9 site の所見 (LD-123 へ)

- **上流 xor 0 の修復待ち 4 site (45d570・45d581・45b1bf・45f938)**: 上流の置換 (45b18b・45d0b5・45f56c) を直した後に、死んだ辺が生きるかを確認する。生きたら store の IR 実行と機械語の消費者の対応を照合し、TRUE_DROP / OK_LOAD を判定する。直らなければ判定不能のまま残る。
- **41ba8a (41ba50)**: IR 61〜64 行の `%4 = load [arg1+16]` (xadd の対象) を `stack_var_-56` (= `[rbp+0x10]`) へ格納している。機械語 41ba7a の `movsq` は `[r8]` (= arg1) を `[rbp+0x10]` へ複写する。第 1 語の複写元が不一致で、IR の `%15` (`%.pr` 経由の間接参照) は機械語と別の値。「脱落」ではなく「誤った元の値」なので TRUE_DROP の定義に当てはまらない。
- **41bfd1 (41bfa0)**: IR は `lock cmpxchg` を成功時の `store %8` だけに落とす。機械語 41bfc9 の失敗時は 41bfce の再読込値を格納し、41bfbd のループで再試行する。単一スレッドで cmpxchg が失敗しないことの根拠は素材に無い。
- **41e513 (41e490)**: 大域の基準 (機械語 VA と IR の 0x400000 差) は一致するが、大域の内容である pointer 値の基準 (VA か image 相対) が IR で一致するかは未確認。
- **45c6dd (45c290)**: IR の tag 読みは `%4 = bitcast ptr %rcx` (alloca) からの `load i16`。機械語は `[arg1]` を読む。分岐条件の対応を確定できない。
- **45d754 (45d610)**: IR の tag は `trunc i64 %arg1 to i16` (引数値そのもの) で、機械語のメモリ読み (`word[arg1]`) と一致しない。経路条件の対応を確定できない。

## 4. 脱落関数の和集合 (暫定・未確定)

- 和集合 = store 宛 DROP 51 ∪ spill 宛 frame 22 (drops_510.tsv) = 69 関数に、spill 宛の確定 TRUE_DROP の増分 3 (4120c0・41a5d0・6c3700) を加えた **72 関数** (`spill_classify_1161.py` の [5][6] 行)。
- 本 PR で spill 宛 TRUE_DROP 関数は 21 のまま (旧 `3e9a7419` の 24 は取り下げた)。和集合は main と同じ 72。
- 未確定の要素: UNDETERMINED 9 site (LD-123 #2688・上流 xor 0 の修復待ち 4 を含む)・未判定 65 site (#2245・#2288・#2583 の対象)・#2253 の判定不能 7 site。最終化は LD-124 (#2689)。

## 5. 監査と測定

- 測定 commit: **`abca9e53`** (results を main の状態へ戻した commit)。以降のコード差分は §7。
- 全 7 step の `audit_lsf_ssa_e2e.sh` は **未実行**。`$ARTIFACTS_DIR` には `fl-win64` しか無く、`work-m11` (`boot_final3.ll`・`m11_image.bin`・`boot*.drc.config.json`) と `work-liftdiff` (`batch_closure.jsonl`) が無いため、step 1〜4 と step 6 は入力が無い。step 5 (`tally_510.py`) も batch の `batch_closure.jsonl` を必須引数に取るため実行できない。
- 実行したのは step 7 のみ。コマンドは `python3 tools/m11/ldfix/spill_classify_1161.py tools/m11/ldfix/results/audit_510_ssa.json <TMP>/spill178_1161.tsv` で、`cmp` の結果は `results/spill178_1161.tsv` と一致 (rc=0・0.03 s・Python 3.14.8)。集計は 確定 97 / 判定不能 16 / 未判定 65、TRUE_DROP 関数 21、和集合 72 (= 69 + 3)。
- 旧測定 (`3e9a7419`・rc=0・149.87 s・7/7) は TRUE_DROP 状態のもので、results を戻したため現 HEAD には当てはまらない。
- 残課題: 全 7 step の再実行 (`bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh`) は、素材 `work-m11` と `work-liftdiff` を展開できる run で前景実行し、7/7 と results/ の一致を確認する。PR 本文の `oc_artifacts:` 行はこの素材を指定する。

## 6. 再現手順

1. `python3 tools/m11/ldfix/site_dump.py <IR> <image.bin> '<cfg glob>' <ssa.json> <OUT> 45d0a0,45b170,45f560` (ssa.json は `audit_lsf_ssa.py --json`。commit 済みの `results/audit_510_ssa.json` も使える)
2. `python3 tools/m11/ldfix/ir_reach_2660.py <OUT>/45d0a0.txt dec_label_pc_45d565 dec_label_pc_45d381:dec_label_pc_45d38e` → `UNREACHABLE` (除外無しは `reachable`)
3. 同様に `dec_label_pc_45d576` (45d581)、`dec_label_pc_45b1b8` (45b1bf・辺 `dec_label_pc_45b1a1:dec_label_pc_45b1b1`)、`dec_label_pc_45f931` (45f938・辺 `dec_label_pc_45f84c:dec_label_pc_45f931`)。
4. 分類表の再生成: `python3 tools/m11/ldfix/spill_classify_1161.py tools/m11/ldfix/results/audit_510_ssa.json <OUT>/spill178_1161.tsv` → `cmp` で `results/spill178_1161.tsv` と一致。

## 7. コード差分

- 測定 commit `abca9e53` 以降のコード差分 (`git diff abca9e53 HEAD -- tools/m11/ldfix/results tools/m11/ldfix/*.py`) は、この REPORT と DOC_MAP の追記のみで 0 行。
- `results/` は main と同一 (`git diff origin/main HEAD -- tools/m11/ldfix/results` は 0 行)。

## 8. 注記

- 前回値の参照先 `REPORT_1161.md` は PR #2661 (未 merge) にあり、本 run は main 基点の TSV/JSONL から値を取り直した。
- 実施順の注記 (#2245・#2288・#2583・#2253) について: 本 issue の 9 site は、いずれの対象 site・関数とも重ならないことを確認した。
