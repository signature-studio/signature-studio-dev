# M11-N154 (#2762): call_arity_mismatch の xmm 呼出し側引数の復元

既知類型との関係: D5 (`docs/DEFECTS.md`、既知 (F2): xmm 引数の落ち) の対処「引数追加 (f2)」の続き。呼出し側の値が署名と個数で食い違う callee (`call_arity_mismatch`) について、呼出し側の i128 placeholder を xmm 値へ変換して渡す方式を入れた。新規類型は無し。

結論: 方式は「呼出し側の i128 (RetDec の xmm 実値) を `trunc`+`bitcast` で float/double に変換して渡す」。N54 の 15 callee (検査なしで復元される) のうち **5 件を復元**、1 件 (`function_40c650`) は変換すると unit 149・158 が退行するため保留、残り 9 件は呼出し個数が IR 引数数と合わず変換できない。復元は 34 → **39** 件。survey (942 unit) は基準と unit 別差 **0**。既定は OFF のまま。

測定 commit: `0ea7df21` (`fix_xmm_args.py` と `m11_xmm_stats.sh` の最終 commit。表 1〜4 はこの内容で測定)。差分 (検証時の HEAD): `git diff 0ea7df21 HEAD -- tools/plugins/lift/passes/fix_xmm_args.py tools/m11/m11_build.sh tools/m11/m11_xmm_stats.sh` は本 REPORT の commit 後に確認 (本 REPORT は測定対象の外)。

## 測定条件

- IR: `tools/m11/work/boot_final.ll` (`work-m11` 展開。同梱に `ir_conditions.json` が無いため、N54 と同じく `m11_cond.py --reset ldfix=pending qstore=not-applied ld108=not-applied pe=<PE>` の後に `ldfix=applied ld108=applied` を手で記録し `--bind` した。`work-m11` の IR は #516 以前の生成 (`work-m11` の注記)。build 時に qstore 既定 (1) が走る)。
- PE: fl-win64 `extracted/block00031_PE.bin` (sha256 `b2c64da4…` 一致)。`FL_WIN64_DIR` は `$RUNNER_TEMP/fl-win64` に 1 本だけ展開。
- 単位: build 単発 (n=1)。survey 単発。load は 0.4〜0.7 (run 中の `uptime`)。
- 基準 (`M11_XMM_ARGS=0`) は本 IR 上で再測定した。N54 の表 1 (869/25) とは IR が違うため比較しない。

## 表 1: 基準と最終版 (同一 IR)

| 測定 | ok | noproc | miss | trap | oom | unit 別差 (942) | build | survey |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| 基準 (`M11_XMM_ARGS=0`) | 871 | 1 | 47 | 22 | 1 | — | 21.6 s | 12.6 s |
| 最終 (`M11_XMM_ARGS=1`, 39 件復元) | 871 | 1 | 47 | 22 | 1 | **0** | 46.2 s ※ | 12.8 s |

※ build 時間は 40 件版 (`40c650` の除外前) の単発値。39 件版の build 時間は別に測っていない。

## 表 2: 退行の切り分け (同一 IR・同一 commit の変換版)

| 構成 | 復元数 | ok | trap | clobber | unit 別差 (基準比) |
|---|---:|---:|---:|---:|---|
| 旧版相当 (新規 6 件を `M11_XMM_SKIP` で外す) | 34 | 871 | 22 | 0 | 0 |
| 新規 6 件すべて (変換あり、`function_40c650` 含む) | 40 | 870 | 21 | 2 | 149 trap→clobber、158 ok→clobber |
| 新規 A のみ (`1311f70`・`40c1d0`・`40c540`) | 37 | 871 | 22 | 0 | 0 |
| 新規 B のみ (`40c650`・`63a690`・`9ce3e0`) | 37 | 870 | 21 | 2 | 149・158 (同上) |
| `40c650` のみ | 35 | 870 | 21 | 2 | 149・158 (同上) |
| **最終 (`40c650` を `NO_CONV` で除外)** | **39** | **871** | **22** | **0** | **0** |

`function_40c650` の呼出し側 16 箇所は、`__asm_movsd` (64 bit) や `cvtss2sd` の結果を渡しており、枠は `float` (`movss`)。変換は機械語どおり下位 32 bit を渡すが、その値で 149・158 が退行する。原因は未特定 (子 issue)。

## 表 3: arity 不一致 46 callee の復元可否 (N54 の範囲)

| 区分 | callee 数 | 内訳・理由 |
|---|---:|---|
| 復元 (i128 を float/double 枠へ変換) | 5 | `function_1311f70` (float)・`function_40c1d0` (double)・`function_40c540` (double)・`function_63a690` (float)・`function_9ce3e0` (double) |
| 変換したが survey 退行のため保留 | 1 | `function_40c650` (float 枠)。表 2 |
| 変換不能 (呼出し個数が IR 引数数 n と違い、`n+枠数` の i128 以外の site、または n 未満の site がある) | 9 | `function_651510`・`function_6613b0`・`function_6774b0`・`function_67d9b0`・`function_695e80`・`function_6a3ac0`・`function_6a4ac0`・`function_7cea90`・`function_7cf4b0` |
| placeholder 無し (検査の有無によらず対象外) | 31 | `no_placeholder` 31 件 (N54 の値と一致) |
| 計 | 46 | |

N54 の「検査なしで復元される 15 callee」は、復元 5 + 保留 1 + 変換不能 9 = 15 に一致する。

## 表 4: 検査あり版の内訳と 0 詰め 48 引数 (同一 IR)

`tools/m11/m11_xmm_stats.sh` の出力 (`work/xmm_stats/`):

| 区分 | 関数数 |
|---|---:|
| fixed (復元) | 39 |
| no_pdata | 452 |
| slot_occupied | 145 |
| no_placeholder | 77 |
| call_arity_mismatch (検査で skip) | 34 |
| partial_slots | 5 |
| 計 | 752 |

- `callsite_xmm_converted` (i128 → float/double に変換した呼出し) 73 site、`callsite_zero_args` (従来の 0.0 追加) 86 site。
- 検査なし (比較用の複製・変換 + 0.0 追加): fixed 49。
- 0 詰め 48 引数 (`set_const_xmm_callee`、N54 表 4): 変換で値が変わったのは 0 件。内訳は slot_occupied 39 引数 (12 callee) と arity 不一致 9 引数 (3 callee: `function_651510`・`function_660cc0`・`function_6a3040`)。

## 再現手順

| 数値 | コマンド |
|---|---|
| 表 1・表 2 | `cd tools/m11 && M11_XMM_ARGS=0 bash m11_build.sh && M11_SURVEY_UNITS=work/survey_xmm0.json node m11_survey.mjs`。`M11_XMM_ARGS=1` の同じ 2 本 (出力 `work/survey_final.json`)。`cmp` 相当は `unit 別差` の python 比較 (配列の要素比較) |
| 旧版相当 | `M11_XMM_ARGS=1 M11_XMM_SKIP=function_1311f70,function_40c1d0,function_40c540,function_40c650,function_63a690,function_9ce3e0` で build |
| 表 3・表 4 | `FL_WIN64_DIR=<展開先> bash tools/m11/m11_xmm_stats.sh` (約 60 秒) |

## 実装

- `tools/plugins/lift/passes/fix_xmm_args.py`:
  - `split_args` (括弧の外で区切る引数列) と `conv_ok` を追加。`conv_ok` は、枠が IR 引数の直後に隙間なく並び (pad 無し)、各呼出しが (a) 引数数 n と一致する、または (b) `n + 枠数` で枠の位置の引数がすべて `i128` のとき真。
  - arity 不一致の callee は `conv_ok` が真なら skip せず適用する (placeholder の判定は従来どおり後段)。
  - 呼出しを書き換えるとき、(b) の site は直前に `%xmmcv.N.i = trunc i128 X to i32/i64` と `%xmmcv.N.f = bitcast ...` を挿入し、その値を枠に渡す。(a) の site は従来どおり `0.0` を末尾に足す。
  - `NO_CONV` (`function_40c650`): 変換すると survey が退行するため、変換から外して arity 不一致のまま skip する (表 2)。
  - report に `callsite_xmm_converted` を追加。
- `tools/m11/m11_xmm_stats.sh`: 検査なし複製の置換文字列を新しい判定行に合わせた。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_40c650` の変換で unit 149・158 が退行する原因 | 15 callee のうち 1 件が保留。float 枠に double 由来の値を渡すこと (機械語どおりの下位 32 bit) が退行の原因か未確認 | [M11-N164] #2902 (子) |
| 変換不能の 9 callee (呼出し個数が IR 引数と違う / i128 以外) | 0 詰め 9 引数 (3 callee) は 0.0 のまま。IR の int 引数の値が呼出し側に無いため、別の方式が要る | [M11-N165] #2903 (子) |
| placeholder 無しの 31 callee | 検査の有無によらず対象外 (N54 の既定案どおり、起票しない) | 起票しない |
| `m11_e2e.sh` の実行 | boot5 の再 lift が要るため、build + survey で代替 (N54 と同じ) | 次 run |
| 既定 `M11_XMM_ARGS` を ON にするか | 既定 OFF のまま | PM 判断 |
