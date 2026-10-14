# REPORT #2438 — spill 宛 未判定 関数群 C 前半の残り 12 site の消費者分類 (LD-114)

親: #2264 (LD-97) / 上位: #1161 (LD-35)。前段の判定は `REPORT_2264.md` §8 (11 site)。本 REPORT は #2264 §8.3 で移管された残り 12 site (415610 の 1 site を含む) を扱う。

## 1. 測定

- 測定 commit: `dfc7968c` (`origin/main` (`3ef67b40`) を取り込んだ merge commit)。e2e が読むパスのコードを変えた最後の commit。判定データ追記と tsv 再生成は `72fd4a51` で行い、取り込み後の `dfc7968c` で e2e を再測定した。
- e2e: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (直列・並列数 1)。

| 実行 | commit | real | uptime load | 結果 |
|---|---|---|---|---|
| 判定追記時 | `72fd4a51` | 2m51.9s | 0.99 | rc=0・7/7 |
| PR 作成時 (merge 後) | `dfc7968c` | 2m1.2s | 0.65 → 0.97 | rc=0・7/7 |
| レビュー (`git archive dfc7968c` で再実行) | `dfc7968c` | 2m35.7s | 0.95 | rc=0・7/7 |
| 修正 run (worktree で `dfc7968c` を実行) | `dfc7968c` | 2m11.4s ※ | 0.30 → 0.96 | rc=0・7/7 |

※ 修正 run の real は、素材 tar の展開 2 本 (work-m11・work-liftdiff) を含む。`dfc7968c` の 3 run の real は 2m1.2s〜2m35.7s (n=3 の min–max)。

- いずれの run も `drops_510.tsv` と `spill178_1161.tsv` は results/ と `cmp` 一致。
- 分類表の集計 (tsv): 確定 83 / 判定不能 16 / 未判定 79。`REPORT_2264.md` §8 時点の 78 / 9 / 91 から、確定 +5・判定不能 +7・未判定 −12。
- `spill_classify_1161.py` の [5][6] は不変 (drops 和集合 69、spill 宛確定 TRUE_DROP 20 関数、drops_510 に無いのは 4120c0・41a5d0)。判定は tally に算入しない設計のまま。
- 素材: work-m11 / work-liftdiff をリポジトリ直下に `tar --zstd -xf` で展開 (gitignore 対象)。fl-win64 は `$RUNNER_TEMP/fl-win64` に展開し、PE 正本は `extracted/block00031_PE.bin`。

### 鮮度の確認 (WORKFLOW §6)

e2e が読むパス (12 本 + results 4 本) を `E2E_PATHS` とする。

- スクリプト 11 本: `tools/m11/ldfix/` の `audit_lsf_ssa_e2e.sh`・`negctl_510.sh`・`audit_lsf.py`・`audit_lsf_ssa.py`・`audit_lsf_disp.py`・`ldmach.py`・`ldmach_img.py`・`window_recount.py`・`dyn_xcheck.py`・`tally_510.py`・`spill_classify_1161.py`
- import 1 本: `tools/m11/lb_base.py` (`ldmach_img.py` が import)
- results 4 本: `tools/m11/ldfix/results/` の `manual_verdicts_510.jsonl`・`candidate_verdicts_1161.jsonl`・`drops_510.tsv`・`spill178_1161.tsv`

```sh
git diff --stat 72fd4a51 dfc7968c -- <E2E_PATHS>   # 出力 0 行 (取り込みで変わったのは E2E_PATHS の外のみ)
git diff --stat dfc7968c HEAD -- <E2E_PATHS>       # 出力 0 行 (HEAD は本 REPORT を含む docs commit)
```

`dfc7968c` の取り込みで `tools/m11/ldfix` に入った 10 ファイル (REPORT 3 本・スクリプト 5 本・results 2 本) は `E2E_PATHS` に含まれない。

## 2. 判定 (12 site)

機械語 (`audit_lsf.descend` で得た CFG 順の逆アセンブル) と IR (`boot_final3.ll` の該当関数) を突合した。詳細な根拠は `results/candidate_verdicts_1161.jsonl` の evidence。

| 関数 | site | 判定 | 要点 |
|---|---|---|---|
| 415610 | 415751 | OK_LOAD | 二段 deref (`%55`) が `[rbp+0x40]` へ。消費は byte 読み・再帰 call 第 2 引数で IR と一致。経路 (415683→415736) は実 load に依存 |
| 415c30 | 415d43 | OK_LOAD | 一段 deref (`%28`)。消費は byte 比較と call 41c0a0 |
| 415c30 | 415d87 | OK_LOAD | 一段 deref (`%53`)。消費は call 415c30・416230・418190 |
| 417b70 | 417c35 | OK_LOAD | 二段 deref (`%26`)。後続消費 9 箇所すべて `storemerge4.reload` と一致 |
| 41e490 | 41e513 | UNDETERMINED | deref は一致するが、head 大域の基準が不一致 (機械語 VA `0x15ec2e0` / IR `0x11ec2e0` = VA−0x400000) |
| 45a2a0 | 45a577 | OK_LOAD | 二段 deref (`%55`) → stack_var_-128 → call 448de0 の引数。前提は §4 |
| 45b170 | 45b1bf | UNDETERMINED | 二段 deref の arm は、型タグ読み `%1 = xor i64 0,0` を畳んだ後に到達不能。消費者の前に rbp を渡す call 45b0f0/45b120 の副作用が未確定 |
| 45c290 | 45c6dd | UNDETERMINED | 32bit deref と消費 (ret) は一致。ただし分岐述語の `%5` が `[arg1]` でなく `%rcx` alloca を読む |
| 45d0a0 | 45d570 | UNDETERMINED | deref・消費は一致。IR の entry 型タグ読み (45d0b5) が `xor i64 0,0` に落ち、畳んだ後はこの block に到達しない |
| 45d0a0 | 45d581 | UNDETERMINED | 同上 (別の型タグ arm 0x15) |
| 45d610 | 45d754 | UNDETERMINED | deref・消費は一致。経路選択の型タグ読み (45d641) が `trunc arg1 to i16` になり、arm の選択が機械語と一致しない |
| 45f560 | 45f938 | UNDETERMINED | deref は局所一致。IR の entry 型タグ読み (45f56c) が `xor i64 0,0` で、畳んだ後はこの block に到達しない |

集計: OK_LOAD 5 / UNDETERMINED 7 / TRUE_DROP 0 / NO_CONSUMER 0。

判定基準 (本 run で適用):

- OK_LOAD: 機械語の二段 deref 値が IR に同じ段数の deref として存在し、後続の消費が IR の対応命令と一致し、site の block が IR で entry から到達できる。
- UNDETERMINED: 上の条件のどれかを確定できない。「deref は存在するが、到達条件が上流の別の脱落に依存する」場合を含む。
- 到達性の確認 (本 fix run): 分岐条件を無視して IR の CFG を辿ると、45d570 の定義 block (`dec_label_pc_45d565`)・45d581 (`dec_label_pc_45d576`)・45f938 (`dec_label_pc_45f931`)・45b1bf の arm (`dec_label_pc_45b1b8`) はいずれも entry から到達可能。`xor` の定数 0 を畳んだ後に到達不能になるのは、型タグ分岐の条件が定数に畳まれるため。UNDETERMINED の判定はこの前提で変えていない。
- TRUE_DROP は、機械語で deref 後の値を使うのに IR にその load が無い場合に付ける。今回の 12 site には該当が無い。
- 推測で埋めた判定は無い。根拠が取れなかった site は UNDETERMINED のまま残した。

## 3. 観測 (判定の外)

- 入口の型タグ読みに `xor i64 0, 0` が当たる例: 415610 (`%2`、415657 `cmp byte[rax],0x16` が 0 になり、41565c 分岐が IR で死ぬ)、45b170 (`%1`)、45c290 (`%5` は別の alloca)、45d0a0 (`%3`、45d0b5)、45f560 (`%3`、45f56c)、45d610 (`%0 = trunc arg1`)。
- `boot_final3.ll` 全体では `= xor i64 0, 0` が 3886 行、3009 関数 (define 14827 件中)。全てが誤脱落とは限らない (レジスタ初期値の定数化を含む)。`docs/DEFECTS.md` の D22 (undef 由来の `xor` 0) と見かけは近いが、今回の例は入口の memory 読み (`movzx`/`cmp byte ptr [reg]`) で、D22 の F4 修復 (`ptrtoint %stack_var`) の対象外。件数の分類は未実施。
- 41e490: head 大域の参照基準 (VA と `VA−0x400000` の混在) が他の大域 load にもあるかは未確認。
- 417b70: 機械語 417dfa〜417e01 と 417e13〜417e1a の `[arg1]` deref が IR の `416db0`・`409c80` の引数に無い。spill 宛ではない別 site (後続の分類対象)。

### 新類型の DEFECTS 行案 (`docs/DEFECTS.md` 形式・未登録)

DEFECTS.md 本体の編集と登録は PM 判断。ID は PM が採番する (仮に D24 とする)。

- **層**: fe (機構は未確定)。**新旧**: 新規 (M11 / #2438 の分類中に観測)。
- **症状 (silent)**: 関数入口の型タグ読みが定数 0 になり、型タグ分岐の arm が IR で到達不能になる。その arm は定数畳み込み後に実行されない扱いになり、arm 内の load/store に対応する spill 宛の判定が UNDETERMINED に落ちる。実行結果への影響は未測定。
- **根本原因**: 未特定。入口の memory 読み (`movzx`/`cmp byte ptr [reg]`) が IR で `xor iN 0, 0` になる経路を再現していない。D22 (undef 由来) と違い、読みの値が undef でなく定数 0 として残る。
- **観測 (証拠)**: 上の 6 例 (415610・45b170・45c290・45d0a0×2・45f560・45d610)。`boot_final3.ll` で 3886 行・3009 関数。
- **検出信号 (案・未実装)**: IR の `%N = xor iW 0, 0` が型タグ分岐の条件に効き、同じ関数の機械語に `[reg]` の byte/word メモリ読みが 1 本以上ある。
- **修復 (案・未実装)**: 入口の型タグ読みを定数化せず load として残す。修復の要否は件数の分類後に PM が判断する。

## 4. 前提と再現

- 45a2a0 の前提: 45a593 の `call 446290` は `&[rbp+0x40]` を渡す。446290 は引数 rcx を `call 413060` に渡すのみで直接 store しないが、413060 の副作用は未確認。IR 側も同じ呼び出しを持つため、判定 (deref と消費の一致) には影響しないと判断した。
- 再現:

```sh
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh   # dfc7968c で rc=0・2m11.4s (素材展開を含む)・7/7 (§1)
```

- 機械語の逆アセンブルは `audit_lsf.descend` (PE 経路 `block00031_PE.bin`) で取得した。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| UNDETERMINED 7 site (41e490 の大域基準、45b170・45c290・45d0a0×2・45d610・45f560 の入口の型タグ読み脱落による到達条件) | spill 宛の判定が 12 中 7 件で確定しない。tally の和集合 69 は変えていない | #2253 (コメント追記・本 PR の 7 site) |
| 入口の memory 読みの `xor i64 0, 0` (新類型候補、3009 関数・§3 の DEFECTS 行案) | 45d0a0・45f560 は定数伝播後に到達不能で、関数全体の修復が前提になりうる。spill 以外の site にも影響しうる | #2253 (コメント追記)。DEFECTS.md への登録と件数の分類は PM 判断 |
| 41e490 の大域基準 (VA と VA−0x400000 の混在) が他の大域 load に広がるか | 未確認。41e490 の判定 (UNDETERMINED) の根拠を広げる | #2253 (コメント追記) |
| 417b70 の別 site (417dfa〜417e01・417e13〜417e1a の `[arg1]` deref が IR の引数に無い) | spill 宛ではない別 site。判定は未実施 | #1767 (LD-62・同じ関数 0x417b70 にコメント追記) |
| 45a2a0 の OK_LOAD の前提: `446290 → 413060` の副作用未確認 (§4) | deref と消費の一致は満たす。前提が崩れると消費者の値が変わりうる | #2253 (コメント追記) |
| 後半 23 site の分類 | 同上 | #2265 (LD-98・既存) |
