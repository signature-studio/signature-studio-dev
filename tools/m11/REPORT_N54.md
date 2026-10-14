# M11-N54 (#954): xmm 引数を読む callee の IR 署名復元 (opt-in `M11_XMM_ARGS=1`)

既知類型との関係: D5 (`docs/DEFECTS.md`、既知 (F2): xmm 引数の落ち) の対処「引数追加 (f2)」を m11 の IR に適用したもの。新規類型は無し。

結論: `M11_XMM_ARGS=1` で、xmm を読む callee 49 件のうち **34 件** を IR 署名へ復元した。残り 15 件は、呼出し側の引数個数が署名と違うため検査で skip する (検査を外すと 49 件すべてが復元され、作業中の版では 9 unit が ok→trap になった: 表 3)。pass 全体の arity 不一致は 46 件で、そのうち 31 件は placeholder が無く、検査が無くても元々対象外。0 詰め 48 引数は 48 件すべて未復元 (実値への置換 0 件、表 4)。survey は既定・opt-in とも基準と unit 別 942 本で差 0。既定は OFF のまま。

測定 commit: `98c2183` (コード変更の最終 commit)。`git diff 98c2183 HEAD -- tools/m11/m11_build.sh tools/plugins/lift/passes/fix_xmm_args.py` は空 (差分 0)。以後の変更は本 REPORT と `tools/m11/m11_xmm_stats.sh` (新規、測定対象の外) のみ。

## 測定条件

- IR: `$ARTIFACTS_DIR/work-m11` の `tools/m11/work/boot_final.ll` (生成 commit 不明)。`m11_cond.py --bind` の指紋 `69c774de…`。ir_conditions は ldfix=applied / ld108=applied を手で記録した。**#1430 の `7e149974` 全再生成 IR とは別物**で、基準 872/23/46/1 とは比較しない。
- PE: fl-win64 `extracted/block00031_PE.bin` (sha256 `b2c64da4…`、本 REPORT の再実行でも一致を確認)。
- 表 1 (survey・build): `m11_build.sh` (増分) → `m11_survey.mjs` (`M11_SURVEY_UNITS` で unit 別 JSON)。load 0.80。survey 値は 98c2183 時点の測定値で、本 REPORT の再実行では再測定していない。
- 表 2・表 4・表 3 の検査なし行: `tools/m11/m11_xmm_stats.sh` を HEAD (`5c12d6a8`、上記の対象コードは 98c2183 と同一) で再実行。load 0.35、72 秒 (1 回)。
- `m11_e2e.sh` は未実行。boot5 の中間物が snapshot に無く RetDec の再 lift が入るため、1 run に収まらない。増分 build と survey で代替した。

## 表 1: 基準と復元版 (同一 IR, 98c2183)

| 測定 | ok | noproc | miss | trap | unit 別差 (942) | build (単発) | survey |
|---|---:|---:|---:|---:|---|---:|---:|
| 既定 (`M11_XMM_ARGS` 未設定) | 869 | 1 | 47 | 25 | 0 (従来 JSON と cmp 一致) | 17 s | 15 s |
| `M11_XMM_ARGS=1` | 869 | 1 | 47 | 25 | 0 | 47 s | 15 s |

build の 17 s / 47 s は各 1 回の単発値 (n≥3 の min–max は未測定)。unit 838 / 882 / 885 は 基準・復元版とも ok / ok / ok。trap 内訳 (基準): OOB 15 / Halt0 7 / unreachable 1 / abort 2。

## 表 2: `fix_xmm_args.py` の内訳 (`M11_XMM_ARGS=1`, 98c2183 のコード)

分母: `fix_xmm_args.py` が処理した `function_` 定義 752 件 (fixed 34 + skipped 718)。

| 分類 | 関数数 |
|---|---:|
| fixed (署名復元) | 34 |
| no_pdata | 452 |
| slot_occupied | 145 |
| no_placeholder | 70 |
| call_arity_mismatch (検査で skip) | 46 |
| partial_slots | 5 |
| skipped 計 | 718 |

fixed 34 件の call site に xmm 用の `0.0` を 78 箇所足した (`callsite_zero_args`)。

arity 検査の内訳: 検査を外した版 (表 3 の「検査なし」) で pass 全体の arity 不一致 46 件を判定すると、**fixed 15 件** / **no_placeholder 31 件**。つまり 49 件中の 15 件が arity 検査で skip され、残り 31 件は placeholder が無く検査が無くても対象外だった。

## 表 3: 退行の切り分け (同一 IR)

「検査なし」行は `m11_xmm_stats.sh` で再現できる (fixed 49)。それ以外の survey 行は、検査前の**作業中の版** (98c2183 に含まれない一時版) による測定で、HEAD では再現できない (非再現)。「検査あり」行は表 1 の opt-in と同一。

| 復元条件 | 復元数 | ok | trap | ok→非 ok の unit |
|---|---:|---:|---:|---|
| 全 49 件 (検査なし、作業中の版) | 49 | 861 | 33 | 146,153,162,184,185,190,370,888,905 (9 件) / trap→ok: 149 |
| 前半 3 件 (非再現) | 3 | 869 | 25 | 0 |
| 前半 4 件 (非再現) | 4 | 869 | 25 | 0 |
| 前半 5 件 + `function_40c1d0` (非再現) | 5 | 862 | 32 | 162,184,185,190,370,888,905 (7 件) |
| 前半 12 件 (非再現) | 12 | 861 | 33 | 9 件 (全 49 と同じ) |
| 全 49 件から `function_40c1d0` だけ除外 (非再現) | 48 | 866 | 28 | 146,153,184,190 (4 件) / trap→ok: 149 |
| **検査あり (98c2183)** | **34** | **869** | **25** | **0** |

二分探索の順序は名前順 (`function_1221bc0` `function_1265390` `function_1311f70` `function_40c0e0` `function_40c1d0` `function_40c420` …) の前半を残す方式。

原因 (9 unit のうち 5 unit): `function_40c1d0` の IR 定義は `define i64 @function_40c1d0()` (引数 0)。呼出しは 68 箇所あり、内訳は `i128` の 1 引数が 65 件、引数 0 が 3 件 (表 5 のコマンド)。検査前の版は全呼出しの末尾に `double 0.0` を足したため、1 引数の 65 件は `(i128 %x, double 0.0)` となり定義の引数個数 (0) と合わなかった。`function_40c1d0` だけを除外すると ok→非 ok が消える 5 unit (162・185・370・888・905) は、この呼出し個数不一致で説明できる。残り 4 unit (146・153・184・190) は `function_40c1d0` を外しても退行が残るため、原因は未特定 (未解決表)。

## 表 4: 0 詰め 48 引数の扱い (検査あり, 98c2183 のコード)

48 引数 = sigfix の 0 詰め引数 (`tools/m11/REPORT_APPENDIX.md` §9、1,049 site / 2,064 引数) のうち、`m11_argrecover.py` が `set_const_xmm_callee` (定数代入だが callee が xmm0..3 を読む。復元しない規則) と分類した引数。`fixes.json` の `site_detail` で集計した。

| fix_xmm_args の判定 (callee 単位) | 引数 | callee |
|---|---:|---:|
| fixed (復元された 34 callee) | 0 | 0 |
| call_arity_mismatch (検査で skip) | 9 | 3 |
| slot_occupied (IR に当該 xmm 位置の整数引数が既にある) | 39 | 12 |
| **計** | **48** | **15** |

- 9 引数 (3 callee) は、検査なしの版では `function_651510` (2 引数) が fixed、`function_660cc0` (4 引数) と `function_6a3040` (3 引数) が no_placeholder。
- 48 引数はいずれも実値に置き換えていない (本 PR は `set_const_xmm_callee` の規則を変えない)。復元した 34 callee にこの分類の引数は 0 件のため、34/49 の復元は 0 詰め 48 引数の値を変えない。

## 表 5: 再現手順 (1 コマンドずつ)

| 数値 | 再現コマンド |
|---|---|
| 表 1 survey・build | `M11_XMM_ARGS=0 bash tools/m11/m11_build.sh` → `M11_SURVEY_UNITS=<既定 JSON> node tools/m11/m11_survey.mjs`。`M11_XMM_ARGS=1` の同じ 2 本を別 JSON に出し、`cmp` で unit 別 JSON を比べる (差 0 が基準)。 |
| 表 2・表 4・表 3「検査なし」 | `bash tools/m11/m11_xmm_stats.sh` (前提: `work/boot_final.ll` と `PE=$FL_WIN64_DIR/extracted/block00031_PE.bin`。出力 `work/xmm_stats/`。stdout の `[表2]` `[表3]` `[arity]` `[0詰め48]` が上記の数値) |
| 表 2 の 78 / 検査前の作業中の版 | 78 は `work/xmm_stats/xa_report.json` の `callsite_zero_args`。検査前の版は非再現 (表 3 の注) |
| 40c1d0 の呼出し個数 | `grep -c 'call [^@]*@function_40c1d0(' work/boot_final.ll` (68)、`grep -c 'call i64 @function_40c1d0(i128 ' work/boot_final.ll` (65)、`grep -c 'call i64 @function_40c1d0()' work/boot_final.ll` (3) |
| PE の同一性 | `tar --zstd -xOf $ARTIFACTS_DIR/fl-win64.tar.zst extracted/block00031_PE.bin \| sha256sum` → `b2c64da4…` |
| 測定 commit からの差分 0 | `git diff 98c2183 HEAD -- tools/m11/m11_build.sh tools/plugins/lift/passes/fix_xmm_args.py` (出力なし) |

## PLUG_XMMARG 経路

`tools/plugins/lift/lift_ranges.sh` (`PLUG_XMMARG=1`) も同じ `fix_xmm_args.py` を呼ぶ (line 106) ため、arity 検査の影響を受ける。`tools/plugins/f2/REPORT_APPENDIX.md` §9.2 の復元・skip 件数は 2f77ace 時点の値で、この版には arity 検査が無い (`git show 2f77ace:tools/plugins/lift/passes/fix_xmm_args.py` に `call_arity` は 0 件)。検査後の件数は未測定。

## 実装

- `tools/m11/m11_build.sh`: `M11_XMM_ARGS=1` のとき `fix_xmm_args.py` を `boot_final.ll` に当て、m11_post の入力を `boot_final.xa.ll` に差し替える。切替えは `work/xmm_args.stamp` で post 結果を無効化する。`M11_XMM_SKIP=f1,f2` は復元から外す関数 (二分探索用)。既定 0 は従来と同じ経路 (unit 別 JSON が基準と一致)。
- `tools/plugins/lift/passes/fix_xmm_args.py`: 呼出し側の引数個数が callee の既存 IR 引数数と違う関数を `call_arity_mismatch` で skip する。PLUG_XMMARG 経路 (opt-in) も同じ検査を通る。
- `tools/m11/m11_xmm_stats.sh` (新規): 表 2・表 4 と「検査なし」版の再現。`fix_xmm_args.py` の arity 検査 3 行を外した複製を `work/xmm_stats/` に作って走らせる。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| arity 不一致で skip した 15 callee の xmm 復元 (placeholder の `i128` 引数を xmm 値へ置換する) | 0 詰め 48 引数のうち 9 引数 (3 callee)。skip 15 callee の xmm 呼出し実値は 0.0 のまま | [M11-N154] #2762 (子) |
| arity 不一致のうち placeholder の無い 31 callee | 検査が無くても元々対象外 (#2762 の範囲外) | PM agent の判断待ち: 起票先 |
| slot_occupied の 0 詰め 39 引数 (12 callee) | IR に当該 xmm 位置の整数引数が既にあり、本 pass は復元しない | PM agent の判断待ち: 起票先 |
| 検査前の退行 4 unit (146・153・184・190) | `function_40c1d0` を外しても退行が残る。原因未特定 | PM agent の判断待ち: 起票先 |
| 既定を ON にするか | 既定 OFF のまま。ON の survey は差 0 だが、KPI 向上は未測定 | PM agent の判断待ち: 既定を ON にするか・既定案: OFF (現状どおり) |
| PLUG_XMMARG=1 経路 (f2 §9.2) の arity 検査後の件数 | §9.2 は検査前の件数。検査後は未測定 | PM agent の判断待ち: 起票先 |
| 基準 JSON (`7e149974` の全再生成) の unit 別再測定、1,172→1,185 の原因 commit、7 カテゴリ | 本 REPORT は work-m11 IR 上の A/B のみ | #1479 (既存) |
| `m11_e2e.sh` の実行 / build の n≥3 の min–max | boot5 の再 lift が要る / 単発値のみ | 次 run |
