# REPORT_1352 — 計測 build (`M11_INSTR_413060=1`) の OFF 871/23 は HEAD で再現しない (#1352, 親 #944 §4(e))

## 0. 結論

- 測定 commit: **`1be53b3f`** (origin/main。このブランチでコードは変えていない。追加は `repro_1352.sh` と本 REPORT のみ)。
- HEAD では計測 build の OFF も **870/24/0** で、既定 build (計測なし) の **870/24/0** と一致する。issue が前提にした 871/23 は、古い測定 (`ba9ba284`・REPORT_944 §1) の値で、現 HEAD では出ない。
- `M11_DEST_READ=0` (dest 読出しを止める) でも 870/24/0。**dest 読出しは集計を変えない**。「volatile 読出しが不正 dest で trap を生む」仮説は HEAD では支持されない。
- 受入条件 1 (3 点 (probe 呼出し・wrapper 改名・`m11_dest_obs` 宣言) の切り分け) は**対象消失のため中止**。HEAD に比べる差 (871/23) が存在せず、切り分ける対象が無い。PM 判断 (#1352 のコメント) で再定義した。差の原因を特定したとは書かない。
- 871/23 が出なくなった時点は未特定 (`ba9ba284` と `1be53b3f` の間で `tools/m11` の post・rt・ov 周辺が変わっている。二分は未実施)。
- HEAD で残る `getmem` の −4 (既定 2012 / 計測 OFF 2008) は、元の 871/23 とは別の事象として #1542 ([M11-N100]) に引き継ぐ。

## 1. 測定 (HEAD `1be53b3f`・直列・単発・`bash tools/m11/trap_triage/repro_1352.sh`)

素材: `fl-win64` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`work-m11` (`tools/m11/work/`)・`toolchain-emsdk` ([EMSDK])。`m11_gen_ir2.sh` で `ir_conditions.json` を生成 (ldfix F1=902 F3c=36 errors=0・`ir_sha256=2c68ceae…`)。

| 構成 | ok | noproc | miss | trap | clobber | 413060 呼出し | dest_obs_n | dest 指紋 | 判定 |
|---|--:|--:|--:|--:|--:|--:|--:|---|---|
| 既定 (`M11_INSTR_413060` 未設定) | 870 | 1 | 47 | 24 | 0 | — | — | — | 870/24/0 一致 |
| 計測 OFF (`M11_INSTR_413060=1`・dest 読出しあり) | 870 | 1 | 47 | 24 | 0 | 227 | 227 | `acb2345ddb678281` | 870/24/0 一致 |
| 計測 OFF・dest 読出し無し (`M11_DEST_READ=0`) | 870 | 1 | 47 | 24 | 0 | 227 | 0 | `14650fb0739d0383` | 870/24/0 一致 |

- 全体所要 1 分 55 秒 (3 build + 3 survey)。survey 単発は 16 秒前後。load 開始 1.06。
- 既定 build の `boot_final3.ll` md5 は `7304232a4b2a28e1456cb3e7527b653d` (REPORT_944 §6 の `repro_705.sh` 実測と同じ)。
- `repro_705.sh` も HEAD で PASS (既定 870/24、OFF/ON/OFF 再実行/ネガコンの計数は REPORT_944 §6 と一致。OFF 指紋 `acb2345ddb678281` 決定的)。

## 2. 解釈

- 計測 probe (`m11_probe(8)`) と dest 観測 (`m11_dest_obs`) を入れても、survey の集計 (ok/noproc/miss/trap/clobber) は既定と同一。
- dest 読出し (volatile 読出し) を止めても集計は同一。読出しが trap の原因ではないことが、HEAD で再確認できた。
- `getmem` は既定 2012 / 計測 OFF 2008 / 計測 OFF・dest 読出し無し 2008 (`survey_*.out` の実測)。計測 build と既定の差 (−4) は dest 読出しに依らないので、probe 呼出し・wrapper 改名・宣言の 3 点のどれかに由来する。ただし survey の判定 (ok/trap/clobber) には出ず、どの点かは未切り分け (1 回ずつの測定)。
- dest 指紋は読出しを止めると 0 件になるので、指紋そのものは `M11_DEST_READ=1` のときだけ意味を持つ (REPORT_944 §6 の記述どおり)。

## 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 871/23 が出なくなった commit の特定 (`ba9ba284`〜`1be53b3f` の二分) | 計測 build の値の由来が未説明 (現 HEAD で既定と一致するため、既定の基準を変える必要は無い)。対象消失のため受入条件 1 は中止 | #1352 (PM 判断で再定義・受入条件 1 は中止) |
| HEAD の `getmem` −4 (既定 2012 / 計測 OFF 2008) の帰属 (3 点のどれか) | survey の判定には出ない。dest 読出しには依らない | #1542 ([M11-N100]) |
| dest 指紋差 (OFF `acb2…` ≠ ON `ac2d…`) の意味的差かビルド差か | REPORT_944 §4 (a) | #1149 ([M11-N67]) |

## 4. 再現

`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH=$AGENT_PY_BIN:$PATH bash tools/m11/trap_triage/repro_1352.sh` (判定 `PASS`)。`AGENT_PY_BIN` は `capstone`・`pefile`・`numpy` を入れた Python venv の bin (agent-setup が作る。`docs/WORKFLOW.md` §11 参照)。
作業ディレクトリは `tools/m11/`。`work/` は `m11_gen_ir2.sh` で生成する (`work-m11` 展開後に実行)。
