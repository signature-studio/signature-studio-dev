# tools/python REPORT: PY-128 ui 読出し 2 件の実装と残り 2 件の保留 (#3005, 親 #2980・#2831)

> 前段: `tools/python/REPORT_PY119.md` (保留 12 件の記録)。前提の #2980 は PR #3010 で merge 済み (2026-10-14)。

## 結論

- 保留 4 件のうち **2 件を確定して実装した**: `ui.getProgTitle` (定数 `FL Studio 2026`)・`ui.getHintValue` (状態を読まない整数の百分率表示)。mock と C の差分 0 (`tests/ui_state_diff.mjs` の呼出し 81 件。main 取り込み後で、PY-130 の setter 分を含む)。
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

## 保留 2 件 (子 issue #3694 へ)

| 関数 | entry | fn (VA) | 確定した事実 | 未確定の点 |
|---|---|---|---|---|
| `ui.getFocusedNodeCaption` | 0x151ba68 | 0xd6e470 | `0xa89600(obj, &slot)`。`0xa89600` は `obj.vtbl[0x100](obj,0)` が非 0 のとき、その `+0x48` の object の `vtbl[0x88]` で slot に書く。slot が空なら `""` | `vtbl[0x100]` が返す focused node の実体・`vtbl[0x88]` が書く対象 |
| `ui.getFocusedNodeFileType` | 0x151ba48 | 0xd6e400 | 先頭の `cmp [global],0` で 0 なら `-1`。`obj.vtbl[0x100](obj,1)` が 0 なら `-1`。非 0 なら `+0x48→+0x18→byte[+0x54]` を符号拡張して int | 2 回の `vtbl[0x100]` が指す object の型・`+0x54` 字段の意味 |

フォーカス無し (mock が持つ唯一の状態) の経路は `""` と `-1`。ただし、フォーカス有りの値が未確定のため、既定値を実装せず保留にした。

## 検証

測定 commit: `ad4642cf2` (M。`origin/main` (`592f4c8e0`) を取り込んだ merge commit。コードを変えた最後の commit)。この REPORT を含む commit (H) は `tools/python/REPORT_PY128.md` のみを変える。

main 取り込みは 8 回あった。1 回目 (`bb6bdcf41` → `43b9e5614`): `fl_mock.mjs`・`fl_engine.c`・`provider_check.mjs`・`ui_state_diff.mjs` が衝突。main 側 (PY-130・#3007 の setter 2 件と ui 版 getVersion) と本 PR (PY-128 の 2 件) の追加なので両方を残した。2 回目 (`1d04852b0` → `a440164c4`): main に PY-132 (#3013) の `pe132` (ui ブラウザ 3 件) が入り、`provider_check.mjs` が衝突。3 回目 (`b6e93d6ac` → `4e8e1dac7`): 競合なし (main 側の `fl_engine.c`・`fl_mock.mjs`・`ilmcp.mjs`・`plugins_diff.mjs` (PY-228) 等)。4 回目 (`93202140d` → `20fef1b35`): 競合なし (main 側の `static64_growth` 系テストの追加のみ。provider・mock・検証テストの本体は変わらない)。衝突はいずれも main 側の追加 (PY-130・#3007 / PY-132・#3013) と本 PR (PY-128) の追加なので両方を残した。`provider_check` の期待値は main 168 / 267 から本 PR の 2 件を足して 170 / 265 (3 回目・4 回目の取り込み後も同じ)。5 回目 (`d39241f69`・PY-138 #3029 の `pe138` 3 件と PY-143 #3041 の `pe143` 2 件): `provider_check.mjs` が衝突。main 側の `pe138`・`pe143` と本 PR の `pe128` を両方残し、件数は main 173 / 262 に本 PR の 2 件を足して 175 / 260 (総数 435 は不変)。6 回目 (`3e55552c1`・PY-133 #3014 の `pe133` 2 件を含む main 59 commit 分): `provider_check.mjs` が衝突。main 側の `pe133` と本 PR の `pe128` を両方残し、件数は main 175 / 260 に本 PR の 2 件を足して 177 / 258 (総数 435 は不変)。7 回目 (`3e55552c1` → `549edb5ea`。main 146 commit 分・PY-235 #3701 の `pe235` 1 件を含む): `provider_check.mjs` のみ衝突。main 側の `pe235` (if 条件と内訳コメントの両方) と本 PR の `pe128` を両方残し、件数は main 176 / 259 に本 PR の 2 件を足して 178 / 257 (総数 435 は不変)。8 回目 (`09bbc6684` → `ad4642cf2`。main `592f4c8e0` の 132 commit 分・PY-136 #3025 の `pe136` (screen 初期化・メニュー 10 件) を含む): 競合は `tests/provider_check.mjs` のみ (`git merge-tree` で事前確認。`docs/DOC_MAP.md`・`host/fl_mock.mjs`・`provider/fl_engine.c` は auto-merge)。main 側の `pe136` と本 PR の `pe128` を両方残し (if 条件に `pe136` を追加。内訳コメントにも追記)、件数は main 186 / 249 に本 PR の 2 件を足して 188 / 247 (総数 435 は不変)。

環境: runner 4 core (load average は M の測定では未記録)。`FL_WIN64_DIR` は素材 `artifacts/fl-win64.tar.zst` (R2 由来) を `$RUNNER_TEMP/fl-win64` に `tar --zstd -xf` で展開 (8.0 秒。`extracted/` を含む)。`toolchain-emsdk` は展開せず [EMSDK] (既存。`docs/REFERENCES.md`) を使用。生成物 (gitignore): `fetch_inputs.sh` (rc 0)・`build_cpython_wasm.sh` (rc 0、207 秒)・`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0、4.9 秒)。M の測定 run の runner には `work/` と `dist/` が無かったため、これらを新規に作った。provider は `bash provider/build.sh` で再ビルド。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・ハンドラ 188 (main 186 + 2) | 1.2 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 188 / 未実装 247 / MCP 静的 60) | 0.28 秒 |
| `node tests/ui_state_diff.mjs` | calls 81、diffs 0、PASS | 0.04 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1.32 秒 |

wall 列は測定 commit `ad4642cf2` での計測 (表の 4 コマンドは同じ commit で実行)。

隣接の差分テスト: `tests/*_diff.mjs` の 23 本 (`ui_state_diff` を含む) と `tests/poc_mcp.mjs` を全て実行し、node の rc は全て 0。各出力の判定は全て PASS (`poc_mcp` は `POC OK`)。主要値: `channels_diff` calls 238・diffs 0、`device_diff` calls 11・diffs 0、`playlist_diff` calls 72・diffs 0、`launchmap_diff` calls 15・diffs 0、`arrangement_diff` calls 39・diffs 0、`ui_browser_diff` ok_calls 8・bad_calls 5・diffs 0、`plugins_diff` calls 56・diffs 0、`ui_editor_diff` ok_calls 6・bad_calls 8・diffs 0、`note_enum_diff` calls 33,264・diffs 0。wall は各 1 回の実行の実測 (0.04〜0.82 秒。`poc_mcp` 0.82 秒が最大)。

mock と C の値 (同一): `getProgTitle()` = `FL Studio 2026`、`getHintValue(50,100)` = `50%`、`(-1,100)` = `-1%`、`(1,8)` = `12%` (12.5 は偶数側)、`(5,0)` と `(0,0)` = `-9223372036854775808%`、`(2147483647,1)` = `-100%` (int32 折返し)、`(None,1)` = code 5。

ネガティブコントロール (M で再測定): `host/fl_mock.mjs` (588 行。旧記録の 438 行は main 取り込み前) の 440 行目の係数 `Math.imul(v, 100)` を `Math.imul(v, 10)` に変えると、`node tests/ui_state_diff.mjs` は `ui 状態ゲッター差分 9 件` (出力の内訳は全て `ui.getHintValue`) で rc 1 (FAIL)。元に戻すと calls 81・diffs 0・PASS (rc 0)。元に戻した後、編集前に取ったバックアップと sha256 が一致し、`git diff --stat -- host/fl_mock.mjs` は空。

コード差分 (測定 commit から H まで、`tools/python` の .md 以外):

```
$ git diff ad4642cf2 HEAD -- tools/python ':!*.md'
(空。0 バイト)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `getFocusedNodeCaption` / `getFocusedNodeFileType` の focused node 実体 | 未実装 (2 件) | #3694 (PY-234) |
| `getHintValue` の PyArg 失敗経路 (`0xd82c20`) の例外型。int32 外の値 (PyArg の OverflowError) | 例外型は provider 規約 (code 5) に合わせた仮定。実機は未確認 | #3694 (PY-234) |
| `getProgTitle` の定数の値が実機で同じか (テスト実行の実測なし) | 定数の読出しは PE 根拠のみ | #3694 (PY-234) |
