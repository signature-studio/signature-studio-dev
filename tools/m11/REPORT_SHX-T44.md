# SHX-T44 (#4189): 入れ子手続 function_448490 の親フレーム site の機械語判定 (D23)

## 1. 結論

- 受入 1 (`function_448490` → `function_4483f0` の 8 site と `function_448430` の 2 site の機械語判定) を満たした。10 site すべてで、親が `mov rcx, rbp` で親フレームを静的リンクとして渡す。`function_4483f0` の 8 site は callee が親の `[rbp+0x48]` (IR `-32`・count)・`[rbp+0x4c]` (IR `-28`・loop 変数) を読み書きする。`function_448430` の 2 site は `[rbp+0x4c]` の読みと `[rbp+0x70]` のみで、`[rbp+0x48]` には触らない (§3)。
- 判定の結論は「通常の rbp 渡しではなく、親の局所を callee が書き換える入れ子手続の形」。ただし IR の親 `function_448490` は、この書き換えを親の SSA に戻さない。D23 の機構と整合する。
- 受入 2 (修復 pass の実装)・3 (OFF/ON 実測)・4 (D23 の「修復」列) は本 run では未実施。前回 `[SHX-T40]` (#3234) は修復 ON で hang・OOB となり既定 OFF のまま main にある (`tools/m11/REPORT_SHX-T40.md`)。修復の設計 (call 前後の同期) は別 issue `[SHX-T45]` #4459 に移す (§5)。
- 受入 4 のうち、D23 の修復列は未達のため更新しない (`docs/DEFECTS.md` は変えない)。

## 2. 測定条件

- 測定 commit: `319b01a80` (origin/main。baseline・site 判定はこの commit のコードで行った)。本 PR の差分は `tools/m11/REPORT_SHX-T44.md` と `tools/m11/frame_share/site_check.py` (解析スクリプトの追加のみ・既存のコードは変えない)。`git diff 319b01a80 HEAD -- tools/m11/ldfix tools/m11/frame_share/detect.py tools/m11/frame_share/classify.py tools/m11/m11_gen_ir2.sh` は 0 行。
- 素材: `fl-win64.tar.zst` の `extracted/block00031_PE.bin` (22,227,016 B)・`work-m11.tar.zst` (`tools/m11/work/`・gitignore)。`toolchain-emsdk` は runner 既存。`toolchain-retdec` は使わない (lift を再実行していない)。
- IR: `FL_WIN64_DIR=/tmp/opencode/fl bash tools/m11/m11_gen_ir2.sh` (52 s・`[gen_ir2] OK: work/boot_final.ll (490761 行)`)。`m11_build.sh` 25 s・`signature mismatch: 0, undefined symbol: 0`。
- baseline (既定 OFF・修復なし): `shimx_link/build.sh --trace --soft` 15 s・`mismatch=0 undefined=0 duplicate=0`。実 boot `run_trace.mjs` 0.49 s・`units_run=17`・`dllmain_done=true`・`total_calls=106`・`va_calls=2`・`icall_ok=24`・`icall_miss=1`。前回 REPORT_SHX-T28 §7 と一致。
- 負荷: 測定時の 1 分平均 load は 0.59〜0.95 (nproc 4)。

## 3. site 単位の判定 (受入 1)

検出器の出力 `frame_share/site_check.py` (機械語の線型 disasm・`detect.py` の `call_site_base` と `walk_callee` を流用)。

| call (VA) | callee | call 直前の引数設定 (機械語) | callee の rbp 基準アクセス (off:size:kind) |
|---|---|---|---|
| `0x448588` | `function_4483f0` | `mov rcx, rbp`・`movzx rdx, word [rax]` | `0x48:4:rmw`・`0x4c:4:load/rmw`・`0x70:8:load` |
| `0x4485c6` | `function_4483f0` | `mov rcx, rbp`・`mov dx, 0x6e` | 同上 |
| `0x44864a` | `function_448430` | `mov rcx, rbp`・`lea rdx, [rip+0x1ae]` | `0x4c:4:load/rmw`・`0x70:8:load` |
| `0x44865b` | `function_448430` | `mov rcx, rbp`・`lea rdx, [rip+0x1b1]` | 同上 |
| `0x448692` | `function_4483f0` | `mov rcx, rbp`・`movzx rdx, word [rdx+rax*2-2]` | `0x48:4:rmw`・`0x4c:4:load/rmw`・`0x70:8:load` |
| `0x4486ca` | `function_4483f0` | `mov rcx, rbp`・`mov edx, eax` | 同上 |
| `0x4486e0` | `function_4483f0` | `mov rcx, rbp`・`movzx rdx, word [rdx+rax*2-2]` | 同上 |
| `0x448708` | `function_4483f0` | `mov rcx, rbp`・`mov edx, eax` | 同上 |
| `0x448720` | `function_4483f0` | `mov rcx, rbp`・`mov dx, 0x3a` | 同上 |
| `0x44872c` | `function_4483f0` | `mov rcx, rbp`・`mov edx, eax` | 同上 |

- 第 2 引数 (rdx) は、文字・長さ・即値のいずれか。第 1 引数 (rcx) はすべて親の `rbp`。
- callee `function_4483f0` の先頭: `mov rbx, rcx` で親の `rbp` を保持し、`mov rcx, [rbx+0x70]` (親の引数 home) を `function_413760` へ渡す。続けて `[rbx+0x4c]` を符号拡張して書込み先の添字にし、`[rbx+0x4c]` と `[rbx+0x48]` を +1 する。
- `0x448578`・`0x448754` は `call` 命令で、`mov rcx, rbp` の渡しではないので本節の対象外。直前の引数設定は `0x448570` が `lea rcx, [rbp+0x38]`、`0x44874b` が `lea rcx, [rbp+0x30]` で、局所の番地を渡す。`0x44873f` の `mov edx, [rbp+0x4c]` は親の読みで、callee へ渡す形ではない。

## 4. 親 IR との突合 (判定の補足)

- 親の機械語: `0x4484d3` `mov dword [rbp+0x48], 1`・`0x4484e4` `mov dword [rbp+0x4c], 1` (初期化)。IR の親には `store i32 1` が `-32` (`%stack_var_-32.0.reg2mem`) の 1 本だけで、`-28` (`[rbp+0x4c]`) の初期 store は無い (REPORT_SHX-T28 §6 と一致)。
- 親 IR の `%stack_var_-104` は `alloca [6 x i64]` (48 B)。callee が触る `+0x70`・`+0x78` を覆わず、`function_4483f0` / `function_448430` の呼出しは `ptr nonnull %stack_var_-104` (48 B) を渡している。
- 親 IR で `-32` は `reg2mem` の SSA 分解で扱われ、callee の書込み (`+0x48` の +1) が親 IR の以降の読みに届かない。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 親フレームを callee の view に結線する修復 pass の実装 (`function_448490` の `-28` store の補完、`this` object の 120 B 拡幅、call 前後の count・length・arg1 の同期)。既定 OFF | unit 18 を越えられない (`VirtualAlloc(0x76910000)` の不発) | `[SHX-T45]` #4459 (親 #4123) |
| 修復 OFF/ON の before-after 実測 (`units_run ≥ 18`・`VirtualAlloc` 不発・`MessageBoxA` 不発・ネガコン) と、`docs/DEFECTS.md` D23 の「修復」列 | 修復の受入 | `[SHX-T45]` #4459 |
| `function_448430` 本体の機械語確認 (2 site)。本 REPORT は callee の読み先のみ確認 | 2 site の判定の裏付け | `[SHX-T45]` #4459 |
| 真の D23 かどうかの site 単位の確定 (IR 幅による分類は REPORT_SHX-T28 §10 で実施済み) | 修復範囲の決定 | `[SHX-T45]` #4459 |
