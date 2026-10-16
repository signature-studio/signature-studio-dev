# PERF-P28 (#5403) の測定付録: 停止の経路 (§3f〜§3h を #3959 付録から分割移動)

停止原因の正本は `REPORT_APPENDIX_3959.md` §3i。本付録は前 run までの測定 (vtable 0 化の窓・memory.fill・calloc の dest) の全文。

## 3f. 子 #5403 の再測定と vtable の書き換え窓 (Node・同期・`fd_write` 書込み版と stub の両方)

測定 commit: `42fad4a17` (origin/main 取り込み後の HEAD)。`tools/perf/p15` は `545bec77b` から変更なし (`git diff 545bec77b 42fad4a17 -- tools/perf/p15` が 0 行)。素材 `work-m6-ott` の `ottl.wasm` (sha `e8fb06203811ff1f`) を展開し、`wasm2wat` → `instr_loops.py` → `wat2wasm` で計装した (wabt は npm で `/tmp/opencode/wabt` に一時導入・commit 外)。

| 測定 (HEAD `42fad4a17`) | 結果 |
|---|---|
| `node_init_sweep.mjs --m 145,146 --timeout 15000` (計装なし) ×1 | M=145 ok (setup 796 ms)・M=146 timeout。前 run と同じ |
| `ctor_loop_trace.mjs 145` (計装) ×1 | 完走 (`completed: 145`)。wall 2.8 s |
| `ctor_loop_trace.mjs 146` (計装) ×3 | 3/3 `unreachable`。loop 170 = 399,163,510 回 (99.09%)。前 run と同値 |
| `PERF_FD_WRITE=1 ctor_loop_trace.mjs 146` ×3 | 3/3 `Error: abort`。loop 170 = 2 回。`fd_text` は前 run と同じ |
| `ctor_vtable_ring.mjs` (`instr_ring.py` で計装) ×3 | 3/3 同じ。ctor 146 の関数入り 418 回のうち、vtable (`0x30203BD0`) 先頭語が 0 と最初に観測されるのは entry 305 (func 23 の入口)。直前 12 entry は `123,122,23,75,119,123,122,23,75,119,123,122,23` |

分かったこと:
- ctor 146 の前、vtable `0x30203BD0` (`slot(145).obj` の vptr の指し先) は `3011de10 00000000 30127800 ...` (16 words) で、146 の trap 時には 16 words すべて 0。書換えは ctor 146 の内部で起きる。
- 最初の 0 の観測は func 23 の入口。直前に走った関数は func 123 → func 122 (`memory.size << 16` の leaf、func 123 から `call 122` で呼ばれる) → func 23 の順。func 123 は `call 122` の後に heap 上端 (`269004816`) を動かす割り当て関数で、`call 4` (`emscripten_resize_heap` の stub) を含む。書換えそのものは func 123 の本体 (`call 122` の後) か、その後の stub 呼び出しの前後のどこかに絞られる。書込みの store は未特定。
- したがって「壊れた vtable を書いた store」は、func 123 の `call 122` 後から func 23 入口の間に限られる。これは §3e の「heap が data 領域に届いた後で vtable が壊れる」仮説と整合するが、store そのものを記録したわけではない。

再現コマンド (素材展開後):

```sh
wasm2wat tools/ott/work/lift/ottl.wasm -o tools/ott/work/lift/ottl.wat
python3 tools/perf/p15/instr_ring.py tools/ott/work/lift/ottl.wat tools/ott/work/lift/ottl_rc.wat
wat2wasm tools/ott/work/lift/ottl_rc.wat -o tools/ott/work/lift/ottl_rc.wasm
node tools/perf/p15/ctor_vtable_ring.mjs tools/ott/work/lift/ottl_rc.wasm
```

## 3g. 子 #5403 (PERF-P28) の書込み store の特定 (Node・同期・`fd_write` stub 下)

測定 commit: `195ee191f` (`instr_fill.py` と `ctor_fill_watch.mjs` を追加した commit。`tools/perf/p15` の既存ファイルは §3f の `42fad4a17` から変更なし)。素材 `work-m6-ott` の `ottl.wasm` (sha `e8fb06203811ff1f`) を `tools/ott/work/lift/` に置き、`wasm2wat` → `instr_fill.py` → `wat2wasm` で計装した (wabt は npm で `/tmp/opencode/wabt` に一時導入・commit 外)。

| 測定 (HEAD `195ee191f`) | 結果 |
|---|---|
| `instr_calls.py` + `ctor_call_window.mjs` ×1 | 0 を最初に観測した call 戻りは site 133 (`f23->f75`)。直前の site 368 (`f75->f119`) の戻りでは非 0 |
| `instr_fill.py` + `ctor_fill_watch.mjs` ×3 | 3/3 同一。146 の ctor の中で vtable 範囲に重なる `memory.fill` が 1 回: dest `0x301d3e40`・n `262144`・範囲 `[0x301d3e40, 0x30213e40)`。vtable `0x30203BD0` は範囲内 offset `0x2FD90`。trap 時 `vt_head` = 0 |
| `ctor_fill_watch.mjs` (記録を ctor 1 から開始) ×1 | 同じ 1 回。145 以前の ctor で同じ範囲の重なりは無い |

分かったこと:
- 計装した store のうち vtable 範囲を覆うのは、wasm func 75 の `memory.fill` 1 箇所 (wat の 71184 行・dest は `local.get 1` (f75 の 2 番目の引数)・val 0・n 262144)。vtable 先頭語を 0 にしたのはこの fill と読める。`ctor_call_window` で見た「`f23->f75` の call 戻り」の直後・f75 本体の中の位置と一致する (`call 119` の後〜fill)。直接の `i32.store` などは未監視のため、この fill が唯一の書込みとは言えない。
- §3f の「store が特定できない」は、計装済みの範囲では `memory.fill` 1 箇所まで絞れた。dest `0x301d3e40` を与える呼び出し元の引数の由来 (`f23` の `call 75` のどの値か) は未確定。
- 3 run の同一性は §3f と同じく計装版の 3 run で確認した。
- **訂正 (本 §3h)**: §3g の「dest は `f75` の 2 番目の引数 (`local.get 1`)」は誤読だった。`f75` は引数を取らず (type 5: `() -> ()`)、`local 1` は `malloc` の戻り値 (`f119` = dlmalloc の `malloc`)。サイズ `max(i64.load 0x1008d070, 1)` = 262144 を `malloc` し、その領域を 0 埋めする calloc 形。dest は heap 側の確保結果である。

未確定:
- dest `0x301d3e40` が f75 の引数としてどう決まるか (`f23` の `call 75` の引数の計算)。
- 計装版は `memory.fill` 1 箇所だけを監視する。vtable 範囲への他の store は見ていない (直接 store を含む全 store の監視は未実装)。
- Chrome (AudioWorklet) で同じ fill が起きるかは未確認。

## 3h. 子 #5403 (PERF-P28) の dest の由来 (Node・同期・`fd_write` stub 下)

測定 commit: `7156a4b3e` (計装 3 ファイルを追加した commit。`tools/perf/p15` の既存ファイルは §3g の `195ee191f` から変更なし)。計装は `tools/perf/p15/instr_calloc.py` (func 75 の `memory.fill` 直前で dest を記録する)、harness は `tools/perf/p15/ctor_calloc_image.mjs`。素材 `work-m6-ott` の `ottl.wasm` (sha `e8fb06203811ff1f`) を `wasm2wat` → 計装 → `wat2wasm` で作った (wabt は `/tmp/opencode/wabt` に一時導入・commit 外)。

| 測定 | 結果 |
|---|---|
| `ctor_calloc_image.mjs` (計装 wasm) ×3 | 3/3 同一。`image_calloc` は ctor 146 の中だけに 10 件: `0x30013dc0`・`0x30053dc8`・`0x30093dd0`・`0x300d3dd8`・`0x30113e28`・`0x30153e30`・`0x30193e38`・`0x301d3e40`・`0x30213e48`・`0x30253e50`。`0x301d3e40` は 8 番目 (vtable `0x30203BD0` を含む 262144 B の領域を覆う) |
| `ctor_fill_watch.mjs` (§3g の計装) ×2 | 2/2 同じ。146 の dest `0x301d3e40`・n `262144`・`vt_head` = 0 |

分かったこと:
- 146 回目の ctor の中で、func 75 の calloc が guest image の範囲 (`0x30000000`〜`0x30284124`) を指す領域を 10 回返す。145 回以前の ctor では image 内の calloc は 0 件。
- 返る領域は `0x40000` (262144 B) ずつ進み、image の data 領域 (`0x301e2000`〜`0x30284124`) の内側に入る。heap が image の上に伸びて、image の領域を再利用する形と読める。
- ここで heap 先頭を直接読む計測は行わなかった。ctor の前後で `malloc` を呼ぶと割り当て順が変わり、dest が変わるため (§3h の検証で確認)。heap 先頭の値は未測定。

未確定:
- heap が image に届く機構 (heap 先頭が image 基底の何 B 手前まで伸びていたか) は未測定。
- 145 回目までの ctor で heap が image に届かない理由、146 回目でだけ届く理由は未確定。
- 「image の領域を calloc が返し、そこに vtable がある」ことが停止の原因かは、停止後の再現 (vtable を別の場所に置く等) で確かめていない。

