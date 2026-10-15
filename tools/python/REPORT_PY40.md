# tools/python REPORT 付録: PY-40 channels グラフ/CS エディタ系 5 関数の PE 解析 (#1529, 親 #1515)

> 正本: `tools/python/REPORT.md`。本付録は PE 解析の実測と未確定事項だけを置く。
> 対象: `closeGraphEditor` / `updateGraphEditor` / `showGraphEditor` / `showCSForm` / `focusEditor` (channels)。
> 解析対象: FL Studio 26.1.7.5653 (fl-win64 素材の `extracted/block00031_PE.bin`、FLEngine PE)。
> 解析手段: `capstone` による逆アセンブル (`analysis/flapi_kwargs.py` の `Image` を流用)。FL は実行していない (静的解析のみ)。

## 結論 (1 行)

5 関数とも引数解析・内部ディスパッチの形は PE で確定した。**範囲外 code の扱い・各 callback が変える状態・戻り値の意味は未確定**のため、`provider/fl_engine.c` への実装は今回行わない (推測実装の禁止)。mock にも 5 関数の意味論は無い。残りは #1529 で継続する。
(追記 run 7: §8 のとおり、確定した引数書式と、件数 = チャンネル数と仮定した index 範囲 (範囲外 code 4 は未確定) だけを C provider と mock に実装した。述語・戻り値・UI 副作用は未モデル。)

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

## 4. 実装と検証の状態 (run 1 時点。run 7 の実装は §8)

- `provider/fl_engine.c` に 5 関数は未実装 (`FL_H(channels, ...)` が無い)。`provider/gen/fl_table.c` には weak 宣言のみ。
- mock (`host/fl_mock.mjs`) に 5 関数の定義は無い (`mixer.focusEditor` のみ、別関数)。そのため差分検査 (`mock` と C の diffs 0) は実施できない。
- 受入条件の判定 (#1529):
  - [ ] 5 関数の引数・戻り値・範囲外 code を PE 解析箇所つきで REPORT に残す — **部分達成**。引数形式・内部経路・callback は本節で記録。戻り値の意味・範囲外 code は未確定 (§3 未確定 1, 4)。
  - [ ] `provider/fl_engine.c` に実装し、`tests/provider_check.mjs` の実装数を更新 — 未達 (意味論未確定のため実装しない)。
  - [ ] mock に追加した関数を差分検査で mock と C の diffs 0 — 未達。
  - [ ] `FL_ENGINE=wasm node tests/all_tools.mjs` が 48/48 ok を維持 — 本 PR はコード変更 0 (文書のみ) のため、実測は未実施。判定対象のコードが変わっていない。

## 5. 追補 (run 2): 未確定 1・4・6 の解析結果

素材: `fl-win64` の `extracted/block00031_PE.bin` (`tar --zstd -xf ... --wildcards '*block00031_PE.bin'`、2.9 秒)。`capstone` で逆アセンブル (`tools/python/work/` のスクリプト・gitignore 対象)。

### 5.1 `0x1005730` の後半 (確定 = 未確定 1 の範囲外経路)

- 引数: `ecx`=index、`dl`=フラグ、`r8`=出力ポインタ。戻り値 `al`。
- `dl!=0`: 配列 `[0x5dcad3]->[0]` を使う。`dl==0`: 配列 `[0x5da9a8]->[0]` を使う (`0x1005779` 以降)。
- 境界: 要素数 `[arr+0x10]-1` に対し `0 <= index <= 要素数-1` のときだけ `0xfe8bb0(arr, index)` を呼び、結果を `[r8]` に書いて `al=1`。
- **範囲外 (負数・上限超過) は `al=0` を返し、`[r8]` には書かない** (`0x10057b2` へ直接飛ぶ)。
- `0xfe8bb0` も同じ境界検査を持ち、範囲外は `NULL` を返す (`0xfe8bd3`)。
- 呼び出し側 `focusEditor` callback (`0xd5c5d0`): `al=0` なら `[obj+0x60]=-4` で失敗終了 (`0xd5c63a`)。`al=1` のみ `[obj+0x60]=0` へ進む。

### 5.2 戻り値 (確定 = 未確定 4 の一部)

- `focusEditor` 入口 `0xd5c660`: `0xd843d0` の結果 `eax` を `0xd82c20(ecx=eax)` に渡し、その戻り値を返す。
- `0xd82c20`: `ecx==0` のとき `[0x860485]` の関数ポインタを呼び、非 0 なら `0` を返す。`ecx>=0` 系は `0xc38bc0` (`[0xa7f719]` のグローバルを返すだけ)。
- `0xd82c20` の `ecx<0` 経路は `[vtable+0x88]` の述語で分岐する。**`0xd82dd0` は分岐先の一つで、`0xc38bc0` を呼んで `[rbp+0x28]` に格納する経路**。`0xc38bc0` の戻り値 (`[0xa7f719]` の中身) が Python 側でどう見えるかは未読。
- したがって「戻り値は常に None」とは断定できない (`0xd82c20` の `ecx>=0` 経路は `0xc38bc0` 経由で非定数)。

### 5.3 未確定 6 (`useGlobalIndex` = 0 時)

- `focusEditor` は `dl = (useGlobalIndex > 0)` を `0x1005730` に渡す (`0xd5c605`〜`0xd5c60a`)。
- よって `useGlobalIndex=0` は **別の配列 (`[0x5da9a8]`) を引く経路**であり、index の扱いは同じ境界検査。配列の中身 (何のテーブルか) は未確定。

### 5.4 残りの未確定

- 未確定 2 (述語 `[vtable+0x98]` / `[vtable+0x88]` の実体): 未解析。
- 未確定 3 (`[obj+0x60]` の `-2`/`-4`/`0` と FL 側の変数の対応): 未確定。
- 未確定 4 の残り (`0xc38bc0` の戻り値の意味): 未確定。
- 未確定 5 (`showCSForm` の `state` 分岐): 未読。

## 6. 次にやること (#1529 で継続)

1. 述語 `[vtable+0x98]` (全 callback 共通) の実体を読み、判定対象を決める。
2. `[0x5da9a8]` と `[0x5dcad3]` が指す配列の中身 (何のテーブルか) を特定する。
3. 決まった範囲で C 実装 + mock 追加 + 差分検査を行う。未確定の関数は実装せず、本節に残す。

残り作業の起票先: #1529 (継続。同一関数群の続きのため、新規子 issue は起票しない)。

## 7. 追補 (run 3): §6 の前提訂正と述語・配列の参照先

### 7.1 §6-2 の前提訂正

`0x1005730` の `[0x5da9a8]` / `[0x5dcad3]` は**絶対 VA ではなく RIP 相対の変位表記**として読んでいた。解決後の参照先は次のとおり (`0x100573e`・`0x1005779` の命令長 7 で解決)。

- `dl!=0` 側: 参照スロット `0x15e2218` (`.data`)。ファイル内の値は `0x16bafc8`。
- `dl==0` 側: 参照スロット `0x15e0128` (`.data`)。ファイル内の値は `0x16bafd0`。

どちらの値も `.bss` (VA `0x15e6000`〜、ファイル上に実体を持たない 0 埋め領域) を指す。**配列の中身は実行時に確保・初期化される**ため、静的な PE の読み取りだけでは中身 (何のテーブルか) は確定できない。

### 7.2 §6-1 述語の参照先

全 callback (`updateGraphEditor` 0xd5c920 / `focusEditor` 0xd5c5d0) の述語は、同じグローバルスロット `0x15e4790` (`.data`) を `[slot]→[+8]→obj` で辿り、`obj` の vtable `+0x98` を呼ぶ形。

- `[0x15e4790]` のファイル内値は `0x141d6b8`。その先 `[0x141d6b8]` は `.data` 内で 0。
- すなわち述語の object は実行時に生成されるインスタンスで、静的解析では vtable の中身 (`+0x98` の実体) に届かない。
- `0x15e4790` への参照は `.text` 内に 2422 件 (SKIPDATA で全命令を走査)。書き込み元を絞るには実行時トレースが要る。

### 7.3 この追補の結論

§6 の 3 項目はいずれも**静的 PE 解析では確定できない** (実行時の状態に依存する)。よって §6 の「決まった範囲で C 実装」に該当する確定事項は現時点で増えていない。C 実装・mock 追加は今回も行わない (推測実装の禁止)。

必要なのは FL 実機 (または動的トレース) での観測。起票先: #1529 (継続)。

## 8. 追補 (run 7): 引数書式と index 範囲の C 実装 (PY-40 #1529)

### 8.1 §7.2 の訂正 (run 6 で確定)

述語の参照鎖は `P=*(G)` (G = `0x15e4790`)、`Q=*(P)`、`O=*(Q+8)`、`call [O+0x98]` の 3 段。§7.2 の「`[slot]→[+8]→obj`」は段数を一つ省いた書き方だった。同じ鎖は selectOneChannel (PY-69, `0xd5af58`) と setChannelPitch の guard (PY-72) と共有する。

### 8.2 実装した範囲 (引数書式は確定・index 範囲は仮定を含む)

| 関数 | 引数 (PyArg 順に全部読む) | index の検査 (範囲外は code 4) | 戻り値 |
|---|---|---|---|
| closeGraphEditor | 1 個 (型検査のみ。callback は `[obj+0x18]==1` の判定に使う) | なし (§3 の記述に範囲検査の呼出しは無い) | None |
| updateGraphEditor | なし | なし | None |
| showGraphEditor | 5 個 (`temporary, param, step, index, useGlobalIndex=True`) | index: `0..件数-1` (件数は仮定 §8.3-2) (`0x1005730`) | None |
| showCSForm | 3 個 (`index, state=1, useGlobalIndex=False`) | index: `0..件数-1` (件数は仮定 §8.3-2) | None |
| focusEditor | 2 個 (`index, useGlobalIndex=False`) | index: `0..件数-1` (件数は仮定 §8.3-2) | None |

C (`provider/fl_engine.c`) と mock (`host/fl_mock.mjs`) は同じ順序で引数を読み、型違いは code 5、件数違いは code 5、index 範囲外は code 4 を返す (上限の件数は仮定 §8.3-2、範囲外 code 4 の出し分けは未確定 §8.3-3)。

### 8.3 未モデル (実装に入れていない・推測で決めていない)

1. **述語 `[O+0x98]` (5 関数共通)**: C と mock は真と仮定する。偽のとき callback は `[obj+0x60]=-4` の失敗経路に入るが、その判定条件は未確定 (子 #3351 で扱う。旧起票先 #2576 は CLOSED のため移送)。
2. **範囲上限の出所**: `0x1005730` が引く配列 (`useGlobalIndex≠0` は `[0x5dcad3]`、`=0` は `[0x5da9a8]`) は `.bss` で実行時に初期化される。C と mock は件数 = チャンネル数と仮定する (selectOneChannel の PY-69 と同じ扱い)。`useGlobalIndex` は値を読むだけで、経路の違いは見ていない。
3. **`-4` の文言**: `0xd82c20` の `-4` → "Index out of range" の出し分けは `0xd82c6a` の別ゲートに依る (#2642 PY-82 の対象)。ゲートが偽のときは例外にならない可能性があり、C は真と仮定して code 4 を返す。
4. **成功時の戻り値**: `0xc38bc0` 経路の戻り値は未読。None と推定 (PY-69 と同じ扱い)。
5. **UI 副作用・分岐**: `0x13076e0` / `0x1307760` / `0x1307490` / `0x737640` / `0x1330c70` の中身、`showCSForm` の `state` 分岐、`closeGraphEditor` の `[+0xa9]` 分岐は未モデル。mock に観測できる状態は無い。

### 8.4 受入条件 (run 7 時点)

- [ ] 1. 5 関数の引数・戻り値・範囲外 code を PE 解析箇所つきで記録 — **部分達成**。引数書式・index 範囲外の経路は §1・§5.1・§8.2 で確定。戻り値 (§8.3-4)・述語 (§8.3-1) は未確定。残りは子 #3351 (PY-189) に移し、#1529 の本文から外した。
- [x] 2. `provider/fl_engine.c` に実装し、`tests/provider_check.mjs` の実装数を更新 — 実装 5 関数。実装数 121 → 126 (commit `ecaa7658`。main 取り込み前の値。現 HEAD は implemented 148 で、main の PY-94・PY-95・PY-101・PY-102・PY-120・PY-172 の実装を含む)。
- [x] 3. mock と C の差分検査で diffs 0 — `tests/channels_diff.mjs` 192 呼出し、diffs 0 (ecaa7658 時点。現 HEAD は 201 呼出し。増えた 9 呼出しは main の PY-101 (#2878) の `channels.isGridBitAssigned`・`channels.getGridBitWithLoop` の呼出し)。
- [x] 4. `FL_ENGINE=wasm node tests/all_tools.mjs` が 48/48 ok — 実測 48/48 (下表)。

### 8.5 検証 (測定 commit `4d0ef6757`)

- 測定 commit: `4d0ef6757` (`origin/main` (`f44264ebe`) の取り込み merge。コードを変えた最後の commit)。前の測定 commit は `946da7fd3` (main `a5966bbc7` の取り込み)。PY-40 の対象は `provider/fl_engine.c`・`host/fl_mock.mjs`・`tests/channels_diff.mjs`・`tests/provider_check.mjs`。
- 競合 (4 回目の取り込み。PR ブランチが main に遅れたため): `tests/provider_check.mjs` の判定列と件数だけ。判定列は本 PR の `pe40` と main の `pe172` (PY-172 #3219、patterns グループ 2 件) を含め、main 側の全項目を残した。件数は main の 143 (implemented、pe172 を含む) + 本 PR の 5 = **148** (implemented)、未実装 287 (総数 435)。`handler 148` (provider build) と一致する。
- 差分確認: `git diff 4d0ef6757 HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 行 (以後の変更は REPORT のみ)。
- 環境: 4 コア。emsdk は `[EMSDK]` (emsdk 6.0.12) を使った。R2 の `toolchain-emsdk.tar.zst` は本 run の ARTIFACTS_DIR に実在し、`$RUNNER_TEMP` 配下に展開して provider を作った。その wasm は `[EMSDK]` 版と sha256 が一致した (取り込み前の 62,292 B で確認)。run 7 が R2 の `toolchain-emsdk` を取得したかは記録に無い。素材は fl-win64 から `extracted/block24429_DATA.bin`・`block24430_DATA.bin`・`block25159_DATA.bin`・`block24618_DATA.bin` の 4 件を展開 (`tar --zstd -xf` の `--wildcards`)、`fetch_inputs.sh` (`FL_WIN64_DIR` 指定) は rc 0。CPython 3.12.1 wasm (`build_cpython_wasm.sh`・rc 0・3 分 59 秒) と flpy (`FLPY_SKIP_TABLE=1 build_flpy.sh`・rc 0・6 秒で `4d0ef6757` 上に再リンク) は本 run で作成・実行した。main 取り込みで CPython・flpy の入力 (`build_*.sh`・`src/`) は変わっていない。

| 検証 | 結果 (実測。`4d0ef6757`) |
|---|---|
| `bash provider/build.sh` | rc 0。`gen_provider.py --check-handlers` の handler 148。`dist/flprov.wasm` 63,031 B |
| `node tests/channels_diff.mjs` | calls 201・diffs 0・PASS (rc 0) |
| ネガティブコントロール (mock の focusEditor の index 範囲検査 `if (idx < 0 \|\| idx >= st.channels.length) throw RANGE();` を一時的に外す) | `4d0ef6757` 上で 1 回実行: `node tests/channels_diff.mjs` が **rc 1**・AssertionError「差分 2 件」(`channels.focusEditor` の args `[3]`・`[-1,false]` で mock は ok、wasm は code 4)。元に戻し `git status` が空 (差分 0 行) を確認 → 再実行 calls 201・diffs 0・PASS・rc 0。レビュワーの実行 (`946da7fd3`) の rc 1 と一致。 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | total 48・ok 48・soft_error 0・raised 0・host_calls 37,425・callback_roundtrip true (rc 0) |
| `node tests/provider_check.mjs` | functions 435・implemented 148・unimplemented 287・mcp_static 60・PASS (rc 0) |
| `node tests/*_diff.mjs` (18 本) | 全て rc 0・diffs 0・PASS (arrangement・arrangement_selection・channels・device・general・ilmcp・launchmap・midi_path・mixer・note_enum・patterns_group・playlist・screen・step_item・transport・ui・ui_display・ui_state) |

- 表の全行は `4d0ef6757` で実行した値。前の測定 commit `946da7fd3` の値 (handler 146・62,292 B・implemented 146・16 本) は main の取り込みで変わったため使わない。
- 起動・GUI の KPI (FLEngine 起動の dispatch 数・通過 unit 数・最初のウィンドウ) は**動かしていない** (flapi の引数検査だけの変更で、FLEngine の boot は実行していない)。
- 解析手段: 静的 (`analysis/flapi/pe_disasm.py` 系)。素材の `block00031_PE.bin` を使う再解析は run 7 では行っていない (§8.3 の未確定点は run 2〜6 の記録のとおり)。

### 8.6 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 述語 `[O+0x98]` の真偽条件と `-4` の失敗経路 | C・mock は述語を真と仮定するため、偽になる実機の失敗経路は成功扱いになる | #3351 (PY-189・同じ O の解析。旧起票先 #2576 (PY-77) は CLOSED のため移送) |
| `0xd82c6a` ゲート (`-4` の文言の出し分け) | range error が Python 例外にならない可能性 | #2642 (PY-82) |
| 成功時の戻り値 (`0xc38bc0` 経路) | None 以外の戻り値の可能性 | #3351 (PY-189) |
| 範囲上限の配列 (`[0x5dcad3]`・`[0x5da9a8]`) の要素数の出所 | useGlobalIndex=0 時の範囲が件数と違う可能性 | #3351 (PY-189) |
| UI 副作用・`showCSForm` の state 分岐・`closeGraphEditor` の `[+0xa9]` 分岐 | 表示状態は観測できないため mock 上は差が出ない | #3351 (PY-189。観測手段が無いため継続。FLEngine boot の前進 #672・#3060 が前提) |
