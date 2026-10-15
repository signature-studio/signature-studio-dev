# REPORT_APPENDIX_CI194 — mypy 厳格化 (Tier 1 / Tier 2) の測定値の正本

CI-194 (親 #2319) の mypy 段階導入の実測。**測定値の正本は本ファイル** (本文 `REPORT.md` は 250 行上限のため付録)。

- 測定日: 2026-10-15 / mypy 2.4.0 (compiled) / python_version = 3.12 (mypy の対象指定) / `--ignore-missing-imports` (外部 stub 無し・`tools/shared/paths` の sys.path 経由 import 用)
- 方法: モジュールを entry point として `mypy` に渡し, そのモジュール内の `error:` 行を数える (`follow_imports = silent` なので被 import 側のエラーは数に入らない)
- 実行: repo ルートで `mypy --config-file mypy.ini` (設定は `mypy.ini`。Tier 1 = `files` の 12 モジュール)

## Tier 1 (CI で blocking / mypy.ini の files)

「前」は導入前の `mypy --strict` をパッケージ一括実行し module 別に集計したエラー数 (主に no-untyped-def/no-untyped-call = 注釈不足)。「後」は `mypy --config-file mypy.ini` の結果。`# type: ignore` は 0 件。

| モジュール | 前 | 後 |
|---|---|---|
| `tools/liftlib/liftlib/ir.py` | 35 | 0 |
| `tools/liftlib/liftlib/pe.py` | 33 | 0 |
| `tools/liftlib/liftlib/diag.py` | 10 | 0 |
| `tools/liftlib/liftlib/env.py` | 9 | 0 |
| `tools/liftlib/liftlib/lb_layout.py` | 4 | 0 |
| `tools/liftlib/liftlib/runtime_lb.py` | 5 | 0 |
| `tools/liftlib/liftlib/passes/boolret.py` | 2 | 0 |
| `tools/liftlib/liftlib/passes/dataimage.py` | 3 | 0 |
| `tools/liftlib/liftlib/passes/fp_bind.py` | 19 | 0 |
| `tools/liftlib/liftlib/passes/icall.py` | 8 | 0 |
| `tools/liftlib/liftlib/passes/l1_restore.py` | 15 | 0 |
| `tools/liftlib/liftlib/passes/remap.py` | 18 | 0 |
| 合計 | 161 | 0 |

境界の契約を固定するため, Tier 1 が呼ぶ側 (Tier 2) の関数にも注釈を足した: `pipeline.load_cfg/rpath/run_all`, `harness/diff.run_diff/fmt`。あわせて Tier 2 の既存エラー 8 件 (annotated 空コンテナ等: `mc.py` 5・`base.py` 1・`p1.py` 1・`recipes/ott/m6_full_extract.py` 1) を直した (挙動不変)。

## Tier 2 baseline (未 strict。拡大は別 issue)

entry point として単体で strict 検査したときのエラー数 (降順)。

| モジュール | エラー数 |
|---|---|
| `tools/ott/lift/x64c.py` | 1365 |
| `tools/flelift/x64c.py` | 1320 |
| `tools/liftlib/liftlib/passes/p1.py` | 442 |
| `tools/targets/freshair/lift2/mlift/mlift.py` | 423 |
| `tools/liftlib/liftlib/simd/kernels.py` | 226 |
| `tools/m11/ldfix/ldfix.py` | 196 |
| `tools/icall/icall_rewrite.py` | 189 |
| `tools/targets/freshair/lift2/mlift/mlift_ops.py` | 182 |
| `tools/liftlib/liftlib/passes/base.py` | 120 |
| `tools/plugins/lift/passes/ir5_patch.py` | 115 |
| `tools/plugins/p0c/x87fix.py` | 114 |
| `tools/plugins/p0c/f80_lower.py` | 112 |
| `tools/targets/{kilohearts/snapins/lift,poc_gain/ref,freshair/ref}/ir5_patch.py` | 103 (各) |
| `tools/liftlib/liftlib/mc.py` | 83 |
| `tools/liftlib/liftlib/recipes/ott/ir7_argpass_fixed.py` | 79 |
| `tools/liftlib/liftlib/pipeline.py` | 66 |
| `tools/liftlib/liftlib/passes/iargs.py` | 61 |
| `tools/liftlib/liftlib/regbind.py` | 60 |
| `tools/liftlib/liftlib/recipes/ott.py` | 58 |
| `tools/liftlib/liftlib/passes/leafabi.py` | 54 |
| `tools/liftlib/liftlib/cli.py` | 54 |
| `tools/liftlib/liftlib/inject.py` | 45 |
| その他 (`liftlib/recipes/ott/ir9_bootstraps.py` 44, `simd/simdtest.py` 35, `harness/spec.py` 31, `simd/gen.py` 29, `passes/f2.py` 28, `passes/f7.py` 25, `stdbuild.py` 24, `harness/specgen.py` 23, `passes/p1_legacy.py` 12, `harness/diff.py` 9, ……)| 12〜44 |

## 検証 (挙動不変)

- `tools/liftlib/tests/test_unit.py`: 変更の前後で per-test の結果が同一 (33 テスト中 25 pass・8 fail。fail は work/ 配下の素材が worktree に無いための FileNotFoundError で, 変更前から同じ)。
- `tools/liftlib/tests/test_boolret.py`: 5 tests OK (unittest)。
- 差分ハーネス (origin/main の liftlib と本変更の liftlib に同一の合成入力を与える): `ir`/`pe`/`remap`/`boolret`/`dataimage`/`icall`/`fp_bind`/`l1_restore`/`lb_layout`/`runtime_lb`/`env` の出力 JSON が一致 (12,801 + 10,926 bytes)。
- ネガコン: Tier 1 の注釈を 1 箇所わざと壊すと `mypy` が 2 errors で赤 (`Success: no issues found in 12 source files` が壊れる) を確認。

## Func.params() の拒否経路の再測定 (HEAD `194081d19`・review round 2 への対応)

検証 HEAD `194081d19`。`Func.params()` の実行コード差分 (`rpartition` 検査と `ValueError`) の影響を、方法 (b) で確認した。

- 差分ハーネスの元の入力 (`12,801 + 10,926 bytes` の生成に使った合成入力) はリポジトリに残っていない。再実行はできないため、(a) ではなく (b) で確認する。
- 実 IR (`work/`・RetDec 出力) は runner に無い。`fl-win64` の tar に `.ll` は 0 件 (`tar --zstd -tf ... | grep -c` で実測)。`work-liftlib` は本 run の `oc_artifacts` に含まれない。したがって **実 IR での確認はしていない**。
- 代わりに、リポジトリ追跡ファイル内の `define` 行 (`git grep -h -E '^\s*define\s'`) を全件集め、旧版 (`325cf6a4d`) と新版 (`HEAD`) の `Func.params()` を比べた。

```
$ git grep -h -E '^\s*define\s' -- . | sed 's/^\s*//' | sort -u | wc -l
75                       (重複除去後の define 行)
DEFINE 正規表現に一致 (params() の入力になり得る行): 66
新旧で結果が同一: 66 / ValueError 発生: 0 / 結果差分: 0
```

- 残り 9 行は `define` を含む散文・コメント・1 行の C 風断片で、`DEFINE` に一致しないため `params()` に入らない。
- 生成側の確認: 仮引数を出力するコード (`inject.py:152`・`f2.py:294`・`iargs.py:338`・`recipes/ott/ir8_valueflow.py:331`・`recipes/ott/ir9_bootstraps.py` 等) は全て `%名前` を付けて出力する。名前の無い仮引数を生成する箇所は見当たらなかった。
- 境界の確認 (旧版との比較): 通常の属性付き仮引数 (`noundef`・`nocapture`・`byval(...)`・`local_unnamed_addr` 付き define) は新旧同一。名前の無い仮引数・可変長・`{ i64, i64 } %s` のような構造体引数・`%"quoted name"` は、旧版で `('{', 'i64')` 等の壊れたタプルを返していた入力で、新版は `ValueError` になる (意図した変更)。
- `passes/iargs.py:94` (`[p[0] for p in fns[name].params()]`) は、旧版で名前無し仮引数を型だけ返していた。新版は ValueError。ただし上記の通りリポジトリ内の定義行には該当が無い。実 IR に該当が無いことは未確認 (素材不足)。

結論: 拒否経路はリポジトリ内の全 `define` 行で発火せず、新旧の出力は一致する。実 IR での確認 (素材 `work-liftlib`) は次節 (review round 4 への対応) で完了した。12 モジュールの差分ハーネスの出力 JSON は `194081d19` で再実行していない (未解決のまま)。

### review round 4 への対応 (実 IR 測定・検証 HEAD `9731385def19957bee7da7bfb54b68a0568b8b85`・測定日 2026-10-15)

実行コードは `194081d19` と同一 (`git diff 194081d19 9731385de -- tools/liftlib/liftlib` は 0 行)。

- 素材: アーティファクト `work-liftlib` を `tools/liftlib/work/` へ展開した (リポジトリ直下で `tar --zstd -xf`)。`.ll` は 596 件。そのうち 64 件は壊れた symlink (外部の絶対パスを指し中身なし) のため除外し、読めた **532 件**を比較した。`.bc` は 4 件で対象外。
- `Func.params()`: 旧版 `325cf6a4d` の `ir.py` と新版 (`9731385de` の `ir.py`) を、読めた 532 件の全 `define` **91,380 関数**で比較した。結果は一致 91,380 / 差分 0 / 新版の ValueError 0 / 旧版の例外 0 / `ret_type()` の差分 0。
- `passes/iargs.py:94` の名前無し仮引数の懸念: 実 IR の 91,380 関数で該当 0 件。解消した。
- 差分ハーネス (12 モジュールの出力 JSON の比較): 元の合成入力がリポジトリに残っておらず**未再実行**。測定値は `73d7d9444` のまま。代わりに、実 IR の `params()` 全件一致を根拠とする。
- `tools/liftlib/tests/test_unit.py`: 旧版 `325cf6a4d` と新版 `9731385de` を同じ `work/` で実行。両方とも `FAIL 8/33: t1 t2 t3 t4 t6 t7 t9 t26`。結果行 (`T*` と `FAIL`) は一致。
- `tools/liftlib/tests/test_boolret.py` (`9731385de`): 5 tests OK。
- 測定スクリプトは repo 外の作業領域に置いた (commit していない)。素材は `work/` (gitignore 対象) にのみ展開し、commit していない。
