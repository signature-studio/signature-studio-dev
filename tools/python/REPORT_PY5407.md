# PY-5407 (#5947・親 #4658): device repeat 系 2 関数の PE 意味論

前段: `tools/python/REPORT_PY390.md` (device の status 経路の作り方)・`REPORT_PY125.md` (dispatch `0xd843d0` の sync 経路)。
対象: `device.repeatMidiEvent` と `device.stopRepeatMidiEvent` (fl_table 356・360)。

## 1. VA 表 (PE 確定)

| 関数 | entry | fn (本体) | 書式 (kwsig) | 本体の流れ |
|---|---|---|---|---|
| repeatMidiEvent | 0x151d3c0 | 0xd762f0 | `O|ii` (eventData, delay=300, rate=300) | device を `0xd77da0` で取得 → `[rbx]` を assigned → 書式解析 `0x415610`→ dispatch `0xd843d0` (callback `0xd76190`) → `0xd82c20(status)` |
| stopRepeatMidiEvent | 0x151d3e0 | 0xd764a0 | 引数なし (flags 4) | device を `0xd77da0` で取得 → dispatch `0xd843d0` (callback `0xd76450`) → `0xd82c20(status)` |

## 2. dispatch callback の status 経路 (PE 確定)

- `0xd843d0` (dispatch) の入口で `*out = -2` (0xd843e9)。`[obj+0x50]` (assigned) の分岐は次の 3 通り (逆アセンブル実測・`tools/python/analysis/flapi/pe_disasm.py`):
  - **assigned が null**: `0xd843f0`〜`0xd843f7` で述語を飛ばし `0xd84409` の enqueue へ進む。callback は呼ばれ、`task+0x60` は callback が決める (`-7`、下記「assigned 無しの経路」)。
  - **assigned 非 null かつ述語 `0xd84f30` が真**: `0xd84409` の enqueue へ進む。callback は `task+0x60 = 0` で本体を実行する。
  - **assigned 非 null かつ述語が偽** (`0xd84403` の `je 0xd84500`): enqueue せず抜ける。`*out` は `-2` のまま。
- callback `0xd76190` (repeat) と `0xd76450` (stop) の先頭は `task+0x60 = -2`。述語 `0x11d1430` (= `vtbl(G→+8)[+0x88]()`、REPORT_PY73_APPENDIX_2817 §1) が真なら `task+0x60 = 0` にして本体を呼ぶ。偽なら `-2` のまま。
- **dispatch は `task+0x60` を `*out` へ写す** (0xd844d7〜0xd844db: `mov rax,[rbx+0x60]; mov [rsi],rax`)。REPORT_PY125 で「未確認 (推定)」だった点はこれで確定。
- 戻りは `0xd82c20(status)` (0 → "OK"、-2 → "Operation unsafe at current time"、-7 → "Device not assigned"、既定 "Unknown error")。
- 述語 `0x11d1430` の偽経路の status は `-2` (unsafe)。C/mock は述語を真と仮定する。

### assigned 無しの経路

callback の `[obj+0x50] == 0` で `task+0x60 = -7` (repeat は `0xd762c2`・stop は `0xd7648c`: `mov qword ptr [rbx+0x60], 0xfffffffffffffff9`)。`0xd82c20(-7)` → "Device not assigned" (fl_err code 7)。

- 実装判定: 「device 無し → -7」は、上の assigned null の経路 (dispatch が enqueue し callback が -7 を書く) と一致する。ただし callback 先頭の述語 `0x11d1430` が偽なら assigned null でも `-2` になる。`0x11d1430` は未確定で真と仮定している (§3・§6)。
- stop (`0xd76450`): 述語 `0x11d1430` が真 → `task+0x60 = 0` → assigned null なら `-7`、非 null なら vtbl `[+0x88]` を呼んで `task+0x60 = 0` のまま。
- repeat (`0xd76190`): 述語が偽なら `0xd762ca` へ抜けて `-2`。真なら assigned null で `0xd762c2` の `-7`。

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

## 5. 検証

測定 commit: `816f0bd36` (コードを変えた最後の commit。以降の commit は REPORT と DOC_MAP と merge のみ)。環境: Linux runner・emsdk latest・CPython 3.12.1 (`build_cpython_wasm.sh` → `build_flpy.sh`)。

| 検査 | 結果 (実測) |
|---|---|
| `bash provider/build.sh` | 警告・エラー 0 で `dist/flprov.{js,wasm}` 生成 |
| `node tests/device_diff.mjs` | `diffs: 0`・`PASS: true`・呼出し 21 件・送出 10 件・新規 repeat 系 6 件を含む (実行 18:53:53 〜 18:53:54) |
| `node tests/provider_check.mjs` | `functions: 435`・`implemented: 233`・`mcp_static: 60`・`PASS: true` (18:53:45 〜 18:53:46) |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | `total: 48`・`ok: 48`・`soft_error: 0`・`raised: 0`・`host_calls: 37425`・`callback_roundtrip: true` (18:53:48 〜 18:53:50) |
| `node tests/all_tools.mjs` (mock) | `total: 48`・`ok: 48`・`host_calls: 37425` (18:53:53 〜 18:53:55) |

load: 本 run は単独の runner 上で実行 (他ジョブとの併走なし)。CPython wasm build は 18:50:42 〜 18:53:27 (約 3 分)・`build_flpy.sh` は 18:53:36 〜 18:53:43。

測定 commit 以降のコード差分 (provider/host/tests): 0 byte。

```
$ git diff 816f0bd36 HEAD -- tools/python/provider tools/python/host tools/python/tests | wc -c
0
```

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 述語 `0x11d1430` の真偽 | 真と仮定 (device 系 handler と同じ仮定) | #2926 |
| repeat/stop の vtbl 先の効果・record の中身 (`0xd87a90` 先) | 状態を持たない | 親 #4658 の追跡 |
| `FlMidiMsg` の bridge 表現 (object 型) | eventData の型違いを wasm で検査できない (`Uint8Array` で代用) | 親 #4658 の追跡 |
| `tools/python/REPORT_PY5407.md` の VA 表の runtime 検証 (動的 run) | PE 静的確定のみ。動的 run は未実施 | 親 #4658 の追跡 |
