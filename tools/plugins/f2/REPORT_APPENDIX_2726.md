# PLG-F2-8 (#2726) 付録: 残不一致 6 関数の原因切り分けと #547 ablation の再定義

REPORT §11 の根拠。測定 commit `26f90ada` (origin/main 取り込み時点)。本 PR は lift 経路のファイルを変更していない (既存ファイルの変更は docs のみ。新規の probe `tools/plugins/f2/xmm_slot_probe.py` は lift 経路に入らない)。PR 作成後に origin/main (`2e50b801`) を merge commit `6ba2e47e` で取り込んだ。測定範囲 (lift 経路・p0c・f2・liftdiff・m11/ldfix・inventory・shared) の非 docs 変更は 11 件 (`tools/liftdiff/tests/ld53_arg_regs.py`・`tools/liftdiff/tests/oob_414ad0_27.py`・`tools/m11/ldfix/fix_d17_e2e.sh`・`tools/m11/ldfix/spill37_1169.py`・`tools/m11/ldfix/spill_classify_1161.py`・`tools/plugins/f2/f2_step2.sh`・`tools/plugins/f2/icall_gate_waivers.json`・`tools/plugins/f2/nc_waiver_proof.py`・`tools/plugins/f2/waiver_proof.py`・`tools/plugins/f2/xmm_slot_probe.py`・`tools/plugins/lift/passes/test_movntps_store.py`) で、いずれも測定経路から参照されない (確認結果: 参照元は docs・結果ファイルと各領域の検査・e2e スクリプト (測定経路の外) だけで、`test_movntps_store.py` は `REPORT_APPENDIX_2094.md` からのみ参照され、`lift_ranges.sh` は passes を名前で呼ぶ)。よって測定 commit `26f90ada` の出力は、HEAD でも有効とみなす。

## 0. 測定条件

- 素材: `fl-win64` (`extracted/*_PE.bin` 313 本)、`toolchain-retdec` (`[RETDEC]`、RetDec v5.0)、`toolchain-emsdk` (`[EMSDK]`)。`work-fw-stage1`・`work-liftlib`・`plugins-ott` は取得されたが、本測定の経路では使わない。
- 前提 work/ の生成 (4 core runner、1 回): `win_scan.py`・`mk_blockmap.py`・`win_funcs.py` (**5 分 11 秒**)・`win_unique.py`・`win_abi.py`。
- lift (11 block、逐次): V0 = `PLUG_XMMARG=0 PLUG_LDFIX=0 PLUG_ICALL=0` **29 秒**、rc 0 ×11、`emcc -c` rc 0 ×11。V1 = `PLUG_XMMARG=1 PLUG_LDFIX=1 PLUG_ICALL=0` **34 秒**、rc 0 ×11、`emcc -c` rc 0 ×11。
- `leaf_diff.sh`: V1 **134 秒** (rc 0)、V0 **128 秒** (rc 0)。各 1 回。
- 最終判定 (23 関数): V0・V1 とも **一致 15 / 不一致 8 / 実行不能 0**。

## 1. ablation の再定義 (V0 → V1)

arm: V0 = `PLUG_XMMARG=0 PLUG_LDFIX=0`、V1 = `PLUG_XMMARG=1 PLUG_LDFIX=1` (いずれも `PLUG_ICALL=0`)。

旧受入 (「pass を外すと 8 関数が戻る」) は成立しない。V0 → V1 で不一致数は 8 のまま、戻る関数は 0 件 (`REPORT_APPENDIX.md` §9.1 の 4 と同じ結論)。再定義は「署名が変わる関数の IR 差分と判定を並べる」。対象は 0x6b0ef0・0x6ca5c0・0x6f1650。

| VA (block) | V0: IR 署名 / 一次採点 / 最終 | V1: IR 署名 / 一次採点 / 最終 | IR 差分 (`p.final.ll`) |
|---|---|---|---|
| 0x6b0ef0 (18982) | `i64(i64, i64)` / mismatch 0/8/11 / mismatch | `i64(i64, i64, double %in.xmm2)` / mismatch 7/8/11 / mismatch | 9 行: 署名 +1、`%in.xmm2.bits` 定義追加、`xor i128 0, 0` → `zext i64 %in.xmm2.bits to i128` |
| 0x6ca5c0 (19013) | 同上 | 同上 | 同上 (同一コード) |
| 0x6f1650 (19059) | `i128()` / match 11/11/11 / match | `i128(i64 %pad0, float %in.xmm1)` / match 11/11/11 / match | 7 行: 署名 +2、`%in.xmm1` の bits 化、`trunc` 追加 |

- V0 と V1 の 23 関数の判定を `leaf_report.md` の行で比べると、差は上の 3 関数 (一次採点と署名) のみ。最終判定の集合は同一。
- 一次採点が変わるのは 0x6b0ef0・0x6ca5c0 (0/8 → 7/8)。残る 1 case の不一致は、§3 の「届かない xmm 入力」と整合する (case の入力を直接 trace で確認したわけではない)。
- 0x6f1650 は署名だけ変わり、判定は両方 match。過去に不一致だった原因は image 配置 (`REPORT_APPENDIX_871.md` §10.1〜§10.2 の `mk_targets` 修正で解消) で、pass とは無関係。
- 上表の 0x6b0ef0・0x6ca5c0 の IR 差分 (9 行) と一次採点の変化 (0/8 → 7/8) は、XMMARG と LDFIX の合成による変化として読む。XMMARG 単独の寄与は本 PR では測っていない。

XMMARG 単独の最終判定の根拠は §9 (HEAD 2f77ace、`PLUG_XMMARG=1`、LDFIX 既定 OFF) の 15/8 だけである。XMMARG 単独 arm (`PLUG_XMMARG=1 PLUG_LDFIX=0`) の一次採点は本 PR で未実測。

V1 の lift で ldfix が適用された件数 (`*.ldfix.json`) は記録していない。V1 の work/ は PR に含まれず、本 run の素材 (`$ARTIFACTS_DIR` は `fl-win64` のみ) には `toolchain-retdec` が無いため再測定できない。

## 2. 残 6 関数の原因 (V1 lift の `p.xa.json` の数値)

| block | fixed | skipped (内訳) | `callsite_zero_args` |
|--:|--:|---|--:|
| 18975 | 3 | 12 (`slot_occupied` 6 / `no_placeholder` 5 / `partial_slots` 1) | 4 |
| 18982 | 1 | 2 (`slot_occupied` 1 / `no_placeholder` 1) | 1 |
| 19005 | 2 | 3 (`slot_occupied` 2 / `partial_slots` 1) | 3 |
| 19006 | 2 | 2 (`slot_occupied` 2) | 2 |
| 19013 | 3 | 1 (`slot_occupied` 1) | 3 |
| 19059 | 1 | 11 (`slot_occupied` 6 / `no_placeholder` 4 / `partial_slots` 1) | 1 |

`REPORT_APPENDIX.md` §9.2 の表と一致する。

| VA | 原因 | `p.xa.json` の skipped / fixed | 修復 |
|---|---|---|---|
| 0x6bfec0 (18975) | no_placeholder | `no_placeholder` (接続できる placeholder が無い) | 未適用 (子 #2850) |
| 0x6c9b60 (18975) | no_placeholder | `no_placeholder` | 未適用 (子 #2850) |
| 0x6c8c90 (19005) | slot_occupied | `slot_occupied(xmm3, IR params=4)`。位置 3 を整数 `%arg4` で宣言済み | 未適用 (子 #2850) |
| 0x6cc2e0 (19006) | slot_occupied | `slot_occupied(xmm3, IR params=4)` | 未適用 (子 #2850) |
| 0x6b0ef0 (18982) | 引数の割当て | fixed: `i64 %arg1, i64 %arg2, double %in.xmm2` (xmm2 のみ) | 部分復元。§3 (子 #2850) |
| 0x6ca5c0 (19013) | 引数の割当て | fixed: 同上 | 同上 |

## 3. 0x6b0ef0・0x6ca5c0: 引数が値として届かない原因

- 2 つの機械語解析の食い違い (`tools/plugins/f2/xmm_slot_probe.py`、block18982 / block19013):
  - (a) `p0c/k80abi.scan_function` (pass が使う): `xmm2` のみ。
  - (b) `tools/liftdiff/ldlib/pe.py` (CFG 上で全経路に定義の無い読み): `xmm1,xmm2,xmm3`。
- 機械語 (VA、block18982 の PE):
  - 0x6b0f03 `je 0x6b117f`。entry から直接 0x6b117f へ分岐する (0x6b0ef0〜0x6b0f03 には分岐が無い)。
  - 0x6b117f `movapd xmm0, xmm1` (xmm1 の読み)、0x6b1191 `mulsd xmm2, xmm3` (xmm3 の読み)、0x6b1195 `movapd xmm3, xmm1` (xmm1 の読み)。この経路では xmm1・xmm3 は未定義のまま読まれる。
  - 線形順 (アドレス順) では、xmm1 の最初の出現は 0x6b0f9c `movapd xmm1, xmm3` (書き)、xmm3 は 0x6b0f68 `movsd xmm3, [rip+..]` (書き)。線形走査はこれらを read-before-write とみなさず、xmm2 (0x6b0f5c の読み) だけを拾う。
- 結論: xmm1・xmm3 は呼出し元の値を読む入力で、pass の署名に無い。wasm 側には届かない。残る 1 case の不一致と整合する。
- 位置の衝突: xmm1 の Win64 位置 1 は IR の `i64 %arg2` (rdx) と同じ。(b) の集合を `occ` 判定に使えば `slot_occupied(xmm1, IR params=2)` で skip になる。現状は、skip すべき関数を部分復元で適用している。
- 未確認: rdx (`%arg2`) と xmm1 のどちらが呼出し元の値として意味を持つかは、呼出し元 (closure 内の call site) の解析が要る。子 #2850 の範囲。

## 4. 回帰

- 23 関数の最終判定は V0・V1 とも 一致 15 / 不一致 8 / 実行不能 0。fvm 2 件 (0x73fa70・0x6ec2f0) は両方 `callee_divergence` (既存。#1398 / #1199 の範囲)。
- lift 経路のコードは変えていない。`nc_leaf.py` は再実行していない (コード変更なしのため。子 #2850 でコードを変える場合に実行する)。
- 新規ファイルは `tools/plugins/f2/xmm_slot_probe.py` のみ (lift 経路に入らない確認用)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `fix_xmm_args.py` の xmm 入力 slot 判定を CFG 解析へ置換し、0x6b0ef0・0x6ca5c0 の部分復元を止める | 部分復元による silent の誤り | #2850 [PLG-F2-9] |
| no_placeholder 2 関数 (0x6bfec0・0x6c9b60) と slot_occupied 2 関数 (0x6c8c90・0x6cc2e0) の修復 | 4 関数が未修復 | #2850 [PLG-F2-9] |
| 呼出し元の xmm 値 (closure 内の call site で 0 を渡す) | closure 内の呼出しで float 値が失われる | #2762 (open。M11 の同種課題 `call_arity_mismatch` の xmm 呼出し側引数。2026-10-14 に f2 の事例を追記)。PR #2907 (`Closes #2762`、ready、base main) が `fix_xmm_args.py` を変更する。#2907 の merge で #2762 が閉じたら、起票先を付け替える |
| XMMARG 単独 arm の一次採点と V1 の ldfix 適用件数 (B1 の数値の帰属) | 受入 5 の数値の帰属 | #2850 (検証手順の再測定に併せて実測。2026-10-14 にコメントで追記) |
| 同一 commit (26f90ada) での LDFIX 単独の対照 (`PLUG_XMMARG=1` のまま `PLUG_LDFIX=0/1` の A/B)。#613 の A/B (commit 1af46f06、17/6/0) が現行で再現しない原因の切り分け (1af46f06→26f90ada の間に ldfix.py 8 件・lift_ranges.sh 7 件・fix_xmm_args.py 1 件の変更あり) | 受入 3 (LDFIX の効果) の根拠が無い。現行では LDFIX 単独の効果を判定していない | #2850 (実測項目。取得後に同じ run で測る) |

## 6. 再現

```sh
source tools/shared/env.sh; source tools/plugins/f2/env.sh
cd tools/plugins
python3 inventory/win_scan.py && python3 f2/mk_blockmap.py && python3 inventory/win_funcs.py   # 前提 work/ (約 5〜8 分)
python3 inventory/win_unique.py && python3 inventory/win_abi.py
BLOCKS="18953 18975 18979 18982 18984 19005 19006 19013 19058 19059 19145"
PLUG_ICALL=0 bash lift/batch_lift.sh $BLOCKS                                    # V0 (既定 = XMMARG=0 LDFIX=0)
python3 f2/closure_stats.py --json work/f2_stats.json $BLOCKS                    # leaf_list の入力
cd ../.. && bash tools/plugins/f2/leaf_diff.sh                                   # V0 の判定
cd tools/plugins && PLUG_XMMARG=1 PLUG_LDFIX=1 PLUG_ICALL=0 bash lift/batch_lift.sh $BLOCKS   # V1
cd ../.. && bash tools/plugins/f2/leaf_diff.sh                                   # V1 の判定 (issue の検証コマンドと同じ)
python3 tools/plugins/f2/xmm_slot_probe.py "$FL_WIN64_DIR/extracted/block18982_PE.bin" 6b0ef0
```

- `leaf_diff.sh` は `work/batch/` を読む。V0 と V1 を比べるには、各 lift の後に `work/batch/` を退避・復元する (本測定は `work/abl/v0`・`work/abl/v1` に退避した)。
- 本測定の `f2/` 前提 (`work/f2_stats.json`・`work/f2/<b>.icall.json`) は `f2_step1.sh` の後半 (閉包統計と `audit_icall.py`) と同じ手順で作った。

## 7. 限界

- 0x6b0ef0 の呼出し元は解析していない。xmm1 と rdx のどちらが意味を持つかは未確定 (#2850)。
- 残る 1 case の不一致 (V1 の 7/8) の入力を trace で直接確認していない。
- 測定は 1 回ずつ (V0・V1 とも `leaf_diff` は 1 回)。再現性の回数測定は未実施。
