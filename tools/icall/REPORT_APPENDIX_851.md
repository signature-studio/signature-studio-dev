# 付録: icall #851 — `0x128c320` の関数境界誤認 (1 バイト関数化) の原因

> 本書は #851 の全文 (旧 `REPORT_APPENDIX.md` §12.3 相当)。`REPORT_APPENDIX.md` は 250 行上限 (`docs/DOC_MAP.md` §1) のため増やさず、本書に別置きした。

---

結論: **誤認の原因は範囲分割 (decode 単位)**。バイナリの境界は正しい。`0x128c320` の本体が同じ decode モジュールに無いと、RetDec は 1 バイトの stub として作る。`.pdata` (unwind 表) と一致する。

素材 `fl-win64` (`block00031_PE.bin`)・`toolchain-retdec` (RetDec v5.0)。検証起点 commit = `adc7f577` (前回実測) / `d4347c5d` (A〜D 再確認・本節の再実行)。
再現: `oc_artifacts: fl-win64 toolchain-retdec` を PR 本文に置いた run で `FL_WIN64_DIR=<展開先> RETDEC=<retdec-decompiler> bash tools/icall/fn_boundary_repro.sh <outdir>`。スクリプトは範囲を直書きし `work/` に依存しない (chunk 行は `RANGES_DIR` 指定時のみ)。
各 run の集計: `<outdir>/<name>.log` に対し `grep -c NonRecursiveCFGBuilder` (警告数)、`<outdir>/<name>.drc.dsm` に対し `grep -h "^; function: function_128c320 at"` (ラベル)、所要はスクリプトが `sec=` で出す。

再実行の実測 (`d4347c5d` 系列、main 取り込み後 `51fb3680` で同じ `tools/icall` を再実行、foreground、`load 0.23`、全体 48.7 s):

| run | rc | sec | 警告 全体 / `function_128c320` 関連 | `function_128c320` のラベル | `function_128c280` のラベル |
|---|--:|--:|---|---|---|
| A | 0 | 12 | 10 / 0 | `0x128c320--0x128dc44` (正) | (A に無し) |
| B | 0 | 13 | 10 / 0 | `0x128c320--0x128dc44` (正) | (B に無し) |
| C | 0 | 10 | 5 / 5 | `0x128c320--0x128c321` (1 B) | `0x128c280--0x128c281` (1 B) |
| D | 0 | 13 | 15 / 5 | `0x128c320--0x128dc44` (正) | (D に無し) |

- 全体 5 → 15 (D は C に本体を足した場合)。増えた 10 件 (`rax_1_reload = rax_1_reg2mem` 5 件・`# empty statement` 3 件・`var*` 2 件) は A/B にも出るので、本体の有無ではなく隣接関数の decode 範囲由来。`function_128c320()` を指す警告は C / D の 5 件のみ。
- 前回の「追加 10 件」は、この内訳と整合する。出所 (隣接 edge の扱い) は未調査のまま。
- rt_flengine chunk 行 (chunk0〜3) は **未検証**。範囲テキスト `before.ranges.N` は `tools/m11/work` (`fle_F.txt`) 由来で、`work-m11` 素材が本 run の `oc_artifacts` に無く、リポジトリ単独では再生成できないため。

**前回 run (`adc7f577`) の数値** (警告 5 件・5→15・279 s・rc=0) は今回の A〜D 再実行 (上表) で突合した。279 s は前回の 4 run + chunk の合計と推定で、本 run の A〜D 合計は 48.7 s。

| decode 範囲 | `function_128c320` のラベル | 備考 |
|---|---|---|
| A: `0x128c280-0x128c2e1` + `0x128c320-0x128dc44` | `0x128c320--0x128dc44` (正) | 本体あり |
| B: A + `0x128c2f0-0x128c313` | `0x128c320--0x128dc44` (正) | 本体あり |
| 2 関数のみ (`0xc589b0-0xc5d667`, `0x128f9e0-0x1294ab8`) | `0x128c320--0x128c321` (**1 B**) | 呼出元 `128f9e0` と同 module。NonRecursive 警告 5 件 |
| 2 関数 + `0x128c320-0x128dc44` | `0x128c320--0x128dc44` (正) | 警告 `function_128c320()` は残る (5 件) |
| rt_flengine chunk0 (呼出元 `128f9e0` を含む) | `0x128c320--0x128c321` (**1 B**) | 警告 5 件 |
| rt_flengine chunk1 | (本体も stub も無し) | |
| rt_flengine chunk2 | `0x128c320--0x128c321` (**1 B**) | 本体を含まない |
| rt_flengine chunk3 (本体を含む) | `0x128c320--0x128dc44` (正) | |

- `.pdata` (RVA → VA) の関数開始: `0x128c280--0x128c2e1` / `0x128c2f0--0x128c314` / `0x128c320--0x128dc44`。`0x128c2f0` は 3 点目の実関数。
- DSM の `; data inside code section at 0x128b811 -- 0x128c320` は、**選択外の関数本体を RetDec が data 扱いする**ことから来る。`0x128c2f0` は F (FLEngine 7,421 関数の選択) に含まれず、`data inside code section at 0x128c2e1 -- 0x128c2f0` と `0x128c313 -- 0x128c320` の間の data として出る。
- 呼出元の `function_128f9e0` (chunk0) から `function_128c320(v47)` へは直接 call 1 箇所。`0x128c320` の rel32 call 元は 4 箇所 (`0x1286317`・`0x1290312`・`0x12a28d3`・`0x12a35da`)。`0x128c2f0` の rel32 call 元は 0 件 (間接参照の可能性は未確認)。同じ chunk0 では `0x128c280` も `--0x128c281` の 1 B 関数になる。
- 5 件の `NonRecursiveCFGBuilder` 警告は chunk0 (呼出元 `128f9e0` を含む側) にのみ出る。本体を足すと `function_128c320` の名前の警告は消えず、全体の警告は 5 → 15 に増える (追加の 10 件は `rax_1_reload` 等の無関係 edge。要調査)。
- 既知類型か: `docs/DEFECTS.md` の D1a〜D18 の文言とは一致しない (1 バイト stub は decode 範囲由来で、命令の誤復号ではない)。**行案は未確定**。確定には 366 落ちとの突合が要る。

#### 未確定 (本 run で未達)

- 隣接関数の lift 欠落の before / after 監査 (`audit_icall.py` の数字) は**未実施**。上の表はラベル (境界) の before / after のみ。
- 追加の警告 10 件 (`rax_1_reload` 等) の出所は未確認。
- 366 落ちとの因果は未検証 (本体を足しても警告 5 件が残る)。

