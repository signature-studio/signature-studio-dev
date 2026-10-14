# PY-59 (#1974): `+0x79c` の dword・qword 書込み先の構造体同定 (部分)

親: #1916 (PY-55)・#1871 (PY-51)・#1829 (PY-50)。前段: `REPORT_PY51.md`・`REPORT_PY55.md`。
既知類型との関係: 該当なし (lift 作業ではない。PE の静的解析)。

## 結論

- 受入条件 1 (3 箇所の対象構造体の同定) は**部分達成**。`0xec7bb8`・`0xec6098` は、書込み先 `this` を持つ関数 (`0xec7840`・`0xec53b0`) まで特定した。`0xdd2002` は `0xdd1fa0` 関数内で `this` (`[rbp+0x60]`) が引数 `rcx` と判明したが、型は未同定。
- 受入条件 2 (幅不一致の扱い) は**未達**。同一構造体の同一フィールドか、別構造体の同オフセットかは、型名が決まらないと確定できない。

## 測定条件

- 素材: `fl-win64.tar.zst` → `extracted/block00031_PE.bin` (`tar --zstd -xf ... --wildcards '*block00031_PE.bin'`、実測 2.8 秒・22,227,016 B)。展開先は `tools/python/work/py59/` (gitignore)。
- 測定 commit: 本 PR の commit (解析スクリプト `tools/python/analysis/py59_func.py`・`py59_callers.py` を追加)。
- 関数範囲は `.pdata` (RUNTIME_FUNCTION・PE 例外テーブル) から取る。実測: 57,816 件。`int3` 区切りや線形復号による推定は、途中の不正命令で境界がずれたため使わなかった (後述 §4)。
- 解析スクリプト:
  - `tools/python/analysis/py59_func.py <PE.bin> <VA> [dump]` — VA を含む関数範囲 (`.pdata`) と、必要なら関数全体の逆アセンブル。
  - `tools/python/analysis/py59_callers.py <PE.bin> <VA>` — 指定 VA への `call` (E8)・`jmp` (E9) の位置を列挙。
- 再現: `python3 tools/python/analysis/py59_func.py tools/python/work/py59/extracted/block00031_PE.bin 0xec7bb8 dump`

## 1. 3 箇所の関数範囲と `this`

| 書込み | 関数 (`.pdata`) | `this` の由来 | 関数の呼び出し元 |
|---|---|---|---|
| `0xdd2002` `mov qword [rax+0x79c],rcx` | `0xdd1fa0..0xdd2124` (0x184) | 引数 `rcx` を `[rbp+0x60]` に退避。`rax=[rbp+0x60]` | `0xe39e2f` 他 14 箇所 (`call`) |
| `0xec7bb8` `mov dword [rax+0x79c],esi` | `0xec7840..0xec7d68` (0x528) | 引数 `rcx` を `[rbp+0x48]` に退避。`rax=[rbp+0x48]` | `0xec7716`・`0xec7f79`・`0xec8002`・`0xec8063` |
| `0xec6098` `mov dword [rax+0x79c],ecx` | `0xec53b0..0xec61dc` (0xe2c) | 引数 `rcx` を `[rbp+0x120]` に退避。`rax=[rbp+0x120]` | `0xebf564` 1 箇所 (ラッパー `0xebf510`) |

- `0xec6098` の関数: `cmp dword [rax+0x7e0],1` の分岐の内側で書かれる。同じ関数で `+0x794`・`+0x798`・`+0x7ae`・`+0x7b0` も書く。`+0x7e0`・`+0x7e8`・`+0x7f4`・`+0x8b8` も読む。
- `0xec7bb8` の関数: `+0x7e0`・`+0x7e8`・`+0x7f4`・`+0x7fc` を読む。`+0x79c` の書込みは `0xec7bb8` の 1 箇所、`+0x794` の読出しは `0xec7c24` の 1 箇所 (`mov ecx,[rbx+0x794]` で `rbx` は別オブジェクト)。
- `0xdd1fa0` の関数: `+0x790` (qword)・`+0x798`・`+0x79c` (qword)・`+0x7ad` (byte)・`+0x7b0`・`+0x380` 系の vtable 呼出し (`call [rbx+0x380]`) を持つ。`+0x79c` は `0xdd2023` で qword として読まれ、`0xdd20a1` で `cmp qword [rax+0x79c],0` される。

## 2. 幅不一致の扱い (推定)

- `0xec6098` (dword) と `0xec7bb8` (dword) は、`+0x79c` を dword で書く。`0xffa6d0` と chan 生成 (`0xdc1540`・`0xdc107f`・`0xdbe405`) は `+0x79c` を byte で読み書きする。
- `0xdd2002` (qword) は `0xdd1fa0` で qword として読み、`cmp qword [rax+0x79c],0` で判定する。
- **結論 (推定)**: `+0x79c` は同一フィールドではなく、**少なくとも 3 種類の別構造体**のフィールドを使う。`0xec6098`・`0xec7bb8` は同じ `this` レイアウト (`+0x7e0`・`+0x7e8`・`+0x7f4` が共通) を持つ可能性があり、`0xdd1fa0` とは別物。ただし型名は未同定のため、確定ではない。

## 3. 未確定と根拠の限界

- 型名 (クラス名) はどれも未同定。`this` の vtable を読めば型を絞れるが、本 run では vtable アドレスの特定まで進めなかった。
- `0xec53b0` の `this` は、ラッパー `0xebf510` が `[rip+0x7fb591]` (グローバル slot) から取って渡す (`0xebf564`)。`0xebf510` の呼び出し元は 17 件あり、引数 `rcx` は使わない。グローバル slot が指す実体が単一か複数かは未確認。
- 「`+0x79c` は別構造体」という結論は、3 関数の `this` が chan (`+0x714`・`+0x718`・`+0x738`・`+0x739` を一切読まない) でないことに基づく。これは確認済み (chan 固有フィールドは 3 関数とも 0 件)。

## 4. 解析手法の注意 (PY-55 との差分)

- `int3` 区切りと線形復号による関数先頭の推定は、`0xec7bb8` で失敗した (逆アセンブル開始位置がずれ、`0xec6bb8` の誤表示も出た)。
  以後は `.pdata` (`py59_func.py`) で範囲を取る。`REPORT_PY55.md` の `py55_fieldwrites.py` が出す偽陽性 (命令の途中から読んだ誤命令) は、本件でも同じ条件で出うる。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0xdd2002`・`0xec7bb8`・`0xec6098` の型名 (クラス名) と vtable | 幅不一致の確定 (受入条件 1・2) | #1974 (PY-59・残り) |
| `0xec53b0` の `this` が単一グローバルか、複数インスタンスか | 同一構造体かどうかの確定 | #1974 (PY-59・残り) |
| `REPORT_PY50.md` の未確定表の更新 | 受入条件 2 | #1974 (PY-59・残り) |
