# tools/python REPORT: PY-128 ui 読出し 4 件の PE 確定と実装 (#3005, 親 #2980・#2831)

> 前段: `tools/python/REPORT_PY119.md` (保留 12 件の記録)。前提の #2980 は PR #3010 で merge 済み (2026-10-14)。

## 結論

- 保留 4 件のうち **2 件を確定して実装した**: `ui.getProgTitle` (定数 `FL Studio 2026`)・`ui.getHintValue` (状態を読まない整数の百分率表示)。mock と C の差分 0 (`tests/ui_state_diff.mjs` 56 呼出し)。
- 残り **2 件** (`ui.getFocusedNodeCaption`・`ui.getFocusedNodeFileType`) は、フォーカスされたノードの実体の vtable slot (`[vtbl+0x100]`・`[vtbl+0x88]`) と字段 (`+0x54`) の意味が未同定のため、実装せず子 issue #3694 (PY-234) に移した。
- 本 PR は issue の範囲を 2 件に縮めて `Closes #3005` とする (規範 11)。

## 確定 2 件 (PE 根拠・実装済み)

| 関数 | entry | fn (VA) | 形式 | 根拠 | 実装 |
|---|---|---|---|---|---|
| `ui.getProgTitle` | 0x151b608 | 0xd6c250 | NOARGS (flags 4) | 状態を読まない。`lea rdx,[0xd6c2c4]` の managed 文字列を `0x41c420` (代入) → `0x414000` (c_str) → Python 化。`0xd6c2c0` の長さ接頭辞 = 14、`0xd6c2c4` の UTF-16LE = `FL Studio 2026` (14 字)。`0x41c420` のバッファは 3×長さ (UTF-16 → UTF-8 の上限と解釈。推定) | `"FL Studio 2026"` |
| `ui.getHintValue` | 0x151b708 | 0xd6cb60 | VARARGS `ii` (flags 1) | PyArg `ii` (value・max を int32 で取得) → `0x11f1a70`。`0x11f1a70` は状態を読まない (第 1 引数は未使用)。式は下記 | `(int32)(value×100) ÷ max` を最近接偶数で整数化し、`%` を付ける |

`0x11f1a70` の式 (逆アセンブル根拠):
- `shl eax,2` と `lea` 2 回 (64 bit) で `value×100` を作るが、`cvtsi2sd xmm0,eax` は下位 32 bit を使う。よって分子は `(int32)(value×100 mod 2^32)`。
- 分母は `cvtsi2sd xmm1,eax` の `max` (int32)。`divsd` で割る。
- `0x40c660` = `cvtsd2si rax,xmm0` (既定の最近接偶数丸め。範囲外と NaN は INT64_MIN)。
- `0x43a820` → `0x43a500` が 10 進 (符号 flag 付き)。`0x414c70` は連結 (長さ `r13+r14` を確保して複写。確認済み)。接尾辞は `0x11f1b14` の `%` (長さ 1)。

## 保留 2 件 (子 issue #234 へ)

| 関数 | entry | fn (VA) | 確定した事実 | 未確定の点 |
|---|---|---|---|---|
| `ui.getFocusedNodeCaption` | 0x151ba68 | 0xd6e470 | `0xa89600(obj, &slot)`。`0xa89600` は `obj.vtbl[0x100](obj,0)` が非 0 のとき、その `+0x48` の object の `vtbl[0x88]` で slot に書く。slot が空なら `""` | `vtbl[0x100]` が返す focused node の実体・`vtbl[0x88]` が書く対象 |
| `ui.getFocusedNodeFileType` | 0x151ba48 | 0xd6e400 | 先頭の `cmp [global],0` で 0 なら `-1`。`obj.vtbl[0x100](obj,1)` が 0 なら `-1`。非 0 なら `+0x48→+0x18→byte[+0x54]` を符号拡張して int | 2 回の `vtbl[0x100]` が指す object の型・`+0x54` 字段の意味 |

フォーカス無し (mock が持つ唯一の状態) の経路は `""` と `-1`。ただし、フォーカス有りの値が未確定のため、既定値を実装せず保留にした。

## 検証

測定 commit: `3bdba9d55` (コードを変えた最後の commit。`feat(python): ui.getProgTitle / getHintValue を PE 確定・mock/C 実装 (#3005)`)。以降の変更は `REPORT_PY128.md` と `docs/DOC_MAP.md` (md のみ)。

環境: runner 4 core、load average 0.15 (HEAD 再現時、03:22:27)。`FL_WIN64_DIR` は素材 `fl-win64` の展開先 (`block00031_PE.bin`・`block24429/24430/25159/24618_DATA.bin` を展開)。`toolchain-emsdk` は [EMSDK] (`docs/REFERENCES.md`)。生成物 (gitignore): `fetch_inputs.sh` (rc 0)・`build_cpython_wasm.sh` (rc 0、3 分 40 秒)・`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・ハンドラ 157 (155 + 2) | 1.3 秒 (emcc キャッシュ済み) |
| `node tests/provider_check.mjs` | PASS (435 / 実装 157 / 未実装 278 / MCP 静的 60) | 0.28 秒 |
| `node tests/ui_state_diff.mjs` | calls 56、diffs 0、PASS | 0.04 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1.28 秒 |

mock と C の値 (同一): `getProgTitle()` = `FL Studio 2026`、`getHintValue(50,100)` = `50%`、`(-1,100)` = `-1%`、`(1,8)` = `12%` (12.5 は偶数側)、`(5,0)` と `(0,0)` = `-9223372036854775808%`、`(2147483647,1)` = `-100%` (int32 折返し)、`(None,1)` = code 5。

ネガティブコントロール: `host/fl_mock.mjs` の係数 `100` を `10` に変えると `node tests/ui_state_diff.mjs` は `ui 状態ゲッター差分 9 件` で rc 1 (FAIL)。元に戻すと calls 56・diffs 0・PASS。

コード差分 (測定 commit から HEAD まで、`tools/python` の .md 以外):

```
$ git diff 3bdba9d55 HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `getFocusedNodeCaption` / `getFocusedNodeFileType` の focused node 実体 | 未実装 (2 件) | #3694 (PY-234) |
| `getHintValue` の PyArg 失敗経路 (`0xd82c20`) の例外型。int32 外の値 (PyArg の OverflowError) | 例外型は provider 規約 (code 5) に合わせた仮定。実機は未確認 | #3694 (PY-234) |
| `getProgTitle` の定数の値が実機で同じか (テスト実行の実測なし) | 定数の読出しは PE 根拠のみ | 親 #2831 の残件として追跡 |
