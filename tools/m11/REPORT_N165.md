# M11-N165 (#2903): call_arity_mismatch の 9 callee の分類

既知類型との関係: D5 (`docs/DEFECTS.md`、xmm 引数の落ち) の子。`REPORT_N154.md` 表 3 の「変換不能 9 callee」を、呼出し個数の不一致の原因で分類した。新規類型は無し。

結論: 9 callee の xmm 枠の位置はすべて IR 引数の直後に揃っている (`xmm3` / `xmm1` / `xmm0`)。不一致の原因は呼出し site の引数列だけにある。8 件は **IR 引数 (GPR) が呼出し側に無い** 0 引数 site を含み、1 件 (`function_6a3ac0`) は **余分な引数の型** (IR 0 引数に対し 4 引数 site: `i64 i64 i8 i128`)。xmm 変換 (`conv_ok`) を満たす site が 1 つも無いため、**復元は 0 件**。survey (942 unit) の A/B は unit 別差 **0**。既定は OFF のまま。

## 測定条件

- IR: `work-m11` の `tools/m11/work/boot_final.ll` (sha256 `69c774de…`、N54 指紋と一致)。`ir_conditions.json` は素材に無いため、`ldfix`・`ld108`・`r8b`・`ld115` = applied を手で記録して `--bind` した (N154 と同じ扱い。正規の生成経路ではない)。
- PE: fl-win64 `extracted/block00031_PE.bin` (sha256 `b2c64da4…` 一致)。
- 測定 commit: `6a253996` (分類の出力を足したコード commit)。以後の REPORT commit は文書のみ (下の差分表)。
- 単位: n=1。`m11_xmm_stats.sh` 1 回 1 分 18 秒 (前処理を含む)。`m11_xmm_ab.sh` (build 2 回 + survey 2 回) 1 分 18 秒。load は測っていない。

## 表 1: 9 callee の分類 (`m11_xmm_stats.sh` の `[arity]` 行を実測)

| callee | IR 引数 n | 機械語が読む xmm 枠 | 呼出し site (個数:型 ×件数) | cause (`ok`/`short`/`xmm`/`extra`) | 区分 |
|---|---|---|---|---|---|
| `function_651510` | 3 (`i64` ×3。`%arg3` は本体で未使用) | xmm3 | 0:[] ×2 | short:2 | IR 引数が呼出し側に無い |
| `function_6613b0` | 1 (`i64`) | xmm1 | 1:[i64] ×1、0:[] ×1 | ok:1,short:1 | IR 引数が呼出し側に無い (一部 site) |
| `function_6774b0` | 1 | xmm1 | 0:[] ×6 | short:6 | IR 引数が呼出し側に無い |
| `function_67d9b0` | 1 | xmm1 | 1:[i64] ×5、0:[] ×3 | ok:5,short:3 | IR 引数が呼出し側に無い (一部 site) |
| `function_695e80` | 1 | xmm1 | 0:[] ×2 | short:2 | IR 引数が呼出し側に無い |
| `function_6a3ac0` | 0 | xmm0 | 4:[i64 i64 i8 i128] ×8、1:[i128] ×1 | xmm:1,extra:8 | 余分な引数の型 |
| `function_6a4ac0` | 1 | xmm1 | 0:[] ×1 | short:1 | IR 引数が呼出し側に無い |
| `function_7cea90` | 1 | xmm1 | 0:[] ×1 | short:1 | IR 引数が呼出し側に無い |
| `function_7cf4b0` | 1 | xmm1 | 1:[i64] ×1、0:[] ×1 | ok:1,short:1 | IR 引数が呼出し側に無い (一部 site) |

- `cause` の定義 (`fix_xmm_args.py` の `arity_cause`): `ok` = 引数数が n と一致 / `short` = n 未満 / `xmm` = n を超え、超えた分が全て `i128` / `extra` = n を超え、超えた分に `i128` 以外を含む。
- 変換の判定 (`conv_ok`) は、全 site が `ok` か「n + 枠数 の位置が全て `i128` の `xmm`」のときだけ真。表 1 の 9 件はすべて `short` か `extra` を含むため偽。
- 0 引数 site へ xmm 値だけを足すと、先頭の GPR 引数 (`i64`) の位置に `double` が入り型が合わない。GPR を 0 詰めすると、呼出し側の未設定の値を実値として渡すことになる (未検証)。このため復元しない。
- 参考: `function_40c650` は cause `xmm:16` (全 site が変換可能) だが、survey 退行 (unit 149・158) のため `NO_CONV` で外している (#2902)。

## 表 2: survey A/B (同一 PE・同一コード。`m11_xmm_ab.sh`)

| arm | ok | trap | miss | noproc | oom | clobber |
|---|---:|---:|---:|---:|---:|---:|
| 0 (`M11_XMM_ARGS=0`) | 872 | 21 | 47 | 1 | 1 | 0 |
| 1 (`M11_XMM_ARGS=1`、この IR で 48 callee 復元) | 872 | 21 | 47 | 1 | 1 | 0 |

- unit 別差 **0 件** (942 本)。ok 喪失 0 件、ok 獲得 0 件、watch unit (838・882・885) の非 ok 0 件。判定は REGRESSION なし (verdict OK)。
- negative control: unit 838 を ok→trap に改変した写しで検出 (loss `[838]`・watch `[838]`)。
- 本 PR の変更は分類情報の追加のみ。`xa.ll` (`fix_xmm_args.py` の出力) は変更前と **バイト一致** (`cmp`) を確認した。

## 表 3: 検査あり版の内訳 (`m11_xmm_stats.sh`、同一 IR)

| 区分 | 関数数 |
|---|---:|
| fixed (復元) | 48 |
| no_pdata | 452 |
| slot_occupied | 145 |
| no_placeholder | 64 |
| call_arity_mismatch | 34 |
| partial_slots | 9 |
| 計 | 752 |

- `call_arity_mismatch` 34 件の内訳 (cause 付き) は `m11_xmm_stats.sh` の `[arity]` 行に出る。
- **N154 表 4 との差**: 同じ IR 指紋 (`69c774de…`) でも fixed は 39 → 48、no_placeholder は 77 → 64、partial_slots は 5 → 9 と違う。arity 不一致 34 件は一致。原因は未確認 (未解決表)。絶対値は使わず、A/B の結果だけを根拠にする。

## 再現手順

| 数値 | コマンド |
|---|---|
| 表 1・表 3 | `FL_WIN64_DIR=<展開先> bash tools/m11/m11_xmm_stats.sh` (`work/ir_conditions.json` の手記録が前提) |
| 表 2 | `FL_WIN64_DIR=<展開先> bash tools/m11/m11_xmm_ab.sh` (`[ab] verdict` と `[negctl]` を見る。IR 不変で終了 2 になる場合は空振り) |

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 9 callee の IR 引数 (GPR) を呼出し側から回収する方式 (0 詰めを含む) が未決 | 9 callee は復元できない。0 詰めは未検証の値を渡すため、採るかどうかは判断が要る | 判断待ち (PM)。方式を決めてから起票 |
| `function_6a3ac0` の 4 引数 site (`i64 i64 i8 i128`) と IR 0 引数の対応 (4 番目の i128 が xmm3 か) | 1 件の復元方式が未確定 | 判断待ち (PM) |
| `function_40c650` の変換で unit 149・158 が退行する原因 | 1 件が `NO_CONV` で保留 | #2902 [M11-N164] |
| N154 表 4 と本 run の内訳の差 (fixed 39 → 48 ほか) | 絶対値は使えない。A/B のみ有効 | #1479 (canonical 基準・OPEN) へのコメント |
