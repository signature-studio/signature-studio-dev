# tools/python REPORT: PY-236 ui.setTimeDispMin の PE 確定と C・mock 実装 (#3706, 親 #3007・PY-130)

> 正本: `tools/python/REPORT_PY130_3007.md` (保留の確定表)・`tools/python/REPORT_PY95.md` (getter 側の所在)。

## 結論

- `ui.setTimeDispMin` の toggle 先を PE VA で確定し、mock と C に実装した。mock と C の差分は 0 (`tests/ui_state_diff.mjs` 86 呼出し)。
- getter `ui.getTimeDispMin` が読む byte は、setter が反転する byte と**同じ** (`0x16bc9f2`)。`.data` の slot `0x15e1e40` の初期値が `0x016bc9f2` で、この slot への書込みは PE 内に無い。
- 残り (`setStepEditMode` の書込み末端 `vtbl[0x200]` の先・S の型) は本 PR では未確定。下の未解決表に書く。

## 確定事項 (PE VA)

| 項目 | VA | 根拠 |
|---|---|---|
| `setTimeDispMin` entry / wrapper / callback | 0x151b748 / 0xd6ccb0 / 0xd6cc60 | `pe_disasm.py` |
| callback の引数読取り | なし (`rbx=rcx`・`[rbx+0x60]` を書くだけ) | `pe_disasm.py 0xd6cc60` |
| gate | `[[G]+8]` の `vtbl[0x98]` (G = 0x15e4790)。真なら次へ | 同上 (実行時オブジェクトのため静的には解けない。PY-119・PY-130 と同じく真と仮定) |
| 副作用 | `call 0x12491c0` | 同上 |
| toggle | `byte [0x16bc9f2] = ([0x16bc9f2] == 0)` | `pe_disasm.py 0x12491c0` |
| toggle 後の呼出し | `0x1248ac0`・`0x12e2ac0`・`0xfdee80` | 同上 |
| getter `getTimeDispMin` | 0xd6cc40: `[*(0x15e1e40)]` を読んで変換 slot `0x15e4280` を呼ぶ | `pe_disasm.py 0xd6cc40` |
| getter の slot 0x15e1e40 | `.data` の初期値 `0x016bc9f2` (qword)。PE 内の書込み 0 件 | `pe_rip_refs.py 0x15e1e40` (参照 4 件・全て読込み) と `.data` の直接読取り |

- `pe_rip_refs.py 0x16bc9f2` の参照は 7 件 (setter 側 callback・toggle・後続の読込み)。getter は slot 経由で同じ byte を読むため、setter 後の getter は setter の反転結果を読む。

## 実装

- `host/fl_mock.mjs`: `ui.setTimeDispMin` は `st.uiTimeDispMin = !st.uiTimeDispMin` (`arity(a,0,0)`)。
- `provider/fl_engine.c`: `FL_H(ui, setTimeDispMin) { NARGS(0, 0); ui_time_disp_min = !ui_time_disp_min; ... }`。`getTimeDispMin` の既存の状態変数と共有する。
- `tests/ui_state_diff.mjs`: setter → getter の順で状態の一致を見る 4 呼出し、引数 1 個の個数違い 1 件を追加。
- `tests/provider_check.mjs`: `pe130` に `ui.setTimeDispMin` を追加。実装件数 188 → 189、未実装 247 → 246 (総数 435 は不変)。

## 検証

測定 commit: 本 PR の最後のコード変更 commit (下の `git diff` で範囲確認)。環境: runner 4 core。素材は `$ARTIFACTS_DIR` の `fl-win64.tar.zst` と `toolchain-emsdk.tar.zst` を確認済み。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` に `block00031_PE.bin` 等を展開し、`fetch_inputs.sh` (rc 0) で `work/` を作った。

| コマンド | 結果 |
|---|---|
| `bash provider/build.sh` | rc 0・`fl_table.c 435 関数, ハンドラ 189` |
| `gcc -fsyntax-only -Wall -Wextra provider/fl_engine.c` | rc 0。警告は既存の `h_channels_getChannelIndex` の未使用変数 1 件のみ (本変更とは無関係) |
| `python3 provider/gen_provider.py --check-handlers provider/fl_engine.c` | rc 0・ハンドラ 189 |
| `node tests/ui_state_diff.mjs` | calls 86・diffs 0・PASS |
| `node tests/ui_diff.mjs` | calls 17・diffs 0・範囲外既知差分 3・PASS |
| `node tests/ui_display_diff.mjs` / `ui_browser_diff.mjs` / `ui_editor_diff.mjs` | PASS (diffs 0) |
| `node tests/provider_check.mjs` | 件数 assert (impl 189・unimpl 246) は通過。section 3 以降が `dist/flpy.js` (CPython wasm) を要るため停止。**未実行** |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | **未実行**: `dist/flpy.js` が無い (`build_cpython_wasm.sh` が必要) |

### ネガティブコントロール

C 側だけ `ui_time_disp_min = !ui_time_disp_min` を `ui_time_disp_min = ui_time_disp_min` に壊して `ui_state_diff.mjs` を実行:

- 結果: rc 1。`AssertionError: ui 状態ゲッター差分 1 件` (mock と C の不一致を検出)。
- 元に戻して `cmp` で一致を確認し、再実行で PASS (86 呼出し・diffs 0)。

(mock と C の両方を同時に壊した検査は差分 0 のままで、負の対照にならないため数値に含めない。)

### コード差分

測定 commit から HEAD までの `tools/python` (.md 以外) の差分は、本 PR の変更そのもの。`git diff origin/main HEAD -- tools/python ':!*.md'` で確認する。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `setStepEditMode` の書込み末端 (`vtbl[0x200]` の先・S の型) | `[S+0x49e]` への書込みは model 上の仮定のまま | #4051 (PY-294) |
| `setTimeDispMin` の gate `[[0x15e4790]+8]->vtbl[0x98]` の真偽 | 実行時オブジェクトのため静的に解けず、真と仮定 (PY-119・PY-130 と同じ) | 実機の挙動確認 (PM 判断) |
| `setTimeDispMin` の toggle 後の `0x1248ac0`・`0x12e2ac0`・`0xfdee80` の副作用 | API からは観測不能 (状態は getter で確認できる) | 未追跡 |
| `provider_check.mjs` の section 3 以降・`all_tools.mjs` (flpy 経路) | 48/48 の維持は未検証 | #4052 (PY-295) |
| stub 説明文の食い違い (`setTimeDispMin` の stub doc "Is time time display set to minutes") | 説明文のみ | 同上 |
