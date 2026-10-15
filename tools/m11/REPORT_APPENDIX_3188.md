# REPORT_APPENDIX_3188 — #3188 の LB=0 と LB=0x10000 の寛容起動の unit 差 8 件 (REPORT_N403.md §7 の全文)

分割移動 (REPORT_N403.md が 250 行を超えるため)。本文の内容は変えていない (§7-0 以降は round 2 の再測定の記録)。

## 7. #3188: LB=0 と LB=0x10000 の寛容起動の unit 差 8 件の切り分け (Actions runner で実測)

測定 commit: `47574748` (main `49f1a94d` の merge commit。この commit が tools/m11 のコードを最後に変えた commit)。検証 HEAD はこの節を含む最後の commit (下 §7-6 で、測定 commit から HEAD までの tools/m11 コード差分は 0)。測定 runner: Actions runner (load average は未採取)。
既知類型との関係: 該当なし (`docs/DEFECTS.md` の ID は未付与。NULL 源の memcpy は下 §7-4 の候補で、既存類型との対応は未確認)。
素材: `fl-win64` (`extracted/block00031_PE.bin` 22,227,016 B を `FL_WIN64_DIR` (`tools/shared/env.sh`) の展開先へ展開・2 s)・`work-m11` (`tools/m11/work/` へ展開・2 s)・`toolchain-emsdk` は展開せず runner 既存の emsdk ([EMSDK]、`docs/REFERENCES.md` §4) を使った。`toolchain-retdec`・`work-liftdiff` は使っていない (lift を走らせていない)。
`m11_e2e.sh` の全再生成 (指紋検査) は使わず、後段だけ `m11_lb_tolerant_repro.sh` で回した (gen_ir2 → data/image → lb_check → build → `m11_tolerant.mjs`)。

### 7-0. 再測定の対象 (round 2 の要求への対応)

- 2 つの commit を測った。`15341d0e` (round 1 の fix commit = レビュー時の HEAD) と `47574748` (それに main `49f1a94d` を merge した commit)。merge は競合が無く (`git merge-tree` が clean)、main が #2211・#1325 系で `tools/m11/ldfix/ldfix.py` などを変えていたため、merge 後の code で測り直した。
- `15341d0e` の LB=0 は reviewer の実測 (942/867/1/47/74) と一致した (下 §7-3)。
- main の取り込みで変わった code: `git diff 15341d0e 47574748 -- tools/m11 ':(exclude)tools/m11/REPORT*'` (main 由来の ldfix 変更)。この差で unit 56 の kind が変わった (§7-3)。
- 本 PR が main に対して加えるのは tools/m11 では `m11_lb_ir_fn_diff.py` だけ (REPORT 除く)。よって merge 後の寛容起動の結果は main の同じ code の結果と同じになる。
- LB 直書きの修正 (`ldfix/fix_ld108.py`・`fix912/m11_fix912.py`) と再現 (`m11_lb_tolerant_repro.sh`)・突合 (`m11_lb_unit_diff.py`) は main (#3160) と同一。

### 7-1. 再現スクリプト (main #3160 版を使う。本 PR で追加するのは `m11_lb_ir_fn_diff.py` のみ)

- `tools/m11/m11_lb_tolerant_repro.sh <LB> <出力先>`: 後段だけの再現。出力は `tools/m11/<出力先>/` (`tolerant_units.json`・`boot_final.ll`・ログ)。
- `tools/m11/m11_lb_unit_diff.py A.json B.json`: unit の index 単位で kind を突合 (VA は LB でずれるので比べない)。差は `kind_diff=N` で出る (exit 0 は差の有無と無関係)。
- `tools/m11/m11_lb_ir_fn_diff.py A.ll B.ll function_X ...`: 関数本体の行差分と、整数定数の変化量 (LB=0x10000 側 − LB=0 側) を出す。第 2 オペランドの定数 (`add i64 %a, N`・`store i64 N`) も数える。

### 7-2. 修正 (受入 2 の前段: LB 直書きの IR 書換え pass が LB=0x10000 で止まる)

修正前 (HEAD `24be607a`) は `M11_LB_BASE=0x10000` の IR も wasm も作れなかった (fail-closed)。原因は LB=0 の定数の直書き 2 件:

| pass | 直書き | 症状 (修正前・LB=0x10000) | 修正 |
|---|---|---|---|
| `ldfix/fix_ld108.py` (D20) | head 変数の store 先 `i64 16404608` (LB=0 の LVA = VA 0x13A5080) | gen_ir2 が `store 行が想定と違う` で停止 (IR の定数は 16470144 = +0x10000) | `HEAD_VA + VA_TO_LVA` |
| `fix912/m11_fix912.py` (#912) | VMT 参照 `i64 994072` (LB=0 の LVA = VA 0x4F2B18) | m11_build.sh が `対象行が無い (before=0 after=0)` で停止 (mode off でも検査する) | `0x4F2B18 + VA_TO_LVA` |

素材なしで確認した範囲: `M11_LB_BASE=0` で `fix_ld108` の照合文字列は `i64 16404608`、`fix912` の VMT は `994072` (修正前と同一)。`M11_LB_BASE=0x10000` で `16470144`・`1059608`。
LB=0 の出力は修正前後で変わらない (修正は LB=0 で同じ定数を出す)。round 2 の LB=0 の値は下 §7-3 の `15341d0e`・`47574748` のとおり。

### 7-3. 寛容起動の結果 (実測。値の正本はこの節だけ)

| 測定 | units | ok | noproc | miss | skipped (oob・halt0・unreachable・abort) | wall (repro 全体) |
|---|---|---|---|---|---|---|
| LB=0 @ `15341d0e` | 942 | 867 | 1 | 47 | 74 (19・7・1・0) | 1 m 23.8 s |
| LB=0 @ `47574748` (1 回目) | 942 | 868 | 1 | 47 | 73 (19・7・0・0) | 1 m 23.8 s |
| LB=0 @ `47574748` (2 回目) | 942 | 868 | 1 | 47 | 73 (19・7・0・0) | (tolerant 12.9 s) |
| LB=0x10000 @ `47574748` | 942 | 868 | 1 | 47 | 73 (oob 16・halt0 8・abort 2・unreachable 0) | 1 m 25.5 s |

- `15341d0e` の LB=0 は `REPORT_N403.md` §6-1 と一致 (差 0)。値の正本は下の表で、§6-1 とは「一致」の 1 行だけ。
- 集計の定義: units = ok + noproc + skipped。skipped は `m11_tolerant.mjs` の SKIP 集合 (halt0・oob・unreachable・abort・other・oom・miss・clobber) の計で、miss を含む。内訳 (oob・halt0・unreachable・abort) の計は miss と別。
- 突合 (`m11_lb_unit_diff.py`, LB=0 vs LB=0x10000 @ `47574748`): **kind 差 8 件**。unit 40 (`0x105bd0` ok→halt0)・153 (`0x265b90` ok→oob)・158 (`0x26d1a0` ok→oob)・291 (`0x432660` oob→ok)・296 (`0x446130` oob→ok)・304 (`0x483140` oob→abort)・555 (`0x7f2500` oob→abort)・745 (`0xabb3b0` oob→ok)。`REPORT_N403.md` §6-2 と一致。
- ネガティブコントロール (決定性): LB=0 @ `47574748` の 2 回の突合 (`m11_lb_unit_diff.py`) は kind 差 0。差 8 件は実行の揺れではない。
- main 取り込みによる変化: `15341d0e` → `47574748` の LB=0 で kind が変わったのは unit 56 (`0x16fde0`) の 1 件 (`unreachable` → `ok`)。LB=0x10000 の unit 56 も `ok`。LB 間の突合には現れない (LB 依存ではない)。main 側の ldfix 変更による差。
- **issue の「現 HEAD で 8 件」は、修正前の HEAD では再現しなかった** (LB=0x10000 の IR が作れない)。修正後に初めて測れた。

### 7-4. 原因の切り分け (途中。未特定)

- **IR の再配置の漏れは見つからなかった** (`m11_lb_ir_fn_diff.py`・`47574748` の 2 本の `boot_final.ll`): 関数 412770 (差 2 行)・4128b0 (差 23 行)・411d20 (1 行)・412c20 (1 行)・412e40 (0)・535c11 (0)。行数は全て LB 間で同一。定数の変化量は全て `[65536]` か `[0, 65536]` (LB=0x10000 側 − LB=0 側) で、それ以外の変化は無い。第 2 オペランドの定数 (`add i64 %a, N`・`store i64 N`) も数えた版で確認済み。
- **image 側**: 線形 0 の NULL 領域は LB=0 で PE ヘッダ (`4d 5a 50 00 …`)、LB=0x10000 で全 0 (`lb_check` の `null_region_nonzero_bytes` = 0)。NULL を読む箇所の値が LB で変わる。
- **候補 (unit 40 の Halt0 経路)**: `function_412770` の memcpy の源が `ptr null` (IR 全体で `ptr null` 源の memcpy は 1 件だけ)。元の機械語 (VA 0x412790) は `mov rsi,[rax]` (arg1 の先頭 8 B を読む) → `rep movsq` 37 qword で、lift が load を脱落させ NULL に置換した silent miscompile の疑い。
  - 否定結果 (旧版の記録): 源を `[arg1+0]` の load に戻すと kind 差 8 件・skipped の内訳は不変だったという記録がある。**ただし再現できない**: 実験の行の指定 (どの行をどう変えたか) は記録に無く、実験ディレクトリ (`work/exp_null_src_*`) も repo と work-m11 の snapshot に無い。この否定結果は参考扱いとし、結論には使わない。再実験は子 #3229 の項目。
  - この NULL 読みが 8 件の原因かどうかは未確定。lift の欠陥そのものは残る。
- **未検証の候補 (C 側)**: `m11_ov.c:194` の icall の `tkey = target + (0x400000 - M11_LB_BASE)` (LVA → VA 換算。VA 形式の target は fallback あり)。
- **未特定**: unit 153・158 (LB=0x10000 で OOB の読み先)、291・296・304・555・745 (LB=0 側の OOB。wasm 関数 `function_535c11`・`function_407e20__lifted`)、304・555 の abort の呼出元 (記録は最内の `abort` だけ)。

### 7-5. 検証範囲と限界

- 範囲: 寛容起動 (`m11_tolerant.mjs`) の unit 別結果と、6 関数の IR 突合のみ。strict (`m11_run.mjs`)・survey・`m11_e2e.sh` の gate は未実行 (指紋検査を迂回しないため)。
- LB=0 の既存 gate (`e2e_expect.env`) への影響は未確認。修正は LB=0 の文字列を変えない (`VA_TO_LVA = 0` で同じ定数) が、gate の再実行は未了 (子 #3229)。
- 回数: `47574748` で LB=0 を 2 回 (同一 HEAD・突合 0)、LB=0x10000 を 1 回。`15341d0e` で LB=0 を 1 回。
- 未解決 (起票先は PR 本文の表): 8 件の原因特定 (上 §7-4 の未特定) → 子 #3229。memcpy 源 NULL の lift 欠陥 (§7-4) → 子 #3229。unit 56 の main 由来の kind 変化 (§7-3) → 子 #3229。

### 7-6. 測定 commit から HEAD までの差分

- 測定 commit: `47574748`。`git diff 47574748 HEAD -- tools/m11 ':(exclude)tools/m11/REPORT*'` の出力は空 (コードは測定 commit と同一)。
- 参考: 旧測定 commit `6a20f8b1` からの 4 パス差分 (ldfix・fix912・repro・unit_diff) は round 1 までの記録のとおり 8 files, +307 −88 で、main の merge に由来する。この差分の結果は §7-3 の `47574748` の測定に含まれる。
