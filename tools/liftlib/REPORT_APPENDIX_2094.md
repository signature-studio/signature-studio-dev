# liftlib 付録 — #2094: movntps の lower_asm_store 追加 (#1581 / `2e2f1dfe`) の回帰測定

- 日付: 2026-10-14 / 親 issue: #2094 (`[PLG-F3-20]`) / 担当: `tools/liftlib/` (測定)・`tools/plugins/lift/passes/` (回帰テスト)
- 数値はすべて本 run で実測。測定は `ws-2094` (HEAD `26f90ada` = origin/main 起点)・`ws-2094-base` (`0d9b5385`)・`ws-2094-mov` (`2e2f1dfe`) の 3 worktree で行い、素材 (gitignore 対象の work) は main の展開済みを各 worktree へ複写した (展開し直しは無し)。
- 測定 commit (コードを変えた最後の commit): `26f90ada`。`git diff 26f90ada HEAD -- tools/liftlib/liftlib tools/liftlib/tests tools/liftlib/liftlib_e2e.sh` の出力は空 (本 PR は liftlib のコードを変えない → 再測定は不要)。

## 0. 結論 (先出し)

| 項目 | 結果 (実測) |
|---|---|
| movntps 変更 (`2e2f1dfe`) 単独の liftlib 回帰 | **無し**。`--quick` ALL PASS (前回 `0d9b5385` と同結果) |
| HEAD (`26f90ada`) の `--quick` | **FAIL** (`ott_auto_none` のみ。IR 一致 6 項目が false)。原因は movntps ではなく **`52ad0ce1` (#1664・A7 空行除去)** |
| OTT の movntps 変更前後 (`ir5_patch.py` 同一入力) | `__asm_movntps` call **8 → 0**・`store` **3004 → 3012 (+8)**・行数 25160 のまま・差分 8 行のみ |
| 子 issue | **#2863** `[PLG-F3-32]` (p1_legacy の IR 一致ゲート FAIL の原因確定と修復) |

## 1. `bash tools/liftlib/liftlib_e2e.sh --quick` の結果

| 測定 commit | 内容 | 結果 | real | load (終了直後の 1 分値) | (a)(b)(c) regress | ott_auto_none |
|---|---|---|---|---|---|---|
| `0d9b5385` | movntps 変更の直前 (`2e2f1dfe^`) | ALL PASS / rc=0 | 5m39.19s | 1.32 | fa_gain・kh_gain・ott PASS | PASS |
| `2e2f1dfe` | movntps 単独 (#1581) | ALL PASS / rc=0 | 5m37.16s | 1.27 | 同 | PASS |
| `26f90ada` | HEAD (origin/main 起点・本 issue の対象) | FAIL / rc=1 | 5m44.42s | 1.04 | fa_gain 400/400・kh_gain 366/366・ott PASS | **FAIL** |

- 単体テスト (`tests/test_unit.py`) は 3 回とも ALL UNIT TESTS PASS。
- HEAD の `ott_auto_none`: `O1_base_identical` は true、`O2a`・`O2b`・`O2c`・`O3a`・`O3b`・`O4` が false。出力 SHA 突合 (42 組合せ・m10 成果物と) は `equal: true`、e2e `checks 8 / broken 0`、trap rc 0。
- 既定の `ott` (`--auto f7,p1`) は 3 回とも PASS (census junkHi 104 ≤ 104)。

## 2. 切り分け (`python3 -m liftlib ott --auto none`・各 約 10 秒)

| commit | 結果 | 備考 |
|---|---|---|
| `3d011ecd` (= `52ad0ce1^`) | PASS | |
| `52ad0ce1` (#1664 A7 空行除去) | **FAIL** (O2a・O2b・O2c・O3a・O3b・O4) | 初めて FAIL した commit |
| `26f90ada` (HEAD) | FAIL (同) | |

- 機構 (推定・p1_legacy の行窓は未検証): `52ad0ce1` は `normalize` (`tools/liftlib/liftlib/passes/base.py` と `tools/m5/ir5_patch.py` の両方) に `; uselistorder directives` の前の空行を消す行を足した。OTT の lift 出力 (`ott_lift.ll`) は空行が 155 行 (155 B) 減るが、**空行を除いた非空行の内容は差分 0** (`diff <(grep -v '^$' a) <(grep -v '^$' b)` = 0 行)。`p1_legacy` が行数の窓で `comis` 直後の分岐を探すため、その検出が変わると推定する。
- 空行を除く `nb()` で比べる O1 が通るのに、P1 以降が落ちる点と整合する。

## 3. movntps 変更前後の OTT 出力 (変更された `tools/plugins/lift/passes/ir5_patch.py`)

- 入力: `tools/m6/work/ott_norm0.ll` (OTT の RetDec 出力を m2 正規化した後の .ll)。
- 処理: `python3 tools/plugins/lift/passes/ir5_patch.py IN OUT`。変更前 = `0d9b5385` の版、変更後 = `26f90ada` の版 (`2e2f1dfe` 以降、この file は無変更)。

| 指標 | 変更前 (`0d9b5385`) | 変更後 (`2e2f1dfe`〜) |
|---|---|---|
| 入力の `call void @__asm_movntps` | 8 | 8 |
| 出力の行数 | 25160 | 25160 |
| 出力の `store` 行 | 3004 | **3012 (+8)** |
| 出力の `call void @__asm_movntps` 残数 | 8 | **0** |
| `declare @__asm_movntps` (宣言) | 1 | 1 |
| 変更前後の差分行 | — | **8 行のみ** (`call @__asm_movntps` → `store i128 %5, ptr %74` 等) |

- liftlib 本体の経路 (`tools/liftlib/liftlib/passes/base.py`・`tools/m5/ir5_patch.py`) には `movntps` が 0 件。`2e2f1dfe` が触った `tools/plugins/lift/passes/` は liftlib から import されない。よって liftlib の `ott_lift.ll` は `2e2f1dfe` で変わらない (`--quick` ALL PASS が裏付け)。

## 4. 回帰テスト (新規 `tools/plugins/lift/passes/test_movntps_store.py`)

- HEAD の `ir5_patch.py`: `PASS n=2` (movntps と movups.2 の 2 件を store へ復元、pxor は残る)。
- ネガティブコントロール (`0d9b5385` の `ir5_patch.py`): `FAIL n=1` (exit 1)。movntps の復元が無いことを検出する。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `52ad0ce1` (#1664) 以降、`ott --auto none` の IR 一致ゲート O2a〜O4 が FAIL (SHA 突合は PASS)。HEAD で `--quick` が FAIL | `liftlib_e2e.sh --quick` が HEAD で FAIL のまま | 子 issue **#2863** `[PLG-F3-32]` |
| `plugins-kilohearts` は展開していない (`--quick` は `--fresh` を使わず、`tools/targets/kilohearts/work` (work-liftlib-targets 由来) で足りる) | `--fresh` (KH の RetDec 再 lift) は未実行 | 起票不要 (本 issue の範囲外・`--quick` の受入に不要) |
