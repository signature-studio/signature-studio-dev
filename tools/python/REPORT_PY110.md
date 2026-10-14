# PY-110 (#2927): flapi 表の引数個数を FLEngine 書式 (kwsig) に合わせ、不一致 24 件を 0 件にする

親: #2883。関連: #2027 (PY-102・`playlist.muteTrackLock`)・#1527 (PY-39 系・生成器の方式案の提案元)。子: #2950 (PY-115)・#2952 (PY-116)。
既知類型との関係: lift 作業ではない。`tools/python/REPORT_PY70.md` §6 と同系統の生成器の個数誤り (類型の行案は §8)。

## 結論

- 表 (`analysis/flapi/flapi_table.json`) の `sig.params` の個数と FLEngine の書式 (`kwsig` の required/max) の不一致は、作業起点 `aa676107` で **24 件**。本 commit では **0 件**。issue 本文の 23 件は `screen.addTextLine` を除いた数だった。
- 生成器 `analysis/flapi_table.py` の `pe_arity` が、個数の違う関数の params を PE の個数で作り直す。名前は kwlist (バイナリ由来)、無ければ stub の同位置か `arg{i}`。既定値が不明な省略可能位置は `PE_OPTIONAL` (リテラルでない印。Python 側の bind は C 側の既定値に任せる)。
- C の個数検査 (`provider/fl_dispatch.c`: `argc < nmin || argc > np` → code 5) が PE と一致した。実装済み 4 関数の、PE が受け付ける個数の呼出しが code 5 にならない (`tests/sig_arity_probe.mjs`: 対象 24・実装あり 4・違反 0)。
- 追加された引数は C 側も mock も読まない (値を変えても結果が変わらない)。その意味論の実装は子 #2950 へ移した。

## 測定

- 測定 commit: `46f5a007` (コード変更の最後の commit)。以下の数値は全てこの commit の内容で測った。
- 差分 0 の証跡: 本 REPORT の commit で増えたのは `tools/python/REPORT_PY110.md` と `docs/DOC_MAP.md` だけ。`git diff 46f5a007 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行。
- 環境: GitHub Actions runner (4 コア)。測定中の load average (`uptime`) は 0.46 / 0.94 / 0.72 (1 / 5 / 15 分)。
- 素材: fl-win64 ([WIN64]) は DATA block 5 本だけを `tar --zstd -xf` で展開 (2.9 s)。emsdk は [EMSDK] の既設を使い、展開はしていない。stub は `tools/python/fetch_inputs.sh` で取得 (IL-Group/FL-Studio-API-Stubs, depth 1)。retdec は使わない。

## 1. 不一致 24 件と修正後の表

`sig` = 修正後の params の個数 (変更前 → 後)。書式は `flapi_kwargs.py` が wrapper の `PyArg_Parse*` 呼出しから復元したもの。

| 関数 | 個数 | 書式 | required/max | kwlist | 修正後の引数名 | C 実装 |
|---|---|---|---|---|---|---|
| `playlist.muteTrack` | 2 → 3 | `i\|ii` | 1/3 | あり | index, value, inGroup | 未実装 |
| `playlist.muteTrackLock` | 1 → 2 | `i\|i` | 1/2 | なし | index, arg1 | 未実装 |
| `playlist.selectTrack` | 1 → 2 | `i\|i` | 1/2 | なし | index, arg1 | 未実装 |
| `channels.getStepParam` | 6 → 5 | `iiii\|i` | 4/5 | あり | step, param, offset, startPos, padsStride | 未実装 |
| `channels.soloChannel` | 2 → 3 | `i\|ii` | 1/3 | あり | index, value, useGlobalIndex | 実装あり |
| `mixer.armTrack` | 1 → 2 | `i\|i` | 1/2 | あり | index, value | 未実装 |
| `mixer.enableTrack` | 1 → 2 | `i\|i` | 1/2 | あり | index, value | 未実装 |
| `mixer.getTrackName` | 1 → 2 | `i\|i` | 1/2 | あり | index, maxLen | 実装あり |
| `mixer.selectTrack` | 1 → 2 | `i\|i` | 1/2 | あり | index, value | 未実装 |
| `patterns.clonePattern` | 1 → 2 | `\|ii` | 0/2 | なし | index, arg1 | 未実装 |
| `device.midiOutMsg` | 4 → 5 | `i\|iiii` | 1/5 | なし | message, channel, data1, data2, arg4 | 実装あり |
| `screen.addMeter` | 0 → 5 | `iiii\|i` | 4/5 | なし | arg0〜arg4 | 未実装 |
| `screen.addTextLine` | 2 → 5 | `siiii` | 5/5 | なし | text, line, arg2, arg3, arg4 | 未実装 |
| `screen.animateText` | 0 → 1 | `i` | 1/1 | なし | arg0 | 未実装 |
| `screen.blank` | 0 → 2 | `ii` | 2/2 | なし | arg0, arg1 | 未実装 |
| `screen.drawRect` | 0 → 5 | `iiiii` | 5/5 | なし | arg0〜arg4 | 未実装 |
| `screen.drawText` | 0 → 6 | `isiiii` | 6/6 | なし | arg0〜arg5 | 未実装 |
| `screen.eraseRect` | 0 → 4 | `iiii` | 4/4 | なし | arg0〜arg3 | 未実装 |
| `screen.findTextLine` | 0 → 4 | `iiii` | 4/4 | なし | arg0〜arg3 | 未実装 |
| `screen.removeTextLine` | 0 → 2 | `i\|i` | 1/2 | なし | arg0, arg1 | 未実装 |
| `screen.setScreenActiveCounter` | 0 → 1 | `i` | 1/1 | なし | arg0 | 未実装 |
| `screen.unBlank` | 0 → 1 | `i` | 1/1 | なし | arg0 | 未実装 |
| `plugins.getColor` | 4 → 5 | `i\|iiii` | 1/5 | あり | index, slotIndex, flag, paramIndex, useGlobalIndex | 未実装 |
| `plugins.getParamValueString` | 5 → 4 | `ii\|ii` | 2/4 | あり | paramIndex, index, slotIndex, useGlobalIndex | 実装あり |

原因 (stub 側。`analysis/flapi_table.py` の `stub_sigs` が読んだ署名):
- `*args` の宣言で個数 0 になる: `screen.*` の 10 件 (stub は `def drawText(*args)` など)。
- 同名オーバロード: `device.midiOutMsg` は 3 定義あり、生成器は最後の定義 (4 個) を採る。PE は 5 個まで受理する。
- 並び・個数が PE と違う: `channels.soloChannel` (stub の 2 番目は `useGlobalIndex`、PE の 2 番目は `value`)、`plugins.getParamValueString` (stub の `pickupMode` は PE に無い)、`channels.getStepParam` (stub の 6 番目 `useGlobalIndex` は PE に無い)、`plugins.getColor` (PE の `paramIndex` が stub に無い)。
- 末尾の省略可能引数が stub に無い: `mixer.armTrack`・`mixer.selectTrack`・`playlist.muteTrackLock` 等。
- `screen.addTextLine`: stub は `(text: str, line: int, /)` の 2 個、PE 書式は `siiii` (必須 5)。PE 側の抽出が正しいかは未確認 (子 #2952)。

## 2. 生成器 `pe_arity` の規則

- 対象: stub の個数 ≠ `kwsig.max` の関数だけ (24 件)。個数は `kwsig.max`、必須数は `kwsig.required` (C の `nmin` は既定値 None の数)。
- 名前: kwlist があればその名前。無ければ stub の同位置の名前、それも無ければ `arg{i}`。
- 型と既定値: 同名の stub 引数からだけ引き継ぐ。省略可能で既定値が不明なら `PE_OPTIONAL`。
- 既存の消費側への影響: `src/fl_api.py` の `_stub_defaults` は非リテラルの既定値を捨てる (`_default_value` の ValueError)。`PE_OPTIONAL` もこの経路に入り、bind は C 側に既定値を任せる。`tests/kwsig_check.py` (b') の「midi. 以外の既定値は eval と同じ」検査は式でない印を対象から外した。`tests/mcp_kwcalls_bind.py` は `literal_eval` の例外を握るので影響なし (PASS)。

## 3. 引数個数の一致 (`analysis/flapi/sig_arity_check.py`)

```
before: 対象 273 件・一致 249・不一致 24   (aa676107 の表)
after : 対象 273 件・一致 273・不一致 0    (46f5a007 の表)
署名の引数個数が変わった関数: 24 件
```

## 4. 検証 (測定 commit `46f5a007` の内容)

| 検証 | 実行 | 結果 |
|---|---|---|
| 生成器の再現 (修正前) | 修正前の生成器で再生成 | 追跡中の表とバイト一致 (作業開始時) |
| 表の検査・ネガコン | `FL_WIN64_DIR=… bash tests/flapi_table_check.sh` | PASS。再生成 3 ファイル一致 (差分 0/3)・win_pair_verified 388 件・ネガコン 6/6 exit 2 (2.26 s) |
| provider ABI | `node tests/provider_check.mjs` | PASS (functions 435・implemented 79・unimplemented 356・mcp_static 60)、0.37 s |
| 全 tool (mock) | `node tests/all_tools.mjs` | 48/48 ok・host_calls 37,425・raised 0 (2.11 s) |
| 全 tool (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok・soft_error 0・raised 0 (2.12 s) |
| 個数検査 (新規) | `node tests/sig_arity_probe.mjs` | 対象 24・実装あり 4 (`channels.soloChannel`・`mixer.getTrackName`・`device.midiOutMsg`・`plugins.getParamValueString`)・違反 0 |
| 差分検査 | `device_diff.mjs`・`mixer_diff.mjs`・`channels_diff.mjs` | diffs 0 (calls 8・49・123)。PE max 個の呼出しを追加 |
| kwsig 照合 | `python3 tests/kwsig_check.py` | OK (比較 231 件・同結果 223・差 7 関数) |
| kwsig 束縛 | `python3 tests/kwsig_bind_check.py` | PASS (103 関数・6122 ケース・misbind 0・mismatch 0) |
| MCP kw 呼出し | `python3 tests/mcp_kwcalls_bind.py src <calls.json>` (calls は `work/` の MCPTools.pyc から抽出) | PASS (14 パターン)。`--neg` は FAIL (期待どおり) |
| 静的 wasm | `bash build_flpy_static.sh` → `FL_ENGINE=wasm node tests/static_check.mjs` | STATIC CHECK OK |
| ビルド | `build_cpython_wasm.sh` 247.6 s・`build_flpy.sh` 7.1 s・`provider/build.sh` 1.3 s | いずれも成功 |

## 5. ネガコン

- probe の負例: 旧 wasm (作業起点 `aa676107` の表から `provider/build.sh` で作った dist) に、新しい表の probe を当てると違反 7 件で rc 1。新しい wasm に戻すと PASS。
- 生成器の負例: 変更前の生成器の出力 (`aa676107` の表) は `sig_arity_check.py` で不一致 24 件。

## 6. 挙動の変化 (C 側の個数検査)

- 実装済み 4 関数: `channels.soloChannel` は 2 → 3 個 (3 個を受理)、`mixer.getTrackName` は 1 → 2 個、`device.midiOutMsg` は 4 → 5 個 (5 個を受理)、`plugins.getParamValueString` は 5 → 4 個 (5 個は code 5 になる。PE と同じ)。
- 未実装 20 関数: `fl_dispatch.c` は未実装を個数検査より先に判定するため、code 2 のまま変化なし。
- `kwsig_check.py` の旧 bind との比較: 差は 11 → 7 関数。`channels.getStepParam`・`channels.soloChannel`・`plugins.getColor`・`plugins.getParamValueString` は、基準の sig が PE に揃ったため差が消えた。期待集合と件数を更新。
- `midi.*` の既定値を持つ引数: 21 引数・20 関数 → 20 引数・19 関数 (`plugins.getParamValueString` の `pickupMode` が PE に無いため消えた)。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実装済み 4 関数の追加引数 (soloChannel の value・useGlobalIndex / getTrackName の maxLen / midiOutMsg の 5 個目 / getParamValueString の index・slotIndex・useGlobalIndex) は C・mock の両方で読まれない | 2 個目以降の値で結果が変わらない。個数違反は解消済み | #2950 (PY-115) |
| kwlist の無い関数の引数名 (`arg{i}`) と型が未確定 (`screen.*` 10 件・`screen.addTextLine`・`playlist.muteTrackLock`・`clonePattern` 等)。`screen.addTextLine` の PE 必須 5 個 (`siiii`) の抽出は未確認 | 名前付き kw は通らない。型検査が緩い | #2952 (PY-116) |
| `playlist.muteTrackLock` の `value` の実装 (#2027 の受入) | 未実装 (code 2)。名前は `arg1` のままなので、実装時に `value` へ直す | #2027 (PY-102) |

## 8. DEFECTS.md への行案 (報告のみ。DEFECTS.md は未編集)

- 類型 (候補): 引数個数の生成誤り (stub の個数 ≠ バイナリの受理個数)。症状: 正当な個数の呼出しが code 5 (TypeError)、または PE が拒否する個数が通る。根本原因: 生成器が stub 署名の個数を正とし、`*args` を 0 個、同名オーバロードの最後の定義を採った。観測: 24 件 (§1)。検出信号: `analysis/flapi/sig_arity_check.py` の不一致数。修復: `analysis/flapi_table.py` の `pe_arity` (kwsig の個数を正とする)。
