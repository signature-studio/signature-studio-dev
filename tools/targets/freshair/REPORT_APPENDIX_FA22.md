# freshair FA-22 (#1578): setter 0x180c9d74c の addr=0x50 SIGSEGV の原因特定 (部分達成)

FA-21 (#1535) の付録 (`REPORT_APPENDIX_FA16.md` §7〜§9) の続き。`FA_NODE1=1` で 1 ノードを入れると、
setter `0x180c9d700` 内の間接 call で落ちる。本付録は**機械語の読みと実測の事実**のみを書く。
判定 (受入 2 の「同一原因か」) は未確定。

## 1. 逆アセンブル (capstone 5.0.7, `0x180c9d700` 先頭)

| 機械語 | 意味 |
|---|---|
| `0x180c9d724: call 0x180ca1480` | controller lookup。`out` は `[rsp+0x48]` |
| `0x180c9d737: je 0x180c9d813` | `[rsp+0x48]` (out[0]) が 0 なら後段へ進まない |
| `0x180c9d73d: mov rcx, [rcx+0x10]` | obj = `out[0]+0x10` |
| `0x180c9d741: mov rax, [rcx]` | obj の vtable を読む |
| `0x180c9d74c: call [rax+0x50]` | vtable の `+0x50` (id) を呼ぶ |

- issue の `addr=0x50` は `rax=0` のときの `[0+0x50]` 読みと整合する (vtable が 0)。
- wasm では同じ call が `fa_icall(t = [rax+0x50])` になり (`ctrl_full.ll` L643426 付近)、`t` が switch に無いと `host` 側で `unreachable` になる。

## 2. 実測 (native, 素の `native_ctrl`・probe 無し, `FA_NODE1=1 FA_DBG=1 FA_HEAP_ZERO=1`)

- `ERR S900 sig=11 rip=180c9d741 addr=0 rcx=a5a5a5a5a5a5a5a5` (S900〜S907 の 8 件とも `rip=180c9d741`)。
- **観測とずれる点**: 上の表の想定では `rip=180c9d74c` (`addr=0x50`) で落ちるはずだが、実際は一つ手前の `mov rax,[rcx]` (`0x180c9d741`) で `addr=0`・`rcx=a5a5…` になる。`rcx` は obj (`[out0+0x10]`) の値。
- **矛盾点 (未解決)**: `0x180c9d741` の `mov rax,[rcx]` が `rcx=a5a5…` で落ちたなら si_addr は `a5a5…` になるはずだが、実測は `addr=0`。`ERR` 行の `rcx` の採取時点 (`g_rcx` は on_sig で更新) と fault 命令の対応が確認できていない。したがって「obj がどの値か」は本付録では確定しない。
- `FA_REGS=1` の実測 (fault 時): `rax=7ffe782ffb98 rcx=a5a5a5a5a5a5a5a5 rdx=0`。`rax` は stack 上の値で、vtable ではない。`si_addr` (= `addr=0`) と `rcx` の不一致はそのまま残る。
- 次に見るもの: `si_addr` の取り方 (非 canonical / guard の経路) を確認し、`rcx` 由来のアドレスと突き合わせる。`out[0]` が node `Z` を指すか (`native_ctrl.c` L102〜104 の `W64(N,0x28,Z)`) を、`out0` の実値で照合する。

## 3. 実測 (native, `FA_PROBE9=1` 併用)

- `ca1480_probe` の出力: `FA9CA S900..S907 eq=1 kc=1 k0=0 path=map ret=out out0=0 out1=0 found=1` (8/8)。
- probe は `found` を `out+0x10` の非 0 で判定する。setter が読む `out[0]` (= `out0`) は 0 のまま。`found` の定義と `out[0]` の関係は未照合。
- probe 併用時は `rip=555555558b9b` (PIE 内, `FA_BT`) で落ち、PE の `0x180c9d7xx` とは対応しない。probe の trampoline 経由の fault は本付録の根拠に使わない。

## 4. wasm 側 (`ctrl_harness.mjs`, `FA_NODE1=1`, `FA_DBG=1`)

- ERR 8/8 (`RuntimeError: unreachable at wasm-function[1102]`)。native の `addr=0` とは別の失敗形。
- found の観測点は wasm 側に無い (`ctrl_harness.mjs` に FA9CA 相当が無い)。**未決定**。

## 5. 基準測定 (ゲート既定 OFF、判定基準は変更なし)

測定 commit: `60932d35` (origin/main。作業ブランチは本付録の commit のみで、`tools/targets/freshair/lift2` のコードは変更なし)。
- `bash run_ctrl.sh 2 5` (`lift2/` 直下から): BIT-EXACT 15/15、wall 4 s、load 0.19→0.63 付近。
- `bash run_fa9.sh`: GATE PASS、wall 5.1 s (`real 0m5.104s`)、load 0.60→0.63。(a) base ERR=0・ca1480=72・found=0・da6c00=0 / (b) ERR=8/8 / (b-wasm) ERR=8/8 / (c) 差分 395 トークン。
- 素材: `fl-win64` は使用していない。`plugins-freshair` を展開し `fetch.sh` で factory .epf 8 本を確認。`toolchain-retdec`・`toolchain-emsdk` は `build_ctrl.sh` (40 s, rc=0) で使用。

## 6. 受入条件の状態

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. setter addr=0x50 の原因 (obj・vtable の構築状態) | 部分 | 機械語 (§1) は確定。実測の `rcx` 値 (§2) が想定と合わず未解決 |
| 2. native と wasm が同一原因か (観測点の決定) | 未達 | wasm の found 観測点が無い (§4)。native の `found` と `out[0]` の関係も未照合 (§3) |
| 3. 判定基準 (run_fa9 (a) の期待値) を変えない | 達成 | 変更なし (GATE PASS) |
| 4. 測定 commit と実測値を REPORT に残す | 達成 | §5 |

## 7. 未解決 (起票先)

| 項目 | 状態 | 起票先 |
|---|---|---|
| `si_addr` (addr=0) と fault 時 rcx (a5a5…) の不一致、想定 (`0x180c9d74c`・addr=0x50) との不一致 | 未解決 | #4223 (FA-52。#1791 (FA-25) は PR #2103 で部分達成のまま CLOSED) |
| `out[0]` と probe の `found` の対応、node `Z` との照合 | 未解決 | #4223 (FA-52) |
| wasm の found・vtable 観測点の追加 (`ctrl_harness.mjs`) と同一原因の判定 | 観測点追加済み・判定は未 (§8) | #1789 (FA-24) |
| 0x180da6c00 到達と Filter 出力比較 | 未着手 | #1182 (FA-16) |

## 8. FA-24 (#1789): wasm 側の found・obj 観測点 (既定 OFF) と初期比較

観測点: `build_ctrl.sh` の `FA_TRACE9=1` で `--trace 180c9d700:180c9d760` を埋め込み、`ctrl_harness.mjs` の `FA_TRACE9=1` で
setter 入口〜出口の命令前レジスタを読む (`TRACE9` 行)。既定ビルドは trace を入れないので出力は変わらない。

- 0x180c9d729 (ca1480 戻り直後): `out0` = `[rsp+0x48]` を読む。
- 0x180c9d741 (`mov rax,[rcx]` 直前): rcx = obj (= `[out0+0x10]`)。

実測 (測定 commit `96d2eeb1f`。S900〜S907、`FA_NODE1=1`、wasm、`FA_TRACE9=1`):
- 各シナリオで 0x180c9d729 を 2 回通る。1 回目 out0=0、2 回目 out0=0x494b690 等 (非 0)。
- trace バッファは mlift の `@fa_trace` (`[8100000 x i64]`・100K 行 x 81) で上限チェックは無い。本測定で溢れたかは未確認 (行数は記録していない)。範囲を広げるとき、または 100K 行を超えうる入力では、`fa_trace_n` を上限で止める変更が必要。
- `traceSetter` は ERR 経路 (catch 内) でのみ呼ぶ。`traceFrom` も ERR 時にしか進まないため、OK の呼び出しの trace 行は次に ERR になったシナリオの `S` 番号で出る。本節の S900〜S907 は全て ERR なので、番号の対応は崩れていない。
- S900 の 2 回目は 0x180c9d741 の rcx=0 (obj=0)。したがって vtable 読みは `[0]` になり、rax=0 で `call [rax+0x50]` (addr=0x50) に進む。wasm では `fa_icall` の `t=0` が host に落ち `unreachable` になる (FA-22 §4 と同じ失敗形)。

native (`FA_PROBE9=1`・`FA_SET9=1`・`FA_NODE1=1`):
- SET9 の出力は S900 の 1 行のみ。FA9CA は S900〜S907 とも 1 行 (ca1480 の 1 回目の呼出・out0=0・found=0)。
- native 側は同じ区間の 2 回目の入場を**観測していない**。probe の仕組み (1 回だけ差替え・再 patch) の限界か、実際に入らないのかは未切り分け。

判定: **同一原因かは未判定**。wasm では 2 回目の入場で obj=0 → vtable=0 → `[0+0x50]` まで確認した。native 側で同じ 2 回目の入場を観測できていないため、found と vtable の比較は完了していない。次は native に `0x180c9d729` 相当の観測を入れ、2 回目の入場の有無と obj の値を揃えること (#1789 の残り・#2207 FA-31 に追記。#2207 は「ca1480 の node 値が実機 controller map に存在するか」が題名で、ここでいう 2 回目再帰の実機判定はその一部)。#1791 の残件は #4223 (FA-52) に移した。判定基準 (`run_fa9.sh` (a) の期待値) は変更していない。

測定 commit `96d2eeb1f` (load 0.18→0.18、素材 plugins-freshair を `$RUNNER_TEMP` に展開して `fetch.sh`):
- `bash run_fa9.sh`: GATE PASS、wall 3.06 s。(a)(b)(b-wasm)(c) の値は §5 (line 43) と同一。
- `bash run_ctrl.sh 2 5`: BIT-EXACT 15/15、wall 2 s、rc=0。
