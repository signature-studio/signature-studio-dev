# Massive X MX-6 (#1123) 付録: 旧測定記録 (REPORT_MX6.md から分割移動)

- 本付録は `REPORT_MX6.md` にあった旧測定の記録を、内容を削らず移したもの。現行の測定値は `REPORT_MX6.md` §1・§7 が正本。
- 各節の値は、その節が示す測定 commit の値。別の commit の値と混ぜて読まない。

## A1. 測定 commit 0dbf9a54d (MX-41 版) の記録 (旧 REPORT_MX6 §1・§7)

- 最後に e2e を実測した commit = **0dbf9a54d** (コードを変えた最後の commit。MX-41 #3792 の集計に除外行の内訳と pefile の section 解決の全件確認を足した版)。再現: `bash tools/targets/massivex/dsp/mx6_e2e.sh` (`MX_PE` で PE を指定)。
- **MX-41 の新版 (分類の関数化・ネガコンの入力書き換え・行ごとの独立照合) は 0dbf9a54d で実測済み** (§1・§3)。旧版 5de22167f のネガコン値は取り消した (§3)。
- MX-41 (#3792・MX-38 の U4b) の追補: 素材は `plugins-massivex` を展開し直した (md5 `622993e7` 一致)。分類の全件表は `REPORT_APPENDIX_3792.md` (0dbf9a54d の出力と全項目一致)。

| 工程 | 結果 |
|---|---|
| NC selftest (合成バイト列) | 5/5 PASS |
| RTTI + 入口面 | seeds 567 / 1-round 3,226 (`dsp/REPORT.md` §2 注の e2e 再現値。同注の mx_closure.py 実測 3,227 とは 1 件違う) / pdata 186,960 (`mx_entry_surface.py` が .text 範囲と `e <= t_hi` で絞った数。§3 の 187,060 は絞らない 1 本目の全 entry で、差 100) |
| vectorcall 検出 | seeds: pdata 始点 livein45 = 0 / one-round: pdata 始点 livein45 = 0 |
| unwind census | 1 本目の .pdata 全体: entry 187,060 / chained 62,526 / EH 23,293 / 読取不能 160 ・ 2 本目: entry 509 / chained 34 / EH 49 / 読取不能 0 (MX-41) |
| funclet | seeds 533 / 和集合 537 / 線形直接参照 4 |
| 判定 | PASS (pdata 始点の vectorcall livein 0 かつ整合 OK) |

- 所要 **23 s** (測定 commit 0dbf9a54d・同一 PE・`OK elapsed=23s`)。load average: 0.72 0.38 0.15 → 0.82 0.43 0.17。全 7 工程 PASS・exit 0。
- MX-41 の判定 (工程 5・6・0dbf9a54d): 1 本目 187,060 / 62,526 / 23,293 / 読取不能 160 (`out_of_image` 160) の維持。2 本目 509 / 34 / 49 / 読取不能 0。独立再計算 (pefile): 読取不能の集合一致 (160 = 160)・行ごとの分類一致 160/160・`get_section_by_rva` の None 160/160・読める行の flags 不一致 0。ネガコン (入力を書き換えて再分類): break `st 000010d0`・ui `06186314` → `49500de8` で +1 (行は `out_of_image`)、fix `st 0002fac0`・ui `49500de8` → `0618ccd0` で −1 (行は除外)。旧版 5de22167f のネガコン値 (160→161・160→159) は入力を変えていなかったため取り消す (§3)。
- 実行: `MX_PE='$RUNNER_TEMP/.../Massive X.vst3' MX6_WORK='$RUNNER_TEMP/massivex-mx6' bash tools/targets/massivex/dsp/mx6_e2e.sh` → exit 0。

- 最後に e2e を実測した commit = **0dbf9a54d** (コードを変えた最後の commit)。`bash tools/targets/massivex/dsp/mx6_e2e.sh` → `OK elapsed=23s`・exit 0 (§1)。
- 実測の出力: repo 外の `$RUNNER_TEMP/mx6_e2e_0dbf9a54d.log`・`$RUNNER_TEMP/massivex-mx6/mx41_pdata2.json`・`mx41_unreadable.tsv`。
- 0dbf9a54d より後の変更は文書のみ (本 REPORT・`REPORT_APPENDIX_3792.md`・PR 本文)。コード範囲の差分:
  `git diff 0dbf9a54d HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx6_e2e.sh` は 0 行 (WORKFLOW §6)。確認した HEAD は PR 本文の検証節に書く。
- 前版 (5de22167f) からのコード差分は 0 行ではない (main 取り込みの `mx33_xmm03.py` 新規・`mx6_vectorcall.py`・工程 4・7 と MX-41 の変更)。そのため 0dbf9a54d で再測定した。
- 素材: `plugins-massivex` を `$RUNNER_TEMP/mx` に展開 (`tar --zstd -xf`) → `parse_setup_headers.py <exe> <work>` → `extract_massivex.py <exe> <work> key` で `Massive X.vst3` (95,356,824 B・md5 `622993e76565f49c094063a2b717d6ca` 一致)。展開 125 件の md5-ok 0/125 は既知事象 (`tools/targets/massivex/REPORT.md` §8.1)。
- レビュー run (head 4bd080b35 の tree で再実行) の参照値 (187,060 / 62,526 / 23,293 / 160・509 / 34 / 49・ネガコン +1 / -1) と 0dbf9a54d の値は一致した。
- 本 run で実行したもの: 上の e2e・`bash -n mx6_e2e.sh`・`python3 -m py_compile mx41_pdata2_census.py`・`pr-lint.sh`。

## A2. 測定 commit 51953f46d・fbc9971f の §1 記録 (main 側の旧 REPORT_MX6 §1)

- 測定 commit = **51953f46d** (e2e の記録があるのはこの commit・§1a・§7)。その後に `mx6_fh4.py` の非挙動の編集 (docstring・未使用変数・`with`) と e2e の step 表記を入れた commit `62e3aefbe` がある。この commit の e2e 再測定は素材 (`plugins-massivex`) が無く本 run では未実施 (§7)。§1b は fbc9971f の旧測定 (参考・削除せず移動)。再現: `bash tools/targets/massivex/dsp/mx6_e2e.sh` (`MX_PE` で PE を指定)。

## 1. 実測 (e2e)

### 1a. 測定 commit 51953f46d (e2e 記録)

本 run では PE (`plugins-massivex`) が無く e2e を再実行していない。以下は 51953f46d の e2e 出力として PR #3815 本文に
記録された値。生ログは REPORT に残っていなかったため、記録が無い工程は「未記録」と書く (推定で埋めない)。

| step (`mx6_e2e.sh`) | 結果 |
|---|---|
| 1/8 NC selftest (合成バイト列・PE 不要) | 5/5 PASS (本 run で HEAD 上でも再確認: `mx6_vectorcall.py --selftest` rc=0) |
| 2/8 RTTI + 入口面 | 未記録 (seeds 567 / 1-round 3,226 は §0・§2 の値。51953f46d の出力としての照合は未了) |
| 3/8 vectorcall | xmm4/5 入口 livein = 0 (pdata 始点・記録) |
| 4/8 受入1 (MX-33) | 17 件 PASS (記録) |
| 5/8 .pdata census | chained 62,526 / EH 23,293 (記録) |
| 6/8 判定 | PASS (記録) |
| 7/8 positive control | funclet 533 / pdata 始点 529 (記録) |
| 8/8 FH4 固定部 | NC 3/3 PASS・entry 2,542 / fi 2,117・固定部 2,540 OK・画像外 2 件 (記録) |
| 所要・exit | exit 0・**43 s**・n=1・並列数 1 (単独直列実行)・load 0.02 0.16 0.18 → 0.57 0.29 0.22 |

### 1b. 参考: fbc9971f の旧測定 (5 step 構成・削除せず移動)

fbc9971f は 51953f46d の祖先だが、e2e の step 構成が違う (旧 5 step・`mx33_xmm03.py` 無し)。下表の値を 51953f46d の値として扱わない。

## A3. 51953f46d → 62e3aefbe の §7 記録 (main 側の旧 REPORT_MX6 §7)

- 測定 commit = **51953f46d** (main 取り込み後の merge・e2e 記録の commit・§1a)。
- 測定後のコード差分: commit `62e3aefbe` (`mx6_fh4.py` の docstring・未使用変数・`with`、`mx6_e2e.sh` の step 表記 /7→/8 のラベル)。
  出力 (`git diff -U0 51953f46d HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx6_e2e.sh`・`index` 行は省略):

```diff
diff --git a/tools/targets/massivex/dsp/mx6_e2e.sh b/tools/targets/massivex/dsp/mx6_e2e.sh
--- a/tools/targets/massivex/dsp/mx6_e2e.sh
+++ b/tools/targets/massivex/dsp/mx6_e2e.sh
@@ -17 +17 @@ T0=$(date +%s)
-echo "== 1/7 NC: 合成バイト列の正例・負例 (PE 不要)"
+echo "== 1/8 NC: 合成バイト列の正例・負例 (PE 不要)"
@@ -20 +20 @@ python3 "$DSP/scripts/mx6_vectorcall.py" --selftest | sed 's/^/   /'
-echo "== 2/7 RTTI + VST3 入口面 (seeds 567 / 1-round closure)"
+echo "== 2/8 RTTI + VST3 入口面 (seeds 567 / 1-round closure)"
@@ -25 +25 @@ python3 "$DSP/scripts/mx_entry_surface.py" "$PE" "$W/rtti_vtables.json" "$W/surf
-echo "== 3/7 vectorcall 静的検出 (本体: CFG must-def / 独立再計算: 線形 anyref / 感度: 非 begin 入口)"
+echo "== 3/8 vectorcall 静的検出 (本体: CFG must-def / 独立再計算: 線形 anyref / 感度: 非 begin 入口)"
@@ -28 +28 @@ python3 "$DSP/scripts/mx6_vectorcall.py" "$PE" "$W/surface_seeds_x64c.json" "$W/
-echo "== 4/7 受入1 (MX-33 #3032): xmm0〜3 だけの入口 livein 保留 17 件の判定 (NC 9 件・独立再計算・感度)"
+echo "== 4/8 受入1 (MX-33 #3032): xmm0〜3 だけの入口 livein 保留 17 件の判定 (NC 9 件・独立再計算・感度)"
@@ -32 +32 @@ grep -v '^| ' "$W/xmm03.log" | sed 's/^/   /'
-echo "== 5/7 .pdata unwind census (CHAININFO / EH handler 名)"
+echo "== 5/8 .pdata unwind census (CHAININFO / EH handler 名)"
@@ -36 +36 @@ python3 "$DSP/scripts/mx6_pdata_eh.py" "$PE" "$W/surface_seeds_x64c.json" "$W/su
-echo "== 6/7 判定 (期待値: seeds と 1-round の pdata 始点で xmm4/5 入口 livein = 0 / 受入1 の内訳が 17 件)"
+echo "== 6/8 判定 (期待値: seeds と 1-round の pdata 始点で xmm4/5 入口 livein = 0 / 受入1 の内訳が 17 件)"
@@ -48 +48 @@ PY
-echo "== 7/7 positive control: funclet 数の固定値 (MX-6 測定値 seeds 533 / pdata 始点 529 が変わらないこと)"
+echo "== 7/8 positive control: funclet 数の固定値 (MX-6 測定値 seeds 533 / pdata 始点 529 が変わらないこと)"
diff --git a/tools/targets/massivex/dsp/scripts/mx6_fh4.py b/tools/targets/massivex/dsp/scripts/mx6_fh4.py
--- a/tools/targets/massivex/dsp/scripts/mx6_fh4.py
+++ b/tools/targets/massivex/dsp/scripts/mx6_fh4.py
@@ -59,3 +59,2 @@ def validate(rd, fi, in_image):
-    """固定部の検査 (独立した 3 条件): (a) 固定部が読める (BBT なし) (b) 各ポインタが画像内 (c) ポインタの順序が
-    構造の並び (dispUnwindMap < dispTryBlockMap < dispIPtoStateMap は必須ではないが、各ポインタは重ならない)。
-    戻り値は違反の list (空なら OK)。"""
+    """固定部の検査 (独立した 3 条件): (a) 固定部が読める (BBT なし) (b) 各ポインタが画像内 (c) 固定部のポインタ値が
+    互いに重複しない (同値の検出のみ。範囲の重なりは見ない)。戻り値は違反の list (空なら OK)。"""
@@ -68 +67 @@ def validate(rd, fi, in_image):
-    for n, (o, v) in f.items():
+    for n, (_, v) in f.items():
@@ -85 +84 @@ def image_checker(pe):
-def fh4_entries(pe, data, rd):
+def fh4_entries(pe, rd):
@@ -117 +116,2 @@ def census(pe_path):
-    data = open(pe_path, 'rb').read()
+    with open(pe_path, 'rb') as fp:
+        data = fp.read()
@@ -120 +120 @@ def census(pe_path):
-    base, rows = fh4_entries(pe, data, rd)
+    base, rows = fh4_entries(pe, rd)
@@ -149 +149,3 @@ def census(pe_path):
-KNOWN_OPEN = 2  # 画像外の dispUnwindMap を持つ 2 件 (原因未確定・REPORT_MX6 §8)
+# 画像外の dispUnwindMap を持つ 2 件 (原因未確定・REPORT_MX6 §8)。解消すると正例が FAIL するので、
+# 解消したら KNOWN_OPEN と REPORT_MX6 §8 を同じ commit で更新する。
+KNOWN_OPEN = 2
```

- 再測定 (未了): commit `62e3aefbe` の e2e は本 run で PE が無く未実行。HEAD で再確認したのは PE 不要の step 1 のみ (`mx6_vectorcall.py --selftest` 5/5 PASS・rc=0)。
  `mx6_fh4.py` は旧版との AST 比較で、差分が docstring・未使用変数の削除・`with` 化だけであることを確認 (挙動は変えない)。
  step 8 の selftest と census は PE が必要で未実行。素材を付けた review run で照合する。
- 検証 (測定 commit 51953f46d の記録): e2e 全件 PASS・exit 0 (§1a)。NC selftest は step 1 (5/5)・step 4 (9/9)・step 8 (3/3) すべて PASS (記録)。

