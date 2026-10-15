# #2426 REPORT — hs InitUnits の OOB 1 件目 `function_414390` の入力定数化を修復 (次の OOB は `function_40c4d0`)

- 担当 issue: #2426 `[PLG-P0b-17]` (親 #2008)。受入 1 を達成し、受入 2・3 は子 #2534 へ移管。
- 測定 commit: `a63e33ab` (コード変更を含む最後の commit・count==0 経路の修正)。起点 `origin/main` `54bacdc0`。
- 既知類型との関係: 該当なし。`docs/DEFECTS.md` D4 (`mov r64,[r8]` の disp=0 deref が脱落し `rD := r8` になる) とは別型で、D4 は引数 reg の値を正しく残して deref だけ落とす。本件は引数 reg の値そのもの (rcx/rdx/r8) が `ptrtoint @G` の定数に畳まれ、被呼出し側が reg を読まない。D21 (呼出し側の引数値がスタック番地の下位 byte になる) とも別。既存 ID とは照合していない (§4 の新類型候補)。
- 結論: `function_414390` (wide string copy) の OOB の直接原因 (入力 rcx/rdx/r8 の定数化) を特定し、hs 経路の IR 修復 `hs_irfix.py` `fix_414390` で解消した。OOB は同 unit (InitUnits idx 18) 内の `function_40c4d0` へ移動し、InitUnits は完走しない。`plug` は依然 0。

## 1. 実測

環境: 4 vCPU・RAM 15 GiB。素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`) に展開、`work-fw-stage1`・`work-liftlib` を worktree 直下に `tar --zstd -xf` で展開 (`$ARTIFACTS_DIR` の実在を確認済み)。load は `uptime` の 1 分値 (開始 → 終了)。

| 手順 | commit | 結果 | 所要 (real) | load |
|---|---|---|---|---|
| `fw_stage2.sh` (非 fresh・stage-1 から全生成・n=1) | 54bacdc0 (stage-2 は本修正の対象外) | rc 0・`SMOKE PASS` (`dispatch=38 units_done=0 va=1 heap=1 ff=0`) | 7 分 41 秒 | 1.00 → 2.53 |
| `hs_e2e.sh --fresh` (修正前・baseline) | 54bacdc0 | rc 1・Phase A PASS (`dispatch=38 ff=0`)・Phase B `memory access out of bounds`・`plug=0x0 rec=7` | 2 分 15.4 秒 | 2.33 → 1.20 |
| `hs_preinit.mjs` (修正前) | 54bacdc0 | DllMain(attach) OOB。チェーン `0x445a40 → 0x415220 → 0x414de0 → 0x414390`。`unit counter=19`。プロセスは `exit(103)` | 計時なし | 計時なし |
| `hs_e2e.sh --fresh` (修正後・count==0 修正前) | 11096d29 | rc 1・Phase A PASS・Phase B OOB・`plug=0x0 rec=7` | 2 分 16.1 秒 | 0.26 → 0.93 |
| `hs_preinit.mjs` (修正後・count==0 修正前) | 11096d29 | DllMain OOB。チェーン `0x445a40 → 0x43ecb0 → 0x439df0 → 0x43b130 → 0x40c4d0`。`unit counter=19` | 計時なし | 計時なし |
| `hs_e2e.sh` 増分 (修正後・count==0 修正前) n=3 | 11096d29 | 3 回とも rc 1・Phase A PASS・Phase B 同一 (`plug=0x0 rec=7`) | 339 / 344 / 343 ms (`date +%s%N` 差分) | 0.93 (開始) |
| `hs_e2e.sh --fresh` (count==0 修正後・現測定) | a63e33ab | rc 1・Phase A PASS (`Halt0/RestoreContext dispatch=38 ff=0`)・Phase B `memory access out of bounds`・`plug=0x0 rec=7`。ログ末尾: `E2E FAIL: 1 項目 — Phase B 例外` | 2 分 38.4 秒 (`time`・emcc 込み) | 0.92 → 1.00 |
| `hs_preinit.mjs` (現測定) | a63e33ab | DllMain OOB。チェーンは 11096d29 と同一 `0x445a40 → 0x43ecb0 → 0x439df0 → 0x43b130 → 0x40c4d0`。`unit counter=19`。`[pre] Phase B 例外: Maximum call stack size exceeded` (DllMain 例外後の同一 instance・参考外) | 計時なし | 0.66 (開始) |
| `hs_e2e.sh` 増分 (現測定) n=3 | a63e33ab | 3 回とも rc 1・Phase A PASS (`dispatch=38 ff=0`)・Phase B `memory access out of bounds` (`status=0xffffffff plug=0x0 rec=7`)。ログ: `E2E FAIL: 1 項目 — Phase B 例外: memory access out of bounds` | 321 / 328 / 331 ms (`date +%s%N` 差分) | 0.66 (開始) |

- 注: 増分 n=3 の実行時間は Phase A (framework smoke) と Phase B の node 実行のみで、emcc は含まない。`fresh` 2 分 38 秒 は emcc 込み。
- count==0 経路 (`0x414394`) は count=261 の e2e では通らない。本修正の効果は e2e では観測できず、IR の該当行 (下記 §3) で確認した。

- `fresh` は n=1 (60 分の上限内に収めるため)。n≥3 のレンジは未取得 (増分のみ n=3)。
- `hs_preinit.mjs` の Phase B 行は DllMain 例外の後に同一 instance で実行するため、`plug`/`rec` の値は参考外 (修正後の出力は `Maximum call stack size exceeded`)。Phase B の判定は `hs_e2e.sh` 側の結果を正とする。
- 修正前後の差 (negative control): 修正前は OOB が `function_414390` で起きる (baseline 実測)。修正後は `function_414390` の OOB が消え、同じ unit の `function_40c4d0` で起きる。Phase A は両方で PASS (回帰なし)。

## 2. 直接原因: `function_414390` の入力が定数に畳まれている

- native (`objdump -d -M intel --start-address=0x414390 fw_icall.dll`、wcsncpy 相当で rcx = dst、edx = count、r8 = src を入力として読む):
  - `0x414390` `test edx,edx`・`0x414392` `jne 0x41439b`: count==0 の不成立側は `0x414394` `mov WORD PTR [rcx],0` (**dst に NUL 1 語を書く**)・`0x414399` `jmp 0x4143c5` (ret)。
  - count≠0 の loop (`0x41439f`〜`0x4143b8`): `movzx rax,WORD PTR [r8]`・`mov [rcx],ax`・`0x4143a6` `test ax,ax`・`0x4143a9` `je 0x4143c5` (src の NUL で即 ret)・`add rcx,2`・`add r8,2`・`sub edx,1`・`jg` (count 回で抜ける)。
  - loop を count 回で抜けた後 (`0x4143ba`〜`0x4143bf`): `test edx,edx`・`jne 0x4143c5`。0 なら `mov WORD PTR [rcx-0x2],0` (末尾の NUL 終端)。
- 呼出し側 `function_414de0` (native `0x414e47 call 0x414390`): 直前に dst を BLK+0x08 (rcx)、count `261` (`0x105` = MAX_PATH+1) を BLK+0x10 (rdx)、src を BLK+0x18 (r8) へ格納する (hs IR の該当行 57585〜57588 相当)。
- lift IR (`fw_flat4_canon3.ll` の `function_414390`、`hs_flat3.ll` も同型): BLK+0x08/+0x10/+0x18 を読まず、`ptrtoint ptr @673 to i32` (count)・`@674` (dst)・`@675` (src) を使う。`and(@673,@673) != 0` は常に真。count がアドレス値 (大きい正数) になるため、loop は src の 0 文字まで読み続け、wasm の線形メモリ (上限 `0x14000000`) の外へ出る。count==0 経路 `dec_label_pc_7cd3f4` の `store i16 0, ptr @674` は native `0x414394` の dst への書込みに対応する。
- 観測: 修正前の `hs_preinit.mjs` は `function_414390` で `memory access out of bounds` を出す。`BLK+0x08/+0x10/+0x18` の実値は `rcx=0x118b5f86`・`rdx=0x105`・`r8=0x10fcab90` (r8 は空文字)。count の 261 が lift では使われていないことが直接の原因。

## 3. 修復 (`hs_irfix.py` の `fix_414390`)

- 10 規則。各規則は置換 1 件を assert し、件数が違えば `exit 1` (`hs_irfix.py` の既存方針と同じ)。定数名 (`@673/@674/@675`) は body から実行時に読む (lift 版ごとに RetDec が振り直すため)。置換後に旧定数が残らないことも確認する。
- 修正後の入力: count = `load i32` (BLK+0x10)、dst = `load i64` (BLK+0x08)、src = `load i64` (BLK+0x18)。
- count==0 経路 (`dec_label_pc_7cd3f4`・native `0x414394`) の `store i16 0` は BLK+0x08 を `load i64` → `inttoptr` した値 (= dst) へ書く。`%hs414390_dst = load i64, ptr inttoptr (i64 9048072 to ptr)` → `%hs414390_dstp = inttoptr i64 %hs414390_dst to ptr` → `store i16 0, ptr %hs414390_dstp, align 8`。`hs_irfix.py` の出力 IR で該当 3 行を確認 (dec_label_pc_7cd3f4 の 3 行目が上記)。
- 前版 (`11096d29`) の誤り: この `store i16 0` を `inttoptr (i64 9048072)` (= dst の値を格納した BLK+0x08 スロット自体) に書いていた。dst は 0 にならず、直後の `function_4143c5` が BLK+0x08 の下位 16bit を 0 にした値を読んでいた (レビュー指摘・a63e33ab で修正)。
- 出力: `[hs_irfix] function_414390 patched: 入力 rcx=@674 rdx=@673 r8=@675 を BLK+0x08/+0x10/+0x18 から読む` (`hs_e2e.sh --fresh` の実ログ)。
- 対象は hs 経路 (`hs_irfix.py`) のみ。stage-2 の canonical IR (`fw_flat4_canon3.ll`) の `function_414390` は同型の定数 fold が 9 箇所あるが未修正 (§5、#2510 の範囲)。

## 4. 次の OOB: `function_40c4d0` と `function_40ffe0` の疑い (未修正)

- `function_40c4d0` (native `0x40c4d0`): `mov rax,[rcx]`・`movsxd rax,DWORD PTR [rax-0x80]` (VMT の負オフセット参照)。lift IR は `inttoptr i64 -92` の `load i32` になっており、wasm では `2^32-92` の境界外アドレス。入力 rcx (this) の読みが定数に畳まれた疑い (未検証)。修正後の `hs_preinit.mjs` の wasm スタック上端は `function_40c4d0 (wasm-function[355]:0x4e62e)`。
- `function_40ffe0` (r8 の出所): native は `mov rax,rcx`・`test rax,rax`・`jne 0x40fff3` (shared `ret`)、その後に `mov rax,[0x6d5c20]`・`lea rax,[rax+0x10]`・`ret`。すなわち `rcx != 0` なら `rcx`、`rcx == 0` なら `[0x6d5c20]+0x10` (native の該当値 `0x40f81c` は空文字)。lift 版は `jne` の分岐を落として `call function_40fff3()` を無条件に行い、戻り値を BLK+0x80 経由で受ける規約。hs IR の `function_40fff3` は `fw_hs_scratch(64)` の戻り値を BLK+0x80 に入れる (`hs_flat3.ll` 868〜873 行)。そのため `r8` は scratch 由来 (`0x10fcab90`・空文字) で、native の `0x40f81c` とは値が違う。今回は空文字だったので OOB にはならなかったが、正しさは未検証。
- 新類型候補 (PM 判断): 「被呼出し側の入力レジスタを読まず、RetDec が定数 (`ptrtoint @G`・`inttoptr <const>`) に畳む型」。`hs_irfix.py` の `fix_414390` は 1 関数ごとの手当てで、一般化はしていない。
- §9 (#2534) も同じ型: `function_40c4d0`・`function_40b3f0` の entry 引数 (this・flag) を `"$"` 定数に畳む。1 関数ごとの手当てで、一般化はしていない (PM 判断)。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_40c4d0` の入力定数化 (`inttoptr -92`) で idx 18 の Init が完走しない | 受入 2・3 (InitUnits 完走・Phase B `plug != 0`) | 子 #2534 `[PLG-P0b-19]` |
| `function_40ffe0` の `jne` 分岐落ちと戻り値規約 (r8 が scratch 由来) | 空文字で無害の見込みだが未検証。値の一致は未確認 | 子 #2534 (受入 2) |
| stage-2 canonical IR の `function_414390` 同型の定数 fold (9 箇所・hs 経路のみ修正) | 非 hs 経路の同一関数が未修正 | 既存 #2510 (`"$"` 定数 fold の生成側修復) に追記 |
| fresh の所要 n≥3 レンジ未取得 (n=1) | 受入 3 の n≥3 | 子 #2534 (受入 3) |
| `hs_preinit.mjs` の Phase B は DllMain 例外の後に同一 instance で走るため判定に使えない | 観測の解釈 | 子 #2534 に併記 (修正は子の範囲) |
| #2425 (CLOSED・stage-2 の idx 16 基準の再定義) | Phase A の `dispatch=38` の意味 | 起票先なし (参照のみ。#2425 は CLOSED で本件の依存ではない) |

## 6. 検証範囲 / 範囲外

- 範囲: hs 経路 (`hs_e2e.sh`・`hs_preinit.mjs`) の DllMain(attach) から InitUnits idx 18 の途中まで。
- 範囲外: Phase B の `plug != 0` (未達)、InitUnits 完走 (未達)、stage-2 canonical IR の修復 (未実施)。
- Phase A の回帰は毎回 `dispatch=38 ff=0` で PASS を確認 (§1)。

## 7. コード差分 (測定 commit 以降)

- 測定 commit `a63e33ab` 以降の差分は本 REPORT のみ (コード 0 行)。`git diff a63e33ab HEAD -- tools/plugins/framework` の出力は `REPORT_2426.md` だけ。
- 前測定 `11096d29` からの差分 (`git diff --stat 11096d29 a63e33ab -- tools/plugins/framework`): `hostshim/hs_irfix.py` 1 行を 3 行に置換 (count==0 経路の書込み先 · +2 −1)、`REPORT_2426.md` (+78)。

## 8. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
mkdir -p $RUNNER_TEMP/fl-win64 && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst   # repo ルートで展開
bash tools/plugins/framework/fw_stage2.sh                        # 非 fresh で stage-2 を生成 (7 分 41 秒・n=1)
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh           # Phase A PASS・Phase B OOB (2 分 16 秒・n=1)
cd tools/plugins/work/hs && node ../../framework/hostshim/hs_preinit.mjs ../fw/fw_image.bin hs_route.cjs   # DllMain OOB のチェーン
```

- 逆アセ確認: `objdump -d -M intel --start-address=0x414390 --stop-address=0x4143d0 tools/plugins/work/fw/fw_icall.dll`・同 `0x40ffe0`・`0x40c4d0`。
- 計測用の probe (BLK 値とチェーンの表示) は scratch で、コミットしていない。

## 9. #2534: `function_40c4d0` の入力定数を修復 (InitUnits は idx 18 で止まったまま・止まりの原因を記録)

- 担当 issue: #2534 `[PLG-P0b-19]` (親 #2426)。受入 1 は『止まる次の idx と原因の記録』の後段で満たした (40c4d0 の IR 修復は済・DllMain は未完走)。完走は子 #3355 (`[PLG-P0b-34]`)。受入 2・3 は未到達で子 #3356 (`[PLG-P0b-35]`) へ移し、#2534 の本文から外した。
- 既知類型との関係: 該当なし。§2 と同じ型 (入力 reg を読まず定数に畳む) で、§4 の新類型候補として扱う。`docs/DEFECTS.md` の既知 ID とは照合していない。
- 測定 commit: `b87aa8e6` (e2e・stage-2 の測定。コードを変えた最後の commit・`hs_irfix.py` の `fix_40c4d0` / `fix_40b3f0`)。起点 `origin/main` `8303a813`。§9.3 の probe 実測は `bb2c2a78c` (probe 追加 commit) で行った。差分は §9.8。
- 結論: `function_40c4d0` の rcx (this) と `[rcx]` の読みを、BLK+0x08 と実メモリから読むように直した (`hs_irfix.py` `fix_40c4d0`)。`function_40b3f0` のエントリ引数 (this・flag) も同じ型で直した。それでも DllMain(attach) は `function_40c4d0` で OOB し、InitUnits は idx 18 のまま (unit counter=19/290)。直接原因は、this (`0x10fcbcf0`・非 0) の先頭 (VMT) が 0 で `[vt-0x80]` が境界外になること (§9.3)。旧記録の『this = 0』は本 HEAD の probe では再現せず、訂正する。

### 9.1 実測

環境: 4 vCPU・RAM 15 GiB。素材: `work-fw-stage1`・`work-liftlib` を worktree 直下に展開 (`$ARTIFACTS_DIR` の実在を確認済み)。`fl-win64` は stage-2 と hs e2e の前提に含まれないため展開していない (`fw_stage2.sh` は stage-1 成果物から生成)。emsdk・retdec は runner に既存 (`docs/REFERENCES.md` の `[EMSDK]`・`[RETDEC]`)。load は `/proc/loadavg` の 1 分値 (開始 → 終了)。

| 手順 | commit | 結果 | 所要 (real) | load |
|---|---|---|---|---|
| `fw_stage2.sh` (非 fresh・stage-1 から全生成・n=1) | 8303a813 (stage-2 は本 PR の対象外) | rc 1。`fw_flat4_canon3.ll`・`fw_image.bin` 生成。末尾の `fw_smoke_check` が FAIL (runerr got 1 / expect 0、init_reach got 16 / expect 288)。`SMOKE PASS` (`dispatch=38 units_done=0 va=1 heap=1 ff=0`) は出る | 7 分 10 秒 | 0.76 → 2.28 |
| `fw_stage2.sh` (再現・同じ手順) | b87aa8e6 | rc 1。上と同じ FAIL (runerr 1/0・init_reach 16/288) | 4 分 34 秒 (`time`) | 未記録 |
| `hs_e2e.sh --fresh` (修正 1: fix_40c4d0) | 8303a813 + 修正 | rc 1。Phase A PASS (`dispatch=38 ff=0`)・Phase B `memory access out of bounds`・`plug=0x0 rec=7` | 2 分 38.9 秒 | 未記録 |
| `hs_e2e.sh --fresh` (修正 3: fix_40b3f0 追加・最終) | **b87aa8e6** | rc 1。Phase A PASS (`dispatch=38 ff=0`)・Phase B `memory access out of bounds`・`plug=0x0 rec=7` | 2 分 40 秒 | 0.61 → 0.98 |
| `hs_e2e.sh --fresh` (再現・probe 追加前) | b87aa8e6 と同じ hs コード | rc 1。Phase A PASS・Phase B OOB (`plug=0x0 rec=7`) と同一 | 1 分 32 秒 (`time`・emcc 込み) | 終了時 1 分値 1.14 |
| `hs_preinit.mjs` (最終) | b87aa8e6 | DllMain OOB。チェーン `0x445a40 → 0x43ecb0 → 0x439df0 → 0x43b130 → 0x40c4d0` (wasm `0x4e67d`)。`unit counter=19/290`。`[0x710030]=0x404c00`・`[0x710038]=0x404c10`・`[0x710040]=0x43d940` | 計時なし | 計時なし |
| `hs_probe_40c4.mjs` (§9.3) | bb2c2a78c | DllMain OOB (同じチェーン)。`[0x7165b8]=0x10fcbcf0`・`[this]=0x0`・`[vt-0x80]=-128` | 計時なし | 計時なし |
| `hs_e2e.sh` 増分 n=3 (最終) | b87aa8e6 | 3 回とも rc 1・Phase A PASS・Phase B OOB (`status=0xffffffff plug=0x0 rec=7`) | 344 / 349 / 339 ms (`date +%s%N` 差分) | 計時なし |

- `fw_smoke_check` の FAIL は本 PR の前から起きている (origin/main `8303a813` の stage-2 で再現)。本 PR は hs 経路 (`hs_irfix.py`) だけを変え、stage-2 の生成物 (`fw_flat4_canon3.ll`) は変えない。framework 単体の期待値 (`init_reach=288`) との差は未解決 (§9.5)。

### 9.2 修復 (`hs_irfix.py`)

- `fix_40c4d0` (native `0x40c4d0`: `mov rax,[rcx]`・`movsxd rax,[rax-0x80]`・`lea rsi,[rcx+rax-8]`)。lift は rcx を文字列定数 `@1` (`"$"`・1 byte = 0x24) に畳み、`[rcx]` の読みを定数 `inttoptr -92` (= 0x24 − 0x80) にしていた。修復: `rcx = load BLK+0x08`・`vt = load [rcx]`・`load i32 [vt-0x80]`。`rdx`/`r8` の定数 store (`@2`・`@4`) は関数内で書換えないため消して caller の値を素通しにする。出力 `function_40c4d0 patched`。
- before/after (IR): 修正なし (`fw_flat4_canon3.ll` の `function_40c4d0`・29243〜29246 行) は `ce5 = inttoptr i64 -92` と `ce6 = ptrtoint ptr @1` で、入力に依らず定数の境界外読みになる。修正あり (`hs_flat.ll` の同関数・29245 行) は `rcx = load BLK+0x08` で、実行時の rcx は `0x10fcbcf0` (§9.3)。修正なしの実行は計測していない (IR の比較のみ)。
- `fix_40b3f0` (native `0x40b3f0`: `this=rcx`・`flag=dl`、flag≠0 なら `call 0x40bce0(rcx, rdx=flag)`)。lift は this を `@594`・flag を `@593` ("$") に畳んでいた。修復: this = `load BLK+0x08`、flag = `load i8 BLK+0x10` を entry で 1 回読み、以降の分岐は SSA 値を使う。出力 `function_40b3f0 patched`。
- Phase A (framework smoke) は全修正で `dispatch=38 ff=0` の PASS を維持 (回帰なし)。

### 9.3 直接原因: `function_40c4d0` の this は非 0 で、その VMT が 0

- probe (`hostshim/hs_probe_40c4.mjs`・追跡対象・§9.7): DllMain(attach) を 1 回実行し、例外 (`memory access out of bounds`) の後に読む。
  - 例外の wasm スタック: `function_40c4d0 (wasm-function[355]:0x4e67d)` ← `function_43b130` ← `function_439df0` ← `function_43ecb0` ← `function_445a40` ← `__icall_dispatch` ← `function_40da80`。
  - `unit counter(0x714c98)=19`。
  - `[0x7165b8]=0x10fcbcf0`: `function_43b130` が `call function_40c4d0` の前に rcx として読む this。**0 ではない**。
  - `[0x8a1008]=0x10fcbcf0`: BLK+0x08 (`fix_40c4d0` が rcx に読む caller 格納値)。上と一致。
  - `[this]=0x0`: this の先頭 (VMT 候補) が 0。`[vt-0x80]` は `-128` で、wasm メモリ (`0x14000000`) の外。これが OOB の直接原因。
- 旧記録 (`[0x7165b8]=0`・`[0]=0xa56b6705`) は本 HEAD の probe で再現しなかった。旧 probe は `work/` にのみあって消失しており、差の原因は未特定。
- 未確認 (推定): `0x10fcbcf0` の格納元 (`function_445a40` の `call function_40b3f0` の戻り値) と、その先頭に VMT を書く初期化が行われていないこと。`function_40bce0`・`function_40bd20` の分岐を含めて未検証。
- 定数 `"$"` の生成側の修復は #2510 (`[PLG-P0b-18]`) の範囲。本件は hs 経路の個別修復にとどめる。

### 9.4 受入条件の判定

| 受入 | 結果 |
|---|---|
| 1. `function_40c4d0` の入力定数化を IR 修復で解消・DllMain が InitUnits を完走 (unit counter=290) か、止まる次の idx と原因を記録 | 満たした (後段の『止まる次の idx と原因の記録』)。40c4d0 の IR 修復は済 (`fix_40c4d0`)。完走は未達 (idx 18 で停止・unit counter=19)。止まりの原因は §9.3 (this 非 0・VMT 0)。完走は子 #3355 へ |
| 2. `function_40ffe0` の `jne` 分岐落ちを確認し、native 戻り値と hs 経路 r8 を実測で比べる | 未達 (未到達)。InitUnits が idx 18 で止まるため hs 経路で `function_40ffe0` に到達しない。動かしていない。子 #3356 へ (本文から外した) |
| 3. InitUnits 完走後、同一 instance で Phase B を実行し `plug != 0` を n≥3 で示す | 未達。Phase B は n=3 とも `plug=0x0` で OOB。子 #3356 へ (本文から外した) |

### 9.5 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_40b3f0` → `40bce0`/`40bd20` の戻り値と、this (`0x10fcbcf0`) の VMT が 0 になる経路 (§9.3・推定・未検証)。entry 引数の "$" 畳み込み (`@578`・`@579`・`@593`・`@594`) | InitUnits idx 18 の完走 (受入 1 の後段・3) | 子 #3355 (`[PLG-P0b-34]`)。this=0 の前提が誤りだった点を #3355 にコメントで訂正。生成側は既存 #2510 |
| `function_40ffe0` の `jne` 分岐落ちと r8 の値の実測 | 受入 2 | 子 #3356 (`[PLG-P0b-35]`) |
| InitUnits 完走後の Phase B `plug != 0` (n≥3) | 受入 3 | 子 #3356 (`[PLG-P0b-35]`) ([PLG-P0b-34] 完了後) |
| `fw_stage2.sh` の `fw_smoke_check` FAIL (runerr 1/0・init_reach 16/288) | framework 単体の照合が red。本 PR の変更とは無関係 (8303a813 で再現・§9.1) | 親 #2426 への提案 (#2426 にコメントで提案。未解決の追跡だけの子は起票しない) |

### 9.6 製品 KPI (起動経路の変更)

| 指標 | 前 | 後 (b87aa8e6) |
|---|---|---|
| FLEngine 起動 dispatch 数 (Phase A `dispatch=`) | 38 (§1 a63e33ab 実測。本 run の 8303a813 の stage-2 smoke でも 38) | 38 |
| 通過 unit 数 (InitUnits `unit counter`) | 19 / 290 (§1 と同じ idx 18 で停止) | 19 / 290 (変化なし) |
| 最初のウィンドウ | なし (`plug=0`) | なし |

### 9.7 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
mkdir -p $RUNNER_TEMP/fl-win64 && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst   # repo ルートで展開
bash tools/plugins/framework/fw_stage2.sh                        # 非 fresh で stage-2 を生成 (rc 1 は §9.5 の smoke_check FAIL)
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh           # Phase A PASS・Phase B OOB
cd tools/plugins/work/hs && node ../../framework/hostshim/hs_probe_40c4.mjs ../fw/fw_image.bin hs_route.cjs   # §9.3 の this・VMT・[vt-0x80]
```

- 逆アセ: `objdump -d -M intel --start-address=0x40c4d0 --stop-address=0x40c540 tools/plugins/work/fw/fw_icall.dll`・同 `0x40b3f0`・`0x445a40` (`0x445b06` の `0x7165b8` 格納)・`0x43b130` (`0x43b17e` の `0x7165b8` 読み)。

### 9.8 コード差分 (測定 commit 以降)

- 測定 commit `b87aa8e6` から HEAD までの差分 (`git diff b87aa8e6 HEAD -- tools/plugins/framework ':!*.md'`) は `hostshim/hs_probe_40c4.mjs` の 38 行追加 (診断専用)。`hs_e2e.sh`・`fw_stage2.sh`・`hs_irfix.py` からは参照されないため、§9.1 の e2e 実測は有効。
- `REPORT_2426.md` の差分は `*.md` のため上の出力に含まれない。
