# #3120 REPORT — stage-2 smoke の InitUnits 中の `Runtime error 203 at 0x1` は未解決 (発生経路を静的に絞った。BLK 修正との因果は未切り分け) [PLG-P0b-29]

- 担当 issue: #3120 `[PLG-P0b-29]` (親 #2566)。前回の作業は PR #3123 (枝 `2566-plg-p0b-21-relift`・2026-10-14 22:34:15Z に merge 済み・merge commit `31334810`)。その修正 commit `66a3dbe1` (`fw_entry_fix.py` の新形 fallback) は、この merge で `origin/main` に入っている。本 PR の測定 commit `77205e76` は同じ内容の再 cherry-pick で、`origin/main` に対する `fw_entry_fix.py` の差分は 0。本 PR の実質の追加は REPORT と DOC_MAP の登録のみ。
- 既知類型との関係: `docs/DEFECTS.md` に該当 ID なし。`REPORT_2510.md` §6 の D24 候補 (BLK slot の constant 化) とは別の失敗 (エラーの種類・番地が変わった)。

## 0. 結論 (1 行)

stage-1 を BLK 修正後の `icall_rewrite` で再生成し stage-2 を再現すると、smoke は `Runtime error 203 at 0x1` (InitUnits 中) で FAIL のまま (`runerr=1`・`init_reach=13`)。修正前素材の `Runtime 268436792 at 0x10000710` (`init_reach=16`) とは別の失敗に変わった。エラーの書込み元 (BLK+0x10 = 203・BLK+0x8 = 1) は静的 IR で絞ったが、書込み元は未特定。受入 1 は未達 (子 [PLG-P0b-31] へ)。

## 1. 検証起点と測定 commit

- 測定 commit: **`77205e76`** (測定時の `origin/main` である `c98d2c99` に `66a3dbe1` を cherry-pick した commit。worktree `../ws-3120`・branch `3120-plg-p0b-29-stage2-smoke`)。
- 素材: `work-fw-stage1` と `work-liftlib` を展開 (gitignore)。`fl-win64` は member 2 本 (`extracted/block18983_PE.bin`・`extracted/block00031_PE.bin`) のみ展開。`[EMSDK]`・`[RETDEC]` (`docs/REFERENCES.md` §1「ローカルツール」) は runner 既存。
- 補助物: `tools/plugins/work/fw_hash_counts.json` は `{}` で代用 (`REPORT_2566.md` §1 と同じ。framework 統計の出力のみに影響)。
- 修正前素材の比較: `work-fw-stage1` を `$RUNNER_TEMP/pre_root` に展開し、`FW_W` で stage-2 を独立に再実行 (`#2584` より前に生成された stage-1 成果物)。
- 実行環境: runner 4 vCPU・RAM 15 GiB。

## 2. 実測 (n=1・測定 commit `77205e76`)

| 手順 | 結果 | 所要 (real) | load (1 分値・終了時) |
|---|---|---|---|
| `fw_prep.py` | rc 0・`F.ranges` 11,736 件 | (未計測) | — |
| `icall_rewrite.py` (BLK は `8a1000`) | rewrote 11,736 funcs / 6,159 sites・`errors {}`・section +5,924,861 B | (未計測) | — |
| `fw_lift.sh` (stage-1・RetDec 8 chunk) | rc 0・`fw_all.restored.ll` 11,939 defines | 5 分 50 秒 | 1.19 (終了時) |
| `fw_stage2.sh --fresh` | rc 1・`entry_fix r8=1 r9=1`・`_StartLib hinst=0x400000 reason=1`・`Runtime error 203 at 0x1`・`fw_smoke_check` FAIL | 9 分 30 秒 | 2.59 (終了時) |

`fw_smoke_check.py` の判定: `runerr=1` (expect 0)・`ff=0` OK・`init_reach=13` (expect 288)。wasm 16,445,681 B (照合なし)。

- `smoke.log` の該当行: 1 行目 `[fw][ov] _StartLib ... hinst=0x400000 reason=1` (入口修正は効いている)。27 行目 `[fw][MessageBoxA] Error: Runtime error 203 at 0000000000000001`。
- 27 行目の直前 (22 行目): `[dispatch] site=0x40701e -> target=0x405670`。その後 27 行目で Error、28 行目以降は InitUnits が続き (`site=0x40da42` の dispatch が続く)、`RestoreContext` で終了。
- 47 行目以降は `Aborted(Assertion failed: native function ... called after runtime exit)` が 4 件出て、`dispatch / va / heap / ff` の情報値が 0 になった (本 run のみ。原因は未調査)。

## 3. 修正前素材との比較 (受入 3・n=1)

| 項目 | 修正前素材 (`#2584` より前の stage-1) | 測定 commit `77205e76` |
|---|---|---|
| stage-2 `--fresh` | rc 1・8 分 37 秒 | rc 1・9 分 30 秒 |
| RunError | `Runtime 268436792 at 0000000010000710` | `Runtime error 203 at 0000000000000001` |
| `runerr` / `ff` / `init_reach` | 1 / 0 / **16** | 1 / 0 / **13** |
| 情報値 `dispatch` / `va` / `heap` | 38 / 1 / 1 | 0 / 0 / 0 (§2 の after-exit) |
| wasm (B) | 15,053,868 | 16,445,681 |

- 失敗の種類と番地が変わった。失敗する InitTable idx は 16 → 13 に前倒しされた。
- **切り分けは未了**: 2 つの素材の差は (a) BLK 配置 (`#2584`)、(b) stage-1 の再生成 (`icall_rewrite.py` の他の変更を含む。セクションは約 0x45970 B 伸びた)、(c) `entry_fix` の新形 fallback (`66a3dbe1`) の 3 つが同時に入っている。この 1 組の比較では (a)〜(c) を分けられない。

## 4. エラーの経路 (静的 IR・`fw_flat4_canon3.ll`・未検証)

| 関数 (定義行) | 内容 |
|---|---|
| `function_4072b0` (10019) | 10041 行で `store i64 %1, ptr inttoptr (7155720)` (`%1` = BLK+0x10 `9048080` の load = **エラーコード**)。10043 行付近で BLK+0x8 `9048072` の load (`%0`) を 7155712 側へ渡し、10062 行で `call function_40e400` |
| `function_40e400` (39434) | BLK 各 slot を読み直し、`function_40e270` (Halt 系) を呼ぶ。MessageBoxA の `Runtime error N at ADDR` 表示はこの経路 (`fw_rt.c` 145 行の shim) |
| `function_40e420(i64 %arg1)` (39490) | `arg1` を 7155720 へ格納して 40e400 を呼ぶラッパー。呼出元 6 箇所 (35804・36230・36380・36632・83483・83553) は観測経路に現れない |
| `function_4072b0` の呼出元 | 9564 行 (`function_4070f0` の内・定義 9397 行)・10232 行 (`function_4072d0` の内・定義 10074 行)・19735 行 |
| `function_407010` (8916) | 動的 trace の `site=0x40701e` (`__icall_dispatch(4223006)`) はここ。target `0x405670` (`function_405670`・2384 行) |

- 動的 trace では `0x40701e → 0x405670` の直後に Error が出る。Error に至る静的な呼出し辺は `4070f0` (9564 行) → `4072b0` (10019 行) → `40e400` (39434 行) が候補。**この辺は動的には確認していない** (`4072b0` の呼出しは direct call で dispatch 行に出ないため)。
- エラーの 203 は BLK+0x10 の値、`at 0x1` は BLK+0x8 の値 (`trunc` で 7155712 側へ) と読める。**この 2 slot の書込み元は未特定** (子 [PLG-P0b-31]。書込みを追うには `ir` の store 検索と、`0x40701e` 直後の BLK 値のダンプが要る)。

## 5. 受入条件の状態 (issue #3120)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. smoke `runerr=0 ff=0 init_reach=288` PASS | **未達** | §2 (`runerr=1`・`init_reach=13`) |
| 2. `Runtime error 203 at 0x1` の発生箇所 (呼出元・IR 行) を特定し、BLK 配置変更が原因か既存欠陥かを切り分ける | **部分** | 発生経路は §4 (静的)・書込み元は未特定。切り分けは §3 の (a)〜(c) が同時に入るため未了 → 子 [PLG-P0b-31] |
| 3. 修正前 artifact との比較を 1 本 | **達成 (n=1)** | §3 |

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `BLK+0x10 = 203`・`BLK+0x8 = 1` の書込み元 (InitUnits 中の 203 の発生源) | smoke PASS 不可 (受入 1) | 子 **[PLG-P0b-31]** (`親: #3120`) |
| (a) BLK 配置・(b) stage-1 再生成・(c) entry_fix fallback の切り分け | 修正の副作用の判定不能 (受入 2) | 子 **[PLG-P0b-31]** |
| after-exit assertion で情報値 (`dispatch`/`va`/`heap`) が 0 になる (§2) | 観測の欠落 | 子 **[PLG-P0b-31]** |
| 受入 2 の 123 行内訳・受入 3 (`init_reach` の直接呼出)・受入 4 (n≥3)・受入 5 (RetDec が BLK slot を constant にする機構) | 修復効果の確定 | #3121 (既存・`親: #2566`) |

## 7. 再現手順

基点は測定時の main `c98d2c99`。現 `origin/main` は `66a3dbe1` を含むため、そこからの cherry-pick は空になって失敗する。

```sh
git worktree add ../ws-3120 -b 3120-plg-p0b-29-stage2-smoke c98d2c99
cd ../ws-3120 && git cherry-pick 66a3dbe1
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftlib.tar.zst
D=$RUNNER_TEMP/fl-win64; mkdir -p $D && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $D extracted/block18983_PE.bin extracted/block00031_PE.bin
echo '{}' > tools/plugins/work/fw_hash_counts.json
FL_WIN64_DIR=$D python3 tools/plugins/framework/fw_prep.py
cd tools/plugins/work/fw && python3 ../../../icall/icall_rewrite.py --pe $D/extracted/block18983_PE.bin --funcs F.ranges --out fw_icall.dll --map fw_map.json
cd ../../../.. && FL_WIN64_DIR=$D bash tools/plugins/framework/fw_lift.sh          # 5 分 50 秒
bash tools/plugins/framework/fw_stage2.sh --fresh                                  # 9 分 30 秒・rc 1
grep -n 'MessageBoxA' tools/plugins/work/fw/smoke.log                              # 27 行目
# 修正前素材の比較 (§3): FW_W=$RUNNER_TEMP/pre_root/tools/plugins/work/fw bash tools/plugins/framework/fw_stage2.sh --fresh
```

## 8. コード差分と確認 (測定 commit 以降)

測定 commit `77205e76` 以降のコード変更は無し (本 PR の追記は REPORT と DOC_MAP のみ)。

```sh
git diff 77205e76 HEAD -- tools/plugins/framework tools/icall tools/liftlib ':!*.md'   # 空 = 実行コード差分 0
```

検証 HEAD `1dd07ee6` での実行結果 (WORKFLOW §6):

- 上の diff: 空 (出力 0 行)。実行コード差分 0。
- `git status --porcelain`: 本 PR の範囲外の未コミット変更 2 件 (`package.json`・`pnpm-lock.yaml`。runner の checkout に残っていたもの) のみ。本 PR の commit には含めていない。
- 20MiB 超の blob: 0 件 (`c98d2c99..HEAD` の全 object で最大 145,533 B)。
- e2e の再実行: 未実施。`$ARTIFACTS_DIR` に `fl-win64.tar.zst` しか無く、`work-fw-stage1`・`work-liftlib`・`toolchain-retdec`・`toolchain-emsdk` が無いため。§2・§3 の実測は測定 commit `77205e76` での別 run の記録で、この HEAD では再現していない。
