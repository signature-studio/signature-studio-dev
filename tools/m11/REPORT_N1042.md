# M11-N60 (#1042) units_run 測定経路と m11_e2e.sh 全体の実測

親: #594。測定 commit (コードを変えた最後の commit): `48496bd5` (main)。本 PR はコード変更なし (REPORT のみ)。

## 結論

- **`functions_dll.csv` の入手経路**: 素材に含めず、run 内で Ghidra 12.1.4 headless (JDK 21・`tools/m2/ghidra_scripts/DumpFunctions.java`) で再生成する。`work-m2-ghidra` 等の新素材は作らない (R2 allowlist 変更が要るため)。Ghidra の取得 (公式 release zip, sha256 `ddac49f9…` 一致) から CSV 生成まで約 10 分で、60 分 run に収まる。
- **`m11_e2e.sh` 全体 (全再生成経路) を HEAD で foreground 実行**: rc 0・judge 通過。reached_stage 4/6、units_run 53/942、survey ok 871 / trap 24 / miss 46 / noproc 1。
- **既定 OFF (`M11_OV_414AD0=0`) と ON (`=1`) の比較**: survey 出力は byte 一致 (md5 `5566a396…`)。ON でも `ov.o` を再ビルドしており (stamp `1`)、wasm 長は 6042952 → 6042942 B で変化している。survey 出力の unit 別 kind・frames・icall が同一。

## 入手経路 (受入 1)

| 項目 | 値 |
|---|---|
| Ghidra | 12.1.4 PUBLIC (`ghidra_12.1.4_PUBLIC_20260921.zip`)、sha256 `ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db` (`REPORT_APPENDIX_960.md` と一致) |
| JDK | Temurin 21 (JDK 21)。runner 既定の 17 では使わない |
| 入力 | `fl-win64` の `block00031_PE.bin` |
| 出力 | `tools/m2/work/ghidra_dll/functions_dll.csv` 59010 行 (測定時に記録した値)、sha256 `90d1bbac…` (REPORT_N27 と一致と記載) |
| 所要 | analyzeHeadless 20:14:10 → 20:24:25 UTC (約 10 分 15 秒)、rc 0、`MAXMEM=8G` |

行数の注記: REPORT_N27 は同じ sha256 に対し、L170 で 59010 行、L183 で 59 009 行、L199 で 59 010 行と記す。数え方の差 (ヘッダ行の有無など) は未確認。CSV は worktree に存在しないため現時点で再計数できない。

## m11_e2e.sh 全体 (受入 2)

素材: `fl-win64`・`toolchain-retdec`・`toolchain-emsdk`・`work-m11`・`work-liftdiff` を展開。`lift_pe.sha256` 無し (work-m11 は #728 以前) のため全再生成経路に入った。

| 項目 | 値 |
|---|---|
| コマンド | `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/m11_e2e.sh` (`M11_OV_414AD0` 既定 0) |
| 所要 (wall) | 10 分 6.8 秒 (user 9 分 49.9 秒、sys 17.0 秒) |
| 経路 | m11_scan → m11_bounds → lift 4 chunks (RetDec) → tail 固定点 ×3 → gen_ir2 → build → 実行 A・B |
| reached_stage | 4/6 (stage 5・6 は未達。期待値 `e2e_expect.env` は stage 4・survey_ok 800 で、judge 通過) |
| units_run | 53 / 942 (`units_run + units_skipped` = 56) |
| survey | ok 871 / noproc 1 / miss 46 / trap 24 (oom 0)、clobber 0 |
| trap kinds | unreachable 1、halt0->longjmp 7、memory access out of bounds 16 |
| stop_reason | trap "unreachable" @ function_8c5eb0 ← function_56fde0 ← m11_icall ← function_4120c0 |
| FastMM4 | GetMem 572 / FreeMem 20 (full)、VirtualAlloc 19 回 275.6 MB |
| ir_sha256 | `d7c72a8c…` (ldfix applied, qstore applied) |
| load | 未採取 (採取していない) |

## OFF 基準 と ON の unit 単位比較 (受入 3)

| 構成 | 所要 (wall) | survey 出力 md5 | 結果 |
|---|---|---|---|
| OFF (既定 `M11_OV_414AD0=0`) | 10 分 6.8 秒 (全再生成) | `5566a396…` | 上の表 |
| ON (`M11_OV_414AD0=1`、増分 build) | 48.0 秒 (lift・IR は再利用) | `5566a396…` | OFF と byte 一致 |

ON の増分 build で `work/ov_414ad0.stamp` が `1`、`work/obj/ov.o` が再生成された (20:35)。unit 別の集計 (kind・frames・icall) は survey 出力 (`work/e2e_survey_{off,on}.out`) の同一性で確認。

## 測定 commit と現 HEAD の差分 (WORKFLOW §6)

測定 commit `48496bd5` から、本 REPORT を含む検証 HEAD までの差分。

```sh
git diff 48496bd5 HEAD -- tools/m2 tools/shared | wc -l    # 0
git diff --name-only 48496bd5 HEAD -- tools/m11            # tools/m11/REPORT_N1042.md のみ
```

測定対象コードの差分は 0 行。`tools/m11` の変更は本 REPORT のみ。

## 未解決

- stage 5 (全 unit 完走) と stage 6 (DllMain attach 完走) は未達。停止点は unit 57 (0x16fde0) 付近の trap (REPORT.md §6・REPORT_N403.md)。これは本 issue の範囲外。
- ON と OFF が同一のため、`M11_OV_414AD0=1` の効果は今回の経路では観測できない (既存の結論と整合: REPORT_595.md・REPORT_683.md)。
