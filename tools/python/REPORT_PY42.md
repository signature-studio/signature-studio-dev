# PY-42 (#1667): patterns 読み取り系 14 関数の実機意味論 (逆解析の途中結果)

親: #1345 (PY-35) / 元: #1336 (PY-32)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- 実機 (FL 26.1.7 `fl-win64`、`block00031_PE.bin`) の逆解析で、14 関数すべてについてハンドラの PyArg 書式と検査・戻り値の経路を読んだ (下表)。ただし戻り値・引数の**意味**まで確定したものは無い。patternMax (定数 999) など一部だけ、戻り値の値そのものは読めた。
- 意味論が未確定の関数は 11 件。残りは子 issue #1804 (`[PY-48]`) に移した。
- 逆解析で `tools/python/analysis/flapi/flapi_table.json` の署名と実機の PyArg 書式が**食い違う**関数を 3 件見つけた (getPatternGroupName・getPatternsInGroup・getChannelLoopStyle)。署名の正本を直す判断は別途必要。
- C provider (`provider/fl_engine.c`) と mock にはコード変更を入れていない。未確定の関数を推測実装すると「推測実装はしない」に反するため。

## 逆解析の方法

- 素材: `$HOME/artifacts/fl-win64.tar.zst` を `tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開 (6.6 秒)。
- 手段: `tools/python/analysis/flapi/pe_handler_probe.py` (PyMethodDef から関数ハンドラを引き、先頭を逆アセンブル) と `pe_disasm.py` (任意 VA)。
- 各ハンドラの PyArg 書式は RIP 相対の文字列を読んで得た (下表の「書式」)。

## 関数ごとの状態

| 関数 | 実機の書式 (PyArg) | 確定した事実 (根拠: ハンドラ VA) | 未確定 |
|---|---|---|---|
| patternMax | () | 定数 `999` (0x3e7) を整数で返す (0xd64d90) | なし |
| patternNumber | () | グローバル変数の `int` を整数で返す (0xd64d20) | グローバルの意味 |
| patternCount | () | i = 1..999 を走査し、`0x12d8d30(i,1,0,0)` が偽のものを数えて整数で返す (0xd64d40) | 述語 `0x12d8d30` の意味 |
| getActivePatternGroup | () | グローバル `int` を整数で返す (0xd66fe0) | グローバルの意味 |
| getPatternGroupCount | () | グローバル配列の要素数 (ポインタ直前の count) を返す。null なら 0 (0xd67000) | 配列の中身 |
| getPatternGroupName | **"i" (索引 1 つ)** | 索引が 0..count-1 の範囲外なら範囲外エラー、内なら配列要素の名前を文字列で返す (0xd67030) | 配列の意味。**署名 `() -> str` と不一致** |
| getPatternsInGroup | **"i" (索引 1 つ)** | 索引 -1 を許す (現在のグループの意味と思われる)。範囲内なら走査して整数列を返す (0xd67110) | 戻り値の組み立て。**署名 `() -> tuple` と不一致** |
| getChannelLoopStyle | **"ii" (2 つ)** | 2 整数を取り、関数 `0x12d0750` の結果を整数で返す (0xd65d00) | 引数の意味。**署名 `() -> int` と不一致** |
| getPatternColor | "i" | 索引 0..999 の範囲外は範囲外エラー。内なら 24 バイト要素の +8 (uint32) を取り、R と B を入れ替えて alpha `0xff` を立てた整数を返す (0xd65090) | 要素 24B の意味は pattern 構造体の推定 |
| getPatternName | "i" | 索引 0..999 の範囲外は範囲外エラー。内なら要素の名前を文字列で返す (0xd64db0) | 要素の名前フィールド |
| getPatternLength | "i" | 索引 0..999 の範囲外は範囲外エラー。要素の +0x44 が正なら `値 / (除数グローバル)`、そうでなければ既定値 `0x12d09e0` (0xd657e0) | 除数グローバルの意味・既定値の算出 |
| isPatternDefault | "i" | 索引の範囲を `cmp 1` と `cmp 0x3e7` で検査 (**下限が 1 で、他の索引関数の 0 と異なる**)。`0x12d8d30` を呼ぶ (0xd66060) | 述語の引数の組み方 |
| isPatternSelected | "i" | 索引を `index-1` に変換して `0xea7420` へ渡し、bool を返す。グローバル `[rcx+0xd34]` が null なら false (0xd65ff0) | 0 ベースへの変換の意味。`0xea7420` の中身 |
| getBlockSetStatus | "iiii" (4 整数) | 4 整数を PyArg で取り、`0x4f2990` で処理した後、`0x12d8740` の結果を間接呼出しで Python 値にして返す。PyArg 失敗時は `0x12d8740` を通らず `0xd82c20` 経由で戻る (0xd658a0) | 戻り値の意味・4 引数 (left/top/right/bottom) の意味 |

## 未解決の疑い (要確認)

- **索引の基準が統一されていない**: getPatternName・getPatternColor・getPatternLength は 0..999、isPatternDefault は 1..999 の検査、isPatternSelected は内部で `index-1`。「1 始まり」か「0 始まり」かは関数ごとに違う可能性がある。実機の呼出しで確かめるまで、どちらにも決められない。
- **署名の不一致**: getPatternGroupName・getPatternsInGroup・getChannelLoopStyle は、実機が引数を取る。`flapi_table.json` の `() -> ...` は誤りの疑い。`flapi_kwargs.json` 側の kwlist と突き合わせる必要がある。

## 測定

- 測定 commit: `7e665077` (origin/main 起点の worktree `ws-1667`)。本 PR はコード変更 0 件 (REPORT のみ)。
- コード差分の確認 (`git diff 7e665077 HEAD -- tools/python/provider tools/python/host tools/python/tests`) は 0 行。
- `provider_check.mjs` と `all_tools.mjs` は再測定していない (コード差分 0。`docs/WORKFLOW.md` §6)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未確定 11 関数 (patternCount・patternNumber・getActivePatternGroup・getPatternGroupCount・getPatternGroupName・getPatternsInGroup・getChannelLoopStyle・getBlockSetStatus・getPatternLength・isPatternDefault・isPatternSelected) の戻り値・引数・副作用 | C provider・mock の実装が 0 件のまま | #1804 (`[PY-48]`) |
| 索引の基準 (0 始まり / 1 始まり) の不統一 | 実装すると索引がずれる | #1804 |
| flapi_table の署名と実機 PyArg 書式の不一致 (3 件) | 表の署名を信じると引数検査が誤る | #1804 |
| getBlockSetStatus の戻り値・4 つの入力引数 (left/top/right/bottom) の意味 | 未実装 | #1804 |
