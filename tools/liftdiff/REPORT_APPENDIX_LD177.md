# 付録: liftdiff LD-177 (#3782) — fvm の候補多重と ret 断片の対象外化 — tools/liftdiff/

> **正本**: `tools/liftdiff/REPORT.md` §12 (要約)。本書は `REPORT_APPENDIX.md` §12.1.2 から分割移動した全文 (250 行上限・`docs/DOC_MAP.md` §1)。

## 12.1.2 LD-177 (#3782): fvm の候補多重と ret 断片の対象外化 (LD-23 残り)

- **問題の実測 (base `68c6cbb75`・sample:800)**: `fvm_candidates` が返す候補数の分布は、fvm 対象 206 関数のうち 0 件 123・1 件 10・2 件 7・3 件 10・5 件 21・6 件 1・7 件 10・8 件 24 (合計 206。2 件以上は 73 件)。候補が多重の関数は、どの引数が pointer か決まらないまま fvm case を走らせていた。
- **方式**: `session.fvm_cand` で次の 2 つを対象外にする。
  - `pe.Analyzer.is_ret_fragment`: entry が `add rsp,N; ret` だけの断片 (本体なし)。対象は `0x4096c0` の 1 件 (候補は 5 件あった。ret が stack の値を戻り先として pop し、rip=0xb で落ちる)。
  - 候補が 2 件以上: 1 つに決める根拠が fault addr に無いため、case を作らない。
  - 候補が 1 件 (10 件) と 0 件 (123 件) は従来どおり。`cases.py` (blob・args の生成) は変更していない (`git diff 68c6cbb75 HEAD -- tools/liftdiff/ldlib/cases.py` の出力は空)。
- **方式の選択**: issue は「deref 位置から引数を特定する」案を例示していた。本 PR は**多重なら捨てる**方式を採った。deref 位置の解析は、native の fault rip から引数レジスタへ逆に辿る必要があり、本件の範囲を超えるため。多重の関数は fvm 未実行のまま残る。救う方式は子 #4173 ([LD-198]) に分離した。
- **対象の内訳 (再計算)**: base `68c6cbb75` で fvm が走った 86 関数の内訳は、ret 断片 1 (`0x4096c0`) / 候補多重 73 / 候補 1 件 12。`cases.fvm_candidates` (引数の kinds と `'s'` の fault addr) を base の jsonl に当てて再計算した。ret 断片の判定は `Analyzer.is_ret_fragment` の規則 (`add rsp,N; ret`)。

### 測定

- **測定 commit**: `9e4bb57cc` (main 取り込み後の HEAD。`91b09de47` は main 取り込み、`9e4bb57cc` は分割と表の訂正)。base = `68c6cbb75` (main)。
- **証跡** (差分 0): `git diff 91b09de47 9e4bb57cc -- tools/liftdiff ':!tools/liftdiff/REPORT*'` の出力は本 PR の REPORT 分割だけ (コード 0)。
- **main 取り込みの影響**: `91b09de47` (main 取り込み) で `tools/liftdiff/ldlib/pe.py` (arity データフローの合流点の再処理。#3708) と `tools/liftdiff/rt/ld_native.c` (LD-171 の hw watch) が変わった。このため、取り込み前 (`2882d58c0`) の測定値はそのままでは現 HEAD の値とはみなさない。本節は取り込み後の HEAD で測り直した値だけを採る。

sample:800 (`liftdiff_e2e.sh --m11-only`、`--shards 12 --state auto`、2 回ずつ・同一環境で連続実行):

| run | match / mismatch / unexec | fvm case 数 (native_fault / both_fault / diff) | 所要 (e2e 全体) |
|---|---|---|---|
| base `68c6cbb75` 1 回目 | 360 / 234 / 206 | 437 (189 / 245 / 3)・86 関数 | 2m49s (load 4.00 → 2.39) |
| 現 HEAD `9e4bb57cc` 1 回目 | 360 / 233 / 207 | 12 (2 / 8 / 2)・12 関数 | 2m40s (load 4.57 → 1.95) |
| 現 HEAD `9e4bb57cc` 2 回目 | 360 / 233 / 207 | 12 (2 / 8 / 2)・12 関数 | 2m44s (load 4.86 → 3.00) |

- 所要と load は `time` と `uptime` の実測。e2e の PASS は各 run で `LIFTDIFF_E2E PASS`。
- **base 同士の揺らぎ**: base 1 回目 (360/234/206) と、#3782 の REPORT 初版の base 2 回 (361/233/206・360/234/206) の幅内。この PR の揺らぎは fvm と無関係。
- **base と head の関数単位遷移** (現 HEAD 2 回の jsonl を base 1 回目と比較。2 回とも同一):
  `match→match 360`・`mismatch→mismatch 233`・`unexec→unexec 206`・`mismatch→unexec 1` (`0x5c1030`)。遷移は 1 件だけで、残りは関数単位で不変。
- **`0x5c1030` の変化**: base では `fvm` case の arg 0 が `diff` (`calls.kind = native_extra_call`・native が `?vmslot3` を呼ぶ) で、この 1 件が mismatch の根拠だった。現 HEAD では候補多重 (8 件) のため fvm を走らせず、全 case が既存の結果のまま unexec になる。この diff の中身 (本物の欠陥か fvm の人工物か) は未切り分けで、子 #4174 ([LD-199]) に分離した。

### fvm の件数

- base: fvm case 437 件 (86 関数)。現 HEAD: fvm case 12 件 (12 関数)。
- 候補 1 件の 12 関数 (base で候補 1 件だった関数) は現 HEAD でも fvm が走る。fvm の結果は native_fault 2 / both_fault 8 / diff 2 (`tests/fvm_transitions.py`)。
- **equal / wasm_trap への遷移は 0 件のまま**。受入条件 (2) の「equal / wasm_trap への遷移」は未達。

### 未達 (受入条件)

- 受入 3 (既存 verdict の不変): 関数単位では `mismatch→unexec` が 1 件 (`0x5c1030`) で、「不変」とは言えない。この 1 件は意図した変化 (候補多重の除外) で、その切り分けは #4174 に分離した。それ以外の 800 件の関数単位 verdict は base と一致する。
- 候補多重 73 件の fvm 救済 (issue の例示案): 本 PR では採らない。起票先: #4173 ([LD-198])。

**対象外の関数一覧** (base で fvm が走った 86 関数のうち、対象外の 74 件 = ret 断片 1 + 候補多重 73):

- `ret_fragment` (1 件): `0x4096c0`
- `multi_candidate` (73 件、昇順): `0x418700 0x472530 0x479be0 0x47b4a0 0x47d460 0x4fb160 0x4fe190 0x50abe0 0x526d50 0x534860 0x534eb0 0x539e00 0x5c1030 0x5c7b70 0x646130 0x64fa70 0x64fc70 0x64ff10 0x675010 0x678460 0x681380 0x705a70 0x72e2d0 0x75a880 0x75b3e0 0x7948c0 0x808700 0x8cbe40 0x8e7080 0x905af0 0x91f320 0x93fbd0 0x940170 0x95bfc0 0x974e80 0xa96550 0xa96620 0xa9e4d0 0xb3e120 0xb413b0 0xc2f3a0 0xc3efe0 0xceeb70 0xd032e0 0xd291c0 0xd2b370 0xd2b5b0 0xd2b620 0xd2bb50 0xdbf550 0xe7d8e0 0xebbfb0 0xebc1a0 0xffeea0 0x10190a0 0x101dfe0 0x10263d0 0x10293b0 0x102b6c0 0x102b750 0x1064bd0 0x1064fc0 0x11e7860 0x11e7940 0x1267f30 0x126e4c0 0x12b5340 0x12b5450 0x12c93a0 0x12cef10 0x12f9ec0 0x1312080 0x132e7a0`

注: 対象外の判定は実装 (`session.fvm_cand`) の結果を jsonl から再計算した値。`fvm_skip` は関数 record (jsonl) には残らない (`session.py` が `rec['fvm_skip']` に入れるのは `_fvm_cases` の戻り値を `rec` に書いたときだけで、ret 断片・多重のどちらでも case は無いため jsonl の `fvm_skip` は全 800 件で未記録)。

**未解決・子 issue**:
- 候補多重 73 件の fvm を deref 位置から救う方式: 起票先 #4173 ([LD-198]・親 #3782)。
- `0x5c1030` の旧 fvm diff (arg 0 の `native_extra_call`) の切り分け: 起票先 #4174 ([LD-199]・親 #3782)。
