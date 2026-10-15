# tools/python REPORT: PY-170 screen テキスト行・表示系 6 件の PE 根拠 (#3999, 親 #3021)

> 前段: `tools/python/REPORT_PY121.md` (呼出し鎖・`0xd82c20` の code 別分岐・`0xd843d0` の述語・`0x15e4280` の変換)・`REPORT_PY121_2985.md` (screen の 5 関数)。
> 既知類型との関係: 該当なし (lift ではなく PE の直接逆アセンブル。docs/DEFECTS.md の類型は対象外)。

## 結論

- 6 件の entry・fn VA・書式 (flapi 表と一致)・引数の割当て・呼出し先は PE (`block00031_PE.bin`) から確定した。
- **確定したのは「戻り値の式」の形まで**。値の意味 (戻り値が何を返すか・範囲 code の意味) は 6 件とも未確定。
  - `removeTextLine`・`addTextLine` の戻り値は、削除・追加の結果ではなく **解析の戻り値 (`ebx`) を `0xd82c20` に渡した結果**。
  - `findTextLine` の戻り値は `0xd7dc70` の戻り値の変換で、`0xd7dc70` の意味が要る。
  - `displayText`・`displayTimedText`・`animateText` の戻り値は `0xd843d0` の out の下位 32bit を `0xd82c20` に渡した結果。`0xd843d0` が out を書く箇所は REPORT_PY121 で未確認のまま。
- **mock/C は変更しない** (実装数の変化 0)。未確定の値を mock/C に書くと silent miscompile になるため。C provider・mock の実装は後続の子 issue に移す (§6)。

## 1. PE 根拠 (VA)

| 関数 | entry | fn (VA) | flags | 書式 (kwlist) | 解析の戻り値 | 戻り値の式 (VA) | 未確定 |
|---|---|---|---|---|---|---|---|
| `addTextLine` | 0x151e5f8 | 0xd7abb0 | 1 | `siiii` | `ebx` (0xd7ac2c) | `0xd82c20(ebx)` (0xd7acb4〜0xd7acb6) | `0xd7d460` の戻り値 (成否・行 id の意味) |
| `removeTextLine` | 0x151e618 | 0xd7ad00 | 1 | `i\|i` | `ebx` (0xd7ad5b) | `0xd82c20(ebx)` (0xd7ad87〜0xd7ad89) | 削除の成否を戻り値に含むか |
| `findTextLine` | 0x151e718 | 0xd7b2d0 | 1 | `iiii` | `rax` (0xd7b34d) | `[0x15e4280](0xd7dc70(...))` (0xd7b3ad〜0xd7b3b4) | `0xd7dc70` の戻り値の意味 |
| `displayText` | 0x151e758 | 0xd7ba80 | 1 | `iiisi\|i` | — | `0xd82c20(low32(out))` (0xd7bb91〜0xd7bb9a) | `0xd843d0` の out の写し方 (REPORT_PY121 未確認 1) |
| `displayTimedText` | 0x151e7b8 | 0xd7c290 | 1 | `s\|i` | — | `0xd82c20(low32(out))` (0xd7c38c〜0xd7c395) | 同上 |
| `animateText` | 0x151e7d8 | 0xd7c460 | 1 | `i` | — | `0xd82c20(low32(out))` (0xd7c53c〜0xd7c53e) | 同上 |

- 書式の文字列は `str@` で読んだ (addTextLine: 0xd7acf8 `siiii`、removeTextLine: 0xd7ad98 `i|i`、findTextLine: 0xd7b410 `iiii`、displayText: 0xd7bc00 `iiisi|i`、displayTimedText: 0xd7c400 `s|i`、animateText: 0xd7c594 `i`)。flapi 表の kwsig と一致。
- 全 6 件とも入口で `call 0xd7eca0` → `[rax]` を取る。`REPORT_PY121` の「`call 0xd7eca0` → `[rax]` → `+0x50` → `+0x3f8` が screen 状態」の読み方に従う (`0xd7eca0` は `[rip+0x86190d]` の関数ポインタを呼ぶ薄い wrapper。6 件とも同じ)。
- 解析は `PyArg` 相当の関数ポインタ (`call qword ptr [rax]`) で行う。成否は符号付きの戻り値 (`jle` で ≤0 を失敗扱い) で判定。**この関数の名前・戻り値の意味は未同定**。

## 2. 各関数の引数の割当て (確定した読み方)

### addTextLine (0xd7abb0)
- out: `r8=&[rbp+0x80]` (s)、`r9=&[rbp+0x9c]`、スタック `&[rbp+0x98]`・`&[rbp+0x94]`・`&[rbp+0x90]`・`&[rbp+0x8c]`。
- **食い違い (未解決 1)**: 書式 `siiii` は 5 項目 (s + i×4) だが、out は 6 個 (r8・r9 + スタック 4)。6 番目 `[rbp+0x8c]` は次の呼出し (0xd7ac88) で `r9` (5 番目の引数) に使われる。書式と out の数の対応は解析関数の仕様が要る。
- 成功時 (`ebx > 0`) のみ: `0x41c6e0(&[rbp+0x78], s)` で s を文字列オブジェクトへ写す (s が空でないとき)。次に `0x4f2990` で `[rbp+0x60]` に 4 int (`[0x9c]`・`[0x98]`・`[0x94]`・`[0x90]`) を詰める。`0xd7d460(obj=scr, 文字列, &[rbp+0x60], [0x8c], -1, -1, 0, 0)` を呼ぶ (0xd7ac7d〜0xd7acaf。`scr` = `[[rsi+0x50]+0x3f8]`、`mov rcx, rsi` で渡る)。`scr == 0` なら呼ばない (0xd7ac54 の `je`)。
- 戻り値: `0xd82c20(ebx)`。`ebx` は解析の戻り値 (成功時は正、失敗時は ≤0)。`0xd7d460` の戻り値は使われない。

### removeTextLine (0xd7ad00)
- out: `r8=&[rbp+0x4c]` (index)、`r9=&[rbp+0x48]` (flag、事前に 1)。スタック 4 つは NULL (`i|i` の 2 項目分のみ使用)。
- 成功時 (`ebx > 0`) で `obj = [rsi+0x50]+0x3f8 != 0` のとき: `0xd7de70(obj, index, flag == 1)` を呼ぶ (0xd7ad7c〜0xd7ad82)。`0xd7de70` は `[obj+0x1c4]` の配列長 (`[rax-8]`) を見る行の削除で、末尾側の境界判定あり (0xd7de8c〜0xd7ded3)。**削除の成否の戻り値は無い** (0xd7de70 の戻り値は使われない)。
- 戻り値: `0xd82c20(ebx)` (0xd7ad87〜0xd7ad89)。`ebx` は解析の戻り値。

### findTextLine (0xd7b2d0)
- out: `r8=&[rbp+0xdc]`・`r9=&[rbp+0xd8]`・スタック `&[rbp+0xd4]`・`&[rbp+0xd0]`・NULL・NULL。`iiii` の 4 int を `[0xdc]`・`[0xd8]`・`[0xd4]`・`[0xd0]` に受ける。
- 成功時 (`rax > 0`) かつ `obj = [rbx+0x50]+0x3f8 != 0`: `0x4f2990` で `[rbp+0x64]` に 4 int を詰める (0xd7b377)。`0xd7dc70(obj, &[rbp+0x64], 0x415c30 の戻り値)` を呼ぶ (0xd7b39c〜0xd7b3a6)。
- 戻り値: `[0x15e4280](ecx = 0xd7dc70 の戻り値)` (0xd7b3ad〜0xd7b3b6)。`0x15e4280` は変換スロット (`0xd7b3b3 + 0x868ecc = 0x15e4280`、REPORT_PY121 の既知点と一致)。
- 失敗時 (`rax ≤ 0`): `0xd82c20(eax)` (0xd7b3c0〜0xd7b3c2)。`obj == 0` の経路は `rax = -1` (0xd7b3bc)。

### displayText (0xd7ba80)
- 書式 `iiisi|i`。out は `[0xbc]`・`[0xb8]`・`[0xb4]`・`[0xac]` (int)・`[0xa0]` (s)・`[0xb0]`。
- 成功時: `0x41c6e0(&[rbp+0x78], s)` で s を写し、`0xd843d0(eng, &[rbp+0x88], callback=0xd7b820 (0xd7bb3a の lea r8,[rip-0x321]), userdata=[rbp+0x78], 5 番目以降 = [0xbc]・[0xb8]・[0xb4]・[0xac]・0・0・sync=1)` を呼ぶ (0xd7bb2b〜0xd7bb8c)。
- 戻り値: `0xd82c20(low32([rbp+0x88]))` (0xd7bb91〜0xd7bb9a)。`[rbp+0x88]` は `0xd843d0` の out で、`-2` で初期化される (REPORT_PY121 の §dispatch)。

### displayTimedText (0xd7c290)
- 書式 `s|i`。`[0xac]` は事前に 1 (既定値)。`[0xa0]` = s。
- 成功時: `0xd843d0(eng, &[rbp+0x88], callback=0xd7c010 (0xd7c33e の lea r8,[rip-0x335]), userdata=[rbp+0x78], 5 番目 = [0xac]・以降 0・sync=1)` (0xd7c334〜0xd7c387)。
- 戻り値: `0xd82c20(low32([rbp+0x88]))` (0xd7c38c〜0xd7c395)。

### animateText (0xd7c460)
- 書式 `i`。out `[0x9c]` = int (初期値は未設定。解析が成功した時だけ使う)。
- 成功時: `0xd843d0(eng, &[rbp+0x80], callback=0xd7c410 (0xd7c4e8 の lea r8,[rip-0xdf]), userdata=0, 5 番目 = [0x9c]・以降 0・sync=1)` (0xd7c4de〜0xd7c530)。
- 戻り値: `0xd82c20(low32([rbp+0x80]))` (0xd7c53c〜0xd7c53e)。

## 3. 範囲 code (`0xd82c20` の分岐) の読み方

REPORT_PY121 の `0xd82c20` の分岐 (a)(b)(c) をそのまま使う。6 件の戻り値は全て `0xd82c20(code)` を経由する。

- `code ≥ 0`: `0xc38bc0` → `[0x16b82e0]` を返す (REPORT_PY173 と同じ読み。None と推定、確定はしない)。
- `code < 0`: `this` の `vtbl[+0x88]()` が真なら code 別のメッセージを設定して 0 を返す。偽なら `0xc38bc0`。
- **このため 6 件の「成功時の戻り値」は全て `[0x16b82e0]` (推定 None) になり、値を持たない**。`findTextLine` だけは `0xd7dc70` の戻り値を変換して返す。

code (= 解析の戻り値・`0xd843d0` の out) が 0 / 負のどの値を取るかは、解析関数と dispatch の仕様が要る。

## 4. 未確定の一覧 (保留の記録)

| # | 関数 | 未確定の内容 | 確定に必要な情報 |
|---|---|---|---|
| 1 | displayText・displayTimedText・animateText | `0xd843d0` の out の写し方 (`task[+0x60]` → `*out`)・述語偽 (`-2`) の Python 側の挙動 | REPORT_PY121 未確認 1 と同じ (PY-125 #3001 の範囲) |
| 2 | addTextLine | 6 out と書式 `siiii` (5 項目) の対応・`0xd7d460` の戻り値 (行 id の意味か) | `0xd7d460` の本体と `0x412f30`・`0x413480` の同定 |
| 3 | removeTextLine | 削除の成否の戻り値への反映 (`0xd7de70` の戻り値は未使用) | `0xd7de70` の戻り値と、`[obj+0x1c4]` 配列の要素型 |
| 4 | findTextLine | `0xd7dc70` の戻り値の意味・`0x415c30` の役割 | `0xd7dc70` の本体 |
| 5 | 6 件共通 | 解析関数 (`[rax]` の関数ポインタ) の名前と、戻り値 (0・負) の意味 | 関数ポインタの同定 (`0x86722e` 等 RIP 相対の先) |
| 6 | 6 件共通 | `obj == 0` (screen 未初期化) の経路の振る舞い | REPORT_PY121_2985 の未確定 1 (`scr == 0` 経路) |

## 5. 手段

- 展開: `mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'` (2.9 秒)。
- probe: `cd tools/python && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_handler_probe.py addTextLine removeTextLine findTextLine displayText displayTimedText animateText`。entry・fn・flags は issue 本文の表と一致。
- 逆アセンブル: `cd tools/python && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_disasm.py <VA> <命令数>`。本文の VA は全て、このコマンドで読んだもの。
- RIP 相対の先は手計算 (次命令のアドレス + disp32)。検算: `0xd7b3b4 + 0x868ecc = 0x15e4280`、`0xc38bc7 + 0xa7f719 = 0x16b82e0`、callback `0xd7bb41 - 0x321 = 0xd7b820`・`0xd7c345 - 0x335 = 0xd7c010`・`0xd7c4ef - 0xdf = 0xd7c410`。

## 6. 検証・範囲

- コード変更なし (RE の記述のみ)。`tools/python` 以外は触らない。
- 測定の基点は main `32e6f8b4`。`git diff 32e6f8b4 HEAD -- tools/python ':!*.md'` の出力は空 (コード差分 0)。
- e2e (`general_diff.mjs` 等) はコードを変えていないため対象外。件数 (実装 / 未実装) は変えていない。
- 受入条件 (6 件の戻り値・範囲 code・引数の意味の根拠 VA 付き記録、確定できないものは理由を記録) は本 REPORT で満たす。値そのものは §4 の未確定として保留。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 6 件の戻り値の値・範囲 code の意味 (§4 の 1〜6) | 6 件とも mock/C 実装ができない | 後続の子 issue (起票先は PR 本文の表を正とする) |
