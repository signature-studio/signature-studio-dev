# PY-173 REPORT (#3220): patterns 数え・選択系 4 関数の索引基準・型・戻り値式

親: #1804 (PY-48)。前段: `REPORT_PY42.md` (未確定 11 関数の一覧)・`REPORT_PY100.md` (patternNumber の slot)。既知類型との関係: 該当なし (逆アセンブルの読解のみ・lift 作業ではない)。

## 1. 結論

- **受入 2 (索引基準を関数ごとに確定): 達成。** patternCount と isPatternDefault は 1 始まり (1..999)。isPatternSelected は入力 i を `i-1` (0 始まり) にして選択リストと照合し、範囲検査は無い。patternNumber は索引を取らない。
- **受入 1 の一部: 型・引数の検査は確定。** 戻り値の型は patternCount `int`・patternNumber `int`・isPatternDefault `bool`・isPatternSelected `bool`。引数の検査は isPatternDefault の `1..999` だけ (範囲外はエラー経路)。戻り値の**値**は述語 `0x12d8d30` の 192 バイト構造体の意味に依存し、未確定 (§5・子 #3271 (PY-179))。
- 述語 `0x12d8d30` の論理式は逆アセンブルから完全に読めた (§3)。構造体の各フィールドの意味は未確定。
- C provider (`provider/fl_engine.c`)・mock (`host/fl_mock.mjs`) は変更しない。値の意味が未確定のため、推測実装はしない (受入 3・4・5 は子 #3271 (PY-179) へ移す)。

## 2. 関数ごとの事実 (根拠: ハンドラ VA)

| 関数 | 書式 | 索引・引数の検査 | 戻り値の式 (型) | 根拠 |
|---|---|---|---|---|
| patternCount | `()` | 検査なし。`esi = 1` から `esi < 0x3e8` まで 1 ずつ増やす (i = 1..999) | `ebx` = #{ i : `pred(i,1,0,0)` が偽 } (int) | `0xd64d40`・`0xd64d5e` `jne`・`0xd64d6c` `jne` |
| patternNumber | `()` | 索引なし | `*(int*)0x15e4018` (int) | `0xd64d20`・`0xd64d2b`。slot は `REPORT_PY100.md` と一致 |
| isPatternDefault | `"i"` | `1 <= i <= 999` (`cmp rax,1`・`cmp rax,0x3e7`)。外れると `-4` を `0xd82c20` へ渡すエラー経路 | `pred(i,1,1,1)` (bool) | `0xd66060`・`0xd66091`・`0xd660a3`・`0xd660b7` |
| isPatternSelected | `"i"` | 検査なし。`edx = i-1` を `0xea7420` へ渡す | `0xea7420(G, i-1)` (bool)。`G` が null なら false | `0xd65ff0`・`0xd66033`・`0xd6602b` |

- 書式の `"i"` は `0xd660d8`・`0xd66054` の文字列 (`i\0`) で確認 (`pe_pattern_probe.py` の出力とは別に読んだ)。
- `G` = `[[ [0x15e35c8] ] + 0xd34]` (`0xd66017`〜`0xd66028` の読み。`0x15e35c8` は `mov rcx,[rip+0x87d5aa]` の RIP 相対先)。
- 0x15e35c8 の内容 (ポインタ) と `+0xd34` の意味は未確定 (§5)。
- 索引の基準の根拠: 述語 `0x12d8d30` は `ecx` をそのまま配列添字に使い (`0x193fce0 + ecx*0xc0`)、patternCount・isPatternDefault は 1..999 を渡す。添字 0 は使われない。isPatternSelected は `i-1` を選択リストの値 (0 始まり) と比べる。

## 3. 述語 `0x12d8d30(i, dl, r8b, r9b)` の論理式

エントリ `E = 0x193fce0 + i*0xc0` (`0x12d8d37`〜`0x12d8d42`: `shl 3` → `lea *3` → `lea *8`)。`pred` は次の式と一致する (`0x12d8d48`〜`0x12d8daf` を 1 命令ずつ追って得た):

```
X    = (P1 != null ∧ dword[P1+0x14] > 0) ∨ (P2 != null ∧ dword[P2+0x14] > 0)    P1 = [E+0x20], P2 = [E+0x28]
pred = ¬X ∧ byte[E+0x84] != 0 ∧ (¬dl ∨ qword[E] == null) ∧ (¬r8b ∨ byte[E+0x14] == 0) ∧ (¬r9b ∨ dword[E+0x10] == -1)
```

- 各分岐の VA: X の 1 項目 `0x12d8d48`〜`0x12d8d61`・2 項目 `0x12d8d63`〜`0x12d8d7c`・`0x12d8d80` (X なら偽)・`0x12d8d82` (`[E+0x84]`)・`0x12d8d8b`〜`0x12d8d93` (dl)・`0x12d8d95`〜`0x12d8d9e` (r8b)・`0x12d8da0`〜`0x12d8da9` (r9b)。
- 呼出し側の組み合わせ: patternCount は `(1,0,0)`、isPatternDefault は `(1,1,1)` (`dl`・`r8b`・`r9b` の順)。
- 検査スクリプトが拾ったフィールド (`[rcx+disp]`): `+0x14` byte・`+0x84` byte・`+0x10` dword・`+0x20` qword・`+0x28` qword。`[E+0x00]` (disp 0) は正規表現の外で、式は逆アセンブルの `cmp qword ptr [rcx], 0` から読んだ。

**式の帰結 (上の論理式からの導出。実値は未確定):**

- patternCount = #{ i ∈ 1..999 : ¬pred(i,1,0,0) } (`pred(i,1,0,0) = ¬X ∧ [E+0x84]≠0 ∧ [E]==null`)。
- isPatternDefault(i) = pred(i,1,1,1) (1..999 のみ)。

## 4. 選択リスト (isPatternSelected の `0xea7420`)

`0xea7420(G, k)` (`0xea7420`〜`0xea746e`): `A = [G+0x6ac]`・`n = [A-8]` (MSVC 形式の件数)。`r = 0..n-1` について `dword[A + 12*r] == k` なら true。見つからないか `A` が null (`n = 0`) なら false。

- したがって isPatternSelected(i) = 「`i-1` を先頭 dword に持つレコードが `G+0x6ac` のリストにある」。
- レコードの先頭 dword が 0 始まりの索引である点は、比較式 (`cmp dword ptr [r9 + r11*4], edx`・`lea r11,[r11+r11*2]`) から読んだ。レコードの残りの意味は未確定。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 述語の構造体 (`E` の 192 バイト) の各フィールドの意味 (`[E+0x00]` ptr・`+0x10` dword・`+0x14` byte・`+0x20`/`+0x28` ptr・`+0x84` byte) と、`P1`・`P2` の指す構造体の意味 | patternCount・isPatternDefault の戻り値の値 | 子 #3271 (PY-179) |
| 選択リスト `G+0x6ac` の書込み元と内容 (レコード 12 バイト・残りのフィールド) | isPatternSelected の値。リストが常に空なら常に false | 子 #3271 (PY-179) |
| `G` = `[[ [0x15e35c8] ]+0xd34]` の意味・初期化 | isPatternSelected の `G` が null かどうか | 子 #3271 (PY-179) |
| patternNumber の slot `0x15e4018` の初期値と 0/1 始まり | patternNumber の値 | 子 #3271 (PY-179) |
| isPatternDefault の範囲外で渡す `-4` (`0xd82c20`) と C 側の `FL_E_RANGE = 4` (`provider/fl_api.h`) の対応 | 範囲外のエラーコードの値 | 子 #3271 (PY-179) |
| C provider・mock の実装、`tests/provider_check.mjs` の数、`all_tools.mjs` 48/48、mock と C の差分検査 | 受入 3・4・5 | 子 #3271 (PY-179) |

## 6. 検証

測定 commit: `5575dd39` (`feat(python): add pattern probe for PY-173 (#3220)`。コードを変えた最後の commit)。以後の commit はこの REPORT と DOC_MAP の文言だけを変える。`git diff 5575dd39 HEAD -- tools/python/analysis` の出力は 0 行。

| コマンド | 結果 | wall |
|---|---|---|
| `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'` | rc 0・`extracted/block00031_PE.bin` を展開 | 1.660 秒 (user 1.497 秒・sys 1.844 秒) |
| `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_pattern_probe.py` (`5575dd39`) | rc 0・5 件 OK (patternCount・patternNumber・isPatternDefault・isPatternSelected・`0xea7420`)・述語のフィールド 5 件 | 0.059 秒 (user 0.043 秒・sys 0.016 秒・load 0.12) |
| 同 `--negctl` (patternCount の走査上限を `0x3e7` に壊す) | rc 1・`patternCount: NG missing=['cmp esi, 0x3e7']` | 同程度 |

ネガティブコントロールは「期待命令を壊すと FAIL する」ことの確認。式そのものの誤りは検出しない (式は手で導出した。範囲外)。

## 7. 再現

```
FL_WIN64_DIR=<fl-win64 展開先> python3 analysis/flapi/pe_pattern_probe.py          # rc 0
FL_WIN64_DIR=<fl-win64 展開先> python3 analysis/flapi/pe_pattern_probe.py --negctl # rc 1
```

`<fl-win64 展開先>` は §6 の `tar` で得る (`extracted/block00031_PE.bin` が要る)。
