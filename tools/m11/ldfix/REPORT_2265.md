# REPORT #2265 — spill 宛 未判定 関数群 C 後半 (19 関数・23 site) の消費者分類 (LD-98)

親: #2246 (LD-94) / #1161 (LD-35)。前 run の機械語後続読み出しの列挙は PR #2286 (merge 済み)。その後の fix commit `b665b667` は main に未取込のため、本 run の起点に含めた。

既知類型との関係 (`docs/DEFECTS.md`): 6 site は **D15** (メモリ間接 call の IR 欠落) と同型。`815050:815220` は REPORT_510 §2 の 2 段 deref 潰れ型 (DEFECTS.md の D4 の変種)。`775340:77545c`・`12f9730:12f9752` は DEFECTS.md に無い形で、§5 に候補として記す。番号は DEFECTS.md の D 番号 (`tools/icall/REPORT.md` §4 の D 番号とは別体系)。

## 1. 結論 (受入条件ごと)

| 受入条件 | 結果 |
|---|---|
| 19 関数・23 site の未判定 site を機械語・IR の両面で追跡し 4 種のいずれかに分類 | **部分達成**。確定 14 (OK_LOAD 13・TRUE_DROP 1) / 未判定 9 (IR・機械語の照合待ち、§4)。NO_CONSUMER 0 / UNDETERMINED 0 |
| 判定の根拠 (機械語・IR の行) を `candidate_verdicts_1161.jsonl` と同じ形式で残す | **部分達成**。確定 14 行を残す (既存 31 行は不変)。照合待ちの 9 行は `results/held_verdicts_2265.jsonl` に根拠の原文のまま退避 (台帳には入れない) |
| 分類表を再生成し範囲の未判定を 0 件にし、`audit_lsf_ssa_e2e.sh` の 7/7 で確認 | **未達**。範囲の未判定は 9 (23 → 9)。head の e2e は未実施 (`work-m11`・`work-liftdiff` の素材が無い、§6)。分類表は commit 済みの入力から再生成して確認 (§6) |
| 脱落関数の和集合の更新を報告 | **達成 (head の再集計・e2e 外)**。69 → 72 (+3。内訳は §3) |

- 判定の根拠は、本 run で IR (`boot_final3.ll`) も機械語像 (`m11_image.bin`) も照合できなかった。確定 14 行の IR 行は前 run の subagent の引用のままで、親が再確認したのは `6c3700:6c3a63` の 1 件だけ (§2・§4)。
- 測定 commit (e2e の実測): **`482ec43d`**。その後の `results/` の変更 (main 取込と判定の撤回) は e2e で再測定していない。

## 2. 対象 23 site の分類

判定は subagent 6 本 (関数単位・並列・読み取りのみ) が機械語 (`ld98_dump.py` と同じ `audit_lsf.descend` で降下) と IR (`tools/m11/work/boot_final3.ll` の `function_<fn>` 本体) を突き合わせて出した。前 run で親は、判定の根拠行を `candidate_verdicts_1161.jsonl` に追記する前に、D15 同型の代表 1 件 (6c3700:6c3a63 の IR 267283-267294 のループ) を直接確認した。本 run では `boot_final3.ll` が無いため IR の照合は 1 件も再実施していない (表の IR 列は前 run の引用のまま)。照合できなかった 9 件は判定から外した (§4)。

| fn | site | 判定 | 機械語の消費者 | IR 側の対応 (boot_final3.ll 行・前 run の引用) |
|---|---|---|---|---|
| 4fa3d0 | 4fa681 | OK_LOAD | 4fa690 → 4fa694 call 0x40faa0 (第1引数) | 181133 load → 181135 call function_40faa0 |
| 4fa3d0 | 4fa7aa | OK_LOAD | 4fa7b9 → 4fa7bd call 0x40faa0 (第1引数) | 181198 load → 181200 call function_40faa0 |
| 4fad10 | 4faf0b | OK_LOAD | 4faf1a → 4faf1e call 0x40faa0 (第1引数) | 181712 load → 181714 call function_40faa0 |
| 4fb780 | 4fb7d9 | OK_LOAD | 4fb7ec → 4fb7f0 call 0x4fb000 (第2引数) | 182351 load → 182358 call function_4fb000 |
| 5c00e0 | 5c013f | OK_LOAD | 5c0143 cmp・5c014e/5c015a 比較・5c017a call 0x439670 | 203721 load → 203722 icmp・203754-203758 call function_439670 |
| 5c0270 | 5c030d | OK_LOAD | 5c0311・5c0321 の読み出し → 5c032f store | 203869 store → 203864 reload → 203867 icmp・203872-203873 |
| 76e720 | 76e74f | OK_LOAD | 76e778 mov rax,[rbp+8] → ret (戻り値) | 287837・287846 store i64 -1 → 287858 load → 287859 ret |
| 775340 | 77545c | 未判定 (旧 TRUE_DROP・照合待ち) | 775657 → 775678 call 0x7747c0 (rcx を読む) | 290821 call function_7747c0() は引数 0 個。被呼出側 290584 の alloca に store 無し → 290589 load が undef |
| 775340 | 77593b | 未判定 (旧 OK_LOAD・照合待ち) | 7759f6・775a29 → float store (P 経由) | 291006 load P → 291069・291092 store (§4) |
| 815050 | 815220 | 未判定 (旧 TRUE_DROP・照合待ち) | 815227 cmp・815231 → 815238 mov rax,[rax-8] | 318485 load G (一段のみ) → 318486・318491・318493 が一段目の値を使う (二段目の deref 欠落) |
| 6c3700 | 6c3a63 | **TRUE_DROP** (親が前 run で直接確認) | 6c3a6b call [rdi+0x128] (第5引数) | 267283-267294 の内側ループはカウンタ加算のみ。間接 call 無し (D15) |
| 6c3700 | 6c3c78 | 未判定 (旧 TRUE_DROP・照合待ち) | 6c3c80 call [r13+0x128] (第5引数) | 267396-267407 のループはカウンタ更新のみ。間接 call 無し (D15) |
| 6c3d20 | 6c44bd | 未判定 (旧 TRUE_DROP・照合待ち) | 6c44c5 call [rsi+0x128] (第5引数) | 267830-267841 のループはカウンタ更新と減算のみ。間接 call 無し (D15) |
| 6c5930 | 6c6125 | 未判定 (旧 TRUE_DROP・照合待ち) | 6c612d call [rbx+0x128] (第5引数) | 対応ブロック無し (267973-268105)。根拠が IR の不在のみ (§4) |
| 1042d20 | 1043e2d | 未判定 (旧 TRUE_DROP・照合待ち) | 1043e34 call [rsi+0x188] (第5引数) | 14896-14897 の load 2 本は 14898 call function_12d6660 の引数に届かず未使用。間接 call 無し (D15) |
| c57a00 | c57e24 | OK_LOAD | c57e84・c57f6f mov ebx,[rbp+0x5c] (直後に add ebx,[rbp+0x58]) | 390006 load → 390040・390163 の add が同じ %220 を消費 |
| f3e050 | f3e0c2 | 未判定 (旧 TRUE_DROP・照合待ち) | f3e10b call [rax+0x38] (rdx=lea [rbp+0x3c] で slot を渡す) | 468265-468278 に call 無し。slot を渡す call は別分岐の 468262 function_a9ece0 のみ (D15) |
| f67400 | f67560 | OK_LOAD | f67573 call 0x661dc0 (第2引数) | 478296 load → 478306 zext → 478310 call function_661dc0 |
| 101d180 | 101d2b4 | OK_LOAD | 101d2c3 → call 0x40faa0 (第1引数) | 7458 load → 7460 call function_40faa0 (反復側 7478-7480 も同経路) |
| 101d180 | 101d423 | OK_LOAD | 101d432 → call 0x40faa0 (第1引数) | 7597 add → 7599 load → 7604 call function_40faa0 |
| 1221290 | 1221676 | OK_LOAD | 1221686・1221699 の比較 (12216c2) | 51268-51270 → 51274 icmp ugt → 51276 select → 51320 icmp slt (§4) |
| 127d420 | 127d881 | OK_LOAD | 127da8f → 127da95 [rsp+0x28] = call 0x6c9d30 の第6引数 | 64754 load → 64764 sext → 64932 trunc → 64933 call function_6c9d30 |
| 12f9730 | 12f9752 | 未判定 (旧 TRUE_DROP・照合待ち) | 12f975e・12f9842 mov ecx,[rsp+0x50] → cmp (比較) | 96779 `xor i64 0,0` → 96781 trunc で store 元が定数 0 に置換。96871 の比較に 0 が流入 |

- 旧 TRUE_DROP 9 件のうち確定として残したのは `6c3700:6c3a63` の 1 件だけ。残り 8 件は §4 のとおり判定から外した。
- 機械語の `[rsp+0x20]` 系 (6c3700・6c3d20・6c5930・1042d20) は Windows x64 の第 5 引数領域で、消費者は後続の間接 call。TSV の後続読み出し 0 件はこの形の結果。

## 3. 分類表と脱落関数の和集合

| 項目 | 前 (b665b667・分類前) | 482ec43d (e2e 実測・旧) | head 1da6d153 + 本 commit (commit 済み入力から再生成・e2e 外) |
|---|---|---|---|
| spill 宛 unk site | 178 / 71 関数 | 178 / 71 関数 | 178 / 71 関数 |
| status 未判定 / 確定 / 判定不能 | 120 / 51 / 7 | 97 / 74 / 7 | **77 / 92 / 9** |
| 範囲 (19 関数・23 site) の未判定 | 23 | 0 | **9** (確定 14) |
| 脱落関数の和集合 (store DROP 51 ∪ spill 確定 TRUE_DROP) | 69 (drops_510.tsv) | 77 (= 69 + 8) | **72** (= 69 + 3) |

- 和集合の増分 3 の内訳: `6c3700` (本 PR の確定 TRUE_DROP)・`4120c0`・`41a5d0` (main 取込の候補行 74・78 行目由来)。`spill_classify_1161.py` の [6] 行が出力した値。
- 482ec43d の 77 は本 PR の 8 新規関数 (`6c3700` `6c3d20` `6c5930` `775340` `815050` `f3e050` `1042d20` `12f9730`) の判定由来。照合待ちで判定を外したため、その 7 関数は和集合から外れた。
- 和集合は確定した TRUE_DROP (目視・候補) だけから作る。候補の未判定は含めない (`spill_classify_1161.py` の定義どおり)。
- `drops_510.tsv` (#510 の目視・動的の集計) は変更していない。`results/` の差分は `candidate_verdicts_1161.jsonl` (9 行削除) と `spill178_1161.tsv` (9 行の status 更新) と `held_verdicts_2265.jsonl` (新規・9 行) のみ。

## 4. 判定の強さ (照合待ちの判定と弱い根拠)

- **判定から外した 9 件** (`results/held_verdicts_2265.jsonl` に根拠の原文を残した。台帳には入れていない。`spill_classify_1161.py` の入力は台帳なので未判定として扱われる):
  - 775340:77545c・815050:815220・6c3700:6c3c78・6c3d20:6c44bd・6c5930:6c6125・1042d20:1043e2d・f3e050:f3e0c2・12f9730:12f9752 (旧 TRUE_DROP 8 件): IR の `boot_final3.ll` が無く、引用行を照合できない。`6c5930:6c6125` は IR 対応ブロックが無いことだけが根拠で、もとから弱い。
  - 775340:77593b (旧 OK_LOAD): 機械語のループ内の間接 call `7759bb` の副作用 (`*X` の書き換え) が未確認。その callee の機械語を確認するには `m11_image.bin` が要るが、本 run に無い。確認できなければ未判定のまま残す (指摘 4 の扱い)。
- **照合待ちの判定を外す基準**: 指摘 3・4 の「確認できない site は判定を外す」。この run で照合できたのは 0 件。
- **残した TRUE_DROP 1 件 (6c3700:6c3a63)**: 前 run で親が IR 267283-267294 を直接確認した記録に基づく。本 run では再照合していない。
- **確定 14 件の IR 行**: 前 run の subagent の引用のまま。本 run で再照合できていない。
- **76e720:76e74f** (OK_LOAD): IR では site の値が定数 `store i64 -1` に置き換わっている。機械語の値 (`[rbp],[rbp+4]` の dword 0xffffffff から組んだ qword -1) と一致するため OK_LOAD とした。定数化を別扱いにする方針なら再判定。
- **1221290:1221676** (OK_LOAD): 値の経路は一致する。判定外の付記として、機械語の比較は符号付き (jg) だが IR は `icmp ugt` と `zext → icmp slt` で符号扱いが一致しない (§5 の候補)。
- **ld98_dump.py の修正**: 76e720 の後続読み出し 0 件は、capstone が小さい変位を 10 進 (`[rbp + 8]`) で出すのに、照合が `0x8` 形式しか見ていなかったための取りこぼし。`(0x%x|%d)` に直し、TSV を再生成した (`ld98_consumers_2265.tsv` の 76e74f 行: 読み 0 → 1 (76e778)・書き 1 (76e774))。他の 22 行は変わらない。

## 5. 既知類型との対応・新規類型の候補 (DEFECTS 行案)

- D15 (既存): 6 site (うち確定は 6c3700:6c3a63 の 1 件。残り 5 件は照合待ちで §4)。`call qword ptr [reg+disp]` の IR 欠落。
- 815050:815220 (REPORT_510 §2 の型・D4 の変種・照合待ち): `mov rax,[rip+cell]; mov rax,[rax]` の二段 deref が IR で一段に潰れる。
- 775340:77545c (候補・DEFECTS 未登録・照合待ち): 間接 call の引数が欠落し、被呼出側が未初期化の alloca を読む。行案 (`docs/DEFECTS.md` 形式):
  - 症状: 間接 call `call [mem]` の呼出先 `7747c0` が、引数 (rcx) に入るはずの値を受け取らず未初期化の値を読む。
  - 根本原因: stage-0 IR の間接 call で引数列が落ち、IR の `call function_7747c0()` が引数 0 個になる。被呼出側の alloca に store が無く、load が undef になる。
  - 観測: 機械語 775657 → 775678 `call 0x7747c0` は rcx を読む。IR 290821 の call は引数 0 個。被呼出側 290584 の alloca に store 無し、290589 の load が undef。
  - 検出信号: 機械語の call 前のレジスタ読み出し (引数) と IR の call 引数数の不一致。機械的に検出可能。
  - 修復: 間接 call の引数列を、機械語の引数レジスタ (rcx/rdx/r8/r9 とスタック) から IR へ転記する。修復は PM 判断 (本 run では未実施)。
- 12f9730:12f9752 (候補・DEFECTS 未登録・照合待ち): 引数由来の値が `xor i64 0,0` の定数 0 に置換される (機械語は二段参照)。行案 (`docs/DEFECTS.md` 形式):
  - 症状: 比較 (cmp) の右辺が定数 0 になり、機械語が [rsp+0x50] から読んだ値と異なる。
  - 根本原因: 二段参照 (ポインタ → 値) の値が lift で定数 0 に置換され、その store 元が `xor i64 0,0` になる。
  - 観測: 機械語 12f975e・12f9842 `mov ecx,[rsp+0x50]` → cmp。IR 96779 `xor i64 0,0` → 96781 trunc で store 元が定数 0。96871 の比較に 0 が流入。
  - 検出信号: store 元が定数 0 の IR と、機械語の同じ位置の load 先の値の不一致。機械的に検出可能。
  - 修復: 二段参照の load を定数に畳み込まないよう lift を直す。`815050:815220` (D4 の変種) と同型か未確認。修復は PM 判断 (本 run では未実施)。
- 1221290:1221676 の符号比較の不一致 (候補): jg (符号) → IR の ugt・slt (符号・非符号の混在)。今回の分類の対象外。

## 6. 検証

- **e2e の実測 (`482ec43d`・最終測定)**: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (`ws-2265` worktree・branch `2265-ld98-spill-consumer-c2`・素材 `work-m11` と `work-liftdiff` を worktree 内に展開)。rc=0・real 2m23.3s・user 2m22.0s・load average 0.21 (開始) → 0.93 (終了)・7/7。`drops_510.tsv` と `spill178_1161.tsv` は results/ と一致 (cmp OK)。この実測は本 PR の旧 HEAD のもの。
  - 実行 1 (`b665b667`・分類前): rc=0・real 2m23.9s・7/7・未判定 120。
  - 実行 2 (分類の追記後・結果ファイル更新前): rc=1。step 7 の `cmp` が `spill178_1161.tsv` の 23 行 (未判定 → 確定) で旧 TSV と不一致。結果ファイルを $OUT の生成物で更新して実行 3 で再測定した。
- **head `1da6d153` と本 commit の e2e は未実施**: 本 run の `$ARTIFACTS_DIR` には `fl-win64.tar.zst` しか無く、`tools/m11/work/` (boot_final3.ll・m11_image.bin・boot*.drc.config.json) と `tools/liftdiff/work/` が無い。`audit_lsf_ssa_e2e.sh` は起動できない。
- **e2e 外の再生成確認 (IR 不要)**: `python3 tools/m11/ldfix/spill_classify_1161.py tools/m11/ldfix/results/audit_510_ssa.json` は、head の commit 版 `spill178_1161.tsv` と一致した (cmp OK・判定の撤回前)。撤回後は同じコマンドで TSV を再生成した (§3 の数値はその出力)。step 7 の入力 `ssa.json` は head で IR から生成されるため、これは step 7 の代替ではなく、分類表の再生成が commit 済み入力だけで決まることの確認。
- **差分の証跡 (測定 commit から HEAD まで・測定対象)**: 前版の「`git diff --stat 482ec43d HEAD -- ... results` → 空」は誤りだった (取り消す)。実測の `git diff --stat 482ec43d HEAD -- tools/m11/ldfix/ld98_dump.py tools/m11/ldfix/results` は 7 files changed, 507 insertions(+), 47 deletions(-)。内訳: `audit_undefload_dest_2202.json` (+210)・`audit_undefload_dest_2202_head.json` (+201)・`ld105_reg2mem_map.tsv` (+16)・`ld110_reg2mem_link.tsv` (+4) は main 取込 (`1da6d153`) 由来。`candidate_verdicts_1161.jsonl` は main 由来の 29 行追記と本 commit の 9 行削除。`spill178_1161.tsv` は 76 行の差し替え (main 由来の候補判定 29 行の反映と、本 commit の 9 行の判定撤回)。`held_verdicts_2265.jsonl` は本 commit の新規 9 行。`ld98_dump.py` は差分 0。WORKFLOW §6 により、この差分の分だけ e2e の再測定が要る (未解決表)。
- 検査: `find tools/m11/ldfix -type f -size +20M` は 0 件。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| HEAD の e2e 再測定 (`audit_lsf_ssa_e2e.sh` の rc・real・load・7/7・step 5/7 と 7/7 の `cmp`) と §3・§6 の数値・測定 commit の head への更新 | 測定 commit `482ec43d` 以降の差分あり (§6)。e2e は未実施 | 本 PR の次回 run (PR 本文の `oc_artifacts: fl-win64 work-m11 work-liftdiff` で素材を要求) |
| 照合待ち 9 件 (`results/held_verdicts_2265.jsonl`) の IR・機械語の照合 (`boot_final3.ll`・`m11_image.bin` が要る) | 範囲の未判定 9 件・脱落集合 (72) の確度 | 同上。照合後に台帳へ戻す |
| 確定 14 件の IR 行の再照合 (親は 6c3700:6c3a63 のみ直接確認) | 確定判定の確度 | 同上 |
| 1221290:1221676 の比較の符号扱い不一致 (機械語 jg / IR ugt・slt) | 判定外の別欠陥候補 | 親 #2246 へ報告 (DEFECTS 行案は §5) |
| ld98_dump 以外 (audit_lsf 系) の 10 進変位の取りこぼしの有無 | 未確認。あれば脱落集合が変わり得る | 親 #2246 へ報告 |
