# REPORT #2265 — spill 宛 未判定 関数群 C 後半 (19 関数・23 site) の消費者分類 (LD-98)

親: #2246 (LD-94) / #1161 (LD-35)。本 run は分類を確定させず、機械語側の後続読み出しの列挙と未判定の残数を残した。

## 1. 測定

- 測定 commit: 016cc403 (run 開始時の main)。worktree branch `2265-ld98-spill-consumer-c2`。
- ベースライン: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (rc=0・所要 2m30s・7/7 完了・load average 1.00)。
  `spill178_1161.tsv` と `drops_510.tsv` は results/ と一致 (cmp OK)。
- 集計 (step 7/7): spill 宛 unk site 178 / 71 関数。status 未判定 120 / 確定 51 / 判定不能 7。脱落関数の和集合 69 (変更無し)。

## 2. 対象 23 site の機械語側列挙

- 出力: `results/ld98_consumers_2265.tsv` (生成: `ld98_dump.py`・`audit_lsf.descend` で関数を降下し、同じ frame slot の後続 memop を列挙)。
- 23 site 中 19 site で後続読み出しが 1 件以上あり、NO_CONSUMER の根拠にはならない。
- 後続読み出しが 0 件の site (4 件): `6c3700:6c3c78`・`6c3d20:6c44bd`・`6c5930:6c6125`・`76e720:76e74f`。
  同一関数内の別経路 (rsp 相対の別表記・`lea` 経由) で読まれる可能性が残るため判定しない。
- `lea` で frame slot の address を取る site (`f3e050:f3e0c2`) は、address 経由の消費者が残るため NO_CONSUMER にしない。

## 3. 判定の結果

- 本 run で確定させた判定: **0 site**。`candidate_verdicts_1161.jsonl` には書いていない。
- 理由: 各 site で IR 側の store→load 対応 (値の出自の追跡・reg2mem / reload 経由の段数) を確認する必要があり、23 site 分は本 run の残り時間に収まらなかった。根拠の無い判定は脱落集合を誤って確定させる。
- 機械語の frame 変位 (`[rbp+0x58]` 等) と IR の `stack_var_N` の対応は未確認。site ごとにこの対応を取るところから始める必要がある。

## 4. 残数と脱落集合

- spill 178 site の status は変わらず (未判定 120 / 確定 51 / 判定不能 7)。本 issue の範囲の未判定は 23 → 23 (0 件更新)。
- 脱落関数の和集合は 69 のまま (変更無し)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 後半 23 site の IR 側の値の出自 (site 単位の判定) | 19 関数の脱落集合への寄与が未確定 | #2265 (LD-98・open のまま。Refs で継続) |
| 後続読み出し 0 件の 4 site の別経路確認 | NO_CONSUMER の可否が未確定 | 同上 |
| 前半 19 関数 | 同上 | #2264 (LD-97) |
| UNDETERMINED 7 site | 同上 | #2253 (LD-95・既存) |
| 群 A / 群 B | 同上 | #2244 / #2245 (既存) |
