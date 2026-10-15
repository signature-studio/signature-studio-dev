# tools/python REPORT: PY-254 arrangement の liveSelection 選択規則の PE 確定と mock/C 反映 (#3796, 親 #3043)

> 前提: `REPORT_PY144.md` (呼出し構造・ゲート・選択 2 件)・`REPORT_PY152.md`。
> 既知類型との関係: 該当なし (逆アセンブルによる同定。`docs/DEFECTS.md` の類型は再現していない)。

## 結論

- `liveSelection` (`0xe43ff0`) の a≠0x7fffffff 経路の規則を確定し、mock と C に反映した。差分 0 (`tests/arrangement_diff.mjs` 状態系列 10)。
- 未確定のまま残した (子 #4058 PY-296): マーカー追加 (`0xe546a0`)・jumpToMarker (`0x1180ef0`)・`0xe7e290`・`0xe4b3a0`・`0xd77e20` の 2 経路の object・ゲートの実行時値。この 3 件 (マーカー・jumpToMarker) は状態を変えない (従来どおり)。
- 受入条件は部分達成。issue の範囲を liveSelection に縮め、残りは子 #4058 へ移した。

## 1. liveSelection の規則 (確定)

`0xe43ff0(obj, a, b)` (rcx = obj・edx = a・r8d = b):

- `a == 0x7fffffff` なら `0xe43fa0(obj, 1)` を呼ぶ (現在位置を使う経路。未モデル)。
- `b != 0` (b==1 として扱う) のとき:
  - `anchor = [obj+0xd7c]`。`anchor >= 0` かつ `anchor != a` なら `0xe43d30(obj, anchor, a, 1, 1)` (範囲 (anchor, a))。
  - それ以外は `0xe43d30(obj, -1, -1, 1, 1)`。
  - どちらの後も `[obj+0xd7c] = -1`。
- `b == 0` のとき: `0xe43d30(obj, -1, -1, 1, 1)` で選択を消し、`[obj+0xd7c] = a`。

`0xe43d30` の書込み規則は REPORT_PY144 §4 のとおり (start=x・end=y、x==y なら end=-1、x>y なら入れ替え)。

## 2. 実装

- `host/fl_mock.mjs`: `liveAnchor` (初期値 -1) と `liveSel(a, b)` を追加し、`arrangement.liveSelection` から呼ぶ。
- `provider/fl_engine.c`: `live_anchor` (初期値 -1) と `live_sel(a, flag)` を追加。`liveSelection` は `NARGS(2, 2)` で個数を検査 (表・PE とも 2 なので挙動は変わらない)。
- `tests/arrangement_diff.mjs`: 状態系列に 5 手を追加。期待値は規則からの手計算。
  - `liveSelection(5,0)` → (-1,-1)
  - `liveSelection(9,1)` → (5,9) (anchor 5 から 9)
  - `liveSelection(2,1)` → (-1,-1) (anchor が無い)
  - `liveSelection(3,0)` → (-1,-1) (anchor=3 を設定)
  - `liveSelection(1,1)` → (1,3) (anchor 3 から 1 へ、入れ替え)

仮置き: anchor の初期値 -1 は PE の初期値を未実測。`0xe43fa0` 経路は未モデル。

## 3. 検証

測定 commit: `9feeac80c` (コードを変えた最後の commit)。測定は同 commit の作業ツリーで行った (load average・個別の wall 時間は未採取)。

前提の生成物 (gitignore): `FL_WIN64_DIR` = fl-win64 の必要 block 5 件 (`tar --zstd -xf --wildcards`・2.7 秒)。`fetch_inputs.sh` (rc 0・0.6 秒)、`build_cpython_wasm.sh` (rc 0・3 分 51 秒)、`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・fl_table 435 関数・ハンドラ 188 | 未計測 |
| `node tests/arrangement_diff.mjs` | calls 39、diffs 0、state 10、stateDiffs 0、PASS | 0.105 秒 |
| `node tests/arrangement_selection_diff.mjs` | calls 8、diffs 0、PASS | 未計測 |
| `node tests/general_diff.mjs` | calls 52、diffs 0、PASS | 未計測 |
| `node tests/provider_check.mjs` | PASS (functions 435 / implemented 188 / unimplemented 247 / mcp_static 60) | 0.112 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425 (変更前と同値)、callback 往復 true | 1.743 秒 |
| `node tests/{ilmcp,midi_path,mixer,transport,ui,ui_state,screen,channels,device}_diff.mjs` | 全て rc 0・PASS (diffs 0) | 未計測 |

ネガティブコントロール: `host/fl_mock.mjs` の liveSelection の分岐条件 (`flag && anc >= 0 && anc !== a`) を否定 (`if (!(...)) selSet(anc, a);`) に書き換えると、`node tests/arrangement_diff.mjs` は `AssertionError [ERR_ASSERTION]` で rc 1 (FAIL)。元に戻すと calls 39・stateDiffs 0・PASS (rc 0)。

## 4. 製品 KPI

起動・GUI に関わらないため KPI は書かない (本 PR は python の arrangement 状態のみ)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| マーカー追加 (`0xe546a0`)・jumpToMarker (`0x1180ef0`)・`0xe7e290`・`0xe4b3a0`・`0xd77e20` の 2 経路の object・ゲート `S->vtbl[0x98]` の実行時値 | マーカー・jumpToMarker の 2 件が状態を変えない | 子 #4058 (PY-296) |
| liveSelection の `0xe43fa0` 経路 (a=0x7fffffff) と anchor の初期値 -1 | 現在位置指定時の選択と初期 anchor が未実測 | 子 #4058 (PY-296) |
| jumpToMarker・liveSelectionStart の個数 (PE と表の不一致) | 表と mock/C が PE と不一致 | PM 判断 (REPORT_PY144 §5) |
