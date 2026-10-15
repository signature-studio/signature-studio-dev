# tools/python REPORT: PY-5328 screen.addTextLine の副作用・引数検査の実装 (#5328, 親 #4741)

## 結論

- `screen.addTextLine` (書式 `siiii`・PE 0xd7abb0) の副作用のうち確定した部分を mock と C provider に実装した。mock と C の差分は 0 (`tests/screen_diff.mjs` 101 呼出し)。
- 確定: 成功経路 (`scr≠0`) で `0xd7d460` が `scr+0x1cc ← scr+0x1dc` と `scr+0x1d1 ← 1` を書く。`scr == 0` では呼出し自体を飛ばす。
- **未確定 (実装していない)**: 行 record ([scr+0x1c4] 配列の末尾に 92 バイトを書く部分) の各 dword の意味。mock・C には入れていない。仮の値は入れていない (R7 ④)。
- 題名の `[PY-4911]` は #5325 と番号が衝突している。番号の振り直しは起票者に任せる。

## 手段

- 逆アセンブル: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> [命令数]`。展開先は `$RUNNER_TEMP/fl-win64` (fl-win64 を 12 秒で展開)。
- 副作用の確認: `0xd7d460` 内の `[scr+...]` 書込みを全て列挙した。`0xd7d6ba`〜`0xd7d6ca` の 2 書込みの後に `0xd7e330` (0xd7d6dc) を必ず呼ぶ。`0xd7e330` の `[scr+0x1cc]` 書込みは `0xd7e4f7`・`0xd7e67b` の 2 箇所 (どちらも `scr+0x1dc` からの復元) で、通る分岐は未確定。mock と C は `0xd7e330` の効果を模していない (下の未確定 2)。

## 確定した点 (PE 根拠)

| 項目 | VA | 内容 |
|---|---|---|
| 呼出し条件 | 0xd7ac54 | `scr == 0` なら `0xd7d460` を呼ばない |
| 行 record の追加位置 | 0xd7d650〜0xd7d6b5 | `[scr+0x1c4]` の長さ +1 (`0x417fc0`)、末尾要素 (`len-1`・要素幅 0x17 dword = 92 バイト) へ `0x416750` で写す |
| 副作用 1 | 0xd7d6ba〜0xd7d6c4 | `scr+0x1cc ← scr+0x1dc` |
| 副作用 2 | 0xd7d6ca | `scr+0x1d1 ← 1` |
| 戻り値 | 0xd7acb4 | `0xd7d460` の戻り値は使われない。`addTextLine` の戻り値は `0xd82c20(解析の戻り値)` (REPORT_PY170) |
| 書式 | 0xd7acf8 | `siiii` (必須 5)。6 個目の out ポインタは解析されない (REPORT_PY116 §2) |

## 未確定 (本 run で確定できなかった点)

1. **行 record の 23 dword の中身**: `0xd7d460` は `0x668670` (テキスト計測)・`0x40c660` (float→int)・`0x4204d0` (件数)・`0x413480`・`0x412f30`・`0x415610` の結果から record を作る。`0x416750` は型記述子 (r8) の tag で分岐する汎用マーシャリングで、全分岐は未読 (REPORT_PY124・REPORT_PY243 と同じ)。
2. **`0xd7e330` の分岐**: 偽の経路で `[scr+0x1c4]` の要素ごとに呼ぶループ (REPORT_PY135)。`scr+0x1cc` を書き戻す経路 (0xd7e4f7・0xd7e67b) は読めたが、どの分岐がどの入力で通るかは未確定。
3. **`scr+0x1dc` の初期値**: 仮置き 0 (REPORT_PY135・PY121 と同じ)。実機の値は未実測。
4. **`0xd7d460` の引数 `index`・`flag` の意味**: `-1` は既定 x/y (`scr+0x14c`・`scr+0x148`) を使うだけ (#3711 の訂正どおり)。`0x110`・`0x118` の値の意味は未確定。

## 検証

測定 commit: `a44acea67` (コードを変えた最後の commit)。環境: runner 4 core、測定時の load average 1.01 (`uptime` 18:56:26)。素材 `fl-win64` と `toolchain-emsdk` を展開して使用 (emsdk は 6.0.12)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0 | 11.1 秒 |
| `bash fetch_inputs.sh` | rc 0 | 0.6 秒 |
| `bash build_cpython_wasm.sh` | rc 0 | 3 分 23 秒 |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 | 20.4 秒 (user) |
| `node tests/provider_check.mjs` | PASS (435 / 実装 229 / 未実装 206 / MCP 静的 60) | 0.42 秒 |
| `node tests/screen_diff.mjs` | calls 101、diffs 0、PASS | 0.05 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1.57 秒 |
| `node tests/general_diff.mjs` | PASS | 0.05 秒 |

ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の `addTextLine` の副作用を外すと `node tests/screen_diff.mjs` は `AssertionError: screen 差分 2 件`・rc 1 で FAIL。戻すと calls 101・diffs 0・PASS (rc 0)。

コード差分 (測定 commit から HEAD まで。`tools/python` の .md 以外):

```
$ git diff a44acea67 HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

- 行 record の中身 (上の未確定 1)・`0xd7e330` の分岐 (未確定 2)・引数 `0x110`/`0x118` の意味 (未確定 4)。受入条件の残り (record の確定と mock・C の record 実装) は未達。元の issue #5328 に残す (`Refs #5328`)。
- `scr+0x1dc` の実機値 (未確定 3)。実機で取得する必要があり、PE だけでは決まらない。
