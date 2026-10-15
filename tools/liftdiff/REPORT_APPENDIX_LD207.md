# LD-207 (#4264): 691dd0 を vtable 付き有効オブジェクトで投入し、判定に入れる

親: #4200 (LD-203・closed)。前段: `REPORT_APPENDIX_LD203.md` §2 (691dd0 は有効オブジェクトを渡しても小サイズ確保のビン読みで segv)。
測定 commit: `0c277b47b` (コードを変えた最後の commit。検証 HEAD = 測定 commit)。基準: origin/main `7ae7c6981`。

## 1. 結論

| 関数 | 結果 | 根拠 |
|---|---|---|
| `691dd0` | **判定に入った (`diff`)。** rcx に vtable 付きの有効オブジェクト (`blob=vmt`) を渡し、r8 (1 byte flag) を 0 にすると、native も wasm も segv せず、`outcome=diff`。 | §2 |

前段 LD-203 の「入らない」は、rcx が blob の値 (`z`・`s`・`p*`・`q*`) を指す投入形に限った結論だった。vtable 付きオブジェクトを rcx に渡すと入る。

## 2. 691dd0 の投入形

- 機械語 (`block00031_PE.bin`・ImageBase `0x400000`): `407a93` `mov rdx,[rbx+8]` → `407a97` `mov rax,[rdx+0x18]` (小サイズ確保のビン読み)。ビン表は VA `0x13a5108` (16B 間隔)。boot 状態 (`work/m11/boot_state.json`) のビン表は fd が 0 の index (7・11・15 など) を含む。どの index を踏むかは rcx の内容で決まる。
- 既定の pattern (`z`・`s`・`p0`・`q0` 等) では rcx が blob の値を指すため、`407a97` で segv する (`native_fault` または `both_fault`)。
- 単発の実測 (`liftdiff.py run targets/m11.json --fn 0x691dd0 --args ... --blob vmt`):

| rcx | rdx | r8 | native | wasm | 結果 |
|---|---|---|---|---|---|
| `a:0x1000` (VMT 付き) | 3 | 0 | ok | ok | `diff` |
| `a:0x1000` | 5 | 0 | ok | ok | `diff` |
| `a:0x1000` | 0 | 0 | ok | ok | `diff` |
| `a:0x1000` | 3 | 1 | segv | ok | `native_fault_all_patterns` |

- 結論: 判定に入る条件は「rcx が VMT 付きオブジェクト」かつ「r8 (flag) = 0」。r8 が 0 以外だと `691e65` の `cmp byte ptr [rbp+0x70], 0` の経路で segv する。
- 規則: `ldlib/cases.py` の `OBJ_PATTERNS` に、691dd0 だけの pattern `vmo` (`blob=vmt`・rcx=`a:0x1000`・rdx/r8=0) を足す。`session._run_one` で、その VA の pattern 列に追加する。

## 3. 検証

- 単体: `tests/test_ld207_obj_pattern.py` PASS (`rc=0`)。ネガコン: `OBJ_PATTERNS` の 691dd0 の行を消すと `rc=1` で落ちる (実測)。
- 単体 (`[0/4]`): `test_ld52_machine_sig`・`test_ld181_i128_entry`・`test_ld179_tagpoint_tr`・`test_ld203_slot_fill` は PASS。
- 691dd0 単発 (`liftdiff.py run targets/m11.json --fn 0x691dd0 --state work/m11/boot_state.json --nobuild`): `vmo` = `diff`、他 11 pattern は従来どおり (`native_fault`・`both_fault`)。`vmo` は native `ret=0x1`・wasm `ret=0x0` で、heap の差が 26 件出る。差の原因は未特定 (§4)。
- e2e: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/liftdiff/liftdiff_e2e.sh --m11-only` → **exit 0・`LIFTDIFF_E2E PASS`・`real 2m48.981s`**。開始時 load 0.04 (09:36:40)・終了直後 4.59 (09:39:29)。
- sample:800 (`--shards 12 --state auto`): **一致 360 / 不一致 234 / 実行不能 206**。LD-203 の測定 (`ad0ca414b`: 361/233/206 と 360/234/206 の 2 通り) と同じ範囲。691dd0 は sample:800 の集合に入っていないため、sample の数値は変わらない。
- コード差分 (測定 commit `0c277b47b` → HEAD): 測定 commit = HEAD のため、差分は 0 行 (`git diff 0c277b47b HEAD -- tools/liftdiff` の出力は 0 行)。
- 製品 KPI (FLEngine 起動・最初のウィンドウ): 本 PR は起動・GUI に関わらないため書かない。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `vmo` の `diff` は heap の差 (wasm の確保経路の後段) と ret (`native=0x1`・`wasm=0x0`)。差の原因が lift 欠陥か比較の問題かは未特定 | 691dd0 は判定に入るが、一致か不一致かの結論は出ていない | 子 issue (本 run で起票) |
| sample:800 の集合に 691dd0 が入っていない (closure の集合拡張が要る) | batch 全体の一致 / 不一致の数値に 691dd0 が反映されない | #4200 配下の後続 (未起票・PM 判断) |
| `653c80` の間接 call slot (LD-203 で埋め済み) の判定 | 本 PR の対象外 | #4200 ([LD-203]) の既存記録 |
