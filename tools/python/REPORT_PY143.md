# tools/python REPORT: PY-143 arrangement の文字列返し 2 件 (currentTimeHint・getMarkerName) の PE 確定と C provider 実装 (#3041, 親 #2983)

> 正本: `tools/python/REPORT_PY152.md` (PE 呼出し構造・PyArg 書式の表)。本付録は PY-143 の確定値と実測のみ。

## 結論

- `getMarkerName` (entry `0x151dc50`・fn `0xd78030`) と `currentTimeHint` (entry `0x151dcf0`・fn `0xd785a0`) の呼出し先を同定した。PE の本体は読めたが、時刻の BBT 分解 (`0x1312080`) の数式は未同定。
- mock と C に 2 件を実装し、`tests/arrangement_diff.mjs` は 39 呼出し・diffs 0・PASS。
- 未達: `FL_ENGINE=wasm tests/all_tools.mjs` 48/48 は未実行 (cpython wasm の生成物が無く、flpy 生成物 `work/midi.py` も無い。`tests/provider_check.mjs` は flpy 節で止まり PASS を確認できていない)。

## 手段

- 素材: `fl-win64.tar.zst` (素材) から `extracted/block00031_PE.bin` のみ `tar --zstd -xf` で展開 (3 秒)。`FL_WIN64_DIR=<展開先>` で `analysis/flapi/pe_disasm.py` を使った。`toolchain-emsdk` は runner 既存の emsdk (既定の `EMSDK_ENV`) を使った。
- 逆アセンブルと字面の読取りは手動 (`pe_disasm.py` と `va_read.py` 相当の一時スクリプト。リポジトリには入れていない)。

## 呼出し先の同定 (VA)

| 関数 | 呼出し | 同定 |
|---|---|---|
| getMarkerName fn `0xd78030` | `0xe53c90(obj, &out, index, 1)` | `0xe53c90` は thunk。`rcx = [obj+0xd84]`・`rdx = &out` のまま `0x1063810` を呼ぶ (r8/r9 は保存されず渡る) |
| getMarkerName の本体 `0x1063810` | 範囲外 (`index < 0` または `index >= 件数`) | `out` を `0x412d60` で空 (ポインタ 0) にして戻る。`0x414000` は null を空文字の静的領域に変換 → **戻り は空文字** (PE 上の根拠) |
| getMarkerName の本体 `0x1063810` | 範囲内 | 表 (要素 52 byte、`+8` が名前ポインタ、`+4` が型、`+0x18` が番号) から名前を作る。型名の結合 `0x662530` と 0 埋め は未読 |
| currentTimeHint fn `0xd785a0` | `0xe4b8b0(&out, mode, time, setRecPPB, isLength==1)` | `0xe4b8b0` は `r9` (setRecPPB) を保存せず捨てる。`isLength` の判定は `[rbp+0xc0]` (stack 5 番目) |
| `0xe4b8b0` | `0x1312080(mode, time, &bar, &beat, &a84, &a80, &a7c, 0)` | BBT 分解。`mode == 1` の経路と PPQ 源は未同定 (未解決) |
| `0xe4b8b0` | `isLength == 0` のとき bar と beat に +1 | 1 始まり。tick は +1 しない |
| `0xe4b8b0` | 文字列化 | `0x43a7e0` で bar を 10 進化、`0x65e0d0` で beat と tick を 0 埋め (幅は `0x1312080` の出力 `a80`・`a7c`。未同定)。最後に `0x414da0(out, 5, bar, ":", beat, ":", tick)` の 5 片連結 (リテラル `0xe4b9f8` = `:`) |

## 戻り値の書式 (PE の確定分)

- `currentTimeHint(mode, time[, setRecPPB[, isLength]])` → `"bar:beat:tick"`。`isLength == 1` のとき bar・beat は 0 始まり、それ以外は 1 始まり。`setRecPPB` は PE 上 `0xe4b8b0` で使われない (値に影響しない)。
- 幅: beat と tick は 0 埋め。幅の値 (`a80`・`a7c`) は未同定。
- `getMarkerName(index)` → str。範囲外は空文字 (PE 0x1063810 の範囲外経路)。範囲内の名前は表の中身 (addAutoTimeMarker の副作用) に依存し、未同定。

## 実装 (mock と C)

- `getMarkerName`: マーカー表を件数 0 の仮置きとし、常に空文字を返す (`addAutoTimeMarker` は副作用が未同定のため登録しない)。
- `currentTimeHint`: PPQ 96・4 拍子の仮置きで BBT を計算し `"bar:beat:tick"` を返す。0 埋めの幅は未確定のため付けない。`mode` と `setRecPPB` は検査のみ (PE の経路が未同定)。
- C 側 `provider/fl_engine.c` は `FL_H(arrangement, getMarkerName)`・`FL_H(arrangement, currentTimeHint)`。mock 側 `host/fl_mock.mjs` は同名の定義。

## 検証 (測定 commit `86700c19b`: main 取り込み後の merge commit。以前の測定 commit `bb215b83a` の値は取り込みで無効)

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` (emsdk 6.0.12 を新規に入れた) | rc 0・ハンドラ 170 (本 PR の 167 + main の PY-132 の 3) | 1.5 秒 |
| `node tests/arrangement_diff.mjs` | calls 39、diffs 0、PASS | 0.07 秒 |
| `node tests/general_diff.mjs` | calls 41、diffs 0、PASS | 0.05 秒 |
| `node tests/ui_browser_diff.mjs` | ok 8・bad 5・browserOp 3、diffs 0、PASS | 0.06 秒 |
| `node tests/*_diff.mjs` (21 本) | 全て PASS (diffs 0) | 合計 1 秒未満 |
| `node tests/provider_check.mjs` | 期待値を impl 170 / unimpl 265 に更新 (435 関数)。節 1・節 2 は PASS。節 3 以降は `work/midi.py` と flpy (cpython wasm) が無く未実行 | — |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 未実行 (cpython wasm と flpy 生成物が無い) | — |

- 測定後のコード差分: `git diff 86700c19b HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 行 (この REPORT の更新は文書のみ)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1312080` の BBT 分解 (PPQ 源・4/4 の確定・`mode == 1` の経路) | currentTimeHint の値が仮置き (4/4・PPQ 96) | #3041 (本 issue を Refs で残し次 run で再依頼) |
| 0 埋め幅 (`a80`・`a7c`) と `0x662530` (型名の結合) | 桁数・名前の末尾が未確定 | #3041 |
| `all_tools.mjs` 48/48・`provider_check.mjs` の PASS | 受入条件 3・4 未達 | #3041 |
