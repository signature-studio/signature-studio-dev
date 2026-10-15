# PY-211 (#3539): patterns の移動・ジャンプ・探索 3 関数の委譲先本体と index 基準 (PE 解析・コード変更 0 件)

親: #3522 (PY-208) / 前段: PR #3541 (`tools/python/REPORT_PY208.md`、未 merge・main には無い) / 兄弟: #3536 (構造体 E)・#3537 (選択リスト)・#3538 (選択系 3 関数)。既知類型との関係: 該当なし (PE の逆アセンブル読解と検査スクリプト。lift 作業ではない)。

## 結論

- **受入 1 (委譲先の本体)**: 3 関数の本体の所在を PE 解析箇所つきで確定した (「委譲先の本体」)。**副作用の本体** (vtable `+0x1f0`・`+0x108` の呼出し先) は未確定で、子 #3558 (PY-213) に移す。
- **受入 2 (範囲外 index)**: **暫定決定**。パターン番号は 1..999。範囲外は**何もせず None を返す** (例外も呼出しもしない)。根拠は movePattern の O=NULL 経路が範囲外を呼ばずに返すこと (0xe33efe–0xe33f0e)。jumpToPattern の本体には範囲検査が無く、実機での挙動は未確認 (#3558)。
- **受入 3 (index 基準)**: パターン番号は **1 始まり**。jumpToPattern・findFirstNextEmptyPat は Python 値をそのまま使う。selectPattern だけ Python 値から 1 を引く (0xd662e1) ので 0 始まりの選択位置になる。**movePattern の引数は番号ではなく相対量** (移動先 = 現在番号 + 引数。既定 1)。
- **前段 `REPORT_PY208.md` の訂正 3 点** (「前段 REPORT_PY208 の訂正」): 表と G の番地は rip 相対の変位 (disp) で VA ではない / 表の要素幅は 24 B ではなく **192 B** / `0x409c80` は flags 変換ではなく **1 バイト複写**。

## 測定

- 測定 commit: `574c37c36` (検査スクリプト `tools/python/analysis/py211_pattern_jump_move.py` を追加した commit)。この後のコード範囲の差分は 0 行 (`git diff 574c37c36 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力 0 行、PR 作成直前に確認)。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (`oc_artifacts: fl-win64`)。展開: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C work/py211 --wildcards '*block00031_PE.bin'` (実測 2.758 秒・`real 0m2.758s`)。展開先 `tools/python/work/py211/extracted/` は gitignore。
- 検査: `python3 analysis/py211_pattern_jump_move.py work/py211/extracted/block00031_PE.bin` → **18/18 PASS**・rc 0・実測 `real 0m0.126s`。load average は同じ検査の直前 (uptime 02:18:43 UTC) で `0.00 0.06 0.09` (1/5/15 分値)。
- ネガティブコントロール: `--mutate` (movePattern の上限 `cmp eax, 0x3e7` の即値を `0x3e8` に書き換えたメモリ上の複製で検査) → `FAIL move.upper_bound_999`・`FAIL crosscheck.bytes_3e7_jg`、16/18 PASS・rc 1。検査は効いている。
- 別算法の検算: capstone の逆アセンブルとは独立に、機械語の並び `3d e7 03 00 00` + `jg` (7f / 0f 8f) を .text のファイル上で正規表現で数えた。出現 26 件の中に 0xe33f09 がある (同形は他関数にもあるため、番地の包含だけを見る)。
- 解析方法: capstone で関数先頭から ret までを逆アセンブルし、rip 相対の参照は「次命令の VA + disp」で VA に解決した (`decode()`)。表 (`0x193fcf8` 付近) の所在は `.bss` (ファイル上に初期値が無く、実行時に埋まる)。要素数は PE から決まらない。

## 委譲先の本体 (受入 1)

### 3 callback の共通の形

- 3 callback (`0xd659c0` jump / `0xd66e70` move / `0xd65b30` find) は同じ gate: `T = [[0x15e4790]]`、`P = [T+8]`、`P.vtable[+0x98]` の戻り値 al が偽なら status は −2 のまま、真なら status を 0 にして本体を呼ぶ (`0xd659d0`〜`0xd659ee`、`0xd66e80`〜`0xd66e9e`、`0xd65b44`〜`0xd65b62`)。
- status の初期値 −2 は `mov qword [rbx+0x60], -2` (`0xd659c8`・`0xd66e78`・`0xd65b3c`)。callback は index を検査しない。
- 本体へ渡す値は raw: jump と move は `mov ecx, [rbx+0x18]` (`0xd659f6`・`0xd66ea6`)。find は `0x409c80` で flags の下位 1 バイトを複写し (後述)、x (`[rbx+0x20]`)・y (`[rbx+0x28]`) をそのまま渡す (`0xd65b82`〜`0xd65b89`)。
- wrapper: jumpToPattern `0xd65a10` (index を `movsxd` して `[rsp+0x20]` へ・`0xd65a7b`〜`0xd65a82`)、movePattern `0xd66ec0` (既定値 `mov dword [rbp+0x9c], 1` が `0xd66ef4`)、selectPattern `0xd66230` (`mov eax, [rbp+0xac]` → `sub eax, 1` が `0xd662db`〜`0xd662e1`)。

### jumpToPattern 本体 `0x12d8af0` (引数 ecx = index)

| VA | 所見 |
|---|---|
| 0x12d8af8 | `index == [0x15d51a0]` (現在番号と比較) なら `0xe5af80` を呼ぶ (役割は未同定) |
| 0x12d8b14〜0x12d8b25 | Z = `[[[0x15e2eb8]]+0x7a8]` (オブジェクト) |
| 0x12d8b30 | `call [Z.vtable+0x1f0]` (引数 Z, index, r8b=1)。**副作用の本体 (未同定 → #3558)** |
| 0x12d8b39〜0x12d8b4f | 要素 E(i) = `0x193fcf8 + 192·i` (rip 解決先)。`cmp dword [E(i)], 0` の直後 `jl` で負なら 0x12d8b74 へ |
| 0x12d8b51〜0x12d8b6f | `[[0x15e1610]]` の byte が非 0 なら `0x11e84a0(dword E(i))` (役割は未同定) |
| 0x12d8b74〜0x12d8b8f | `0x12ddaa0([0x15d51a0])`。`0x1046710()` が非 0 なら `0xbd68e0(0x14, 0)` |
| 0x12d8b94〜0x12d8bc5 | `[[0x15e2478]] ≠ 0` かつ `[[[0x15e2478]]+0x9e8]` の byte (+0xa9) が非 0 なら `0xe55c80` |
| 0x12d8bd0 | ret。**index の上限・下限の検査は無い** |

### movePattern 本体 `0xe33e20` (引数 ecx = 相対量 ebx)

| VA | 所見 |
|---|---|
| 0xe33e3d〜0xe33e4e | O = `[[0x16ba808]+0xd34]` (選択の対象)。O が NULL なら 0xe33ee7 へ |
| 0xe33e57〜0xe33ec1 | O ≠ NULL (選択あり): 数 n = `0xea6e30(O)`、番号の配列 arr[i] = `0xea66b0(O, i)`。`[O+0x6f7] = 0` (0xe33ed2) |
| 0xe33ee7〜0xe33efb | O = NULL: `0xe5af90` が min = max = 現在番号 (`[[0x15e4018]]` の指す dword) を返す |
| 0xe33efe〜0xe33f02 | `min + ebx <= 0` なら 0xe33f6f (呼出し無し) |
| 0xe33f04〜0xe33f0e | `max + ebx > 999` なら 0xe33f6f (呼出し無し)。範囲内なら arr = [min..max] |
| 0xe33f90〜0xe33fbc | T = `[[0x15e4790]]` (callback の gate と同じ T)、Y = `[T+0x10]`。`call [Y.vtable+0x108]` (引数 Y, arr, 末尾, ebx, flag)。**副作用の本体 (未同定 → #3558)** |

- 0xe33f6f 以降の共通部は、配列の長さが 0 なら呼出しを飛ばす (`test`・`jle` の順。0xe33f7f〜0xe33fc2)。O = NULL で範囲外のとき、配列は 0 のままなので呼出しは起きない。

### findFirstNextEmptyPat の探索 `0x12d8be0` (引数 cl = flags (u8)、edx = x、r8d = y)

| VA | 所見 |
|---|---|
| 0x12d8bf2〜0x12d8c08 | 開始 r14 = 0 (flags の bit0 が立つとき) / `[0x15d51a0]` (立たないとき)。戻り値の初期値 −1 (0x12d8bf6) |
| 0x12d8c15〜0x12d8c39 | 候補 cand = ((r14 + k − 1) mod 999) + 1 (k = 1..1000、`cmp r13d, 0x3e8` at 0x12d8d0a)。`imul` の魔法数 0x83340521 で 999 の剰余を取る。**cand ∈ [1, 999]** |
| 0x12d8c3e〜0x12d8c5e | flags の bit3 (8) が立つと、dword E(cand) ≥ 1 の候補を捨てる (空きだけを採る) |
| 0x12d8c64〜0x12d8c75 | `0x12d8d30(cand, dl=1, r8b=0, r9b=0)` (空き判定の述語) が偽なら次の候補 |
| 0x12d8c85〜0x12d8c8d | bit2 (4) が立たないなら `0x12d8af0(cand)` = jumpToPattern の本体を呼ぶ |
| 0x12d8c98〜0x12d8cae | bit1 (2) が立たないなら `0x12e21a0(x, y, −1, word)` |
| 0x12d8d18 | 見つからなければ −1 のまま。戻り値は callback が捨てる |

### flags の変換 `0x409c80` (memmove: dst = rdx、src = rcx、n = r8)

- 0x409c80 は n ≤ 0x20 の経路を持つ汎用の複写。n = 1 は 0x409cc8 の経路 (`movzx eax, byte [src]` → `mov byte [dst], al`) で 1 バイトだけ写す。
- callback `0xd65b30` は `mov r8d, 1` で呼ぶ (`0xd65b72`〜`0xd65b78`)。つまり **flags は下位 8 bit に切り詰められる** (256 以上は上位が落ちる)。issue の『flags の変換』は、この切り詰めのこと。

## 範囲外の扱い (受入 2)

| 関数 | 本体の検査 | 決定 | 根拠 |
|---|---|---|---|
| jumpToPattern | 無し (`0x12d8af0`) | **暫定**: 範囲外 (1..999 の外) は何もせず None | 同系の movePattern (O = NULL) が範囲外を呼ばずに返す。callback・wrapper に範囲外用のエラー経路が無い |
| movePattern (O = NULL) | あり (0xe33efe〜0xe33f0e) | **確定** (native どおり): 移動先が 1..999 の外なら何もしない | 実測の分岐 |
| movePattern (O ≠ NULL) | 無し | **暫定**: jumpToPattern と同じく何もしない (実機未確認 → #3558) | 本体は全選択を vtable `+0x108` に渡すだけ。範囲の判定は呼出し先次第 |
| findFirstNextEmptyPat | index は無い | 探索は 1..999 を wrap。空きが無ければ −1 で何もしない | 候補式 (0x12d8c18〜0x12d8c3b) |

- **status −4 (Index out of range) は、この 3 関数では返らない。** callback が status に書くのは −2 (初期値) と 0 だけ (3 callback の `mov qword [rbx+0x60], 0` は `0xd659ee`・`0xd66e9e`・`0xd65b62`)。
- P が偽のとき (status −2) の文言は前段 PY208 の対応表 (「Operation unsafe at current time」) による。本 REPORT では再確認していない。

## index の基準 (受入 3)

| 根拠 | 場所 (VA) | 示すこと |
|---|---|---|
| movePattern: 移動先の下限を `<= 0` で弾く | 0xe33efe〜0xe33f02 | 有効な番号の下限は 1 |
| movePattern: 移動先の上限を `> 999` で弾く | 0xe33f09〜0xe33f0e | 上限は 999 |
| findFirst: 候補式 `(x mod 999) + 1` | 0x12d8c18〜0x12d8c3b | 候補は 1..999。0 は一度も探索されない |
| findFirst: 開始は現在番号 `[0x15d51a0]` からの次 | 0x12d8c08・0x12d8c15 | `[0x15d51a0]` は 1 始まりの現在番号と読める (推定) |
| jumpToPattern は Python 値を加工しない | 0xd659f6・0xd65a7b | Python 値 = 表の添字 |
| selectPattern は Python 値 − 1 | 0xd662e1 | 0 始まりの選択位置へ写す (選択の loop の意味は前段 PY208 の所見) |

- パターン番号は **1 始まり・有効 1..999**。
- jumpToPattern・findFirstNextEmptyPat の番号は Python 値のまま (加工なし)。
- selectPattern のみ `値 − 1` (0 始まりの選択位置)。
- movePattern の引数は番号ではなく **相対量** (既定 1)。flapi_table.json の movePattern は sig が null (引数名は不明)。実装する側は、引数を番号として扱わないこと。
- 残る注意: E(0) (`0x193fce0 + 0x18`) は表の中に存在するが、探索も範囲検査も 0 を使わない。0 が実行時に未使用かは実値が要る (未解決)。

## 前段 REPORT_PY208 の訂正 (PR #3541 は別 run の branch のため触らない)

1. 表の `表 0x6671b8`・`G=0x87edb9`・`G=0x87d909` などは、rip 相対の変位 (disp) である。VA は「次命令の VA + disp」で、表 = `0x193fcf8`、P の大域 = `0x15e4790` (3 callback 共通)。
2. 表の要素幅は「24 バイト」ではなく **192 B**。`shl rbx, 3` → `lea rbx, [rbx+rbx*2]` → `[rax+rbx*8]` で `24·8·i`。
3. `0x409c80(&flags, &byte, 1)` は flags 変換ではなく **1 バイト複写 (memmove・n = 1)**。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| jumpToPattern の副作用本体 (vtable `+0x1f0`・Z の型) と、範囲外の実機の挙動 | jumpToPattern の副作用・暫定決定の確度 | #3558 (PY-213) |
| movePattern の副作用本体 (vtable `+0x108`)・O ≠ NULL の範囲外の挙動 | movePattern の副作用・暫定決定の確度 | #3558 (PY-213) |
| 空き判定 `0x12d8d30`・`0x12e21a0`・`0xe5af80`・`0x11e84a0`・`0x12ddaa0`・`0xe55c80` の本体 | findFirst・jump の副作用の細部 | #3558 (補助)・#3536 (構造体 E) |
| `[0x15d51a0]` と `[[0x15e4018]]` が同じ現在番号か (1 始まりの根拠の強さ) | index 基準の根拠 (推定) | 本 REPORT に推定として残す (追跡のみで子は起票しない) |
| E(0) が実行時に未使用か | 0 を範囲外とする決定の根拠 | 同上 |

## 再現

```
cd tools/python
tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C work/py211 --wildcards '*block00031_PE.bin'
python3 analysis/py211_pattern_jump_move.py work/py211/extracted/block00031_PE.bin
python3 analysis/py211_pattern_jump_move.py work/py211/extracted/block00031_PE.bin --mutate
```

- 第 1 行: 18/18 PASS・rc 0。第 2 行: FAIL 2 件・rc 1 (ネガティブコントロール)。

## 検証範囲 / 範囲外

- 範囲内: 上記の VA の逆アセンブル (capstone) と 18 件の検査。
- 範囲外: 実行時の値 (表の中身・現在番号の実値・オブジェクトの型)、呼出し先 (vtable `+0x1f0`・`+0x108` など) の本体。範囲外に関わる結論は「暫定」と書いた。
- provider・host の実装は変えていない (推測実装は禁止・実装は本 issue の範囲外)。
