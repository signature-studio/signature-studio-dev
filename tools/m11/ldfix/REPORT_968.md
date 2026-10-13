# #968 (LD-21) D17 修復 pass: rip 相対ポインタセルの 2 段 deref 潰れの IR 修復 (部分達成)

**判定: 部分達成**。store 宛 CELL_COLLAPSED のうち「セル K を読む IR load がちょうど 1 本」の 24 関数・29 セルを修復。
残り (複数 load の 28 関数、spill 宛 37 site) は子 issue に分割。受入条件 2 (CELL_COLLAPSED 0) と 3 (liftdiff 動的差分) は未達。PR は `Refs #968`。

前提: #510 (`REPORT_510.md`) の D17 (rip 相対セルの 2 段 deref が IR で 1 段に潰れる)。修復方式は `fix_d17.py`。

## 1. 修復方式

`load T, ptr inttoptr (K)` (K = セル自身の LVA) を
`%cellp.K = load ptr, ptr inttoptr (K)` + `load T, ptr %cellp.K` に置き換える。機械語 `mov rA,[rip+cell]; mov rD,[rA]` の意味どおり。
対象は audit (`audit_lsf_ssa.py` の `--json`) の CELL_COLLAPSED のうち store 宛 (frame=False)、かつ関数内で K を読む load が 1 本だけの site。
複数 load の関数は、どの load が機械語の site に対応するか IR だけでは決まらないので見送る。

## 2. 実測 (`fix_d17_e2e.sh`、PE 無し、work-m11 のみ)

| 項目 | 修復前 | 修復後 |
|---|--:|--:|
| CELL_COLLAPSED store 宛 site | 86 | 53 |
| CELL_COLLAPSED store 宛 関数 | 49 | 28 |
| CELL_COLLAPSED spill 宛 site | 37 | 37 |
| CELL_DEEP store 宛 site | 19 | 52 |
| alg3 SHALLOW (unk) | 78 | 49 |
| alg3 flagged 関数 | 77 | 58 |

- 修復関数数 24 (`fixed_fns=24 fixed_cells=29`)。関数一覧は `fix_d17_report.json` (e2e の work 内)。
- audit の集計 (`lsf_sites_arg 90 / unresolved 370 / fns_unresolved 169`) は修復前後で不変 (修復は load の形だけを変える)。
- emcc 構文検証 (`-O0 -g1 -c`): rc=0。
- audit_lsf_ssa.py の import 不具合を修正: `machine_sites` が #509 で 5 要素を返すようになり、3 要素の unpack が失敗していた (13 s で再現)。

## 3. 再現

`M11_WORK=<work-m11>/tools/m11/work bash tools/m11/ldfix/fix_d17_e2e.sh` (修復前 audit → 修復 → 修復後 audit → emcc)。

## 4. 未達・未実施 (子 issue)

- 複数 load の CELL_COLLAPSED 28 関数 / 53 site: 機械語の site と IR load の対応付けが要る (別 pass)。
- spill 宛 CELL_COLLAPSED 37 site (22 関数): 消費者の追跡が要る (#510 §4.3)。
- 動的差分 (liftdiff native vs wasm): PE から wasm を作る全数 batch が要る。修復関数の unexec→match は未確認。
- ネガコン: 未実施。e2e の step 1 (修復前 audit) が「修復を外した」基準で、CELL_COLLAPSED store 86 が戻ることを確認する対照として使える。専用の negctl は子 issue に含める。
- `docs/DEFECTS.md` への D17 行の追記は PM 判断 (issue 本文どおり、本 PR では編集しない)。
