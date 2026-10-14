# 付録: icall #2231 (ICALL-67) — fatal RIP 群 B/C/D/E/G/H の引数由来と群 I の正体

> 親: #2198 (ICALL-63)。前付録: `REPORT_APPENDIX_2198.md` §2.3。本 run は受入条件 1〜3 の切り分けまで。
> 測定 commit: `slot_trace.c` の fatal 経路にレジスタダンプを足した変更 (本 PR)。

## 1. 結論

- **群 I (下位 12 bit `0x96f`) は harness 側の現象で確定**: 落ちている RIP は `missing_import` の `movaps [rsp],xmm6` (`slot_trace+0x296f`)。
  thunk は `rcx=0x40` (import index) で `missing_import` を `call rax` するため、`rsp` が 16 byte 整列していない状態で `movaps` が SIGSEGV する。
  この SIGSEGV は `fprintf` より前に起きるため `MISSING IMPORT` が出ない。guest の挙動ではない。
- **群 G・H・D は harness の synthetic 引数 (0 埋め heap・`0x5000xxxx` の heap ポインタ) に由来**と確認した。
- **群 C (`0x18103d494` fast-fail) は harness の `SLOT_ENC_INIT` 設定に依存**: `SLOT_ENC_INIT` なしでは stub 経路が `rc=0` で正常復帰、あり (`0x1813068d0` を cookie で敷く) では `int 0x29`。
  guest の不正とは断定しない。harness が敷いた暗号化 slot の値が fast-fail の条件になっている。
- **群 B・E は由来が harness 由来とは言えない**。faulting 値 (`0xa080`・`0x400`) は heap の `0x5000xxxx` でも 0 でもない。
  guest 内で計算・読込された値と見るのが妥当だが、値の起源はまだ追跡していない (未解決)。
- 受入条件 (1)(3) は部分達成。(2) は因果を実測で確認した。

## 2. 実測

### 2.1 測定条件

- 再現: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (baseline) / `SLOT_STUB_VA=1810806a0 SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (stub)。
- 所要: baseline 13.8 s real / user 11.3 s / sys 2.0 s。stub は修正後に時間を計測していない。
- load average: 1.37 (10:26 測定時)。
- 素材: `fl-win64`・`plugins-freshair`・`work-icall`・`work-liftlib` を展開。

### 2.2 集計 (clean rerun)

| 条件 | rc 内訳 | zero-fill VA 数 | 既知 12 hit |
|---|---|--:|--:|
| baseline | rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8 | 10 | 3/12 |
| stub 有効 | rc=0: 72, rc=124: 1, rc=95: 47, rc=97: 3, rc=98: 8 | 11 | 4/12 |

2198 の REPORT と一致する。`0x1813068d0` が stub 有効で新規 hit (2198 と同じ)。

注意: 同じ出力ファイルに対して実行を重ねると `F` 行が重複して 262 件になる (作業中の計数誤り)。本表は各 run を
クリーンに取り直した値のみ。

### 2.3 群ごとの確定結果 (baseline / stub)

| 群 | RIP | base / stub | fault | 引数の由来 (実測) |
|---|---|--:|---|---|
| B | `0x180c8b9c0` | 3 / 3 | SIGSEGV `0xa098` | `rcx=0xa080`。heap (`0x5000xxxx`) でも 0 でもない。guest 内で計算された値の可能性 (未追跡) |
| C | `0x18103d494` | 1 / 4 | `int 0x29` | 下記 §2.4 |
| D | `0x18106a3b4` | 2 / 2 | SIGSEGV (nil) | `ldmxcsr [rsp+8]`。`ecx=0x50001b80` (heap ポインタを MXCSR として渡している)。harness の heap 引数に由来 |
| E | `0x18105bd74` | 2 / 0 | SIGSEGV `0x400` | `rax=0x400`・`rcx=0x6000`。`0x400` は harness の heap サイズと一致するが、由来は未追跡 (未解決) |
| G | `0x180da6e99` | 2 / 2 | SIGSEGV `0x19a4` | `rax=0`・`rcx=0x50000010` (heap 引数 0)。`[rcx+0x10]` が 0 → harness 由来 |
| H | `0x180da6d0b` | 2 / 2 | SIGSEGV `0x8` | `rcx=0`・`rax=0x20`。`[rcx+0x10]` が 0 → harness 由来 |
| I | `0x55..96f` 形 | 9 / 9 | SIGSEGV (nil) | §2.5 (harness 側) |

群 A (`0x1810806a0`・stub で消える)・F (`0x18100ca79`) は 2198 の記録どおり。

### 2.4 群 C の因果

- 経路: `0x18103d37c` が `xor r10,[0x1813068d0]`・`ror r10,cl` で enc slot を復号し、結果 0 なら `0x18103d417` へ分岐して
  `call 0x18103d47c`。そこから `0x18103d494` の `int 0x29` に至る。
- 実測: stub 有効 (`SLOT_STUB_VA=1810806a0`) で `0x18103d42c` を単体実行した。
  - `SLOT_ENC_INIT` なし: `rc=0`・`STUB 2`・`DONE` (正常復帰)。
  - `SLOT_ENC_INIT=1`: `rc=95`・`fatal sig=11 rip=0x18103d494`。
- 結論: fast-fail の条件は harness が `0x1813068d0` 系の slot に cookie を敷くことである。
  guest の不正入力ではない。stub で `rax=0` を返すこと自体は正常経路に乗る。

### 2.5 群 I の正体

- 落ちる RIP の下位 12 bit `0x96f` は `missing_import` (`slot_trace+0x2962` から `+0x296f`) の `movaps [rsp],xmm6`。
- `make_thunk` は `mov ecx,idx; mov rax,missing_import; call rax` で入る。`call` は 16 byte 整列を崩すため、
  `sub rsp,0xa8` 後の `movaps` が整列違反で SIGSEGV する。
- 実測の register: `rcx=0x40` (import index)・`rsp` 整列違反。`fprintf` より前に落ちるので `MISSING IMPORT` が出ない。
- 2198 の仮説 (`movaps` 整列不一致) は確定。計測のノイズで、群 I の 9 件はすべてこれ。

## 3. 再現

```
bash tools/ott/native/build.sh
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
cp tools/icall/work/slot_trace_fatal.txt tools/icall/work/fatal_base.txt
SLOT_STUB_VA=1810806a0 SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
cp tools/icall/work/slot_trace_fatal.txt tools/icall/work/fatal_stub.txt
```

レジスタ確認 (本 PR で追加した stderr 行): `gcc -O1 -g -o tools/icall/work/slot_trace tools/icall/diff/slot_trace.c tools/ott/native/ms_call.S -lm`
後、`tools/icall/work/slot_trace "<SlateCore.core_64>" <fn_va>` の stderr に `regs` と `heap_args` が出る。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 群 B (`rcx=0xa080`)・群 E (`rax=0x400`) の faulting 値の起源 (guest 内で計算された値か) | 受入条件 1 (群 B・E の切り分け) | #2247 (ICALL-68) |
| 群 C の `SLOT_ENC_INIT` 依存が guest の意図か harness の artefact か | 受入条件 2 の解釈 | #2247 (ICALL-68) |
