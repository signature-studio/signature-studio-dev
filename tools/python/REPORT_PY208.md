# PY-208 (#3522): patterns の選択・移動・探索系 6 関数の PE 解析 (コード変更 0 件)

親: #1798 (PY-46) / 前段: `REPORT_PY43.md` (入口・書式)・`REPORT_PY46.md` (委譲チェーン) / 兄弟: #1799 (PY-47)。既知類型との関係: 該当なし (PE の逆アセンブル読解のみ。lift 作業ではない)。

## 結論

- 6 関数すべてについて、**引数書式・既定値・callback の VA・callback 内の分岐・戻り値の写像 (0xd82c20)** を PE 実測で確定した (下表・status 表)。
- **戻り値**: 成功時は None。失敗時は status に応じた例外文言 (status 表) を設定して NULL。例外文言の表は `0xd82c20` の `lea rdx` 先の C 文字列を直接読んだ。
- **範囲外**: `selectPattern` は範囲外を例外にせず、何もせず None (status 0)。他 5 関数は callback 内に範囲検査が見えない (`jumpToPattern`・`movePattern` の範囲検査は委譲先 `0x12d8af0`・`0xe33e20` 側にあるか未確認)。
- **副作用**: 委譲先の名前 (選択 setter `0xea6e50`・`0xea6a00`・`0xea7280`・`0xea7420`、移動 `0xe33e20`、ジャンプ `0x12d8af0`、探索 `0x12d8be0`) は確定。**本体は未読のため、どのフィールドを書くかは未確定**。
- **index の基準が関数で異なる**: `selectPattern` は Python 側 index から 1 を引いて内部 index にする (0xd662db)。`jumpToPattern`・`movePattern` は加工せず渡す。内部表の基準は未確定。
- 受入条件 (実機意味論 = 戻り値・副作用・引数範囲の確定) は**未達**。確定したのは「呼び出し形・戻り値の写像・callback の分岐」まで。残りは子 issue へ分割 (下表)。

## 測定

- 測定 commit: `853874e67` (origin/main 起点・worktree `ws-3522`・branch `3522-py208-pattern-select-semantics`)。コード変更 0 件 (追加は本 REPORT と `docs/DOC_MAP.md` の 1 行)。
- コード差分 (測定 commit から HEAD まで、コード範囲): `git diff 853874e67 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (PR 作成直前に確認)。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (`oc_artifacts: fl-win64`)。展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C tools/python/work/py208 --wildcards '*block00031_PE.bin'` (実測 2.44 秒・`real 0m2.442s`)。展開先 `tools/python/work/py208/extracted/` は gitignore。
- 逆アセンブル: `python3 analysis/py41_disasm.py work/py208/extracted/block00031_PE.bin 0xd65a10 0xd65ba0 0xd66230 0xd66430 0xd66560 0xd66ec0 0xd659c0 0xd67690 0xd82c20` (実測・rc 0)。callback 群 (`0xd66e70 0xd66390 0xd66500 0xd660e0 0xd65b30`)・`0x12d8af0`・`0xd843d0` も同じ方式。
- 文字列・kwlist・RIP 相対の参照先は、capstone で関数先頭から `ret` まで走査して読んだ (一時スクリプトは `work/py208/`・未コミット)。
- 実行時の値 (グローバル変数の中身) は静的解析では得られない。以下の「P」「O」は構造だけを書く。

## 共通の呼び出し形

全 6 関数は同じ形 (`REPORT_PY46.md` と一致):

1. `0x415610` で引数解析の初期化 (中身は未読)。`0xd67690` は間接呼び出しで self の実体を返す (`rbx = [rax]`)。
2. 引数解析は**間接呼び出し** (`call [G]`) で行う。`jumpToPattern` は positional の `i`、`findFirstNextEmptyPat`・`selectPattern` は kwlist 付きの `i|ii`、`movePattern` は positional の `|i`。`selectAll`・`deselectAll` は引数なし。
3. 解析に失敗すると、解析関数の戻り値 (0 以下) をそのまま status として `0xd82c20` に渡す (`jle` 分岐。例: `0xd65a65`)。
4. 成功すると `0xd843d0(obj, &status, callback, 0, index, value, preview, 0,0,0,0,0, flag=1)` を呼ぶ。`0xd843d0` は `*out = -2` を書き、`0x526190` を呼んだ後に `rec+0x60` を `*out` へ複写する (`0xd844d7`〜`0xd844db`)。callback は `rec` (= `0xd843d0` の構造体) を rcx で受け取る。
5. `0xd82c20(int32(status))` で Python の戻り値に写像して終わる。

callback の共通形: `rec+0x60 = -2` (初期値) → P が真なら `rec+0x60 = 0` にして本体へ進む。P が偽なら `-2` のまま。P は `[[G]+8]->vtable[+0x98]` の呼び出しで、G は関数ごとに別のグローバル (下表)。

### 6 関数の表

| 関数 (entry) | 書式 (fmt) | kwlist | 既定値 | 内部 index (rec+0x18) | callback | 真の時の処理 |
|---|---|---|---|---|---|---|
| jumpToPattern (`0xd65a10`) | `i` | なし | 必須 | Python 値そのまま | `0xd659c0` (G=`0x87edb9`) | `0x12d8af0(index)` |
| movePattern (`0xd66ec0`) | `\|i` | なし | 1 | Python 値そのまま | `0xd66e70` (G=`0x87d909`) | `0xe33e20(index)` |
| findFirstNextEmptyPat (`0xd65ba0`) | `i\|ii` | flags, x, y | x=-1, y=-1 | flags (rec+0x18), x (rec+0x20), y (rec+0x28) | `0xd65b30` (G=`0x87ec45`) | `0x409c80(&flags, &byte, 1)` の戻り値は未使用 → `0x12d8be0(byte, x, y)` |
| selectPattern (`0xd66230`) | `i\|ii` | index, value, preview | value=-1, preview=0 | **Python 値 − 1** (`0xd662db`) | `0xd660e0` (G=`0x87e699`) | 下の「selectPattern の分岐」 |
| selectAll (`0xd66430`) | なし | なし | — | 0 (未使用) | `0xd66390` (G=`0x87e3e8`) | 0..count−1 の各 i で `0xea6e50(O, i, r8=0)` |
| deselectAll (`0xd66560`) | なし | なし | — | 0 (未使用) | `0xd66500` (G=`0x87e279`) | O≠0 のとき `0xea6a00(O, dl=1)` |

- `O` は `[G']→[0]→[+0xd34]` (選択 setter と preview の対象)。count は `[O+0x6c8]→[+0x10]` (int32)。`selectAll`・`selectPattern` は count を使う。`jumpToPattern`・`movePattern`・`findFirstNextEmptyPat` は O を使わない。
- `selectPattern` の O は `[0x87d4a7]→[0]→[+0xd34]`。`selectAll` の O は `[0x87d1fa]→[0]→[+0xd34]`。`deselectAll` の O は `[0x87d08b]→[0]→[+0xd34]`。

### selectPattern の分岐 (`0xd660e0`)

1. P が真 → `rec+0x60 = 0`。O が null なら status 0 のまま終了 (None)。
2. 内部 index (= Python 値 − 1) が `< 0` または `> count−1` なら**何もせず status 0 で終了 (None)**。範囲外は例外にならない。
3. value が −1 (既定) → `0xea7420(O, idx)` (選択済みか) を見て、選択済みなら value=0、未選択なら value=1 にする (トグル)。
4. value=0 → `0xea7280(O, idx)` (単独の選択解除) → 終了。
5. value=1 → `0xea6e50(O, idx, r8b=1)` (選択) → preview (rec+0x28) > 0 なら `0xea6730(O)` と `0xe4e7f0(O, idx)` → 終了。
6. value が −1・0・1 以外 → 何もせず status 0 (None)。

## status → 戻り値 (`0xd82c20`・実測)

| status | 戻り値 | 例外文言 (C 文字列の実値) |
|---|---|---|
| 0 | `[0x860485]()` が非 0 なら NULL (例外は設定済みとみなす)。0 なら None | — |
| 1 以上 | None (`0xc38bc0`) | — |
| −1 | NULL (条件付き) | `Unspecified error` |
| −2 | NULL (条件付き) | `Operation unsafe at current time` |
| −3 | NULL (条件付き) | `Range error` |
| −4 | NULL (条件付き) | `Index out of range` |
| −5 | NULL (条件付き) | `Wrong number of function parameters or wrong parameter type` |
| −6 | NULL (条件付き) | `Linked device not assigned` |
| −7 | NULL (条件付き) | `Device not assigned` |
| −8 | NULL (条件付き) | `Plugin not valid` |
| −9 以下 | NULL (条件付き) | `Unknown error` |

- 「条件付き」は、グローバル `[0x861b1f]→[0]→[+8]` の vtable `[+0x88]` が偽なら例外を出さず None を返すこと (`0xd82c6a`〜`0xd82c86`・`0xd82dd0`)。真なら `PyErr_SetString` 相当 (`[0x861bf2]`) で文言を設定して NULL。型は `[0x85e38a]→[0]→[0]` (型の名前は未同定)。
- `0xd82cf2` の `OK` は `0xd82cee` (status −3〜−1 の分岐の fall-through) にあるが、status < 0 では到達しない (未使用と判断)。
- 負の status は、解析関数 (0x415610 系) の戻り値が直接入る場合もある (解析失敗時)。その場合の文言対応は解析関数の戻り値の意味に依存し、未確定。

## 未確定 (子 issue に移す)

1. **P の本体**: 6 個の別グローバルから `[+0x98]` を呼ぶ。`-2` の文言が "Operation unsafe at current time" なので安全性判定と推定できるが、本体・G の同一性は未読。
2. **選択 setter の本体**: `0xea6e50` (r8b の意味。selectAll は 0、selectPattern は 1 で呼ぶ)・`0xea6a00` (dl=1)・`0xea7280`・`0xea7420` (真偽の返し方)・`0xea6730`・`0xe4e7f0` (preview)。
3. **移動・ジャンプ・探索の本体**: `0xe33e20`・`0x12d8af0` (vtable `+0x1f0` の仮想呼び出し、表 `0x6671b8` の stride 24 バイト参照、`0x11e84a0`・`0x12ddaa0`・`0x1046710`・`0xbd68e0(0x14,0)`・`0xe55c80`)・`0x12d8be0`・`0x409c80`。範囲検査の有無は未確認 (`0x12d8af0` は `cmp`・`jl` で表を読むが上限の検査は見えない)。
4. **index の基準**: `selectPattern` だけ Python 値 − 1。他は加工しない。内部表の 0 始まり/1 始まりは未確定。
5. **`[0x860485]`・`[0x861b1f]+0x88` の正体**: status 0 の扱いと例外の出し分けを決める。未読。
6. **同期性**: `0xd843d0` が `0x526190` の内部で callback を同期に呼ぶことは、`REPORT_PY46.md` の `0xd84297` (`call [rbx+0x58]`) の所見と整合するが、呼び出し経路を最後まで追っていない。

## 分割先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 選択系 3 関数の P・選択 setter 本体・preview 本体 (未確定 1・2・4 の選択部分) | #3522 の受入条件 (副作用・引数範囲) | 子 issue (PY-210) |
| 移動・ジャンプ・探索 3 関数の本体・範囲検査・index 基準 (未確定 3・4 の残り) | #3522 の受入条件 (副作用・範囲外) | 子 issue (PY-211) |
| 状態判定 `[0x860485]`・`[0x861b1f]+0x88` と同期性 (未確定 5・6) | status 0 と例外の出し分け | 子 issue の本文に明記 |
