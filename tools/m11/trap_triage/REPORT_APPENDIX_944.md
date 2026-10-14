# REPORT_APPENDIX_944 — unit 158・j=12 の dest 値差の後続経路 (#1945・#1864 の残り)

REPORT_944.md §9.3 の付録。測定 commit: **`e5e3c7c2`** (origin/main。本節の作業ではコードを変えていない)。
コード差分 0 (文書のみ)。確認コマンド: `git diff --stat e5e3c7c2 HEAD -- tools/m11`。出力:

```
 tools/m11/trap_triage/REPORT_944.md          |  1 +
 tools/m11/trap_triage/REPORT_APPENDIX_944.md | 55 ++++++++++++++++++++++++++++
 2 files changed, 56 insertions(+)
```

文書以外を除いた差分 `git diff e5e3c7c2 HEAD -- tools/m11 ':!tools/m11/trap_triage/REPORT_944.md' ':!tools/m11/trap_triage/REPORT_APPENDIX_944.md'` は 0 行。

## 1. 再現 (受入条件 3・同一 build 内の決定性)

コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH=$HOME/.local/agent-py/bin:$PATH bash tools/m11/trap_triage/repro_1389.sh` (OFF → OFF 再実行 → ON・直列・単発)。判定 `PASS`。全体 1 分 49 秒 (`time` の real・load 開始 0.93 / 1.03 / 1.01)。
素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`)・work-m11 (gitignore 対象の作業領域)・`toolchain-emsdk` ([EMSDK]・`releases-6e9f6885`)。`m11_gen_ir2.sh` を 50 秒で実行 (ldfix F1=902 F3c=36 errors=0)。

| 構成 | 記録 (呼出し数) | 比較の結果 | survey elapsed |
|---|--:|---|--:|
| OFF | 227 | — | 16.243 s |
| OFF 再実行 | 227 | OFF と完全一致 (差 0) | 16.065 s |
| ON (`M11_OV_413060=1`・読出しあり) | 216 | unit・順番で揃った 216 件中、差 1 件: unit `0x26d1a0` j=12 (`st` `len` `rc` `h` の 4 フィールド) | 16.149 s |

差分の中身 (`cmp_1389.py` の出力): OFF `{st 0, len 0, rc 0}` / ON `{st 1, len 1, rc 1}`。ON 側の 11 件は片側のみ (ON は 216 件のため `k` の対応が 11 件分外れる)。

## 2. unit 158 の呼出し列 (OFF/ON・記録より)

unit `0x26d1a0` の f413060 呼出しは OFF 28 回・ON 17 回 (`cost_<label>.json`)。全体の k は 136〜163 (OFF)。
j=0〜11 は OFF/ON で一致 (`st` は j=1,3,6 のみ 1 (len 59)、他は len 0)。j=12 (k=148) で ON だけ `st=1 len=1` (OFF は `len 0`)。
j=13 (k=149) 以降は OFF/ON とも同じ値 (`len 59`) だが、ON はこの unit の呼出しが j=16 までしか無い (17 回)。

## 3. ON の trap (unit 158)

- ON の survey: unit 158 は `memory access out of bounds` で trap (`detail` の `trap` 種別)。OFF は ok。
- 同一 build (`M11_INSTR_413060=1 M11_OV_413060=1 M11_DEST_READ=1`・記録あり) の再実行で同じ trap (証跡は gitignore 対象の作業領域。repo には含まれない)。
- 最上位 frame は未取得 (detail は種別のみ。`top_frame_idx` は全体集計で unit 158 に紐付かない)。REPORT_684 の `414bb0` ←`652500` 系 (unit 158 は REPORT.md §最上位 frame 表の `414bb0` 群) と関係する可能性はあるが、**未検証**。
- **読出しのみの ON (`M11_DEST_READ=0`・記録なし) の再測定**: unit 158 は **ok** (survey 870/24、REPORT_944 §9.2 と一致)。呼出し 28・getmem 140 (OFF は 139)・freemem 94 (OFF は 92)。`m11_build.sh` の stamp (`M11_DEST_READ` を含む `work/neg_413060.stamp`) で build を切り替えて測定した。**実際に使った環境変数の組と実行手順は記録に残っておらず、repo にもこの測定を再現するスクリプトは無い** (`repro_1389.sh` は OFF/OFF/ON の 3 点のみで `M11_DEST_READ=0` を含まない)。下記は build 切替の仕組みからの再構成で、未検証: `M11_INSTR_413060=1 M11_OV_413060=1 M11_DEST_READ=0 bash m11_build.sh` → `M11_INSTR_413060=1 M11_SURVEY_COST=<out> node m11_survey.mjs`。証跡 (build ログ・survey 出力) は gitignore 対象の作業領域にあり repo には含まれない。本 PR の検証では再実行していない。
- 記録あり ON (`M11_DEST_READ=1`) の unit 158 は trap で、呼出し 17 で止まり getmem 23・freemem 16 (OFF 139/92 と大きく違う)。
- 以上から、観測を入れた ON で unit 158 が trap し、観測を止めた ON では ok になる。これは **記録側の読出し/書込みが unit 158 の実行を変えている**ことを示す。
- ただし `DEST_READ=0` では j=12 の値を観測していないため、「ON の値差 (`len 0→1`) が後続の結果に効かない」とは言えない。値差が後続の呼出し・読出しを変えるかは、IR で unit 158 の後続経路を追うまで未確定 (受入条件 1)。

## 4. 受入条件の判定 (#1945)

1. **値差が結果に効くか (後続の呼出し・読出し)**: **未達**。j=12 の値差後に ON で呼出しが 28→17 に減り trap するが、「値差が原因で後続が変わる」か「記録の副作用で trap する」かの切り分けは未了。後続経路の IR 突き合わせ (呼出し元・後続の読出し) は未着手。
2. **§9.3 追記・§4 (a) 更新**: 本付録へのリンクを §9.3 に追記。結論は「未確定」のまま。
3. **決定的な測定と実測値**: **達成**。§1 の OFF 2 回一致・所要・load を記録。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 158・j=12 の値差の後続経路 (呼出し元・後続の読出し) の IR 突き合わせと、ON trap の最上位 frame の取得 | 値差が結果に効くかの確定 (受入条件 1) | #2003 ([M11-N132]) |
| 記録なしの ON (読出し 1 回のみ) の再測定 (build の切替が要る) | §9.2 の結論の再確認 | #2003 に含める |
| issue 本文の `M11_DEST_GUARD=1` は repo に存在しない | 検証方法の記述が無効 | PM 判断 (issue 本文の修正) |
