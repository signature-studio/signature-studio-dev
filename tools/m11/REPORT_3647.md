# REPORT_3647 — e2e rc=1 の残件 (完了数・survey exact・通常起動の ptr 基準超過) の原因特定 (#3647)

既知類型との関係: 該当なし。ハーネスのゲート基準の陳腐化で、lift 欠陥の類型 (docs/DEFECTS.md) には当たらない。分類 B (未 remap VA) は 0 件 (§2)。DEFECTS.md の全類型との照合はしていない。

**結論 (3 行)**
- **(c) ptr 超過が rc=1 の唯一の原因**。基準 69359 は strict 通常起動が unit 56 で止まる時点の ratchet で、strict の完了数の期待値が #134 で 101 に上がったあとも据え置かれていた。基準を 69669 に更新した。69669 は REPORT_N3129 §3・§4 の fresh 再生成 (同じ IR `9a9cfa06`) でも同じ値。分類 B の基準は main (#3129) の値 (run 0・survey 3) を使い、本 PR では変えない。測定 commit `d66eb7c34` (main `f0899c773` 取り込み後) で e2e rc=0。
- **(a) 完了数 101 ≠ 期待 56 は現 main に存在しない**。56 は #2714 時の pin で、#134 (`f70a4b6ba`・`fd5f58f09`) が 101 に更新済み。本測定も 98+3=101 で一致。56 → 101 は停止点の後退 (改善)。それを生んだ commit は未二分。
- **(b) survey ok 873 ≠ 期待 872 は取り違えの値**。872 は `M11_FIX_50A830=1` (ON) の値。既定 clean は 873 で pin 873 と一致。#2714 時の 872 と環境差 (872〜874) は未切り分け。

## 1. 測定条件

- 測定 commit: `d66eb7c34` (コードを変えた最後の commit。main `f0899c773` を merge した `c3d3faa35` の後に、`e2e_expect.env` のコメントだけを直した)。その後の差分は本 REPORT の commit のみ。
- 69669 の由来は 2 つ。(i) REPORT_N3129 §3・§4 の fresh 再生成 (`m11_run.mjs` 直接・同じ IR `9a9cfa06`・units_run 98・分類 B 0)。(ii) 本 PR の e2e 測定 (下の参考値)。
- 本 PR の e2e 測定は参考値の範囲: `tools/m11/work/lift_pe.sha256` と `ir_conditions.json` が素材に無い。既定経路は指紋検査で止まるため、`M11_SKIP_LIFT_FP=1` で指紋検査だけを迂回した (#2779 の参考値経路)。全再生成 (`--full`) は行っていない。(i) は fresh 再生成の実測 (指紋検査の迂回なし・ir_conditions.json 付き) で、(ii) は e2e の経路を通した実測。値の一致は両方の経路で同じ 69669 が出ることを示す。
- 素材: `work-m11` を `tools/m11/work/`、`work-liftdiff` を `tools/liftdiff/work/` に展開。`fl-win64` は `extracted/block00031_PE.bin` (sha256 `b2c64da4…`) のみを `$RUNNER_TEMP/fl-win64/` に展開。toolchain (emcc・retdec) は runner に有り。
- 測定の起動: `cd tools/m11 && M11_SKIP_LIFT_FP=1 M11_LB_BASE=0 FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash m11_e2e.sh`
- IR: `m11_gen_ir2.sh` で再生成 (main の `m11_passes.py` を含む)。e2e 内で boot5 を足すと `ir_sha256` は `9a9cfa06…` (以後の測定はすべてこの IR)。
- 負荷: 開始時の `uptime` は load 0.43 (1 分)・並列 1 (4 コア)。

## 2. 実測

| 測定 | tree | strict 完了 (units_run + skipped) | survey ok / trap / miss / noproc | survey ptr (max 71001) | run ptr (max) | run 分類 B (unremap_cand) | 寛容起動 | e2e rc |
|---|---|---|---|---|---|---|---|---|
| (1) 修正前の pin で e2e | 512b09ffa | 98 + 3 = 101 | 873 / 22 / 46 / 1 | 71001 pass | **69669 FAIL** (max 69359) | 0 (gate 未設定) | attempted 942・ok 875・noproc 1・skipped 66 | **1** |
| (2) 基準のみ override (69669・分類 B 0) | 512b09ffa | 101 | 873 / 22 / 46 / 1 | 71001 pass | 69669 pass | 0 pass | 同上 | 0 |
| (3) 前版 (分類 B 基準 0 を設定していた版・撤回) | e7131890b | 101 | 873 / 22 / 46 / 1 | 71001 pass | 69669 pass | 0 pass (max 0) | 同上 | 0 |
| (4) 前版の最終 (分類 B 基準は未設定) | 8a1c7eafd | 98 + 3 = 101 | 873 / 22 / 46 / 1 | 71001 pass | 69669 pass (max 69669) | 0 (情報のみ・gate 無し) | attempted 942・ok 875・noproc 1・skipped 66 | 0 |
| (5) **最終 (測定 commit `d66eb7c34`・main の分類 B 基準 0 / 3 を有効化)** | d66eb7c34 | 98 + 3 = 101 | 873 / 22 / 46 / 1 | 71001 pass (max 71001) | 69669 pass (max 69669) | **0 pass (max 0)** | attempted 942・ok 875・noproc 1・skipped 66 | **0** |

- (5) の実測 (`work/e2e_full.out`・`work/e2e_survey.out` の ptrcheck JSON): run `image_va_words_new` 69669・`unremap_cand` 0・`gate.pass` true (run)。survey `image_va_words_new` 71001・`unremap_cand` 3・`gate.pass` true (survey max 3)。寛容起動 `M11_TOLERANT gate` は合格・NEGCTL 3 本検出。
- (5) の所要: e2e 全体 wall 182 秒・開始 load 0.43 (IR 再生成・boot5・build・3 実行を含む)。
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
- 69669 の出所: `REPORT_N3129.md` は、IR `9a9cfa06` の fresh 再生成 (ir_conditions.json 付き・指紋検査の迂回なし) で run `image_va_words_new` = 69,669 (`units_run` 98・分類 B 0) を実測している。本 REPORT の e2e 測定 (§2) は同じ 69669 を、指紋検査だけを `M11_SKIP_LIFT_FP=1` で迂回して得た。2 つの経路の違いは、前者が fresh の指紋検査を通すのに対し、後者は素材に無い `lift_pe.sha256`・`ir_conditions.json` を迂回する点だけ。`REPORT_N134.md` §18 の 69668 (#134 時点の IR) とは 1 差で、IR の版差と推定。
- 対応: 基準を 69669 に上げる (ratchet の方針どおり)。境界は §2 で確認。分類 B の基準は main の #3129 の値 (run 0・survey 3) をそのまま使う。本 PR では分類 B の基準を変えない。

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

- 測定 commit: `d66eb7c34`。その後の差分は本 REPORT の commit のみ (`tools/m11/REPORT_3647.md`)。
- main `f0899c773` の取り込み (`c3d3faa35`・競合なし) と測定 commit の間の `tools/m11` の差分 (`git diff bf3e0160c HEAD -- tools/m11 ':!*.md'` の numstat):

```
$ git diff --numstat bf3e0160c d66eb7c34 -- tools/m11 ':!*.md'
1	1	tools/m11/e2e_expect.env
31	0	tools/m11/m11_passes.py
262	0	tools/m11/m11_setother_nonimm_cfg.py
58	0	tools/m11/m11_setother_nonimm_cfg_check.py
```

- `m11_passes.py` は `m11_gen_ir2.sh` (IR 生成) から呼ばれる。e2e 経路に入るため、取り込み後の HEAD で e2e を再測定した (§2 (5))。`m11_setother_nonimm_cfg*.py` は e2e 経路から参照されない。
- 測定 commit `d66eb7c34` から現 HEAD までの `tools/m11` の差分 (REPORT_3647.md を除く):

```
$ git diff --numstat d66eb7c34 HEAD -- tools/m11 ':!tools/m11/REPORT_3647.md'
(空 = 0 行)
```
- `git diff --stat bf3e0160c d66eb7c34 -- tools/m11` の実出力 (main 取り込み分 + 本 PR の変更):

```
 tools/m11/REPORT_N171.md                   |   1 +
 tools/m11/REPORT_N172.md                   | 132 +++++++++++++++
 tools/m11/e2e_expect.env                   |   2 +-
 tools/m11/m11_passes.py                    |  31 ++++
 tools/m11/m11_setother_nonimm_cfg.py       | 262 +++++++++++++++++++++++++++++
 tools/m11/m11_setother_nonimm_cfg_check.py |  58 +++++++
 6 files changed, 485 insertions(+), 1 deletion(-)
```

- この範囲の `e2e_expect.env` の差分は #3647 の注釈コメント 1 行だけ (値 69669 は `bf3e0160c` で設定済み)。`m11_setother_nonimm_cfg*.py` は e2e 経路 (`m11_e2e.sh`・`m11_gen_ir2.sh`) から参照されない (grep 確認)。
- 負例: §2 の境界 (69668 で FAIL)・`m11_ptrcheck_negctl.sh` (NEGCTL OK・最終 commit)・寛容起動の NEGCTL 3 本 (最終 commit の e2e 出力)。
- 範囲外: 全再生成 (`--full`)・lift の指紋検査 (`lift_pe.sha256`)・unit 単位の増分測定・commit の二分・survey の分類 B 3 語の由来 (#3957)・run の全再生成での再確認 (#3958)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (c) ptr 増分 +310 の unit 単位の直接測定 (途中停止の手段が `m11_run.mjs` に無い) | 「units 57〜101 の書込みが増分を生んだ」は時期の一致による推定。分類 B 0 は未 remap 混入が無いことしか示さない | #3520 (親) へコメント |
| (a) 56 → 101 (停止点の後退) を生んだ commit の二分 | 改善の由来の commit が特定できない | #3520 へコメント |
| (b) pin 872 (#2714 時) の出所と環境差 872〜874 | 既定 clean の期待値が環境で動き得る | #3520 へコメント |
| survey の分類 B 3 語 (VA `0x156ee68`) の由来。分類 B 基準 (survey 3) は ratchet | 3 語が真の未 remap なら survey の B ゲートは未 remap 3 件を通している | #3957 |
| run の件数 69669 の全再生成 (`m11_e2e.sh --full`) での再確認。main の run 件数基準 69359 の失敗の未特定 | 69669 は fresh 再生成 (N3129) と本 PR の e2e 経路で一致するが、全再生成の e2e では未確認 | #3958 |
| 指紋検査 (`lift_pe.sha256`・`ir_conditions.json`) が素材に無く、本 PR の e2e 測定は `M11_SKIP_LIFT_FP=1` の参考値 | 受入の根拠には全再生成 (`--full`・約 22 分) が要る | #3122 (全再生成 IR の survey) |
| IR の sha256 の版差 (`bcfda317`・`9a9cfa06` など) | ptr 基準の由来が IR の版で動き得る | #3129 (IR 来歴の記録) |
