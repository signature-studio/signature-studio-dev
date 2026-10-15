# tools/python REPORT: PY-141 ui 操作 27 関数の戻り値の値と型・selectWindow の引数型 (#3034, 親 #2981)

> 前段: `tools/python/REPORT_PY120.md` (PY-120・PR #3018 merged)。PE の呼出し契約と保留の正本は REPORT_PY120。本書は PY-120 で保留した 4 項目の確定と、確定できなかった項目の記録だけを持つ。
> 検算: `analysis/flapi/pe_py141_probe.py` (`FL_WIN64_DIR=<展開先>`)。素材は fl-win64 (`extracted/block00031_PE.bin`)。

## 結論

- **成功時の戻り値の既定値規則 (受入 1): 確定。既定値規則は無い。** out+8 は PE 上のどの経路でも書かれない。0x415610 は out+0x10 (managed の string 1 件) だけを 0 にし、0xd84680 は out+0 だけを書く。26 関数の成功時の戻り値 `PyLong_FromLong(out+8)` の値は PE の静的解析では定まらない (ハンドラのフレームの未初期化スロット)。実行時の値は保留 (未解決の表)。
- **0xc38bc0 (受入 2): 確定。`_Py_NoneStruct` (Py_None) を返す leaf。** scrollWindow の戻り経路 0xd82c20 は、status ≥ 0 の範囲で Py_None を返す。
- **0x15e4280 (受入 3): 確定。`PyLong_FromLong` (C long → Python int)。bool 系ではない。** 公開 stub の戻り型 `int` と一致する。
- **selectWindow の引数型 (受入 4): 確定。PE の `i` (C int) が正。** 公開 stub の `shift: bool` は型注記が不正確 (値 ≤0 の扱いが PE と食い違う)。stub の修正は本 issue の値の確定の範囲外 (未解決の表)。
- 27 関数の作用先と mock/C 実装は対象外 (PY-140 の子 #3758・#3759・#3761)。

## 確定・保留 (受入 1〜4)

| 項目 | 判定 | 根拠 (VA) |
|---|---|---|
| 0x415610 の out+8 への作用 | 確定: 無し | 型記述子 0xd81740 → `TPyCallSynchronizedResult` (RecSize 0x18、managed 1 件 = string、FldOffset 0x10)。tkUString 分岐の `mov qword ptr [rax], 0` (0x4157b9) は out+0x10 の 8 バイトだけ。out+8 に触れない |
| 0xd84680 の out への作用 | 確定: out+0 だけ | out への store は `mov qword ptr [rbx], 0 / -1 / -2` (0xd846b7・0xd846c0・0xd846c9) の 3 箇所。0xd846ad の `call 0xfdd2c0` に out (rbx) は渡らない |
| selectWindow (0xd6c140) の out+8 | 確定: 読むだけ | `[rbp+0x58]` (= out+8) への store は無い。読むのは 0xd6c1be `mov ecx, [rbp+0x58]` → 0xd6c1c8 `call [0x15e4280]` の 1 箇所 |
| 成功時の戻り値の値 | 保留 | out+8 は未初期化。PE の静的解析では値が決まらない (未解決の表) |
| 0xc38bc0 | 確定: Py_None を返す | `mov rax, [rip+0xa7f719]` → 0x16b82e0 (loader が GetProcAddress("_Py_NoneStruct") を格納。名前 VA 0xc3a41e)。`ret`。呼出し先なし |
| 0xd82c20 (scrollWindow の戻り経路) | 確定 (status ≥ 0) | status > 0 (0xd82c3a) は例外確認を飛ばして 0xd82c5c の `call 0xc38bc0` → Py_None。status == 0 は `PyErr_Occurred()` ([0x15e30c8] → 0x16b8470) が非 NULL なら NULL (0xd82c4a)、NULL なら Py_None。status < 0 は 0xd82c6a の経路 (未追跡) |
| 0x15e4280 | 確定: PyLong_FromLong | `[0x15e4280]` = 0x16b8298 (変数へのポインタ)。loader 0xc396c5 が GetProcAddress("PyLong_FromLong") を格納 (名前 VA 0xc3a292) |
| 変換の戻り型 | 確定: int | `PyLong_FromLong` は `PyObject*` (Python int)。公開 stub の `returns: int` と一致 (`analysis/flapi/flapi_table.json` の `modules.ui`) |
| 0x15e1e58 (参考) | 確定: PyArg_ParseTuple | `[0x15e1e58]` = 0x16b82f0 (変数へのポインタ)。loader 0xc397fd が格納 (名前 VA 0xc3a45e) |
| selectWindow の引数型 | 確定: C int (`i`) | 書式 `i` (0xd6c172 `lea rdx, [0xd6c220]`)。0xd6c1a0 `mov r9d, [rbp+0x6c]` で受けた値を 0xd84680 に渡す。stub の `shift: bool` は 0/1 では一致するが、負値は PE が ≤0 側に入る |
| 引数の作用 (op 0x3b の分岐) | 確定 (この分岐の範囲): 符号判定だけ | 0xfde0af `mov eax, [rbp+0x44]; test eax, eax; jle 0xfde0d3`。両側で `0x8186a0` を呼ぶ (ecx=9、dx は 0x0000 / 0x0100、r8d=1)。値そのものは渡らない。0xfdd2c0 の入口から 0xfde0af までの途中の arg 参照が op 0x3b の経路で通るかは未追跡 |
| 他 25 関数への一般化 | 保留 | 検算は selectWindow (0xd6c140) と scrollWindow の経路だけ。残りの 25 関数の `0x15e4280` 経由の形は PY-120 の表 (呼出し先・書式) からの推定 |

## 手段

- 逆アセンブル: `analysis/flapi/pe_disasm.py <VA> <命令数>` (`FL_WIN64_DIR` 指定)。
- 検算: `analysis/flapi/pe_py141_probe.py` (本 PR の新規)。out への store の列挙、ハンドラの out+8 への store の有無、loader の名前解決 (`lea` の参照先 UTF-16 名 → `mov [var], rax`)、参照チェーン (スロット → 変数) を assert する。
- 引数の確認: `0xfdd2c0` の op 0x3b の分岐 (0xfde0af) と、その先の `0x8186a0` の先頭 (`test r8d, r8d` で 16bit のフラグ word `dx` を見る)。

## 検証

- 測定 commit: `7dfc960a8` (probe を追加した commit。コードを変えた最後の commit)。
- 測定 commit から HEAD までのコード差分 (`tools/python` の md 以外。差分 0 の証跡):

```
$ git diff 7dfc960a8 HEAD -- tools/python ':!*.md'
(空)
```

- 検算の出力 (測定 commit `7dfc960a8`):

```
0xd84680 の store 先: ['byte ptr [rsp + 0x20]', 'qword ptr [rbx]', 'qword ptr [rbx]', 'qword ptr [rbx]']
ok   0xd84680 の out (rbx 基底) への store は out+0 (qword ptr [rbx]) の 3 箇所だけ
ok   0xd6c140 に out+8 ([rbp+0x58]) への書込みは無い (読むのは 0xd6c1be の 1 箇所)
ok   loader: var 0x16b8298 <- 'PyLong_FromLong' (実測 'PyLong_FromLong')
ok   loader: var 0x16b82e0 <- '_Py_NoneStruct' (実測 '_Py_NoneStruct')
ok   loader: var 0x16b82f0 <- 'PyArg_ParseTuple' (実測 'PyArg_ParseTuple')
ok   loader: var 0x16b8470 <- 'PyErr_Occurred' (実測 'PyErr_Occurred')
ok   [0x15e4280] = 0x16b8298 (PyLong_FromLong の変数へのポインタ)
ok   [0x15e1e58] = 0x16b82f0 (PyArg_ParseTuple の変数へのポインタ)
ok   [0x15e30c8] = 0x16b8470 (PyErr_Occurred の変数へのポインタ)
ok   0xc38bc0 は [0x16b82e0] (= _Py_NoneStruct のアドレス) を返す leaf (呼出し無し)
ok   0xd6c1c1 の mov は [0x15e4280] を読む (PyLong_FromLong)
PASS
```

| コマンド (測定 commit `7dfc960a8`) | 結果 | wall |
|---|---|---|
| `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py141_probe.py` | PASS (11 項目 ok・rc 0) | 0.091 秒 (load average 0.00 / 0.16 / 0.19、03:56 UTC) |
| ネガティブコントロール: 同じ probe の `"PyLong_FromLong"` を `"PyBool_FromLong"` に変えた一時コピー (`$RUNNER_TEMP` 配下。commit しない) | rc 1 (FAIL 2 行: loader の名前照合が落ちる) | 未計測 |

- 前段 REPORT_PY120 の表 (selectWindow の書式 `i`・op 0x3b・r9 = 受け取った引数) と、本 probe の出力は一致する。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| out+8 の実行時の値 (未初期化スロット) | 26 関数の成功時の戻り値の値。mock の戻り値を PE から決められない | #3758 [PY-245] (`mode` の実機値の由来と同じ確認。実行時トレースの要否を同じ子で判断) |
| 0xd82c20 の status < 0 の経路 (0xd82c6a〜) | scrollWindow のエラー時の戻り値 | #3761 [PY-247] (scrollWindow の作用先と戻り経路) |
| 引数 arg が op 0x3b の経路で符号判定以外に使われるか | selectWindow の作用 | #3035 [PY-140] (親。作用先の追跡は REPORT_PY140.md) |
| stub `ui.selectWindow` の `shift: bool` (PE は C int) | 公開 API の型注記。selectWindow を実装するときの引数契約 | #3759 [PY-246] (確定関数の mock/C 実装と同時に stub を直す) |
| 他 25 関数の個別検算 | 戻り値の形の一般化 | 起票なし。`pe_py141_probe.py` の対象を 27 関数に広げて PR 本文の未解決表で扱う |

## 受入条件の結果

- [x] 0x415610 の既定値規則 (out+8) を VA 付きで確定 (結論: 既定値規則は無い。成功時の値は未確定と明示)
- [x] 0xc38bc0 (ui.scrollWindow の戻り経路) を同定 (`_Py_NoneStruct` の leaf)
- [x] 0x15e4280 の int / bool 判定 (PyLong_FromLong = int) と公開 stub の戻り型との対応 (`int`)
- [x] ui.selectWindow の引数型の正を確定 (PE の `i`)
- [x] 結果を本 REPORT に残し、確定と保留を分けた
