# liftdiff REPORT 付録: OTT 旧 chain の前回比差分の切り分け (LD-16 / #825)

本書は `REPORT.md` §10 の要約の全文。親 issue #406 / PR #802 の前回比差分 (38/108/66) の追跡。

## 結論

- 前回比の基準は `59eea5c` = **38/108/66** (素材から再計算した報告値。3 回とも同一。生ログは未 commit)。
- 基準 `59eea5c` からの変化:
  - 38→40 (`origin/main` c4e93550): `ldlib/cases.py` の pattern 追加 (`79584ef7`・9→11 pattern) が主因と推定。ただし `cases.py` のみ main 版にした実行は **n=1** の報告値 (40/110/62)。main 全体の 3 回 (40/110/62) もログ無しの報告値。
  - 38→35 (`986e7415` 現 HEAD): 3 回とも 35/112/65。`results/liftdiff_e2e_head986e7415_n{1,2,3}.log` の `OTT_SUMMARY` で検証可能。主因の切り分けは未実施。
- **LD-31 (#1069) による訂正**: 以前の本付録の「旧 `59eea5c` = 33/110/69」「38→33 は `rt/ld_native.c` の計時追加が原因」「`cases.py` 差し替えで 33→35 が再現」は**再現しなかった**。これらは訂正前の報告値で、根拠のログも無いため無効。関連の表は本書から削除した (旧版は git 履歴に残る)。
- 非決定性: 現 HEAD `986e7415` の OTT 集計は 3 回同一 (ログで確認)。`59eea5c` と main の 3 回同一は報告値。
- issue 本文・PR #802 の 38/108/66 は、#1069 の素材再計算で再現した (報告値)。PR #802 当時の素材・環境との完全一致は未確認。

## 1. 実測値

| commit | 回 | 集計 (一致 / 不一致 / 実行不能) | D1 / D2 / D3 / D4_D5 / D6 | 根拠 |
|---|---|---|---|---|
| `59eea5c` (基準) | 1 | 38 / 108 / 66 | 4 / 6 / 14 / 18 / 26 | 報告値 (ログ無し) |
| `59eea5c` (基準) | 2 | 38 / 108 / 66 | 4 / 6 / 14 / 18 / 未表示 | 報告値 (ログ無し) |
| `59eea5c` (基準) | 3 | 38 / 108 / 66 | 4 / 6 / 14 / 18 / 未表示 | 報告値 (ログ無し) |
| `origin/main` c4e93550 | 1〜3 | 40 / 110 / 62 | 4 / 6 / 15 / 19 / 未表示 | 報告値 (ログ無し) |
| `986e7415` (現 HEAD) | 1〜3 | 35 / 112 / 65 | 4 / 6 / 14 / 20 / 26 | commit 済みログ |

- 出典の一次データ: `results/ott_ld31_repro_summary.txt` (`check_ott.py` 出力からの手作業の抜粋。生の `OTT_SUMMARY` 行ではない)。
- 旧 `59eea5c` の 1 回目は build 時の素材不足で失敗した実行を除き、素材を入れ直して再実行した結果。

## 2. ファイル単位の差し替え (削除)

旧版の本節は、基準が 33/110/69 だった時点の実行に基づく表で、LD-31 により無効。本節は削除した。
`cases.py` 単独差し替えによる 38→40 系の寄与は n=1 の報告値のみで、検証には §5 の手順での再実行が必要 (未実施)。

## 3. 関数単位の突合 (削除)

旧版の本節は、旧基準 33/110/69 の batch と `986e7415` の関数単位の差分に基づく。基準の訂正 (38/108/66) で無効となり削除した。38 基準の関数単位の突合は未実施 (旧 `batch.jsonl` が本 run に無い)。

## 4. n=3 の非決定性

- OTT 集計 (`check_ott.py`): `986e7415` は 3 回同一 (commit 済みログで確認)。`59eea5c` と main の 3 回同一は報告値。
- m11 sample:800 (`liftdiff_e2e.sh` [4/4]): 現 HEAD 3 回 = 一致 361 / 360 / 361、不一致 229 / 230 / 229、実行不能 210 / 210 / 210。1 件の揺れ (run 依存)。
  - 揺れの原因は推定 (native timeout・負荷による case outcome の揺らぎ、REPORT_APPENDIX §11 と同類)。関数単位の特定は未実施。
- e2e 全体: 3 回とも exit 0・`LIFTDIFF_E2E PASS`・所要 184.9 / 185.5 / 183.4 s (load avg は 1 分平均で 4.8〜6.4 の間で変動)。

## 5. 数え方の定義と再計算

- 対象: `targets/ott_old.json` の closure 212 関数 (`batch --set closure`)。
- 集計: 関数ごとの `verdict` (`match` / `mismatch` / `unexec`) の件数。
- D1〜D6 (`tests/check_ott.py`): D1 = tag `icall_drop` の関数数、D2 = `short_global`、D3 = `callsite_arg_drop` ∪ `arg_drop`、D4_D5 = C 定義 (`sig.c`) かつ mismatch、D6 = `xmm_arg_drop` ∪ `zero_init_drop` ∪ `fp_flag_unreflected` ∪ `spill_slot_deref`。tag は複数重複あり。
- 再計算:
  ```
  python3 liftdiff.py batch targets/ott_old.json --set closure --shards 4 --nobuild --out work/ott_old/batch.jsonl
  python3 tests/check_ott.py                     # OTT_SUMMARY を出力
  python3 tests/ott_delta.py <旧 batch.jsonl> <新 batch.jsonl>   # 関数単位の差分
  ```
- 旧 commit の再現: `git worktree add --detach <dir> 59eea5c`、`tools/{ott,m6,m11,liftdiff}/work/` を素材から入れる。
- 推奨基準 (今後の前回比): `59eea5c` (38/108/66) を固定基準とし、以後の比較対象は commit 済みの `OTT_SUMMARY` ログがある commit に限る。

## 6. 検証の範囲・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `59eea5c`・`origin/main` の 3 回分の生 `OTT_SUMMARY` ログ未 commit (報告値のみ) | 基準 38 と 40 の根拠が検証不能 | #1069 ([LD-31]) |
| `ldlib/cases.py` 単独差し替えの再現は n=1 のみ | 38→40 の主因の再現性が未確認 | #1069 ([LD-31]) |
| 38→35 (`986e7415`) の主因の切り分け未実施 | 集計差の機序が未特定 | #1069 ([LD-31]) |
| 関数単位の tag 変化の機序 (vm0/u16 pattern の効果) は未確認 | pattern 追加の効果の説明が推定止まり | #1070 ([LD-32]) |
| m11 sample:800 の 1 件揺れの関数特定 | 非決定性の出所が未特定 | #1070 ([LD-32]) |
| 素材の展開・python 依存 (`numpy capstone pefile`) は run ごとに必要 | 素の runner で e2e が exit 2 | 既に REPORT_APPENDIX §10 の未解決 (agent-setup) |
