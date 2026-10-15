# 付録: liftdiff LD-177 (#3782) — fvm の候補多重と ret 断片の対象外化 — tools/liftdiff/

> **正本**: `tools/liftdiff/REPORT.md` §12 (要約)。本書は `REPORT_APPENDIX.md` §12.1.2 から分割移動した全文 (250 行上限・`docs/DOC_MAP.md` §1)。

## 12.1.2 LD-177 (#3782): fvm の候補多重と ret 断片の対象外化 (LD-23 残り)

- **問題の実測 (base `68c6cbb75`・sample:800)**: `fvm_candidates` が返す候補数の分布は、fvm 対象 206 関数のうち 0 件 123・1 件 10・2 件 7・3 件 10・5 件 21・6 件 1・7 件 10・8 件 24 (合計 206。2 件以上は 73 件)。候補が多重の関数は、どの引数が pointer か決まらないまま fvm case を走らせていた。
- **方式**: `session.fvm_cand` で次の 2 つを対象外にする。
  - `pe.Analyzer.is_ret_fragment`: entry が `add rsp,N; ret` だけの断片 (本体なし)。対象は `0x4096c0` の 1 件 (候補は 5 件あった。ret が stack の値を戻り先として pop し、rip=0xb で落ちる)。
  - 候補が 2 件以上: 1 つに決める根拠が fault addr に無いため、case を作らない。base で fvm が走っていた 86 関数の内訳は、ret 断片 1 / 候補多重 73 / 候補 1 件 12。
  - 候補が 1 件 (10 件) と 0 件 (123 件) は従来どおり。`cases.py` (blob・args の生成) は変更していない (`git diff 68c6cbb75 HEAD -- tools/liftdiff/ldlib/cases.py` の出力は空)。
  - 対象外の理由は関数ごとに `rec['fvm_skip']` (`ret_fragment` / `multi_candidate`) に残す。
- **方式の選択**: issue は「deref 位置から引数を特定する」案を例示していた。本 PR は**多重なら捨てる**方式を採った。deref 位置の解析は、native の fault rip から引数レジスタへ逆に辿る必要があり、本件の範囲を超えるため。多重の関数は今後も fvm 未実行のまま残る (件数は下表)。
- **測定 commit**: `2882d58c0` (コードを変えた最後の commit)。base = `68c6cbb75`。
- **証跡** (差分 0): `git diff 2882d58c0 HEAD -- tools/liftdiff ':!tools/liftdiff/REPORT*'` の出力は空 (本節の追記は REPORT のみ)。

sample:800 (`liftdiff_e2e.sh --m11-only`、`--shards 12 --state auto`、同一 worktree で連続実行):

| run | match / mismatch / unexec | fvm case 数 (native_fault / both_fault / diff / hang) | 所要 (batch) |
|---|---|---|---|
| base `68c6cbb75` 1 回目 | 361 / 233 / 206 | 437 (189 / 245 / 3 / 0) | 189 s (e2e 全体・date 実測・load 5.98) |
| base `68c6cbb75` 2 回目 | 360 / 234 / 206 | 437 | 188 s (load 6.30) |
| 新 `2882d58c0` 1 回目 | 360 / 233 / 207 | 12 (2 / 7 / 2 / 1) | 186 s (load 5.67) |
| 新 `2882d58c0` 2 回目 | 360 / 233 / 207 | 12 | 183 s (load 5.51) |

- **base 同士の揺らぎ**: `0x959a40` が base 1 回目 match・2 回目 mismatch (既存 pattern `p1`・`pall`・`qall` の outcome が equal↔diff で揺れる。fvm は関与しない)。verdict の揺らぎは 1 件、case の揺らぎは 5 関数。
- **base と新の遷移** (2 回ずつ比較): `0x5c1030` が mismatch→unexec (両組で再現)。これは意図した変化で、旧 fvm の arg 0 の diff が根拠の 1 件 (候補多重の関数)。`0x959a40` の match→mismatch は base 側の揺らぎと同じ方向で、新側の 2 回とも mismatch。
- **判定 (受入条件 3)**: 関数単位の verdict 変化は揺らぎ幅 (base 同士で 1 件) の内側。ただし **`0x5c1030` の mismatch→unexec は意図した変化**で、「既存 verdict 不変」の厳密な意味では不変ではない。この 1 件は本 PR の受入条件の対象外として明記する。
- **fvm の件数**: 437 → 12。新側の fvm 対象 12 関数は、base で候補 1 件だった関数 (10 件 + `0x1024830`・`0x132f6a0` の 2 件 = 計 12 件) と一致する。候補多重の関数 (base) の fvm は 0 件。equal は 0 件 (従来と同じ)。wasm_trap は 0 件。
- **未達**: fvm の equal / wasm_trap への遷移は 0 件のまま。受入条件 (2) の対象一覧は本節で記録した (`fvm_skip` 理由と関数 VA は `tools/liftdiff/work/m11/batch_sample_800.jsonl` の `fvm_skip`。work は gitignore のため、対象一覧は下記に書く)。

**対象外の関数一覧** (base で fvm が走っていた 86 関数のうち対象外になった 74 件。全件は `cases.fvm_candidates` と `Analyzer.is_ret_fragment` を base の jsonl に当てて再計算できる):

- `ret_fragment` (1 件): `0x4096c0` (`add rsp,0x28; ret`)
- `multi_candidate` (73 件、昇順): `0x418700 0x472530 0x479be0 0x47b4a0 0x47d460 0x4fb160 0x4fe190 0x50abe0 0x526d50 0x534860 0x534eb0 0x539e00 0x5c1030 0x5c7b70 0x646130 0x64fa70 0x64fc70 0x64ff10 0x675010 0x678460 0x681380 0x705a70 0x72e2d0 0x75a880 0x75b3e0 0x7948c0 0x808700 0x8cbe40 0x8e7080 0x905af0 0x91f320 0x93fbd0 0x940170 0x95bfc0 0x974e80 0xa96550 0xa96620 0xa9e4d0 0xb3e120 0xb413b0 0xc2f3a0 0xc3efe0 0xceeb70 0xd032e0 0xd291c0 0xd2b370 0xd2b5b0 0xd2b620 0xd2bb50 0xdbf550 0xe7d8e0 0xebbfb0 0xebc1a0 0xffeea0 0x10190a0 0x101dfe0 0x10263d0 0x10293b0 0x102b6c0 0x102b750 0x1064bd0 0x1064fc0 0x11e7860 0x11e7940 0x1267f30 0x126e4c0 0x12b5340 0x12b5450 0x12c93a0 0x12cef10 0x12f9ec0 0x1312080 0x132e7a0`

注: 上の VA は、base で fvm が走った 86 関数のうち候補 2 件以上の 73 件 (ret 断片と候補 1 件を含まない)。`cases.fvm_candidates` と `Analyzer.is_ret_fragment` を base の jsonl に当てて得た実測値。

**未解決・子 issue**:
- 候補多重の関数の fvm を deref 位置から救う方式 (issue の例示案): 本 PR では採らない。起票先: 本 issue の子として別途 (未起票・PM 判断)。
- `0x5c1030` の verdict 変化の根拠 (fvm arg 0 の diff の中身 `native_extra_call` 等): 未切り分け。
