# LD-119 (#2660): spill 宛 判定不能 9 site の IR 側再検証 (#1161 残)

既知類型との関係 (docs/DEFECTS.md): 該当なし。D1a〜D23 のどれにも未登録。新類型候補は `REPORT_2438.md` §3 の「入口の memory 読みの `xor i64 0, 0`」に当たる。登録は PM 判断。

## 1. 結論

- 9 site を機械語・IR の両面で再検証した。**9 site すべて UNDETERMINED (判定不能) のまま**で、判定は変えない。
- 4 site (45d570・45d581・45b1bf・45f938) は、機械語の消費者 (store 直後の load・間に call 無し) を確認できた。一方、IR の保存ブロックが entry から到達不能なのは、上流の `xor i64 0,0` (機械語 45b18b・45d0b5・45f56c の型タグ読みの置換) が作る死んだ辺による。上流が直ると辺は生き、store は IR で実行される。独立した脱落ではないため、TRUE_DROP への確定は取り下げた (§2)。上流修復の追跡は LD-127 (#2745) (§2.2)。
- LD-127 (#2745): 上流 xor 0 の 3 関数の入口タグ読みを load に戻す pass F3d を追加した (既定無効・`--passes f3d`)。4 site の判定と `results/` は未更新 (§2.3)。F3d の既定化は #2833、4 site の判定更新は #2834 (§2.4)。
- 残る 5 site (41ba8a・41bfd1・41e513・45c6dd・45d754) も UNDETERMINED。所見は §3 に残し、子 issue LD-123 (#2688) に移した。
- 脱落関数の和集合は **72 関数** (69 + TRUE_DROP 増分 3・PR 基点 `62b33c07` の results での計算。`REPORT_2265.md` §3 の公表値と同じ)。9 site が未確定のため最終化は未了。最終化は子 issue LD-124 (#2689)。現 main (`738074af`) の results は本 PR と版が違い、その和集合は未測定 (§7)。
- 測定: 測定 commit `57d6612b` (F3d を入れたコード commit)。`audit_lsf_ssa_e2e.sh` を前景実行し rc=0・7/7 完走 (120.9 s)。HEAD `4e85ea56` でも再実行し rc=0・7/7 完走 (165.1 s)。主要値は §5。旧測定 (`8a323067`・154.7〜154.8 s) は §5 に旧版の注記付きで残す。

## 2. 9 site の判定

機械語は `site_dump.py` の降下 (`descend`)、IR は `boot_final3.ll` の関数本体。到達性は `ir_reach_2660.py` で、定数畳み込みで死ぬと作者が判断した辺を除いた CFG から判定した。除外前は到達可能であることも確認した (sanity)。ツールは辺が本当に定数で死ぬかは検査しない。辺は作者の前提である。

| 関数 | site | 機械語の消費者 | IR 側の対応 | 判定 |
|---|---|---|---|---|
| 45d0a0 | 45d570 | 45d574 jmp → 45d5ea `mov rax,[rbp+0x38]` → ret (間に call 無し) | `dec_label_pc_45d565` は entry 到達不能 (死んだ辺 `45d381→45d38e`。`%3` = 上流 45d0b5 の `xor i64 0,0` 由来の `%122`/`%123` が定数) | UNDETERMINED (上流 xor 0 の修復待ち) |
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

### 2.2 上流 xor 0 の置換箇所 (追跡: LD-127 #2745)

| 関数 | 機械語 (置換前の型タグ読み) | boot_final3.ll の置換行 |
|---|---|---|
| 45b170 | 45b18b `movzx rsi, word ptr [rbx]` | 161459 `%1 = xor i64 0, 0` |
| 45d0a0 | 45d0b5 `movzx rax, word ptr [rax]` (rax = `[rbp+0x50]`) | 164220 `%3 = xor i64 0, 0` |
| 45f560 | 45f56c `movzx rax, word ptr [rbx]` | 167844 `%3 = xor i64 0, 0` |

- 3 関数の同じ xor 行は `boot0.lift.ll` (RetDec lift 段の出力) に既にあり、置換は lift 段で入る。`%4 = trunc i64 %3 to i16` が型タグ分岐の条件になる。
- 修復 (型タグ読みを定数にせず load として残す) と 4 site の判定確定は LD-127 (#2745) で行う。本 PR の範囲は追跡の紐付けまで。

### 2.3 上流 xor 0 の修復 (LD-127 #2745・F3d)

- 機械語 (実 PE `block00031_PE.bin`・capstone 降下): 45b170 は 45b184 `mov rbx, rdx` → 45b18b `movzx rsi, word ptr [rbx]` (arg2)。45d0a0 は 45d0ac `mov [rbp+0x50], rcx` → 45d0b1 `mov rax, [rbp+0x50]` → 45d0b5 `movzx rax, word ptr [rax]` (arg1)。45f560 は 45f569 `mov rbx, rcx` → 45f56c `movzx rax, word ptr [rbx]` (arg1)。3 関数とも入口ブロックの 16 bit 型タグ読み。
- lift 段の行: `boot0.lift.ll` の 58554 (45b170 の `%1`)・61313 (45d0a0 の `%3`)・64937 (45f560 の `%3`) に既に `xor i64 0, 0` がある。`boot_final3.ll` の行 (161459・164220・167844) は、ここから merge・asmfix・passes を経た後の位置である。m11 の生成コードに `xor i64 0, 0` を出力する箇所は無い (grep)。RetDec 内部のどの pass が定数化したかは未特定 (§2.4)。
- 既存 F3b が取りこぼした理由: F3b は zero-disp の `mov` load だけを数え (`movzx` を除外)、入口の `xor` が 1 本であることも求める (45d0a0・45f560 は入口に 3 本)。`ldfix.py --passes f3b --only 45b170,45d0a0,45f560` は 3 関数とも件数 0。
- 修復 `fix_f3d` (`ldfix.py`・`--passes f3d` で有効・既定無効): 入口ブロックの機械語に movzx word の zero-disp load が 1 本 (rsp/rbp 基底を除く)・基底が argN に解決・入口の `xor i64 0,0` のうち結果が `trunc i64 %x to i16` か `and i64 %x, <imm>` で使われるものがちょうど 1 本、の全てを満たすときだけ、`xor` 行を `load i16` + `zext` に置き換える。
- 修復の結果 (`--passes f3d --only 45b170,45d0a0,45f560`・3 関数): 161459 は arg2 の `load i16`、164220・167844 は arg1 の `load i16` になった (3 関数の xor 行を、load と zext を含む 2〜3 行に置き換えた差分のみ)。
- 修復前後の到達性 (`ir_reach_2660.py`・site_dump の IR):

| 関数 | TARGET (site) | 修復前 (`boot_final3.ll`) | 修復後 (F3d 適用 IR) |
|---|---|---|---|
| 45d0a0 | dec_label_pc_45d565 (45d570) | 辺を除かない CFG で reachable。死んだ辺 `45d381→45d38e` を除くと UNREACHABLE。その辺は `%123` の偽側で、`%3` = 0 のとき `%123` は常に真 | 辺を除かない CFG で reachable。`%3` は `zext i16 (load)`。同じ辺の条件は load 由来 |
| 45d0a0 | dec_label_pc_45d576 (45d581) | 同上 (同じ辺) | 同上 |
| 45b170 | dec_label_pc_45b1b8 (45b1bf) | 辺を除かない CFG で reachable。死んだ辺 `45b1a1→45b1b1` を除くと UNREACHABLE。その辺は `%8` の偽側で、`%1` = 0 のとき `%8` は常に真 | 辺を除かない CFG で reachable。`%1` は `zext i16 (load)`。同じ辺の条件は load 由来 |
| 45f560 | dec_label_pc_45f931 (45f938) | 辺を除かない CFG で reachable。死んだ辺 `45f84c→45f931` を除くと UNREACHABLE。その辺は `%122` の真側で、`%3` = 0 のとき `%122` は常に偽 | 辺を除かない CFG で reachable。`%3` は `zext i16 (load)`。同じ辺の条件は load 由来 |

- 読み方: 「辺を除かない CFG で reachable」は修復前でも成り立つ (CFG だけを見る検査)。修復で変わったのは、死んだ辺の条件式の入力が定数 0 (上流の `xor`) から load 由来の値になった点である。`ir_reach_2660.py` で辺を除くと、修復後も UNREACHABLE になる (実測)。これは「その辺が死んでいれば届かない」ことを示すだけで、辺が生きることの証明ではない。辺が実際に生きるかは load の値に依存し、本 REPORT の範囲外。
- 影響範囲 (F3d 単独・`boot_final3.ll` の全 7421 関数): 60 関数に当たる (3 関数は本節の対象、残り 57 関数は同じ類型か未検証)。F3d は既定無効のまま。既定化には 60 関数の IR 変更の build・e2e 検証が要る (#2833)。ガードの内訳と negative control は §2.5。
- 既定経路の回帰: `62b33c07` の `ldfix.py` と修復後 `ldfix.py` の既定出力 (`boot_final3.ll` 入力) は `cmp` で一致 (F3d 既定無効のため)。再現は §6 の 6。
- 4 site の判定 (`candidate_verdicts_1161.jsonl`・`spill178_1161.tsv`) は更新していない。`results/` は本番 IR (F3d 未適用) から生成されるため、F3d を既定化して IR を再生成するまで判定の根拠が無い。これは子 issue (#2834) に移した。
- 測定の版: 測定 commit は **`57d6612b`** (F3d を入れたコード commit)。`audit_lsf_ssa_e2e.sh` を前景で実行: rc=0・7/7 完走・120.9 s。`drops_510.tsv` と `spill178_1161.tsv` は `results/` と一致。spill 宛の分布は 確定 109・判定不能 28・未判定 41 (§5)。
- コード差分: `git diff 57d6612b HEAD -- tools/m11/ldfix/results tools/m11/ldfix/*.py` は 0 行 (HEAD `4e85ea56` 時点・本節の REPORT 更新と `f3d_negctl_2745.sh` の追加は含まれない。`.sh` は audit の経路に入らない)。

### 2.4 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| F3d の既定化 (60 関数の IR 変更の build・e2e 検証) | 既定の pipeline は未修復。4 site は UNDETERMINED のまま | #2833 (LD-134) |
| 4 site の判定と `candidate_verdicts_1161.jsonl`・`spill178_1161.tsv` の更新 | `results/` は本番 IR (F3d 未適用) 基準のまま | #2834 (LD-135) |
| RetDec 内部で xor 0 化した pass の特定 (m11 の出力には `xor i64 0,0` を出す箇所は無い) | 上流 (lift 段) を直すか否かの判断に必要。F3d で IR 側に対処済み | #2745 へのコメント (本 PR の merge で close されるため、追跡はそのコメントに残す。新規子 issue は立てない) |
| main 側 results の再測定 (現 main `738074af` は 確定 117・判定不能 30・未判定 31) | 本 PR の results は基点 `62b33c07` の版 (109/28/41)。main の和集合は未測定 | LD-124 (#2689) |

### 2.5 F3d ガードのネガティブコントロール (`f3d_negctl_2745.sh`)

ガードを 1 つずつ外した複製 `ldfix.py` で `boot_final3.ll` 全関数に `--passes f3d` を掛けた (既定との比較)。`f3d_negctl_2745.sh` の出力 (実測):

| 設定 | f3d_fns (既定 60) | base 未解決 | 曖昧 | 既存 load | 既定比の追加・削除関数 | 出力 (既定比) |
|---|---|---|---|---|---|---|
| 既定 (ガードあり) | 60 | 3 | 21 | 0 | — | — |
| unres: base 未解決で arg1 に決め打ち | 60 | 3 | 24 (+3) | 0 | 0・0 | 0 行 |
| load: 既存 load の検査を外す | 60 | 3 | 21 | 0 | 0・0 | 0 行 |
| amb: 入口 xor の一意性を外す (候補 2 本以上は先頭を採用) | 60 | 3 | 21 | 0 | 0・0 | 0 行 |

- 曖昧 21 件の内訳 (`f3d_ambiguous_n<候補数>`): 候補 0 本が 21 件、候補 2 本以上は 0 件 (`dist` モード)。
- unres で外すと 3 関数は後段の候補チェックで落ち (曖昧 21→24)、base 未解決ガードはこの入力では冗長。
- load と amb は、この入力では判定に効いていない (既存 load 0 件・候補 2 本以上 0 件)。**この入力ではどのガードを外しても出力は変わらない。** ガードが効く入力 (FAIL を出す入力) は未測定で、F3d の既定化前に合成入力で確認する (#2833 の範囲)。

## 3. UNDETERMINED 9 site の所見 (LD-123 へ)

- **上流 xor 0 の修復待ち 4 site (45d570・45d581・45b1bf・45f938)**: 上流の置換 (45b18b・45d0b5・45f56c、§2.2) を直した後に、死んだ辺が生きるかを確認する。生きたら store の IR 実行と機械語の消費者の対応を照合し、TRUE_DROP / OK_LOAD を判定する。直らなければ判定不能のまま残る。
- **41ba8a (41ba50)**: IR 61〜64 行の `%4 = load [arg1+16]` (xadd の対象) を `stack_var_-56` (= `[rbp+0x10]`) へ格納している。機械語 41ba7a の `movsq` は `[r8]` (= arg1) を `[rbp+0x10]` へ複写する。第 1 語の複写元が不一致で、IR の `%15` (`%.pr` 経由の間接参照) は機械語と別の値。「脱落」ではなく「誤った元の値」なので TRUE_DROP の定義に当てはまらない。
- **41bfd1 (41bfa0)**: IR は `lock cmpxchg` を成功時の `store %8` だけに落とす。機械語 41bfc9 の失敗時は 41bfce の再読込値を格納し、41bfbd のループで再試行する。単一スレッドで cmpxchg が失敗しないことの根拠は素材に無い。
- **41e513 (41e490)**: 大域の基準 (機械語 VA と IR の 0x400000 差) は一致するが、大域の内容である pointer 値の基準 (VA か image 相対) が IR で一致するかは未確認。
- **45c6dd (45c290)**: IR の tag 読みは `%4 = bitcast ptr %rcx` (alloca) からの `load i16`。機械語は `[arg1]` を読む。分岐条件の対応を確定できない。
- **45d754 (45d610)**: IR の tag は `trunc i64 %arg1 to i16` (引数値そのもの) で、機械語のメモリ読み (`word[arg1]`) と一致しない。経路条件の対応を確定できない。

## 4. 脱落関数の和集合 (暫定・未確定)

- 和集合 = store 宛 DROP 51 ∪ spill 宛 frame 22 (drops_510.tsv) = 69 関数に、spill 宛の確定 TRUE_DROP の増分 3 (4120c0・41a5d0・6c3700) を加えた **72 関数** (`spill_classify_1161.py` の [5][6] 行)。
- 本 PR で spill 宛 TRUE_DROP 関数は 21 のまま (旧 `3e9a7419` の 24 は取り下げた)。和集合は本 PR の results の版で 72。
- 未確定の要素: UNDETERMINED 9 site (LD-123 #2688・上流 xor 0 の修復待ち 4 を含む)・未判定 41 site (#2245・#2288・#2583 の対象)・#2253 の判定不能 7 site。最終化は LD-124 (#2689)。

## 5. 監査と測定

- **現行 (測定 commit `57d6612b`・HEAD `4e85ea56` で再実行)**: `audit_lsf_ssa_e2e.sh` を素材 `work-m11`・`work-liftdiff` (main 側の展開先を `M11_WORK`・`LD_WORK` で指定) で前景実行。HEAD: rc=0・7/7 完走・165.1 s (loadavg 0.28 → 0.96・nproc 4)。`57d6612b` 時点の実行は 120.9 s。両 commit の `results/` は同一 (`git diff 57d6612b HEAD -- tools/m11/ldfix/results` は 0 行)。

| step | 主要値 (HEAD `4e85ea56`) |
|---|---|
| 1/7 `audit_lsf.py` | lsf 90 site / 解決不能 370 site / 169 関数 |
| 2/7 `audit_lsf_ssa.py` | alg1 26・alg2 38・alg3 77 関数 (alg1 ∪ alg2 = 41 関数)。step 1 の 90 / 370 / 169 と一致 |
| 3/7 `window_recount.py` | window_pairs 420・window_not_in_dataflow 0 |
| 4/7 `dyn_xcheck.py` | 既知 TRUE_DROP 8 関数: match 2・mismatch 3・unexec 3。解決不能 169 関数: match 25・mismatch 52・unexec 92 |
| 5/7 `tally_510.py` | store 宛 192 site の最終判定: DROP 89 site / 51 関数 (目視 37・自動 52)、UNDETERMINED 2 site。`drops_510.tsv` は results と一致 |
| 6/7 `negctl_510.sh` | NC0〜NC7 完走 |
| 7/7 `spill_classify_1161.py` | 確定 109 / 判定不能 28 / 未判定 41。TRUE_DROP 関数 21 (drops_510 に無いもの 4120c0・41a5d0・6c3700)。和集合 72 (= 69 + 3)。`spill178_1161.tsv` は results と一致 |

- 判定不能 28 のうち 16 site が本 issue (#2660) の 9 site と #2253 (LD-95) の 7 site (c3460e・dcdeee・1284dab・128cad6・128d007・128d495・12900c4) で、いずれも HEAD の results で UNDETERMINED (§8)。
- **旧測定 (測定 commit `8a323067`・154.7〜154.8 s・2 回)**: step 1〜6 の値は現行と同じ。step 7 は 確定 97 / 判定不能 16 / 未判定 65 で、これは PR 作成時の旧基点 `858ceef0` の `results/spill178_1161.tsv` の版による値 (`8a323067` は `858ceef0` と同じ results を持つ)。TRUE_DROP 関数 21・和集合 72 は同じ。現行の測定ではない。
- 旧測定 (`3e9a7419`・rc=0・149.87 s・7/7) は TRUE_DROP 状態のもので、results を戻したため現行には当てはまらない。
- 残課題: 上流 xor 0 の修復 (F3d 既定化・4 site の判定更新) は #2833・#2834。上流 pass の特定は #2745 へのコメント (§2.4)。

## 6. 再現手順

1. `python3 tools/m11/ldfix/site_dump.py <IR> <image.bin> '<cfg glob>' <ssa.json> <OUT> 45d0a0,45b170,45f560` (ssa.json は `audit_lsf_ssa.py --json`。commit 済みの `results/audit_510_ssa.json` も使える)
2. `python3 tools/m11/ldfix/ir_reach_2660.py <OUT>/45d0a0.txt dec_label_pc_45d565 dec_label_pc_45d381:dec_label_pc_45d38e` → `UNREACHABLE` (辺を除かない場合は reachable)
3. 同様に `dec_label_pc_45d576` (45d581)、`dec_label_pc_45b1b8` (45b1bf・辺 `dec_label_pc_45b1a1:dec_label_pc_45b1b1`)、`dec_label_pc_45f931` (45f938・辺 `dec_label_pc_45f84c:dec_label_pc_45f931`)。修復後 IR (`--passes f3d` の出力) に同じ 3 を掛ける。
4. 分類表の再生成: `python3 tools/m11/ldfix/spill_classify_1161.py tools/m11/ldfix/results/audit_510_ssa.json <OUT>/spill178_1161.tsv` → `cmp` で `results/spill178_1161.tsv` と一致。
5. F3d の件数 (m1): `python3 tools/m11/ldfix/ldfix.py tools/m11/work/boot_final3.ll <out.ll> --pe <FL_WIN64_DIR>/extracted/block00031_PE.bin --passes f3d --report <out.json>` → `F3d(type-tag)=60`・`f3d_fns`=60・`f3d_base_unresolved`=3・`f3d_ambiguous`=21 (`--passes` を付けない既定では F3d は走らない)。`tools/m11/work/` は gitignore の素材 (`M11_WORK` で指定可)。
6. 既定経路の cmp (m1): `D=$RUNNER_TEMP/ldfix_cmp; mkdir -p $D/ldfix; cp tools/m11/ldfix/*.py $D/ldfix/; cp tools/m11/lb_base.py $D/; git show 62b33c07:tools/m11/ldfix/ldfix.py > $D/ldfix/ldfix.py` の後、`python3 $D/ldfix/ldfix.py tools/m11/work/boot_final3.ll $D/base.ll --pe <PE>` と `python3 tools/m11/ldfix/ldfix.py tools/m11/work/boot_final3.ll $D/head.ll --pe <PE>` の出力を `cmp` → 一致。
7. ネガティブコントロール (§2.5): `bash tools/m11/ldfix/f3d_negctl_2745.sh` (`M11_WORK`・`FL_WIN64_DIR` を環境変数で指定)。
8. 監査: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (`M11_WORK`・`LD_WORK`)。

## 7. コード差分

- 測定 commit `57d6612b` 以降のコード差分 (`git diff 57d6612b HEAD -- tools/m11/ldfix/results tools/m11/ldfix/*.py`) は 0 行 (HEAD `4e85ea56` 時点で確認)。`f3d_negctl_2745.sh` は本 commit で追加した再現スクリプトで、audit の経路には入らない。
- 参考: `8a323067` からの差分 (`git diff 8a323067 HEAD -- tools/m11/ldfix/results tools/m11/ldfix/*.py`) は 12 ファイル・+721/-32 行。旧測定の commit の後に F3d と results が変わっている。
- `results/` の版: PR の基点 (merge-base) は `62b33c07`。その `results/spill178_1161.tsv` は 確定 109・判定不能 28・未判定 41 で、`57d6612b` と同一 (`git diff 62b33c07 57d6612b -- tools/m11/ldfix/results` は 0 行)。旧 PR 基点 `858ceef0` の版 (97/16/65) とは `git diff --numstat 858ceef0 62b33c07 -- tools/m11/ldfix/results` で +110/-24 行の差がある。
- 現 main (`738074af`) の `results/spill178_1161.tsv` は 確定 117・判定不能 30・未判定 31 (`git show origin/main:tools/m11/ldfix/results/spill178_1161.tsv` の集計)。本 PR はこの変更を含まず、main 側の再測定は LD-124 (#2689) で行う。

## 8. 注記

- 前回値の参照先 `REPORT_1161.md` は PR #2661 (未 merge) にあり、本 run は main 基点の TSV/JSONL から値を取り直した。
- 実施順の注記 (#2245・#2288・#2583・#2253・#2679 (LD-120)) について: 本 issue の 9 site の関数 (41ba50・41bfa0・41e490・45b170・45c290・45d0a0・45d610・45f560) は、各 issue の本文に現れないことを確認した。#2253 の 7 site は別の関数 (128c320・1280530・dcdde0・c343f0・128f9e0) で、#2679 の 128f9e0 (12 site) とも重ならない。
- `REPORT_2438.md` §5 は xor 0 の類型をコメントで #2253 に残す方針だったが、#2253 は別の 7 site の担当で修復を扱わない。上流 xor 0 の追跡は LD-127 (#2745) に置く。

## 9. LD-134 (#2833): F3d 適用 IR の build・e2e 実測と既定化の判断

- 結論: F3d を適用した IR (58 関数) は build でき、e2e の主要値 (到達 stage・survey ok・通過 unit・trap) は HEAD と同一だった。wasm は +525 B。**既定化しない** (`ldfix.py` の `if tag == 'f3d' and passes is None` の除外は残す。理由は §9.3)。
- 測定 commit: HEAD 側 `554303875` (origin/main・F3d 無効)、F3d 側 `dabf01a96` (F3d の引数欠落 guard を含むコード commit)。本節を足した commit は docs のみで、`git diff dabf01a96 HEAD -- tools/m11/ldfix/results tools/m11/ldfix/*.py` は 0 行。
- 素材の扱い: `work-m11` を worktree `ws-2833` の `tools/m11/work/` に展開し、`fl-win64` の `extracted/block00031_PE.bin` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR`)。素材に `work/lift_pe.sha256` が無いため、素材の PE の sha256 (`b2c64da4…f9496d`) を記録して全再生成を避けた。素材に無い boot5 は RetDec で lift し直し、`m11_data.c`・`m11_image.bin` は PE から生成し直した。

### 9.1 実測 (`bash tools/m11/m11_e2e.sh`・前景・timeout 1200 s)

| 項目 | HEAD (`554303875`) | F3d (`dabf01a96`・58 関数) |
|---|---|---|
| IR 生成 | `m11_gen_ir2.sh` (boot5 を lift し直し) | `LDFIX_ARGS="--passes f1,f1v,f2,f3a,f3b,f3c,f3d,f4" bash m11_gen_ir2.sh` 50.8 s・`f3d_fns`=58 |
| build (emcc 増分) | ok | ok |
| e2e 所要 (wall) | 3 m 09.4 s (`time`) | gen + e2e 合計 125 s (`date` 01:57:51 → 01:59:56) |
| rc | 1 | 1 |
| 到達 stage | 4 (期待 4 を満たす) | 4 |
| survey ok / trap / miss | 873 / 22 / 46 | 873 / 22 / 46 |
| 通常起動 units | 98 / 942 | 98 / 942 |
| 通常起動の trap | memory access out of bounds @ function_535c11 | 同じ |
| wasm bytes | 6047712 | 6048237 (+525) |
| rc=1 の内容 | tolerant gate: 通常起動完了 101 ≠ 期待 56・survey ok 873 ≠ 期待 872 (exact) | 同じ |

- rc=1 は HEAD でも同じ (`e2e_expect.env` の pin と本 snapshot の不一致。F3d の影響ではない)。pin は変えていない。
- load: 測定中の採取はしていない。記録時点の loadavg 0.97 / 0.87 / 0.57・nproc 4。
- gen を含むため、所要の HEAD と F3d の差は直接比較しない。

### 9.2 引数欠落の欠陥 (本節で修正)

- 初版の F3d (`fix_f3d`・guard 無し) は、`function_42d290`・`function_45b8b0` (IR は `define i64 @functionX()` で仮引数 0) の入口に `load i16, ptr %arg1` を挿入した。`argN` の存在を確かめていなかったため、`boot_final3.ll:134179` で `use of undefined value '%arg1'` となり **build が失敗** した (`m11_build.sh` の cc 段・fail-closed)。
- 修正: 仮引数の数が `argN` に足りないときは適用せず `f3d_arg_missing` を数える (`ldfix.py` `fix_f3d`・commit `dabf01a96`)。対象は 60 → 58 関数。3 対象 (45b170・45d0a0・45f560) と判定は変わらない。
- 既定経路 (`--passes` 無し) では F3d は走らないため無変更 (`git diff 554303875 dabf01a96 -- tools/m11/ldfix` は 1 ファイル・5 行追加・5 行削除)。

### 9.3 既定化の判断: しない

1. e2e の主要値が HEAD と同一で、既定化の効果 (到達 stage・通過 unit の増加) を示せない。
2. 受入条件の「57 関数の機械語・IR 突合」は未了。`fix_f3d` の guard (base の argN 解決・入口の movzx word 1 本・xor 候補 1 本) は機械的な一致判定で、独立した突合ではない。確認できない関数は既定化から外す規則に従うと、既定化の根拠が無い。
3. 初版は guard の漏れで build を壊していた。guard に対する negative control (効く入力での FAIL) は未測定。

### 9.4 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| F3d 58 関数のうち 3 対象以外の 55 関数の機械語・IR 突合と、`audit_lsf_ssa_e2e.sh` の HEAD / F3d 比較 (未実施) | 既定化の判断材料が無い | #3528 (LD-160) |
| 既定 e2e の pin (STRICT_DONE 56・SURVEY_OK_EXACT 872) と本 snapshot の不一致 (HEAD でも発生) | 既定の e2e が rc=1 で終わる | #3528 (LD-160) の注意欄 |
