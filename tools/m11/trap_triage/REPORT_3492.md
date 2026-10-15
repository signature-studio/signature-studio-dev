# #3492: strict 証拠表 (接尾辞対応版 288 件) の行 241〜288 の件ごと判定

判定: 対象 48 件のうち **46 件を判定** (真陽性 44・偽陽性 2)。残り 2 件 (行 270・271) は比較値が間接 call の戻り値で由来を確定できず**保留** → 子 issue #3574。
偽陽性率は判定済み 46 件中 2 件 (4.3%)。288 件全体の偽陽性率は、行 194〜240 (#1655 の残り) が終わるまで書かない。

## 1. 測定条件

- 測定 commit: `d82a36b04` (`tools/m11/trap_triage/judge_ctx.py` を追加した commit)。
  - `git diff d82a36b04 HEAD -- tools/m11/guard699 tools/m11/ldfix tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_dump.py tools/m11/trap_triage/judge_ctx.py` = **0 行** (測定後にコードを変えていない)。
- 基準 commit: `origin/main` = `e5c96411e`。
- 入力 (`tools/m11/work/`・gitignore。`oc_artifacts: fl-win64 work-m11` で取得):
  - `boot_final.ll` 19,787,837 B・sha256 `69c774ded8aaf717…` (REPORT_718 §4a と一致)。
  - `block00031_PE.bin` 22,227,016 B (`fl-win64`・`extracted/`)。
- 生成 (本 run):
  - `python3 tools/m11/guard699/scan_guard.py tools/m11/work/boot_final.ll --pe <PE> --report tools/m11/work/strict3492.json` → strict **288**・4.1 s。
  - positive control: `function_8c5eb0` の `8c5f18 jg → 8c6066` (#699) が strict に入る (✓)。
  - `python3 tools/m11/trap_triage/strict_evidence.py ... --out tools/m11/work/strict_evidence_3492.tsv` → TSV **288 行** (ヘッダ除く)・12.0 s。
- 環境: `uptime` の load average 0.14 0.08 0.11 (判定後の時点)。判定は subagent 6 本の並列 (各 8 件)。

## 2. 判定規則

対象: 機械語の jcc A (直前の cmp/test の被演算子 X・Y) が前方の脱出先 T へ飛ぶ。A の帰属ブロック B の IR 終端は無条件 `br` で、後方のループ先頭 L に入る。L へは back-edge がある (`scan_guard.py` の strict 定義)。

問い: 機械語の guard と**同じ値・同じ条件の判定**が IR に残っているか。

- **真陽性 (TP)**: 同じ値・同じ条件の判定が IR に無い。B→L の入口経路にも L の頭にも無い。L 末尾の判定 (count 判定 `icmp eq (rdi-1), 0` など) は事後の判定で、guard (事前の判定) とは条件が異なるため根拠にならない。
- **偽陽性 (FP)**: 次のいずれか。(a) IR に同じ値 (reg2mem の store/load を遡って一致) の同等判定が、同じ脱出の効果へ至る形である。(b) 機械語の jcc が恒偽で、T へ飛ばない (挙動差が無い)。
- **保留**: SSA を遡りきれない、または値の由来が IR で確定できない。推測で TP/FP にしない。
- レジスタ名の一致だけは根拠にしない。機械語の初期値 (`xor eax,eax` → `mov ebx,eax` など) と IR の初期値 (`store i64 0`) と更新 (`+1`・`-1`) の両方を照合する。

判定材料は `tools/m11/trap_triage/judge_ctx.py` が出す (行ごとに、jcc 直前 10 命令・CMP 被演算子・B の IR・L の IR・L への分岐元・T への IR 分岐・比較レジスタの reg2mem 参照行)。判定はしない。

## 3. 結果

| 判定 | 件数 | 行 |
|---|---|---|
| 真陽性 (TP) | 44 | 241〜254・256・257〜260・262〜269・272〜280・281〜288 |
| 偽陽性 (FP) | 2 | 255・261 |
| 保留 | 2 | 270・271 (→ #3574) |
| 合計 | 48 | 241〜288 |

## 4. 件ごとの判定

行 = 証拠表のデータ行 (ヘッダ除く 1 始まり)。X vs Y は機械語の cmp 被演算子。`N` は機械語の値の由来。

| 行 | 関数 | jcc → T | 判定 | 根拠の要点 |
|---|---|---|---|---|
| 241 | function_e44090 | e440aa jg → e440df | TP | X=ebx=0 (xor eax,eax)、Y=edi=N−1。N≤0 で脱出。B→L 入口に判定無し。L 末尾は count 判定のみ |
| 242 | function_e442c0 | e442da jg → e44326 | TP | 241 と同型。入口判定無し |
| 243 | function_e4b5f0 | e4b62e jg → e4b6a9 | TP | X=ebx=0、Y=r14d=N−1。入口判定無し。末尾は事後判定 |
| 244 | function_e4b750 | e4b7b2 jg → e4b82f | TP | X=ecx=0、Y=r14d=N−1。入口判定無し。末尾は counter 判定 |
| 245 | function_e53810 | e53878 jg → e5395c | TP | X=ecx=0、Y=r14d=M−2。入口判定無し。末尾は事後の ==0 |
| 246 | function_e55c80 | e55ece jg → e56265 | TP | X=[rbp+0x7c]=0、Y=esi=N−1。L 頭の icmp は byte 判定のみ |
| 247 | function_e591f0 | e59298 jg → e5934b | TP | X=ecx=0、Y=edi=N'(call 後に読込)。N'=−1 で本体を実行。機械側 `[rbp+0x28]` と IR `%arg1` の同一性は未照合 (判定は IR 側に入口判定が無いことで決まる) |
| 248 | function_e59ad0 | e59b08 jg → e59bb1 | TP | X=edi=0、Y=r13d=N−1。入口判定無し |
| 249 | function_e83a50 | e83af7 jg → e83b51 | TP | X=eax=0、Y=r8d=K−1 (K≤0 で脱出)。B→L・L 頭に K 判定無し |
| 250 | function_e83a50 | e83be6 jg → e83c4f | TP | 249 と同型 (r8d=K−1)。入口判定無し |
| 251 | function_e90060 | e900f2 jg → e902bc | TP | X=ecx=0、Y=r13d=N−1。入口・L 頭に N 判定無し |
| 252 | function_e92440 | e92467 jg → e924a4 | TP | X=edi=0、Y=r14d=N−1。L 頭の判定は別のフラグ |
| 253 | function_ea77c0 | ea77fc jg → ea7821 | TP | X=edi=0、Y=r14d=M−1。L (tail と同一) に M 判定無し |
| 254 | function_ea7ae0 | ea7d46 jg → ea7e45 | TP | X=ebx=0、Y=r13d=M−1。L 頭は配列要素の比較のみ |
| 255 | function_ea8a80 | ea8af0 jg → ea8bd4 | **FP** | 入口 ea8a80 に `icmp slt N,1 → ret(-1)` (N≤0 で脱出) がある。guard は N≥1 の経路でのみ到達し、そこで 0 > N−1 は恒偽。前提は §5 |
| 256 | function_ec2150 | ec2210 jg → ec24de | TP | X=ecx=0、Y=edi=K−1。入口・L に K 判定無し。参照段数の不一致は §6 |
| 257 | function_ec3190 | ec31f5 jg → ec3242 | TP | X=esi=0、Y=r14d=N−1。B→L 入口に N 判定無し |
| 258 | function_ec3190 | ec32d6 jg → ec32ff | TP | X=esi=0、Y=ecx=N−1。入口判定無し |
| 259 | function_ec3190 | ec3372 jg → ec33c2 | TP | X=esi=0、Y=r14d=N−1。第1ループを経ない経路 (ec329c.crit→ec335c) でも判定無し |
| 260 | function_ec3190 | ec34e2 jg → ec350c | TP | X=esi=0、Y=ecx=N−1。入口判定無し。L 頭の slt は element 側 |
| 261 | function_ec35f0 | ec3667 jg → ec380c | **FP** | X=ebx=1 (`mov eax,1` が ec364d で必ず実行される)、Y=r14d∈{999,1000} (`setge`+999)。1 > r14d は恒偽で T へ飛ばない。挙動差なし。§5 |
| 262 | function_f0da60 | f0da80 jg → f0daa1 | TP | X=esi=0、Y=edi=N−1。B は関数先頭。入口判定無し |
| 263 | function_f3e190 | f3ef3f jg → f3effa | TP | X=[rbp+0x39c]=0、Y=ebx=N−1。B→L 入口判定無し |
| 264 | function_f40840 | f4321d jg → f4325c | TP | X=[rbp+0x45e8]=0、Y=ebx=low32(call 0x103b7c0)−1。入口判定無し |
| 265 | function_f40840 | f43567 jg → f4362d | TP | X=[rbp+0x45e8]=0、Y=N−1。入口・L 頭に N 比較無し。末尾は count 判定 |
| 266 | function_f40840 | f436f4 jg → f43b73 | TP | X=ecx=0、Y=eax−1 (call 0x12f9ed0 の戻り)。入口判定無し |
| 267 | function_f40840 | f43b99 jg → f43cde | TP | 266 と同型 (call 0x12f9ed0)。入口判定無し |
| 268 | function_f40840 | f44307 jg → f44342 | TP | X=[rbp+0x45e8]=0、Y=ebx−1 (ebx=[rbp+0x138])。f442a2 の icmp は V==0 で別値 |
| 269 | function_f552a0 | f552c3 jg → f5538c | TP | X=esi=0、Y=edi=N−1。B は無条件 br。N=0 で本体を 1 回実行 |
| 270 | function_f5cf40 | f5d0d6 jg → f5d198 | **保留** | Y=eax−1、eax は間接 call `call qword ptr [rax+0x28]` の戻り値。IR に対応する call が無く由来を確定できない → #3574 |
| 271 | function_f5d510 | f5d782 jg → f5d82d | **保留** | 270 と同型 (間接 call の戻り値)。→ #3574 |
| 272 | function_f69390 | f69412 jg → f695ed | TP | X=eax=0、Y=ecx=N−1。B は関数先頭。入口判定無し。N 源の定数は IR 0x11E0A00・機械 0x15E0A00 (差 0x400000 = 像ベース差) |
| 273 | function_f697d0 | f69804 jg → f69860 | TP | X=eax=0、Y=r9d=N−1。B→L・L 頭に N 判定無し |
| 274 | function_f6d390 | f6d3b6 jg → f6d420 | TP | X=edi=0、Y=r14d=R−1 (R=call 0x611430 の戻り)。入口判定無し |
| 275 | function_f825b0 | f825cc jg → f82644 | TP | X=eax=0、Y=r9d=N−2。入口判定無し |
| 276 | function_f82850 | f828bb jg → f82961 | TP | X=eax=0、Y=r8d=N−1。N<0 は f8286e (slt 11) から B→L に入り、N≤0 の判定が IR に無い |
| 277 | function_f82c20 | f82c78 jg → f82cc0 | TP | X=esi=0、Y=r14d=N−1。入口・L 頭に N 判定無し |
| 278 | function_fe74d0 | fe74ed jg → fe7553 | TP | X=ebx=0、Y=edi=N−1。B は関数先頭で入口判定無し。参照段数の不一致は §6 |
| 279 | function_fe75c0 | fe75df jg → fe7629 | TP | X=esi=0、Y=edi=N−1。入口判定無し。参照段数の不一致は §6 |
| 280 | function_fea390 | fea49b jg → fea503 | TP | X=esi=0、Y=edi=N−1。fea3dd の `slt 1` は宛先が B (skip ではない) |
| 281 | function_ff0d70 | ff237c jg → ff2dc3 | TP | X=[rbp+0x454]=0、Y=N−1 (zext byte)。N=0 で本体へ入る。B→L 入口に N 判定無し |
| 282 | function_ff0d70 | ff23bd jg → ff2db0 | TP | X=[rbp+0x458]=0、Y=M−1。内側ループの入口に M 判定無し |
| 283 | function_ff0d70 | ff2e81 jg → ff30ec | TP | X=[rbp+0x458]=0、Y=M−1。B の pred に M 判定無し |
| 284 | function_ff0d70 | ff31b5 jg → ff33ad | TP | X=[rbp+0x454]=0、Y=N−1。N 由来の入口判定無し (L の slt は添字) |
| 285 | function_ff0d70 | ff35e9 jg → ff3928 | TP | X=[rbp+0x458]=0、Y=K−1。K を被演算子にする icmp 無し (`%1443` は別値) |
| 286 | function_ff0d70 | ff3611 jg → ff3915 | TP | X=[rbp+0x454]=0、Y=N−1。入口判定無し |
| 287 | function_ffa560 | ffa603 jg → ffa6c4 | TP | X=ecx=0、Y=edx=M−1。M≤0 で探索に入らず返るはずが、IR は探索本体に入る |
| 288 | function_ffa940 | ffa96e jg → ffa9ed | TP | X=r13d=0、Y=r14d=M−1。M≤0 で ffa9ed へ抜けるはずが、IR はエントリから探索本体に入る |

## 5. 偽陽性 2 件の根拠

- **行 255 (`function_ea8a80`)**: 機械語の guard は `cmp esi(=0), r14d(=N−1); jg` で、N≤0 のとき T=ea8bd4 へ飛ぶ。IR の入口 ea8a80 には `%2 = load [arg1+20]`・`%3 = icmp slt N,1`・`br %3 → ret(-1)` (ea8be8) がある。同じ値・同じ条件の判定が、guard より前に IR に存在する。
  - 検算: guard に到達するのは N≥1 の経路だけで、そこでは 0 > N−1 が恒偽。
  - 前提 (未確定): guard の N は入口判定の後 (`call function_1060d20(arg1)` の後) に再読込される。`function_1060d20` 本体は `[arg1+20]` を読むだけで、書くのは `[arg1+72]` のみ (確認済み)。内部で呼ぶ `function_12df530` の副作用は**未確認**。ここが崩れると TP になる。 → #3574 の受入条件に入れた。
- **行 261 (`function_ec35f0`)**: 機械語は `mov eax,1` (ec364d) の後に `mov ebx,eax` (ebx=1)、`r14 = setge + 999` (999 または 1000)、`cmp ebx, r14d; jg ec380c`。1 > r14d は恒偽で、jcc は一度も成立しない。IR に T への脱出が無いのは挙動差を生まない。判定の型は「同じ判定が IR にある」ではなく「機械語の guard が恒偽」(FP の (b))。

## 6. 所見 (判定の外)

- **参照段数の不一致 (行 256・278・279)**: 機械語は `mov rcx,[G]; mov rcx,[rcx]; mov edi,[rcx+0x10]` (qword 逆参照 2 段) で N を読む。IR は `%0 = load i32 [G]` (G の下位 32bit) → `load i32 [sext(%0)+16]` の 1 段で、`mem64[P1]` の逆参照が IR に無い。IR の N は機械語の N と別の値になりうる。TP の判定 (入口判定の欠落) は変わらないが、値そのものの誤りの有無と件数は未測定。起票先: #1187 (件ごとの真偽・偽陽性率の既存親) へのコメントで提案する (DEFECTS 行案は PM 判断)。
- **間接 call (行 270・271)**: 比較値の由来が間接 call の戻り値。IR に対応する call が無く、lift で call が落ちている可能性がある。判定は #3574。
- **行 241 と 242 の意味**: N=0 のとき、機械語は本体を飛ばすが IR は本体を 1 回実行し、末尾の `rdi-1 = −1` (trunc 32bit) で後方へ続く。TP の根拠はこの挙動差ではなく、入口判定の欠落そのもの。

## 7. 再現

```sh
cd tools/m11
python3 guard699/scan_guard.py work/boot_final.ll --pe <block00031_PE.bin> --report work/strict3492.json
python3 trap_triage/strict_evidence.py work/boot_final.ll --pe <block00031_PE.bin> --report work/strict3492.json --out work/strict_evidence_3492.tsv
python3 trap_triage/judge_ctx.py work/boot_final.ll --pe <block00031_PE.bin> --tsv work/strict_evidence_3492.tsv --lo 241 --hi 288
```

- 同じ commit (`d82a36b04`) で、行 241〜248 の出力が判定に使った `ctx` と一致することを確認 (`cmp`)。
- ネガティブコントロール: strict 288 件の中に positive control `8c5f18` があり、検出器は既知の真陽性を拾う。

## 8. 検証範囲と限界

- 件ごとの判定は subagent 6 本の SSA 追跡 (各 8 件)。lead は次を読み直して照合した: 行 241・242 (機械語と IR の全体)、行 255 (入口ブロックと `function_1060d20`)、行 256・278・279 (機械語の逆参照段数)、行 261 (`mov eax,1` と `setge`)。
- 別アルゴリズムの検算 (IR の被演算子を機械的に再計算する突合) は未実施。判定の誤りを見つける検収は reviewer に任せる。
- 「B は無条件 br・B に icmp が無い」は TSV の `ir_block_cond=0` と BLK-icmp の空で機械的に確認した (48 件とも `ir_block_cond=0`)。

## 9. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 行 270・271 の判定 (間接 call の戻り値) | 2 件が保留 | #3574 |
| 行 255 の FP 前提 (`function_12df530` の副作用) | FP 判定の確度 | #3574 |
| 参照段数の不一致 (行 256・278・279 ほか。IR 1 段・機械 2 段) の件数と、値の誤り | 値の誤りの有無は未測定。TP 判定には影響しない | #1187 へのコメント (提案) |
| 行 194〜240 (#1655 の残り) | 288 件中 46 件を判定、残り 194〜240 は未判定 | #1655 (既存) |

## 10. 範囲

- 変更: `tools/m11/trap_triage/judge_ctx.py` (新規・判定材料の出力のみ)、`tools/m11/trap_triage/REPORT_3492.md` (新規)、`docs/DOC_MAP.md` (登録)。
- 変更しない: `tools/m11/guard699/`・`tools/m11/ldfix/`・`strict_evidence.py`・`judge_dump.py`・RetDec 本体・`m11_ov.c`。
- 20 MiB 超の blob: なし。`tools/m11/work/` は gitignore (commit しない)。
