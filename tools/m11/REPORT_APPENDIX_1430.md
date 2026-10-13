## 基準 (before) #1430: xmm 引数の callee 署名復元の前測定 (REPORT_APPENDIX §9 から分割移動)

既知類型との関係: 該当 (icall §4 の `callsite_arg_drop` = liftdiff 分類、REPORT_APPENDIX §9 の xmm 退行行案の続き)。

測定 commit `7e149974` (origin/main, 本 branch の起点)。`work-m11` は `lift_pe.sha256`・`functions_dll.csv`・`ir_conditions.json` を含まないため `m11_e2e.sh --full` の全再生成経路に入った。`functions_dll.csv` は Ghidra 12.1.4 (公式 zip sha256 `ddac49f9…` 一致) + JDK 21 + `tools/m2/ghidra_scripts/DumpFunctions.java` で作成 (9 分 37 秒、59,010 行)。

| 項目 | 実測 |
|---|---|
| `m11_e2e.sh --full` (`7e149974`) | 626.99 秒 (10 分 27 秒), rc 0, load 0.68 |
| survey (全再生成直後, unit 別 942 本) | **ok 872 / trap 23 / miss 46 / noproc 1** (trap 内訳 OOB 15 / Halt0 7 / unreachable 1) |
| survey (増分再実行, unit 別 JSON 出力) | 46.94 秒, ok 872 / trap 23 / miss 46 / noproc 1 (全再生成直後と一致) |
| 0 詰め site / 引数 (`m11_sigfix_stats.sh`, `7e149974` の全再生成 IR) | **1,061 site / 2,084 引数** (argrecover 突合 1,016 site, 突合済み引数 1,983。未突合 101 = 2,084 − 1,983) |
| unit 838 / 882 / 885 | ok / ok / ok (基準の退行チェック対象) |

### 突合済み引数の内訳 (`7e149974` の全再生成 IR)

| 分類 | 引数数 |
|---|---:|
| callee_unused | 313 |
| inherit | 1,185 |
| set_const | 18 |
| set_const_xmm_callee | 49 |
| 測定済み 4 カテゴリの和 | **1,565** |

上の 4 カテゴリ (和 1,565) は前 run で `7e149974` の全再生成 IR から記録された値で、本 run では再測定していない。残りの set_other / stack_set_other / callee_nopdata (和 418) は、この run では `7e149974` の IR を再生成できず測定できないため、表に載せない。その測定と 1,983 との突合は #1479 に移す。

### 再測定 (本 PR, work-m11 スナップショット): 3e49295 の記録と一致

`7e149974` の全再生成 IR は本 run では作り直していない。代わりに `$ARTIFACTS_DIR/work-m11.tar.zst` を展開した `tools/m11/work/boot_final.ll` (生成 commit は未確認) から、`bash tools/m11/m11_sigfix_stats.sh` を実行した (3.94 秒, rc 0, load 0.70, n=1)。`fl-win64` の `block00031_PE.bin` を `PE` に指定。`m11_argrecover_verify.py` は 18/18 一致。

| 分類 | 引数数 | 旧記録 (3e49295, §9) |
|---|---:|---|
| callee_unused | 313 | 313 |
| inherit | 1,172 | 1,172 |
| set_const | 18 | 18 |
| set_const_xmm_callee | 48 | 48 |
| set_other | 378 | 378 |
| stack_set_other | 32 | 32 |
| callee_nopdata | 2 | 2 |
| 7 カテゴリの和 | **1,963** | 1,963 (= 2,064 − 未突合 101) |

0 詰め site 1,049 / 引数 2,064、突合 site 1,004 (`no_pdata` 23・`unmatched` 22)。7 項目すべてが 3e49295 の記録と一致した。

この結果から言えること:
* `work-m11` の IR から出した 7 カテゴリは 3e49295 の記録と全項目一致 (生成 commit は未確認)。`7e149974` の全再生成 IR の値 (inherit 1,185 / xmm 49) とは異なる。この差 (1,172 → 1,185、48 → 49) は、本節の注記でのみ説明する。分類器 (`m11_argrecover.py`) は両 commit で不変。
* どの commit の変更で動いたかは、3e49295 と 7e149974 の site 単位突合が必要で、本 run では未実施 (#1479 の前提・受入条件に記載)。
* `work-m11` 由来の 1,963 は `7e149974` の 1,983 とは別の測定値で、表には混ぜない。
* 未突合の 101 は両方とも同じ gap (2,064 − 1,963 = 101、2,084 − 1,983 = 101)。内訳 (work-m11 の `fixes.json` の `site_detail`、0 詰め引数 = `want − have`): `no_pdata` 23 site / 33 引数 (callee の .pdata が無い)、`unmatched` 22 site / 68 引数 (突合不能)。合計 101。`no_pdata` / `unmatched` の site は両方で 1,016 site の突合から外れた (1,061 − 1,016 = 45 site = 23 + 22)。
* 0 詰め引数の差は 2,084 (7e149974) − 2,064 (work-m11) = +20、突合済みの差は 1,983 − 1,963 = +20。未突合 101 は両方で同じなので、この +20 はすべて突合済み側に入る。内訳のうち既知なのは inherit +13 (1,172 → 1,185) と xmm +1 (48 → 49) の計 +14。残りの +6 は 7e149974 の set_other / stack_set_other / callee_nopdata の合計 418 (= 1,983 − 1,565) と 3e49295 の 412 の差に当たるが、418 は未測定のため、この +6 の内訳は不明 (#1479 の突合で確定する)。

### 注記
* 数値の原因: 1,172 → 1,185 の原因は**未特定**。3e49295 と 7e149974 の site 単位の突合を #1479 の前提と受入条件に追加した。
* `tools/m11/results/sigfix_zeropad_remaining.tsv` は `m11_sigfix_stats.sh` の再生成物のため、本 PR には含めない (未コミット)。
* 再測定 (after) と `fix_xmm_args.py` の接続は未実施 (子 issue #1479)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| set_other / stack_set_other / callee_nopdata (和 418) の `7e149974` 値と 1,983 との突合 | 表が 4 カテゴリまでしか埋まらない | #1479 |
| 1,172 → 1,185 / 48 → 49 の原因 commit (3e49295 と 7e149974 の site 単位突合) | 基準の分類値の解釈 | #1479 |
| xmm 引数を読む callee の署名復元と unit 別 after 測定 (unit 838/882/885 を含む) | set_const_xmm_callee 49 引数が未解決 | #1479 |
