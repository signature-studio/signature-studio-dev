# freshair FA-31 (#2207): 実機 controller map (C+0x318 木) の node 有無 — 木を埋める経路の特定と harness 観測

FA-30 (#2187, `REPORT_APPENDIX_FA30.md` §5) で未解決として #2207 に移した「実機 controller map に node があるか」の付録。
判定基準 (`run_fa9.sh` (a) の期待値) は変更していない。既知類型: 該当なし。

## 1. 結論

- **受入 1 (実機の controller map を空 map 以外の実経路で観測): 未達。** 本 harness の経路では木 (`[ctl+0xa8]`) を埋める関数が 1 回も実行されない。
  F ctor と PROCESS の全 8 シナリオで、木への挿入候補 `0x180caa820` と、その上流 5 関数の呼出は 0 回 (§3)。
  したがって node の有無は本 harness では観測できない。
- **受入 2・3:** 受入 1 が未達のため node の有無を前提にする判定はできない (未実施)。(a) の期待値は不変 (受入 3 は達成)。
- **新しい静的事実:** 木を埋める候補の上流は、UI 系クラスの vtable から到達する (§2)。前回の候補 `0x180a79c30` も UI 系 vtable (`UIGraphicEq`) から呼ばれる。
  実機で木に node が入るのは、GUI の操作 (モジュレーション表示・編集) 経由の可能性がある。**未確認**: 挿入先が C+0x318 の controller と同一か、UI 経路だけで足りるか (boot 連鎖 #672 が要るか)。

## 2. 経路 (静的読み。capstone・pdata 関数境界・vtable 所属。VA)

| 関数 | 静的な役割 | 到達 |
|---|---|---|
| `0x180d8c0b0` | ModulationKnobsPopup の vtable (`0x18110a420`) slot 5 | vtable 経由 (直接 E8 の呼出元なし) → E8 `0x180d8d700` |
| `0x180d8d700` (0xd2d B) | `0x180d8c140` を 4 回呼ぶ | E8 (`0x180d8c140` の呼出元はこの関数のみ) |
| `0x180d8c140` (0x1ad B) | `0x180d8ae60` を呼ぶ | E8 `0x180d8c24b` |
| `0x180d8ae60` (0x298 B) | `0x180e15030` を呼ぶ | E8 `0x180d8aec7` |
| `0x180d8c4f0` (0x3be B) | `0x180e15030` を呼ぶ (直接の呼出元なし) | E8 `0x180d8c7b9` |
| `0x180e15030` (0x67a B) | `0x180e12f20` を呼ぶ | E8 `0x180e1511e` |
| `0x180e12f20` (0x1f3 B) | ModulationFormatter (vtable `0x181110fc8`) を構築する | `lea` で vtable を書く (`0x180e12fae`) |
| vtable `0x181110fc8` slot 2 = `0x180e13590` | 仮想呼出 (直接の E8 なし) | `.?AVModulationFormatter@?A0xc6f8f7e4@@` |
| `0x180e13590` (0x8fe B) | `0x180caa820` を呼ぶ | E8 `0x180e139a2` |
| `0x180caa820` (0x862 B) | **挿入候補**: `[this+0xa8]` を `0x180ca7db0` で lower_bound し、`[this+0x380]` の木を走査、key は u16 (`[r12]`)。無ければ node を作る (vtable `+0x50`/`+0x58` 呼出と、割当と見られる `0x18100beb0` 呼出を含む。詳細は未読) | E8 (`0x180e13590` と自身の再帰) |
| `0x180ca7db0` | 陽性対照: ca1480 の map 経路の lower_bound | E8 `0x180ca1537` (ca1480 の内部) |

- 前回 run の候補 `0x180a79c30` (C+0x2d0/0x328/0x318 を書く) は `0x180a79100` から呼ばれ、`0x180a79100` は `UIGraphicEq` の vtable (`0x1810f5128`) slot 5。UI 側。
- `0x180dde530` (大きな構築関数。`0x180ddef50` を呼ぶ) の呼出元 3 つは未特定 (本付録の範囲外)。

## 3. 観測 (測定 commit `e11367a6b`・`fa31_ctl.sh`・8 シナリオ S900–S907 の epf)

`FA_CTL31=1` の診断フック (`native/native_ctrl.c`, 既定 OFF) で、各関数の入口の呼出回数を数えた。
各 probe は元の機械語を一時復元して本物を呼ぶ (`ca1480` の probe と同じ方式)。陽性対照で方式が効くことを確認した。

| 条件 | ca7db0 (陽性対照) | caa820 (挿入候補) | e13590 | d8c4f0 | d8ae60 | e15030 | e12f20 |
|---|---|---|---|---|---|---|---|
| base (既定・空 map) | **72** | 0 | 0 | 0 | 0 | 0 | 0 |
| node1 (`FA_NODE1=1`・1 node 注入) | 8 | 0 | 0 | 0 | 0 | 0 | 0 |

- ca7db0 が base で 72 回 = ca1480 の呼出数 (72) と一致。probe の方式は効いている。
- caa820 が 0 回のため、CAA31 行 (木のノード数 `tree=`) は出ていない。木のノード数は未観測。
- node1 で ca7db0 が 8 回に減る理由は未確認 (ca1480 の found 経路の違い)。本付録の判定には使わない。

## 4. 測定 (測定 commit `e11367a6b`・HEAD 差分 0 行)

- `bash tools/targets/freshair/lift2/run_fa9.sh`: 初回 (build_ctrl を含む、work 無し) **40.8 s (n=1)**、load 0.10→0.54。**GATE PASS**。
  (a) base: ERR=0・ca1480=72・path=map・eq=1・found=0・da6c00=0 / (b) alt: ERR=8/8 path=static / (b-wasm) alt: wasm ERR=8/8 / (c) pert: 差分 395 トークン・L/R 同一 40 呼出・差分 0 呼出。
- `bash tools/targets/freshair/lift2/run_ctrl.sh 2 5`: **BIT-EXACT 15/15** (epf 8 + structured 2 + random 5, fma0+fma1)、**wall 4.4 s (n=1)**、load 0.50→0.54、rc=0。
- `bash tools/targets/freshair/lift2/fa31_ctl.sh`: rc=0、wall 0.5 s (n=1)、load 0.54→0.54。§3 の表。
- 測定 commit から HEAD までの lift2 差分: `git diff e11367a6b HEAD -- tools/targets/freshair/lift2` (本付録の commit は docs のみ) = 0 行。
- 製品 KPI (FLEngine 起動 dispatch 数・units_run・最初のウィンドウ): **動かしていない** (native harness の診断のみ。起動経路と GUI の挙動は既定で不変)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 木 (`[ctl+0xa8]`) に node が入る経路の実行: UI 系 `0x180d8c0b0` (ModulationKnobsPopup slot 5) から `0x180caa820` までを harness で実行し、木の node 数を観測 | 受入 1・2 が未達 | #2207 (本 issue・open のまま。Refs) |
| `0x180caa820` の `this` (controller) が C+0x318 の controller と同一か | 挿入先の同定 (受入 1 の前提) | #2207 |
| UI 経路だけで木が埋まるか、boot 連鎖 (#672) が要るか | blocked_by の要否 | PM 判断 (#2207 コメント) |
| `0x180dde530` の呼出元 3 つ (snapin 構築側) の特定 | 木の初期化の全体像 | #2207 |
| node1 で ca7db0 が 8 回に減る理由 | 観測の解釈 (判定には未使用) | #2207 |
