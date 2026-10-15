# PY-174 REPORT (#4009): patterns 単体属性 3 関数の PE 解析・索引基準

親: #3221 (PY-174) / #1804 (PY-48)。兄弟: `REPORT_PY173.md` (数え・選択系 4 関数)・`REPORT_PY179.md` (実装仮置き)。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift 作業ではない)。
検証対象: fl-win64 の `block00031_PE.bin` (22,227,016 B・ImageBase 0x400000)。解析は `analysis/flapi/pe_pattern_attr_probe.py`。

## 1. 結論

- **引数の型・個数・順序: 達成。** getPatternLength は `"i"`、getChannelLoopStyle は `"ii"`、getBlockSetStatus は `"iiii"` (`flapi_table.json` の sig と一致)。
- **戻り値の型: 推定 (int)。** 3 関数とも変換スロット `0x15e4280` (PY-173 と同じ) を通す。PE からは int と bool を区別できない。
- **索引基準: 3 関数で扱いが異なる (下表)。** getPatternLength の索引は 0 始まり (0..999。PY-173 の patternCount・isPatternDefault の 1..999 とは別)。getBlockSetStatus は行 (y) の下限を 1 に丸める (行 0 は読まない)・列 (x) の下限を 0 に丸める。getChannelLoopStyle の第 1 引数は検査なしの直接添字。「1 始まり / 0 始まり」の名称は、丸めの下限からの推定を含む。
- **戻り値の値の意味: 未達。** getPatternLength の除数は実行時に書き換わるグローバル、getChannelLoopStyle の表の中身は実行時の状態、getBlockSetStatus の戻り値 (0..2) の意味は未確定。推測実装はしない (§4)。
- C provider・mock は変更しない (実装は子 #4010)。

## 2. 関数ごとの事実 (根拠: ハンドラ VA)

| 関数 | ハンドラ | 引数 (PyArg) | 索引・範囲 | 戻り値 (型は推定) |
|---|---|---|---|---|
| getPatternLength | `0xd657e0` | `"i"` → `[rbp+0x2c]` | 0..999 (`test`/`jl`・`cmp 0x3e7`/`jg`。外れると `-4` を `0xd82c20` へ渡す = "Index out of range") | int。下の式 |
| getChannelLoopStyle | `0xd65d00` | `"ii"` → 第 1 `[rbp+0x2c]`・第 2 `[rbp+0x28]` | 第 1 は検査なし (`0x12d0750` の表添字)。第 2 は検査なし (key) | int。`0x12d0750(第1, 第2)` の結果 |
| getBlockSetStatus | `0xd658a0` | `"iiii"` → 第 1 `[rbp+0x4c]`・第 2 `[rbp+0x48]`・第 3 `[rbp+0x44]`・第 4 `[rbp+0x40]` | 下の §3 | int (0..2)。`0x12d8740` の結果 |

### getPatternLength の式
- 要素 `elem = [0x15e2aa0] + idx*0xc0` (`lea rdx,[rax+rax*2]` と `[rcx+rdx*8]` で 192 B 刻み。`[0x15e2aa0]` = `0x193fce0`・`.bss`・静的には 0)。
- `elem.+0x44 > 0` のとき: `elem.+0x44 / *[0x15e25f8]` (`[0x15e25f8]` は `0x15d89c4` へのポインタ。除数 `*0x15d89c4` は実行時に書かれる値。下 §4)。
- それ以外: `0x12d09e0(elem)` = `((elem.+0x50) + V - 1) / V * 4`。`V = *[0x15e27f0]` (`0x15d89c8`・静的 96・実行時は `*0x15d89c4 * 4`)、`*0x15e1c70` = `0x15d898c` = 4。
- 除数が 0 の場合のガードは無い (`idiv` が trap する)。

### getChannelLoopStyle の式 (`0x12d0750(a, b)`)
- 表の基底 `0x193fd08` (`.bss`)。要素は 192 B 刻みで、`obj = [基底 + a*0xc0]` が非 null のとき、`[obj+0x54] != 0` かつ `[obj+0x58]` のリスト (件数は `[リスト-8]`) を先頭から走査する。要素は 5 dword (key = +0, value = +4) で、`key == b` の最初の value を返す。見つからなければ 0。
- `a` の上限・下限とも `0x12d0750` では検査していない (呼出し元 `0xd65d00` も検査しない)。

## 3. getBlockSetStatus の式 (`0x4f2990` → `0x12d8740`)
- `0x4f2990` は構造体 `S = {x=第1, y=第2, z=第3, w=第4}` を作る (dword 4 つ)。
- `0x12d8740(&S)`:
  - 行 (top..bottom): `top = max(S.y, 1)`・`bottom = min(S.w, 500)`。行の基底は `0x12e1a20()` (表から選んだポインタ) `+ j*0x114 + 0x24`。
  - 列 (left..right): `left = max(S.x, 0)`・`right = S.z` (上限の検査は無し)。
  - セルの値 `0x100bfa0(行, i)` = `[0x15453b4 + flag*4]`。`flag` は 0..7 (セル非 null・`+0xd2`・`+0xda` の一致の組み合わせ)。表は `{0, 1, 2, 2, 2, 2, 2, 2}` (`.data`・ファイルから読んだ値)。
  - 戻り値 = 全セルの最大値 (`max`)。`flag` の値域から 0..2 に限られる (実行時の状態によらない)。
- `S` の対応は `S.x = 第1 (左), S.y = 第2 (上), S.z = 第3 (右), S.w = 第4 (下)` (`0x4f2990` の store 順と `0x12d8740` の読み出し offset から)。名前 (left/top/right/bottom) は読み出しの対応からの推定。
- 戻り値は全セルの最大値 (内側ループは値 2 で打ち切るが、最大値は変わらない)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| getPatternLength の除数 `*0x15d89c4` は `.text` 内の書込み `0x13111e5` (関数 `0x13111b0`: `0x1311050(...) >> 2` を格納) で決まる。`0x13111b0` の呼出し元は直接 `call` では見つからず、呼ばれる経路は未確定 | 値の式を静的に決められない。除数 0 のトラップの扱いも未確定 | #4010 (実装の入力として引き継ぐ。PM 判断) |
| 既定値経路の `V = *0x15d89c8` (= `4 * 除数`) と `elem.+0x50` の意味 | 既定値の式の意味が未確定 | #4010 |
| getChannelLoopStyle の第 1 引数の上限と意味 (channel か loop 表の添字か) | 範囲検査を入れる位置・エラー code が決まらない | #4010 |
| 表 `0x193fd08` の内容 (実行時に作られる) と第 2 引数 key の意味 | 戻り値の値が決まらない | #4010 |
| getBlockSetStatus の戻り値 0..2 の意味・第 1〜第 4 引数の名前 (left/top/right/bottom は推定) | 値の対応を決められない | #4010 |
| 戻り値の型 (int と bool の区別) | PE から区別できない (PY-173 と同じ) | 未確定のまま。`REPORT_PY120.md` の項 |

## 5. 再現
- 展開: 素材 `fl-win64` (`oc_artifacts` の名前) を `tar --zstd -xf <素材>.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'` (`FL_WIN64_DIR=<展開先>`)
- 注釈付き逆アセンブル: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_pattern_attr_probe.py d657e0 d65d00 d658a0 4f2990 12d0750 12d8740`
- 書込み先の検索 (`.text` の rip 相対 mov): `... pe_pattern_attr_probe.py --writers` (実測 34 秒)
