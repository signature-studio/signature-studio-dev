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
- **事前測定** (base の jsonl・fvm 以外に equal/diff/wasm_trap 無し・候補 2 件以上の 73 件): fault base が引数由来に伝播できたのは 36 件 (arg0 34 / arg1 1 / arg2 1)。base が引数由来でない 42 件 (`rbx`・`rax` などの 2 段目以降の間接参照。`0x41a7c0` 系の 6 件を含む)、分岐で線形追跡を打ち切った 9 件、ret 断片 1 件。
- **測定 commit**: `85f5e93f7` (コードを変えた最後の commit)。base: `1f12b1b6d` (origin/main)。両方とも同一環境で `liftdiff_e2e.sh --m11-only` を 1 回ずつ実行 (base 189 s PASS・HEAD 197 s PASS・`LIFTDIFF_E2E PASS`)。
- **証跡**: `git diff 1f12b1b6d 85f5e93f7 -- tools/liftdiff` は `pe.py` の `fault_arg` 追加と `session.py` の `fvm_cand` の分岐追加の 2 ファイル (+39 行)。

| run | match / mismatch / unexec | fvm case (native_fault / both_fault / diff / hang) | fvm 関数数 | 所要 |
|---|---|---|---|---|
| base `1f12b1b6d` | 360 / 234 / 206 | 12 (2 / 7 / 2 / 1) | 12 | 189 s PASS |
| HEAD `85f5e93f7` | 360 / 235 / 205 | 41 (15 / 22 / 3 / 1) | 41 | 197 s PASS |

- **関数単位の verdict 変化**: 1 件 (`0x5c1030` unexec→mismatch)。fvm の `diff` (arg 0・`native_extra_call`) によるもので、LD-177 §12.1.2 で未切り分けとしていた件 (#4137 へ)。
- **fvm の outcome**: fvm case 41 件 (関数 41 件・各 1 case) の内訳は native_fault 15 / both_fault 22 / diff 3 / hang 1。equal / wasm_trap への遷移は 0 件。
- **非 fvm case の変化**: `fvm_transitions.py` で `EXISTING_PATTERN_CHANGED` は base のみ 14 関数。fvm の救済で増えた case の影響ではなく、既存 pattern の outcome の変化として記録する。

### 未達 (受入条件)

- 受入 2 (equal / wasm_trap への遷移): 0 件。fvm の救済は native 側が fault で落ちる case を増やしただけで、wasm 側と一致する case は作れていない。
- 受入 3 (既存 verdict の base 比): 関数単位で 1 件 (`0x5c1030`) のみ変化。揺らぎ判定 (base 同士の幅) は未実施 (同一 base の 2 回目を取っていない)。
- 残り 37 件 (多重のうち引数由来に伝播できない関数): 起票先 #4173 で継続 (本 PR で閉じない)。
