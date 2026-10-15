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

- `pe_rip_refs.py 0x16bc9f2` の参照は 7 件。書込みは 3 件、読込みは 4 件 (`0x11a0063` の lea は読込みではなくアドレス渡し)。
  - 0x12491ce (toggle・`0x12491c0` 内): setter の本体。本 PR の対象。
  - 0x1249150 (`mov byte [...], al`・関数 `0x1249130` 内): `0x1249130` の直接呼出しは PE 内に無い。絶対 VA の関数ポインタとして `0xd715d3` で参照される (間接呼出し)。
  - 0x12491ad (`mov byte [...], 0`・関数 `0x12491a0` 内): `0x12491a0` の直接呼出しは PE 内に無い。絶対 VA の関数ポインタとして `0xd72fbe` で参照される (間接呼出し)。
  - `setTimeDispMin` の呼出し木 (`0xd6cc60` → `0x12491c0` → `0x1248ac0`・`0x12e2ac0`・`0xfdee80`) からは、`0x1249130`・`0x12491a0` は直接には呼ばれない。ただし間接呼出しの先 (`0xd715d3`・`0xd72fbe` の表の持ち主) が `ui.setTimeDispMin` の経路から到達するかは未確定。
  - よって「setter 後の getter は反転結果を読む」は、**間接呼出しで 0x1249130・0x12491a0 が挟まらない**という前提付きで成り立つ。mock と C はこの前提の下で toggle のみを実装している。
  - getter は slot 経由で同じ byte を読むため、この前提の下で setter 後の getter は setter の反転結果を読む。

## 実装

- `host/fl_mock.mjs`: `ui.setTimeDispMin` は `st.uiTimeDispMin = !st.uiTimeDispMin` (`arity(a,0,0)`)。
- `provider/fl_engine.c`: `FL_H(ui, setTimeDispMin) { NARGS(0, 0); ui_time_disp_min = !ui_time_disp_min; ... }`。`getTimeDispMin` の既存の状態変数と共有する。
- `tests/ui_state_diff.mjs`: setter → getter の順で状態の一致を見る 4 呼出し、引数 1 個の個数違い 1 件を追加。
- `tests/provider_check.mjs`: `pe130` に `ui.setTimeDispMin` を追加。実装件数 188 → 189、未実装 247 → 246 (総数 435 は不変)。

## 検証

測定 commit: `3d505311a` (main 取り込み merge・`provider_check.mjs` の件数 204/231 への解消後。コードを変えた最後の commit)。main の取り込み前の本 PR の変更は `b87af9d82` (奇数回 toggle 列の追加・provider_check コメント修正)。環境: runner 4 core。素材は `$ARTIFACTS_DIR/fl-win64.tar.zst` (存在を `ls` で確認)。`tar --zstd -xf` で `*block*` を `$RUNNER_TEMP/fl-win64` に展開し、`fetch_inputs.sh` (rc 0) で `work/` を作った。emsdk は素材に無いため上流 `emsdk install 6.0.12` + `activate` で代替した (`emcc` 6.0.12)。

| コマンド | 結果 (実測・b87af9d82) |
|---|---|
| `bash provider/build.sh` | rc 0・1 秒・`fl_table.c 435 関数, ハンドラ 204` |
| `python3 provider/gen_provider.py --check-handlers provider/fl_engine.c` | rc 0・ハンドラ 204 |
| `node tests/ui_state_diff.mjs` | rc 0・0 秒・`calls 88, diffs 0, PASS` |
| `node tests/ui_diff.mjs` | rc 0・0 秒・`calls 17, diffs 0, outOfRangeKnownDiffs 3, PASS` |
| `node tests/ui_display_diff.mjs` | rc 0・0 秒・`ok 12, bad 11, diffs 0, PASS` |
| `node tests/ui_browser_diff.mjs` | rc 0・0 秒・`ok 8, bad 5, diffs 0, PASS` |
| `node tests/ui_editor_diff.mjs` | rc 0・0 秒・`ok 6, bad 8, diffs 0, PASS` |
| `node tests/provider_check.mjs` | §1・§2 の件数 assert (`impl 204`・`unimpl 231`) は通過 (`AssertionError` 0 件)。§3 (`dist/flpy.js` 経路) で `ERR_MODULE_NOT_FOUND` により停止 (**未実行・未解決 #4052**) |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | **未実行**: `dist/flpy.js` が無い (`build_cpython_wasm.sh` が必要・#4052) |

### ネガティブコントロール (merge 後の HEAD で実施)

C 側だけ `ui_time_disp_min = !ui_time_disp_min` を `ui_time_disp_min = ui_time_disp_min` に壊して `provider/build.sh` → `ui_state_diff.mjs` を実行 (`b87af9d82` 上・作業ツリーのみ変更):

- 結果: rc 1。`AssertionError [ERR_ASSERTION]: ui 状態ゲッター差分 2 件` (mock と C の不一致を検出)。
- 元に戻して `cmp` で一致を確認 (`RESTORED`)、再 build・再実行で `PASS (calls 88, diffs 0)`・rc 0。

(mock と C の両方を同時に壊した検査は差分 0 のままで、負の対照にならないため数値に含めない。)

### コード差分

本 PR のコード差分は `cb76a81c5..b87af9d82` (`tests/ui_state_diff.mjs`・`tests/provider_check.mjs`) と、main 取り込み merge `3d505311a` での `tests/provider_check.mjs` の件数・コメント解消のみ。`3d505311a` 以降の `tools/python` の差分は REPORT の更新だけ。main 取り込みで入った他 issue の変更 (PY-135・PY-215 など) は本 PR の範囲外。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `setStepEditMode` の書込み末端 (`vtbl[0x200]` の先・S の型) | `[S+0x49e]` への書込みは model 上の仮定のまま | #4051 (PY-294) |
| `setTimeDispMin` の gate `[[0x15e4790]+8]->vtbl[0x98]` の真偽 (`pm-decision`: 既定案は「真と仮定・mock は常に toggle」) | 実行時オブジェクトのため静的に解けない。gate が偽なら mock とのずれになる | 実機の挙動確認 (PM 判断・未追跡) |
| `setTimeDispMin` の toggle 後の `0x1248ac0`・`0x12e2ac0`・`0xfdee80` の副作用 | API からは観測不能 (状態は getter で確認できる) | 未追跡 |
| `provider_check.mjs` の section 3 以降・`all_tools.mjs` (flpy 経路) | 48/48 の維持は未検証 | #4052 (PY-295) |
| stub 説明文の食い違い (`setTimeDispMin` の stub doc "Is time time display set to minutes")。出所は `flapi_table.json` (生成物) | 説明文のみ。挙動には影響しない | #4145 (PY-305) |
