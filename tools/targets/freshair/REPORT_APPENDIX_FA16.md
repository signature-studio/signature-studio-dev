# freshair FA-16 (#1182): 非空 controller map の静的読み (受入 1 の前半)

REPORT §12-5 の未解決 (非空 map による 0x180da6c00 到達) の付録。FA-9 本体の測定値は `REPORT.md` §12 が正本。
本付録は**静的読み (逆アセンブル, capstone 5.0.7・disasm.py) のみ**で、実行による検証は含まない。

## 1. 0x180ca1480 の分岐 (controller lookup)

| 機械語 | 意味 |
|---|---|
| `0x180ca14a4..14b2`: `[C+0x328]` と `[C+0x2d0]` を比較、一致で `0x180ca151b` (map 経路) | 等しければ map を引く |
| `0x180ca14b4..14dc`: 不一致かつ keycnt==1 かつ key0==0 → `{C+0x308, C+0x470}` を返す (静的分岐) | map を引かない |
| `0x180ca151b`: `rcx = [C+0x318] + 0xa8`、`r8w = key0`、`rdx = out` で `0x180ca7db0` を呼ぶ | controller map の検索 |
| `0x180ca153c`: `[out+0]` が非 0 なら found (`0x180ca156f`)、0 なら `{0,...}` を返す | found 判定 |

## 2. 0x180ca7db0 (map lower_bound) のノード配置

`0x180ca7db0(rcx = map header, rdx = out, r8w = key)` は MSVC 形式の `std::map` 下限探索。読み取った配置:

| オフセット | 内容 |
|---|---|
| `+0x00` | left |
| `+0x10` | right |
| `+0x19` (byte) | isnil (1 で終端) |
| `+0x20` (u16) | key |
| `+0x28` | value (qword, `out[0]` へコピー) |
| `+0x30` | shared_ptr 制御ブロック (`out[1]`。参照カウンタ `+8`) |

候補ノードは `0x180ca7dbb..0x180ca7dd8` で isnil 終端まで辿る。found 判定は `0x180ca7de1`: `key < node.key` (`jb`) なら not found、`node == head` でも not found。
found 時は `out[0] = node.+0x28`、`out[1] = node.+0x30` (参照カウンタを増やす)。

## 3. 0x180c9d700 (setter) と 0x180da6c00 の入口条件

- setter は `0x180ca1480` の `out[0]` が非 0 のときだけ後段へ進む (`0x180c9d737: je 0x180c9d813`)。
- found 後、`obj = out[0]+0x10` の vtable `+0x50(id)` → 戻り値の vtable `+0x18` → 戻り値の vtable `+8(value)` を呼ぶ。
- その後 `0x180da6c00(out[1], id, idx, r9=2)` を呼ぶ (`0x180c9d791`)。
- `0x180da6c00` は `r9==2` のとき `0x180f9e540` の結果 (`[rax]`) と `this+0xe8` を比較し、**一致で** `[this]+0x50` 経路 (`0x180da6c67`)、**不一致で**表 `this+0x30` への書き込み (`0x180da6c39`) へ進む。

したがって非空 map で `0x180da6c00` に届くには、(a) `C+0x2d0 == C+0x328`、(b) 検索 key で `[C+0x318]+0xa8` の木に node が 1 つ以上、(c) found 後の `out[0]+0x10` の vtable `+0x50/+0x18/+8` が有効、の 3 条件が必要。

## 4. 現行 harness との差 (実測済みの事実)

- `native/native_ctrl.c` の `build_tree` は `W64(C + 0x21a8, 8, C + 0x21b8)` で head を空 (`H.isnil=1`, `H = C+0x21b8`) にする。
- MAPTRACE (FA-4) の key は `{keycnt=1, key0=0}` で、found 無し (`run_fa9.sh` (a): found=0 が 72/72、da6c00=0)。
- 既存の判定ゲートは wasm 側 `native/ctrl_harness.mjs` と bit-exact 比較 (15/15) するため、map を変えるときは **native と wasm の両方を同時に変える**必要がある。

## 5. 未確認 (次の作業)

- (c) の vtable 配置 (`out[0]+0x10` が指す object の vtable 実体、`+0x50` の戻り先) は未読。
- node を 1 つ構築した際の `0x180ca7db0` の返り値が設計どおりか (found の実測) は未実行。
- 受入 2 以降 (Filter 出力変化の比較・DUMP idx 2・wasm ネガコン) は未着手。子 issue で扱う。

## 6. FA-17 (#1207): wasm 側ネガティブコントロール (受入 4)

- `native/ctrl_harness.mjs` に `FA_ALT9=1` (C+0x328 を C+0x2d0 と不一致にし静的分岐を強制) を追加。`run_fa9.sh` の判定ゲートに `(b-wasm)` を追加。
- 実測 (`run_fa9.sh`, 同 commit): (a) base ERR=0・ca1480=72・path=map・found=0・da6c00=0 / (b) native alt ERR=8/8 path=static / (b-wasm) wasm alt ERR=8/8 / GATE: PASS / run_ctrl BIT-EXACT 15/15。
- 非空 map (受入 1〜3) は未着手。found=0・da6c00=0 のまま (§4)。

## 7. FA-21 (#1535): 1 ノードの非空 controller map (native / wasm 同時変更)

- 変更 (測定 commit `0cf238bb`): `native/native_ctrl.c` と `native/ctrl_harness.mjs` に同一の 1 ノードを追加 (`C+0x21b8` の head に接続、key u16=1、value=Z、blk=RB0)。
  key=1 は静的読み §1 の `[C+0x328]` 比較の後の探索 key (`keycnt`、`0x180ca1499` の `edx`) に合わせた。key=0 では found=0 のまま (実測)。
- 修正 (commit `ad1f4768`): 1 ノード追加を `FA_NODE1=1` の裏に置いた (既定 OFF)。既定 OFF では旧 baseline (found=0・ERR=0) を維持し、ゲート (a) は既存の期待値のまま。found=1 は `FA_NODE1=1` 専用の別行として下記に残す。
- 実測 (HEAD `ad1f4768`, `bash run_fa9.sh`, 既定 OFF): `(a) base: scenarios=8 ERR=0 ca1480=72 path=['map'] eq=['1'] found=['0'] da6c00=0` / `(b) alt: ERR=8/8 ca1480=8 path=['static']` / `(b-wasm) alt: wasm ERR=8/8` / `(c) pert: 状態ダンプ差分トークン=395 / L/R 同一 40 呼出 / 差分 0 呼出` / **GATE: PASS** / `run_ctrl 2 5` **BIT-EXACT 15/15** (wall 3 s)。
- 実測 (HEAD `ad1f4768`, `FA_NODE1=1` で手動 probe, 専用行・ゲート外): native `scen 8 ERR 8 ca1480 8 found=['1'] eq=['1'] path=['map']` / wasm (`FA_NODE1=1 ctrl_harness.mjs`) ERR 8/8。既知の失敗 (setter `0x180c9d74c` の `addr=0x50` SIGSEGV、#1182 の範囲)。
- 実測 (`bash run_fa9.sh`, `0cf238bb`, clean build, load 0.18→0.55, wall 35.98 s):
  - (a) base: scenarios=8, ERR=8/8, ca1480=72, path=map, **found=1 (72/72)**, da6c00=0 (旧 baseline は found=0)。
  - 失敗原因: found=1 の後、setter (`0x180c9d74c`) が `addr=0x50` で SIGSEGV (`out[0]+0x10` の vtable が未構築)。受入 2 後半 (0x180da6c00 到達) は範囲外 (#1182)。
  - (b) alt: native ERR=8/8 path=static / wasm ERR=8/8 (変化なし)。
  - (c) pert: 差分トークン 0 (ERR のため状態ダンプに届かない)。
  - GATE: **FAIL** — (a) の期待値 (found=0・ERR=0) が旧 baseline のままのため。ゲートは緩めていない。
- 実測 (`bash run_ctrl.sh 2 5`, `0cf238bb`, wall 0 s): **BIT-EXACT 15/15** (fma0/fma1, 両側 ERR 14/14 同一 scenario)。※ `0cf238bb` 版の値。現 HEAD の値は §8 を参照。

## 8. FA-21 (#1535): 受入 1・2 の判定 (HEAD `9480d5ed`、測定 commit `ad1f4768` と lift2 差分 0)

- 既定 OFF (`bash run_fa9.sh`, HEAD, wall 41 s, load 0.36→0.53): (a) base ERR=0・ca1480=72・found=0・da6c00=0 / (b) ERR=8/8 / (b-wasm) ERR=8/8 / (c) 差分 395 トークン / **GATE: PASS** / `run_ctrl 2 5` **BIT-EXACT 15/15** (wall 4 s)。
  → 既定ビルドでは 1 ノードは入らない。受入 1 (native/wasm の 1 ノード構築) と受入 2 (found>=1) は**既定では未達**。
- 測定 commit の整理: lift2 のコードは `ad1f4768` 以降 HEAD まで変更なし (`git diff ad1f4768 HEAD -- tools/targets/freshair/lift2` = 0 行)。`0cf238bb` の値 (§7 の旧行) は HEAD の根拠にしない。
- 実測 (HEAD `01c78f64`, 既定 OFF, 再測定): `bash run_ctrl.sh 2 5` **BIT-EXACT 15/15** (wall 3 s, load 0.74) / `bash run_fa9.sh` **GATE PASS** (wall 3 s, load 0.70; (a) ERR=0・ca1480=72・found=0・da6c00=0 / (b) ERR=8/8 / (b-wasm) ERR=8/8 / (c) 差分 395 トークン)。
- `FA_NODE1=1` 専用 (ゲート外, HEAD, `FA_PROBE9=1`):
  - native: 8/8 scenario で `found=1` (`FA9CA` 行 8/8)。ERR 8/8 (setter `0x180c9d74c` の `addr=0x50` SIGSEGV、#1182 の範囲)。
  - wasm: found は**未観測** (`ctrl_harness.mjs` に FA9CA 相当の観測点が無い)。ERR 8/8 (`RuntimeError: unreachable` at wasm-function[1102], native とは別の失敗形)。wasm 側で 1 ノードが found=1 になったかは本測定では判定できない。
- 判定: issue #1535 の受入 1・2 は未達。判定基準 (a) の期待値 (found=0・ERR=0) は変更していない。found=1 の既定化と wasm 側の観測点・ERR 形の解消は #1182 で扱う。

## 9. 未解決表 (PM 改訂 (A) 分割に合わせる)

| 項目 | 状態 | 起票先 |
|---|---|---|
| 既定 OFF での 1 ノード成立 (map 非空の既定化) | 未達 | #1182 (FA-16) |
| `run_fa9.sh` (a) の `found>=1` (期待値は変更しない) | 未達 | #1182 (FA-16) |
| native ERR=8/8: setter `0x180c9d74c` の `addr=0x50` SIGSEGV の原因特定 | 未解決 | #1578 (FA-22) |
| wasm の found 観測点と ERR 形 (`RuntimeError: unreachable`) | 未解決 | #1578 (FA-22) (観測点は #1182 の範囲) |
| 0x180da6c00 到達と Filter 出力比較 | 未着手 | #1182 (FA-16) |

## 10. FA-25 (#1791): FA_NODE1=1 の fault 値の採取と out[0] の照合

- 付録 `REPORT_APPENDIX_FA22.md` は本 checkout に無い。FA-22 の記述 (`rip=180c9d74c addr=0x50`) は `FA_ALT9=1` の結果 (§6 (b)) で、`FA_NODE1=1` の結果ではなかった。
- `FA_NODE1=1` (probe 無し, 実測): `ERR S900 sig=11 rip=180c9d741 addr=0 ... rcx=a5a5a5a5a5a5a5a5 rdx=0`。`0x180c9d741` は `mov rax,[rcx]` (setter の vtable 読み)。`rcx` は `[out0+0x10]` で、ヒープ poison 値 `a5a5...` が入っている。`a5a5...` は非 canonical アドレスなので #GP となり、Linux は `si_addr=0` を返す。`si_addr` と `rcx` の不一致は採取の誤りではない (`on_sig` は `si_addr` と `REG_RCX` を同一 ucontext から読む)。
- 旧 probe の `found=1` は誤り: `ca1480_probe` は `out+0x10` を見ていた。修正後 (`found = out[0] != 0`) は `found=0` (S900–S907, key={1,0}, 8/8)。
- `probe_guard` 版 (`[C+0x318]+0xa8` の読みを範囲内に限る) でも `out[0]=0` で、node Z (`out[0]` 候補) とは一致しない。`out[0]=0` と setter の `rcx=[out0+0x10]` の poison は両立しない。probe 自体が呼出順を変えている可能性があり、未解決。
- `FA9OBJ` 行 (観測専用) は `out[0]` が自前の node Z と一致するときだけ `+0x10` を読む (`bf7b39fc` で修正。想定外の値は deref しない)。既定 probe (`FA_PROBE9=1`) では `out[0]=0` のため出力 0 行、`FA_NODE1=1` の probe でも `out[0]=0` で 0 行 (実測)。
- 判定基準 (`run_fa9.sh` (a) の期待値 found=0・ERR=0) は変更していない。

測定 (測定 commit `bf7b39fc` = lift2 のコードを変えた最後の commit, `bash tools/targets/freshair/lift2/run_fa9.sh`, load 0.48→0.52, wall 5 s):
- (a) base: ERR=0・ca1480=72・path=map・eq=1・found=0・da6c00=0 / (b) alt: ERR=8/8 path=static / (b-wasm) alt: wasm ERR=8/8 / (c) pert: 差分 395 トークン・L/R 同一 40 呼出・差分 0 呼出 / **GATE: PASS**
- `bash run_ctrl.sh 2 5`: **BIT-EXACT 15/15** (wall 4 s)
- 測定 commit から HEAD までの lift2 差分: `git diff bf7b39fc HEAD -- tools/targets/freshair/lift2` (下記 HEAD 時点で 0 行)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `FA_NODE1=1` で `out[0]` が 0 (probe 下) と poison (probe 無し) になる不一致 | out[0] と node Z の照合が未了 (受入 2) | #1791 (本 issue に残す) |
