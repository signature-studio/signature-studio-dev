# liftlib 付録 — #2863: p1_legacy の IR 一致ゲートが #1664 (A7 空行除去) 後に FAIL する原因の確定と修復

- 日付: 2026-10-14 / issue #2863 (`[PLG-F3-32]`) / 親 #2094 / 担当: `tools/liftlib/` (`liftlib/recipes/ott.py`・`liftlib/passes/p1_legacy.py`・`tests/test_unit.py`)
- 既知類型との関係: D1a (P1 同型) と関係あり・未検証 (§5 参照)。ゲートの失敗原因 (`%pc` 一時名の差) 自体は意味の差ではない (§2)
- 測定 commit (コードを変えた最後の commit): `dce097af` (`fix(liftlib): relink broken material symlinks in ott recipe (#2863)`)。
  `git diff dce097af HEAD -- tools/liftlib/liftlib tools/liftlib/tests tools/liftlib/liftlib_e2e.sh` の出力は空 (本付録の追加以降はコード差分 0)。
  `dce097af` 以前の IR 一致の修復 (`054ee527`) は変えていない。`dce097af` は素材の壊れた symlink の張り直し (`recipes/ott.py`) と既定値の表記だけ。
- 修復前の測定 base: `13fcecca` (origin/main 取込み時点・修復前)。作業 worktree: `../ws-2863` (`2863-liftlib-p1-gate`)。素材 (gitignore 対象の `work/`) は本体の展開済みを `cp -a` で複写した。

## 0. 結論 (先出し)

| 項目 | 結果 (実測) |
|---|---|
| 原因 | `p1_legacy.legacy_p1` の一時名 `%pc<入力行 index>` が、#1664 (A7 の空行除去) で変わった行 index に依る。名前だけが変わり、命令と分岐は不変 (名前を正規化した比較の差分は 0 行。§2) |
| 修復 | IR 一致ゲート (`ott.same`) の比較前に、`%pc` 一時名の出現順の全単射な改名 (`p1_legacy.canon_tags`) だけを両辺へ適用。ゲートの他の部分と `p1_legacy` 本体は変えていない |
| `python3 -m liftlib ott --auto none` | 修復前 **FAIL** (IR 一致 O2a〜O4 の 6 項目が false・11.76 s) → 修復後 **PASS** (全 7 項目 true・e2e checks 8/0・出力 SHA 42/42 一致・n=3 で 10.88〜10.94 s) |
| `python3 -m liftlib ott` (既定 auto f2,f7,p1) | PASS (census junkHi 104 ≤ 104・e2e checks 8/0・`dce097af`) |
| `bash tools/liftlib/liftlib_e2e.sh --quick` 全体 (`dce097af`) | **ALL PASS** (rc=0・wall 257 s)。unit T1〜T26 ok (T6 含む)・fa_gain 400/400・kh_gain 366/366・ott PASS・ott_auto_none PASS。素材は `$ARTIFACTS_DIR` から展開 (§4) |
| P1 の分岐書換え | 挿入 18 箇所の置換 19 組のうち **適用 0 組** (実測・§5)。挿入フラグは使用 0 件。e2e は PASS だが、参照 `ir7e_p1.ll` も同じ状態で作られている |

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

- ユニット (`python3 tests/test_unit.py`・`dce097af`): T1〜T26 ok。T17b は `LL_XRET_LL` / `LL_XRET_DLL` 未設定で skip (既存の仕様)。**T6 も ok** (FA の `SlateCore.core_64` を `work-liftlib-targets` から展開して通過)。`ALL UNIT TESTS PASS`。
- `bash tools/liftlib/liftlib_e2e.sh --quick` (`dce097af`・foreground・単独 run): **rc=0・ALL PASS**・wall **257 s** (うち `regress` の elapsed 33.6 s)。起動直前の load average (1/5/15 分) = 0.32 / 0.67 / 0.35、nproc = 4。
  - (a)(b)(c) `regress`: `fa_gain` **BIT-EXACT 400/400**・`kh_gain` **BIT-EXACT 366/366**
  - `ott` (既定 auto `f2,f7,p1`): PASS。e2e checks 8/0・band maxdev 0.0 nbad 0・trap rc 0・census `[0x248]=0` junkHi **104 ≤ 104**・出力 SHA 比較は auto 既定のため適用外
  - `ott_auto_none`: PASS。IR 一致 7 項目 **true**・e2e checks 8/0・出力 SHA **42/42 equal** (f0 21/21)
- 素材 (`$ARTIFACTS_DIR` の 12 本のうち使ったもの): `work-liftlib-targets`・`work-m6-ott`・`work-liftlib` は `tar --zstd -xf` で worktree 直下へ展開 (tar の中身は repo 相対パス)。`plugins-freshair` は展開先 `$RUNNER_TEMP/plugins-freshair` を経て `tools/targets/freshair/fetch.sh` (`FA_DL`) に渡し、factory `.epf` 8 本を補完 (`win: 9 files, factory .epf: 8`)。`plugins-kilohearts` は展開していない (`work-liftlib-targets` に `tools/targets/kilohearts/work/winpkg/HeartCore.core_64` が入り、前提検査は通過)。
- 素材の壊れた symlink: `work-liftlib`・`work-m6-ott` の同梱 symlink 201 件が、取得元 VM の m6 作業 dir (repo 外の絶対パス) を指していた。`recipes/ott.py` の `full_t1.drc.{ll,dsm}` 張り直し (`dce097af`) で、e2e が使う作業 dir 2 組 (`tools/liftlib/work/ott/work/`・`tools/liftlib/work/ott_auto_f2_f7_p1/work/`・計 4 件) が正しい向きになった。残り 197 件は過去の作業 dir (`cab238`・`hang`・`wt_cab238`・`ott_auto_f7` など) で、`--quick` の経路では参照されず PASS (gitignore 対象・本 PR の範囲外)。
- `--quick` が省くもの (`liftlib_e2e.sh` の仕様): (d) SIMD helper・(e) 注入・(f) leaf spec。受入条件 (`--quick`) の範囲外で、本 run では未実行。
- §1 の `054ee527` の計測 (3 回) は、`dce097af` と比べると IR・SHA の経路が違わない (差分は `recipes/ott.py` の symlink 張り直し 2 行と表記のみ・`git diff 054ee527 dce097af --stat` で確認)。`dce097af` の `ott_auto_none` は上記の run で再確認した (所要の再計測は未実施)。
- 測定 commit は `dce097af` (コードを変えた最後の commit)。その後のコード差分は `7c5dcd36` の docstring 1 行だけ (`git diff dce097af 7c5dcd36 -- tools/liftlib/liftlib tools/liftlib/tests tools/liftlib/liftlib_e2e.sh` の出力: `recipes/ott.py` 行 222 の `auto f7,p1` → `auto f2,f7,p1`)。`ast` の比較で、差分は docstring の文字列 1 箇所だけ。実行コードは同一のため `--quick` は再測定していない (`dce097af` の記録を示す)。
- 作業ツリーは `dce097af` の時点で main より 363 commit 遅れている。`git merge-tree` で main との衝突は無し (rc=0)。main は取り込んでいない (取り込むと測定済みコードと差が生じ、再測定が要るため)。

## 5. 分岐書換えの実測と未解決

`legacy_p1(ott_lift.ll)` (入力 `tools/m6/work/ott_lift.ll`・修復後の `p1_legacy`・挿入 18 箇所) の測定:

| 測定 | 結果 |
|---|---|
| 挿入した `%pc` フラグの定義 | cf 18・zf 18・pf 18 の計 54 本 |
| 定義以外の使用 (使用箇所) | 0 件 (cf・zf・pf とも全て未使用) |
| 出力の `br i1 %pc` | 0 本 |
| 置換対象 (repmap) | 19 組 (br_cf 16・br_zf 1・or 1 箇所 = 2 組) |
| 実装が書換えを行う行 `out[j]` に旧名が含まれる組 | **0 / 19** (適用 0 件) |
| 挿入行数の和だけずらした正しい行に旧名が含まれる組 | 19 / 19 (旧名のまま残る) |

- 原因: `repmap` は挿入前の行番号 `j` で登録するが、適用は挿入後の `out[j]` に対して行う。挿入行の分だけずれるため、書換えが当たらない (推定から実測で確定)。
- 確認方法: `legacy_p1` の repmap 適用ループの直前で `inserts` と `repmap` を捕捉し (作業用の一時スクリプト・コミットしない)、`out[j]` と挿入行数の和だけずらした行を旧名の有無で比べた。
- 影響: P1 の分岐は挿入フラグを参照しない (D1a 同型の対策が OTT で効いていない)。e2e (maxdev 0・SHA 42/42) は通るが、参照 `ir7e_p1.ll` も同じ状態 (`br i1 %pc` 0 件) で作られているため。直すと参照 IR・m10 出力・SHA の再測定が要る。本 PR では直さない (挙動変更のため PM 判断)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `legacy_p1` の `repmap` が挿入前の行番号 `j` で登録し挿入後の `out[j]` に適用するため、分岐の書換えが 1 件も適用されない (実測 0 / 19・上表)。挿入フラグ (cf・zf・pf 各 18 本) は使用 0 件 | 参照 chain の P1 (`DEFECTS.md` D1a 同型の対策) が OTT で効いていない。e2e (maxdev 0・SHA 42/42) は通るが、参照 `ir7e_p1.ll` も同じ状態のため。直すと参照 IR・m10 出力・SHA の再測定が要る (本 PR では直さない・挙動変更のため PM 判断) | #3067 (`[LIFTLIB-21]`・親 #2863。修正の是非と再測定の範囲は PM 判断) |
