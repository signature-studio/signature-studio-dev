# PY-5407 (#5947・親 #4658): device repeat 系 2 関数の PE 意味論

前段: `tools/python/REPORT_PY390.md` (device の status 経路の作り方)・`REPORT_PY125.md` (dispatch `0xd843d0` の sync 経路)。
対象: `device.repeatMidiEvent` と `device.stopRepeatMidiEvent` (fl_table 356・360)。

## 1. VA 表 (PE 確定)

| 関数 | entry | fn (本体) | 書式 (kwsig) | 本体の流れ |
|---|---|---|---|---|
| repeatMidiEvent | 0x151d3c0 | 0xd762f0 | `O|ii` (eventData, delay=300, rate=300) | device を `0xd77da0` で取得 → `[rbx]` を assigned → 書式解析 `0x415610`→ dispatch `0xd843d0` (callback `0xd76190`) → `0xd82c20(status)` |
| stopRepeatMidiEvent | 0x151d3e0 | 0xd764a0 | 引数なし (flags 4) | device を `0xd77da0` で取得 → dispatch `0xd843d0` (callback `0xd76450`) → `0xd82c20(status)` |

## 2. dispatch callback の status 経路 (PE 確定)

- `0xd843d0` (dispatch) の入口で `*out = -2` (0xd843e9)。`[obj+0x50]` (assigned) が非 null なら述語 `0xd84f30` を見る (0xd843f9〜0xd84403)。偽なら分岐して `*out` は `-2` のまま。
- callback `0xd76190` (repeat) と `0xd76450` (stop) の先頭は `task+0x60 = -2`。述語 `0x11d1430` (= `vtbl(G→+8)[+0x88]()`、REPORT_PY73_APPENDIX_2817 §1) が真なら `task+0x60 = 0` にして本体を呼ぶ。偽なら `-2` のまま。
- **dispatch は `task+0x60` を `*out` へ写す** (0xd844d7〜0xd844db: `mov rax,[rbx+0x60]; mov [rsi],rax`)。REPORT_PY125 で「未確認 (推定)」だった点はこれで確定。
- 戻りは `0xd82c20(status)` (0 → "OK"、-2 → "Operation unsafe at current time"、-7 → "Device not assigned"、既定 "Unknown error")。
- 述語 `0x11d1430` の偽経路の status は `-2` (unsafe)。C/mock は述語を真と仮定する。

### assigned 無しの経路

callback の `[obj+0x50] == 0` で `task+0x60 = -7` (0xd762c2 / 0xd76450 の `0xd7648c`)。`0xd82c20(-7)` → "Device not assigned" (fl_err code 7)。

## 3. 未確定 (仮置き)

| 項目 | 仮置き | 追跡 |
|---|---|---|
| 述語 `0x11d1430` の真偽 | 真と仮定 (device 系 handler と同じ仮定) | REPORT_PY73_APPENDIX_2817・#2926 |
| repeat の vtbl 先 `[assigned+0x90]` (= `0xd762f0` の callback 内 `call [rbx+0x90]`) の効果 | 状態を持たない (記録しない) | 未読 |
| stop の vtbl 先 `[assigned+0x88]` の効果 | 状態を持たない | 未読 |
| `0xd87a90(assigned, [job+0x18])` の中身 (repeat の record) | 未読・効果は仮置き | 未読 |
| `eventData` (FlMidiMsg) の object 型検査 | 未検査 (wasm bridge は object を運べない: fl_provider.mjs は bytes/scalar/__cb のみ) | 本 PR の未解決 |

## 4. 実装

- `provider/fl_engine.c`: `h_device_repeatMidiEvent` (NARGS 1〜3・device 無しは -7)・`h_device_stopRepeatMidiEvent` (NARGS 0・device 無しは -7)。
- `host/fl_mock.mjs`: 同じ判定順 (arity → -7)。
- `tests/device_diff.mjs`: 6 件 (device 有無 × 引数個数)。`eventData` は `Uint8Array` で代用 (上記 §3)。
- `tests/provider_expect/py5407.json`: 2 関数を登録。

## 5. 検証 (commit は本 PR の HEAD)

| 検査 | 結果 |
|---|---|
| `bash provider/build.sh` | 警告・エラー 0 で `dist/flprov.{js,wasm}` 生成 |
| `node tests/device_diff.mjs` | `diffs: 0`・`PASS: true` (呼出し 21 件・送出 10 件・新規 6 件を含む) |
| `node tests/provider_check.mjs` | 未実施 (`dist/flpy.js` (CPython wasm) が必要。下記) |
| `FL_ENGINE=wasm tests/all_tools.mjs` (48/48) | 未実施 (同上) |

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `dist/flpy.js` (CPython wasm) の build と `provider_check`・`all_tools` 48/48 の実測 | 受入条件の 2 項目が未検証 | 本 PR で実施 (下記の結果を追記) |
| 述語 `0x11d1430` の真偽 | 真と仮定 | #2926 |
| repeat/stop の vtbl 先の効果・record の中身 | 状態を持たない | 親 #4658 の追跡 |
| `FlMidiMsg` の bridge 表現 (object 型) | eventData の型違いを wasm で検査できない | 親 #4658 の追跡 |
