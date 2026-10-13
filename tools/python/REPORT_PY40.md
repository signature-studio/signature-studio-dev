# tools/python REPORT 付録: PY-40 channels グラフ/CS エディタ系 5 関数の PE 解析 (#1529, 親 #1515)

> 正本: `tools/python/REPORT.md`。本付録は PE 解析の実測と未確定事項だけを置く。
> 対象: `closeGraphEditor` / `updateGraphEditor` / `showGraphEditor` / `showCSForm` / `focusEditor` (channels)。
> 解析対象: FL Studio 26.1.7.5653 (fl-win64 素材の `extracted/block00031_PE.bin`、FLEngine PE)。
> 解析手段: `capstone` による逆アセンブル (`analysis/flapi_kwargs.py` の `Image` を流用)。FL は実行していない (静的解析のみ)。

## 結論 (1 行)

5 関数とも引数解析・内部ディスパッチの形は PE で確定した。**範囲外 code の扱い・各 callback が変える状態・戻り値の意味は未確定**のため、`provider/fl_engine.c` への実装は今回行わない (推測実装の禁止)。mock にも 5 関数の意味論は無い。残りは #1529 で継続する。

## 1. 入口と引数形式 (確定)

`flapi_kwargs.json` の `fn_va` を `Image.off()` に渡して読んだ。アドレスは同ツールの VA 表記。

| 関数 | fn_va | flags | 書式 | kwlist | 引数の受け取り |
|---|---|---|---|---|---|
| closeGraphEditor | 0xd5cab0 | 1 (VARARGS のみ) | `i` | なし | 位置 1 個 (`[rbp+0x9c]`) |
| updateGraphEditor | 0xd5c980 | 4 (NOARGS) | なし | — | 引数なし |
| showGraphEditor | 0xd5cc90 | 3 | `iiii\|i` | temporary, param, step, index, useGlobalIndex | 5 個 (必須 4) |
| showCSForm | 0xd5c270 | 3 | `i\|ii` | index, state, useGlobalIndex | 3 個 (必須 1)。既定 state=1, useGlobalIndex=0 |
| focusEditor | 0xd5c660 | 3 | `i\|i` | index, useGlobalIndex | 2 個 (必須 1)。既定 useGlobalIndex=0 |

- `closeGraphEditor` は kwlist なし (flags=1)。実 FL はキーワード引数を受けない (`flapi_kwargs.py` の方式説明どおり)。
- `showGraphEditor` の `useGlobalIndex` 既定値は `True`。`flapi_table.json` の `sig` と一致する。
- `focusEditor` の書式 `i|i` と kwlist は、`provider/gen/fl_table.c` の `"ib"` (2 引数・必須 1) と整合する。

## 2. 共通の内部経路 (確定)

5 関数とも同じ形を取る。

1. `PyArg_Parse*` 相当 (import 表経由の call) で引数を受ける。
2. `0xd5e620` を呼ぶ。これは import 表の関数を 1 回呼ぶだけの薄いラッパー。結果の先頭 8 バイトを、以後の対象オブジェクト (`rbx`) として使う。
3. 引数を解析した後、`0xd843d0` に `(rcx=obj, rdx=イベント領域, r8=callback, r9=ctx)` を渡す。`0xd843d0` は `[obj+0x50]` の既存エントリを確認し、無ければ `0xd841e0` で新規エントリを作り、引数を `obj+0x18..0x40` と `obj+0x58` に保存する。
   - `showGraphEditor` は `[rsp+0x20..0x40]` に 5 引数 + 0 を積んでから呼ぶ。
   - `showCSForm` は `[rsp+0x20..0x30]` に 3 引数、続けて 0 を積む。
   - `focusEditor` は `[rsp+0x20..0x28]` に 2 引数、続けて 0 を積む。
   - `closeGraphEditor` は `[rsp+0x20]` に index (`[rbp+0x9c]`)、続けて 0 を積む。
   - `updateGraphEditor` は引数なしで、全て 0 を積む。
4. 戻り値は `0xd82c20(eax)` の結果。`0xd82c20` は `ecx==0` のとき、`[rip+...]` の関数ポインタ経由で一度判定してから返す (None 相当の経路)。

callback の VA: `closeGraphEditor` → 0xd5ca50 / `updateGraphEditor` → 0xd5c920 / `showGraphEditor` → 0xd5cbd0 / `showCSForm` → 0xd5c180 / `focusEditor` → 0xd5c5d0。

## 3. callback の動き (一部確定・一部未確定)

- **共通**: 各 callback は `[obj+0x60]` に `-2` (`0xfffffffffffffffe`) を書いてから、`[obj_vtable+0x98]` の述語関数を呼ぶ。述語が偽なら `[obj+0x60]` を `-4` (`0xfffffffffffffffc`) にして戻る (失敗経路)。
- **closeGraphEditor (0xd5ca50)**: 述語が真なら `[obj+0x60]=0`。次にグローバル `[...]+0xa9` が非 0 のとき `0x13076e0(cl = ([obj+0x18]==1))` を呼ぶ。`0x13076e0` は `0x863270` または `0x617920`→`0x425210` を呼び、最後にフラグ `+0x7e3` を 0 にする。
- **updateGraphEditor (0xd5c920)**: 述語が真なら `[obj+0x60]=0`。`[...]+0xa9` が非 0 のとき `0x1307760` を呼ぶ。`0x1307760` は `0x130ebf0` を経て vtable `+0x178` を呼ぶ。
- **showGraphEditor (0xd5cbd0)**: 述語が真なら `0x1005730(index, ...)` を呼び、成功なら `[obj+0x60]=0` で `0x1307490(cl=([obj+0x38]>0)...)` を呼ぶ。`0x1307490` は `[obj+0x78c]` に値を書き、`+0x7e3` フラグを見て `0xfc6560` を呼ぶ。
- **showCSForm (0xd5c180)**: 述語 → `0x1005730` → 成功なら `[obj+0x60]=0`。`index-1` で分岐し、`index==0` 相当なら `[rbp+0x28]+0x7b4` のポインタの `+0x49e` を見て `0x737640` を呼ぶ。それ以外の経路は未読。
- **focusEditor (0xd5c5d0)**: 述語 → `0x1005730` → 成功なら `[obj+0x60]=0`。`0x132f780` (`[rcx+0x64] >= 0` を返すだけ) を見て真なら `0x1330c70` を呼ぶ。`0x1330c70` は vtable `+0xe0` と `+0x260` を呼ぶ。

### 未確定 (今回の解析では確定できず)

1. **範囲外 code**: `0x1005730` は `dl` (flag) が真なら `0xfe8bb0` 経由の配列参照、偽なら別の配列を参照し、`[rdx+0x10]-1` (= 要素数 - 1) と `r8=ecx` を比較する。境界外は `al=0` で返る。ただし **`0x1005730` の後半 (境界外の戻り値と、`[r8]` へ書く値) は未読**。範囲外時に何 code を返すかは確定していない。
2. **述語の中身**: 全 callback が `[vtable+0x98]` の述語を呼ぶ。この述語が何を判定するか (エディタ可視状態・オブジェクト有効性など) は未解析。
3. **状態の意味**: `[obj+0x60]` の `-2` / `-4` / `0` は、callback の戻り値 (`al`) とは別の内部状態。FL のどの変数に対応するかは未確定。
4. **戻り値**: `0xd82c20` の None 経路は確定したが、5 関数の戻り値が常に None かどうかは、`0xd82dd0` 側の分岐を読んでいないため未確定。
5. **`showCSForm` の `state` の意味**: `state` は `[obj+0x20]` に入り、`-1` / `0` / その他で分岐する (`0xd5c1d6` 以降)。各分岐の意味は未読。
6. **`focusEditor` の `useGlobalIndex`**: `[rbx+0x20]>0` で `0x1005730` の `dl` を決める。`dl=0` 時の index の扱いは未確定。

## 4. 実装と検証の状態

- `provider/fl_engine.c` に 5 関数は未実装 (`FL_H(channels, ...)` が無い)。`provider/gen/fl_table.c` には weak 宣言のみ。
- mock (`host/fl_mock.mjs`) に 5 関数の定義は無い (`mixer.focusEditor` のみ、別関数)。そのため差分検査 (`mock` と C の diffs 0) は実施できない。
- 受入条件の判定 (#1529):
  - [ ] 5 関数の引数・戻り値・範囲外 code を PE 解析箇所つきで REPORT に残す — **部分達成**。引数形式・内部経路・callback は本節で記録。戻り値の意味・範囲外 code は未確定 (§3 未確定 1, 4)。
  - [ ] `provider/fl_engine.c` に実装し、`tests/provider_check.mjs` の実装数を更新 — 未達 (意味論未確定のため実装しない)。
  - [ ] mock に追加した関数を差分検査で mock と C の diffs 0 — 未達。
  - [ ] `FL_ENGINE=wasm node tests/all_tools.mjs` が 48/48 ok を維持 — 本 PR はコード変更 0 (文書のみ) のため、実測は未実施。判定対象のコードが変わっていない。

## 5. 次にやること (#1529 で継続)

1. `0x1005730` の後半 (範囲外時の戻り値と `[r8]` の書込み) を読み、範囲外 code を決める。
2. 5 関数の述語 (`[vtable+0x98]`) の実体を読み、判定対象を決める。
3. 戻り値 (`0xd82dd0` 側) を確認する。
4. 決まった範囲で C 実装 + mock 追加 + 差分検査を行う。未確定の関数は実装せず、本節に残す。

残り作業の起票先: #1529 (継続。新規子 issue は起票しない。同一関数群の続きのため)。
