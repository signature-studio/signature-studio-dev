# REPORT #2227 — spill 宛 未判定 120 site の消費者分類 (分割)

親: #1161 (LD-35)。本 run は未判定 120 site を全件分類せず、関数群に分割した。

## 1. ベースライン実測 (commit 7d15ceab・origin/main)

- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (work-m11 / work-liftdiff 展開済み)
- 結果: rc=0・所要 2m32s・7/7 完了。`spill178_1161.tsv` と `drops_510.tsv` は results/ と一致 (cmp OK)
- 負荷: 実行開始時 load average 0.98 (1 分平均)
- 集計 (step 7/7):
  - spill 宛 unk site 178 site / 71 関数
  - status: 未判定 120 / 確定 43 / 判定不能 15
  - 脱落関数の和集合 69 (store 宛 DROP 51 ∪ spill 宛 22 関数)。spill 宛の確定 TRUE_DROP 関数 10 は全て drops_510 に含まれる

## 2. 機械語側の一次確認 (cf3790・18 site)

- 18 site は全て `mov qword ptr [rbp + X], rax` (`alg2=FRAME`)。
- 機械語上の後続 load (`cmp`/`mov`/`lea` 経由の読み出し) は 18 site 全てで 1 件以上あり、NO_CONSUMER ではない。
- IR 側の対応 (store と reload の突合) は未確定。TRUE_DROP / OK_LOAD の判定は本 run では入れていない (根拠不足のため)。

## 3. 分割

| 群 | 関数数 | site | 起票先 |
|---|---|---|---|
| A (`cf3790`・`c589b0`・`128f9e0`) | 3 | 42 | #2244 (LD-92) |
| B (`10c7cd0`・`1046a30`・`ddf630`・`6bb3f0`・`466af0`・`12cb680`) | 6 | 32 | #2245 (LD-93) |
| C (残り 38 関数) | 38 | 46 | #2246 (LD-94) |

合計 120 site (未判定) = 42 + 32 + 46。分割の根拠は `spill178_1161.tsv` の `status=未判定` 行を fn 別に数えた結果。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未判定 120 site の機械語・IR 両面の分類 | spill 宛の脱落関数の和集合 69 が未確定 | #2244 / #2245 / #2246 |
| UNDETERMINED 15 site の IR 側再検証 | 同上 | #2228 (LD-89・既存) |
