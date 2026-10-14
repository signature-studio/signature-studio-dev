# 付録: icall #2231 (ICALL-67) — fatal RIP 群 B/C/D/E/G/H の引数由来と群 I の正体

> 親: #2198 (ICALL-63)。前付録: `REPORT_APPENDIX_2198.md` §2.3。本 run は受入条件 1 の一部・2・3 の切り分けまで。
> 測定 commit: `4c59ce30` (`slot_trace.sh` の fatal 行抽出に `regs` / `heap_args` を追加。計測条件は不変)。
> 検証 HEAD と差分の証跡は §5。

## 1. 結論

- **群 I (下位 12 bit `0x96f`) は harness の thunk 経路の現象**: 落ちている RIP は `missing_import` の `movaps [rsp],xmm6` (`slot_trace+0x296f`)。
  落ちた時点の `rsp` は `…478` (16 で割ると余り 8)。`missing_import` の入口 `rsp` は 16 の倍数で、正規の `16n+8` からずれている。
  thunk 内の `push` ×2 と `sub 0xa8` は入口 `rsp` が `16n+8` なら整列するので、**原因は thunk に入る時点の呼出し元の `rsp` が整列していないこと**。
  呼出し元 (harness の entry か guest 内の call 元か) は未追跡。`fprintf` より前に落ちるため `MISSING IMPORT` が出ない。
- **群 D: 1 件は harness 引数 (heap 引数 0) を直接使っている**。入口 `0x18106a3b0` の行は `ecx=0x50000010` = heap 引数 0 そのもの。
  `mov [rsp+8],ecx` の後の `ldmxcsr [rsp+8]` で、MXCSR の予約ビット (bit 16–31) が立つ値のため #GP → SIGSEGV。
  もう 1 件 (入口 `0x18105c1cc`) の `ecx=0x50001b80` は heap 引数のどれとも一致せず、guest 内で得た値 (未追跡)。
- **群 G: 1 件は harness 引数を直接使い、fault の `rax=0` は読出し結果**。入口 `0x180da6e60` の行は `rcx=0x50000010` = heap 引数 0 そのもの。
  `mov rax,[rcx+0x10]` (`0x180da6e95`) の結果が 0 (0 埋め heap)。fault 番地 `0x19a4` は `rax=0` 基準のアクセス (命令 bytes が途中で切れており、disp の完全な確認は未了)。
  もう 1 件 (入口 `0x180ca2450`) は `rcx=0x50000370` で heap 域内の guest 計算値 (未追跡)。
- **群 H は harness 由来とは言えない (未追跡)**: `rcx=0` は heap 引数 (`0x50000010` 等) と一致しない。
  `mov rax,[rcx+0x8]` (`0x180da6d0b`) で `rcx=0` を読み、fault 番地 `0x8` = `rcx(0)+8` と一致。`rcx` を 0 にした経路は未追跡。
- **群 C (`0x18103d494` fast-fail) は harness の `SLOT_ENC_INIT` 設定に依存**: `SLOT_ENC_INIT` なしでは stub 経路が `rc=0` で正常復帰、あり (`0x1813068d0` を cookie で敷く) では `int 0x29`。
  guest の不正とは断定しない。harness が敷いた暗号化 slot の値が fast-fail の条件になっている。
- **群 B・E は harness 由来とは言えない**。faulting 値 (`rcx=0xa080`・`rax=0x400`) は heap 引数のどれとも一致しない。guest 内で計算・読込された値と見るのが妥当だが、起源は未追跡。
- 受入条件 (1) は部分達成 (D の 1 件・G の 1 件は heap 引数由来と確認、他は未追跡)。(2) は因果を実測で確認。(3) は達成。

## 2. 実測

### 2.1 測定条件

- 再現: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (baseline) / `SLOT_STUB_VA=1810806a0 SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (stub)。
- 検証 HEAD `071b1023` の worktree で、foreground・1 run ずつ実行。n=3 (各条件)。
  - baseline: real 12.15–12.17 s / user 10.96–10.98 s / sys 1.65–1.69 s。
  - stub: real 12.16–12.96 s / user 10.93–10.95 s / sys 1.71–1.73 s。
  - 各 run 開始直前の load average (1 分): 0.71–0.84。
- 時間は n=3 の min–max。同じ harness でも負荷で wall time は変わるため、時間は参考値。rc・件数は全 run で一致した (§2.2)。
- 素材: `plugins-freshair` (`Fresh Air.Win.zip` を `fetch.sh` で展開)・`work-icall`・`work-liftlib` を `$ARTIFACTS_DIR` から展開。`tools/ott/native/build.sh` は OK。

### 2.2 集計

| 条件 | rc 内訳 | zero-fill VA 数 | 既知 12 hit |
|---|---|--:|--:|
| baseline | rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8 | 10 | 3/12 |
| stub 有効 | rc=0: 73, rc=124: 1, rc=95: 47, rc=97: 2, rc=98: 8 | 11 | 4/12 |

- baseline は sweep 3 回すべて同じ内訳。
- stub の rc 内訳は 2 通りを観測: rc=0: 73 / rc=97: 2 (`18105bb90`・`18105bea0`) と、rc=0: 72 / rc=97: 3 (`18105bb90`・`18105bea0`・`18105d8ac`)。
  `18105d8ac` は run ごとに rc=0 と rc=97 の両方を観測した。揺れの原因は未特定 (§4)。
- `0x1813068d0` が stub 有効で新規 hit (2198 と同じ)。
- fatal 行の保存: `slot_trace_fatal.txt` に `fatal` / `regs` / `heap_args` の 3 種が入る (base: 53 件ずつ・stub: 47 件ずつ)。

### 2.3 群ごとの確定結果 (baseline / stub)

| 群 | RIP | base / stub | fault | 引数の由来 (実測) |
|---|---|--:|---|---|
| B | `0x180c8b9c0` | 3 / 3 | SIGSEGV `0xa098` | `mov rax,[rcx+0x18]`。`rcx=0xa080` (`0xa080+0x18=0xa098` と一致)。heap 引数と不一致。未追跡 |
| C | `0x18103d494` | 1 / 4 | `int 0x29` | §2.4 |
| D | `0x18106a3b4` | 2 / 2 | SIGSEGV (nil) | `ldmxcsr [rsp+8]` (`0x18106a3b4`)。入口 `0x18106a3b0` の行は `ecx=0x50000010` (heap 引数 0 直接)。入口 `0x18105c1cc` の行は `ecx=0x50001b80` (heap 引数と不一致・未追跡) |
| E | `0x18105bd74` | 2 / 0 | SIGSEGV `0x400` | `mov ecx,[rax]`。`rax=0x400`・`rcx=0x6000`。heap 引数と不一致。未追跡 |
| G | `0x180da6e99` | 2 / 2 | SIGSEGV `0x19a4` | `mov rax,[rcx+0x10]` (`0x180da6e95`) の結果が 0。入口 `0x180da6e60` の行は `rcx=0x50000010` (heap 引数 0 直接)。入口 `0x180ca2450` の行は `rcx=0x50000370` (未追跡) |
| H | `0x180da6d0b` | 2 / 2 | SIGSEGV `0x8` | `mov rax,[rcx+0x8]`。`rcx=0` (heap 引数と不一致)。未追跡 |
| I | `0x55..96f` 形 | 9 / 9 | SIGSEGV (nil) | §2.5 |

- 群 A (`0x1810806a0`・stub で消える)・F (`0x18100ca79`) は 2198 の記録どおり。
- 群 D の ldmxcsr: `0x50000010`・`0x50001b80` はどちらも bit 30 を持つ (MXCSR の予約ビット)。値が heap ポインタであることが #GP の原因と読める (推定。実測は fault のみ)。

### 2.4 群 C の因果

- 経路: `0x18103d37c` が `xor r10,[0x1813068d0]`・`ror r10,cl` で enc slot を復号し、結果 0 なら `0x18103d417` へ分岐して
  `call 0x18103d47c`。そこから `0x18103d494` の `int 0x29` に至る。
- 実測: stub 有効 (`SLOT_STUB_VA=1810806a0`) で `0x18103d42c` を単体実行した。
  - `SLOT_ENC_INIT` なし: `rc=0`・`STUB 2`・`DONE` (正常復帰)。
  - `SLOT_ENC_INIT=1`: `rc=95`・`fatal sig=11 rip=0x18103d494`。
- 結論: fast-fail の条件は harness が `0x1813068d0` 系の slot に cookie を敷くことである。guest の不正入力ではない。

### 2.5 群 I の正体

- 落ちる RIP の下位 12 bit `0x96f` は `missing_import` (`slot_trace+0x2962` から `+0x296f`) の `movaps [rsp],xmm6`。
- 実測 (9 件中の代表 `0x1803b3fc0`): fault 時 `rsp=0x7ffd1b012478` (`…478` = 16 で割ると余り 8)。
  thunk の `push` ×2 + `sub 0xa8` (計 0xb8) を戻すと入口 `rsp` は `…530` (16 の倍数) で、正規の `16n+8` からずれている。
- `make_thunk` は `mov ecx,idx; mov rax,missing_import; call rax` で入る。thunk 内の `push` ×2 と `sub 0xa8` は、入口 `rsp` が `16n+8` なら `movaps` で整列する。
  よって違反の原因は thunk に入る時点の呼出し元の `rsp` である (thunk 自体の押し込みは原因ではない)。
- 実測の register: `rcx=0x40` (import index)。`fprintf` より前に落ちるので `MISSING IMPORT` が出ない。
- 2198 の仮説 (`movaps` 整列不一致) は確定。計測のノイズではなく、9 件すべてこの経路 (`0x55..96f` 形 9 件)。

## 3. 再現

```
bash tools/ott/native/build.sh
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
cp tools/icall/work/slot_trace_fatal.txt tools/icall/work/fatal_base.txt
SLOT_STUB_VA=1810806a0 SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
cp tools/icall/work/slot_trace_fatal.txt tools/icall/work/fatal_stub.txt
```

- `fatal_*.txt` には `regs` / `heap_args` 行も入る (`slot_trace.sh` の抽出を `grep -E 'fatal|regs|heap_args'` に修正済み, `4c59ce30`)。
- 単体の register 確認: `gcc -O1 -g -o tools/icall/work/slot_trace tools/icall/diff/slot_trace.c tools/ott/native/ms_call.S -lm` の後、
  `tools/icall/work/slot_trace "<SlateCore.core_64>" <fn_va>` の stderr に `regs` と `heap_args` が出る。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 群 B (`rcx=0xa080`)・群 E (`rax=0x400`)・群 H (`rcx=0`) の faulting 値の起源 (guest 内で計算された値か) | 受入条件 1 (群 B・E・H の切り分け) | #2247 (ICALL-68) |
| 群 D (入口 `0x18105c1cc` 行の `ecx=0x50001b80`)・群 G (入口 `0x180ca2450` 行の `rcx=0x50000370`) の heap 域値の起源 | 受入条件 1 (群 D・G の残り) | #2247 (ICALL-68) |
| 群 I の thunk 呼出し元 (harness の entry か guest 内の call 元か) | 群 I の機構の上流 | #2247 (ICALL-68) |
| 群 C の `SLOT_ENC_INIT` 依存が guest の意図か harness の artefact か | 受入条件 2 の解釈 | #2247 (ICALL-68) |
| `18105d8ac` の stub 条件の rc が run 間で揺れる (rc=0 と rc=97 の両方を観測)。原因は未特定 | 付録 §2.2 の stub の rc 内訳 (73/2 と 72/3 の 2 通り) | 本 PR の未解決表のみ (追跡。子は起票しない) |

## 5. 検証

- 測定 commit: `4c59ce30` (`tools/icall/diff/slot_trace.sh` の fatal 抽出修正。`tools/icall/diff` の計測コードの最後の変更)。
- 検証 HEAD: `071b1023` (main 取り込み merge・競合解消後)。§2 の実測はこの HEAD の worktree で行った。
- `git diff 4c59ce30 071b1023 -- tools/icall/diff tools/ott` の出力:

  ```
   tools/icall/diff/slot_table_reach.py | 31 +++++++++++++++++++++++++++++++
   1 file changed, 31 insertions(+)
  ```

  測定対象 (`slot_trace.c`・`slot_trace.sh`・`tools/ott`) は差分 0。差分は main 取り込み由来の `slot_table_reach.py` の新規追加のみ。
- `slot_table_reach.py` は harness (`slot_trace.sh`・`slot_trace.c`) から呼ばれない (判定手順として `REPORT_APPENDIX_2197.md` から参照されるだけ)。
- `git diff 2c1c8121 071b1023 -- tools/icall/diff` は `slot_trace.sh` の 1 行 (抽出 grep の修正) と、main 由来の `slot_table_reach.py` の 31 行追加のみ。
