# REPORT_942_QSTORE — 本番の IR 生成順 (ldfix → ld108 → qstore) で stage4 trap の変化を測る (#942 受入 1・2)

既知類型との関係: 消えた 3 件 (unit 53・87・138) は D17 (4B 初期化 slot を 8B で読む。qstore 対象)。`REPORT_942_PTRSLOT.md` (未 merge の診断記録・commit `e40916d2`) の予測 (「qstore 適用 IR で消える」) を本測定で確認した。

## 0. 結論

- 前 run までの survey の基準 (snapshot `tools/m11/work/boot_final3.ll`) は qstore 前の IR (`docs/WORKFLOW.md` §11: #516 以前の生成)。本番の生成順 (`m11_gen_ir2.sh` の ldfix → fix_ld108 → `m11_build.sh` の qstore) を再現すると、survey は **ok 136 → 139・trap 9 → 6**。
- 消えた trap は unit 53 (0x158e20)・unit 87 (0x19f9a0)・unit 138 (0x243270)。3 件とも qstore の確定 site が直す (下の §2)。
- unit 144 (0x25c540) は OOB から halt0 に種別が変わる (trap の総数には含まれたまま)。変化の原因は未確認。
- ldfix (F3a 2・F3c 33) と fix_ld108 は survey の件数を変えない (ab_pnq = 136/9。canonical e2e の fix も 136/9)。
- 逐次 boot (stage4) は 4 variant すべて unit 17 で `memory access out of bounds` (units_run 17)。**qstore は boot threw を解消しない**。受入 2 の原因は未特定のまま。

## 1. 測定

- commit `3525c2c4` (`tools/m11/ldfix/qstore_ab_942.sh` 追加。既存の ldfix.py・fix_ld108.py・qstore・stage4.sh・survey_stage4.mjs を呼ぶのみ)。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/qstore_ab_942.sh` → **111.7 秒・rc 0** (load 0.47 / 0.54 / 0.30 → 1.08 / 0.73 / 0.40)。n=1。
- 素材: fl-win64・work-m11 (snapshot `boot_final3.ll`・`m11_image.bin`)・work-liftdiff。toolchain-emsdk は [EMSDK] (`docs/REFERENCES.md` §4) を使用。

| variant | IR の作り方 | stage4 threw (units_run) | survey ok | miss | trap | OOB | halt0 | raw から消えた trap |
|---|---|---|---|---|---|---|---|---|
| ab_raw | snapshot そのまま | OOB (17) | 136 | 14 | 9 | 8 | 1 | — |
| ab_qs | + qstore | OOB (17) | 139 | 14 | 6 | 4 | 2 | 53・87・138 |
| ab_pnq | ldfix → fix_ld108 | OOB (17) | 136 | 14 | 9 | 8 | 1 | — |
| ab_prod | ldfix → fix_ld108 → qstore | OOB (17) | 139 | 14 | 6 | 4 | 2 | 53・87・138 |

先頭 trap unit (VA・種別):
- raw: 17 (0x55790) OOB / 53 (0x158e20) OOB / 56 (0x16fde0) OOB / 87 (0x19f9a0) OOB / 114 (0x223840) halt0 / 138 (0x243270) OOB / 144 (0x25c540) OOB / 149 (0x264260) OOB / 158 (0x0) OOB
- prod: 17 OOB / 56 OOB / 114 halt0 / **144 halt0 (raw は OOB)** / 149 OOB / 158 OOB

同一 HEAD の canonical e2e (`bash tools/m11/ldfix/ldfix_e2e.sh`・commit `c98d2c99` = 作業開始時の origin/main): **60.3 秒・rc 0・judge PASS**。stage4 base/fix とも units 17/942・threw OOB。survey base = fix = ok 136 / trap 9。修復件数 F3a 2 / F3c 33 / F1 0 / F2 0 / F3b 0。

## 2. 消えた 3 件の対応 (qstore の確定 site)

`tools/m11/qstore/results/qstore_sites.tsv` の verdict `fix` の site (本測定の qs.log: fixed_stores=279):

| unit | 最内 frame (raw) | qstore の確定 site (verdict fix) | 適用後の IR |
|---|---|---|---|
| 53 | C `418190` ← `418210` ← `function_8cbb00` | `function_8cbb00` -48 (・-56) | `alloca i64`・`store i64 0` |
| 87 | C `418190` ← `function_59f9a0` | `function_59f9a0` -16・-24・-32 | 同じ形に書換え |
| 138 | C `418190` ← `418210` ← `function_646130` | `function_646130` -32・-40 | 同じ形に書換え |

機構は D17 (4B の 0 初期化が上位 4B の残骸を残し、8B で読まれる)。unit 53 は `REPORT_942_PTRSLOT.md` の E1 (IR の 1 slot だけを `alloca i64` にした対照) と同じ結果。

## 3. 測定の注意

- survey は `m11_boot_enter` で InitUnits ループを抑止し、942 unit を 1 本ずつ隔離して実行する (`survey_stage4.mjs`)。逐次 boot (stage4) とは停止点が違う。
- trap の VA は `first_trap_units` (先頭 12 件まで) から取った。raw 9 件は全件出ている。
- ab_qs と ab_prod は ok・trap・trap 種別が一致 (ldfix と ld108 は survey の件数を変えない)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 17 (逐次 boot の threw) の発生 load。qstore 後も残る (C `function_4133f0` の `D(old-8)` の old の上流) | 受入 2 | #942 (次 run) |
| unit 56・149・158 の引き金の値 (`REPORT_942_TRAPSITE.md` §2 の未確定分) | 受入 1 | #942 (次 run) |
| unit 144 の OOB → halt0 の変化の原因 (qstore 適用で何の値が変わったか) | 受入 1 (副作用の評価) | #942 (次 run) |
| survey の基準 (snapshot = qstore 前) を本番順の IR に置き換えるか。`ldfix_e2e.sh` の入力を変えると他の測定の基準も変わる | 測定の基準 | PM 判断 (#942 に記録) |
| 受入 3 (現 main 生成 IR での件数反映) | 受入 3 | 済 (#1292・#1469) |

## 5. 次の入口

1. unit 17: qstore 適用 IR (`tools/m11/ldfix/work/qstore_ab/ab_prod.ll`) で C `function_4133f0` の `old` を probe する (`REPORT_942_TRAPSITE.md` §7 の手順)。`*dest` の上位 4B の書込み元を qstore の未検出分から探す。
2. unit 144: `function_407e20__lifted` の `i32.store8` の番地の計算値を raw と prod で比べる。

## 6. 差分 (`docs/WORKFLOW.md` §6)

- 測定 commit: `3525c2c4` (`qstore_ab_942.sh` を追加した commit。測定はこの commit で実施)。
- e2e の測定 commit: `c98d2c99`。
- 差分 (e2e 経路): `git diff c98d2c99 HEAD -- tools/m11/ldfix/ldfix_e2e.sh tools/m11/ldfix/stage4.sh tools/m11/ldfix/survey_stage4.mjs tools/m11/ldfix/ldfix.py tools/m11/ldfix/fix_450560.py tools/m11/ldfix/fix_ld108.py tools/m11/qstore tools/m11/m11_ov.c | wc -l` → 0。

## 7. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP   # 素材展開後 (fl-win64 / work-m11 / work-liftdiff)
bash tools/m11/ldfix/qstore_ab_942.sh                              # 4 variant の stage4 + survey + 集計
bash tools/m11/ldfix/ldfix_e2e.sh                                  # canonical e2e (base/fix)
```
