# M11-N54 (#954): xmm 引数を読む callee の IR 署名復元 (opt-in `M11_XMM_ARGS=1`)

結論: `M11_XMM_ARGS=1` で、xmm を読む callee 49 件のうち **34 件** を IR 署名へ復元した。残り 46 件は呼出し側の引数個数が署名と合わないため復元しない (未解決表)。survey は既定・opt-in とも基準と unit 別 942 本で差 0。既定は OFF のまま。

測定 commit: `98c2183` (コード変更の最終 commit)。`git diff 98c2183 HEAD -- tools/m11/m11_build.sh tools/plugins/lift/passes/fix_xmm_args.py` は空 (以後は本 REPORT のみ)。

## 測定条件

- IR: `$ARTIFACTS_DIR/work-m11` の `tools/m11/work/boot_final.ll` (生成 commit 不明)。`m11_cond.py --bind` の指紋 `69c774de…`。ir_conditions は ldfix=applied / ld108=applied を手で記録した。**#1430 の `7e149974` 全再生成 IR とは別物**で、基準 872/23/46/1 とは比較しない。
- PE: fl-win64 `block00031_PE.bin` (sha256 `b2c64da4…`、REPORT 記載と一致)。
- 実行: `m11_build.sh` (増分) → `m11_survey.mjs` (`M11_SURVEY_UNITS` で unit 別 JSON)。load 0.80。
- `m11_e2e.sh` は未実行。boot5 の中間物が snapshot に無く RetDec の再 lift が入るため、1 run に収まらない。増分 build と survey で代替した。

## 表 1: 基準と復元版 (同一 IR, 98c2183)

| 測定 | ok | noproc | miss | trap | unit 別差 (942) | build | survey |
|---|---:|---:|---:|---:|---|---:|---:|
| 既定 (`M11_XMM_ARGS` 未設定) | 869 | 1 | 47 | 25 | 0 (従来 JSON と cmp 一致) | 17 s | 15 s |
| `M11_XMM_ARGS=1` | 869 | 1 | 47 | 25 | 0 | 47 s | 15 s |

unit 838 / 882 / 885 は 基準・復元版とも ok / ok / ok。trap 内訳 (基準): OOB 15 / Halt0 7 / unreachable 1 / abort 2。

## 表 2: `fix_xmm_args.py` の内訳 (`M11_XMM_ARGS=1`, 98c2183)

| 分類 | 関数数 |
|---|---:|
| fixed (署名復元) | 34 |
| call_arity_mismatch (新設の検査で skip) | 46 |
| slot_occupied | 145 |
| no_placeholder | 70 |
| no_pdata | 452 |
| partial_slots | 5 |

fixed 34 件の call site に xmm 用の `0.0` を 78 箇所足した (`callsite_zero_args`)。

## 表 3: 退行の切り分け (作業中の版, 同一 IR)

検査前の 49 件の復元を、名前順 (`function_1221bc0` `function_1265390` `function_1311f70` `function_40c0e0` `function_40c1d0` `function_40c420` …) の前半だけ残して二分探索した。

| 復元条件 | 復元数 | ok | trap | ok→非 ok の unit |
|---|---:|---:|---:|---|
| 全 49 件 (検査なし) | 49 | 861 | 33 | 146,153,162,184,185,190,370,888,905 (9 件) / trap→ok: 149 |
| 前半 3 件 | 3 | 869 | 25 | 0 |
| 前半 4 件 | 4 | 869 | 25 | 0 |
| 前半 5 件 (+ `function_40c1d0`) | 5 | 862 | 32 | 162,184,185,190,370,888,905 (7 件) |
| 前半 12 件 | 12 | 861 | 33 | 9 件 (全 49 と同じ) |
| 全 49 件から `function_40c1d0` だけ除外 | 48 | 866 | 28 | 146,153,184,190 (4 件) / trap→ok: 149 |
| **検査あり (98c2183)** | **34** | **869** | **25** | **0** |

原因: `function_40c1d0` は IR 定義が `define i64 @function_40c1d0()` (引数 0) だが、呼出し側 68 箇所は `i128` の 1 引数 (RetDec の placeholder 形) を渡している。検査前の版は `double 0.0` を末尾へ足し、呼出しが `call i64 @function_40c1d0(i128 %1, double 0.0)` となって型と位置が合わなかった。検査前の版の退行 unit (162/184/888 など) は、いずれも名前の無い wasm 関数 845 で `unreachable` に当たった。845 が fix 対象のどれに対応するかは未確定 (未解決表の子 issue で扱う)。

## 実装

- `tools/m11/m11_build.sh`: `M11_XMM_ARGS=1` のとき `fix_xmm_args.py` を `boot_final.ll` に当て、m11_post の入力を `boot_final.xa.ll` にする。切替えは `work/xmm_args.stamp` で post 結果を無効化する。`M11_XMM_SKIP=f1,f2` は復元から外す関数 (二分探索用)。既定 0 は従来と同じ経路 (unit 別 JSON が基準と一致)。
- `tools/plugins/lift/passes/fix_xmm_args.py`: 呼出し側の引数個数が callee の既存 IR 引数数と違う関数を `call_arity_mismatch` で skip する。PLUG_XMMARG 経路 (opt-in) も同じ検査を通る。その経路の survey は未測定。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼出し側の引数個数が署名と違う 46 callee の xmm 復元 (placeholder の `i128` 引数を xmm 値へ置換する) | 0 詰め 48 引数の大半が未復元。呼出し側の xmm 実値は 0.0 のまま | [M11-N154] #2762 (子) |
| 既定を ON にするか | 既定 OFF のまま。ON の survey は差 0 だが、KPI 向上は未測定 | PM 判断 |
| 基準 JSON (`7e149974` の全再生成) の unit 別再測定、1,172→1,185 の原因 commit、7 カテゴリ | 本 REPORT は work-m11 IR 上の A/B のみ | #1479 (既存) |
| `m11_e2e.sh` の実行 (boot5 の再 lift が要る) | 増分 build と survey で代替した | 次 run |
