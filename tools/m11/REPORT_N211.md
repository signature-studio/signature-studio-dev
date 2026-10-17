# M11-N211 (#4748): `function_40c650` を退行しない形で変換し、survey 基準差 0 を実測

親: #3678 / #2902 / #3642。原因の切り分けは `REPORT_N210.md` (#4747)。本 REPORT は受入条件 1 (退行しない形の survey 差 0) の実測。

## 結論

`fix_xmm_args.py` の `function_40c650` 変換で、呼出し 16 site のうち **IR 順の 3・4 番目 (`function_662e50` 内) だけを 0.0 のまま残し、他 14 site を実値で渡す**。survey (942 unit) は基準 `M11_XMM_ARGS=0` と unit 別差 0 (`cmp` 終了 0)。

除外は `fix_xmm_args.py` の `CONV_ZERO_SITES = {'function_40c650': {3, 4}}` で入れた (`NO_CONV` は空)。site 番号で除外するため、IR が変われば見直す (#2902 の残件)。

## 測定

- 測定の基点: `fe48dca85` (origin/main) の作業ツリーに `fix_xmm_args.py` の 1 ファイルの変更を入れて測った (commit 前に測定)。このコードを commit した後の HEAD で、build と survey を再実行して同じ結果を確認する (下の「再測定」)。
- 素材: fl-win64 / work-m11 / work-liftdiff を `$HOME/artifacts` から展開。toolchain-retdec・toolchain-emsdk は `/opt/retdec`・`/opt/emsdk` に既存。
- IR: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash m11_gen_ir2.sh` rc 0 (51 秒)。
- 基準 build `M11_XMM_ARGS=0` 18.2 秒、survey 5.9 秒。
- 変換 build `M11_XMM_ARGS=1` (`fix_xmm_args] fixed=47 skipped=651`)、survey 約 6 秒。`function_40c650` は `double %in.xmm0` に変換。変換 site 87、0.0 のまま 104 (`callsite_zero_args`)。

| 構成 | units | ok | noproc | miss | trap | clobber | unit 別差 |
|---|---:|---:|---:|---:|---:|---:|---|
| 基準 `M11_XMM_ARGS=0` | 942 | 873 | 1 | 47 | 21 | 0 | — |
| 変換 (3・4 を 0.0) `M11_XMM_ARGS=1` | 942 | 873 | 1 | 47 | 21 | 0 | 0 (`cmp` 終了 0) |

## 前提と限界

- 基準は issue の値 (ok 873 / noproc 1 / miss 47 / trap 21 / clobber 0) と一致。
- 除外 site の結論は、同一 commit (`a8906a4c3`、PM 判断で採用) での単独測定 (全 16 site 変換で 149・158 が clobber、3・4 を 0.0 にすると差 0) に基づく。本 run では除外を入れた状態で再測定した。
- 前 run の「単独 site 1〜8 は全て同一」との食い違い (`REPORT_N210.md` の ctlC 系列と合わせて) は未解決。機構は #4777 (M11-N221)。
- `work-m11` は #516 以前の生成物を含むため、絶対値は canonical 基準 (#1479) 待ち。差の判定は同一 IR 上の A/B。
