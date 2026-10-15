# tools/python REPORT: PY-144 arrangement の選択・マーカー副作用と引数個数の PE 確定 (#3043, 親 #2983)

> 前提: `REPORT_PY152.md` (arrangement 6 件の PE 呼出し構造・未解決表)。本 REPORT は同表の 5 行 (選択・マーカーの副作用、jumpToMarker 個数、liveSelectionStart 個数、int/bool・負値) を扱う。
> 既知類型との関係: 該当なし (逆アセンブルによる同定。`docs/DEFECTS.md` の lift の miscompile 類型の再現は行っていない)。

## 結論

- 5 件の書込み系 (`addAutoTimeMarker`・`jumpToMarker`・`liveSelection`・`selectionClear`・`selectionSet`) の呼出し経路を VA 付きで確定した。共通経路 `0xd843d0` はレコードを作り、コールバックへ引数を渡す。コールバックは `[0x15e4790]` の sub-object の vtable `+0x98` (ゲート) が真のときだけ効果を実行する。
- **選択の 2 件を状態に反映した**。`selectionClear` は `0xe43d30(obj, -1, -1)`、`selectionSet` は `0xe43d30(obj, a, b)` を呼ぶ。`0xe43d30` の書込み規則 (start=a・end=b。a==b なら end=-1、a>b なら入れ替え) を mock と C に入れ、`tests/arrangement_diff.mjs` の状態系列 (期待値は規則からの手計算) で両エンジン一致 (差分 0)。
- **未確定**: マーカー追加 (`0xe546a0`)・liveSelection の b=0 経路と anchor `+0xd7c` の設定元・jumpToMarker (`0x1180ef0`)・`0xe7e290`・`0xd77e20` が返す 2 経路の object の意味。この 3 件 (マーカー・liveSelection・jumpToMarker) は状態を変えず、引数検査だけ行う (従来どおり)。残りは子 #3796 (PY-254) に分けた。
- **個数**: `jumpToMarker` は PE が `i|i` (必須 1)、表は 2。`liveSelectionStart` は PE が引数を読まず任意の個数を受理し、表は 0。どちらも**表と mock/C は変えない** (理由は §5)。PE 側の確定は済み、表の扱いは PM 判断。
- **int と bool**: 変換スロット `0x15e4280` は `PyLong_FromLong` (`REPORT_PY152` で同定)。bool 戻りの 4 件 (PY-87) も同じ slot を通るため、PE 上の Python 型は int (0 / 1)。stub の bool とは一致しない。実機の値は未実測。
- 負値: 変換は 32 bit の `long` で、`selectionClear` の `-1` は未選択の番兵 (Python の int `-1`)。

## 手段

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` から `extracted/block00031_PE.bin`・`block24429/24430/24618/25159` を `tar --zstd -xf --wildcards` で展開し、`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` とした (展開 2.5 秒)。
- 逆アセンブル: `analysis/flapi/pe_disasm.py <VA> <命令数>` (capstone)。entry・fn・flags は `analysis/flapi/pe_handler_probe.py`。
- RIP 相対の参照先は「次命令の番地 + disp」で計算した (`0xd77e60` の参照は `0x15e4790`)。
- 本体の読解は手動 (同定した呼出し・引数・分岐)。読んでいない分岐は「未読」と書く。

## 1. 呼出し構造 (5 件の handler → 共通経路 `0xd843d0`)

| 関数 | entry | fn | flags | PyArg 書式 | 引数 → レコード rec | コールバック (VA) | 最後の引数 (flag) |
|---|---|---|---|---|---|---|---|
| addAutoTimeMarker | 0x151dc70 | 0xd781e0 | 1 | `is` (time, name) | time → rec+0x18 (int)・name → rec+0x48 (`0x41c6e0` で std::string 化) | 0xd78130 | 未読 |
| jumpToMarker | 0x151dc30 | 0xd77eb0 | 3 | `i\|i` kwlist (delta, select) | delta → rec+0x18・select (既定 0) → rec+0x20 | 0xd77e50 | 未読 |
| liveSelection | 0x151dc90 | 0xd783c0 | 1 | `ii` (a, b) | a → rec+0x18・b → rec+0x20 | 0xd78360 | 1 |
| selectionClear | 0x151dd70 | 0xd787b0 | 4 (NOARGS) | なし | なし | 0xd78750 | 1 |
| selectionSet | 0x151dd90 | 0xd78940 | 3 | `ii\|iii` kwlist (p1〜p5) | p1〜p5 → rec+0x18〜+0x38 (既定 0) | 0xd78880 | 1 |

- 全 5 件は先頭で `0xd78c80(self)` → engine object (`mov rbx, [rax]`) を取り、`0xd843d0(rbx, out, cb, aux, arg5..arg10, flag)` を呼ぶ (Win64 の 5 番目以降は stack)。
- 関数内の引数の並びは PyArg の varargs 順で、`selectionSet` の p1 は `[rbp+0xac]`、p5 は `[rbp+0x9c]` に入る (`0xd78a1a`〜`0xd78a51`)。

## 2. 共通経路 `0xd843d0` (レコードと戻り値)

- 引数: rcx = engine obj (`rbx`)・rdx = out (`rsi`)・r8 = コールバック (→ rec+0x58)・r9 = aux (→ rec+0x48、`0x4133f0` で複写)・arg5〜arg10 → rec+0x18〜+0x40 (`0xd8446b` 付近)・arg11 (byte) = flag (非 0 で `[slot 0x15e4...]` の関数を呼ぶ)。
- レコード `rec` = `0xd841e0(global, dl=1, obj)` の戻り値。`rec+0x60` はこの関数では書かず、コールバックが先頭で `-2` を書く (§3)。
- out: 初期値 `[out] = -2` (`0xd843e9`)。戻る前に `[out] = rec+0x60`・`[out+8] = rec+0x10`・`[out+0x10]` ← rec+0x50 の複写 (`0xd844d7`〜`0xd844d2`)。
- 実行: `0x526190(0, &{0xd84290, rec})` を呼ぶ。`0xd84290` が rec+0x58 を呼ぶと読めるが、この呼出しの同期性は**未確認**。
- 先頭の早期 return: `[obj+0x50] != 0` かつ `0xd84f30` が真なら効果を出さずに戻る (`0xd843f0`〜`0xd84403`)。`0xd84f30` の意味は**未同定**。
- 戻り値の変換 (None か int か) は本 REPORT の範囲外。`REPORT_PY152` の表 (None・int) を変えない。

## 3. ゲートと `0xd77e20`

- 5 件のコールバックは先頭で `rec+0x60 = -2` にし、`S = *(*(0x15e4790) + 8)`・`al = S->vtbl[0x98](S)` を呼ぶ (例: `0xd77e60`〜`0xd77e74`)。`al == 0` なら戻る (rec+0x60 は -2 のまま)。真なら `rec+0x60 = 0` にして効果を実行する。
- `0xd77e20()` (効果の対象 object を返す) は 2 経路:
  - `P = *(0x15e4558)`。`*P != 0` なら `*P` を返す。
  - `*P == 0` なら `*(*(0x15e35c8))` を返す (`0xd77e39`〜`0xd77e40`)。
  - 各経路の object の意味は**未同定**。addAutoTimeMarker のコールバック 0xd78130 は `*(0x15e35c8)` を直接読んで `0xe546a0` の第 1 引数にする (`0xd78196`〜`0xd7819d`)。
- ゲートの値は実行時の状態のため、PE からは真偽を決められない。mock と C は**真と仮定**する (`general.setRecPPQ` の REPORT_PY119_2977 と同じ扱い)。

## 4. 効果 (ゲート真の経路)

| コールバック | 呼出し (VA) | 引数 | 確定度 |
|---|---|---|---|
| selectionClear 0xd78750 | `0xe43d30(obj, -1, -1, 0, 1)` | start=-1・end=-1 | **確定** (引数)。`0xe43d30` の規則は下 |
| selectionSet 0xd78880 | `0xe43d30(obj, p1, p2, p3==1, p4==1)` | start=p1・end=p2 | **確定** (引数)。p5==1 のとき `0xe7e290(obj, p1, p2, xmm3)` も呼ぶ (未同定) |
| liveSelection 0xd78360 | `0xe43ff0(obj, a, b==1)` | a・b | 一部。`a == 0x7fffffff` なら `0xe43fa0(obj, 1)`。b≠0 かつ `anchor = [obj+0xd7c] ≥ 0` かつ `anchor ≠ a` のとき `0xe43d30(obj, anchor, a, 1, 1)`。それ以外の経路 (b=0 等) は**未読** |
| addAutoTimeMarker 0xd78130 | `0xe546a0(*(0x15e35c8), &name, &time, 1)` | name (std::string)・time | 一部。`time == 0x7fffffff` なら `0xe43fa0` で現在位置を使う経路。マーカーを追加する本体は**未同定** |
| jumpToMarker 0xd77e50 | `0x1180ef0(delta, select==1)` → `[rec+0x10] = eax` | delta・flag | **未同定** (`0x1180ef0` の本体を未読)。戻り値は out[1] |

### `0xe43d30` の書込み規則 (確定)

- 引数: rcx = obj・edx = x・r8d = y・r9d = flag (r13 に保存)。
- `[obj+0xd74] = x`・`[obj+0xd78] = y` を書く (`0xe43d63`〜`0xe43d69`)。
- `x == y` なら `[obj+0xd78] = -1` (`0xe43d77`〜`0xe43d79`)。
- `x > y` なら `[obj+0xd74]` と `[obj+0xd78]` を入れ替える (`0xe43d85`〜`0xe43db1`)。
- `[obj+0xd78]` の旧値が 0 以上なら `0xe4b3a0` を呼ぶ (`0xe43d52`〜`0xe43d5e`)。この呼出しの効果は**未同定**。mock と C は状態のみを扱う。
- 後段 (`[obj+0xc48]` を読む分岐・`0x11d47c0`) は**未読**。

`[obj+0xd74]` は `liveSelectionStart` (`0xd78500`) が読む値と同じ。`selectionStart`・`selectionEnd` (PY-96) も `+0xd74`・`+0xd78` を読む。

## 5. 引数個数・型・負値

- **jumpToMarker**: PE の書式 `i|i` (kwlist delta, select) は必須 1・上限 2。flapi 表 (`analysis/flapi/flapi_table.json`) と `provider/gen/fl_table.c` は `2, 2` で、mock と C はどちらも表に従い必須 2 にしている。
  - **表と mock/C は変えない**。理由: 表は `flapi_table.json` (MCP・kwsig 検査と共有する生成元) から作られる。個数の不一致は `REPORT_PY102.md` §3 の 23 件の一つで、PY-147 (#2927) は closed のまま残りを扱っていない。どちらに寄せるかは PM の判断。
- **liveSelectionStart** (`0xd78500`・flags 1): PyArg を呼ばず、引数を読まない。PE は任意の個数を受理する。表は `0, 0`、C は `NARGS(0, 0)`。`liveSelectionStart` の引数は表と C と mock の 0 個のままで、PE との差は §5 の PM 判断に含める。
- **int と bool**: `0xd78520` (currentTime) などの変換は `call [0x15e4280]` で、`0x15e4280` の先は `PyLong_FromLong` (REPORT_PY152 §変換スロット)。bool 戻りの `general.getUseMetronome` 等 (`REPORT_PY87`) も同じ slot。PE から見た Python 上の型は int。stub の bool とは一致しない。
- **負値**: 変換は `mov ecx, eax` (32 bit)。`-1` は Python の int `-1`。`selectionClear` が渡す `-1` は `0xe43d30` の end=-1 規則と同じ未選択の番兵。

## 6. 実装 (本 PR)

- `host/fl_mock.mjs`: `selSet(x, y)` を追加 (§4 の `0xe43d30` の規則)。`selectionClear` は `selSet(-1, -1)`、`selectionSet` は `selSet(a, b)` (p3〜p5 は検査のみ)。
- `provider/fl_engine.c`: `sel_set(x, y)` を追加し、同じ規則で `selectionClear`・`selectionSet` から呼ぶ。
- `tests/arrangement_diff.mjs`: 状態系列 5 手を追加。各手で setter を両エンジンに流し、`selectionStart`・`selectionEnd` の戻りを**規則からの期待値**と照合する (両エンジンの出力を比べるだけでは足りないため)。

系列 (期待値 = (start, end)): `selectionSet(3,1)` → (1,3)・`selectionSet(2,2)` → (2,-1)・`selectionSet(-1,4,true,false,0)` → (-1,4)・`selectionSet(5,-1)` → (-1,5)・`selectionClear()` → (-1,-1)。

仮置き (本 PR では未確定): 初期値 `sel_start = sel_end = -1` は PE の初期値を未実測 (PY-96 の仮置き)。ゲートは真と仮定。`0xe4b3a0` (旧範囲の後始末) は未モデル。

## 7. 検証

測定 commit: `62476e2ae` (コードを変えた最後の commit。`feat(python): arrangement の選択 2 件 ... (PY-144 #3043)`)。測定は同 commit の作業ツリー (`git status -- tools/python` 空) で行った。runner の load average は測定開始時 `uptime` で 0.47 (1 分)・1.00 (5 分)・0.60 (15 分)。

前提の生成物 (gitignore): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。`bash fetch_inputs.sh` (rc 0)、`bash build_cpython_wasm.sh` (rc 0、3 分 21 秒。`cpython-3.12.1.json` の notices 記録のみ)、`FLPY_SKIP_TABLE=1 bash build_flpy.sh` (rc 0)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0 | 0.82 秒 |
| `node tests/arrangement_diff.mjs` | calls 25、diffs 0、state 5、stateDiffs 0、PASS | 0.04 秒 |
| `node tests/arrangement_selection_diff.mjs` | calls 8、diffs 0、PASS | 0.04 秒 |
| `node tests/general_diff.mjs` | calls 41、diffs 0、PASS | 0.04 秒 |
| `node tests/ui_state_diff.mjs` | calls 58、diffs 0、PASS | 0.04 秒 |
| `node tests/ui_diff.mjs` | calls 17、diffs 0、範囲外既知差分 3、PASS | 0.04 秒 |
| `node tests/mixer_diff.mjs` | calls 69、diffs 0、PASS | 0.04 秒 |
| `node tests/provider_check.mjs` | PASS (functions 435 / implemented 165 / unimplemented 270 / mcp_static 60) | 0.29 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1 秒未満 |

ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の `selSet` の入れ替え (`x > y` の分岐) を外すと、`node tests/arrangement_diff.mjs` は `AssertionError [ERR_ASSERTION]: arrangement 状態差分 2 件` で rc 1 (FAIL)。元に戻すと calls 25・stateDiffs 0・PASS (rc 0)。

コード差分 (測定 commit から HEAD まで。`tools/python` の .md 以外):

```
$ git diff 62476e2ae HEAD -- tools/python ':!*.md'
(空)
```

## 8. 受入条件の対応

| 受入条件 (#3043) | 結果 |
|---|---|
| 1. 0xd843d0 とコールバック 5 件の副作用を VA 付きで確定し、0xd77e20 の object と `[0x15e4790]+0x98` のゲートを同定する | 経路・引数・ゲート・レコードは §1〜§4 で確定。0xd77e20 の 2 経路の object の意味と、マーカー・liveSelection・jumpToMarker の効果本体は未同定 (子 #3796 (PY-254)) |
| 2. 確定した副作用を mock の状態 (選択範囲・live selection・マーカー) に反映し、C と差分 0 | 選択範囲 (selectionSet・selectionClear) は反映し差分 0。live selection・マーカーは未反映 (子 #3796 (PY-254)) |
| 3. jumpToMarker の必須個数を確定する | PE は必須 1 (`i|i`) と確定。表・mock・C は 2 のまま (理由 §5。PM 判断) |
| 4. liveSelectionStart の引数個数を確定する | PE は任意の個数を受理と確定。表・mock・C は 0 のまま (理由 §5。PM 判断) |
| 5. 負値と bool 戻りの Python 型 | 負値 -1 は int -1、bool 戻りは PE 上 int (`PyLong_FromLong`) と確定。実機値は未実測 |

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| マーカー追加 (`0xe546a0`)・liveSelection の b=0 経路と anchor `+0xd7c` の設定元・jumpToMarker (`0x1180ef0`)・`0xe7e290`・`0xe4b3a0`・`0xd84f30`・`0xd77e20` の 2 経路の object の意味 | マーカー・liveSelection・jumpToMarker の 3 件が状態を変えない | 子 #3796 (PY-254) |
| jumpToMarker の個数 (PE 必須 1 / 表 2) と liveSelectionStart の個数 (PE 任意 / 表 0) | 表と mock/C が PE と不一致。`arrangement.jumpToMarker(1)` は code 5 になる | PM 判断 (PY-102 REPORT §3 の 23 件の一つ。PY-147 #2927 は closed) |
| bool 戻り 4 件の Python 型 (PE は int・stub は bool) | Python 上の `True` と `1` の区別が未確定。REPORT_PY87 の論点と同じ | PM 判断 (親 #2983・PY-87) |
| 初期値 `sel_start`・`sel_end` = -1 の実機値 | getter の既定値が仮置き | PY-96 (#2832) の残件 (REPORT_PY152 §前提の不一致と同じ) |
| ゲート `S->vtbl[0x98]` の実行時値 | 効果の有無が実機と異なる可能性 | 子 #3796 (PY-254) |
