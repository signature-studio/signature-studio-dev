# REPORT_1275 — ClassCreate ON の unit 304/555 (oob→abort): `function_535c2e` の正体と kind 遷移 (#1275, 親 #912)

結論: `function_535c2e` が IR に無いのは **lift (RetDec) 起因**。機械語では `function_535bf0` の本体内の `ret` (VA 0x535c2e) で、関数入口ではない。RetDec がこの `ret` を独立した関数への `call` として出力したため、IR に定義が無い。受入条件 1・2・3 は本 run で判定できた (§1)。304/555 の真因 (OOB) は本 issue の範囲外で、#1426 (N91) ほかに残る。

既知類型との関係: 該当なし (lift の分岐先の `ret` を関数呼出しに誤ったもの。DEFECTS.md の既存類型には当たらない。新類型として §4 に行案を記す)。

## 0. 基準

- 測定 commit: `604e900f` (origin/main 取込時点。コード変更なし)。本 PR は `40c35ed5` (再現スクリプト `n78_measure.sh` のみ追加)。現 HEAD は `a57e158b` (その後は REPORT・DOC_MAP のみ変更。コード差分は §8)。
- 素材: fl-win64 (`$RUNNER_TEMP/fl-win64`)・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff (`$HOME/artifacts` から展開。実在確認済み)。`m11_gen_ir2.sh` で IR を作り直した (`ldfix=applied`)。
- 再現: `FL_WIN64_DIR=... RETDEC_ROOT=... EMSDK=... bash tools/m11/trap_triage/n78_measure.sh` (全工程 rc=0。測定 commit `604e900f` で 2 分 20 秒、load 0.13〜0.6。HEAD `a57e158b` で再実行し 2 分 25 秒、開始時 load average 1.38・終了時 1.08。両方とも §4 と同じ数値)。

## 1. 受入条件の判定

| 受入条件 | 判定 | 根拠 |
|---|---|---|
| `function_535c2e` が IR に無い理由を機械語突合で特定 | **達成** | §2。`0x535c2e` は `function_535bf0` (63B) の内部の `ret`。RetDec が分岐先の `ret` を call に変換 |
| ON の abort 2 件 (304/555) の扱いを REPORT に記録 | **達成** | §3。現状 (abort = fail-fast) と、転記 `M11_FIX_535BF2=1` の効果 (abort→oob・ok 数不変)。既定は変えない (PM 判断) |
| OFF / ON 両構成で 304/555 の kind 遷移を `survey_diff.py` で記録 | **達成** | §4 |

## 2. `function_535c2e` の機械語突合

`disasm_fn.py` で `0x535bf0` の 63B を逆アセンブル (`FL_WIN64_DIR` の `block00031_PE.bin`):

```
535bf0: jmp 0x535c11                 ; 関数入口
535bf2: add qword ptr [rcx+0x10], 1 ; cnt++
  ...
535c0b: je  0x535c11
535c0d: mov al, 1
535c0f: jmp 0x535c2e                 ; ← ここが 535c2e へ飛ぶ
535c11: ... cmp [rcx+0x10], rax
535c2a: jl  0x535bf2
535c2c: xor eax, eax
535c2e: ret                          ; ← 535c2e = 関数 535bf0 の共通の ret
```

- `0x535c2e` は `[0x535bf0, 0x535bf0+63)` の内側。関数の入口ではない (`disasm_fn.py 0x535c2e` は `.pdata` に入口が無く KeyError)。
- IR (`work/boot_final.ll`): 189350 行で `call i64 @function_535c2e()`、490151 行で `declare i64 @function_535c2e()` (定義なし)。
- したがって原因は **lift**: 分岐先の `ret` を RetDec が独立関数への call に変えた。closure の seed を足しても直らない (`ret` の途中アドレスで `size(sv)` が 0 になる。REPORT_714 §2 と一致)。
- `m11_rt.c:190` の `m11_unresolved_function` が fail-fast で abort させる (ON 時の abort の直接原因)。

## 3. ON の abort 2 件 (304/555) の扱い

| 構成 | 304 | 555 | 備考 |
|---|---|---|---|
| OFF (既定) | oob | oob | 先頭フレーム `function_535bf2` |
| ON (`M11_OV_CLASSCREATE=1`) | **abort** | **abort** | `[m11][fail-fast] unresolved function call: function_535c2e` |
| ON + `M11_FIX_535BF2=1` | oob | oob | 転記で abort は消える。OOB は残る (先頭 `function_410010`) |

- 扱いの選択肢: (a) 現状維持 (ON の abort を残す)、(b) 転記 `M11_FIX_535BF2` を ON と併用、(c) closure 拡張 (不可: §2 の通り seed では直らない)。
- (b) は abort を OOB に変えるだけで、ok 数は動かない (ON+転記 ok 869 = ON ok 869)。既定は変えていない (`M11_FIX_535BF2` 既定 0 のまま)。既定 ON 化は PM 判断。
- ON の 190 (ok→oob) は本件の範囲外。REPORT_704 の既知の退行で、ON+転記でも変わらない (§4)。

## 4. kind 遷移 (`survey_diff.py`、測定 commit `604e900f`)

種別の合計は 3 構成とも 942 unit (`survey_units.mjs` の出力と一致)。`trap` 列は `survey_diff.py` の派生値 (`oob + halt0 + abort + other`) で、種別の 1 つではないので合計に含めない。

| 構成 | ok | oob | abort | halt0 | miss | noproc | other | 合計 | trap (派生) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| OFF | 870 | 16 | 0 | 7 | 47 | 1 | 1 | 942 | 24 |
| ON | 869 | 15 | 2 | 7 | 47 | 1 | 1 | 942 | 25 |
| ON + `M11_FIX_535BF2=1` | 869 | 17 | 0 | 7 | 47 | 1 | 1 | 942 | 25 |

`trap` の OFF → ON の +1 は unit 190 (ok→oob) による。304/555 の oob→abort は trap 数を変えない (2 件とも trap のまま)。

`survey_diff.py` の全出力 (HEAD `a57e158b`、上記の数値と同じ実行):

```
$ python3 trap_triage/survey_diff.py work/n78/units_off.json work/n78/units_on.json 304 555 101 190 291 296 923
A: {'halt0': 7, 'miss': 47, 'noproc': 1, 'ok': 870, 'oob': 16, 'other': 1}  trap=24
B: {'abort': 2, 'halt0': 7, 'miss': 47, 'noproc': 1, 'ok': 869, 'oob': 15, 'other': 1}  trap=25
遷移 (A -> B):
  halt0   -> halt0   7
  miss    -> miss    47
  noproc  -> noproc  1
  ok      -> ok      869
  ok      -> oob     1
  oob     -> abort   2
  oob     -> oob     14
  other   -> other   1
ok 退行 unit: 1 [190]
unit 304: oob -> abort Aborted(native code called abort())
unit 555: oob -> abort Aborted(native code called abort())
unit 101: ok -> ok 
unit 190: ok -> oob memory access out of bounds
unit 291: ok -> ok 
unit 296: ok -> ok 
unit 923: oob -> oob memory access out of bounds
kind 以外も含めた差分 unit (frames は深さのみ比較): 10 [114, 190, 280, 291, 296, 302, 304, 555, 659, 888]

$ python3 trap_triage/survey_diff.py work/n78/units_off.json work/n78/units_on_fix.json 304 555 101 190 291 296 923
A: {'halt0': 7, 'miss': 47, 'noproc': 1, 'ok': 870, 'oob': 16, 'other': 1}  trap=24
B: {'halt0': 7, 'miss': 47, 'noproc': 1, 'ok': 869, 'oob': 17, 'other': 1}  trap=25
遷移 (A -> B):
  halt0   -> halt0   7
  miss    -> miss    47
  noproc  -> noproc  1
  ok      -> ok      869
  ok      -> oob     1
  oob     -> oob     16
  other   -> other   1
ok 退行 unit: 1 [190]
unit 304: oob -> oob memory access out of bounds
unit 555: oob -> oob memory access out of bounds
unit 101: ok -> ok 
unit 190: ok -> oob memory access out of bounds
unit 291: ok -> ok 
unit 296: ok -> ok 
unit 923: oob -> oob memory access out of bounds
kind 以外も含めた差分 unit (frames は深さのみ比較): 10 [114, 190, 280, 291, 296, 302, 304, 555, 659, 888]
```

遷移 (OFF → ON) の要約: ok→ok 869、ok→oob 1 (unit 190)、oob→abort 2 (unit 304, 555)、oob→oob 14、miss/halt0/noproc/other は不変。
遷移 (OFF → ON+転記) の要約: ok→ok 869、ok→oob 1 (unit 190)、oob→oob 16 (304/555 を含む)、miss/halt0/noproc/other は不変。

- 304 / 555: OFF `oob` → ON `abort` → ON+転記 `oob`。kind 遷移の判定はこの通り。
- 291 / 296 (REPORT_682 の ok 対象): OFF・ON とも `ok`。ネガコンは §5。
- `check_682.py` (304/555/923/291/296): 実測の出力は `units ok 0 / 5`・rc=1。kind は 291・296 が ok、304・555・923 が oob で、ok 判定は 2/5 が正しい。0/5 になるのは `check_682.py` が `labels[u]` を文字列として比べているのに、`survey_units.mjs` の出力は unit ごとの dict のため (スクリプトの不具合・本 PR では未修正。`n78_measure.sh` の末尾行の「2/5 が期待値」も同じ理由で実出力と合わない)。受入 (5 unit 全 ok) は未達のまま (本 issue はこの 5 件の ok 化を目的としない)。

## 5. 検証と限界

- ネガティブコントロール: `M11_FIX_535BF2` を ON にすると 304/555 の kind が `abort` → `oob` に変わる (フラグが効いていることの確認)。フラグを外すと `abort` に戻る (§3 の表)。
- 再現性: 本 run の数字は 1 回 (n=1)。OFF 単独測定 (手作業) と通し測定 (`n78_measure.sh`) は、kind 遷移・ok/trap 数とも一致。
- 限界: 304/555 の OOB の真因 (`tbl`/`cnt`/`obj` の実値、`_UStrAsg` の src) は未採取。本 issue の受入条件には含まれない。
- 範囲外: 923 (`410b10`) は OOB のまま (不変)。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 304/555 の OOB の真因 (ON+転記でも oob 残存) | 2 unit が trap | #1426 `[M11-N91]` (既存・OPEN)・#714 (経緯・前任の測定) |
| 190 の ON 退行 (ok→oob)・`412e40` 経由 | ON の ok 退行 1 件 | #704 `[M11-N31]` 系 (既存・OPEN)、#912 |
| `function_535c2e` を lift で正しく出す修正 (RetDec 出力の分岐先 `ret` の扱い) | closure 外の根本 | #714 (既存・OPEN)。lift 側の修正 (PM 判断) |
| `M11_FIX_535BF2` を既定 ON にするか | ON 時の abort 2 件 | PM 判断 (本 PR では既定を変えない) |

## 7. 新類型の行案 (DEFECTS.md 形式・PM 判断で採用)

- 症状: 関数の内部 (途中) の `ret` へ飛ぶ分岐が、IR で未定義の関数への `call` になる。ON 時に fail-fast abort。
- 根本原因: RetDec が分岐先の `ret` を独立関数として切り出した (関数入口ではない VA を call 先にした)。
- 観測: `function_535c2e` (VA 0x535c2e、`function_535bf0` 内の `ret`)。`declare` のみ・定義なし。
- 検出信号: IR 内の `declare` のみの関数 (`@function_<VA>`) で、VA が `.pdata` の関数入口でない。
- 修復: 分岐先の `ret` を呼出し元の `ret` に置換する (本 run では未実施。転記 `M11_FIX_535BF2` が暫定の代替)。

## 8. 差分 (差分 0 の証跡)

測定 commit `604e900f` (origin/main) から現 HEAD `a57e158b` までの差分 (md を除く):

```
$ git diff 604e900f a57e158b -- tools/m11 ':!*.md'
 tools/m11/trap_triage/n78_measure.sh | 19 +++++++++++++++++++
 1 file changed, 19 insertions(+)
```

コード差分は再現スクリプト `n78_measure.sh` の追加のみ。`m11_*.sh`・`m11_ov.c`・`survey_units.mjs`・`survey_diff.py` は未変更。測定はスクリプトの追加前の `604e900f` で手動実行した。スクリプトは HEAD `a57e158b` で通しで再実行し (rc=0、§0)、§4 の数字と一致することを確認した。`40c35ed5` 以降の docs のみの commit (`211ced3d`・`a57e158b`) は測定対象外。
