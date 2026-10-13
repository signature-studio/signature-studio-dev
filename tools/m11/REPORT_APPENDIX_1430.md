## 基準 (before) #1430: xmm 引数の callee 署名復元の前測定 (REPORT_APPENDIX §9 から分割移動)

既知類型との関係: 該当 (icall §4 の `callsite_arg_drop` = liftdiff 分類、REPORT_APPENDIX §9 の xmm 退行行案の続き)。

測定 commit `7e149974` (origin/main, 本 branch の起点)。`work-m11` は `lift_pe.sha256`・`functions_dll.csv`・`ir_conditions.json` を含まないため `m11_e2e.sh --full` の全再生成経路に入った。`functions_dll.csv` は Ghidra 12.1.4 (公式 zip sha256 `ddac49f9…` 一致) + JDK 21 + `tools/m2/ghidra_scripts/DumpFunctions.java` で作成 (9 分 37 秒、59,010 行)。

| 項目 | 実測 |
|---|---|
| `m11_e2e.sh --full` (`7e149974`) | 626.99 秒 (10 分 27 秒), rc 0, load 0.68 |
| survey (全再生成直後, unit 別 942 本) | **ok 872 / trap 23 / miss 46 / noproc 1** (trap 内訳 OOB 15 / Halt0 7 / unreachable 1) |
| survey (増分再実行, unit 別 JSON 出力) | 46.94 秒, ok 872 / trap 23 / miss 46 / noproc 1 (全再生成直後と一致) |
| unit 838 / 882 / 885 | ok / ok / ok (基準の退行チェック対象) |

### work-m11 スナップショットの 7 カテゴリ (測定 commit 未確認)

上の全再生成 IR (`7e149974`) による 7 カテゴリの和は、本 PR では測っていない。代わりに `$ARTIFACTS_DIR/work-m11.tar.zst` を展開した `tools/m11/work/boot_final.ll` (生成 commit は未確認) から、`bash tools/m11/m11_sigfix_stats.sh` を実行した (3.94 秒, rc 0, load 0.70, n=1)。`fl-win64` の `block00031_PE.bin` を `PE` に指定。`m11_argrecover_verify.py` は 18/18 一致。

| 分類 | 引数数 | 旧記録 (§9) |
|---|---:|---|
| callee_unused | 313 | 313 |
| inherit | 1,172 | 1,172 |
| set_const | 18 | 18 |
| set_const_xmm_callee | 48 | 48 |
| set_other | 378 | 378 |
| stack_set_other | 32 | 32 |
| callee_nopdata | 2 | 2 |
| 7 カテゴリの和 | **1,963** | 1,963 (= 2,064 − 未突合 101) |

0 詰め site 1,049 / 引数 2,064、突合 site 1,004 (`no_pdata` 23・`unmatched` 22)。

この結果から言えること:
* 上の 7 カテゴリは work-m11 の IR から出した値で、測定 commit は未確認。旧記録 (§9) と全項目一致した。
* 未突合の 101 引数の内訳 (work-m11 の `fixes.json` の `site_detail`、0 詰め引数 = `want − have`): `no_pdata` 23 site / 33 引数 (callee の .pdata が無い)、`unmatched` 22 site / 68 引数 (突合不能)。合計 101。
* 本節の 1,963 は `7e149974` の全再生成 IR による値ではない。全再生成 IR での 7 カテゴリの実測と、その和の提示は #1532 で行う。

### 注記
* `tools/m11/results/sigfix_zeropad_remaining.tsv` は `m11_sigfix_stats.sh` の再生成物のため、本 PR には含めない (未コミット)。
* 再測定 (after) と `fix_xmm_args.py` の接続は未実施 (子 issue #1479)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未測定の 3 項目 (set_other / stack_set_other / callee_nopdata) の `7e149974` 値 | 本表は work-m11 の値のみ | #1479 |
| 全再生成 IR による 7 カテゴリの実測と和、work-m11 由来 1,963 との突合 (差の由来を含む) | 基準の分類値の解釈 | #1532 |
| xmm 引数を読む callee の署名復元と unit 別 after 測定 (unit 838/882/885 を含む) | set_const_xmm_callee 48 引数が未解決 | #1479 |
