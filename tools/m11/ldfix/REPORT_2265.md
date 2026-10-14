# REPORT #2265 — spill 宛 未判定 関数群 C 後半 (19 関数・23 site) の消費者分類 (LD-98)

親: #2246 (LD-94) / #1161 (LD-35)。前 run の機械語後続読み出しの列挙は PR #2286 (merge 済み)。その後の fix commit `b665b667` は main に未取込のため、本 run の起点に含めた。本 run で 23 site の分類を完了した。

既知類型との関係 (`docs/DEFECTS.md`): 6 site は **D15** (メモリ間接 call の IR 欠落) と同型。`815050:815220` は REPORT_510 §2 の 2 段 deref 潰れ型 (DEFECTS.md の D4 の変種)。`775340:77545c`・`12f9730:12f9752` は DEFECTS.md に無い形で、§5 に候補として記す。番号は DEFECTS.md の D 番号 (`tools/icall/REPORT.md` §4 の D 番号とは別体系)。

## 1. 結論 (受入条件ごと)

| 受入条件 | 結果 |
|---|---|
| 19 関数・23 site の未判定 site を機械語・IR の両面で追跡し 4 種のいずれかに分類 | **達成**。OK_LOAD 14 / TRUE_DROP 9 / NO_CONSUMER 0 / UNDETERMINED 0 |
| 判定の根拠 (機械語・IR の行) を `candidate_verdicts_1161.jsonl` と同じ形式で残す | **達成**。23 行を追記 (既存 31 行は不変、`git diff` は + 23 行のみ) |
| 分類表を再生成し範囲の未判定を 0 件にし、`audit_lsf_ssa_e2e.sh` の 7/7 で確認 | **達成**。範囲の未判定 0 (23/23 が確定)。e2e rc=0・7/7 (§6) |
| 脱落関数の和集合の更新を報告 | **達成**。69 → **77** (+8 関数、§3) |

- 全 site に根拠を付けた (推測で埋めた判定は無い)。判定の強さに差がある 2 件は §4 に明記した。
- 測定 commit (コードと結果の最後の変更): **`482ec43d`**。

## 2. 対象 23 site の分類

判定は subagent 6 本 (関数単位・並列・読み取りのみ) が機械語 (`ld98_dump.py` と同じ `audit_lsf.descend` で降下) と IR (`tools/m11/work/boot_final3.ll` の `function_<fn>` 本体) を突き合わせて出した。親は、判定の根拠行を `candidate_verdicts_1161.jsonl` に追記する前に、D15 同型の代表 1 件 (6c3700:6c3a63 の IR 267283-267294 のループ) を直接確認した。残りは subagent の引用行に依る (6c5930 を含め、§4 の注記を参照)。

| fn | site | 判定 | 機械語の消費者 | IR 側の対応 (boot_final3.ll 行) |
|---|---|---|---|---|
| 4fa3d0 | 4fa681 | OK_LOAD | 4fa690 → 4fa694 call 0x40faa0 (第1引数) | 181133 load → 181135 call function_40faa0 |
| 4fa3d0 | 4fa7aa | OK_LOAD | 4fa7b9 → 4fa7bd call 0x40faa0 (第1引数) | 181198 load → 181200 call function_40faa0 |
| 4fad10 | 4faf0b | OK_LOAD | 4faf1a → 4faf1e call 0x40faa0 (第1引数) | 181712 load → 181714 call function_40faa0 |
| 4fb780 | 4fb7d9 | OK_LOAD | 4fb7ec → 4fb7f0 call 0x4fb000 (第2引数) | 182351 load → 182358 call function_4fb000 |
| 5c00e0 | 5c013f | OK_LOAD | 5c0143 cmp・5c014e/5c015a 比較・5c017a call 0x439670 | 203721 load → 203722 icmp・203754-203758 call function_439670 |
| 5c0270 | 5c030d | OK_LOAD | 5c0311・5c0321 の読み出し → 5c032f store | 203869 store → 203864 reload → 203867 icmp・203872-203873 |
| 76e720 | 76e74f | OK_LOAD | 76e778 mov rax,[rbp+8] → ret (戻り値) | 287837・287846 store i64 -1 → 287858 load → 287859 ret |
| 775340 | 77545c | **TRUE_DROP** | 775657 → 775678 call 0x7747c0 (rcx を読む) | 290821 call function_7747c0() は引数 0 個。被呼出側 290584 の alloca に store 無し → 290589 load が undef |
| 775340 | 77593b | OK_LOAD | 7759f6・775a29 → float store (P 経由) | 291006 load P → 291069・291092 store (注 §4) |
| 815050 | 815220 | **TRUE_DROP** | 815227 cmp・815231 → 815238 mov rax,[rax-8] | 318485 load G (一段のみ) → 318486・318491・318493 が一段目の値を使う (二段目の deref 欠落) |
| 6c3700 | 6c3a63 | **TRUE_DROP** | 6c3a6b call [rdi+0x128] (第5引数) | 267283-267294 の内側ループはカウンタ加算のみ。間接 call 無し (D15) |
| 6c3700 | 6c3c78 | **TRUE_DROP** | 6c3c80 call [r13+0x128] (第5引数) | 267396-267407 のループはカウンタ更新のみ。間接 call 無し (D15) |
| 6c3d20 | 6c44bd | **TRUE_DROP** | 6c44c5 call [rsi+0x128] (第5引数) | 267830-267841 のループはカウンタ更新と減算のみ。間接 call 無し (D15) |
| 6c5930 | 6c6125 | **TRUE_DROP** | 6c612d call [rbx+0x128] (第5引数) | 対応ブロック無し (267973-268105)。根拠が IR の不在のみ (§4) |
| 1042d20 | 1043e2d | **TRUE_DROP** | 1043e34 call [rsi+0x188] (第5引数) | 14896-14897 の load 2 本は 14898 call function_12d6660 の引数に届かず未使用。間接 call 無し (D15) |
| c57a00 | c57e24 | OK_LOAD | c57e84・c57f6f mov ebx,[rbp+0x5c] (直後に add ebx,[rbp+0x58]) | 390006 load → 390040・390163 の add が同じ %220 を消費 |
| f3e050 | f3e0c2 | **TRUE_DROP** | f3e10b call [rax+0x38] (rdx=lea [rbp+0x3c] で slot を渡す) | 468265-468278 に call 無し。slot を渡す call は別分岐の 468262 function_a9ece0 のみ (D15) |
| f67400 | f67560 | OK_LOAD | f67573 call 0x661dc0 (第2引数) | 478296 load → 478306 zext → 478310 call function_661dc0 |
| 101d180 | 101d2b4 | OK_LOAD | 101d2c3 → call 0x40faa0 (第1引数) | 7458 load → 7460 call function_40faa0 (反復側 7478-7480 も同経路) |
| 101d180 | 101d423 | OK_LOAD | 101d432 → call 0x40faa0 (第1引数) | 7597 add → 7599 load → 7604 call function_40faa0 |
| 1221290 | 1221676 | OK_LOAD | 1221686・1221699 の比較 (12216c2) | 51268-51270 → 51274 icmp ugt → 51276 select → 51320 icmp slt (注 §4) |
| 127d420 | 127d881 | OK_LOAD | 127da8f → 127da95 [rsp+0x28] = call 0x6c9d30 の第6引数 | 64754 load → 64764 sext → 64932 trunc → 64933 call function_6c9d30 |
| 12f9730 | 12f9752 | **TRUE_DROP** | 12f975e・12f9842 mov ecx,[rsp+0x50] → cmp (比較) | 96779 `xor i64 0,0` → 96781 trunc で store 元が定数 0 に置換。96871 の比較に 0 が流入 |

- TRUE_DROP 9 件のうち、D15 同型 (間接 call の欠落) が 6 件 (6c3700 ×2・6c3d20・6c5930・1042d20・f3e050)、残り 3 件は §5 の別形。
- 機械語の `[rsp+0x20]` 系 (6c3700・6c3d20・6c5930・1042d20) は Windows x64 の第 5 引数領域で、消費者は後続の間接 call。TSV の後続読み出し 0 件はこの形の結果。

## 3. 分類表と脱落関数の和集合 (実測・`audit_lsf_ssa_e2e.sh` の 7/7 出力)

| 項目 | 前 (baseline・`b665b667`) | 後 (`482ec43d`) |
|---|---|---|
| spill 宛 unk site | 178 / 71 関数 | 178 / 71 関数 |
| status 未判定 / 確定 / 判定不能 | 120 / 51 / 7 | **97 / 74 / 7** (確定 +23) |
| verdict (candidate) TRUE_DROP / OK_LOAD / NO_CONSUMER / UNDETERMINED | 21 / 1 / 2 / 7 | **30 / 15 / 2 / 7** (+9 / +14) |
| 範囲 (19 関数) の未判定 | 23 | **0** (python で 23 行を照合: 全行が確定) |
| spill 宛の確定 TRUE_DROP 関数 | 18 | **26** |
| 脱落関数の和集合 (store DROP 51 ∪ spill TRUE_DROP) | 69 (drops_510.tsv) | **77** = 69 + 新規 8 |

- 新規 8 関数: `6c3700` `6c3d20` `6c5930` `775340` `815050` `f3e050` `1042d20` `12f9730`。`drops_510.tsv` (#510 の目視・動的の集計) は変更していない (`cmp` で一致)。和集合 77 は `spill_classify_1161.py` の [6] 行の数 (8) を 69 に加えた値。[5] 行は 510 の表だけから計算するため 69 のまま出る。
- 和集合は確定した TRUE_DROP (目視・候補) だけから作る。候補の未判定は含めない (`spill_classify_1161.py` の定義どおり)。

## 4. 判定の強さ (弱い根拠の注記)

- **6c5930:6c6125** (TRUE_DROP): 機械語では 6c6042 の jle から到達するが、IR の 267973-268105 にその領域の対応ブロックが無い。消費者と流入先が IR に無いことだけが根拠で、他の TRUE_DROP より弱い。
- **775340:77593b** (OK_LOAD): 値の経路 (spill → P → float store) は IR の 291006 load と一致する。ただし機械語のループ内の間接 call (7759bb) に対応する IR の call が無い。その call が `*X` を書き換えるなら、IR の再 load と機械語の値は一致しない。未確認。
- **76e720:76e74f** (OK_LOAD): IR では site の値が定数 `store i64 -1` に置き換わっている。機械語の値 (`[rbp],[rbp+4]` の dword 0xffffffff から組んだ qword -1) と一致するため OK_LOAD とした。定数化を別扱いにする方針なら再判定。
- **1221290:1221676** (OK_LOAD): 値の経路は一致する。判定外の付記として、機械語の比較は符号付き (jg) だが IR は `icmp ugt` と `zext → icmp slt` で符号扱いが一致しない (§5 の候補)。
- **ld98_dump.py の修正**: 76e720 の後続読み出し 0 件は、capstone が小さい変位を 10 進 (`[rbp + 8]`) で出すのに、照合が `0x8` 形式しか見ていなかったための取りこぼし。`(0x%x|%d)` に直し、TSV を再生成した (`ld98_consumers_2265.tsv` の 76e74f 行: 読み 0 → 1 (76e778)・書き 1 (76e774))。他の 22 行は変わらない。

## 5. 既知類型との対応・新規類型の候補 (DEFECTS 行案)

- D15 (既存): 6 site。`call qword ptr [reg+disp]` の IR 欠落。
- 815050:815220 (REPORT_510 §2 の型・D4 の変種): `mov rax,[rip+cell]; mov rax,[rax]` の二段 deref が IR で一段に潰れる。
- 775340:77545c (候補・DEFECTS 未登録): 間接 call の**引数**が欠落し、被呼出側が未初期化の alloca を読む (IR `call function_7747c0()` は引数 0 個)。
  - 行案: `call の引数欠落 | stage-0/IR 段で、間接 call の引数列から P 由来の値が落ち、被呼出側が undef を読む | 機械語 ↔ IR の call 引数数の不一致で検出可能`
- 12f9730:12f9752 (候補・DEFECTS 未登録): 引数由来の値が `xor i64 0,0` の定数 0 に置換される (機械語は二段参照)。
- 1221290:1221676 の符号比較の不一致 (候補): jg (符号) → IR の ugt・slt (符号・非符号の混在)。今回の分類の対象外。

## 6. 検証

- 測定: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (`ws-2265` worktree・branch `2265-ld98-spill-consumer-c2`・素材 `work-m11` と `work-liftdiff` を worktree 内に展開)。
  - 実行 1 (`b665b667`・分類前): rc=0・real 2m23.9s・7/7・未判定 120。
  - 実行 2 (分類の追記後・結果ファイル更新前): rc=1。step 7 の `cmp` が `spill178_1161.tsv` の 23 行 (未判定 → 確定) で旧 TSV と不一致。結果ファイルを $OUT の生成物で更新して実行 3 で再測定した。
  - 実行 3 (**`482ec43d`・最終測定**): rc=0・real 2m23.3s・user 2m22.0s・load average 0.21 (開始) → 0.93 (終了)・7/7。`drops_510.tsv` と `spill178_1161.tsv` は results/ と一致 (cmp OK)。
- ネガティブコントロール (step 6、NC0-NC7): 出力が実行 1 と実行 3 で md5 一致 (`a41b5345`)。分類の追加は step 6 の入力 (IR・機械語) を変えないため、出力が変わらないのは期待どおり。主な値: NC1 の 5c0270 alg2 は OK,OK、NC7 の 52a750 は alg3=SHALLOW・CELL_COLLAPSED。
- 差分 0 の証跡 (測定 commit から HEAD まで、コードと結果の差分が無い):
  `git diff --stat 482ec43d HEAD -- tools/m11/ldfix/ld98_dump.py tools/m11/ldfix/results` → 空 (出力 0 行)。
- 検査: `find tools/m11/ldfix -type f -size +20M` は 0 件。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| TRUE_DROP 9 site の IR 側修復 (間接 call 欠落 6・引数欠落 1・二段 deref 1・定数化 1) | 脱落集合 77 関数の lift 修復は本 issue の範囲外 (分類のみ) | 親 #2246 へ報告 (PM 判断。修復の子 issue は PM が決める) |
| 弱い根拠 2 件 (6c5930:6c6125 の IR 不在・775340:77593b の間接 call 7759bb の副作用) | 当該 site の判定の確度 | 親 #2246 へ報告。必要なら IR を再確認 |
| 1221290 の比較の符号扱い不一致 (jg / ugt・slt) | 判定外の別欠陥候補 | 親 #2246 へ報告 (DEFECTS 行案は §5) |
| ld98_dump 以外 (audit_lsf 系) の 10 進変位の取りこぼしの有無 | 未確認。同種の取りこぼしがあれば脱落集合が変わり得る | 親 #2246 へ報告 |
