# liftdiff REPORT 付録: LD-57 (#1636) OTT 旧 chain 6 関数の命令単位 trace (native 側)

親 issue #1313 (LD-44) の残り。前提は `REPORT_APPENDIX_LD44.md` §5 と `REPORT_APPENDIX_LD16.md` §8.3。

## 結論

- 受入条件は**部分達成**。native 側の命令単位 trace (single-step) は 6 関数 × vm0/u16 で取得し、`callee_divergence` の分岐点を命令単位で示した。
- wasm 側の命令単位 trace は**未実装**。native と wasm の rip・レジスタ値の対応付けは未達 (子 issue に分割)。
- `1801c5e84` の分岐点: `1c0b6f` の `je` (`test rcx, rcx` の結果) が分かれ目。vm0 は `rcx=0` で早期 return、u16 は `rcx` に UTF-16 文字列データが入り `HeapFree` (IAT `1c0b82`) を呼ぶ。`HeapFree` 経路の真偽は wasm 側 trace が無いため未確定。

## 1. 測定条件

- 測定 commit: `3ff24dbc` (`tools/liftdiff/rt/ld_native.c` の single-step 追加。`git diff` は §5)。
- 測定 runner: 4 vCPU・メモリ 15 GiB。
- 素材: `fl-win64` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`plugins-ott` / `analysis-ott-binaries` (`PLUGINS_DIR=$HOME/analysis/plugins`)・`work-m11` / `work-liftdiff` (`tools/liftdiff/work/`)。
- 実行コマンド (1 関数 1 パターンずつ):
  `LD_STEP_N=20000 LD_STEP_OUT=work/ld57/<fn> python3 liftdiff.py run targets/ott_old.json --fn 0x<fn> --pattern <vm0|u16> --nobuild --notrace --json work/ld57/r_<fn>_<pat>.json`
- `ld_native` は commit 済みソースから `gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm` で再ビルドした。
- 生データ: `results/ld57/insn_<fn>_<pat>.txt` (1 行 1 命令: rva と rax,rcx,rdx,rbx,rsp,rbp,rsi,rdi,r8,r9 の 16 進)。

## 2. 命令単位 trace の取得結果 (native 側)

1 回の実行で 12 件を取得した。再現性は未確認 (同一条件の 2 回目は未実施)。

| 関数 | pattern | 命令数 | 先頭 rva |
|---|---|---|---|
| 1801ab1d0 | vm0 / u16 | 40 / 40 | 1ab1d0 |
| 1801ab258 | vm0 / u16 | 41 / 41 | 1ab258 |
| 1801c5e84 | vm0 | 74 | 1c5e84 |
| 1801c5e84 | u16 | 114 | 1c5e84 |
| 1801c621c | vm0 / u16 | 998 / 1048 | 1c621c |
| 1801c682c | vm0 / u16 | 112 / 115 | 1c682c |
| 1801c69cc | vm0 / u16 | 1028 / 1078 | 1c69cc |

上限は 20000 命令 (未到達)。`1801c5e84` の vm0 と u16 は `1c0b6c` で分岐する (§3)。

## 3. `callee_divergence` の分岐点 (`1801c5e84`, native 側)

`1c0b6c` (`test rcx, rcx`) に 5 回到達する。命令は `0x1c0b6c: test rcx,rcx` / `0x1c0b6f: je 0x1c0ba8` / `0x1c0b71: push rbx` …。

| 回 | vm0 の rcx → 次 rva | u16 の rcx → 次 rva |
|---|---|---|
| 1 | `1720f3000` → `1c0b6f` (je 不成立) | `1400000001` → `1c0b6f` (不成立) |
| 2 | `0` → `1c0b6f` (成立・`1c0ba8` へ) | `530020004c0046` (UTF-16 "F\0L\0S\0") → `1c0b6f` (不成立) |
| 3〜5 | `0` (以降同じ) | `69006400750074` / `3600320020006f` / `37002e0031002e` (UTF-16 文字列) |

- `1c0b6f` の `je` の時点で vm0 は `rcx=0` (早期 return)。u16 は非ゼロの値。`1c0b76` の `mov r8, rcx` でその値は `r8` に移り、`1c0b82` の `call [IAT]` (IAT の import は `KERNEL32!HeapFree`、PE 解析で確認) の第 3 引数 (解放対象ポインタ) になる。`1c0b9c` (`QueryPerformanceCounter`) は両 pattern とも未到達。`1c0b82` 時点の `r8` は u16 の 1 回目が `1400000001`、2 回目以降は `530020004c0046` 等の UTF-16 文字列値。vm0 の呼出しは `r8=1720f3000` の 1 回のみ。`1c0b82` 直前の `rcx` (hHeap) は両 pattern とも 0 (`ld57` trace の値)。
- `KERNEL32!HeapFree` (`1c0b82`) の呼出し回数: vm0 = 1 回 / u16 = 5 回。
- wasm 側では `function_1801baef8` が未定義で呼ばれ `callee_divergence` (`ld57_base.log` の `1801c5e84` 行) になっている。native の 5 回の HeapFree 呼出しと wasm の対応は、wasm 側 trace が無いため未確認。

## 4. 未達 (受入条件 1・2 の残り)

- wasm 側の命令単位 trace は未取得。native と wasm の rip・レジスタの対応付けは未達。
- 残りの 5 関数 (`1801c621c`・`1801c682c`・`1801c69cc` ほか) の分岐点の比較も wasm 側が無いと確定できない。

## 5. 測定 commit と差分

- 測定 commit: `3ff24dbc`。
- コード差分 `git diff 3ff24dbc HEAD -- tools/liftdiff/rt tools/liftdiff/ldlib` は 0 件 (HEAD = `83508f6d`。以降の commit は REPORT と `results/ld57/` の追加のみ)。
- `3ff24dbc` のコード差分: `tools/liftdiff/rt/ld_native.c` (+40 / -1)。`LD_STEP_N` 未設定時の既存動作との同一性は**未検証** (既存 e2e は未実行)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 側の命令単位 trace (`ld_wasm.c` / `fle_runner.mjs` への single-step 相当) | native と wasm の rip・レジスタ対応が取れない。`HeapFree` 経路の真偽が確定しない | LD-64 (#1854) |
| `1801c621c`・`1801c682c`・`1801c69cc` の分岐点の wasm 比較 | 6 関数のうち 3 関数は native 側 trace のみ | LD-64 (#1854) |
