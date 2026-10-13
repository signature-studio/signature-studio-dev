# tools/plugins/g1/REPORT_APPENDIX.md — REPORT.md §9 (旧版: 検証起点 86ca2d5 の実測) の全文

`REPORT.md` の 250 行上限のため分割移動した (内容は削除していない)。 #539 (main の `batch_lift.sh` が既定 `PLUG_ICALL=1`・12 列 `status.csv`) 取り込み前の測定。 現行の検証は `REPORT.md` §9。

## 旧 §9. 検証 (86ca2d5)

コミット済み HEAD **86ca2d5** を `git worktree add --detach` した別 worktree (`work/` 空) で実行。 4 core / 15 GiB の Actions runner、実行は逐次 (並列数 1)、各 run の間に他の重い処理は走らせていない。
前提 inventory (`prep.sh`) は clean worktree へ dev worktree の生成物 (`win_scan` / `winfuncs` / `win_unique` / `win_abi` / `kernel_table` の JSON) をコピーして使い、再生成していない。

| 項目 | 実測 |
|---|---|
| 前提 inventory の生成 (dev worktree で 1 回、`prep.sh`) | **377 s** (`win_funcs.py` が主。 `Pool(14)` を 4 core で実行、終了時 load average (1 分) 16.3)。 `g1_e2e.sh` は work/ が在れば作り直さない |
| `g1_e2e.sh` 全体 (C++ DLL 7 本を含む。 3 run: dev / clean / clean 2 回目) | **440 / 442 / 448 s** (dev / clean 1 回目 / clean 2 回目)、いずれも exit 0 |
| 開始時 load average (1 分) | 0.62 / 0.51 / 0.90 (同順) |
| lift 秒 (`status.csv` の seconds 12 block 計。 同上 3 run の min–max) | **33–39 s** (39 / 33 / 36) |
| C++ DLL 7 本の lift 秒 (`engines.csv` の `lift_s`、3 run の min–max、block 順は §7) | 9 / 38–39 / 45–46 / 33–34 / 39–40 / 36 / 46–52 |
| run 間の一致 | dev と clean 2 回で `facts.json` はバイト一致 (sha256 先頭 `6152896e`)。 `status12.csv` (seconds 列を除く)・`icall_table.md`・`define_table.md`・`cpp_facts.json`・`engines.csv` (lift_s 列を除く) も一致 |
| gate 通過 | clean HEAD で gate 1 (12/12 block) / 1b (不合格 0) / 2 (148/148) / 3 (13/13) / 4 (sweep ≠ 到達 + gap の block 0) / C++ DLL 形式検査 (7/7) すべて合格、exit 0 |
| `g1_nega.sh` (clean HEAD 86ca2d5) | exit 0、**38 s**、NC1〜NC9 すべて DETECTED (dev worktree の同内容の run も全 DETECTED) |

ネガティブコントロール (数値; 対照は無改変で合格することを併記):
- NC1 `emcc -c` (Wasp 24302): `final.ll` の定義 1 つの `ret` を除去 → rc **0 → 1**。
- NC2 ranges: 閉包 ranges 8 → 7 (末尾 `function_6a55f0` を落として再 lift) → define 9 → 7、 対象関数 1 → 0。
- NC3 `judge.py`: 実測 `status12.csv` (12 行、対照 rc 0) を 1 箇所ずつ壊した **137 変異** (block ごとに lift_rc=1 / f80=3 / emcc_c_rc=1 / unimpl=5 と -1 / defines=closure-1 / closure=defines+1 / closure=0 / seconds 非数値 / 行削除 / 行重複の 11 種 × 12、要求外 block 追加 1、ファイル全体 4 = ヘッダのみ・空・ヘッダ不正・不在) → **受理 0 / 拒否 137**。
- NC4 e2e の終了コード: 先頭 block の `emcc_c_rc` を 1 にした CSV を `G1_STATUS_CSV` で渡して `g1_e2e.sh --skip-lift --judge-only` → **rc 1、通過行 0** (対照 rc 0、通過行 1)。 `work/g1/status12.csv` は不合格 run の前後で sha256 不変。
- NC5 `matrix_check.py` / NC6 `ids_crosscheck.py`: 対照 rc 0。 BassDrum の `closure_funcs`+1・Fruit Kick を欠く・空 facts → rc 1 (3 件とも)。 3x Osc の ID 2 の件数 3 → 4・空 facts → rc 1。
- NC7 `icall_check.py` / NC8 `engine_check.py`: 対照 rc 0。 3x Osc の audit 静的 site +1・audit JSON 1 本欠く → rc 1。 engines.csv の末尾行を欠く・`lift_rc` を非整数 → rc 1。
- NC9 `define_audit.py`: 対照 rc 0 / `function_408930` を `function_ffffff` に改名 → rc 1 / `final.ll` 無し → rc 1。

別系統の突合は gate 2 (matrix 148 項目) / 3 (ID の独立走査) / 4 (間接 call の線形 sweep)。 規約確認 (HEAD): `git diff bfccd23 HEAD --stat` の変更は `tools/plugins/g1/` と `docs/DOC_MAP.md` のみ。 20 MiB 超の blob なし (`find tools/plugins/g1 -size +20M` 空)。 REPORT は 250 行以内。
検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`) と host / kernel / 間接 call の静的な数え上げ。 範囲外: wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp。 範囲外の項目について本書は何も主張しない。
