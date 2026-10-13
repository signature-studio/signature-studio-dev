# liftdiff REPORT 付録: OTT 旧 chain の前回比差分の切り分け (LD-16 / #825・LD-31 / #1069)

本書は `REPORT.md` §10 の要約の全文。親 issue #406 / PR #802 の前回比差分の追跡。

## 結論

- 38→40 (main) と 38→35 (986e7415) の 2 組: 基準 `59eea5c` = 38/108/66 から、`origin/main` c4e93550 = 40/110/62、`986e7415` (現 HEAD) = 35/112/65 への差分。基準 38 は素材から再計算した報告値 (3 回同一・生ログ未 commit)。
- 前回比の基準 (PM 判断 #1069, 2026-10-14): **『同一 HEAD で n=3 回採点した値 (集計 min–max)』**。過去の報告値は基準にしない。比較は基準側 (main の HEAD) と変更側を同じ run で n=3 採点し、生の `OTT_SUMMARY` 行を `results/` に commit して参照する。
- 訂正 (LD-31): 旧版 LD-16 付録の基準値 (訂正前の報告値) と、それに基づく切り分け (ld_native.c 計時の寄与・関数単位の表) は再現せず無効。本書から削除した (旧版は git 履歴に残る)。
- 生ログ: 本節末尾の「生ログの根拠」を参照。

## 1. 実測値

| commit | 回 | 集計 (一致 / 不一致 / 実行不能) | D1 / D2 / D3 / D4_D5 / D6 | 根拠 |
|---|---|---|---|---|
| `59eea5c` (前回比の旧基準) | 1〜3 | 38 / 108 / 66 (3 回同一) | 4 / 6 / 14 / 18 / 26 (1 回目) | 報告値 (ログ無し) |
| `origin/main` c4e93550 | 1〜3 | 40 / 110 / 62 (3 回同一) | 4 / 6 / 15 / 19 / 未表示 | 報告値 (ログ無し) |
| `986e7415` (現 HEAD) | 1〜3 | 35 / 112 / 65 (3 回同一) | 4 / 6 / 14 / 20 / 26 | commit 済みログ `results/liftdiff_e2e_head986e7415_n{1,2,3}.log` |

- 旧 `59eea5c` の 1 回目は build 時の素材不足で失敗した実行を除き、素材を入れ直して再実行した結果。
- `results/ott_ld31_repro_summary.txt` は `check_ott.py` 出力からの手作業の抜粋で、生の `OTT_SUMMARY` 行ではない。

## 2. ファイル単位の差し替え (未実施)

- `ldlib/cases.py` 単独差し替えによる 38→40 の寄与は n=1 の報告値のみ (ログ無し)。n=3 の再現は §5 の手順で行う。
- 38→35 (`986e7415`) の主因の切り分けは未実施。

## 3. 関数単位の突合 (未実施)

- 関数単位の差分 (`tests/ott_delta.py`) は、再計算した `batch.jsonl` が揃った後に行う。本 run では未実施。

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
- 前回比の基準: PM 判断 (#1069) のとおり、同一 HEAD で n=3 採点した値。過去の報告値は使わない。

## 6. 検証の範囲・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ldlib/cases.py` 単独差し替え (38→40 の主因) の再現は n=1 のみ | 38→40 の主因の再現性が未確認 | #1069 ([LD-31]) |
| 38→35 (`986e7415`) の主因の切り分け未実施 | 集計差の機序が未特定 | #1069 ([LD-31]) |
| 関数単位の tag 変化の機序 (vm0/u16 pattern の効果) は未確認 | pattern 追加の効果の説明が推定止まり | #1070 ([LD-32]) |
| m11 sample:800 の 1 件揺れの関数特定 | 非決定性の出所が未特定 | #1070 ([LD-32]) |
| 素材の展開・python 依存 (`numpy capstone pefile`) は run ごとに必要 | 素の runner で e2e が exit 2 | 既に REPORT_APPENDIX §10 の未解決 (agent-setup) |

## 生ログの根拠

(生ログ commit 後に記入)
