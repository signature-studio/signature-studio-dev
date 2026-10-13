# 付録: icall #851 — `0x128c320` の関数境界誤認 (1 バイト関数化) の原因

> 本書は #851 の全文 (旧 `REPORT_APPENDIX.md` §12.3 相当)。`REPORT_APPENDIX.md` は 250 行上限 (`docs/DOC_MAP.md` §1) のため増やさず、本書に別置きした。

---

結論: **誤認の原因は範囲分割 (decode 単位)**。バイナリの境界は正しい。`0x128c320` の本体が同じ decode モジュールに無いと、RetDec は 1 バイトの stub として作る。`.pdata` (unwind 表) と一致する。

素材 `fl-win64` (`block00031_PE.bin`)・`toolchain-retdec` (RetDec v5.0)。検証起点 commit = `a2243d34` (本節の A〜D 実測)。前回の実測起点は `adc7f577` / `d4347c5d`。
再現: `oc_artifacts: fl-win64 toolchain-retdec` を PR 本文に置いた run で `FL_WIN64_DIR=<展開先> RETDEC=<retdec-decompiler> bash tools/icall/fn_boundary_repro.sh <outdir>`。スクリプトは範囲を直書きし `work/` に依存しない (chunk 行は `RANGES_DIR` 指定時のみ)。
各 run の集計: `<outdir>/<name>.log` に対し `grep -c NonRecursiveCFGBuilder` (警告数)、`<outdir>/<name>.drc.dsm` に対し `grep -h "^; function: function_128c320 at"` (ラベル)、所要はスクリプトが `sec=` で出す。

実測 (HEAD `a2243d34`、foreground、`load 0.43`、スクリプト全体 49.5 s。`$RUNNER_TEMP/fnb_851` で採取):

| run | rc | sec | 警告 全体 / `function_128c320` 関連 | `function_128c320` のラベル | `function_128c280` のラベル |
|---|--:|--:|---|---|---|
| A | 0 | 12 | 10 / 0 | `0x128c320--0x128dc44` (正) | `0x128c280--0x128c2e1` |
| B | 0 | 13 | 10 / 0 | `0x128c320--0x128dc44` (正) | `0x128c280--0x128c2e1` |
| C | 0 | 10 | 5 / 5 | `0x128c320--0x128c321` (1 B) | `0x128c280--0x128c281` (1 B) |
| D | 0 | 14 | 15 / 5 | `0x128c320--0x128dc44` (正) | `0x128c280--0x128c281` (1 B) |

- 集計は `grep -c NonRecursiveCFGBuilder <run>.log` と、`grep NonRecursiveCFGBuilder <run>.log | grep -c function_128c320` (関連数)。
- 全体 5 → 15 (D は C に本体を足した場合)。A/B にも出る 10 件 (`rax_1_reload` 5 件・`# empty statement` 3 件・`var*` 2 件) は隣接関数の decode 範囲由来。`function_128c320()` を指す警告は C / D の 5 件のみ。
- 前回 (`adc7f577`) の警告 5 件・5→15 は本 HEAD の A〜D 実測と一致する。前回の「279 s」は実測ではないため採らない。
- rt_flengine chunk0〜3 は **本 HEAD では未検証** (前回 `adc7f577` の実測のみ・範囲テキスト未コミット)。`before.ranges.N` は `tools/m11/work` (`fle_F.txt`) 由来で、`work-m11` 素材が本 run の `oc_artifacts` に無く、リポジトリ単独では再生成できないため。

**前回 `adc7f577` の chunk 実測 (本 HEAD で未再現)**: chunk0 (呼出元 `128f9e0` を含む) は `0x128c320--0x128c321` (1 B)・警告 5 件、chunk2 は本体を含まず 1 B、chunk3 (本体を含む) は正。chunk1 は本体も stub も無し。範囲テキストは未コミットのため根拠は再検証できない。

- `.pdata` (RVA → VA) の関数開始: `0x128c280--0x128c2e1` / `0x128c2f0--0x128c314` / `0x128c320--0x128dc44`。`0x128c2f0` は 3 点目の実関数。
- DSM の `; data inside code section at 0x128b811 -- 0x128c320` は、**選択外の関数本体を RetDec が data 扱いする**ことから来る。`0x128c2f0` は F (FLEngine 7,421 関数の選択) に含まれず、`data inside code section at 0x128c2e1 -- 0x128c2f0` と `0x128c313 -- 0x128c320` の間の data として出る。
- 呼出元の `function_128f9e0` から `function_128c320(v47)` へは直接 call 1 箇所。`0x128c320` の rel32 call 元は 4 箇所 (`0x1286317`・`0x1290312`・`0x12a28d3`・`0x12a35da`)。`0x128c2f0` の rel32 call 元は 0 件 (間接参照の可能性は未確認)。2 関数のみ (C) でも `0x128c280` が `--0x128c281` の 1 B 関数になる (実測)。
- 5 件の `NonRecursiveCFGBuilder` 警告は呼出元 `128f9e0` を含む側 (C / D) にのみ出る。本体 (D) を足すと `function_128c320` の名前の警告は消えず、全体の警告は 5 → 15 に増える (追加の 10 件は `rax_1_reload` 等の無関係 edge。要調査)。
- 既知類型か: `docs/DEFECTS.md` の D1a〜D18 の文言とは一致しない (1 バイト stub は decode 範囲由来で、命令の誤復号ではない)。**行案は未確定**。確定には 366 落ちとの突合が要る。

#### 未確定 (本 run で未達)

- 隣接関数の lift 欠落の before / after 監査 (`audit_icall.py` の数字) は**未実施**。上の表はラベル (境界) の before / after のみ。
- 追加の警告 10 件 (`rax_1_reload` 等) の出所は未確認。
- 366 落ちとの因果は未検証 (本体を足しても警告 5 件が残る)。

## #1059 (ICALL-19): 隣接関数・警告の出所 (測定 commit `9aad4595` = main, 再現 `tools/icall/fn_boundary_repro.sh`)

素材: `fl-win64` (`block00031_PE.bin`)・`toolchain-retdec` (RetDec v5.0)。runner 上で foreground、全 4 run の所要 8〜11 s、`load 0.87 → 1.30`。`tools/icall` に変更なし (`git diff 9aad4595 HEAD -- tools/icall` 出力 0 行)。

| run | rc | sec | 警告 全体 | `function_128c320` 関連 | `function_128c320` のラベル |
|---|--:|--:|--:|--:|---|
| A | 0 | 10 | 10 | 0 | `0x128c320--0x128dc44` (正) |
| B | 0 | 11 | 10 | 0 | `0x128c320--0x128dc44` (正) |
| C | 0 | 8 | 5 | 5 | `0x128c320--0x128c321` (1 B) |
| D | 0 | 11 | 15 | 5 | `0x128c320--0x128dc44` (正) |

- 警告の内訳 (`grep NonRecursiveCFGBuilder <run>.log`): A/B は `# empty statement` 3・`rax_1_reload = rax_1_reg2mem` 5・`var514`/`var512` 系 2 (隣接関数由来、本体無しでも出る)。C は `function_128c320(var3)` へのエッジ 5 件のみ。D は C の 5 件 (`function_128c320()`) に A/B 相当の 10 件が加わる。
- **1 バイト化は範囲分割で確定** (再掲): A/B で正、C で 1 B。`0x128c2f0` は B で `function_128c2f0 at 0x128c2f0--0x128c313` として選択時のみ出る (A では `data inside code section at 0x128c2e1--0x128c2f0` と `0x128c313--0x128c320` の data)。
- `function_128c320` を呼ぶ 0x128f9e0 の C 出力 (`D.drc.c` line 2948) には `function_128c320();` が残る。それでも D の警告は `there is no node for an edge to function_128c320()`。捨てられる段階は未特定 (D.log の phase 単位では切り分け未了)。
- `audit_icall.py` 突合 (`--funcs` で 5 関数 / 3 関数に限定。ただし旧 run の `--funcs` 関数一覧は本節に未記録で、5 関数 / 3 関数が C / D のどれに対応するかは確定できない): C は 388 site 中 dropped 387、D は 388 中 dropped 386 (`other_insn` 2)。A/B/D の隣接 3 関数 (`0x128c280`・`0x128c2f0`・`0x128c320`) は 14 site で dropped 13 (`other_insn` 1、3 run で同数)。**隣接関数の lift 欠落は before/after とも 13/14 で同じ** — 本体の有無で隣接関数の欠落は変わらない。
- 追加の 10 件 (`rax_1_reload` 等) は A/B にも出るので 1 バイト化の原因ではない。出所 (どの IR 命令が起点か) は未特定。
- 既知類型: `docs/DEFECTS.md` に 1 バイト stub (decode 範囲由来) の類型は無い。命令の誤復号ではないため、行案は未確定のまま。

## #1285 (ICALL-22): edge 捨て段の特定と 183 site 突合 (測定 commit `604e900f`)

素材: `fl-win64` (`block00031_PE.bin`)・`toolchain-retdec` (RetDec v5.0 `53e55b4b`)。foreground で実行。`load 0.53` (開始時)。
測定 commit `604e900f` は tools/icall のコードを変えた最後の commit。以後の差分はこの節と REPORT のみで、鮮度の証跡は次の通り (`git diff 604e900f HEAD -- tools/icall`):

```
 tools/icall/REPORT_APPENDIX_851.md | 61 ++++++++++++++++++++++++++++++++++++--
 1 file changed, 58 insertions(+), 3 deletions(-)
```

REPORT 以外 (`':!tools/icall/REPORT*'`) の差分は 0 行。よって `604e900f` での測定値は HEAD で有効。

### (1) 再現 (A〜D、`fn_boundary_repro.sh`)

前節 #851 の表と一致する元測定 (`604e900f`) の値。本 run では `fn_boundary_repro.sh` を再実行していない。

| run | rc | sec | 警告 全体 | `function_128c320` 関連 | ラベル |
|---|--:|--:|--:|--:|---|
| A | 0 | 12 | 10 | 0 | `0x128c320--0x128dc44` (正) |
| B | 0 | 12 | 10 | 0 | `0x128c320--0x128dc44` (正) |
| C | 0 | 10 | 5 | 5 | `0x128c320--0x128c321` (1 B) |
| D | 0 | 14 | 15 | 5 | `0x128c320--0x128dc44` (正) |

全体 49.3 s (`real`)。

### (2) edge が捨てられる段: `removing code that is not reachable in a CFG`

D の `D.log` で `function_128c320()` を指す警告 5 件はすべて、この段 (`Running phase: removing code that is not reachable in a CFG`) の中で出る (`D.log` 行 59〜62 ほか。後続段の再出力を含む)。

- `--print-after-all` (`D.pa.log`、682 段) で `function_128c320` の定義と呼出しを段ごとに数えた。LLVM 段の全段で `@function_128c320(` 定義は残り、呼出し `call i64 @function_128c320(), !insn.addr !1080` (`0x128f9e0` 内、`0x1290312` の site) も残る。
- つまり、LLVM 段では消えていない。BIR 変換段 (`converting function function_128c320`、`D.log` 行 56) では関数ノードは作られている。
- 捨てられるのは LLVM→BIR 後の `NonRecursiveCFGBuilder` (CFG 構築) 段で、「ノードが無い」と判定される。その内部 (BIR のどのノードが対応を失うか) は `--print-after-all` が BIR を dump しないため未特定。
- 結論: 段は **「BIR 変換 → CFG 構築 (`removing code that is not reachable`)」** まで絞れた。段内部の原因は未特定。

### (3) 183 site 単位の突合 (`audit_icall.py` 直接監査、before 側 IR)

`--funcs` で C (`0xc589b0`・`0x128f9e0`) / D (+`0x128c320`) を監査。`sites_{C,D}.json` を site ごとに突合。

| 関数 | C 全 site | C dropped | D 全 site | D dropped |
|---|--:|--:|--:|--:|
| `0xc589b0` | 183 | **183** | 183 | **183** |
| `0x128f9e0` | 191 | **190** | 191 | **190** |
| `0x128c320` | 0 | 0 | 14 | 13 |

- C→D で既存 site の状態変化は **0 件** (`status change C->D: []`)。`0x128c320` 本体を足しても `0xc589b0` / `0x128f9e0` の site 落ちは変わらない。
- したがって「`0xc589b0` の 183 site 落ち」と「`0x128c320` 本体の有無」は独立 (`0x128f9e0` は 190 / 191 落ち)。`function_128c320` の edge 捨ては 183 site 落ちの原因ではない。
- 注: 本節の数値は `audit_icall.py` の before 側 IR 直接監査で、REPORT (`roundtrip.sh` 経由・書換え後の 366 落ち) とは対象が違う。REPORT の 183 と本節の `0xc589b0` の 183 は一致するが、`0x128f9e0` は 190 (REPORT 183) で一致しない。両者は別条件のため直接比べない。
- 前節 (#851) との比較: 前節の C「388 site 中 dropped 387」と本節の C (`0xc589b0`+`0x128f9e0`、計 374 site・dropped 373) は一致しない。本節の C は `--funcs "0xc589b0-0xc5d667,0x128f9e0-0x1294ab8"` (`fn_boundary_repro.sh` の run C 指定と同じ 2 関数)、D は同 + `0x128c320-0x128dc44`。前節の `--funcs` 関数一覧は未記録のため、前節の 388 が別の関数集合 (隣接 3 関数 `0x128c280`・`0x128c2f0`・`0x128c320` の 14 site を足すと 374 + 14 = 388 と一致) で測られた可能性を排除できない。確定は旧 run の `--funcs` 指定が判明してからとする。両節とも、比較は関数一覧を揃えた上で行う。

### (4) 結論と既知類型

- 既知類型か: `docs/DEFECTS.md` D1a〜D20 のどれとも一致しない (D15 は「call 命令の IR ブロックが空」だが、本件は IR に `call i64 @function_128c320()` が残る)。1 バイト stub の decode 範囲由来 (前節) と、BIR での node 欠落 (本節) の 2 つが絡む。
- **行案は未確定**。仮置きの類型名: `RNC-edge-drop` (RetDec `NonRecursiveCFGBuilder` が、decode 範囲で 1 バイト化した関数への edge を捨てる)。`docs/DEFECTS.md` への追記は、BIR 段内部の原因が確定してから行う。
- 366 落ちとの因果: 本体の有無は落ちに影響しない (上記 (3))。ただし、366 の内訳 (`0x128f9e0` 183 相当) との 1 対 1 対応は、`roundtrip.sh` 経由の条件で未確認。

### 未達 (子 issue へ分割)

- `NonRecursiveCFGBuilder` が BIR の `function_128c320` ノードを失う原因 (BIR 段内部、RetDec ソース追跡が要る)。
- `rax_1_reload` 等 10 件の出所 (IR 命令単位の追跡)。
- `roundtrip.sh` 条件 (書換え後) での 183 site 単位の突合 (REPORT の 366 内訳との対応)。
- rt_flengine chunk0〜3 の再現 — `RANGES_DIR` (`tools/m11/work` 由来、`work-m11` 未取得) が無く未検証。

