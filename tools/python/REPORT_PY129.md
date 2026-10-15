# tools/python REPORT: PY-129 ui setter 4 件の PE 呼出し経路と C provider 実装 (#3006, 子 #3719 PY-242。前段 PY-119)

> 正本: `tools/python/REPORT_PY119.md` (保留 12 件の一覧と VA)。本 run の根拠は PE `block00031_PE.bin` の逆アセンブル (VA 付き)。

## 結論

- PY-119 で保留した ui の setter 4 件のうち、**3 件** (`ui.setHintMsg` / `ui.setFocused` / `ui.setSnapMode`) は呼出し経路 (書込み先の呼出し・引数の変換・戻り型) を PE で確定し、mock と C provider に実装した。実装の戻り値は None。**状態は持たない (仮置き)**。書込んだ値を後で読み出す経路は未確定のため、setter は値を記録しない。
- 残り **1 件** `ui.snapMode` は保留 (`0xfdd2c0` の意味が未同定)。実装しない。
- mock と C の差分は 0 (`tests/ui_state_diff.mjs` calls 109・diffs 0・PASS)。`tests/provider_check.mjs` は functions 435・実装 208 / 未実装 227 (件数は `provider_expect/*.json` の和集合から導出する。手書きの件数は持たない。pe129 は `provider_expect/pe129.json` に置いた)。`FL_ENGINE=wasm tests/all_tools.mjs` は 48/48 ok を維持 (host_calls 37,425)。
- 測定 commit: `12db2a260` (main `ce906a3be` の取り込み merge。`tools/python` のコードを最後に変えた commit)。検証 HEAD はこの REPORT 修正を含む commit。`tools/python` の md 以外は `12db2a260` から HEAD まで差分 0 (下の「コード差分」)。
- 未確定の点 (setter の状態モデル・setSnapMode の範囲外・snapMode) は子 issue **#3719 ([PY-242])** に分けた。

## 手段

- ハンドラ探索と逆アセンブル: `tools/python/analysis/flapi/pe_handler_probe.py` (入力は `$FL_WIN64_DIR/extracted/block00031_PE.bin`。`fl-win64.tar.zst` を `[FL-WIN64]` の展開先に展開して使う)。entry・fn VA は名前指定で得た (`FL_WIN64_DIR=$FL_WIN64_DIR python3 analysis/flapi/pe_handler_probe.py setHintMsg setFocused setSnapMode snapMode`)。cb と共通経路は VA 指定で ret まで逆アセンブルした (`... pe_handler_probe.py 0xd6b700 0xd843d0`。VA 指定は本 PR で追加: `c2ee73c93`)。RIP 相対の絶対アドレスは `次命令 + disp` で求めた。
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

- 有効域と status: `setSnapMode` の cb (`0xd6b700`) は、gate 偽なら status -2 のまま何もしない。gate 真では status を -4 にしてから範囲検査 (`cmp eax, 0xf`・マスク `0x7fff` のビット i) に入り、i ∈ 0..14 で bit が立つときだけ書込み (`vtbl[0x1f0]`) を行い、status を 0 にする。i ∉ 0..14 (i = 15 を含む) では書込みをせず、status は -4 のまま終わる (逆アセンブル: `-2` を書く d6b709 → gate 通過で `-4` を書く d6b72f → 範囲検査が偽なら d6b75f から終了)。
- 3 関数とも PE の戻り値は None (戻り値の格納は共通経路の `&ret` で、Python には返さない)。
- 実装の仮置き: mock と C は型検査 (引数個数 1・setHintMsg は文字列・setFocused / setSnapMode は整数 (bool 可)) のみ行い、None を返す。`ui_state_diff` で None 呼出しを固定した (None を 0 として扱うかは未確認)。状態を変えない。範囲外の挙動は実装していない (有効域チェックはしない)。

## 保留 1 件 `ui.snapMode` (子 #3719)

| 関数 | entry | fn (VA) | 確定した事実 | 未確定の点 | 子 issue |
|---|---|---|---|---|---|
| `ui.snapMode` | 0x151b468 | 0xd6b8d0 | flags 1 (VARARGS)・stub は int。PyArg `i` の後 `0xd84680(obj, &out, id=0x31, value=i, flag=0xfdd270(), 0xf)` → 内部で `0xfdd2c0(id, value, flag, 0xf)` | `0xfdd2c0` の意味 (読み書きの別・戻り値の範囲)。`0xd82c20` (戻り変換) の確認 | PY-242 (#3719) |

## 検証

測定 commit は `12db2a260` (main `ce906a3be` の取り込み merge)。以下の全件をこの commit で再実行した (CPython・flpy を含む)。`tools/python` の md 以外は `e5ea7a6dc` (PR 前 HEAD) から `12db2a260` まで、pe129.json の追加と provider_check.mjs の main 側採用のみ。

環境: runner 4 core。`load` は OS の 1 分平均の負荷値 (`/proc/loadavg` の 1 分値)。`fl-win64` を `$RUNNER_TEMP/fl-win64` に展開し (`FL_WIN64_DIR`)、`fetch_inputs.sh` で `work/` に配置した (win64 経路。mac pkg 無し)。`toolchain-emsdk.tar.zst` を展開し `/opt/emsdk` (`[EMSDK]`) でビルドした。`wall` の「未計測」は時間を測っていない行。

| コマンド | 測定 commit | 結果 | wall | load |
|---|---|---|---|---|
| `bash build_cpython_wasm.sh` | `12db2a260` | rc 0 (`python.wasm` 5,927,853 バイト) | 3 分 30 秒 | 2.46 (開始直後) |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | `12db2a260` | rc 0 (`flpy.wasm` 5,924,680 バイト) | 4.9 秒 | 未計測 |
| `bash provider/build.sh` | `12db2a260` | rc 0・fl_table 関数 435・ハンドラ 208 | 1.5 秒 | 未計測 |
| `node tests/provider_check.mjs` | `12db2a260` | PASS (functions 435・implemented 208・unimplemented 227・mcp_static 60) | 0.28 秒 | 1.69 |
| `node tests/ui_state_diff.mjs` | `12db2a260` | calls 109・diffs 0・PASS | 未計測 | 未計測 |
| `node tests/general_diff.mjs` | `12db2a260` | calls 52・diffs 0・PASS | 未計測 | 未計測 |
| `node tests/ui_diff.mjs` | `12db2a260` | calls 17・diffs 0・範囲外既知差分 3・PASS | 未計測 | 未計測 |
| `node tests/mixer_diff.mjs` | `12db2a260` | calls 69・diffs 0・PASS | 未計測 | 未計測 |
| `node tests/arrangement_diff.mjs` | `12db2a260` | calls 39・state 10・stateDiffs 0・PASS | 0.04 秒 | 0.95 |
| `node tests/device_diff.mjs` | `12db2a260` | calls 21・link_calls 9・rejects 13・midi_out 10・diffs 0・PASS | 0.04 秒 | 0.95 |
| `node tests/channels_diff.mjs` | `12db2a260` | calls 238・loop_cases 9・grid_calls 1200・diffs 0・PASS | 0.07 秒 | 0.95 |
| `node tests/playlist_diff.mjs` | `12db2a260` | calls 72・diffs 0・PASS | 0.04 秒 | 0.95 |
| `node tests/screen_menu_diff.mjs` | `12db2a260` | calls 42・diffs 0・PASS | 0.05 秒 | 0.95 |
| `node tests/ui_editor_diff.mjs` | `12db2a260` | ok 6・bad 8・diffs 0・PASS | 0.04 秒 | 0.95 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | `12db2a260` | 48/48 ok・host_calls 37,425・callback_roundtrip true・rc 0 | 未計測 | 未計測 |

注:
- `python.wasm` のサイズは `5e92b8104` の旧記録 (5,927,853 バイト) と一致した。旧 REPORT の 5,928,327 バイトは本測定と一致しないため、旧記録は取り消す。
- `ui_state_diff.mjs` の calls は 102 → 109 に変わった。増分の内訳は未確認 (main 取り込みによる呼出し追加を含むと思われるが、検証していない)。
- ネガティブコントロール: 本測定では実施していない (前回測定 `9952407f4` では `arity(a, 1, 1)` → `arity(a, 1, 2)` で ui_state_diff が rc 1 (FAIL) となり、戻すと PASS を確認済み)。

## コード差分

- `host/fl_mock.mjs`: `ui.setHintMsg` (文字列検査)・`ui.setFocused` / `ui.setSnapMode` (整数検査) を PY-119 の ui 行の直後に追加。状態は持たない。
- `provider/fl_engine.c`: 同じ 3 関数を `FL_H(ui, ...)` で追加 (`NARGS(1, 1)` と `A_STR(0)` / `A_INT(0, 0)`、戻り `fl_ret_none`)。
- `tests/provider_check.mjs`: main 側 (`provider_expect/` 方式) を採用。pe129 の 3 件は `provider_expect/pe129.json` に移した。件数 assert の手書きは無い。
- `provider_expect/pe129.json`: 新規。tag `pe129`・refs `#3006`・functions 3 件。
- `tests/ui_state_diff.mjs`: setter の呼出し列を追加 (通常 15 件。`setFocused(null)`・`setSnapMode(null)` は None の試験)・引数個数違い 6 件)。
- `analysis/flapi/pe_handler_probe.py`: VA 指定 (`0x...`) で任意の VA を逆アセンブルできるようにした。名前指定の動作は変えていない。

```
$ git diff 12db2a260 HEAD -- tools/python ':!*.md'
(空。差分 0 行。測定 commit から本 REPORT を含む最終 HEAD まで、md 以外のコードは変えていない)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| setHintMsg / setFocused / setSnapMode の状態モデル (値を持たない。書込んだ値の読出し経路は未確定: getHintMsg の `[0x15e2eb8]→+0xbe8` と `0x11f16b0` の `+0x858` 系が同じ object か、getFocused の sub-object の読出し) | 書いた値を後で読めない。mock と C は getHintMsg / getFocused / getSnapMode を初期値で返す | 子 #3719 (PY-242) |
| setSnapMode の範囲外 (i ∉ 0..14)。gate 真では status -4 のまま書込み無し (`0xd6b75f`)。gate 偽は -2 のまま | 範囲外の status (-4) を Python 側の戻り変換 `0xd82c20` が例外・値のどれにするかが未確認。mock と C は範囲検査せず None を返す | 子 #3719 (PY-242) |
| snapMode (`0xfdd2c0` id 0x31) の意味・戻り型 | `ui.snapMode` は未実装 (Unspecified error) | 子 #3719 (PY-242) |
| 実装 3 件の値 (None・状態なし) は実機測定していない | 実機の戻り挙動は未確認 | 子 #3719 (PY-242) |
