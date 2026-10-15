# M11 ptrcheck survey の実行と分類 B 基準 (#3129・親 #3113)

親: #3113 (PR #3130 で merge 済み)・#2778・#1004・#403。素材: work-m11 (boot0〜4 の lift・image・旧 wasm)・fl-win64 (`extracted/block00031_PE.bin` のみ展開。sha256 `b2c64da4…`)。IR は素材の `boot_final.ll` を使わず、`m11_gen_ir2.sh` で作り直した。

測定 commit: **`512b09ffa`** (origin/main。`tools/m11`・`tools/shared` は `a5ba5e3f6` (着手時の main) から差分 0)。本 PR のコード変更は `tools/m11/e2e_expect.env` の基準値だけで、survey の測定値には影響しない (§8)。

## 1. 結論

- 受入 1 (survey 用 wasm と IR 来歴): **達成**。`_m11_set_va_unit_budget` を export する wasm (6,047,906 B・sha256 `e3058a84…`) を作った。IR 来歴は `work/ir_conditions.json` に ldfix・qstore・ld108・ld115・r8b = applied、`pe` = `block00031_PE.bin` (sha256 `b2c64da4…`)、`ir_sha256` = `9a9cfa06…`。
- 受入 2 (survey 実測): **達成**。`image_va_words_new` = 71,001 = A 7,611 + B 3 + D 68 + C 63,319。
- 受入 3 (分類 B の survey 基準とネガコン): **達成**。基準 `M11_EXPECT_PTR_SURVEY_UNREMAP_MAX=3` (ratchet)。`m11_ptrcheck_negctl.sh --survey` は `NEGCTL OK`。
- 未解決: survey の分類 B 3 語の由来 (#3957)。run の件数 69,669 が基準 69,359 と合わない原因と全再生成の再測定 (#3958)。

## 2. 手順

1. `tar --zstd -xf fl-win64.tar.zst --wildcards '*block00031_PE.bin'` で PE を展開し、`FL_WIN64_DIR` を指す。
2. `m11_lift.sh m11_extra_ranges5.txt boot5 600` (RetDec・8 s・`boot5.lift.ll` 2,686 行)。
3. `m11_gen_ir2.sh` (46 s・`boot_final.ll` 492,791 行)。boot0〜4 は素材の lift をそのまま使い、再 lift していない。
4. `m11_data_gen.py`・`m11_image_gen.py` で作り直し、`lb_check.py` を通した。image の sha256 は素材と一致 (`2d10d692…`)。`m11_data.c` は素材 (旧生成器) と 2 行目のコメントだけが違う。
5. `m11_build.sh` (23 s) で `work/m11_boot.cjs.wasm` (6,047,906 B) を作った。export 名は wasm では `m11_set_va_unit_budget` (JS 側で `_` が付く)。素材の wasm にはこの export が無い。
6. `m11_ptrclass.py work/boot_final.ll --pe …` で `classes.json` を作った (code 7,447・IR のポインタ定数 (範囲内) 8,835・data 691・D 68)。
7. `M11_PTRCHECK_DUMP=… node m11_survey.mjs` と `m11_ptrclass.py --hits` で分類した。
8. `bash m11_ptrcheck_negctl.sh --survey` を実行した。

**未実行**: `m11_e2e.sh --full` (Ghidra による `functions_dll.csv` の作成と lift 4 chunk の再実行を含む全再生成)。`work/lift_pe.sha256` は書いていない。素材の lift (boot0〜4) が同じ PE 由来であることは PE の指紋が一致することだけを確かめた。

## 3. 実測 (測定 commit 512b09ffa・作業 runner・単独実行・load average 0.13〜0.5)

| 条件 | 結果 |
|---|---|
| `m11_run.mjs` (run) | rc 0・wall 1.49 s・units_run 98・units_skipped 3 (units_total 942)・`image_va_words_new` 69,669 |
| run の分類 | A 7,709・**B 0**・D 68・C 61,892 (合計 69,669) |
| `m11_survey.mjs` (survey) | rc 0・wall 15.0 s・`image_va_words_new` 71,001 (worktree の HEAD でも再現: 71,001) |
| survey の分類 | A 7,611・**B 3**・D 68・C 63,319 (合計 71,001) |
| survey の B 3 語 | 3 語とも値は VA `0x156ee68` (IR の `.data` 定数・使用関数 `function_1375120`)。heap の byte offset は `0x102a0334`・`0x10aa1528`・`0x10aa1538` |
| survey のネガコン (`--survey`) | `NEGCTL OK` (wall 143 s)。`image_va_words_new` は clean 71,001 → 注入 (offset 22519877) 71,002 (+1)。`unremap_cand` は clean 3 → 注入 (値 0x153fb68) 4 (+1)。基準 = clean で exit 0・注入で exit 1 + FAIL 行・非整数で exit 1・分類ファイル欠落で exit 1 |
| run のネガコン | `NEGCTL OK`。`image_va_words_new` clean 69,669 → 注入 69,670 (+1)。`unremap_cand` clean 0 → 注入 1 (+1) |

## 4. 基準の採用

- **survey**: `M11_EXPECT_PTR_SURVEY_UNREMAP_MAX=3`。実測の 3 を置いた ratchet。0 を要求すると現 HEAD は不合格になる。3 語が真の未 remap か、LVA 整数との偶然の一致かは未判定 (#3957)。件数が増えたら不合格になる。
- **run**: `M11_EXPECT_PTR_UNREMAP_MAX=0`。fresh 再生成の run 実測 B = 0 (#3113 の未解決「fresh 再生成での run の分類 B 基準」を閉じる)。
- **run の件数基準 `M11_EXPECT_PTR_NEW_MAX=69359` は変えない**。HEAD の run は 69,669 で、この値のままだと run の ptrcheck ゲートは不合格になる。原因は未特定 (#3958)。survey の件数基準 `M11_EXPECT_PTR_SURVEY_NEW_MAX=71001` は実測と一致する。

## 5. run の件数が REPORT_N2778 と合わない件 (未特定)

- `REPORT_N2778.md` §8.2 (測定 commit 9b795530・fresh 再生成) は run 69,359・units_run 53・IR sha256 `de46cada…`。本測定は run 69,669・units_run 98・IR sha256 `9a9cfa06…`。survey は両方 71,001 で一致した。
- IR の sha256 が違うので、IR は同一ではない。原因の候補は次のとおり (切り分けは未実施)。
  - (a) 9b795530 から origin/main までの `tools/m11` の変更 (非 md で 109 ファイル・`m11_run.mjs` は 4 行変更・`m11_ptrclass.py` は新規)。
  - (b) 素材の lift (boot0〜4) を再 lift していない。9b795530 の測定時の lift と版が違う可能性がある。
  - (c) `m11_data.c` の生成器の版差 (2 行目のコメントだけが違う)。

## 6. 限界

- B は IR の定数として現れる VA だけを見る。計算で作られた VA と、IR に定数の無い VA は判定の外にある。
- 基準は素材 1 組 (fresh 再生成 1 回) の実測値。`m11_e2e.sh --full` (全再生成) では確かめていない (#3958)。
- wasm の sha256 `e3058a84…` は本 runner の build。同じ件数を再現するには同じ IR・同じ image・同じ data が要る。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| survey の分類 B 3 語 (VA `0x156ee68`) の由来 | 基準 3 は ratchet。3 語が真の未 remap なら survey の B ゲートは未 remap 3 件を通している | #3957 ([M11-N203]) |
| run の件数 69,669 ≠ 基準 69,359・units_run 98 ≠ 53・IR sha256 `9a9cfa06…` ≠ `de46cada…` | `e2e_expect.env` の run 件数基準で、e2e の run ゲートが不合格になる (本 PR では基準を変えない) | #3958 ([M11-N204]) |
| `work/lift_pe.sha256` 未記録・`m11_e2e.sh --full` 未実行 | 素材 lift (boot0〜4) の PE 由来は指紋の一致だけで確認。全再生成での件数は未検証 | #3958 (受入 2) |

## 8. 測定 commit からの差分

`git diff 512b09ffa HEAD -- tools/m11 ':!tools/m11/REPORT_N3129.md'` の出力 (本 PR で変えたのは基準値と、その理由を書いたコメントだけ):

```diff
diff --git a/tools/m11/e2e_expect.env b/tools/m11/e2e_expect.env
index 965a71ace..e324af4e5 100644
--- a/tools/m11/e2e_expect.env
+++ b/tools/m11/e2e_expect.env
@@ -12,7 +12,8 @@
 # 基準は fresh 再生成 (ir_conditions.json 付き・boot5 込み) の実測値 (ratchet。REPORT_N2778.md §8)。値 0 は正当な LVA 整数のため使えない (§5)。
 : "${M11_EXPECT_PTR_NEW_MAX:=69359}"
 : "${M11_EXPECT_PTR_SURVEY_NEW_MAX:=71001}"
-# #3113: 分類 B (IR のデータ領域 VA 定数が新規 word に VA のまま入った未 remap の疑い) の基準。未設定 = 情報出力のみ (既定)。
-# 基準は同一 wasm・image・IR の実測値 (ratchet)。本素材の run 実測は分類 B 0 件で合格 (REPORT_N3113.md §3)。fresh 再生成の実測は未実施 (REPORT_N3113.md §6・#3129)。
-: "${M11_EXPECT_PTR_UNREMAP_MAX:=}"
-: "${M11_EXPECT_PTR_SURVEY_UNREMAP_MAX:=}"
+# #3113: 分類 B (IR のデータ領域 VA 定数が新規 word に VA のまま入った未 remap の疑い) の基準 (ratchet)。
+# #3129: fresh 再生成 (ir_conditions.json 付き・boot5 込み) の実測。詳細と基準の根拠は REPORT_N3129.md §3・§4。
+# survey の未 remap 疑いの語の由来は未判定 (#3957)。基準 3 は増加を止めるための値で、真の未 remap かどうかの判定ではない。
+: "${M11_EXPECT_PTR_UNREMAP_MAX:=0}"
+: "${M11_EXPECT_PTR_SURVEY_UNREMAP_MAX:=3}"
```

## 9. 再現

```sh
export FL_WIN64_DIR=<block00031_PE.bin を含む extracted/ の親>
cd tools/m11
bash m11_lift.sh m11_extra_ranges5.txt boot5 600
bash m11_gen_ir2.sh
rm -f work/m11_image.bin work/m11_data.c
python3 m11_data_gen.py "$FL_WIN64_DIR/extracted/block00031_PE.bin"
python3 m11_image_gen.py "$FL_WIN64_DIR/extracted/block00031_PE.bin"
bash m11_build.sh
python3 m11_ptrclass.py work/boot_final.ll --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin"
M11_PTRCHECK_DUMP=work/ptrclass/survey_new.txt node m11_survey.mjs
python3 m11_ptrclass.py --hits work/ptrclass/survey_new.txt
bash m11_ptrcheck_negctl.sh --survey
```
