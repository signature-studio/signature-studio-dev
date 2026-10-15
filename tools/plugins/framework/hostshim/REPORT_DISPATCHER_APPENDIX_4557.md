# PLG-P0b-51 (#4557) — G18 書込み関数の呼出し元と P45 分岐の前提

親 #4385 (PLG-P0b-47)。前身は `REPORT_DISPATCHER_APPENDIX_3673.md` §2・§4.1 (6 ID の書込み元 VA と未確定)。
本付録は新規ファイル。#4385 の付録 (`REPORT_DISPATCHER_APPENDIX_4385.md`) とは別に、本 issue の計装結果をここに書く。

## 0. 結論

| 受入 | 結果 | 状態 |
|---|---|---|
| 1 0x41d8f0 の呼出し元 0x1376870 の経路と `r9` の値 | 0x41d8f0 の直接呼出しは 0x1376870 の 1 件 (E8 走査)。その外側 0x1376820 は直接・間接の参照が画像内に無い (下 §2)。`r9 == 1` で G18 書込み (0x41d919) に到達。`r9` の実行時の値は**未確定** | 部分 |
| 2 P45 の分岐 0x11fbb4f の前提と書込み | 分岐は `[[rbp+0x140]+0x10] == 0xb` (0x11fbb4f)。`[rbp+0x140]` は 0x6668d0 の戻り値。0x11fc2b3 の到達は戻り値の `+0x10 == 0xb` のとき。0x6668d0 の戻り値の実体は**未確定** | 部分 |
| 3 G18・P45 の実行時の値 | 未確定 (上の 1・2 の未確定部分)。書込み条件 (`r9==1`・`[+0x10]==0xb`) までを確定 | 部分 |

## 1. 測定条件

- 測定 commit: probe 系 (§3・§4・§5b) は `a854ce3d3` (HEAD で実行)。probe コードの最後の変更は `b182389f3` で、`git diff b182389f3 a854ce3d3 -- tools/plugins/framework/hostshim ':!*.md'` は 0 行。e2e 系 (§5) は `ebd21817e` (`hs_val_probe.py` に `g18caller`・`p45caller` を追加した commit)。基点は main `566304b53`。
- e2e 経路の差分: `git diff ebd21817e a854ce3d3 -- tools/plugins/framework/fw_stage2.sh tools/plugins/framework/hostshim/hs_e2e.sh tools/plugins/framework/hostshim/hs_e2e.mjs tools/plugins/framework/hostshim/hostshim.c tools/plugins/framework/hostshim/hs_disp_emu.py` は出力 0 行。e2e はこれらを使う。
- `ebd21817e` から HEAD までの hostshim 差分 (`git diff --stat ebd21817e a854ce3d3 -- tools/plugins/framework/hostshim ':!*.md'`): `hs_p56_callers.py | 21 +`・`hs_val_probe.py | 63 +` (0 行削除。#4558 側の commit を含む)。#4557 の追加は `hs_val_probe.py` の `callers` 関数と `__main__` の分岐。`g18caller`・`p45caller` の本体と分岐は変えていない。e2e 経路は `hs_val_probe.py`・`hs_p56_callers.py` を呼ばない (`grep -rln 'hs_val_probe\|hs_p56_callers' tools --include=*.sh --include=*.mjs --include=*.cjs --include=*.js --include=*.ts --include=*.yml --include=*.json` が 0 件) ため、§5 の e2e 測定値は HEAD でも有効。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (5.7 秒)。`work-fw-stage1` はリポジトリ root 基準のパスで `tools/plugins/work/fw/` に展開 (12 ファイル)。
- Python: `$RUNNER_TEMP/hsvenv` (`unicorn 2.1.4` / `pefile` / `capstone`)。
- 負の確認: `g18caller` の `edx=0` と `edx=2` で G18 書込みが無いこと、`p45caller` の `+0x10=0` で P45 書込みが無いことで、観測点が効いていることを確かめた。

## 2. 呼出し元の探索 (静的)

| 対象 | 探索 | 結果 |
|---|---|---|
| 0x41d8f0 | rel32 直接呼出し | 0x1376870 の 1 件 |
| 0x1376820 | rel32 直接呼出し・jmp・rip 相対 lea・8 バイト絶対参照・4 バイト RVA・即値 | 0 件 (`.pdata` の unwind 項目のみ)。直接の呼出し元は無い |
| 0x11fba90 | rel32 直接呼出し | 0x124e621 の 1 件 |
| 0x124e410 | rel32・RVA・lea | 0 件 (`.pdata` のみ)。直接の呼出し元は無い |
| 0x6668d0 | rel32 直接呼出し | 0x946622・0x11fbb23 の 2 件 |

0x1376820 と 0x124e410 はどちらも静的に参照されず、実行時に間接的に呼ばれる。呼出し元を辿れるのは、この 2 関数の一段上まで。

0x1376870 (rel32 直接呼出しの呼出し箇所) は、関数 0x1376820 の本体 (`.pdata` の範囲 `[0x1376820, 0x1376893)`) の中にある (0x1376820 から +0x50)。よって受入 1 の呼出し箇所は、probe の対象 0x1376820 の本体に含まれる。probe が見るのは関数入口 (0x1376820) であり、0x1376870 の直前の状態は見ていない。

## 3. 受入 1: G18 (0x41d919 `mov [G18], rdi`)

`hs_val_probe.py g18caller` (HEAD `a854ce3d3`・n=1・1 プロセス 7 秒・load 0.81〜0.86)。0x1376820 を `edx` ごとに単独実行 (`rcx=HOST, r8=0x18`):

| edx (= 0x41d8f0 の r9d) | 0x41d919 (G18 書込み) | 書込み値 |
|---|---|---|
| 0 | 到達せず | - |
| 1 | 到達 | `rdi` = `[rbp+0x30]` = 0x40000000 (stub 入力) |
| 2 | 到達せず | - |

0x41d8f0 の `r9d == 1` の分岐 (0x41d905) が条件。書込み値は 0x41d8f0 の第 3 引数 `r8` (`rdi`)。0x1376820 では `r8` = `[rbp+0x30]`、つまり 0x1376820 の第 1 引数 (rcx)。

main 側の `hs_val_probe.py g18_caller` (#4385 由来・HEAD `a854ce3d3`・6 秒) も再実行した。`r9=1` の 6 ID (0x18・0x45・0x54・0x56・0x64・0x65) は全て 0x41d919 に到達し、`r9=0` の 6 ID は全て未到達。`g18caller` の結果 (`r9d=1` のみ到達) と一致する。

**未確定**: 0x1376820 の呼出し元が `edx` に何を入れるか。静的参照が無いため、実行時の値は測れていない。

## 4. 受入 2: P45 (0x11fc2b3 `mov [P45], rax`)

`hs_val_probe.py p45caller` (HEAD `a854ce3d3`・n=1・1 プロセス 6 秒・load 0.84〜0.86)。0x11fba90 を単独実行 (`rcx=obj`, `[obj+0x34a8]=0`, `[obj+0x3518]=0x77`)。0x6668d0 は stub で `[+0x10]` を指定:

| 0x6668d0 戻り値の `[+0x10]` | 0x11fbb4f (cmp eax,0xb) | 0x11fc2b3 (P45 書込み) |
|---|---|---|
| 0xb | je 0x11fc2ac へ分岐 | 到達 (rax = rcx = this) |
| 0x0 | 0x11fc53b へ | 到達せず |

書込み値は `rax` = `[rbp+0x170]` = 0x11fba90 の第 1 引数 (rcx = this)。

main 側の `hs_val_probe.py p45_caller` (#4385 由来・HEAD `a854ce3d3`・7 秒) は `[+0x10]` を固定せず単独実行する。0x11fbaef までは到達 (True) するが、0x11fbb4f (分岐) と 0x11fc2b3 (書込み) は未到達 (False・False)。前提 (`[0x6668d0 戻り値]+0x10==0xb`) が無いため、`p45caller` の `+0x10=0xb` の結果と矛盾しない。

**未確定**: 0x6668d0 の戻り値の実体 (受け手のオブジェクトと `+0x10`)。P45 = this は確定、`[this+0x3518]` の値 (ID 0x45 の応答) は未確定。

## 5. 回帰 (Phase A)

- `fw_stage2.sh` (`FW_W` 既定): 6 分 53 秒・rc=1。`[fw] SMOKE PASS (Halt0/RestoreContext 到達): dispatch=38 units_done=0 va=1 heap=1 ff=0`。`fw_smoke_check` の FAIL (`runerr` / `init_reach`) は既存 #2510 の既知の失敗。
- `hs_e2e.sh`: 2 分 38 秒・rc=1。Phase A `[fw] Phase A (framework smoke): Halt0/RestoreContext dispatch=38 ff=0` → PASS。Phase B `memory access out of bounds` は既存 #2911 の既知の失敗。
- load average: 開始時 0.52、終了時は未採取。
- 注: 測定 commit `ebd21817e` から HEAD `a854ce3d3` までの hostshim 差分は `hs_p56_callers.py` 21 行・`hs_val_probe.py` 63 行の追加のみ (§1)。`hostshim.c` と e2e 経路 (`hs_e2e.sh`・`fw_stage2.sh`・`hs_e2e.mjs`・`hs_disp_emu.py`) は変わらない (§1 の `git diff` が 0 行)。e2e は `ebd21817e` で測定した値をそのまま使う。

## 5b. 追加計測: Dispatcher 経路での呼出し元の観測 (`callers` モード)

`hs_val_probe.py callers [IDs]` を新設。Dispatcher (0x13173a0) を ID ごとに実行し、0x1376820・0x124e410・0x41d8f0・0x11fba90 の入口に届いたかと、入口の戻り番地 `[rsp]` を出す。

並列化: `callers()` は ID を逐次に回すループである。並列は、ID を 0-63・64-127・128-191・192-255 の 4 つに分けて `hs_val_probe.py callers <IDs>` を 4 プロセス同時に起動した (シェルの `&`・`wait`)。1 プロセス内は逐次。

- 窓 `[0x13173a0, 0x1400000)` の既定 (窓外は stub): 全 256 ID (HEAD `a854ce3d3`)。4 並列で 50 秒 (load 0.5→1.8)。1 プロセス逐次では 76 秒 (load 1.0)。4 関数のいずれも到達 0 件 (`hits=-` が 256・`callers total hits = 0`)。
- 256 ID の stop 理由: `ended` 256 件・`return` 0・`step上限` 0・`exception` 0。path 長 (命令数): 最小 486・中央値 856・最大 941。`ended` は `emu_start` が例外なく終わったこと (上限 `MAX_STEPS`=400000 に届いていない)。よって「0 件」は途中終了ではなく、実行が最後まで進んだうえでの否定結果。
- イメージ全体を許可 (`HS_CALLERS_FULL=1`): 全 256 ID を 4 並列で 56 秒 (load 0.6→1.8)。到達 0 件 (`callers total hits = 0`×4)。stop 理由は `ended` 219・`exception` 37 (`Invalid instruction` 11・`Invalid memory mapping` 25・`Unhandled CPU exception` 1)。`exception` の 37 ID は途中で止まっている。その中で入口に届く前に止まった ID は、到達判定ができない。path 長は最小 485・中央値 4968・最大 5472。
- G18・P45 の 6 ID (0x18・0x45・0x54・0x56・0x64・0x65) は全て `stop=ended` (path 4967〜4992)。6 ID の到達 0 件は途中終了の影響を受けない。
- 前回の測定値 (10 分 59 秒・1 ID 12.6 秒・4 並列 32.8 秒) は、本 HEAD の再測定で再現しなかった (上の値に置換)。

読み: Dispatcher の実行経路 (6 ID) では、0x41d8f0 (G18 書込み) と 0x11fba90 (P45 書込み) の入口に届かない。したがって `r9`・`[0x6668d0 戻り値]+0x10` の値を、この経路の観測からは確定できない。0x1376820・0x124e410 を呼ぶ上流は、Dispatcher とは別の経路 (ID 受信後の非同期処理・コールバック等) にあると考えられるが、本 run では特定できていない。

## 6. 未解決 (起票先)

| 0x1376820 の呼出し元 (静的参照なし・間接呼出し) と `edx` (= `r9`) の実行時の値 | G18 (ID 0x18) の値 | #4385 ([PLG-P0b-47]) |
| 0x124e410 の呼出し元と、0x6668d0 の戻り値 (`[+0x10]`) の実体 (0x946622 の経路を含む) | P45 (ID 0x45) の値と応答 | #4385 ([PLG-P0b-47]) |
