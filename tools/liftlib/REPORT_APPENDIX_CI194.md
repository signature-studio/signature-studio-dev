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

- `tools/liftlib/tests/test_unit.py`: 変更の前後で per-test の結果が同一 (33 テスト中 26 pass・7 fail。fail は work/ 配下の素材が worktree に無いための FileNotFoundError で, 変更前から同じ)。
- `tools/liftlib/tests/test_boolret.py`: 5 tests OK (unittest)。
- 差分ハーネス (origin/main の liftlib と本変更の liftlib に同一の合成入力を与える): `ir`/`pe`/`remap`/`boolret`/`dataimage`/`icall`/`fp_bind`/`l1_restore`/`lb_layout`/`runtime_lb`/`env` の出力 JSON が一致 (12,801 + 10,926 bytes)。
- ネガコン: Tier 1 の注釈を 1 箇所わざと壊すと `mypy` が 2 errors で赤 (`Success: no issues found in 12 source files` が壊れる) を確認。
