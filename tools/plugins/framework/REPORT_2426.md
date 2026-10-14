# #2426 REPORT — hs InitUnits の OOB 1 件目 `function_414390` の入力定数化を修復 (次の OOB は `function_40c4d0`)

- 担当 issue: #2426 `[PLG-P0b-17]` (親 #2008)。受入 1 を達成し、受入 2・3 は子 #2534 へ移管。
- 測定 commit: `11096d29` (コード変更を含む最後の commit)。起点 `origin/main` `54bacdc0`。
- 既知類型との関係: 該当なし。`docs/DEFECTS.md` D21 (呼出し側の引数値がスタック番地の下位 byte になる) とは別型。本件は「被呼出し側が入力レジスタを読まず、RetDec が定数 `ptrtoint @G` / `inttoptr <const>` に畳む」型で、既存 ID とは照合していない (§4 の新類型候補)。
- 結論: `function_414390` (wide string copy) の OOB の直接原因 (入力 rcx/rdx/r8 の定数化) を特定し、hs 経路の IR 修復 `hs_irfix.py` `fix_414390` で解消した。OOB は同 unit (InitUnits idx 18) 内の `function_40c4d0` へ移動し、InitUnits は完走しない。`plug` は依然 0。

## 1. 実測

環境: 4 vCPU・RAM 15 GiB。素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`) に展開、`work-fw-stage1`・`work-liftlib` を worktree 直下に `tar --zstd -xf` で展開 (`$ARTIFACTS_DIR` の実在を確認済み)。load は `uptime` の 1 分値 (開始 → 終了)。

| 手順 | commit | 結果 | 所要 (real) | load |
|---|---|---|---|---|
| `fw_stage2.sh` (非 fresh・stage-1 から全生成・n=1) | 54bacdc0 (stage-2 は本修正の対象外) | rc 0・`SMOKE PASS` (`dispatch=38 units_done=0 va=1 heap=1 ff=0`) | 7 分 41 秒 | 1.00 → 2.53 |
| `hs_e2e.sh --fresh` (修正前・baseline) | 54bacdc0 | rc 1・Phase A PASS (`dispatch=38 ff=0`)・Phase B `memory access out of bounds`・`plug=0x0 rec=7` | 2 分 15.4 秒 | 2.33 → 1.20 |
| `hs_preinit.mjs` (修正前) | 54bacdc0 | DllMain(attach) OOB。チェーン `0x445a40 → 0x415220 → 0x414de0 → 0x414390`。`unit counter=19`。プロセスは `exit(103)` | 計時なし | 計時なし |
| `hs_e2e.sh --fresh` (修正後) | 11096d29 | rc 1・Phase A PASS・Phase B OOB・`plug=0x0 rec=7` | 2 分 16.1 秒 | 0.26 → 0.93 |
| `hs_preinit.mjs` (修正後) | 11096d29 | DllMain OOB。チェーン `0x445a40 → 0x43ecb0 → 0x439df0 → 0x43b130 → 0x40c4d0`。`unit counter=19` | 計時なし | 計時なし |
| `hs_e2e.sh` 増分 (修正後) n=3 | 11096d29 | 3 回とも rc 1・Phase A PASS・Phase B 同一 (`plug=0x0 rec=7`) | 339 / 344 / 343 ms (`date +%s%N` 差分) | 0.93 (開始) |

- `fresh` は n=1 (60 分の上限内に収めるため)。n≥3 のレンジは未取得 (増分のみ n=3)。
- `hs_preinit.mjs` の Phase B 行は DllMain 例外の後に同一 instance で実行するため、`plug`/`rec` の値は参考外 (修正後の出力は `Maximum call stack size exceeded`)。Phase B の判定は `hs_e2e.sh` 側の結果を正とする。
- 修正前後の差 (negative control): 修正前は OOB が `function_414390` で起きる (baseline 実測)。修正後は `function_414390` の OOB が消え、同じ unit の `function_40c4d0` で起きる。Phase A は両方で PASS (回帰なし)。

## 2. 直接原因: `function_414390` の入力が定数に畳まれている

- native (`objdump -d -M intel fw_icall.dll`、VA `0x414390`): `test edx,edx` → `movzx rax,WORD PTR [r8]` → `mov [rcx],ax` → `add rcx,2`・`add r8,2`・`sub edx,1`・`jg`。wcsncpy 相当で、rcx = dst、edx = count、r8 = src を入力として読む。
- 呼出し側 `function_414de0` (native `0x414e47 call 0x414390`): 直前に dst を BLK+0x08 (rcx)、count `261` (`0x105` = MAX_PATH+1) を BLK+0x10 (rdx)、src を BLK+0x18 (r8) へ格納する (hs IR の該当行 57585〜57588 相当)。
- lift IR (`hs_flat3.ll`・`fw_flat4_canon3.ll` の `function_414390`、同型): BLK+0x08/+0x10/+0x18 を読まず、`ptrtoint ptr @673 to i32` (count)・`@674` (dst)・`@675` (src) を使う。`and(@673,@673) != 0` は常に真。count がアドレス値 (大きい正数) になるため、loop は src の 0 文字まで読み続け、wasm の線形メモリ (上限 `0x14000000`) の外へ出る。
- 観測: 修正前の `hs_preinit.mjs` は `function_414390` で `memory access out of bounds` を出す。`BLK+0x08/+0x10/+0x18` の実値は `rcx=0x118b5f86`・`rdx=0x105`・`r8=0x10fcab90` (r8 は空文字)。count の 261 が lift では使われていないことが直接の原因。

## 3. 修復 (`hs_irfix.py` の `fix_414390`)

- 10 規則。各規則は置換 1 件を assert し、件数が違えば `exit 1` (`hs_irfix.py` の既存方針と同じ)。定数名 (`@673/@674/@675`) は body から実行時に読む (lift 版ごとに RetDec が振り直すため)。置換後に旧定数が残らないことも確認する。
- 修正後の入力: count = `load i32` (BLK+0x10)、dst = `load i64` (BLK+0x08)、src = `load i64` (BLK+0x18)。`store i16 0` の dst も BLK+0x08 から。
- 出力: `[hs_irfix] function_414390 patched: 入力 rcx=@674 rdx=@673 r8=@675 を BLK+0x08/+0x10/+0x18 から読む` (`hs_e2e.sh --fresh` の実ログ)。
- 対象は hs 経路 (`hs_irfix.py`) のみ。stage-2 の canonical IR (`fw_flat4_canon3.ll`) の `function_414390` は同型の定数 fold が 9 箇所あるが未修正 (§5、#2510 の範囲)。

## 4. 次の OOB: `function_40c4d0` と `function_40ffe0` の疑い (未修正)

- `function_40c4d0` (native `0x40c4d0`): `mov rax,[rcx]`・`movsxd rax,DWORD PTR [rax-0x80]` (VMT の負オフセット参照)。lift IR は `inttoptr i64 -92` の `load i32` になっており、wasm では `2^32-92` の境界外アドレス。入力 rcx (this) の読みが定数に畳まれた疑い (未検証)。修正後の `hs_preinit.mjs` の wasm スタック上端は `function_40c4d0 (wasm-function[355]:0x4e62e)`。
- `function_40ffe0` (r8 の出所): native は `mov rax,rcx`・`test rax,rax`・`jne 0x40fff3` (shared `ret`)、その後に `mov rax,[0x6d5c20]`・`lea rax,[rax+0x10]`・`ret`。すなわち `rcx != 0` なら `rcx`、`rcx == 0` なら `[0x6d5c20]+0x10` (native の該当値 `0x40f81c` は空文字)。lift 版は `jne` の分岐を落として `call function_40fff3()` を無条件に行い、戻り値を BLK+0x80 経由で受ける規約。hs IR の `function_40fff3` は `fw_hs_scratch(64)` の戻り値を BLK+0x80 に入れる (`hs_flat3.ll` 868〜873 行)。そのため `r8` は scratch 由来 (`0x10fcab90`・空文字) で、native の `0x40f81c` とは値が違う。今回は空文字だったので OOB にはならなかったが、正しさは未検証。
- 新類型候補 (PM 判断): 「被呼出し側の入力レジスタを読まず、RetDec が定数 (`ptrtoint @G`・`inttoptr <const>`) に畳む型」。`hs_irfix.py` の `fix_414390` は 1 関数ごとの手当てで、一般化はしていない。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_40c4d0` の入力定数化 (`inttoptr -92`) で idx 18 の Init が完走しない | 受入 2・3 (InitUnits 完走・Phase B `plug != 0`) | 子 #2534 `[PLG-P0b-19]` |
| `function_40ffe0` の `jne` 分岐落ちと戻り値規約 (r8 が scratch 由来) | 空文字で無害の見込みだが未検証。値の一致は未確認 | 子 #2534 (受入 2) |
| stage-2 canonical IR の `function_414390` 同型の定数 fold (9 箇所・hs 経路のみ修正) | 非 hs 経路の同一関数が未修正 | 既存 #2510 (`"$"` 定数 fold の生成側修復) に追記 |
| fresh の所要 n≥3 レンジ未取得 (n=1) | 受入 3 の n≥3 | 子 #2534 (受入 3) |
| `hs_preinit.mjs` の Phase B は DllMain 例外の後に同一 instance で走るため判定に使えない | 観測の解釈 | 子 #2534 に併記 (修正は子の範囲) |
| #2425 (stage-2 の idx 16 基準の再定義) | Phase A の `dispatch=38` の意味 | 既存 #2425 (open・本件の依存ではない) |

## 6. 検証範囲 / 範囲外

- 範囲: hs 経路 (`hs_e2e.sh`・`hs_preinit.mjs`) の DllMain(attach) から InitUnits idx 18 の途中まで。
- 範囲外: Phase B の `plug != 0` (未達)、InitUnits 完走 (未達)、stage-2 canonical IR の修復 (未実施)。
- Phase A の回帰は毎回 `dispatch=38 ff=0` で PASS を確認 (§1)。

## 7. コード差分 (測定 commit 以降)

測定 commit `11096d29` は HEAD のコード状態。以降の差分は本 REPORT と `docs/DOC_MAP.md` の登録行のみ (コード 0 行)。

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
