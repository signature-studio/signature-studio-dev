# 付録: icall #2198 (ICALL-63) — fatal RIP 群の切り分けと slot_trace の計上漏れ

> 親: #2170 (ICALL-61)。前付録: `REPORT_APPENDIX_2170.md`。本 run は受入条件 3 (fatal RIP の原因切り分け) のうち、
> 群ごとの命令・fault 種別の確定と、harness の計上漏れの修正まで。群の**引数由来の確定**は子 issue へ移管 (§4)。

## 1. 結論

- **計上漏れを修正**: `slot_trace` は fatal 時に `_exit(95)` するため、crash した関数の `ACC` 行が一切出力されていなかった
  (rc=95 の 47〜53 件すべて ACC 0)。fatal 経路で ACC を出力するよう修正した (`c2f52068`)。
  これにより、#2170 の「既知 12 の読出しは 3 件」は**正常終了した関数だけの数**だったと分かった。
- 修正後も既知 12 の hit 数はベースライン 3/12 のまま。stub 有効では 4/12 (`0x1813068d0` が新規)。
- fatal RIP の群は 9 種に分かれた (§2.3)。`0x295f` 形の host 側 9 件は**harness 自身の shim** (`k_HeapReAlloc`) で、guest の挙動ではない。
- 受入条件 3 (原因の確定) は**部分達成**。命令・fault 種別までは確定、引数の由来 (harness が渡す値か、guest 内の不正か) は未確定。

## 2. 実測

### 2.1 測定条件

- 測定 commit: `c2f52068` (変更は `tools/icall/diff/slot_trace.c` の fatal 経路に ACC 出力を足す 3 行のみ)。
- 再現: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (ベースライン) /
  `SLOT_STUB_VA=1810806a0 SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (stub 有効)。
- 所要: ベースライン 12.4 s (real) / user 11.0 s / sys 1.9 s。stub 有効は修正後に時間を計測していない (修正前の同条件 12.4 s real)。
- load average: 0.51 (測定時, 10:10)。
- 素材: `work-icall` (`tools/icall/work/`)・`plugins-freshair` (`fetch.sh` で `tools/targets/freshair/work/`)。

### 2.2 集計 (c2f52068)

| 条件 | rc 内訳 | zero-fill VA 数 | 既知 12 hit |
|---|---|--:|--:|
| ベースライン | rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8 | 10 | 3/12 |
| stub 有効 | rc=0: 72, rc=124: 1, rc=95: 47, rc=97: 3, rc=98: 8 | 11 | 4/12 |

修正前 (`fe6f0acc` 相当) は zero-fill 7 個・3/12 (ベースライン)。修正で増えた VA は `0x1813062e0` (ベースライン)・
`0x1813068d0`・`0x1813071c8`・`0x1813071d0` (stub) で、いずれも crash した関数からの読出し。

- 既知 12 のうち stub 有効で新規 hit の `0x1813068d0` は、`0x18103d37c` (rip `0x18103d3f3`、`xor r10,[0x1813068d0]` の復号式) から読まれる。
  `0x18103d37c` は `0x18103d424`・`0x18103d440` 経由で `0x18103d494` の fast-fail に至る (§2.3 の群 C)。

### 2.3 fatal RIP の群 (ベースライン rc=95 の 53 件 / stub 有効 47 件)

| 群 | RIP | ベース | stub | fault 種別 (addr) | 命令・由来 |
|---|---|--:|--:|---|---|
| A | `0x1810806a0` | 7 | 0 | SIGSEGV (nil) | `jmp rax` の thunk。`0x1810806a2` 以降は `int3` 埋め。stub で消える (#2148 の stub 対象) |
| B | `0x180c8b9c0` | 3 | 3 | SIGSEGV `0xa098` | `mov rax,[rcx+0x18]`。rcx 由来の不正ポインタを疑う (未確定) |
| C | `0x18103d494` | 1 | 4 | `int 0x29` | `__fastfail`。`IsProcessorFeaturePresent` 後の分岐で `ecx=5`。stub で 1 → 4 件に増える |
| D | `0x18106a3b4` | 2 | 2 | SIGSEGV (nil) | `ldmxcsr [rsp+8]`。`ecx` 由来の不正 MXCSR 値を疑う (未確定) |
| E | `0x18105bd74` | 2 | 0 | SIGSEGV `0x400` | `mov ecx,[rax]`、`rax=[rbp+0x30]=0x400`。引数の値を疑う (未確定) |
| F | `0x18100ca79` | 2 | 2 | `int 0x29` | `__fastfail` `ecx=2` 経路 |
| G | `0x180da6e99` | 2 | 2 | SIGSEGV `0x19a4` | `inc [rax+0x19a4]`。`rax=[rcx+0x10]` が 0 と推定 (未検証) |
| H | `0x180da6d0b` | 2 | 2 | SIGSEGV `0x8` | `mov rax,[rcx+0x8]`。`rcx=[rcx+0x10]` が 0 と推定 (未検証) |
| I | `0x55..96f` 形 | 9 | 9 | SIGSEGV (nil) | **harness 側**。`slot_trace+0x296f` は `missing_import` (未実装 import の fail-fast shim) の `movaps [rsp],xmm6` |
| その他 | 1 件ずつ | 残り | 残り | 各種 | 一覧は `tools/icall/work/fatal_base.txt`・`fatal_stub.txt` (gitignore) |

- 群 I は 9 件すべて下位 12 bit が `0x96f` で揃う (ASLR で基底だけが変わる)。下位 12 bit は `missing_import` 内の `movaps` (`slot_trace+0x296f`) と一致する。
  `missing_import` は未実装 import の fail-fast shim で、本来は `MISSING IMPORT` を出して `_exit(99)` する。
  ただし単独再現 (`1803b3fc0`) では stderr に `MISSING IMPORT` が出ず、fatal 行 (`sig=11`) だけが出た。
  よって「未実装 import の呼出し」は**未確認**の仮説。`movaps` の整列不一致による SIGSEGV と見るのが素直だが、基底との対応も未検証。
  guest 挙動ではなく harness 側の現象として扱う。
- 群 C・F は `int 0x29` (`__fastfail`)。guest 側の意図的な abort である。群 C はベースラインにも 1 件あり、stub 有効で 4 件に増える。
  stub で `0x1810806a0` の thunk が返り値 0 を返すと、後続の復号検査 (`0x18103d37c`) に進み、そこで fast-fail する、という経路が見える (因果は未確認)。
- 群 B・G・H・E は NULL・小さい整数のポインタからの読出しで、harness が渡す synthetic 引数 (0 埋めの heap) の影響が疑わしい。
  引数の由来は未確定 (§4)。

### 2.4 受入条件への影響

- 既知 12 の判定は、修正後の集計 (fatal 経路の ACC を含む) でベースライン 3/12・stub 有効 4/12。
  既知 12 の hit 増は stub 時の `0x1813068d0` のみで、`0x1813071c8`・`0x1813071d0`・`0x1813062e0` は既知 12 の外。
  #2170 の 3/12 は crash した関数の読出しを含まないため過小の可能性がある。ベースラインでは修正前後とも 3/12 のままで、差は zero-fill VA 数 (7 → 10) にのみ現れた。

## 3. 再現

```
bash tools/ott/native/build.sh
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
cp tools/icall/work/slot_trace_fatal.txt tools/icall/work/fatal_base.txt
SLOT_STUB_VA=1810806a0 SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
cp tools/icall/work/slot_trace_fatal.txt tools/icall/work/fatal_stub.txt
```

- 命令の確認: `objdump -d -M intel` で各 RIP の直前 8〜24 byte を見た。群 I は `slot_trace` 自身を `objdump` した。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 群 B・D・E・G・H の引数の由来 (harness の synthetic 引数か guest 内の不正か) の確定 | 受入条件 3 (原因の確定) | #2231 (ICALL-67) |
| 群 C (`0x18103d494` fast-fail) の因果: stub 返り値 0 → 復号検査 → fast-fail の経路 | 受入条件 3・2 (`0x1813068d0` の判定) | #2231 (ICALL-67) |
| 群 I (`missing_import` の `movaps`) の正体: `MISSING IMPORT` が出ない理由 | 計測のノイズ (9 件) | #2231 (ICALL-67) |
| 既知 12 の判定の残り (5 件 `0x1813068d0`〜`0x181306910` の読む表) | 受入条件 2 | #2224 (ICALL-64) |
