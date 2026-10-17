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

## 6. #6016 の追加解析 (未達の 3 件)

再現: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_xref.py 193fd08` (rip 相対の参照 49 件・store 0 件・約 62 秒)、`pe_xref.py` の `pe_e8_callers.py 12d0750` (直接 call 元 10 件)。

### 6-1. getChannelLoopStyle の第 1 引数 (`0x12d0750(a, b)` の a)
- 意味: **表 `0x193fd08` の行添字** (192 B 刻み)。`flapi_table.json` の sig は第 1 引数を `pattern: int` と名付けている。PE 上も `a` を検査なしで行に当てる (`0x12d0750` の `shl rcx,3`・`lea ...*3`。`0xd65d00` も検査しない)。
- 上限: **PE からは決まらない**。行の件数は表の実行時の大きさで、静的に持つ件数が無い (`0x193fd08` は `.bss`)。範囲外の `a` は表の外を読む。未確定。
- 第 2 引数 `b`: 行の list の 20 B 記録 (`rec+0` = key, `rec+4` = value) の key と比べる (`cmp dword [r11+rbx*4], edx`)。REPORT_PY101 の `0x12d3ff0` も同じ 20 B 記録の `rec+0 == cid` (channel index) で引く。したがって `b` は channel の key と読めるが、呼出し元の値の由来は**未確認**。

### 6-2. 表 `0x193fd08` の内容
- 静的には作られない: `.text` の rip 相対 store は 0 件 (`pe_xref.py`)。実行時に計算した先へ書かれる。
- 行 (192 B) の形: `+0x54` = byte フラグ (0 なら不一致扱い)、`+0x58` = list ポインタ (件数は `[list-8]`)。list の要素 = 20 B 記録。
- 直接 call 元は 10 件 (`pe_e8_callers.py 12d0750`: `0xd3482e`・`0xe487ab`・`0xe54cf8`・`0xe57ca8`・`0xfc9e4e`・`0xfcb8d7`・`0x102dd83`・`0x12cf572`・`0x12dd9c0`・`0xd65d31`)。うち `0xd65d31` が getChannelLoopStyle。**他の 9 件の引数の由来は未確認** (逆アセンブルの確認は未実施)。`0xe54cf8`・`0x12cf572` は `[rax+0xc48]` を第 2 引数 (`edx`) に入れており、行の値は実行時の状態のまま。

### 6-3. getBlockSetStatus の引数名と戻り値
- 引数の対応は確定 (`0xd658a0` の `PyArg` 格納先 → `0x4f2990` の store 順 → `0x12d8740` の読み出し):
  `S+0 = 第 1 (x)`・`S+4 = 第 2 (y)`・`S+8 = 第 3 (z)`・`S+0xc = 第 4 (w)`。
- 読み出しの丸め: `x` は `max(x,0)` (列の下限)、`y` は `max(y,1)` (行の下限)、`z` は検査なし (列の上限・右端)、`w` は `min(w,500)` (行の上限)。
- 名前: 丸めの方向と `(z-x+1)` の幅の取り方から **left = x, top = y, right = z, bottom = w** と整合する。ただし Python 側の引数名は REPORT_PY32 の文書由来で、PE から名前そのものは確定しない (推定のまま)。
- 戻り値 0..2 の意味: **未確認**。セル値は `0x100bfa0` の `[0x15453b4 + flag*4]` (表 `{0,1,2,2,2,2,2,2}`) の最大値。`flag` の意味 (`+0xd2`・`+0xda` の一致) が未確定のため、値の意味は決められない。

### 6-4. 受入条件の判定
| 受入 | 判定 | 残り |
|---|---|---|
| 第 1 引数の上限と意味 | 意味は行添字 (確定寄り・根拠 6-1)、上限は**未確定** (根拠 6-5) | 上限を持つ静的な件数が PE に無い。実行時の表の件数 (PE 外) |
| 表 `0x193fd08` の内容と第 2 引数 key | 作られ方 (実行時・rip store 0) を確定。key = channel は**推定** | 呼出し元の値の由来 (6-1 の b) |
| getBlockSetStatus の戻り値・引数名 | 引数の対応 (x,y,z,w) は確定。名前は推定のまま。戻り値 0..2 の意味は**未確認** | `flag` の意味 (`+0xd2`・`+0xda`) |

### 6-5. 行添字の上限の追加解析 (#6267)
- 素材: `fl-win64` の `block00031_PE.bin` (22,227,016 B・ImageBase 0x400000)。セクション: `.text` 0x401000、`.data` 0x13a5000、`.bss` 0x15e6000 (VirtualSize 0x388e9c = 終端 0x196ee9c)。
- 読み出し (`pe_xref.py 193fd00,193fd08,193fd10,193fd18,193fcf8,193fd20`・実測 64.3 秒): `0x193fd08` への rip 相対参照は 49 件、`.text` からの store は **0 件**。`0x12d0750` の読み出しは `[base + a*0xc0]` の非 null 判定だけで、`a` の大小は見ていない (`cmp qword ptr [r8 + r9*8], 0`・`je`)。
- 上限の候補を探した結果 (いずれも `0x193fd08` の添字には効かない):
  - `0x12d2790` の `cmp rax, 0x1f4` (`0x12d274c`) は `[rbx+0x70]` への検査で、`0x12d278c` の `[rbx+0x50]` を `0x193fd08` に当てる経路とは別の添字。
  - `0x193fc00..0x193fe00` への store は `0x193fc68`・`0x193fc6c`・`0x193fc88`・`0x193fca8`・`0x193fce8` の 5 アドレスのみで、件数を持つ変数は見つからない (`0x193fd08` の前後は別のグローバル)。
  - `.bss` 終端 `0x196ee9c` までは 192,916 B = 1004 行分。ただし `.bss` は表専用ではなく (`0x196ea20`〜の別グローバルを参照)、終端は件数の根拠にならない。
- 結論: **未確定**。静的な件数は PE に無い (表は `.bss` に実行時に作られる)。`a` の上限は実行時の表の件数で決まり、PE だけでは確定できない。範囲外の `a` は表の外を読む (6-1 と同じ)。
- 次の一手 (PE 外): 実行時に表 `0x193fd08` の作成直後の件数を観測する (`g1_runtime_5932.py` 系の方式)。本 issue の範囲外。

PE 解析は完了。以上 3 件は子 #4010 の入力として残す (実装は本 issue の範囲外)。
