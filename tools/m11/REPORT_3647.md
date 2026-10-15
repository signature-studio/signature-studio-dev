# REPORT_3647 — e2e rc=1 の残件 (完了数・survey exact・通常起動の ptr 基準超過) の原因特定 (#3647)

既知類型との関係: 該当なし。ハーネスのゲート基準の陳腐化で、lift 欠陥の類型 (docs/DEFECTS.md) には当たらない。分類 B (未 remap VA) は 0 件 (§2)。DEFECTS.md の全類型との照合はしていない。

**結論 (3 行)**
- **(c) ptr 超過が rc=1 の唯一の原因**。基準 69359 は strict 通常起動が unit 56 で止まる時点の ratchet で、strict の完了数の期待値が #134 で 101 に上がったあとも据え置かれていた。基準を 69669 に更新した (snapshot 実測。canonical fresh 実測は 69668 で 1 差)。分類 B の基準は未設定のまま (fresh 未実測のため 0 を置かない・#3129)。測定 commit `8a1c7eafd` で e2e rc=0。
- **(a) 完了数 101 ≠ 期待 56 は現 main に存在しない**。56 は #2714 時の pin で、#134 (`f70a4b6ba`・`fd5f58f09`) が 101 に更新済み。本測定も 98+3=101 で一致。56 → 101 は停止点の後退 (改善)。それを生んだ commit は未二分。
- **(b) survey ok 873 ≠ 期待 872 は取り違えの値**。872 は `M11_FIX_50A830=1` (ON) の値。既定 clean は 873 で pin 873 と一致。#2714 時の 872 と環境差 (872〜874) は未切り分け。

## 1. 測定条件

- 測定 commit: `8a1c7eafd` (`tools/m11/e2e_expect.env` のみ変更。PR の親 `b5bb75903` は origin/main `8cc728a74` の取り込み merge)。
- 69669 の測定 (§2 (1)(2)) は PR の元の base `512b09ffa` で行った。`512b09ffa` から `8a1c7eafd` までの `tools/m11` の実行コードの差分は main の分析スクリプトの追加のみで、e2e の経路 (`m11_e2e.sh`・`m11_run.mjs`・`m11_survey.mjs`・`m11_ptrcheck*`・`m11_ptrclass.py`・生成と build) からは呼ばれない (§4)。
- 素材: `work-m11` を `tools/m11/work/`、`work-liftdiff` を `tools/liftdiff/work/` に展開。`fl-win64` は `extracted/block00031_PE.bin` (sha256 `b2c64da4…`) のみを `$RUNNER_TEMP/fl-win64/` に展開。toolchain (emcc・retdec) は runner に有り。
- 測定の起動: `M11_SKIP_LIFT_FP=1 M11_LB_BASE=0 FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/m11_e2e.sh`
- **参考値の範囲**: `tools/m11/work/lift_pe.sha256` と `ir_conditions.json` が素材に無い。既定経路は全再生成 (Ghidra + RetDec 4 chunk) に入るため、`M11_SKIP_LIFT_FP=1` で指紋検査だけを迂回した (#2779 の参考値経路)。全再生成は行っていない。よって 69669 は snapshot 実測で、fresh 再生成の実測ではない。
- IR: `m11_gen_ir2.sh` で再生成。e2e 内で boot5 を足すと `ir_sha256` は `9a9cfa06…` (以後の測定はすべてこの IR)。
- 負荷: 開始時の `uptime` は load 0.66 (1 分)・並列 1 (4 コア)。

## 2. 実測

| 測定 | tree | strict 完了 (units_run + skipped) | survey ok / trap / miss / noproc | survey ptr (max 71001) | run ptr (max) | run 分類 B (unremap_cand) | 寛容起動 | e2e rc |
|---|---|---|---|---|---|---|---|---|
| (1) 修正前の pin で e2e | 512b09ffa | 98 + 3 = 101 | 873 / 22 / 46 / 1 | 71001 pass | **69669 FAIL** (max 69359) | 0 (gate 未設定) | attempted 942・ok 875・noproc 1・skipped 66 | **1** |
| (2) 基準のみ override (69669・分類 B 0) | 512b09ffa | 101 | 873 / 22 / 46 / 1 | 71001 pass | 69669 pass | 0 pass | 同上 | 0 |
| (3) 前版 (分類 B 基準 0 を設定していた版・撤回) | e7131890b | 101 | 873 / 22 / 46 / 1 | 71001 pass | 69669 pass | 0 pass (max 0) | 同上 | 0 |
| (4) **最終 (HEAD の測定・分類 B 基準は未設定)** | 8a1c7eafd | 98 + 3 = 101 | 873 / 22 / 46 / 1 | 71001 pass | 69669 pass (max 69669) | 0 (情報のみ・gate 無し) | attempted 942・ok 875・noproc 1・skipped 66 | **0** |

- (4) の所要: e2e 全体 wall 154 秒 (IR 再生成・boot5・build・3 実行を含む)。
- 境界 (run・`node m11_run.mjs`・(3) で測定): 基準 69669 → rc 0 / 基準 69668 → rc 1 (`FAIL: ptrcheck image_va_words_new=69669 > max=69668`)。ptr の判定コードは (3) から (4) で変わっていない (§4)。
- 分類 B (run・(4)): `unremap_cand` 0・`image_copy` 68・`other` 61892 (`tools/m11/work/e2e_full.out` の `ptrcheck.unremap`)。`"gated":false` のため情報のみで、判定は `gate.pass`。JSON の top-level `ok` は `image_va_words_new === 0` の意味で、判定には使わない。
- 負例 (最終 commit): `bash m11_ptrcheck_negctl.sh` → `NEGCTL OK`。clean `image_va_words_new=69669`・注入 `69670` (diff 1)。`unremap_cand` clean 0・注入 `0x153fb68` で 1。基準を与えると、クリーンで exit 0・注入で exit 1 + FAIL 行。
- 寛容起動の gate (最終 commit の e2e 出力): `TOLERANT_GATE_FAILED` 無し・NEGCTL 3 本 (attempted-1・strict_done-1・survey_ok-1) すべて検出。

## 3. 原因

### (c) 通常起動の ptr 69669 > 基準 69359

- 基準 69359 の出所: `REPORT_N2778.md` §8.2 (fresh 再生成・ゲート無しの `m11_run.mjs` ×3 で `units_run 53 + units_skipped 3 = 56`・`image_va_words_new 69,359`・3 回一致) と §8.3 (基準の採用)。ratchet はこの時点の値。
- strict 完了数の期待値は #134 (`f70a4b6ba`・`fd5f58f09`) で 101 に上がった。ptr は同じ #134 の canonical 再測定で `69668 > 69359` と記録され (`REPORT_N134.md` §18・「+309 の原因は未分析」)、基準は据え置かれたまま未分析で残った。
- 分類 B (`unremap_cand`) は 0 件 (§2)。分類 B は IR のデータ領域 VA 定数が VA のまま新規 word に入った未 remap の疑いを数える (`REPORT_N3113.md`)。増分 +310 は分類 B に当たらない。
- 因果の度合い: **推定**。strict の進行 (unit 56 → 101) と ptr 増分 (+309 at #134・+310 now) が同時期に現れた。unit 単位で増分を直接測ってはいない (`m11_run.mjs` に途中停止の手段が無い。§5)。
- 69669 の出所: snapshot 実測 (`M11_SKIP_LIFT_FP=1`・fresh 未実施)。同じ 101 unit の fresh canonical 実測は `REPORT_N134.md` §18 の 69668 で、1 差。IR の版差 (`9a9cfa06` と #134 時の IR) と推定。`REPORT_3520.md` の 69669 は IR `bcfda317` での値で、今回の IR `9a9cfa06` でも同じ 69669 だった。
- 対応: 基準を 69669 に上げる (ratchet の方針どおり)。境界は §2 で確認。分類 B の基準は**設定しない** (未設定のまま)。fresh の分類 B 件数が未実測のため、0 を置くと根拠の無いゲートになる。基準化は #3129 の fresh 実測後。

### (a) 完了数 101 ≠ 期待 56

- 56 は `REPORT_N2714.md` (#2714 時の pin)。`REPORT_N2768.md` でも 56。
- 現 main の `e2e_expect.env` は `M11_EXPECT_STRICT_DONE:=101` (#134 `f70a4b6ba`・`fd5f58f09` で更新済み)。`m11_tolerant_gate.py` に 56 は無い。
- 本測定の strict 完了数は 98 + 3 = 101 で、pin と一致。よって不一致は現 main には無い。**期待値の陳腐化** (#2714 の pin の残存) が原因で、実測の回帰ではない。
- 56 → 101 は停止点の後退 (unit 57 → 98 で trap)。改善方向。それを生んだ commit は未二分 (§5)。

### (b) survey ok 873 ≠ 期待 872

- 872 は `M11_FIX_50A830=1` (ON) の clean build の値 (`REPORT_3520.md` §2 の行 2)。既定の ov.o を作る stamp は `work/ov_50a830.stamp` で管理済み (`68b9de191`)。
- 本測定は stamp の値 `0` (既定) で build。survey ok = 873 で、pin `M11_EXPECT_SURVEY_OK_EXACT:=873` と一致。
- よって (b) の不一致は、ON build の ov.o を既定の測定が再利用したことによる取り違えで、stamp の修正で解消済み。pin 872 の出所 (#2714 時の環境) と、環境で 872〜874 に動く理由は未切り分け (§5)。

## 4. 検証

- 測定 commit: `8a1c7eafd`。その後の差分は本 REPORT の commit のみ (`tools/m11/REPORT_3647.md`)。コードの差分 0 行:

```
$ git diff --stat 8a1c7eafd HEAD -- tools/m11
 tools/m11/REPORT_3647.md | 69 +++++++++++++++++++++++++++++-------------------
 1 file changed, 42 insertions(+), 27 deletions(-)
$ git diff --numstat 8a1c7eafd HEAD -- tools/m11 ':!tools/m11/REPORT_3647.md' | wc -l
0
```

- (3) → (4) の env の差 (判定の基準): `git diff --numstat e7131890b 8a1c7eafd -- tools/m11/e2e_expect.env` は `5 3` (基準のコメントと分類 B 基準の撤回。`M11_EXPECT_PTR_NEW_MAX` の値は両方 69669)。
- main 取り込み分 (`512b09ffa` 以降の `tools/m11` の実行コード): `git diff --numstat 512b09ffa 8a1c7eafd -- tools/m11 ':!*.md'` は分析スクリプト 5 件 (`ldfix/dyn_ld143_2987.mjs`・`ldfix/prod_order_3608.sh`・`m11_setother_mem_class.py`・`m11_unit_map.py`・`trap_triage/native_zeroinit_2891.py`) と xmm 基準 JSON 3 件の追加。`tools/m11/*.sh`・`*.mjs`・`*.py`・`ldfix/*.sh` を grep して、e2e の経路からの参照は無いことを確認した。`m11_ptrcheck.mjs` と `m11_ptrclass.py` は変更されていない。
- 負例: §2 の境界 (69668 で FAIL)・`m11_ptrcheck_negctl.sh` (NEGCTL OK・最終 commit)・寛容起動の NEGCTL 3 本 (最終 commit の e2e 出力)。
- 範囲外: 全再生成 (`--full`)・lift の指紋検査 (`lift_pe.sha256`)・unit 単位の増分測定・commit の二分・survey の分類 B (#3129)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (c) ptr 増分 +310 の unit 単位の直接測定 (途中停止の手段が `m11_run.mjs` に無い) | 「units 57〜101 の書込みが増分を生んだ」は時期の一致による推定。分類 B 0 は未 remap 混入が無いことしか示さない | #3520 (親) へコメント |
| (a) 56 → 101 (停止点の後退) を生んだ commit の二分 | 改善の由来の commit が特定できない | #3520 へコメント |
| (b) pin 872 (#2714 時) の出所と環境差 872〜874 | 既定 clean の期待値が環境で動き得る | #3520 へコメント |
| 分類 B の基準化 (fresh 再生成で run の分類 B を実測し `M11_EXPECT_PTR_UNREMAP_MAX` に設定) | e2e の分類 B ゲートが既定で無効 (情報のみ) | #3129 (N3113 §7 から継続) |
| 指紋検査 (`lift_pe.sha256`・`ir_conditions.json`) が素材に無く、既定の e2e 経路を通していない。rc=0 は参考値 (#2779 の定義) | 受入の根拠には全再生成 (`--full`・約 22 分) が要る | #3122 (全再生成 IR の survey) |
| IR の sha256 の版差 (`bcfda317`・`9a9cfa06` など) | ptr 基準の由来が IR の版で動き得る | #3129 (IR 来歴の記録) |
