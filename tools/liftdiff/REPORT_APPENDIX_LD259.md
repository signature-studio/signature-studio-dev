# 付録: liftdiff LD-259 (#5202): `--patch` の `p=` 受理の確認と 691dd0 vmo の単発再現

親: #4524 (LD-222)。前段: `REPORT_APPENDIX_LD207.md` §2・§4 (vmo は判定に入るが heap 差 26 件・ret 差の原因は未特定)。
前回 run (#4524 の再実行) では単発 `vmo` が `unexec` (native segv) になり、batch だけ `diff` になった。本 run でその食い違いを再確認した。

## 1. 結論

| #5202 の受入条件 | 結果 | 根拠 |
|---|---|---|
| `liftdiff.py run --patch` の `p=` が C ランナーで受理される | **達成** | §2。patch を入れると wasm の ret が変わる (`0x101a9000` → `0x101a9100`) |
| 規則を壊すと落ちるテスト | **達成** | `tests/test_ld259_patch_p.py` (patch を外すと wasm ret が変わらず落ちる。e2e `[0/4]` に追加) |

#4524 の残件 (補正 IR での 691dd0 vmo の再実行・heap 差 26 件と ret 差の切り分け・DEFECTS 照合) は、#5202 の範囲から外して親 #4524 の本文に移した。補正 IR の生成手段が liftdiff に無いため、本 run では作っていない (§4)。

## 2. p= の受理 (実測)

`tests/test_ld259_patch_p.py` と同じ条件 (`--args i:a:0x1000,i:0x3,i:0x0 --blob vmt`・`--state work/m11/boot_state.json`・`--nobuild`)。
rdx=3 の手動投入なので、heap 差 (31 / 38) は pattern `vmo` (rdx=0・heap 差 26) の値とは別。比較に使うのは ret の変化。

| patch | native ret | wasm ret | heap 差 |
|---|---|---|---|
| なし | `0x1` | `0x101a9000` | 31 |
| `a:0x1078:q=0x7` | `0x1` | `0x101a9100` | 38 |
| `a:0x1078:q=0x0` | `0x1` | `0x101a9000` | 31 |

`a:0x1078:q=0x7` で wasm ret が変わるので、C ランナーは `p=` を読み、`ld_case_begin` で適用している (`rt/ld_core.h` の `p` パース・`ld_case_begin`)。`q=0x0` では変わらず、値が効いている。

## 3. 691dd0 vmo の単発と batch (本 run の実測)

- 単発 (`liftdiff.py run --fn 0x691dd0 --pattern vmo --state work/m11/boot_state.json --nobuild`): **`diff`** (2 case とも同じ)。ret `native=0x1` / `wasm=0x0`、heap 差 26 件。
  - 前回 run (#4524 の再実行) の単発は `unexec` (native segv)。同じ手順で結果が変わった。単発の結果は実行ごとに揺れる。
- 単発の trace (`-v --json`): native は `0x410320` → `0x409410` (VMT 間接 call・`call [rax-0x30]`) へ進む。wasm は `0x410320` の直後に `0x40f9e0` へ進み、`0x409410` を呼ばない。
  - wasm 側の `function_410320` は IR が `ret arg1` のみ (`boot_final3.ll` L116075)。間接 call が IR に無い。これは `REPORT_APPENDIX.md` の D15 型候補 (410320 の 82 件) と一致する。
  - 最初の食い違いは trace index 5 (`entry_va`・native `0x409410` / wasm `0x40f9e0`)。

## 4. 補正 IR での再実行 (未達・残件)

- 補正 IR (`function_410320` に `call [rax-0x30]` を補った IR) は、今回の run では作っていない。
- `liftdiff` の IR 経路 (`targets/m11.json` の `ir`・`ldlib/build_wasm.py`) には間接 call を補う段が無い。`m11_ov.c` の `ICALL_AT(0x41032e, Q(self-0x30), ...)` は C 転記側 (`m11_icall`) にあり、`function_410320` の IR 本体には入っていない。
- そのため、補正 IR で ret と heap 差 26 件が消えるかは未確認。残件は親 #4524 に残す。

## 5. 検証 (実測)

- e2e (測定 commit `e58b48545`・HEAD と同一): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/liftdiff/liftdiff_e2e.sh --m11-only` → **exit 0・`LIFTDIFF_E2E PASS`・real 3m32.5s**。load 2.39 (16:54:01) → 4.88 (16:57:34)、4 core。`[0/4]` で `PASS test_ld259_patch_p` を含む。
  - sample:800 (801 件): **一致 360 / 不一致 236 / 実行不能 205**。前回 run (#4524) の 360 / 236 / 205 と一致。
- 単体: `tests/test_ld259_patch_p.py` → `PASS test_ld259_patch_p wasm_rax 0x101a9000 -> 0x101a9100` (rc=0・13.1 s)。
- 測定 commit: `e58b48545` (コードを変えた最後の commit)。
- コード差分 (測定 commit → HEAD): 測定 commit = HEAD のため `git diff e58b48545 HEAD -- tools/liftdiff` は 0 行。本 PR の REPORT 追記・DOC_MAP 登録は tools/liftdiff の外・REPORT のみ。
- 基準 (origin/main `641595411`) からの差分: `git diff 641595411 HEAD -- tools/liftdiff` は新規テスト・e2e の 1 行・REPORT のみ (コード経路の変更なし)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 補正 IR (410320 の間接 call) で 691dd0 vmo を再実行し、heap 差 26 件と ret 差を lift 欠陥か比較・投入の問題かに分ける | 受入 2 未達。691dd0 の vmo 判定の原因が未確定 | #4524 (親・本文にチェックリストとして残す) |
| 単発 vmo の結果が run ごとに揺れる (`unexec` ↔ `diff`) | 単発の結論が再現しない。batch の判定の根拠が揺れる | #4524 (残す。単発と batch の差の切り分けが先) |
| 単発 trace で、wasm 側 `function_410320` に間接 call が無い | D15 型の確定には補正 IR での確認が要る | #4524 / 既存 D15 追跡 (`docs/DEFECTS.md` D15 行) |
