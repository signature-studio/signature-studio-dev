> 本書は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) の §F を分割移動したもの (250 行上限のため。移動に加え、repo 外パスの置換 (素材行) と存在しない `--stat` 添付文の削除のみ行った)。
> 測定の結論は [REPORT.md](REPORT.md) を見る。他の節 (§A〜§E) は REPORT_APPENDIX.md。

## F. #1536: PLUG_NO_STATIC_DETECT の既定化 (1)

- 既定化: `lift/lift_ranges.sh` で `PLUG_NO_STATIC_DETECT` の既定を 1 にした (未設定 = `--disable-static-code-detection` あり)。`PLUG_NO_STATIC_DETECT=0` で従来 (静的検出あり) に戻る。 測定 commit: **b3030f4b** (コードを変えた最後の commit。以下 F-1 / F-2 の数値はすべてこの commit で測定)。
- 素材: `fl-win64` / `plugins-ott` を R2 配置の artifacts から展開して使用 (`FL_WIN64_DIR=<fl-win64 展開先>`。取得指定は `docs/WORKFLOW.md` §11)。ツールは `[EMSDK]` (emcc 6.0.12) と `[RETDEC]` (RetDec v5.0) を runner 同梱のものを使用。
- 測定 commit 以降のコード差分 (main 取り込み後): `git diff 0d51d876 b3030f4b -- tools/plugins/lift tools/plugins/synth` の内訳は `lift_ranges.sh` (+4、`PLUG_NAME_DEFS` opt-in)・`passes/fix_i32_ptr_arg.py` (#1509 伝播)・`passes/name_defs_to_va.py` (新規、#1537 opt-in)・`passes/test_fix_i32_ptr_arg.sh` (+35)・`REPORT_APPENDIX.md`・`synth/cpp_lift.sh` (21202 の既定 `PLUG_I32PTR_FUNCS` の修正)。 `git diff b3030f4b HEAD -- tools/plugins/lift tools/plugins/synth` は 0 行 (測定 commit 以降のコード差分 0)。 出力の全文は `git diff` で再現できる。
- **21202 の既定経路の修正 (b3030f4b)**: 直前の `5a5046de` の既定 `PLUG_I32PTR_FUNCS="function_180049450 function_180056120"` には呼出元 `function_1800599bc` が無く、`fix_i32_ptr_arg.py` の [P-T2] が「仮引数 %arg1 を伝播できない」で rc 1 になっていた (lift.log)。 呼出元を最後に足して (`function_180049450 function_180056120 function_1800599bc`) 既定 env で rc 0 になった。 これにより F-1 は現 HEAD の既定経路で再測定済み。

### F-1. BooBass_Eng (21202) の受入 (測定 commit b3030f4b、既定 env)

`bash tools/plugins/synth/cpp_lift.sh 21202 1500` (既定 env、`PLUG_I32PTR_FUNCS` 未指定)、所要 61.2 s (real)、実行直後の load `0.89 0.70 0.34` (`uptime`):

`summary.csv` = `21202,1579,0,1602,0,12,3,1,0,1,60,2,417,0,23,1600,0`

- `lift_rc` = 0 (5a5046de では P-T2 FAIL で rc 1 だった。修正 b3030f4b で解消)。
- `missing_define` = **2** (欠落 417 B / 参照欠落 0)。 `lift.log` の `[P-T2] i32 ptr-arg → i64: 分類 {"const": 17, "param": 2, "trunc": 13}`。 `missing_define_classify.py` の内訳は `symbol_named` 2 件 (`CreatePlugInstance` / `entry_point`)、`static_linked` 0 件。 受入 (`missing_define` <= 2) を満たす。
- `emcc_c_rc` は 1 (E3 `'%arg2' defined with type 'i32' but expected 'i64'`、既存と同一)。 0d51d876 の値 (`…,48,2,417,0,23,1600,0`) と比べて `lift_s` 48 → 60 のみ差分 (揺れの範囲内)。

### F-2. 他の C++ DLL への影響 (既定 vs `PLUG_NO_STATIC_DETECT=0`)

測定 commit: **b3030f4b** (HEAD と同一)。 既定 (1) は同 HEAD で 7 本を流した (`cpp_lift.sh <block> 240`)。`summary.csv` 全行 (`lift_s` を含む):

| block | 既定 (1) の `summary.csv` (b3030f4b) |
|--:|---|
| 23914 | `23914,3194,0,3697,0,34,3,0,0,0,171,2,111,0,503,3695,0` |
| 23916 | `23916,3193,0,3694,1,35,3,1,0,1,171,2,111,0,501,3692,0` |
| 24159 | `24159,1638,0,1790,0,36,3,0,0,0,54,1,61,0,152,1789,0` |
| 24163 | `24163,1644,0,1707,1,21,3,1,0,1,67,1,61,0,63,1706,0` |
| 24167 | `24167,1676,0,1833,1,22,3,1,0,1,63,1,61,0,157,1832,0` |
| 24216 | `24216,1841,0,1927,1,30,3,1,0,1,93,1,61,0,86,1926,0` |
| 24298 | `24298,3257,0,3741,0,21,3,0,0,0,159,2,111,0,484,3739,0` |

- 列 `defines`・`missing_define`・`missing_bytes`・`emcc_c_rc`・`emcc_c_rc_after_fixcmp` は 0d51d876 で測った従来 (0) / 既定 (1) の値と一致 (`lift_s` のみ 45〜171 s の範囲で揺れた)。 従来 (0) との比較は、0d51d876 の表 (`PLUG_NO_STATIC_DETECT=0` 側) を F-2 の参照値として保持し、b3030f4b で従来 (0) を再測定していないことを明記する。
- 7 本が `fix_i32_ptr_arg.py` の変更の影響を受けない根拠: `lift/lift_ranges.sh` は `PLUG_I32PTR_FUNCS` が空なら `cp` のみ (I3_ARGS 空分岐)。 `synth/cpp_lift.sh` は `B=21202` のときだけ `PLUG_I32PTR_FUNCS` を export する。 7 本は 21202 ではないため `fix_i32_ptr_arg.py` は通らず、b3030f4b の差分 (`fix_i32_ptr_arg.py` の伝播・`cpp_lift.sh` の 21202 行) は F-2 の経路に入らない。 `lift_ranges.sh` の差分は `PLUG_NAME_DEFS` opt-in の追加のみ。
- 0d51d876 の値 (WIP 測定) との比較は、既定 (1) の `missing_define`・`emcc_c_rc`・`defines` が一致することで確認した。`.ll` 本体のバイト比較はしていない。

### F-2 補遺: 従来 (0) の参照値 (0d51d876 時点)

従来 (`PLUG_NO_STATIC_DETECT=0`) の 7 本の参照値。 0d51d876 の作業ツリーで測定 (b3030f4b では未再測定)。

| block | 従来 (0) | 既定 (1) との差 |
|--:|---|---|
| 23914 | `…,34,3,0,0,0,132,2,111,0,503,3695,0` | `lift_s` のみ |
| 23916 | `…,35,3,1,0,1,132,2,111,0,501,3692,0` | `lift_s` のみ |
| 24159 | 既定と同一 (`…,36,3,0,0,0,45,1,61,0,152,1789,0`) | 差なし |
| 24163 | 既定と同一 (`…,21,3,1,0,1,51,1,61,0,63,1706,0`) | 差なし |
| 24167 | `…,22,3,1,0,1,48,1,61,0,157,1832,0` | `lift_s` のみ |
| 24216 | 既定と同一 (`…,30,3,1,0,1,75,1,61,0,86,1926,0`) | 差なし |
| 24298 | `…,21,3,0,0,0,127,2,111,0,484,3739,0` | `lift_s` のみ |

- 従来 (0) を b3030f4b で同一 HEAD 再測定していない。 上の表の従来 (0) は 0d51d876 の値で、b3030f4b の既定 (1) と比べたのは異なる HEAD 間の比較である (欠落・emcc 列は一致)。 同一 HEAD での従来 (0) 比較は、受入 (既定の是非) の判定には必須でないと判断して省いた。 必要になれば次の run で `PLUG_NO_STATIC_DETECT=0 bash tools/plugins/synth/cpp_lift.sh <block> 240` を 7 本流して追記する。

### F-3. 未解決

- `batch_lift.sh` 系 (PLUG_ICALL=1 の batch / engine_lift など `lift_ranges.sh` を呼ぶ全 lift) の出力比較は未実施。 既定化で RetDec 引数が変わるため、 batch 系の summary は再測定が必要。 起票先: #1698 (PLG-G2-21)。
- `CreatePlugInstance` / `entry_point` (symbol_named 2 件) の `function_<VA>` への正規化: 起票先 #1537 (PLG-G2-19)。

## #1686: cpp_lift 残 5 block と 23916 の修復前後 emcc_c_rc (#1509 受入条件 3)

測定: `bash tools/plugins/synth/cpp_lift.sh <block> 1500` (既定の受入コマンドそのまま)。 素材 fl-win64・toolchain-retdec・toolchain-emsdk・work-liftlib・work-fw-stage1 を展開。
- 修復後: 測定 commit `576c4976` (main)。 修復前: `1e3ee7af` (dae815ef の親)。 **修復前の比較は `PLUG_NO_STATIC_DETECT=1` を明示して取り直した** (1e3ee7af は 0d51d876 より前で、静的検出の既定が異なるため)。

| block | 修復前 summary (PLUG_NO_STATIC_DETECT=1) | 修復後 summary (576c4976) | emcc_c_rc 前→後 | 最初のエラー 前後 |
|---|---|---|--:|---|
| 23916 | `23916,3193,0,3694,1,35,3,1,0,1,186,2,111,0,501,3692,0` | `23916,3193,0,3694,1,35,3,1,0,1,168,2,111,0,501,3692,0` | 1 → 1 | 同一 (`fp_round` f80) |
| 24159 | `24159,1638,0,1790,0,36,3,0,0,0,87,1,61,0,152,1789,0` | `24159,1638,0,1790,0,36,3,0,0,0,87,1,61,0,152,1789,0` | 0 → 0 | 同一 |
| 24163 | `24163,1644,0,1707,1,21,3,1,0,1,63,1,61,0,63,1706,0` | `24163,1644,0,1707,1,21,3,1,0,1,93,1,61,0,63,1706,0` | 1 → 1 | 同一 (`fp_extend`) |
| 24167 | `24167,1676,0,1833,1,22,3,1,0,1,63,1,61,0,157,1832,0` | `24167,1676,0,1833,1,22,3,1,0,1,90,1,61,0,157,1832,0` | 1 → 1 | 同一 (`fp_extend`) |
| 24216 | `24216,1841,0,1927,1,30,3,1,0,1,93,1,61,0,86,1926,0` | `24216,1841,0,1927,1,30,3,1,0,1,99,1,61,0,86,1926,0` | 1 → 1 | 同一 (`fp_extend`) |
| 24298 | `24298,3257,0,3741,0,21,3,0,0,0,165,2,111,0,484,3739,0` | `24298,3257,0,3741,0,21,3,0,0,0,160,2,111,0,484,3739,0` | 0 → 0 | 同一 |

- 列は `summary.csv` の値。 `lift_s` 列 (11 列目) 以外は修復前後で完全一致。 `lift_s` は測定ごとに変動 (例: 23916 186 → 168 秒)。 6 block の `lift_s` の範囲は 63〜186 秒 (lift 段のみ。lift + emcc の所要は上の「所要」行)。
- 測定時の load: 修復前 1.7〜2.5 / 修復後 1.2〜3.5 (1 分平均、4 vCPU、並列 3)。
- 所要 (lift + emcc 込み、秒): 修復後 23916 176 / 24159 92 / 24163 97 / 24167 94 / 24216 102 / 24298 164。 修復前 (PLUG_NO_STATIC_DETECT=1) 23916 192 / 24159 92 / 24298 170。
- 結論: 6 block とも `emcc_c_rc` は修復前後で変化なし。 修復は 21202 のみに効く (`cpp_lift.sh` の `PLUG_I32PTR_FUNCS` 設定が 21202 限定) ため、この結果と整合する。
- 測定 commit 以降のコード差分: `git diff 576c4976 HEAD -- tools/plugins/lift tools/plugins/synth` の出力は、lift 差分 0 行 / synth 差分は本ファイル (`REPORT_APPENDIX_F.md`) の #1686 節追記のみ (文書のみ)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 21202 の `emcc_c_rc=0` 後も残る E3 以外の欠陥 | 本 issue の範囲外 | #1301 (PLG-G2-13) |
