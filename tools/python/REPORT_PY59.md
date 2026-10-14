# PY-59 (#1974): `+0x79c` の dword・qword 書込み先の構造体同定 (部分)

親: #1916 (PY-55)・#1871 (PY-51)・#1829 (PY-50)。前段: `REPORT_PY51.md`・`REPORT_PY55.md`。
既知類型との関係: 該当なし (lift 作業ではない。PE の静的解析)。

## 結論

- 受入条件 1 (3 箇所の対象構造体の同定) は**部分達成**。`0xec7bb8`・`0xec6098` は、書込み先 `this` を持つ関数 (`0xec7840`・`0xec53b0`) まで特定した。`0xdd2002` は `0xdd1fa0` 関数内で `this` (`[rbp+0x60]`) を引数 `rcx` で初期化するが、`0xdd1fde` で `0x410320` の戻り値に再代入される (呼び出し元 14 件はすべて `dl!=0` で、この経路に入る)。型は未同定。
- 受入条件 2 (幅不一致の扱い) は**未達**。同一構造体の同一フィールドか、別構造体の同オフセットかは、型名が決まらないと確定できない。

## 測定条件

- 素材: `fl-win64.tar.zst` → `extracted/block00031_PE.bin` (`tar --zstd -xf ... --wildcards '*block00031_PE.bin'`、22,227,016 B)。展開先は `tools/python/work/py59/` (gitignore)。展開の実測は 2 回: 2.27 秒 (cfc80969 の再測定)・2.86 秒 (レビュー側の再測定)。
- 測定 commit: `2f115b91` (解析スクリプト `tools/python/analysis/py59_func.py`・`py59_callers.py` を最後に変えた commit)。`git diff 2f115b91 HEAD -- tools/python/analysis/py59_func.py tools/python/analysis/py59_callers.py` の出力は 0 行 (差分 0)。後続 `cfc80969` は本 REPORT の文言修正のみ。`tools/python/analysis` 全体では main 取り込み (py54・py58 の追加) により差分があるが、PY-59 の解析スクリプトには触れていない。
- 関数範囲は `.pdata` (RUNTIME_FUNCTION・PE 例外テーブル) から取る。実測: 57,816 件。`int3` 区切りや線形復号による推定は、途中の不正命令で境界がずれたため使わなかった (後述 §4)。
- 解析スクリプト:
  - `tools/python/analysis/py59_func.py <PE.bin> <VA> [dump]` — VA を含む関数範囲 (`.pdata`) と、必要なら関数全体の逆アセンブル。
  - `tools/python/analysis/py59_callers.py <PE.bin> <VA>` — 指定 VA への `call` (E8)・`jmp` (E9) の位置を列挙。
- 再現: `python3 tools/python/analysis/py59_func.py tools/python/work/py59/extracted/block00031_PE.bin 0xec7bb8 dump`

## 1. 3 箇所の関数範囲と `this`

| 書込み | 関数 (`.pdata`) | `this` の由来 | 関数の呼び出し元 |
|---|---|---|---|
| `0xdd2002` `mov qword [rax+0x79c],rcx` | `0xdd1fa0..0xdd2124` (0x184) | 引数 `rcx` を `[rbp+0x60]` に退避。`0xdd1fde` で `[rbp+0x60]` を `0x410320` の戻り値で再代入 (`dl!=0` のとき。`dl==0` なら rcx のまま)。`rax=[rbp+0x60]` | 計 14 箇所 (`0xe39e2f` を含む・全件 `call`。全件で呼出し直前 8 命令の窓内に `mov dl, 1` があり、窓内で dl を書く命令はそれだけ) |
| `0xec7bb8` `mov dword [rax+0x79c],esi` | `0xec7840..0xec7d68` (0x528) | 引数 `rcx` を `[rbp+0x48]` に退避。`rax=[rbp+0x48]` | `0xec7716`・`0xec7f79`・`0xec8002`・`0xec8063` |
| `0xec6098` `mov dword [rax+0x79c],ecx` | `0xec53b0..0xec61dc` (0xe2c) | 引数 `rcx` を `[rbp+0x120]` に退避。`rax=[rbp+0x120]` | `0xebf564` 1 箇所 (ラッパー `0xebf510`) |

- `0xec6098` の関数: `cmp dword [rax+0x7e0],1` の分岐の内側で書かれる。同じ関数で `+0x794`・`+0x798`・`+0x7ae`・`+0x7b0` も書く。`+0x7e0`・`+0x7e8`・`+0x7f4`・`+0x8b8` も読む。
- `0xec7bb8` の関数: `+0x7e0`・`+0x7e8`・`+0x7f4`・`+0x7fc` を読む。`+0x79c` の書込みは `0xec7bb8` の 1 箇所、`+0x794` の読出しは `0xec7c24` の 1 箇所 (`mov ecx,[rbx+0x794]` で `rbx` は別オブジェクト)。
- `0xdd1fa0` の関数: `+0x790` (qword)・`+0x798`・`+0x79c` (qword)・`+0x7ad` (byte)・`+0x7b0`・`+0x380` 系の vtable 呼出し (`call [rbx+0x380]`) を持つ。`+0x79c` は `0xdd2023` で qword として読まれ、`0xdd20a1` で `cmp qword [rax+0x79c],0` される。

## 2. 幅不一致の扱い (推定)

- `0xec6098` (dword) と `0xec7bb8` (dword) は、`+0x79c` を dword で書く。`+0x79c` を byte で読むのは `0xffa6d0` (`cmp byte [rcx+0x79c],0` の読出しのみ)、byte で書くのは chan 生成 (`0xdc1540`・`0xdc107f`・`0xdbe405`、書込みのみ)。
- `0xdd2002` (qword) は `0xdd1fa0` で qword として読み、`cmp qword [rax+0x79c],0` で判定する。
- **結論 (推定)**: `+0x79c` は `0xdd1fa0` 系 (qword) と、`0xec53b0`・`0xec7840` 系 (dword) の**少なくとも 2 種類**の `this` に現れる。`0xec6098`・`0xec7bb8` は同じ `this` レイアウト (`+0x7e0`・`+0x7e8`・`+0x7f4` が共通) を持つ可能性があり、`0xdd1fa0` とは別物と見られる。ただし型名は未同定のため、確定ではない。

## 3. 未確定と根拠の限界

- 型名 (クラス名) はどれも未同定。`this` の vtable を読めば型を絞れるが、本 run では vtable アドレスの特定まで進めなかった。
- `0xec53b0` の `this` は、ラッパー `0xebf510` が `[rip+0x7fb591]` (グローバル slot) から取って渡す (`0xebf564`)。`0xebf510` の呼び出し元は 17 件あり、引数 `rcx` は使わない。グローバル slot が指す実体が単一か複数かは未確認。
- 「`+0x79c` は別構造体」という結論は、3 関数の `this` が chan (`+0x714`・`+0x718`・`+0x738`・`+0x739` を一切読まない) でないことに基づく。これは確認済み (chan 固有フィールドは 3 関数とも 0 件)。

## 4. 解析手法の注意 (PY-55 との差分)

- `int3` 区切りと線形復号による関数先頭の推定は、`0xec7bb8` で失敗した (逆アセンブル開始位置がずれ、`0xec6bb8` の誤表示も出た)。
  以後は `.pdata` (`py59_func.py`) で範囲を取る。`REPORT_PY55.md` の `py55_fieldwrites.py` が出す偽陽性 (命令の途中から読んだ誤命令) は、本件でも同じ条件で出うる。
- `py59_callers.py` は E8/E9 のバイト列走査のため、単独では命令境界を保証しない。§1 の呼び出し元の件数は、逆アセンブルで命令境界上の `call` と照合して全件一致を確認した。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0xdd2002`・`0xec7bb8`・`0xec6098` の型名 (クラス名) と vtable | 幅不一致の確定 (受入条件 1・2) | #1974 (PY-59・残り) |
| `0xec53b0` の `this` が単一グローバルか、複数インスタンスか | 同一構造体かどうかの確定 | #1974 (PY-59・残り) |
| `REPORT_PY50.md` の未確定表の更新 | 受入条件 2 | #1974 (PY-59・残り) |

## 6. 追加の測定 (2 回目 run)

- 測定 commit: `ec02f804` (新規 `tools/python/analysis/py59_refs.py` を追加した commit)。
  - 前回の測定 commit `2f115b91` からの差分: `git diff --stat 2f115b91 ec02f804 -- tools/python` は 18 ファイル・916 行追加 (main 取り込み分 py54・py58 等を含む)。
  - PY-59 の実行コードは変わっていない: `git diff 2f115b91 HEAD -- tools/python/analysis/py59_func.py tools/python/analysis/py59_callers.py` の出力は 0 行。
  - `py59_refs.py` は `git log --oneline -- tools/python/analysis/py59_refs.py` で `ec02f804` のみ (初登場)。
- 新規スクリプト `tools/python/analysis/py59_refs.py <PE.bin> <VA>...` は `.pdata` の関数単位で逆アセンブルし、rip 相対で指定 VA を参照する命令を列挙する。実測 33.6 秒 (`.text` 全体)。
- global slot `0x16baaf0` (`0xebf558` で `0xec53b0` の `this` として読む) を rip 相対で参照する箇所は 13 件 (`0xebf51e`・`0xebf528`・`0xebf53f`・`0xebf54b`・`0xebf558`・`0xebf584`・`0xebf58e`・`0xebf7b2`・`0xebf7bb`・`0xebfb04`・`0xebfb12`・`0xec652e`・`0xec6537`)。
  - 直接の書込みは `0xebf7bb`・`0xec6537` の `mov qword [slot], 0` の 2 箇所のみ。
  - `0xebf53f` は `lea rdx, [slot]` で slot の**アドレス**を `0x11c8950` に渡す。slot の実体はこの呼出し先で間接的に書かれうるため、「非 0 を入れる命令は無い」とは言えない。`0x11c8950` の中身は未確認。
- `0xdd1fde` の `call 0x410320` は vtable 呼出しの thunk: `mov rax, rcx` の後 `dl>=0` のとき `call qword [rax-0x30]` を行い、戻り値を `this` にする。thunk の先頭アドレスから型は導けない。
- RTTI の型名文字列 (`.?AV...`) は本 binary に見当たらない (`grep -a` で 0 件)。型名は vtable の直接参照を辿る必要がある。
- 以上により、受入条件 1 (型名・vtable) は未達のまま。残りは「global slot の実体を入れる生成元の特定」と「`[obj+0]` に vtable を書く生成関数の特定」。

## 7. 追加の測定 (3 回目 run)

- 測定 commit: `ab13d73d` (作業 base = origin/main。解析スクリプトは変更していない)。`git diff ec02f804 HEAD -- tools/python/analysis/py59_func.py tools/python/analysis/py59_callers.py tools/python/analysis/py59_refs.py` の出力は 0 行。
- 素材: `fl-win64.tar.zst` → `tools/python/work/py59/extracted/extracted/block00031_PE.bin` (`$ARTIFACTS_DIR` で実在確認後に展開)。
- `0xe39e2f`・`0xe39e5d`・`0xe39e8b`・`0xe39eb9` の 4 箇所 (`0xdd1fa0` の呼び出し元。`0xe39d50..0xe3a086` の関数内) は、第 1 引数 `rcx` を `[rip+disp]` の slot から読む。読出し先 VA は `0xdd26a0`・`0xbd2e10`・`0xde9450`・`0xdf12c0` (逆アセンブルの rip 計算値)。
  - この VA はいずれも `.text` (raw `0x9d1aa0`・`0x7d2210`・`0x9e8850`・`0x9f06c0`) で、データ slot ではない。値は code 相当のバイト列で、型を示す vtable として読めない。rip 計算が誤っている可能性を含め未確定。
- `0xdd1fa0` の `this` 供給元の slot は `0x15e30f8` (`.data`) (`r9` 経由で `0xdd1fa0` の第 3 引数に渡る値の参照元。`mov r9, [rip+...]; mov r9, [r9]`)。`[slot]` の値は runtime で決まる。
- `0x16baaf0` (§6 の global slot) は `.bss` (raw 0・zero-init)。ファイル内の初期値は 0 で、非 0 の値は起動後に入る。
- `0x11c8950` は引数を `0x86a470` へ転送するだけ (`0x86a470..0x86a601`)。`0x11c8950` が slot の実体を入れるとは確認できなかった。
- `0xec7bb8` の関数 `0xec7840..0xec7d68` は、`+0x7f4` の配列 (`[[rcx+0x7f4]+8][i]`) と `+0x7e4`・`+0x7fc` を読む。`+0x79c` の書込みは `0xec7bb8` 1 箇所 (§1 と一致)。vtable (`[this+0]`) の読出しは関数内に無い。
- 結論: 3 箇所の型名と vtable は本 run でも未同定。受入条件 1・2 は未達のまま。残りは「`0xdd1fa0` の呼び出し元 4 種の slot を実 VA で正しく読み直す」と「`0xec7840` の `this` を生成する関数の特定」。
