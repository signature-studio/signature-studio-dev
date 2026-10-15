# PY-358 (#4699): screen.drawText の個数検査 (max=6 を code 5 で拒否) を flapi に合わせる

親: #4674 (PY-352)。前段: `tools/python/REPORT_PY352_4674.md` §5 が本件を未解決として #4699 に起票した。既知類型: 該当なし (lift 作業ではない。probe の引数サンプルの型の誤り)。

## 結論

- C 側の個数は正しい。`provider/fl_engine.c` の `NARGS(6,6)`・`provider/gen/fl_table.c` の `{"screen","drawText",'n',6,6,...}`・`analysis/flapi/flapi_table.json` の `kwsig.max=6` が一致している。
- 失敗の原因は個数ではなく **型**。`sig_arity_probe.mjs` は型不明 (`sig.params[i].type == null`) の引数を整数 `0` で埋めていた。`drawText` の `kwsig.fmt` は `isiiii` で、第 2 引数 (`s`) は文字列。C の `A_STR` は整数を受けると code 5 (WRONG_PARAM) を返すため、正しい個数の呼出しが拒否されていた。
- 直したのは probe だけ (`tests/sig_arity_probe.mjs`)。型不明の引数は `kwsig.fmt` の文字で決める (`s` なら文字列、それ以外は整数)。C・表・mock は変えていない。

## 1. 測定

- 素材: 不要 (probe は provider の wasm と `analysis/flapi/` の表だけを使う)。provider のビルドに使う emsdk は `tools/m1/flags.sh` の pin `6.0.12` を `emsdk install` で導入し、`EMSDK_ENV=<emsdk>/emsdk_env.sh bash provider/build.sh` が rc 0。
- 基準 (修正前): `origin/main` (`569b5c984`) の provider を `provider/build.sh` でビルドし、修正前の probe を実行。

  ```
  node tests/sig_arity_probe.mjs
  → actual: [{ name: 'screen.drawText', why: 'max=6 個が拒否された', wasm: { code: 5 } }]  (exit 1)
  ```

- 修正後: 本 PR の worktree (`17ee56db4` + probe 修正) で `provider/build.sh` rc 0 → probe:

  ```
  {"kwsig_targets":24,"implemented":[...13 件...],"unimplemented":11,"fails":0,"PASS":true}
  ```

  `implemented` に `screen.drawText` を含み、fails 0。
- 検査の意味: probe は各関数で (1) max 個の呼出しが code 5 にならず mock と一致 (2) max+1 個が code 5 (3) required-1 個が code 5 を確認する。`drawText` は (2) で 7 個、(3) で 5 個を拒否することを確認済み。

## 2. 未実施

- `screen_diff.mjs` などの差分検査は未実行。C の変更は 0 行で、probe のみを変えたため。

## 3. 変更

- `tools/python/tests/sig_arity_probe.mjs`: `sample` を `sampleAt(type, fmtCh)` に置換。型不明 (`null`) の引数は `kwsig.fmt` の文字で決め、`s` だけ文字列にする。`okArgsOf(t)` で全引数を組む。`fmt` の `|` は除く。

## 4. 差分の確認

- 本 PR のコード差分は `tools/python/tests/sig_arity_probe.mjs` の 1 ファイルのみ。`provider/`・`host/` の差分は 0 行。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `build_flpy.sh` が `EMSDK_DIR` を `set -u` で参照して落ちる | flpy 経由の `provider_check`・`all_tools` が未実施 | #4698 (PY-357) |

注: `screen.addTextLine` (`kwsig.fmt=siiii`) も第 2 引数が文字列。probe は `kwsig.fmt` に従って文字列を入れるようになったが、この関数は未実装 (probe の `unimplemented`) のため実装時に検証される。
