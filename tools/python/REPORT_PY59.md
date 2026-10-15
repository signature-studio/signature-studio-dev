# PY-59 (#1974): `+0x79c` の dword・qword 書込み先の構造体同定 (部分)

親: #1916 (PY-55)・#1871 (PY-51)・#1829 (PY-50)。前段: `REPORT_PY51.md`・`REPORT_PY55.md`。
既知類型との関係: 該当なし (lift 作業ではない。PE の静的解析)。

## 結論

- **5 回目 run (§9・#2471): 受入条件 1〜3 を達成。** §8 の「登録 ID」は VMT のインスタンスサイズ (`[H-0x80]`) で、型はクラス名 (VMT の `[H-0x88]`) で同定した。`+0x79c` の書込幅の不一致は、別構造体 (TPRBaseToolForm と TPlugListForm) の同オフセットと確定した。詳細は §9。以下は 1〜4 回目の記録。
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
- 素材: `fl-win64.tar.zst` → `tools/python/work/py59/extracted/block00031_PE.bin` (`$ARTIFACTS_DIR` で実在確認後に展開)。
- `0xe39e2f`・`0xe39e5d`・`0xe39e8b`・`0xe39eb9` の 4 箇所 (`0xdd1fa0` の呼び出し元。`0xe39d50..0xe3a086` の関数内) は、第 1 引数 `rcx` を `[rip+disp]` の slot から読む。読出し先 VA は `0xdd26a0`・`0xbd2e10`・`0xde9450`・`0xdf12c0` (逆アセンブルの rip 計算値)。
  - この VA はいずれも `.text` (raw `0x9d1aa0`・`0x7d2210`・`0x9e8850`・`0x9f06c0`) で、データ slot ではない。値は code 相当のバイト列で、型を示す vtable として読めない。rip 計算が誤っている可能性を含め未確定。
- 呼び出し元の引数割当 (`0xe39e0b` 付近): 第 1 引数 `rcx` (`this`) = `[rip+disp]` の値、第 3 引数 `r8` = `[[rip+disp]]` (参照元 slot `0x15e30f8`・`.data`)、第 4 引数 `r9` = 呼び出し元の rcx。`0x15e30f8` は `this` の供給元ではない。
- 注意: `this` の読出し先 (`0xdd26a0` 等) が `.text` を指す点は、rip 計算か逆アセンブルの同期 (関数途中からの復号) のどちらかの誤りの可能性がある。未確定。
- `0x16baaf0` (§6 の global slot) は `.bss` (raw 0・zero-init)。ファイル内の初期値は 0 で、非 0 の値は起動後に入る。
- `0x11c8950` は引数を `0x86a470` へ転送するだけ (`0x86a470..0x86a601`)。`0x11c8950` が slot の実体を入れるとは確認できなかった。
- `0xec7bb8` の関数 `0xec7840..0xec7d68` は、`+0x7f4` の配列 (`[[rcx+0x7f4]+8][i]`) と `+0x7e4`・`+0x7fc` を読む。`+0x79c` の書込みは `0xec7bb8` 1 箇所 (§1 と一致)。vtable (`[this+0]`) の読出しは関数内に無い。
- 結論: 3 箇所の型名と vtable は本 run でも未同定。受入条件 1・2 は未達のまま。残りは「`0xdd1fa0` の呼び出し元 4 種の slot を実 VA で正しく読み直す」と「`0xec7840` の `this` を生成する関数の特定」。

## 8. 追加の測定 (4 回目 run): Delphi の静的ハンドルと登録 ID

### 8-1. 結論

- 受入条件 1 は**一部達成**。`0xdd2002` の `this` は、`0xdd1fa0` の呼出し元 14 件すべての slot → 静的ハンドル → 登録 ID まで特定した (候補は登録 ID 12 種。型名は未同定)。`0xec6098` の `this` は登録 ID 2296 の実体。`0xec7bb8` は未着手。
- 受入条件 2 は**未達** (幅不一致の確定と `REPORT_PY50.md` 未確定表の更新は行っていない)。
- 本 binary は **Delphi** と判断した (下記 8-2)。MSVC の RTTI (`.?AV`) 前提の vtable 探索は使えない。

### 8-2. 前提の訂正

- コンパイラ: `grep -a -c` で `System.TObject` 37 件・`Classes.TPersistent` 24 件・`Classes.TComponent` 36 件。`.?AV` は 0 件。Delphi の単位名付きクラス名と判断した。
- §1・§6・§7 の「`[rip+disp]` の読出し先 `0xdd26a0` 等は `.text` で、code 相当のバイト列」は誤り。`0xdd26a0` の qword は `0xdd2768` (`.text` 内の静的ハンドル) を指すポインタである。`0xdd2768` 自体の先頭 qword は `0x619200` (関数の先頭) で、vtable ではない。
- `0xdd1fa0` の呼出し元は全件 `mov dl, 1` で、thunk `0x410320` は `dl>=0` で `call [H-0x30]` を行い、その戻り値を `this` にする (§6)。よって `0xdd2002` の `mov qword [rax+0x79c],rcx` の `rax` (= `[rbp+0x60]`) は静的ハンドルではなく、解決後の実体である。書込み先が `.text` になるという矛盾は、この解決で消える。

### 8-3. 解決の chain (実測)

- 静的ハンドル `H` の `[H-0x30]` は、測定した全 H (下表 15 件) で同じ関数 `F = 0x40f960` を指す。`F` は `movsxd rcx, dword [rbx-0x80]` (`rbx` = `H`) で登録 ID を読み、`0x409410(ID)` (ID > 0 のとき `[rip+0xf9c86c]` の関数ポインタを呼ぶ) の戻り値 X を `0x40fb40(H, X)` に渡す。`0x40fb40` は `0x40fb66` の `mov [rsi],rdi` で `*X = H` を書いてから X を返す (`0x40fbf3`)。よって `F(H)` は X を返し、X の先頭 qword に H が入る。`0x409410` の詳細は未解析。

- `0xec6098` 系 (`0xebf510` → `0xec53b0`): slot `0x16baaf0` (.bss) は `0x11c8950` (`rdx = &slot` を out 引数として渡す) → `0x86a470` の `*out = F(B)` で書かれる。`B = 0xebef58` (ID 2296)。`0x86a470` は `[A+0xa4]` の判定の後、`call [B-0x30]` (`rcx = B`) の戻り値を `*out` に入れる。したがって `0xec6098` の `this` は、ID 2296 の登録済み実体である。
- `0xdd2002` 系: `0xdd1fa0` の呼出し元は 14 件 (`0xe39e2f`〜`0xe3a07c`)。全件 `mov dl, 1` で thunk `0x410320` を通り、戻り値 E を `0xdd2002` の `[E+0x79c]` 書込みに使う (`0xdd1fe3` の call の後は無条件)。よって `this` の候補は登録 ID 12 種 (2088・2240 は 2 件ずつ)。14 件の chain と `0xec6098` 系の 1 件を下表に載せる。slot は呼出し直前 8 命令以内の `mov rax, qword ptr [rip+disp]` の読出し先 (次命令 VA + disp)、H は slot の qword、ID は `py59_handle.py` の `[H-0x80]`。

| 呼出し元 | slot | H | ID |
|---|---|---|---|
| `0xe39e2f` | `0xdd26a0` | `0xdd2768` | 2208 |
| `0xe39e5d` | `0xbd2e10` | `0xbd2ed8` | 2224 |
| `0xe39e8b` | `0xde9450` | `0xde9518` | 2248 |
| `0xe39eb9` | `0xdf12c0` | `0xdf1388` | 2328 |
| `0xe39ee7` | `0xdf3ac0` | `0xdf3b88` | 2240 |
| `0xe39f15` | `0xdeb270` | `0xdeb338` | 2136 |
| `0xe39f43` | `0xdec3d0` | `0xdec498` | 2088 |
| `0xe39f71` | `0xdedeb0` | `0xdedf78` | 2064 |
| `0xe39f9f` | `0xdf57f0` | `0xdf58b8` | 2344 |
| `0xe39fcd` | `0xdefdc0` | `0xdefe88` | 2088 |
| `0xe39ffb` | `0xde7800` | `0xde78c8` | 2272 |
| `0xe3a026` | `0xdd0000` | `0xdd00c8` | 2240 |
| `0xe3a051` | `0xdeecb0` | `0xdeed78` | 2080 |
| `0xe3a07c` | `0xe0f3a0` | `0xe0f468` | 4568 |
| `0xebf538` (`0xec6098` 系) | `0xebee90` | `0xebef58` | 2296 |

- 測定 commit `73f40ec4` (`py59_handle.py` の `with` 化。コード変更は本 commit のみ)。`git diff 73f40ec4 HEAD -- tools/python/analysis/py59_handle.py` の出力は 0 行。HEAD で `py59_handle.py` に上表の 15 件の H を与え、`[H-0x30]=0x40f960`・ID が表と一致することを確認した。
- `0xec7bb8` 系 (`[rbp+0x48]` = `0xec7840` の `this`): 生成元は未確認。

### 8-4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 登録 ID 2064・2080・2088・2136・2208・2224・2240・2248・2272・2296・2328・2344・4568 が指す実体の型 (`0x409410` の登録表と、ID を登録する箇所) | 受入条件 1 (型名・vtable) | #2471 (PY-68) |
| `0xec7bb8` の `this` (`[rbp+0x48]`) の生成元 | 受入条件 1 | #2471 (PY-68) |
| 幅不一致の確定と `REPORT_PY50.md` 未確定表の更新 | 受入条件 2 | #2471 (PY-68) |

§9 (5 回目 run) で 3 件とも解決した。§8-4 はその時点の記録として残す。

## 9. 5 回目 run: VMT による型同定と幅不一致の確定 (#2471・PY-68)

### 9-1. 結論

- 受入条件 1 は**達成**。`0xdd2002` の `this` は TPRBaseToolForm 派生の TPR*Form 14 種のいずれか (呼出し元 14 箇所が各 H の NewInstance で生成)。`+0x79c` は TPRBaseToolForm の所有域。`0xec6098`・`0xec7bb8` の `this` は TPlugListForm の実体 (`0xec7bb8` は公開ハンドラ `FormMouseDown`・`FormKeyDown` の Self から来る)。
- 受入条件 2 は**達成**。§8 の「登録 ID」13 種 (H は 15 件) の指す型は §9-4 の表。
- 受入条件 3 は**達成**。`+0x79c` の書込幅 (qword と dword) の不一致は**別構造体の同オフセット**。`REPORT_PY50.md` の `+0x79c` 行と未確定表を更新した (§9-6)。
- 前提の訂正: §8 の「登録 ID」`[H-0x80]` は VMT の**インスタンスサイズ** (`vmtInstanceSize`) である (値は 0x8a0 = 2208 など)。ID と型は 1 対 1 ではない (2088 は TPRKeyLimitForm と TPRLevelScaleForm、2240 は TPRStrumForm と TPRScoreCreatorForm)。型の同一性は H (VMT) で決まる。
- `0x409410` は ID (サイズ) を受ける確保側と見られる (推定)。中身は未解析で、型の同定には不要だった。

### 9-2. 測定条件

- 素材: `fl-win64.tar.zst` → `tools/python/work/py59/extracted/block00031_PE.bin` (22,227,016 B。`tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で展開。`$ARTIFACTS_DIR` の実在を確認してから展開)。
- 測定 commit: `13e3de11` (`analysis/py68_vmt.py` を追加した commit)。`git diff 13e3de11 HEAD -- tools/python/analysis/py68_vmt.py` の出力は 0 行 (測定後にスクリプトは変えていない)。
- 解析スクリプト: `tools/python/analysis/py68_vmt.py` (新規)。
  - `py68_vmt.py vmt <PE> <H>...` — クラス名・インスタンスサイズ・親チェーン
  - `py68_vmt.py methods <PE> <H>...` — 親チェーン各段の公開メソッド (名前・コード VA)
- 既存の `py59_func.py`・`py59_callers.py`・`py59_refs.py`・`py59_handle.py` は再実行のみ (変更なし)。

### 9-3. VMT の構造 (実測)

Delphi 64-bit の VMT 負オフセット。15 件すべてで `[H-0xc8]==H` (自己ポインタ) が成立した。

| オフセット | 内容 (実測) |
|---|---|
| `-0xc8` | 自己ポインタ (= H) |
| `-0x98` | 公開メソッド表 (件数 word・各エントリ `[size word][code qword][ShortString 名]`) |
| `-0x88` | クラス名 (ShortString へのポインタ) |
| `-0x80` | インスタンスサイズ (dword)。§8 の「登録 ID」 |
| `-0x78` | 親 VMT の**格納位置** (`[[H-0x78]]` が親 VMT。ポインタのポインタ) |
| `-0x30` | NewInstance 相当の F (§8-3。`[H-0x30]` = `0x40f960`) |

### 9-4. H → 型 (受入条件 1・2)

`vmt` モードの出力 (HEAD = `13e3de11`)。親チェーンは、TPR 系 14 種が `TPRBaseToolForm <- TFLBaseVectorForm <- TVectorForm <- ... <- TObject`、TPlugListForm が `TBaseGlassForm <- TChildVectorForm <- TVectorForm <- ... <- TObject`。

| 呼出し元 (`0xe39d50..0xe3a086` 内) | H | `[H-0x80]` (旧「登録 ID」) | 型 |
|---|---|---|---|
| `0xe39e2f` | `0xdd2768` | 2208 (0x8a0) | TPRLegatoForm |
| `0xe39e5d` | `0xbd2ed8` | 2224 (0x8b0) | TPRQuantizeForm |
| `0xe39e8b` | `0xde9518` | 2248 (0x8c8) | TPRSliceForm |
| `0xe39eb9` | `0xdf1388` | 2328 (0x918) | TPRArpForm |
| `0xe39ee7` | `0xdf3b88` | 2240 (0x8c0) | TPRStrumForm |
| `0xe39f15` | `0xdeb338` | 2136 (0x858) | TPRFlamForm |
| `0xe39f43` | `0xdec498` | 2088 (0x828) | TPRKeyLimitForm |
| `0xe39f71` | `0xdedf78` | 2064 (0x810) | TPRFlipForm |
| `0xe39f9f` | `0xdf58b8` | 2344 (0x928) | TPRRandomForm |
| `0xe39fcd` | `0xdefe88` | 2088 (0x828) | TPRLevelScaleForm |
| `0xe39ffb` | `0xde78c8` | 2272 (0x8e0) | TPRLFOForm |
| `0xe3a026` | `0xdd00c8` | 2240 (0x8c0) | TPRScoreCreatorForm |
| `0xe3a051` | `0xdeed78` | 2080 (0x820) | TPRTripletForm |
| `0xe3a07c` | `0xe0f468` | 4568 (0x11d8) | TPRChordToolForm |
| `0xebf538` (`0xec6098` 系) | `0xebef58` | 2296 (0x8f8) | TPlugListForm |

登録 ID 13 種 (受入条件 2) の型: 2064 TPRFlipForm・2080 TPRTripletForm・2088 TPRKeyLimitForm **と** TPRLevelScaleForm・2136 TPRFlamForm・2208 TPRLegatoForm・2224 TPRQuantizeForm・2240 TPRStrumForm **と** TPRScoreCreatorForm・2248 TPRSliceForm・2272 TPRLFOForm・2296 TPlugListForm・2328 TPRArpForm・2344 TPRRandomForm・4568 TPRChordToolForm。2088 と 2240 は別クラスで、同じサイズを持つ。

### 9-5. 3 書込み箇所の対象構造体 (受入条件 1)

| 書込み | 幅 | 関数 | `this` の由来 | 所有域 (親の instsize から) | 同じ関数で扱う他フィールド |
|---|---|---|---|---|---|
| `0xdd2002` `[this+0x79c]` | qword | `0xdd1fa0..0xdd2124` | 呼出し元 14 箇所 (§9-4 の H ごとに NewInstance した実体) を rcx で受ける。型は 14 種のいずれか | TPRBaseToolForm `[0x798,0x7c8)` (親 TFLBaseVectorForm = 0x798) | `+0x798`・`+0x7ad`・`+0x7b0` は同域。`+0x790` は TFLBaseVectorForm `[0x768,0x798)` |
| `0xec6098` `[this+0x79c]` | dword | `0xec53b0..0xec61dc` | wrapper `0xebf510` が global slot `0x16baaf0` を渡す (rcx は未使用)。slot は `F(0xebef58)` = TPlugListForm の実体 (§8-3) | TPlugListForm `[0x770,0x8f8)` (親 TBaseGlassForm = 0x770) | `+0x794`・`+0x798`・`+0x7ae`・`+0x7b0` は同域 |
| `0xec7bb8` `[this+0x79c]` | dword | `0xec7840..0xec7d68` | 呼出し元 (下記) が渡す Self。TPlugListForm の実体 | TPlugListForm `[0x770,0x8f8)` | `+0x7e0`・`+0x7e8`・`+0x7f4`・`+0x7fc` (読出し) は同域 |

`0xec7bb8` の `this` の生成元 (§8 で未確認だった点):

- `0xec7ed0` は `TPlugListForm.FormMouseDown` (公開メソッド表の `FormMouseDown=0xec7ed0`)。`rbx = rcx` (Self) を保存し、`0xec7f79`・`0xec8002`・`0xec8063` で `rcx = rbx` として `0xec7840` を呼ぶ。
- `0xec7060` は `TPlugListForm.FormKeyDown` (公開メソッド表)。`0xec7114`〜`0xec7121` で `[rbp+0x30] = 0xec7710`・`[rbp+0x38] = Self` の対 (`TMethod` 形) を組み、`lea rdx,[rbp+0x30]` で渡す。ラッパー `0xec7710` は `rcx` を通し、`0xec7716` で `call 0xec7840` (`edx=0`)。Data (Self) が rcx に入る経路は Delphi のメソッドポインタ呼出し規約による (推定。受け側の関数は未解析)。
- よって 2 経路とも `this` は TPlugListForm の Self。

`0xdd1fa0` は公開メソッド表にも VMT の仮想スロットにも無い (静的メソッド)。所有域の判定は、書込みフィールドが親の instsize より後ろにあることによる。名前は推定でコンストラクタ本体。

### 9-6. 幅不一致の確定 (受入条件 3)

- `+0x79c` への書込み: qword (`0xdd2002`・TPRBaseToolForm 系) と dword (`0xec6098`・`0xec7bb8`・TPlugListForm)。
- 2 型の共通の先祖は TVectorForm (instsize 0x768)。TPRBaseToolForm の所有域は 0x798 以上、TPlugListForm の所有域は 0x770 以上で、`0x79c` を含む共有フィールドは無い。
- **結論: 別構造体の同オフセット**。同一フィールドの書込幅の不一致ではない。`REPORT_PY50.md` の `+0x79c` 行と未確定表を本 run で更新した。
- 残り: `0xffa6d0` の `byte [+0x79c]` 読出しと、`0xdc1540`・`0xdc107f`・`0xdbe405` の byte 書込みは chan の `+0x79c` で、chan の型は未同定 (§9-7)。

### 9-7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| chan (`0xffa6d0` の `byte [+0x79c]` 読出し、`0xdc1540` 等の byte 書込み) の型 | `REPORT_PY50.md` の `+0x79c` の名前と chan 系の幅 | PM 判断 (親 #1974・#1871 は close 済み。PR 本文の未解決表で追跡) |
| `+0x79c`・`+0x794` のフィールド名 | 名前のみ (幅と所有域は確定) | PM 判断 (同上) |
| `0xdd1fa0` の名前 (推定: TPRBaseToolForm 系のコンストラクタ本体) と `0x409410` の中身 | 名前のみ。型同定には不要 | PM 判断 (同上) |
