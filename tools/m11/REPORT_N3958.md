# REPORT_N3958 — run の ptrcheck 件数 69,669 と基準 69,359 の差と全再生成での再測定 (#3958・親 #3129)

既知類型との関係: 該当なし。ハーネスのゲート基準の陳腐化の確認で、lift 欠陥の類型 (docs/DEFECTS.md) には当たらない。

測定 commit: **`26d6d4a03`** (origin/main。コードを変えた最後の commit はこの測定の前の main)。本 PR の変更は `tools/m11/e2e_expect.env` のコメント 1 行だけで、基準値は変えない。

## 1. 結論

- 基準 `M11_EXPECT_PTR_NEW_MAX` は **69,669 のまま正しい**。issue の前提の 69,359 は REPORT_N2778 (測定 commit 9b795530) の古い値で、#3647 で 69,669 に更新済みだった。
- `m11_e2e.sh --full` (Ghidra による `functions_dll.csv` の作成・lift 4 chunk の再実行・boot5 込みの IR 再生成・build・3 実行) で、run `image_va_words_new` = **69,669**・`units_run` = **98**・分類 B = 0 を実測した。survey は 71,001・分類 B = 3 で、既存の基準と一致する。
- 比較できた事実: lift の版 (boot0〜4) と image と data の本体は素材と一致した。素材の IR (`boot_final.ll`) と再生成の IR は、boot5 の 26 関数の有無でも違う。ただし 69,359 の基準 (REPORT_N2778) の IR も boot5 を含むため、boot5 の有無は 310 語の差を説明しない。差の原因は未特定で、二分は未実施 (§5)。

## 2. 測定

| 項目 | 値 |
|---|---|
| 起動 | `FL_WIN64_DIR=<展開先> TMPDIR=$RUNNER_TEMP M11_LB_BASE=0 bash m11_e2e.sh --full` (指紋検査の迂回なし) |
| PE 指紋 | `block00031_PE.bin` sha256 `b2c64da4…` (素材と一致・`work/lift_pe.sha256` を新規記録) |
| 所要 | 21 分 21 秒 (wall)・開始 load 0.48・4 コア・単独実行 |
| e2e rc | **0** |
| IR | `ldfix`・`qstore`・`ld108`・`ld115`・`r8b` = applied・`ir_sha256` `1f1134e3…` |
| run | `image_va_words_pre` 406,576・`image_va_words_new` **69,669**・`units_run` 98・`units_skipped` 3 (計 101)・`unremap_cand` 0 |
| survey | `image_va_words_new` 71,001・`unremap_cand` 3 (基準 3) |
| 寛容起動 | attempted 942・ok 875・noproc 1・skipped 66・gate 合格・NEGCTL 3 本検出 |
| survey ok | 873 (`M11_EXPECT_SURVEY_OK_EXACT` 873 と一致) |
| ゲート | run 69,669 ≤ 69,669 pass・分類 B run 0 ≤ 0 pass・survey 71,001 ≤ 71,001 pass・分類 B survey 3 ≤ 3 pass |

## 3. 素材の成果物との比較 (切り分け)

素材 `work-m11` の成果物 (作業 IR `69c774de…` 前後の版) と、全再生成の成果物を比べた。

| 成果物 | 比較 | 結果 |
|---|---|---|
| `boot0`〜`boot4.lift.ll` | 空行を除いて diff | 0 行 (一致。lift の版差は無い) |
| `m11_image.bin` | sha256 | 一致 (`2d10d692…`) |
| `m11_data.c` | diff | コメント 2 行だけ (本体一致) |
| `boot_final.ll` | 関数定義の差 | 新側に 26 関数多い。すべて boot5 (`m11_extra_ranges5.txt`・25 関数 + 1) 由来。素材の IR は boot5 を含まない版 |
| `boot5.lift.ll` | — | 素材に無い (新規生成) |

- 候補 (a) `tools/m11` の変更: 素材 IR と再生成 IR は boot5 の有無でも違う。一方、69,359 の基準の IR (`de46cada…`) も boot5 を含むため、boot5 の有無だけでは 310 語の差は説明できない。`m11_gen_ir2.sh` 経路の差が本体かは未二分。
- 候補 (b) 素材の lift の版差: boot0〜4 は一致したため、この差は無い。
- 候補 (c) `m11_data.c` の生成器版差: 本体が一致したため、この差は無い。

## 4. 限界

- 素材に prebuilt wasm (`m11_boot.cjs`) はあるが、`units_run` 17・`image_va_words_new` 68,938 の古い版で、今の run とは比較できない。比較に使わなかった。
- 9b795530 の IR (`de46cada…`) を再現して二分する作業は、本 run の範囲に収まらなかった。REPORT_N2778 の 69,359 が現在の IR で再現しない理由は未特定。
- 基準 69,669 は全再生成 1 回の実測 (本 REPORT の §2)。REPORT_3647 §2 は `M11_SKIP_LIFT_FP=1` の経路 (指紋検査の迂回) の測定で、全再生成の確認ではない。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 9b795530 (IR `de46cada…`・run 69,359・units 53) と現 IR (`1f1134e3…`・69,669・units 98) の差の二分 (issue #3958 の受入 1 件目。本 PR では未実施) | 基準の由来の説明のみ。ゲートは現値 69,669 で合格するため回帰判定には影響しない。二分には 9b795530 の IR の再現が要り、1 run に収まらないため本 PR の範囲から外した | 子 issue は起票しない (再測定・原因の追跡だけのため WORKFLOW §3)。PM の判断待ち。issue #3958 の本文からは受入 1 件目を外した |

## 6. 測定 commit からの差分

本 PR のコード変更は `tools/m11/e2e_expect.env` のコメント 1 行だけ。

`git diff 26d6d4a03 -- tools/m11 ':!tools/m11/REPORT_N3958.md'` の出力 (コードの変更は無く、コメント 1 行の追加だけ):

```diff
diff --git a/tools/m11/e2e_expect.env b/tools/m11/e2e_expect.env
index b7247229e..d7781dce9 100644
--- a/tools/m11/e2e_expect.env
+++ b/tools/m11/e2e_expect.env
@@ -12,6 +12,7 @@
 # 基準は実測値 (ratchet。REPORT_N2778.md §8)。69359 までは fresh 再生成 (ir_conditions.json 付き・boot5 込み) の実測。値 0 は正当な LVA 整数のため使えない (§5)。
 # #3647: 69669 は IR 9a9cfa06 の run 実測。同じ IR の fresh 再生成 (ir_conditions.json 付き・m11_run.mjs 直接) でも 69669・units_run 98 (REPORT_N3129.md §3・§4)。#3647 の e2e 測定は lift_pe.sha256 が素材に無いため M11_SKIP_LIFT_FP=1 で指紋検査だけを迂回した (REPORT_3647.md §1)。全再生成 (--full) の確認ではない。
 # #3647: strict の完了数の期待値は #134 で 101 に上がったが、ptr 基準は 69359 (unit 56 時点) のまま据え置かれていた (REPORT_3647.md §3)。
+# #3958: 全再生成 (m11_e2e.sh --full・Ghidra から作り直し) の run 実測も 69669 (units_run 98・IR 1f1134e3…)。基準 69669 は全再生成と一致 (REPORT_N3958.md)。
 : "${M11_EXPECT_PTR_NEW_MAX:=69669}"
 : "${M11_EXPECT_PTR_SURVEY_NEW_MAX:=71001}"
 # #3113: 分類 B (IR のデータ領域 VA 定数が新規 word に VA のまま入った未 remap の疑い) の基準 (ratchet)。
```

注: 測定 commit `26d6d4a03` の時点で `tools/m11` の基準値は測定と同じ。本 PR のコミット後の差分はこのコメント 1 行だけ。
