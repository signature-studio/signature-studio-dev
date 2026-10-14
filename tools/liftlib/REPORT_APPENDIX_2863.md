# liftlib 付録 — #2863: p1_legacy の IR 一致ゲートが #1664 (A7 空行除去) 後に FAIL する原因の確定と修復

- 日付: 2026-10-14 / issue #2863 (`[PLG-F3-32]`) / 親 #2094 / 担当: `tools/liftlib/` (`liftlib/recipes/ott.py`・`liftlib/passes/p1_legacy.py`・`tests/test_unit.py`)
- 既知類型との関係: 該当なし (`docs/DEFECTS.md` D1a〜D23 のどれにも当たらない。意味の差ではなく SSA 一時名の差)
- 測定 commit (コードを変えた最後の commit): `054ee527` (`fix(liftlib): ignore %pc temp-name renumbering in IR gate (#2863)`)。
  `git diff 054ee527 HEAD -- tools/liftlib/liftlib tools/liftlib/tests tools/liftlib/liftlib_e2e.sh` の出力は空 (本付録の追加以降はコード差分 0)。
- 修復前の測定 base: `13fcecca` (origin/main 取込み時点・修復前)。作業 worktree: `../ws-2863` (`2863-liftlib-p1-gate`)。素材 (gitignore 対象の `work/`) は本体の展開済みを `cp -a` で複写した。

## 0. 結論 (先出し)

| 項目 | 結果 (実測) |
|---|---|
| 原因 | `p1_legacy.legacy_p1` の一時名 `%pc<入力行 index>` が、#1664 (A7 の空行除去) で変わった行 index に依る。名前だけが変わり、命令と分岐は不変 (名前を正規化した比較の差分は 0 行。§2) |
| 修復 | IR 一致ゲート (`ott.same`) の比較前に、`%pc` 一時名の出現順の全単射な改名 (`p1_legacy.canon_tags`) だけを両辺へ適用。ゲートの他の部分と `p1_legacy` 本体は変えていない |
| `python3 -m liftlib ott --auto none` | 修復前 **FAIL** (IR 一致 O2a〜O4 の 6 項目が false・11.76 s) → 修復後 **PASS** (全 7 項目 true・e2e checks 8/0・出力 SHA 42/42 一致・n=3 で 10.88〜10.94 s) |
| `python3 -m liftlib ott` (既定 auto f7,p1) | PASS (census junkHi 104 ≤ 104・e2e checks 8/0) |
| `bash tools/liftlib/liftlib_e2e.sh --quick` 全体 | **未達**。FA/KH の素材 (`work-liftlib-targets`・`plugins-freshair`・`plugins-kilohearts`) が本 run に無く、前提検査で rc=2 (§4)。素材を足して再実行するまで、受入条件の `--quick` ALL PASS は未確認 |

## 1. 修復前の再現 (base `13fcecca`・`ott --auto none`)

| 項目 | 修復前 (`13fcecca`) | 修復後 (`054ee527`) |
|---|---|---|
| 結果 | FAIL (rc=1) | PASS (rc=0) ×3 |
| real (n) | 11.755 s (n=1) | 10.88 / 10.90 / 10.94 s (n=3) |
| O1 base vs m6 `ott_lift.ll` | true | true |
| O2a p1 / O2b shift / O2c gdata | false / false / false | true / true / true |
| O3a memfix0 / O3b memfix1 / O4 m10 | false / false / false | true / true / true |
| e2e checks / broken | 8 / 0 | 8 / 0 |
| band maxdev / nbad / trap rc | 0.0 / 0 / 0 | 0.0 / 0 / 0 |
| 出力 SHA (42 組合せ・f0 21/21) | equal: true | equal: true |

- 負荷: 起動直前の `uptime` の load average (1/5/15 分) = 0.49 / 0.71 / 0.46、nproc = 4。計測は単独 run (並列なし)。
- 修復前の値は `work/cab2863/base_ott_none.log`、修復後は `work/cab2863/fix_none_run{1,2,3}.log` (本体 `tools/liftlib/work/` は gitignore 対象)。

## 2. 原因の切り分け (`--auto none` の O1〜O2a)

手順は `ott.run` と同じ経路 (`B.run_base` → `IR.Module.parse` → `dump(strip=True)` → `p1_legacy.legacy_p1`)。

- **O1 は一致**: 空行を除いて比べると、`base` の出力は `m6/work/ott_lift.ll` と一致 (nb 一致 true)。
- **空行の数**: 参照 `m6/work/ott_lift.ll` は 25158 行中 2459 行が空行。A7 後の lift は 24816 行中 2117 行が空行。A7 が除いた空行は **342 行**。
- **O2a の差分は名前だけ**: 参照 `m6/work/ir7e_p1.ll` と比べると、差分は `%pc1659…` → `%pc1657…` のような番号のずれ。名前を `%pc\d+` → 出現順の番号へ改名して比べると、非空行 **22878 行** が一致し、意味的な差分は **0 行**。`p1_legacy` の挿入数は両者とも 18 (br_cf 16・br_zf 1・or_cfzf 1)。
- **行 index への依存**: `legacy_p1` は `tag = 'pc%d' % idx` (入力テキストの行 index) を使い、呼び出し直後の 12 行の窓 (`idx + 13`) を見る。A7 で行 index がずれるため、名前が変わる。窓の結果は本入力では変わらなかった (挿入数が一致)。
- 別経路の確認: 元の空行入り `ott_lift.ll` を入力にした `tests/test_unit.py` T2 は p1 の出力を**完全一致**で比べ、従来どおり PASS。

## 3. 修復の内容

- `liftlib/passes/p1_legacy.py`: `canon_tags(text)` を追加。`%pc<番号><接尾>` の番号を、テキスト中の出現順 (最初に現れた順) に `0, 1, 2, …` へ振り直す。出現順の対応は全単射なので、2 つの文が「一方の一時名を他方の一時名へ一対一に付け替えて一致する」ときだけ、改名後に一致する。
- `liftlib/recipes/ott.py` `same()`: 比較前に両辺へ `canon_tags` を適用。O1 は `%pc` を含まないので影響しない。
- `tests/test_unit.py` T26 (新規):
  1. 空行を除いた `ott_lift.ll` を `legacy_p1` に通すと、出力は参照と**文字列として異なる** (前提) が、改名後は非空行が一致 (22878 行)。
  2. ネガティブコントロール: 参照の `fcmp ult float %pc…` を 1 箇所だけ `fcmp ule` にすると、`canon_tags` 後も不一致 (`same()` が False)。
  3. 別算法の検算: 非空行を行ごとに対応させ、`%pc` 番号の対応表が一意かつ単射であることを確認 (18 種の改名)。
  - 出力: `T26 ok (%pc 改名だけ無視: 行 22878・改名 18 種・ネガ FAIL 確認)`。

## 4. 検証の範囲と未実施

- ユニット (`python3 tests/test_unit.py` 相当): T1〜T5・T7〜T26 は PASS (T17b は `LL_XRET_*` 未設定で skip。`work/cab2863/run_each.py` で個別実行)。**T6 は FAIL**: `tools/targets/freshair/work/...` (FA の `SlateCore.core_64`) が無いため `FileNotFoundError`。本 run の素材に無く、修復とは無関係。
- `bash tools/liftlib/liftlib_e2e.sh --quick`: **rc=2** (前提検査で停止)。`前提が無い: .../targets/freshair/work/win/Fresh Air/.../SlateCore.core_64 (bash tools/targets/freshair/fetch.sh)`。FA と KH の展開物は本 run に無い。必要な `oc_artifacts` 名は `work-liftlib-targets` `plugins-freshair` `plugins-kilohearts` (本 issue の `oc_artifacts:` 行には含まれているが、直近の依頼コメントの行には含まれていなかった)。
- 素材の確認: `$HOME/artifacts` には `fl-win64`・`toolchain-retdec`・`toolchain-emsdk`・`plugins-ott`・`analysis-ott-binaries`・`work-m6-ott`・`work-liftlib`・`work-icall`・`work-fw-stage1` のみ。展開先の `tools/targets/{freshair,kilohearts}/work` は存在しない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `liftlib_e2e.sh --quick` の FA/KH 部分 (`regress` の fa_gain・kh_gain) と T6 が未実行 (素材不足)。`oc_artifacts` に `work-liftlib-targets plugins-freshair plugins-kilohearts` を足して再実行が必要 | 受入条件 (`--quick` ALL PASS at HEAD) が未達。本 PR は部分達成 | #2863 (PM が依頼コメントの `oc_artifacts` を足して再起動) |
| `p1_legacy` の分岐の書き換えが参照 IR に入っていない。挿入した `%pc` フラグ 36 本は使われるが、条件分岐 18 本 (`br i1 %cf.*`・`%zf.*`) は 1 本も `%pc` へ変わっていない (参照 `ir7e_p1.ll` でも `br i1 %pc` は 0 件)。`legacy_p1` の `repmap` が、挿入前の行番号 `j` で挿入後の `out[j]` を書き換えていることが原因と推定 (未検証) | 参照 chain の P1 (`DEFECTS.md` D1a 同型の対策) が OTT で効いていない可能性。e2e (maxdev 0・SHA 42/42) は通るため、影響の有無は未検証。修正すると参照 IR・m10 出力・SHA の再測定が要る | #2863 へのコメントで PM 判断を依頼 (子 issue は未起票) |
