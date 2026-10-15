# 付録: liftdiff LD-177 (#3782) — fvm の候補多重と ret 断片の対象外化 — tools/liftdiff/

> **正本**: `tools/liftdiff/REPORT.md` §12 (要約)。本書は `REPORT_APPENDIX.md` §12.1.2 から分割移動した全文 (250 行上限・`docs/DOC_MAP.md` §1)。

## 12.1.2 LD-177 (#3782): fvm の候補多重と ret 断片の対象外化 (LD-23 残り)

- **問題の実測 (base = main `09d6e4b84`・sample:800)**: fvm 以外の case で判定した対象は 209 関数。`cases.fvm_candidates` の候補数の分布は 0 件 123・1 件 12・2 件 7・3 件 10・5 件 21・6 件 1・7 件 10・8 件 25 (合計 209)。候補 2 件以上は 74 件 (多重 73 + ret 断片 `0x4096c0` 1 件。ret 断片は候補が 5 件あった)。候補が多重の関数は、どの引数が pointer か決まらないまま fvm case を走らせていた。
- **方式**: `session.fvm_cand` で次の 2 つを対象外にする。
  - `pe.Analyzer.is_ret_fragment`: entry が `add rsp,N; ret` だけの断片 (本体なし)。対象は `0x4096c0` の 1 件 (候補は 5 件あった。ret が stack の値を戻り先として pop し、rip=0xb で落ちる)。
  - 候補が 2 件以上: 1 つに決める根拠が fault addr に無いため、case を作らない。
  - 候補が 1 件 (12 件) と 0 件 (123 件) は従来どおり。`cases.py` (blob・args の生成) は変更していない。
- **方式の選択**: issue は「deref 位置から引数を特定する」案を例示していた。本 PR は**多重なら捨てる**方式を採った。deref 位置の解析は、native の fault rip から引数レジスタへ逆に辿る必要があり、本件の範囲を超えるため。多重の関数は fvm 未実行のまま残る。救う方式は子 #4173 ([LD-198]) に分離した。

### 母集団と内訳 (再計算)

母集団は「fvm 以外の case で判定し、equal / diff / wasm_trap が無い関数」の 209 件。base で fvm が走ったのは候補 1 件以上の 86 件 (= 単一候補 12 + 多重 73 + ret 断片 1)。

| 区分 | 関数数 | 内訳 (関数の VA) | base (main) | 現 HEAD |
|---|---|---|---|---|
| 候補 0 件 | 123 | — | fvm 未実行 | fvm 未実行 |
| 候補 1 件 | 12 | `0x101e250 0x101ea80 0x1024830 0x132f6a0 0x410a50 0x450260 0x47d670 0x5c5500 0xdc0450 0xdc2130 0xe860d0 0xe8dce0` | fvm 実行 | fvm 実行 (12 件) |
| 候補 2 件以上 (多重) | 73 | 下の対象外一覧 | fvm 実行 | 対象外 (case を作らない) |
| ret 断片 | 1 | `0x4096c0` | fvm 実行 | 対象外 |
| 合計 | 209 | | | |

### 測定

- **測定 commit**: `f7d5abbfa` (現 HEAD のコード。`9e4bb57cc` 以降の変更は docs のみ)。
- **base**: `09d6e4b84` (main。現 HEAD が取り込んだ main と同一)。base と HEAD の差分は fvm の変更 (`tools/liftdiff/ldlib/pe.py` と `session.py`) だけ。
- **証跡**: `git diff 09d6e4b84 f7d5abbfa -- tools/liftdiff ':!tools/liftdiff/REPORT*'` は `pe.py` の `is_ret_fragment` 追加と `session.py` の `fvm_cand` 追加だけ (本 PR の変更)。

sample:800 (`liftdiff_e2e.sh --m11-only`、`--shards 12 --state auto`、2 回ずつ・同一環境で連続実行。4 コアの runner):

| run | match / mismatch / unexec | fvm case 数 (native_fault / both_fault / diff) | fvm 関数数 | 所要 (e2e 全体) | load (uptime 1 分値 開始 → 終了) |
|---|---|---|---|---|---|
| base `09d6e4b84` 1 回目 | 360 / 234 / 206 | 437 (189 / 245 / 3) | 86 | 177 s (PASS) | 0.86 → 4.61 |
| base `09d6e4b84` 2 回目 | 360 / 234 / 206 | 437 (189 / 245 / 3) | 86 | 177 s (PASS) | 2.00 → 5.17 |
| 現 HEAD `f7d5abbfa` 1 回目 | 360 / 233 / 207 | 12 (2 / 8 / 2) | 12 | 177 s (PASS) | 4.37 → 5.49 |
| 現 HEAD `f7d5abbfa` 2 回目 | 360 / 233 / 207 | 12 (2 / 8 / 2) | 12 | 176 s (PASS) | 3.93 → 4.40 |

- e2e の PASS は各 run で `LIFTDIFF_E2E PASS`。所要は shell の経過秒数。load は `uptime` の 1 分値。
- **base 同士・HEAD 同士の揺らぎ**: 関数単位の verdict は、base の 2 回・HEAD の 2 回で各々完全に一致した (差 0)。
- **base と HEAD の関数単位遷移** (2 回とも同一): `match→match 360`・`mismatch→mismatch 233`・`unexec→unexec 206`・`mismatch→unexec 1` (`0x5c1030`)。遷移は 1 件だけで、残りは関数単位で不変。
- **`0x5c1030` の変化**: base では `fvm` case の arg 0 が `diff` (`calls.kind = native_extra_call`・native が `?vmslot3` を呼ぶ) で、この 1 件が mismatch の根拠だった。現 HEAD では候補多重 (8 件) のため fvm を走らせず、全 case が既存の結果のまま unexec になる。この diff の中身 (本物の欠陥か fvm の人工物か) は未切り分けで、既存の子 #4137 ([LD-194]・受入 3 の原文移管先) で扱う。
- **fvm の outcome 内訳 (再計算)**: base は native_fault 189 / both_fault 245 / diff 3。現 HEAD は native_fault 2 / both_fault 8 / diff 2。equal / wasm_trap への遷移は 0 件のまま。

### fvm の件数

- base: fvm case 437 件 (86 関数)。現 HEAD: fvm case 12 件 (12 関数)。差は候補多重 73 関数と ret 断片 1 関数の対象外化による。
- 候補 1 件の 12 関数は現 HEAD でも fvm が走る。fvm の結果は native_fault 2 / both_fault 8 / diff 2 (`tests/fvm_transitions.py`)。
- 受入条件 (2) の「equal / wasm_trap への遷移」は未達 (遷移 0 件)。

### 未達 (受入条件)

- 候補多重 73 件の fvm 救済 (issue の例示案): 本 PR では採らない。起票先: #4173 ([LD-198])。
- `0x5c1030` の verdict 変化 (mismatch→unexec 1 件) の切り分け: 本 PR の範囲外。起票先: #4137 ([LD-194]・#3782 の受入 3 の移管先)。#4174 ([LD-199]) も同じ切り分けを扱う。#4137 と内容が重なるため、どちらに残すかは PM が決める。

**対象外の関数一覧** (base で fvm が走った 86 関数のうち、対象外の 74 件 = ret 断片 1 + 候補多重 73):

- `ret_fragment` (1 件): `0x4096c0`
- `multi_candidate` (73 件、昇順): `0x418700 0x472530 0x479be0 0x47b4a0 0x47d460 0x4fb160 0x4fe190 0x50abe0 0x526d50 0x534860 0x534eb0 0x539e00 0x5c1030 0x5c7b70 0x646130 0x64fa70 0x64fc70 0x64ff10 0x675010 0x678460 0x681380 0x705a70 0x72e2d0 0x75a880 0x75b3e0 0x7948c0 0x808700 0x8cbe40 0x8e7080 0x905af0 0x91f320 0x93fbd0 0x940170 0x95bfc0 0x974e80 0xa96550 0xa96620 0xa9e4d0 0xb3e120 0xb413b0 0xc2f3a0 0xc3efe0 0xceeb70 0xd032e0 0xd291c0 0xd2b370 0xd2b5b0 0xd2b620 0xd2bb50 0xdbf550 0xe7d8e0 0xebbfb0 0xebc1a0 0xffeea0 0x10190a0 0x101dfe0 0x10263d0 0x10293b0 0x102b6c0 0x102b750 0x1064bd0 0x1064fc0 0x11e7860 0x11e7940 0x1267f30 0x126e4c0 0x12b5340 0x12b5450 0x12c93a0 0x12cef10 0x12f9ec0 0x1312080 0x132e7a0`

注: 対象外の判定は実装 (`session.fvm_cand`) の規則を、base の jsonl (fvm 以外の case) に当てて再計算した値。`session.py` の `rec['fvm_skip']` は書き出し経路 `liftdiff.py` の `make_record` が捨てるため、jsonl には残らない。

**未解決・子 issue**:
- 候補多重 73 件の fvm を deref 位置から救う方式: 起票先 #4173 ([LD-198]・親 #3782)。
- `0x5c1030` の旧 fvm diff (arg 0 の `native_extra_call`・native が `?vmslot3` を呼ぶ) の切り分け: 起票先 #4137 ([LD-194]・#3782 の受入 3 の移管先)。

## 12.1.3 LD-198 (#4173): 多重候補の関数を fault base の引数伝播で救う

- **方式**: `pe.Analyzer.fault_arg(va, rip)`。fault rip の命令のメモリ base を、entry から rip 直前まで線形に走査した mov 伝播 (rcx/rdx/r8/r9 の引数由来を追跡。call で全消去、分岐・ret を跨ぐと None) で引数 index に寄せる。`session.fvm_cand` は候補が 2 件以上のとき、その引数が候補に含まれれば候補を 1 つに決めて case を作る。決まらなければ従来どおり `multi_candidate` で対象外。`cases.py` (blob・args) は変更していない。
- **修正 (commit `1b53c5b86`)**: `fault_arg` は (a) 3000 命令で打ち切ったら `None`、(b) 64bit の reg-reg `mov` 以外で書かれた族 (明示 dst・capstone の暗黙 write・`cmpxchg` の暗黙 rax・部分書き込み) を全て `prov` から外す。
- **多重候補の内訳 (修正後 `fault_arg`・測定 HEAD `d8d474ab8` の実測)**: 母集団は fvm 以外に equal/diff/wasm_trap 無し・`s` の fault あり・候補 2 件以上の 73 件。表の値は再現コマンドの出力そのもの。

  | 分類 | 件数 | 内容 |
  |---|---|---|
  | resolved | 29 | fault base が引数 index に伝播し、その index が候補に含まれる (fvm 救済の対象) |
  | arg_not_candidate | 3 | 伝播できたが、その引数が候補外 |
  | unresolved_base_not_arg | 32 | 線形追跡で最後まで引数由来でない |
  | unresolved_jump_before_rip | 6 | rip より前で分岐を跨いだ |
  | unresolved_ret_before_rip | 2 | rip より前で ret を跨いだ |
  | ret_fragment | 1 | ret 断片 (`0x4096c0`) |
  | 合計 | 73 | |

  合計 73 = 29 + 3 + 32 + 6 + 2 + 1。
- **母集団の入力**: `tools/liftdiff/work/m11/batch_sample_800.jsonl` (801 行・fvm case 42 件。gitignore のため commit しない・素材には含まれない)。HEAD `c592c0e47` (コード差分 0 の `258eb9fa6` と同じ code) で `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/liftdiff/liftdiff_e2e.sh --m11-only` を実行して生成した (195 秒・LIFTDIFF_E2E PASS)。sha256 `a5cecab28791900129db97acbd2c81302a31d8da175a8c2734fa9f4ddaf8f5a5`。素材 `work-liftdiff` の `batch_sample_800.jsonl` (sha `b219553f…`・fvm 0 件) は fvm を通していない古い版で、表の根拠にしない。以前 REPORT に書いた sha `5506d464…` は今回の再生成と一致しなかったため、撤回する。
- **再現**: 上記の e2e で jsonl を作った後、`FL_WIN64_DIR=<展開先> python3 tools/liftdiff/ld198_recount.py tools/liftdiff/work/m11/batch_sample_800.jsonl`。出力は `合計: 73` (resolved 29 / arg_not_candidate 3 / unresolved_base_not_arg 32 / unresolved_jump_before_rip 6 / unresolved_ret_before_rip 2 / ret_fragment 1)。VA 一覧は `VA <分類>:` 行に出る。
- **古い artifact 由来の 88 件**: `work-liftdiff` の artifact の `batch_sample_800.jsonl` (sha256 `b219553f…`・fvm case 0 件) は fvm 起動を通していない。その母集団の多重候補は 88 件 (resolved 32・候補外 4・base 非 arg 42・分岐 7・ret 跨ぎ 2・ret 断片 1) で、修正前の古い値。現在の表 (73) とは別物。
- **88 と 73 の差 15 件**: 古い母集団 (`b219553f…`) にだけある多重候補 15 件 (`0x102b430 0x11e7860 0x526f70 0x539670 0x623840 0x6682b0 0x813a70 0x8ce510 0x926f10 0x93e920 0x9773f0 0x97e460 0xcf0a90 0xec3190 0xff5ec0`) は、HEAD の jsonl で fvm 以外の case の outcome が変わったため、多重候補の条件 (候補 2 件以上・`s` の fault あり・fvm 以外に equal / diff / wasm_trap が無い) を外れた。HEAD の jsonl での除外理由 (fvm 以外の case で実測): equal / diff / wasm_trap が現れて除外 11 件 (wasm_trap 7・equal 3・diff 1)、`s` の fault が無くて除外 4 件 (`0x623840 0x93e920 0x11e7860 0xff5ec0`)。古い母集団では 15 件とも verdict `unexec`。fvm 救済の影響ではない (fvm 救済は `s` の fault がある多重候補にだけ作用する)。
- **測定 commit**: `d8d474ab8` (コードを変えた最後の commit)。再測定の HEAD は `258eb9fa6` と現 HEAD `c592c0e47` (表の最終行)。コード差分 (`git diff --stat d8d474ab8 258eb9fa6 -- tools/liftdiff/ldlib tools/liftdiff/ld198_recount.py tools/liftdiff/liftdiff.py tools/liftdiff/liftdiff_e2e.sh`) の実出力は空。
- **差分証跡** (WORKFLOW §6): 測定 commit `c592c0e47` (今回の再測定の HEAD) と本 PR の code 範囲の差分は、`git diff --stat 258eb9fa6 c592c0e47 -- tools/liftdiff/ldlib tools/liftdiff/ld198_recount.py tools/liftdiff/liftdiff.py tools/liftdiff/liftdiff_e2e.sh` の実出力が空。ただし e2e がビルドする `tools/liftdiff/rt/ld_native.c` は main 取り込みで `55 insertions / 2 deletions` 変わっており、上の範囲には入らない。このため再測定の HEAD を `c592c0e47` に置き、fvm の outcome は `258eb9fa6` の値から変わった (下の表)。変化が `ld_native.c` 由来か実行の揺らぎかは未切り分け。
- **fvm 12 → 42 (+30) の説明**: base の fvm は 12 関数 (native_fault 2 / both_fault 8 / diff 2)。HEAD `258eb9fa6` は 42 関数 (native_fault 15 / both_fault 24 / diff 3 / hang 0)、現 HEAD `c592c0e47` は 42 関数 (native_fault 15 / both_fault 23 / diff 3 / hang 1。hang は `0x47d670`・候補 1 件の fvm)。新規 fvm 30 件は `0x10263d0 0x10293b0 0x102b6c0 0x102b750 0x11e7940 0x126e4c0 0x472530 0x47d460 0x4fb160 0x534eb0 0x539e00 0x5c1030 0x64fa70 0x64fc70 0x675010 0x678460 0x681380 0x808700 0x8cbe40 0x8e7080 0x905af0 0xa96550 0xa96620 0xc3efe0 0xd2b370 0xd2b5b0 0xd2b620 0xd2bb50 0xebbfb0 0xebc1a0`。入力 (sha `a5cecab2…`・現 HEAD `c592c0e47` の再生成) の fvm 42 件は、多重候補 (recount の 73) に入らない 12 関数 (`0x101e250 0x101ea80 0x1024830 0x132f6a0 0x410a50 0x450260 0x47d670 0x5c5500 0xdc0450 0xdc2130 0xe860d0 0xe8dce0`) と、多重候補から fvm が走った 30 件に分かれる。後者 30 件 = resolved 29 件 + `0x808700`。`0x808700` は recount では ret 跨ぎ (`unresolved_ret_before_rip`) に分類されるが、session の `_fault_base_arg` 経路で fvm が走った (outcome は native_fault)。recount (`fault_arg` のみ) と session (`_fault_base_arg` を含む) の分類は一致しない。base の jsonl は保存していないため、base の fvm 12 関数との VA 一致は本ラウンドでは未検証 (前回測定の記録のみ)。
- **測定**: base `1f12b1b6d` と HEAD `d8d474ab8` で `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/liftdiff/liftdiff_e2e.sh --m11-only` を 1 回ずつ、同一 runner で連続実行 (base は detached worktree `$RUNNER_TEMP/base_1f12b1b6d`)。素材 `fl-win64`・`work-m11`・`work-liftdiff` は `$ARTIFACTS_DIR` から展開。emsdk は pin 6.0.12 を上流から入れた ([EMSDK]・素材 `toolchain-emsdk` は本 run に無い)。

| run | commit | 所要 (経過秒) | load (uptime 1 分値 開始 → 終了) | match / mismatch / unexec | fvm 関数数 (= fvm case 数) | fvm outcome (native_fault / both_fault / diff / hang) |
|---|---|---|---|---|---|---|
| base | `1f12b1b6d` | 191 PASS | 2.44 → 5.99 | 360 / 234 / 206 (800 関数) | 12 | 2 / 8 / 2 / 0 |
| HEAD | `d8d474ab8` | 205 PASS | 1.10 → 4.39 | 360 / 235 / 206 (801 行) | 42 | 15 / 24 / 3 / 0 |
| HEAD 再測定 | `258eb9fa6` | 199 PASS | — → 4.93 | 360 / 235 / 206 (801 行) | 42 | 15 / 24 / 3 / 0 |
| HEAD 再測定 (現 HEAD) | `c592c0e47` | 195 PASS | — (`tools/liftdiff/work/m11/` 再生成) | 360 / 235 / 206 (801 行) | 42 | 15 / 23 / 3 / 1 |

- **関数単位の verdict 変化**: base と HEAD の 800 関数の共通集合で、verdict の遷移は 0 件 (`0x5c1030` は base・HEAD とも unexec。`fvm_held` で据え置き)。HEAD の jsonl には `0x691dd0` (mismatch・`callee_divergence`) が 1 件多い。これは `sample:N` の抽出に LD-225 (#4561) の `OBJ_PATTERNS` VA が加わったためで、fvm を含まず、本 PR の変更とは無関係。
- **fvm の outcome**: `258eb9fa6` は native_fault 15 / both_fault 24 / diff 3 / hang 0、現 HEAD `c592c0e47` は native_fault 15 / both_fault 23 / diff 3 / hang 1 (計 42)。どちらも equal / wasm_trap への遷移は 0 件。
- **注**: `ld198_recount.py` の分類は、`258eb9fa6` の e2e が作った jsonl で上記の値になる (`d8d474ab8` の測定と同じ)。`e1efecc2f` 時点の値 (resolved 29 / unresolved_base_not_arg 33 / jump 5) とは一部違うため、旧値は置き換える。
- **非 fvm case の変化**: 未測定。`fvm_transitions.py` の再実行は本 PR では行っていない。

### 未達 (受入条件)

- 受入 2 (equal / wasm_trap への遷移): 0 件。fvm の救済は native 側が fault で落ちる case を増やしただけで、wasm 側と一致する case は作れていない。
- 受入 3 (既存 verdict の base 比): 関数単位で 1 件 (`0x5c1030`) のみ変化。揺らぎ判定 (base 同士の幅) は未実施 (同一 base の 2 回目を取っていない)。
- 残り 44 件 (多重 73 − resolved 29。候補外 3・引数由来に伝播できない 40 (base 非 arg 32 + 分岐 6 + ret 跨ぎ 2)・ret 断片 1): 起票先 #4173 で継続 (本 PR で閉じない)。

## 12.1.3 LD-195 (#4139): 候補多重の fvm を fault base レジスタ値で一意化する (LD-177 の残り・部分達成)

**結論**: 候補多重 73 関数のうち 13 関数で fvm case が走るようになったが、equal / wasm_trap への遷移は 0 件。受入 1 の「救う」は未達 (残りは #4173 (LD-198) へ)。

**方式**: 's' の native fault 命令 (rip) のメモリ base レジスタを capstone で逆アセンブルし、fault detail の同レジスタ値が候補引数 `SMALL[i]` とちょうど 1 つだけ一致すれば、その引数を pointer 候補にする (`session.fvm_cand` → `_fault_base_arg`)。一致が無い・複数なら従来どおり `multi_candidate` で対象外。既存 pattern の blob・args と、1 件候補の挙動は変えない。

**採らなかった案**: fault 命令の base が引数レジスタ (rcx/rdx/r8/r9) かで決める案。候補多重 73 件の probe では base が rcx 21・rdx 3・r8 1 の 25 件しか覆えず、rbx 27・rax 16・rdi 5 (引数ではない) が多数を占めたため不採用。

**probe (73 関数の 's' native fault)**: base レジスタ値が候補と一致 51 件 (うち fvm 対象になった 13 件)・不一致 22 件。不一致は `rep movsq` (rdi) など base が引数由来でない形。

**候補多重 73 件の内訳 (算術)**: 73 = fvm 実行 13 + 非対象 60。非対象 60 = base 不一致 22 + base 一致で fvm 非対象 38。

**38 件の理由は未計測** (本 run では確定できない)。sample:800 の jsonl (関数ごとの `s` fault) が `tools/liftdiff/results` に無く、`work-m11` 素材も無いため、probe と `fvm_cand` を再計算できなかった。考えられる理由 (未検証):
- (a) probe は「候補値と一致」で数えたが、`_fault_base_arg` は「ちょうど 1 件一致」を要求するため、一致が 2 件以上で `multi_candidate` になった。
- (b) base レジスタが `fault.detail` に無い (r9・r10〜r15。m2)。
- (c) HEAD の run で `s` が native_fault にならず fault が無かった (run 間の揺らぎ)。

どれが件数を占めるかは未確定。切り分けは #4173 (LD-198) で行う。

**sample:800 (`liftdiff_e2e.sh --m11-only`、`--shards 12 --state auto`、4 コアの runner、2 回ずつ)**。以下は LD-195 当時 (`d96bda5fd`・`80e066053`) の過去測定の記録。現 HEAD の値は上の LD-198 節の表を正とする:

| run | commit | match / mismatch / unexec | fvm case (native_fault / both_fault / diff / hang) | fvm 関数数 | e2e |
|---|---|---|---|---|---|
| base 1 回目 | `1f12b1b6d` (main) | 360 / 234 / 206 | 12 (2 / 8 / 2 / 0) | 12 | 192 s PASS |
| base 2 回目 | `1f12b1b6d` | 360 / 234 / 206 | 12 | 12 | PASS |
| HEAD 1 回目 | `d96bda5fd` | 360 / 235 / 205 | 25 (12 / 10 / 3 / 0) | 25 | 192 s PASS |
| HEAD 2 回目 | `d96bda5fd` | 360 / 235 / 205 | 25 (12 / 9 / 3 / 1) | 25 | PASS |

- base → HEAD の関数単位遷移 (2 回とも同一): `unexec→mismatch 1` (`0x5c1030`)・他は不変。
- `0x5c1030`: fvm arg 0 が `diff` (`calls.kind = native_extra_call`・native が `?vmslot3` を呼ぶ)。LD-177 §12.1.2 で未切り分けと記録した件と同じ。この 1 件が mismatch として再び見える。本物の欠陥か fvm の人工物かは #4137 (LD-194) で扱う。
- **揺らぎ**: 関数単位の verdict は base 同士・HEAD 同士とも不変 (0 件)。既存 pattern の outcome (fvm 以外) は base 同士 4 関数・HEAD 同士 7 関数で変わり、コード由来ではない (native の fault/hang の揺らぎ)。
- **fvm 側の揺らぎ**: HEAD 1 回目は fvm case 25 件 (native_fault 12 / both_fault 10 / diff 3 / hang 0)、2 回目は 25 件 (12 / 9 / 3 / 1)。2 回目で both_fault → hang が 1 件出た。verdict は両方 235 / 205 で同じ。
- **候補多重 73 件のうち fvm が走った 13 件の outcome**: HEAD 1 回目は native_fault 10・both_fault 2・diff 1・hang 0、2 回目は native_fault 10・both_fault 1・diff 1・hang 1。全 fvm case 合計から単一候補 12 件を引いた導出値で、単一候補の outcome は base (2 / 8 / 2 / 0) と同じと仮定した。equal / wasm_trap は 0。
- **2 回目の所要**: 未計測 (表の e2e 列は PASS のみ)。
- **m1 (既知の限界)**: `_fault_base_arg` は、base レジスタの値が `SMALL[i]` (3〜17 の奇数) と偶然一致する場合 (カウンタ等) を区別できない。
- **m2**: `fault.detail` に載らないレジスタ (r9・r10〜r15) が base の場合は `None` (対象外) になる。件数は未計測 (上記 38 件の理由 (b) に含まれ得る)。

**未達と起票先**: 残りの候補多重 60 件 (fvm 非対象。内訳 38 件の理由は未計測) と、equal / wasm_trap への遷移の成立は #4173 (LD-198)。`0x5c1030` の切り分けは #4137 (LD-194)。

**`0x5c1030` の据え置き (PM 判断 R7・LD-196、適用済み)**: fvm の `native_extra_call` 系 diff を持つ `0x5c1030` だけ、mismatch にせず unexec のまま据え置く (`session.FVM_HOLD_VAS`・`fvm_held` を `classify.verdict` で除外)。fvm の件数の増加 (12 → 25) は残す。

- 実装の範囲は `0x5c1030` の 1 件。fvm の `native_extra_call` diff を持つ関数は sample:800 にほかに `0x1024830`・`0x132f6a0` の 2 件あり、main でも mismatch (保存 verdict) のため、規則を一般化すると main の数値が変わる。よって一般化せず関数アドレス指定にした。
- 据え置き規則を一般化する案 (`native_extra_call` 全件を据え置く) は mismatch 232 になり、PM 判断の既定案 (234) と合わない。採らない。
- `classify.verdict` は `fvm_held` の case を数えない (`fvm_held` は fvm の diff にだけ付く)。

**測定 (HEAD `80e066053`・`liftdiff_e2e.sh --m11-only`・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`・素材 `work-m11` `work-liftdiff` を展開済み)**:

| run | commit | match / mismatch / unexec | fvm case (native_fault / both_fault / diff) | e2e | 所要 (`time` 実測) |
|---|---|---|---|---|---|
| main 再測定 | `1f12b1b6d` | 360 / 234 / 206 | 12 | PASS | 182 s |
| HEAD 1 回目 | `80e066053` | 360 / 234 / 206 | 25 (12 / 10 / 3) | PASS | 179 s |
| HEAD 2 回目 | `80e066053` | 360 / 234 / 206 | 25 | PASS | 182 s |

- 保存された verdict (jsonl の `verdict`) で main と HEAD を関数単位に突き合わせると、遷移 0 件 (match 360・mismatch 234・unexec 206 が一致)。
- 注: `verdict()` を main の jsonl の `cases` に当て直すと `0x5c1030` が mismatch に見える (235)。main の実行時の保存 verdict は unexec なので、main の値は 234 が正しい。当て直しは fvm の diff を含んだ cases を見るため、保存値と一致しない。
- 2 回の mismatch 集合は同一 (差 0)。
