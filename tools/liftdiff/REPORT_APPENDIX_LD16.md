# liftdiff REPORT 付録: OTT 旧 chain の前回比差分の切り分け (LD-16 / #825・LD-31 / #1069)

本書は `REPORT.md` §10 の要約の全文。親 issue #406 / PR #802 の前回比差分の追跡。

## 結論

- 前回比の基準は、同一 HEAD で n=3 採点した値 (min–max)。過去の報告値 (38/108/66・33/110/69) は基準にしない。`59eea5c` の 38/108/66 は旧基準・報告値で、比較の参照点にとどめる (生ログ commit 済み・下記)。
- 参考: 旧基準 `59eea5c` (38/108/66) から、`origin/main` c4e93550 = 35/112/65 (38→35)。このうち `ldlib/cases.py` だけで 38→40 が再現する (main 全体では 40 でなく 35)。
- 基準の決定 (PM 判断 #1069, 2026-10-14): 『同一 HEAD で n=3 回採点した値 (集計 min–max)』。
- 訂正 (LD-31): 旧版 LD-16 付録の基準値 (訂正前の報告値) と、それに基づく切り分け (ld_native.c 計時の寄与・関数単位の表) は再現せず無効。本書から削除した (旧版は git 履歴に残る)。
- 生ログ: 本節末尾の「生ログの根拠」を参照。

## 1. 実測値

| commit | 回 | 集計 (一致 / 不一致 / 実行不能) | D1 / D2 / D3 / D4_D5 / D6 | 根拠 |
|---|---|---|---|---|
| `59eea5c` (前回比の基準) | 3 | 38 / 108 / 66 (3 回同一) | 4 / 6 / 14 / 18 / 26 | 生ログ `results/ott_ld31_n3_c59eea5c_n{1,2,3}.log` |
| `origin/main` c4e93550 | 3 | 35 / 112 / 65 (3 回同一) | 4 / 6 / 14 / 20 / 26 | 生ログ `results/ott_ld31_n3_cmain_n{1,2,3}.log` |
| HEAD 4716440c (`ldlib/`・`rt/` は main と差分 0) | 3 | 35 / 112 / 65 (3 回同一) | 4 / 6 / 14 / 20 / 26 | 生ログ `results/ott_ld31_n3_head_n{1,2,3}.log`。`986e7415` の既存ログ `results/liftdiff_e2e_head986e7415_n{1,2,3}.log` も 35/112/65 |
| `59eea5c` + main の `ldlib/cases.py` のみ | 3 | 40 / 110 / 62 (3 回同一) | — | 生ログ `results/ott_ld31_n3_cases59_n{1,2,3}.log` |

測定方法 (全行共通): wasm は素材 `work-liftdiff` 同梱の凍結 snapshot (`work/ott_old/ld_wasm.wasm`) を使い、`ld_native` は各 commit の `rt/` から再ビルド。`batch --set closure` (212 関数) → `check_ott.py`。wasm 側は 3 commit で同一のため、差はすべて liftdiff 側 (`ldlib/`・`rt/`) の違いに由来する。wasm を各 commit で再 build した測定ではない (emsdk の runner 未導入)。

- 前回比は、同一 run で測った基準側 n=3 と変更側 n=3 の組で行う (PM 判断 #1069)。旧基準 59eea5c (38/108/66) は参照点のみ。
- 検証の途中で、`work/` の展開直後の `liftdiff.py build` が `sigs.json` (212→178 関数) を書き換えた事故があった。素材 tar から `sigs.json`・`batch.jsonl` を戻し直した後の測定のみ採用する。

## 2. ファイル単位の差し替え (未実施)

- `ldlib/cases.py` 単独 (main 版) で 38→40 が n=3 で再現 (生ログ commit 済み)。main 全体 (35) は cases.py 以外の変更 (`ldlib/compare.py`・`classify.py`・`pe.py`・`session.py`・`rt/` 等) を含み、その寄与は未切り分け。

## 3. 関数単位の突合 (未実施)

- 関数単位の差分 (`tests/ott_delta.py`) は、再計算した `batch.jsonl` が揃った後に行う。本 run では未実施。

## 4. n=3 の非決定性

- OTT 集計 (`check_ott.py`): `59eea5c`・main・HEAD・`cases.py` 単独版は各 3 回同一 (生ログ commit 済み)。`986e7415` は 3 回同一 (既存ログ)。
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
- 前回比の運用 (PM 判断 #1069): 基準側 (main の HEAD) と変更側を同じ run で n=3 採点し、生の `OTT_SUMMARY` 行を `results/` に commit して REPORT から参照する。生ログの無い数値は「報告値」と明記する。

## 6. 検証の範囲・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| main 全体 (match 35) と `cases.py` 単独 (match 40) の差の原因 (cases.py 以外の main 側変更) の切り分け未実施 | 38→35 の機序が未特定 | #1069 ([LD-31]) |
| wasm を各 commit で再 build していない (凍結 snapshot 使用・emsdk 未導入) | 3 commit の wasm 側差分は未測定 (liftdiff 側差分のみ) | #1069 ([LD-31]) |
| 関数単位の tag 変化の機序 (vm0/u16 pattern の効果) は未確認 | pattern 追加の効果の説明が推定止まり | #1070 ([LD-32]) |
| m11 sample:800 の 1 件揺れの関数特定 | 非決定性の出所が未特定 | #1070 ([LD-32]) |
| 素材の展開・python 依存 (`numpy capstone pefile`) は run ごとに必要 | 素の runner で e2e が exit 2 | 既に REPORT_APPENDIX §10 の未解決 (agent-setup) |

## 生ログの根拠

すべて `results/` に commit 済みの生ログ (`OTT_SUMMARY` 行を含む)。

- `results/ott_ld31_n3_c59eea5c_n{1,2,3}.log`: 59eea5c の n=3
- `results/ott_ld31_n3_cmain_n{1,2,3}.log`: origin/main (c4e93550) の n=3
- `results/ott_ld31_n3_head_n{1,2,3}.log`: HEAD 4716440c の n=3
- `results/ott_ld31_n3_cases59_n{1,2,3}.log`: 59eea5c + main の `cases.py` の n=3
- `results/liftdiff_e2e_head986e7415_n{1,2,3}.log`: 986e7415 の n=3 (LD-16 時の既存ログ)

`results/ott_ld31_repro_summary.txt` は手作業の抜粋で、本節の根拠には使わない (旧報告値の出典であり、無効)。
