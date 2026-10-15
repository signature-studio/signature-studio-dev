# tools/python REPORT: PY-129 ui setter 4 件の PE 呼出し経路と C provider 実装 (#3006, 親 #2980 PY-119, 子 #3719 PY-242)

> 正本: `tools/python/REPORT_PY119.md` (保留 12 件の一覧と VA)。本 run の根拠は PE `block00031_PE.bin` の逆アセンブル (VA 付き)。

## 結論

- PY-119 で保留した ui の setter 4 件のうち、**3 件** (`ui.setHintMsg` / `ui.setFocused` / `ui.setSnapMode`) は呼出し経路 (書込み先の呼出し・引数の変換・戻り型) を PE で確定し、mock と C provider に実装した。実装の戻り値は None。**状態は持たない (仮置き)**。書込んだ値を後で読み出す経路は未確定のため、setter は値を記録しない。
- 残り **1 件** `ui.snapMode` は保留 (`0xfdd2c0` の意味が未同定)。実装しない。
- mock と C の差分は 0 (`tests/ui_state_diff.mjs` calls 77・diffs 0。増分 25 件は main の PY-130 の呼出し (setter・getVersion) を含む)。`tests/provider_check.mjs` は実装 168 / 未実装 267 (main 取り込み後。本 PR の pe129 3 件と main の pe130 3 件・pl61 7 件を含む。PR 前の本体は 155 → 158)。`FL_ENGINE=wasm tests/all_tools.mjs` は 48/48 ok を維持。
- 未確定の点 (setter の状態モデル・setSnapMode の範囲外・snapMode) は子 issue **#3719 ([PY-242])** に分けた。

## 手段

- ハンドラ探索と逆アセンブル: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` (展開済み) の `block00031_PE.bin` を `analysis/flapi/pe_handler_probe.py` で読み、entry・fn VA を得た。逆アセンブルは repo 外の補助スクリプト (非コミット) で、RIP 相対の絶対アドレスは `次命令 + disp` で求めた。
- 形式・戻り型: 公開 stub (`analysis/flapi/flapi_table.json` の `sig.returns` / `kwsig.fmt`)。`flapi_table.json` の既存エントリ (`ui.setHintMsg` = `s`・`ui.setFocused` / `ui.setSnapMode` = `i`、np 1) と PE の PyArg 書式は一致した。
- 共通経路 `0xd6fd10` (self → object) と `0xd843d0` (書込みの投入):
  - `0xd843d0(obj, &ret, cb, value, ...)`: 第 1 引数 obj の +0x50 sub-object が非 null かつ `0xd84f30(sub)` が偽なら何もしない (status -2 = 未適用)。それ以外は node を作り (`0xd841e0`)、value・stack 引数・cb (node+0x58) を格納して `0x526190` で投入する。`0xd84290` が node+0x58 の cb を呼ぶ。戻り status は node+0x60 (-2 = 未適用 / -4 = 途中 / 0 = 適用)。
  - 本 PR の 3 setter は、いずれも cb の中で書込む。cb の gate は `G = 0x15e8790` (UI 根オブジェクト) を起点にする。

## 確定した 3 関数 (PE 根拠・実装済み・値は持たない)

`G` = 絶対アドレス `0x15e8790`。

| 関数 | entry | fn (VA) | 形式 | 経路 (cb の中身) | 書込み先 | 変換 | 戻り型 (stub) | 実装の値 |
|---|---|---|---|---|---|---|---|---|
| `ui.setHintMsg` | 0x151b668 | 0xd6c5b0 | VARARGS `s` (flags 1) | `0x41c6e0` で std::string 化 → `0xd6fd10(self)` の obj → `0xd843d0(obj, &ret, cb=0xd6c570, value)`。cb は gate `0x11d1430` (`G→+8→vtbl[0x88]()` の真偽) が真なら `0x11f16b0(*[0x15e0ff8], value, 0)` | `0x11f16b0` 経由 (`[0x15e2eb8]→+0x858` 系を参照) | str → std::string | None | None (状態なし) |
| `ui.setFocused` | 0x151b788 | 0xd6ce50 | VARARGS `i` (flags 1) | `0xd6fd10` → `0xd843d0(obj, &ret, cb=0xd6cdf0, i)`。cb は `G→+8→vtbl[0x98]()` が真なら `G→+0x54` の sub-object の `vtbl[0x38](i を 1 byte に切り詰めた値)` | sub-object (`G→+0x54`) の vtbl 0x38 (getFocused の vtbl 0x28 と対。意味は未確定) | int → byte | None | None (状態なし) |
| `ui.setSnapMode` | 0x151b448 | 0xd6b7b0 | VARARGS `i` (flags 1) | `0xd6fd10` → `0xd843d0(obj, &ret, cb=0xd6b700, i)`。cb は gate `G→+8→vtbl[0x98]()` が真で、かつ `i ∈ 0..15` かつ 16bit マスク `0xd6b7a0` (値 0x7fff) のビット i が立つ場合のみ、`*([0x15e2eb8])+0xb18` の object の `vtbl[0x1f0](0x7a0d50(obj, i), 1)` を呼ぶ | `[0x15e2eb8]→+0xb18` の object | int | None | None (状態なし) |

- 有効域: `setSnapMode` は **i ∈ 0..14** (マスク 0x7fff)。範囲外・gate 偽では書込みは無く、status は -2 のまま。
- 3 関数とも PE の戻り値は None (戻り値の格納は共通経路の `&ret` で、Python には返さない)。
- 実装の仮置き: mock と C は型検査 (引数個数 1・setHintMsg は文字列・setFocused / setSnapMode は整数 (bool 可・None は 0)) のみ行い、状態を変えない。範囲外の挙動は実装していない (有効域チェックはしない)。

## 保留 1 件 `ui.snapMode` (子 #3719)

| 関数 | entry | fn (VA) | 確定した事実 | 未確定の点 | 子 issue |
|---|---|---|---|---|---|
| `ui.snapMode` | 0x151b468 | 0xd6b8d0 | flags 1 (VARARGS)・stub は int。PyArg `i` の後 `0xd84680(obj, &out, id=0x31, value=i, flag=0xfdd270(), 0xf)` → 内部で `0xfdd2c0(id, value, flag, 0xf)` | `0xfdd2c0` の意味 (読み書きの別・戻り値の範囲)。`0xd82c20` (戻り変換) の確認 | PY-242 (#3719) |

## 検証

測定 commit: `a052f7390` (コードを変えた最後の commit。`origin/main` (abb5fbf9d) の取り込み merge。衝突 4 件 (`host/fl_mock.mjs`・`provider/fl_engine.c`・`tests/provider_check.mjs`・`tests/ui_state_diff.mjs`) は PR 側と main 側の両方を残して解消)。その前の取り込み (`72ae6d066`・origin/main 8c23860cd) の衝突 2 件 (`docs/DOC_MAP.md`・`tests/provider_check.mjs`) も両方残した。`build_cpython_wasm.sh` の測定は `72ae6d066` の時点 (以降の差分は provider・host・tests のみで CPython の入力に無い)。以降の commit は `tools/python/REPORT_PY129.md` のみ。

環境: runner 4 core。`load` は各コマンドの終了直後の `/proc/loadavg` (1 分平均)。`fl-win64` は `$RUNNER_TEMP/fl-win64` に展開し `FL_WIN64_DIR` に指定。`toolchain-emsdk` は本 run の素材に無かったため、emsdk を pin 6.0.12 で `$RUNNER_TEMP/emsdk` に導入し、`[EMSDK]` (`docs/REFERENCES.md`) の位置に symlink した (`emcc --version` 6.0.12)。

| コマンド | 結果 | wall | load |
|---|---|---|---|
| `bash fetch_inputs.sh` | rc 0 (`work/` に MCPTools.pyc・midi.py・utils.py・device script を配置) | 未計時 | — |
| `bash build_cpython_wasm.sh` | rc 0 | 3 分 25.5 秒 (205.5 秒) | 未計測 |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 | 4.6 秒 | 未計測 |
| `bash provider/build.sh` | rc 0・ハンドラ 168 (`fl_table.c`: 関数 435。`a052f7390` で再ビルド) | 未計時 | 未計測 |
| `node tests/provider_check.mjs` | PASS (functions 435・実装 168・未実装 267・MCP 静的 60) | 0.264 秒 | 0.52 |
| `node tests/ui_state_diff.mjs` | calls 77・diffs 0・PASS (rc 0)。52 → 77 は main の PY-130 の呼出し (setter・getVersion) の追加 | 0.041 秒 | 0.52 |
| `node tests/general_diff.mjs` | calls 41・diffs 0・PASS (rc 0) | 0.043 秒 | 0.52 |
| `node tests/ui_diff.mjs` | calls 17・diffs 0・範囲外既知差分 3・PASS (rc 0) | 0.042 秒 | 0.52 |
| `node tests/mixer_diff.mjs` | calls 69・diffs 0・PASS (rc 0)。calls 62 → 69 は main 側の `mixer_diff.mjs` の追加 (本 PR の変更ではない) | 0.043 秒 | 0.52 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok・soft_error 0・raised 0・host_calls 37,425・callback_roundtrip true (rc 0) | 1.239 秒 | 0.56 |

- `ui_state_diff.mjs` の calls 52 は、通常呼出し (ui ゲッター 14 + getFocused 3 + setter 13 = 30) と引数個数違い (22) の合計。setter 追加分は 19 呼出し (通常 13 + 個数違い 6)。
- 参考: PY-119 報告の `ui_state_diff` calls 12 は、現在のスクリプトの呼出し列と一致しない (PR 前の列は、ゲッター 17 + 個数違い 16 = 33 件と列から数えた値で、実行して測ったものではない)。PY-119 の件数は古いまま残っている (本 PR では訂正しない)。

ネガティブコントロール: `host/fl_mock.mjs` の `ui.setSnapMode` の引数個数検査 (382 行) を `arity(a, 1, 1)` から `arity(a, 1, 2)` に変えると、`node tests/ui_state_diff.mjs` は `ui 状態ゲッター差分 1 件` で rc 1 (FAIL)。元に戻すと calls 52・diffs 0・PASS (rc 0)。元に戻した後の `git diff -- tools/python/host/fl_mock.mjs` は空。`provider/*.wasm` は変えていない (mock のみの変更)。

## コード差分

- `host/fl_mock.mjs`: `ui.setHintMsg` (文字列検査)・`ui.setFocused` / `ui.setSnapMode` (整数検査) を PY-119 の ui 行の直後に追加。状態は持たない。
- `provider/fl_engine.c`: 同じ 3 関数を `FL_H(ui, ...)` で追加 (`NARGS(1, 1)` と `A_STR(0)` / `A_INT(0, 0)`、戻り `fl_ret_none`)。
- `tests/provider_check.mjs`: `pe129` の Set (3 件) と実装判定への追加、件数 assert は 168 / 267 (PR の pe129 3 件を加えて 158 / 277。main 取り込み分として `pl61` (PY-61・7 件) と `pe130` (PY-130・3 件) を判定行に両方残した結果)。
- `tests/ui_state_diff.mjs`: setter の呼出し列 (通常 13・引数個数違い 6) を追加。

```
$ git diff a052f7390 HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| setHintMsg / setFocused / setSnapMode の状態モデル (値を持たない。書込んだ値の読出し経路は未確定: getHintMsg の `[0x15e2eb8]→+0xbe8` と `0x11f16b0` の `+0x858` 系が同じ object か、getFocused の sub-object の読出し) | 書いた値を後で読めない。mock と C は getHintMsg / getFocused / getSnapMode を初期値で返す | 子 #3719 (PY-242) |
| setSnapMode の範囲外 (i ∉ 0..14・gate 偽) の挙動 (status -2 のまま。Python 側の戻り変換 `0xd82c20` が未確認) | 範囲外で例外になるかが未確認。mock と C は範囲検査せず None を返す | 子 #3719 (PY-242) |
| snapMode (`0xfdd2c0` id 0x31) の意味・戻り型 | `ui.snapMode` は未実装 (Unspecified error) | 子 #3719 (PY-242) |
| 実装 3 件の値 (None・状態なし) は実機測定していない | 実機の戻り挙動は未確認 | 親 #2831 の残件として追跡 |
