# REPORT 付録 PY-15 — 省略引数のホスト受け渡し方式と誤束縛 0 検証 (#653)

> 本体: [REPORT.md](REPORT.md) §16 の全文。250 行上限 (`docs/DOC_MAP.md` §1) のため分割移動 (内容は無変更で、節番号のみ §16 に統一)。


## 16. 省略引数のホスト受け渡し方式と誤束縛 0 検証 (PY-15, #653)

既知類型との関係 (DEFECTS.md): 該当なし (lift ではなく Python 側の引数束縛。「別の引数の既定値が入る」は本 run の誤束縛の定義)。
親: #81 (PY-9 b)。起点 HEAD: `8d883c3` (main)。検証版 HEAD: `39f42ba` (src/ は `53a013d` から不変、tests/ はこの HEAD で固定。以後の commit は REPORT のみ)。

### 方式の決定 (3 案の比較)
| 案 | 内容 | 判定 |
|---|---|---|
| センチネル | 省略を表す新タグを 16B スロット ABI に追加 | **不採用**。`flhost_lib.js` / `provider/fl_dispatch.c` / `fl_mock.mjs` / 実 FLEngine 側の 4 箇所を同時変更が要る。途中の省略を使う実呼出しが、本 run の MCPTools 20 箇所 (14 パターン) には 0 件 (下表) |
| 位置省略 (末尾のみ) | tuple を短くし、C 側 (`fl_dispatch.c` の `nmin ≤ argc ≤ np`) の既定値に任せる | **採用 (末尾)** |
| C 側既定値の静的特定 | 書式の既定値を binary から復元 | **不採用**。`PyArg_ParseTupleAndKeywords` の既定値は呼出し前の局所変数初期化で、静的に確定できない (#81 (a) の実機確認が必要) |

途中の省略 (既定値不明の引数を飛ばして後続を kw 指定) は `TypeError` (推測で埋めない)。

### 既定値の規則の変更 (誤束縛の原因)
旧 (main, PY-9 b): stubs の既定値を「同名」または「同位置の名前違い」から引き継いでいた。
- 名前違いの同位置 10 件は**別の引数の既定値**: 例 `channels.getChannelVolume` の `mode=False` → `useDb`、`mixer.getTrackVolume` の `mode=0` → `flag`、`general.saveUndo` の `update=True` → `updateHistory`、`device.forwardMIDICC` の `mode=1` → `forwardTo`。
- `midi.*` 10 種 (21 引数) と `'1 / 24'` (1 引数) は `eval` で `NameError` / 数値化。
- 新: 同名のみ引き継ぎ、単純リテラル (`ast.literal_eval` が通る値) のみ採用。`eval` 廃止。

§12 の旧記述「stubs 名が kwlist の別位置に現れる 3 関数 (`channels.soloChannel` / `plugins.getColor` / `plugins.getParamValueString`) は既定値を引き継がない」は**誤り** (訂正)。実装は同名なら位置によらず引き継いでおり、今回の変更で残ったのは「既定値不明の位置を飛ばす」規則だけ。`plugins.getColor` では旧 main が `useGlobalIndex` の既定値を `paramIndex` の位置へ入れて誤束縛していた (新は TypeError)。

### 計測 (全て本 run、`python3 --version` 3.14 / wasm 不要)
| 検査 | 結果 | 所要 |
|---|---|---|
| `tests/kwsig_bind_check.py` (新規) | functions 103 / cases **6122** (期待 tuple 1123 + TypeError 4999) / ok **6122** / misbind **0** / mismatch **0** → PASS | 0.09 秒 (load average 2.26 = CPython wasm ビルドと並行) |
| `tests/kwsig_bind_check.py --src <main の src>` (ネガコン) | ok 5995 / misbind **25** / mismatch **102** → **FAIL** (exit 1) | 同 |
| `tests/kwsig_check.py` (更新) | OK。旧 (stubs 署名のみ) との比較 224 件のうち同結果 208、差 16 件 (11 関数)。差はすべて上の規則変更 (a)〜(c) で説明済み | 0.09 秒 (同 load) |
| MCPTools の flapi kw 呼出し (`tests/mcp_kwcalls_extract.py` + `tests/mcp_kwcalls_bind.py`) | pyc (win64 `block25159_DATA.bin`, 100,674 B) から 20 箇所・**14 パターン**。新 bind で **14/14 PASS (rc=0)**、wall 0.03 秒 ×3。不合格 1 件を足すと (`--neg`) rc=1。途中の省略を要する呼出し **0**。**旧 main の src でも 14/14 PASS (rc=0)** = この 14 パターンは旧新を区別しない (区別は下の 6122 ケース) | 0.03 秒 (python3 3.14 / 3 回) |

- kwlist 関数の検証定義: misbind = 位置 j ≥ k の値が「その位置の kw 識別子 (値 200000+最初の位置)」でも「同名 stubs 既定値」でもない。mismatch = それ以外の不一致 (期待と違う例外・長さ・値)。
- 期待値は `flapi_table.json` の仕様 (kwlist・required・同名リテラル既定値) から `tests/kwsig_bind_check.py` 内で組む (`src/fl_api.py` の実装は見ない)。positional のみ (kw 0 個) は既存仕様どおり素通し。
- MCP 14 パターンは旧 main でも 14/14 PASS した。REPORT §12 旧記述の「旧 main は 13/14 (`plugins.getParamValueString` の `NameError`)」は、本 run の抽出形式 (positional 個数 = CALL の argc) と値検査付き判定では再現しなかった。旧計測の呼出し形式は不明で、**原因未確定**。起票先: #653 (PM コメント 2026-10-13 09:04Z で本 issue 追跡と記載済み)。

### 検証環境
- 実測 load average・秒は表の値。`tests/kwsig_bind_check.py` の並列 1 本、Python 3.14、`tools/python` の既存テスト (`kwsig_check.py`) と同一条件。
- `tests/mcp_kwcalls_extract.py` は `python3.12` (3.12 の pyc を読むため)。入力は `fl-win64.tar.zst` の `extracted/block25159_DATA.bin` (`tar --zstd -xf ... extracted/block25159_DATA.bin`、2.4 秒)。

### 追補 (PY-15 review 対応。検証 HEAD `39f42ba`)

**規則変更 (a)〜(c)**: `tests/kwsig_check.py` (8) の比較基準は PR 前の stubs 署名のみの bind。stubs 署名と kwlist がある 94 関数の「位置 k 個 + kw 1 個」224 件のうち、同結果 208・差 16 件 (11 関数)。差の規則:
- (a) 名前だけ違う同位置の既定値を引き継がない → 末尾は省略 (C 側の既定値)、途中は `TypeError`。対象 8 関数: channels.getChannelVolume / soloChannel / setChannelPitch, mixer.getTrackVolume / getEventIDName / automateEvent, general.saveUndo, device.forwardMIDICC。
- (b) 旧が位置をずらして誤束縛していた → 新は束縛せず `TypeError`。対象 2 関数: plugins.getColor (useGlobalIndex を paramIndex の位置へ)、plugins.getParamValueString (5 引数目を渡す)。
- (c) バイナリは 5 引数なので旧の 6 つ目 (useGlobalIndex の stubs 既定値) を渡さない。対象 1 関数: channels.getStepParam。
- 注 (基準の範囲): (a)〜(c) の対象は上の 224 件基準 (旧 bind が通った呼出しのみ)。6122 基準の拒否 19 件には、この 8 関数に入らない `device.linkToLastTweaked` (3 件: 位置 0〜2 + kw `eventID`) が含まれる。stubs の `global_link` (既定 `False`) が kwlist の `globalLink` (同位置・名前違い) に当たり (a) と同型。224 件基準から外れたのは、旧 bind 側で stubs 既定値 `midi.REC_None` を eval すると `NameError` になるため (`kwsig_check.py` (8) は旧が `ok` の呼出しだけを比べる)。

**挙動変更の内訳 (旧 = main `8d883c3` の fl_api.py、新 = 本 PR)**: `tests/kwsig_bind_check.py --dump` の全 6122 ケースを `tests/kwsig_behavior_diff.py` で比べた。値の表示は識別子 (位置引数 = 100000+i、kw = 200000+i)。再現: `python3 tests/kwsig_bind_check.py --src <main の src> --dump old.jsonl; python3 tests/kwsig_bind_check.py --dump new.jsonl; python3 tests/kwsig_behavior_diff.py old.jsonl new.jsonl` (2 回実行、出力のバイト一致)。

| 区分 | 件数 | 意味 |
|---|---|---|
| 同一 | 5995 | 旧新とも同じ結果 |
| NameError | 102 | 旧は `midi.*` 既定値の `eval` で NameError。新は 52 件が TypeError、50 件が値 (NameError 解消) |
| **拒否** | **19** | 旧は値を返し、新は TypeError (利用者影響) |
| 値変更 | 6 | 旧新とも値を返すが値が違う (旧は別の引数の既定値を入れていた) |
| 受理 | 0 | 旧 TypeError → 新で値 |

```
cases 6122
  同一: 5995
  NameError: 102
  拒否: 19
  値変更: 6
[拒否] 19 件
  channels.getChannelVolume pos=0 kw=['index', 'useGlobalIndex']: old=[200000, False, 200002] new=TypeError
  channels.getChannelVolume pos=1 kw=['useGlobalIndex']: old=[100000, False, 200002] new=TypeError
  channels.setChannelPitch pos=0 kw=['index', 'value', 'pickupMode']: old=[200000, 200001, 0, 200003, False] new=TypeError
  channels.setChannelPitch pos=0 kw=['index', 'value', 'pickupMode', 'useGlobalIndex']: old=[200000, 200001, 0, 200003, 200004] new=TypeError
  channels.setChannelPitch pos=1 kw=['value', 'pickupMode']: old=[100000, 200001, 0, 200003, False] new=TypeError
  channels.setChannelPitch pos=1 kw=['value', 'pickupMode', 'useGlobalIndex']: old=[100000, 200001, 0, 200003, 200004] new=TypeError
  channels.setChannelPitch pos=2 kw=['pickupMode']: old=[100000, 100001, 0, 200003, False] new=TypeError
  channels.setChannelPitch pos=2 kw=['pickupMode', 'useGlobalIndex']: old=[100000, 100001, 0, 200003, 200004] new=TypeError
  mixer.automateEvent pos=0 kw=['index', 'value', 'flags', 'res']: old=[200000, 200001, 200002, 0, 0, 200005] new=TypeError
  mixer.automateEvent pos=0 kw=['index', 'value', 'flags', 'isIncrement', 'res']: old=[200000, 200001, 200002, 0, 200004, 200005] new=TypeError
  mixer.automateEvent pos=1 kw=['value', 'flags', 'res']: old=[100000, 200001, 200002, 0, 0, 200005] new=TypeError
  mixer.automateEvent pos=1 kw=['value', 'flags', 'isIncrement', 'res']: old=[100000, 200001, 200002, 0, 200004, 200005] new=TypeError
  mixer.automateEvent pos=2 kw=['flags', 'res']: old=[100000, 100001, 200002, 0, 0, 200005] new=TypeError
  mixer.automateEvent pos=2 kw=['flags', 'isIncrement', 'res']: old=[100000, 100001, 200002, 0, 200004, 200005] new=TypeError
  mixer.automateEvent pos=3 kw=['res']: old=[100000, 100001, 100002, 0, 0, 200005] new=TypeError
  mixer.automateEvent pos=3 kw=['isIncrement', 'res']: old=[100000, 100001, 100002, 0, 200004, 200005] new=TypeError
  device.linkToLastTweaked pos=0 kw=['controlIndex', 'channel', 'eventID']: old=[200000, 200001, False, 200003] new=TypeError
  device.linkToLastTweaked pos=1 kw=['channel', 'eventID']: old=[100000, 200001, False, 200003] new=TypeError
  device.linkToLastTweaked pos=2 kw=['eventID']: old=[100000, 100001, False, 200003] new=TypeError
[値変更] 6 件
  channels.getChannelVolume pos=0 kw=['index']: old=[200000, False, False] new=[200000]
  mixer.getEventIDName pos=0 kw=['index']: old=[200000, 0] new=[200000]
  mixer.getTrackVolume pos=0 kw=['index']: old=[200000, 0] new=[200000]
  general.saveUndo pos=0 kw=['undoName', 'flags']: old=[200000, 200001, True] new=[200000, 200001]
  general.saveUndo pos=1 kw=['flags']: old=[100000, 200001, True] new=[100000, 200001]
  device.forwardMIDICC pos=0 kw=['message']: old=[200000, 1] new=[200000]
[受理] 0 件
```

- 訂正: 旧版の注記にあった `channels.soloChannel(1, useGlobalIndex=True)` は**挙動変更ではない**。旧 main でも `TypeError` (kwlist の `value` に既定値が無い)。実測で旧新とも同じ。`channels.getChannelVolume(1, useGlobalIndex=True)` は旧 `(1, False, True)` → 新 `TypeError` で、上の拒否 19 件に含まれる。
- 検証範囲外: kwlist なし関数 `channels.incEventValue` (`kwsig_bind_check.py` の対象は kwlist 103 関数のみ)。stubs 既定値 `1 / 24` (式) は旧 main が `eval` で採用していた。実測: `incEventValue(1, step=5)` は旧 `(1, 5, 0.041666666666666664)` → 新 `(1, 5)` (C 側の既定値に任せる)。`incEventValue(1, 2)` は旧新とも `(1, 2)`。

**ネガコン (不合格が exit 1 になること・実測)**

| 検査 | 入力 | 結果 | rc |
|---|---|---|---|
| `kwsig_bind_check.py` | `--src` に main の `fl_api.py` | misbind 25 / mismatch 102 → FAIL | 1 |
| `mcp_kwcalls_bind.py --neg` | 14 パターン + 不合格 1 件 `channels.getChannelVolume(1, useGlobalIndex=True)` | distinct 15: pass 14, fail 1 → FAIL | 1 |
| `mcp_kwcalls_bind.py` (値検査) | 1 件 `channels.getChannelVolume(pos=1, kw=[useGlobalIndex])` を main の src で実行 | 旧は値を返すが `NG slot 1 (useDb) = False is not a same-name stubs literal default` → FAIL | 1 |
| `mcp_kwcalls_bind.py` (本 PR) | 14 パターン | 14/14 PASS | 0 |

**wasm 回帰 (本 PR head。`fetch_inputs.sh`・`build_flpy.sh`・`provider/build.sh` を同一 worktree で実行)**
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2,324,302,252 B) を `tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開 (6.4 秒、`extracted/` 25,166 件)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。`$ARTIFACTS_DIR/toolchain-emsdk.tar.zst` は実在を確認したが展開せず、runner 既存の `[EMSDK]` (emcc 6.0.12) を使用。
- CPython 3.12.1 wasm: `build_cpython_wasm.sh` rc=0、4 分 07 秒 (native + wasm)。
- `fetch_inputs.sh` + `build_flpy.sh` + `provider/build.sh`: rc=0、8.9 秒。WARN は mac dylib 無し (既存の `midi_script_callbacks_in_binary` 27 件を引き継ぎ・既知)。ビルド後 `git status` に tracked の差分なし。
- `node tests/all_tools.mjs` (JS mock): 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true、rc=0、1.967 秒。
- `FL_ENGINE=wasm node tests/all_tools.mjs`: 48/48 ok、host_calls 37,425、rc=0、1.994 秒 (`FL_ENGINE=wasm` は `provider/` の C 実装 `fl_api_call` を使う経路)。
- `node tests/provider_check.mjs`: PASS (functions 435、implemented 60、unimplemented 375、rc=0、0.347 秒)。
- 計測時の load average: 0.67〜1.38 (`uptime`、4 vCPU)。n=1 (all_tools / provider_check)。
- `analysis/mcp/tool_coverage.json` (`all_tools.mjs` JS mock の生成物) は tracked 版 (host_calls 37,424) と一致しない。旧 main の src で同じ回帰を回すと 37,425 で、48 件の結果・api_calls は本 PR と全件一致 (差分 0)。tracked 版が main の既存コードより古いため、本 PR では更新せず差分を戻した (範囲外)。
- 未実行: `run_all.sh` 全体 (step 4 が `FL_MAC` / `FL_WIN` 固定パスを使うため。#630)、`browser_check.mjs` / `mcp_ui_check.mjs` / `midi_ui_check.mjs` (headless Chrome・Vite が要る)、`poc_mcp.mjs` / `midi_script.mjs` / `subinterp_probe.mjs` (本 PR の変更範囲外として未実行)。

**検証の組み込み**: `kwsig_bind_check.py` は `run_all.sh` の step 8b に接続 (wasm 不要、`python3 tests/kwsig_bind_check.py` が FAIL で止まる)。ただし `run_all.sh` は手動 E2E で `.github` の workflow からは呼ばれないため、`kwsig_bind_check.py` は **CI 未接続・手動実行**。`mcp_kwcalls_*.py` と `kwsig_behavior_diff.py` は手動 (`mcp_kwcalls_extract.py` は python3.12 と fl-win64 展開が要るため run_all に入れていない)。

**限界**: 期待値は stubs の同名既定値を正として組んでいる。C 側の実既定値との一致は未確認 (#81 (a) の実機確認)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 旧 main の 13/14 (§12 旧記述) の再現条件が不明 | 判定結果には影響しない (main も 14/14) | #653 (PM コメント 2026-10-13 09:04Z で追跡) |
| 省略引数の C 側既定値との一致 (実機) | 期待値は stubs 同名既定値を正とする | #81 (a) |
| kwlist なし `channels.incEventValue` の `1 / 24` 既定値の消失 | 検証範囲外。kwlist なし関数の省略時の値が変わる (上の追補) | #711 (PY-17) |
| provider の `None` と JS mock の `undefined` による省略の表し方の統一 | 本 PR は省略を短い tuple で渡す。provider・mock 側の扱いは未確認 | #712 (PY-18) |
| `run_all.sh` の `FL_MAC` / `FL_WIN` 固定パス | run_all 全体は本 run で未実行 | #630 (既存) |
| `tool_coverage.json` の tracked 版が main の既存コードの出力と不一致 (37,424 vs 37,425) | 生成物の更新漏れ。本 PR の変更とは無関係 (旧 main でも同じ出力) | #712 (PY-18) |
| `browser_check` / `mcp_ui_check` / `midi_ui_check` 未実行 | UI 側の影響は未検証 | #712 (PY-18) |

### 16-b. 本 PR head の wasm 回帰 (検証 HEAD `a92cd53`、node v22.23.3、4 vCPU)

§14 の wasm 数値 (`bdd2f7c`) は src が main 取り込みで変わったため、本 head で再計測した。`src/` は `53a013d` 以降不変で、`a70b4c8`→`a92cd53` は docs のみ。

| 手順 (直列・前景) | 結果 | rc | 所要 |
|---|---|---|---|
| `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR`) | `extracted/` 展開済み | 0 | 5.401 秒 |
| `fetch_inputs.sh` | 完了 (mac pkg なしのため win64 DATA から取得) | 0 | 0.282 秒 |
| `build_cpython_wasm.sh` | `python.wasm` 生成 | 0 | 4 分 03.8 秒 |
| `build_flpy.sh` | `flpy.wasm` 生成 | 0 | 7.037 秒 |
| `provider/build.sh` | `flprov.wasm` 生成 | 0 | 1.214 秒 |
| `tests/provider_check.mjs` | PASS (functions 435・implemented 60) | 0 | 0.924 秒 |
| `tests/all_tools.mjs` (JS mock) | 48/48 ok・host_calls 37,425・callback_roundtrip true | 0 | 3.194 秒 |
| `FL_ENGINE=wasm tests/all_tools.mjs` | 48/48 ok・host_calls 37,425・callback_roundtrip true | 0 | 3.277 秒 |
| `tests/kwsig_bind_check.py` | PASS (103 関数・6122 ケース、misbind 0・mismatch 0) | 0 | 0.238 秒 |
| `tests/mcp_kwcalls_bind.py` (`src` と `analysis/mcp` の calls.json を引数指定) | 14/14 PASS | 0 | — |
| 同 `--neg` (不合格 1 件を追加) | distinct 15: pass 14, fail 1 → FAIL | 1 | — |

- 実行後の `git status` は空 (`tool_coverage.json` の書き換えなし)。生成物 (`work/`・`dist/`) は gitignore 対象。
- 差分の手順は `run_all.sh` の step 1・2・5・9b を個別に実行したもの。`run_all.sh` 全体は step 4 の固定パス (#630) のため使えない。
- 範囲外 (未実行): `mcp_ui_check.mjs` / `midi_ui_check.mjs` (Vite が要る)、`browser_check.mjs`・`midi_script.mjs` 等の §14 記載分は本 head では再計測していない。
