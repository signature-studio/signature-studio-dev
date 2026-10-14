# #2425 REPORT — Phase A の `dispatch=38` 基準を InitUnits 完走基準に再定義 (idx 16 の fold は未修復・子へ移管)

- 担当 issue: #2425 `[PLG-P0b-16]` (親 #2008)。
- 既知類型との関係: `docs/DEFECTS.md` D21 (呼出し引数の値が `ptrtoint %stack_var` の下位 byte に化ける) と**同型の可能性あり・未確認**。本 run の観測は「呼出し引数 (BLK+8) が `ptrtoint ptr @342` (`"$"` 定数の番地) に化ける」。D21 の機構 (dl=0 仮説) とは直接対応を確認していない。REPORT_2008 §8.3 の「RTL 未初期化」候補とは別経路の観測。
- **結論 (1 行)**: 受入 2 (基準の再定義・旧基準の事実の記録) と受入 3 (n=3 実測) は達成。受入 1 (idx 16 の RunError を消す) は**未達**で、子 `[PLG-P0b-18]` (番号は起票後に確定) へ移管し issue 範囲を縮めた。新基準では stage-2 smoke が **FAIL** になる (旧基準の偽 PASS を外した結果。§4)。

## 0. 検証起点と測定 commit

- 検証起点: `origin/main` `54bacdc0` (worktree `../ws-2425`・branch `2425-plg-p0b-16-init-units`)。
- 測定 commit (コードを変えた最後の commit): `980dfcff` (`fix(plugins): smoke gate を InitUnits 完走基準に再定義 (#2425)`)。
- 素材: `work-fw-stage1` を `tools/plugins/work/fw/` に、`work-liftlib` を `tools/liftlib/work/` に展開 (gitignore。`tar --zstd -xf`)。`toolchain-emsdk` / `toolchain-retdec` は runner の `/opt/emsdk`・`/opt/retdec` が既に存在したため展開しなかった (`/opt/emsdk/emsdk_env.sh`・`/opt/retdec/bin/retdec-decompiler` の存在を確認)。`fl-win64` は stage-2 (`fw_icall.dll` 起点) が使わないため展開していない。

## 1. 旧基準 (`dispatch=38`) の中身 — 受入 2 の「旧基準が RunError 終端だった事実」

変更前 (`54bacdc0` の tree) の `fw_stage2.sh` 増分実行で得た `smoke.log` (42 行) の要点:

| smoke.log 行 | 内容 |
|---|---|
| 21 | `[dispatch] site=0x40dae6 -> target=0x43db30` (InitTable idx 16 の Init) |
| 22 | `[dispatch] site=0x40701e -> target=0x405670` (`_GetMem` の FastMM 関数ポインタ呼出) |
| 23 | `[fw][MessageBoxA] Error: Runtime 268436792 at 0000000010000710` (RunError。Delphi の `Runtime error N at ADDR` の書式) |
| 24〜39 | `[dispatch] site=0x40da42` が FInit 系 (0x43db50・0x4423c0・… 0x419890) を逆順に 16 件呼ぶ |
| 40 | `[fw][RestoreContext] SEH unwind 到達 — 初期化シーケンス終了扱い (m11 方式)` |
| 41 | `Aborted(Runtime error: The application has corrupted its heap memory area (address zero)!)` |
| 42 | `[fw] SMOKE PASS (Halt0/RestoreContext 到達): dispatch=38 units_done=0 va=1 heap=1 ff=0` |

- 旧判定 (`fw_smoke_check.py` の `DEF_EXPECT`) は PASS の**終端** (`Halt0/RestoreContext 到達`) だけを見ていた。RunError は終端経路の途中で出るため、PASS 行は RunError を含んでも出る。`dispatch=38` は InitUnits の完走を示さない。
- `[dispatch]` 行数は 33 (`grep -c '^\[dispatch\]'`)。`fw_dispatch_count()` の 38 との差 5 は、trace に出ない経路の呼出 (未調査)。
- 別の見方: `units_done=0` (0x714C98 の u32) は、idx 0〜16 の Init が dispatch されたのに 0 のまま。この counter は stage-2 では InitUnits の進捗を表さない (未調査)。

## 2. IR 上の fold 位置 — 受入 1 の「原因 IR 行を特定する」

対象: `tools/plugins/work/fw/fw_flat4_canon3.ll` (stage-2 の canon3 IR。`fw_stage2.sh` 成果物・gitignore)。`@153`・`@342`・`@344`・`@498`・`@499` は全て `[2 x i8] c"$\00"` (`"$"` の定数文字列) の internal constant (239・428・430 行など)。

| 関数 (IR 行) | 行 | 観測 |
|---|---|---|
| `function_40ea20` (38125〜) | 38146〜38155 | 分岐条件 (`%cenh1664`) が `ptrtoint ptr @342 to i32` の and/icmp だけで決まる (定数の分岐)。native の `test` 対象の値が定数に化けている |
| 同 | 38158〜38163 | BLK+8 (`0x8A1008` = 9048072) に `inttoptr (zext (ptrtoint @342))` を格納し、BLK+0x10 に `@344`、BLK+0x18 に `@342` を格納 |
| 同 | 38178 | `call i64 @function_40e5e0()` (引数は BLK 経由) |
| `function_40e5e0` (36978〜) | 36997〜37005 | `%ce5n11 = ptrtoint ptr @153 to i32` と `%ce0n12 = ptrtoint ptr @153 to i32` の `and`・`icmp` が分岐 `%cenh1592` (37005) を決める。長さ判定が `"$"` の番地で決まる |
| 同 | 37022〜37025 | `%cenh1597` (37022) で分岐し、`dec_label_pc_7bb677` (37025) で BLK+8 ← `@153`、BLK+0x10 ← `@154`、BLK+0x18 ← `@152` を格納し、`function_40af70` を呼ぶ |
| `function_407010` (8724〜) | 8742 | 関数先頭の `%cenh258 = icmp sge ptr @499, null` が分岐を決める (GetMem の入口。BLK+8 = `@499` の番地を前提)。分岐先 `dec_label_pc_7a5b01` (8745) で BLK+8 ← `@499` を格納 |
| `function_40e400` (Error。36388〜) | — | RunError の出力経路。直接の呼出元は IR 9611・36466・140441 行 |

- 観測の要点: 呼出引数 (BLK+8) が、native の値 (Delphi 文字列の長さ・ポインタ) ではなく `"$"` 定数の番地として IR に入る。このため `function_40e5e0`・`function_407010` の分岐は定数で決まり、`function_40e400` の RunError 経路に入る。RunError の引数 `268436792` (= 0x10000538 相当) と `0x10000710` (`@153` の番地) も同じ fold 由来と推定 (推定。未検証)。
- **最初の fold 点** (この call chain 内で観測した範囲): `function_40ea20` 38146〜38163 行。これより上流 (呼出元 `function_417bc0`・`function_43c780`・`function_43d9a0`) で `"$"` の番地が BLK+8 に入るかは未検証。REPORT_2008 §8.3 の chain (`0x43db30 → 0x43d9a0 → 0x43c780 → 0x417bc0 → 0x40ea20 → 0x40e5e0`) は scratch 観測で、今回の IR の直接 call (`417bc0` 34448 行・`43c780` 90943 行・`40ea20` 11530 行など) と整合するかは確認していない。
- 修復はこの run では行わない。scratch の override (`fw_hostfix.py` 型の戻り値差し替え) は silent miscompile を隠すため、受入 1 の「修復」とは認めない。

## 3. 旧基準を外した新基準 — 受入 2

`fw_smoke_check.py` (`980dfcff`) の既定期待値:

| キー | 定義 (独立に `smoke.log` と `fw_image.bin` から再計算) | 期待値 |
|---|---|---|
| `runerr` | `[fw][MessageBoxA] Error: Runtime N at ADDR` 行の件数 | 0 |
| `ff` | `fw_ff_count()` (PASS 行の `ff=`) | 0 |
| `init_reach` | InitTable (`fw_image.bin` の VA `0x6c1460`、16 byte/entry、先頭が Init。290 件中 Init 非 0 は 289 件) の Init 値のうち、最初の RunError より前に `[dispatch]` の target として現れた最大 unit idx | 288 (= 最後の Init 非 0 の idx) |
| 情報 | `dispatch` / `units_done` / `va` / `heap` (ゲートしない。§1 の数え方) | — |

- `init_reach` は `[dispatch]` (間接呼出) だけを数えるため**下限**。直接呼出の Init は数えない。今回の log では idx 14 の Init (`0x6d6e78`) が trace に出ず、連続到達は 13 だが、本基準は最大 idx (16) を使う (連続値 13 は別途の参考)。
- PASS 行が無い場合は従来どおり FAIL。

### 3.1 ネガティブコントロール (数値)

| 入力 | 判定 | 結果 |
|---|---|---|
| 測定 commit の実 `smoke.log` (42 行) | 既定 (runerr=0 ff=0 init_reach=288) | **FAIL** (runerr=1 MISMATCH・init_reach=16 MISMATCH・ff=0 OK) rc=1 |
| 同じ log から `MessageBoxA` 行 (1 件) を除いた `smoke_nc.log` (41 行) | `--expect runerr=0 ff=0 init_reach=16` | **PASS** (runerr=0 OK・init_reach=16 OK) rc=0。RunError 1 件を取り除くと runerr が 1→0 に変わることを確認 |

## 4. stage-2 gate の状態 (新基準の影響)

- 新基準では、現在の stage-2 (`fw_stage2.sh`) の最終 smoke 判定が **FAIL (rc=1)** になる。これは旧基準の偽 PASS を外した結果で、InitUnits 完走 (受入 1) が未達である事実と一致する。
- 下流: `hs_e2e.sh` は `fw_stage2.sh` の**終了コードではなく**成果物の存在を前提にしている (`[ -f "$WFW/$f" ]` の確認)。`fw_269_verify.sh` は `&&` で rc を記録するだけ (期待値は既定を使う)。CI の `.github/workflows` には `fw_stage2` の参照が無い。
- 受入 1 が達成されれば、同じ判定器で PASS に戻る (`runerr=0`・`init_reach` は本 run の trace では 16 のまま)。

## 5. 実測 — 受入 3 (n≥3)

環境: runner 4 vCPU・15 GiB。load は `/proc/loadavg` の 1 分値 (開始 → 終了)。

| 手順 | commit | 結果 | 所要 (real) | load (開始 → 終了) |
|---|---|---|---|---|
| `fw_stage2.sh` (変更前・増分。steps 1〜16 の中間物は無い状態から再生成・emcc・smoke) | `54bacdc0` | rc 0・`SMOKE PASS` (旧基準 `dispatch=38`) | 5 分 58.8 秒 (14:34:05 → 14:40:04) | 終了時 1 分値 2.78 (開始時は未記録) |
| `fw_stage2.sh` 増分 (`fw_route.cjs`・`fw_route.wasm` を消し emcc + smoke のみ)・n=1 | `980dfcff` | rc 1 (新基準 FAIL: runerr=1・init_reach=16) | 24.55 秒 | 0.04 → 0.37 |
| 同 n=2 | `980dfcff` | rc 1 (同上) | 24.03 秒 | 0.37 → 0.59 |
| 同 n=3 | `980dfcff` | rc 1 (同上) | 23.94 秒 | 0.59 → 0.73 |

- n=3 のレンジ: **23.94〜24.55 秒** (増分)。3 回とも判定結果は同一 (runerr=1・init_reach=16・ff=0・wasm 15,062,043 B)。
- 変更前の行 (54bacdc0) は中間物の再生成を含む 1 回の実測で、増分の n は取っていない。増分の比較対象は無い。
- wasm サイズ: 15,062,043 B (`fw_route.wasm`)。既定では照合しない (`--size` 未指定)。

## 6. コード差分 (測定 commit 以降)

測定 commit `980dfcff` 以降のコード変更は無し (本 REPORT の追加のみ)。

```sh
git diff 980dfcff HEAD -- tools/plugins/framework ':!*.md'   # 空 = 実行コード差分 0
```

- 出力は空 (本 REPORT の commit 後に実行して確認する。`*.md` の差分は文書のみ)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1: `function_40ea20` 38146〜38163 行の `"$"` 番地の fold の上流 (呼出元で BLK+8 に入る経路) と、それを生成側で直す修復 | idx 16 で RunError → InitUnits 未完走 (`runerr=1`) | 子 `[PLG-P0b-18]` (本 PR の後に起票。`親: #2425`) |
| `init_reach` が間接呼出の下限 (idx 14 の Init `0x6d6e78` が trace に出ない) | 到達 idx の正確な値が取れない | 子 `[PLG-P0b-18]` の受入 (直接呼出の計測を含める) |
| `dispatch=38` と `[dispatch]` 行 33 の差 5 / `units_done=0` の意味 | 旧基準の内訳が未確定 | 本 REPORT §1 (未調査。修復に直結しないため子は起票しない) |
| idx 18 (`0x445a40`) の OOB と Phase B の `plug != 0` | 受入の本体 (hs ビルド) | 既存 #2426 (`[PLG-P0b-17]`) |

## 8. 再現手順

```sh
git worktree add ../ws-2425 -b 2425-plg-p0b-16-init-units origin/main   # (済)
cd ../ws-2425 && tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64          # stage-2 本体は fw_icall.dll (work-fw-stage1) を使う
bash tools/plugins/framework/fw_stage2.sh          # 初回は中間物を作る (§5 の 5 分 58.8 秒)。最後の smoke 判定が FAIL で rc 1
cd tools/plugins/work/fw && rm -f fw_route.cjs fw_route.wasm && bash ../../framework/fw_stage2.sh   # 増分 (§5 の 23.94〜24.55 秒)
python3 ../../framework/fw_smoke_check.py --log smoke.log --image fw_image.bin                        # 新基準の判定
grep -n 'MessageBoxA' smoke.log                                                                         # RunError の行 (23 行)
```

## 9. 検証範囲 / 範囲外

- 範囲内: stage-2 増分 (emcc + smoke) の n=3、`smoke.log` の 1 本からの判定器の再計算、RunError 行を除いたネガティブコントロール、IR の行番号の特定。
- 範囲外: 修復 (受入 1)、hs ビルド (`hs_e2e`)、Phase B、`fl-win64` を使う処理、フル fresh 再生成の n≥3 (変更前の 1 回だけ実測)。
- 本 REPORT の IR 行番号は測定 commit の生成物 (`fw_flat4_canon3.ll`・85,532,545 B) に対するもの。生成物は gitignore のため再生成が要る。
