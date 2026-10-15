# REPORT_2556 — function_450560 の IR 修復 (fix_450560) を本番 IR 生成に常設し、C 転記の既定を無効化する (#2556 / CI-104)

## 0. 結論

- `m11_gen_ir2.sh` の ldfix 直後に `ldfix/fix_450560.py` を常設し、`ir_conditions.json` に `450560=applied` を記録する (記録の無い IR は build しない)。
- `m11_ov.c` の `function_450560` 転記の既定を**無効**にした (`M11_OV_450560` 既定 0 = `-DM11_OV_NO_450560`)。旧既定は `M11_OV_450560=1` で戻せる。
- 実測: C 転記 ON (旧既定) と IR 修復 ON (新既定) で、units_run・GetMem・icall ok/miss・survey ok/trap の内訳が**全て一致**した。wasm サイズは 6048131 → 6048008 bytes (差 −123)。
- 受入 4 (`44cb40` の引数) は機械語で確認した (§4)。引数は読まれていない。

## 1. 測定条件

- 測定 commit: `2e15e1f29` (コードを変えた最後の commit。`git diff 2e15e1f29 HEAD -- tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/m11_ov.c tools/m11/ldfix/fix_450560.py` の差分は本 REPORT の commit 以降は 0)。
- 素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`)・`work-m11`・`work-liftdiff` を展開。`toolchain-*` は runner の `/opt/retdec`・`/opt/emsdk` を使用。
- 環境: 4 vCPU・load average 0.37〜0.71。
- **`m11_e2e.sh --full` は実行していない**。素材の `work-m11` に `ir_conditions.json` と `lift_pe.sha256` が無く、全再生成 (scan → Ghidra 12.1.4 → lift 4 chunk → tail 固定点) が 20 分超で本 run の上限 (58 分) に収まらないと判断した。代わりに既存の lift 成果物から `m11_gen_ir2.sh` → `m11_build.sh` → `m11_e2e.sh` (`M11_SKIP_LIFT_FP=1`・参考値) の経路で測った。これは `REPORT_3647.md` §1 と同じ迂回。**受入 3 の `--full` 実測は未達**。

## 2. 測定結果 (同一 PE・同一 run 経路)

| 変種 | IR (`450560`) | `m11_ov.c` 450560 転記 | units_run | GetMem | FastMM GetMem | icall ok / miss | survey ok / trap | wasm bytes | e2e rc |
|---|---|---|---|---|---|---|---|---|---|
| 旧既定 (C 転記 ON・IR 修復 OFF) | disabled | 有効 | 98 | 715 | 2041 | 391 / 3 | 875 / 20 | 6048131 | 1 (judge の期待値不一致) |
| 新既定 (C 転記 OFF・IR 修復 ON) `2e15e1f29` | applied | 無効 | 98 | 715 | 2041 | 391 / 3 | 875 / 20 | 6048008 | 1 (同上) |

- 両変種とも `reached_stage 4`・trap は `memory access out of bounds` (`function_535c11`)・`survey trap kinds` は halt0->longjmp 6 / OOB 14 で同一。
- 新既定の IR sha256: `4044f989…` (`ir_conditions.json` 記録)。旧既定: `a770b0fc…`。
- survey の `ptrcheck` の `image_va_words_new` (69669 / 71001) と `unremap_cand` (0 / 3) は両変種で一致 (gate 通過)。
- **rc=1 の理由**: `m11_tolerant_gate.py` が `survey ok=875 != 期待 873` で失敗する。**旧既定でも同じ 875 で失敗する**ので、本変更による退行ではない。期待値 (`e2e_expect.env` の `M11_EXPECT_SURVEY_OK_EXACT=873`) は本 run の素材・環境と一致しない (既存の差)。期待値の更新は本 PR の範囲外として、未解決に起票する (§5)。
- 検証の再現に使った命令 (HEAD `2e15e1f29`):
  - `M11_SKIP_LIFT_FP=1 M11_LB_BASE=0 bash tools/m11/m11_e2e.sh` (実時間 1 分 06 秒・load 0.37)
  - 旧既定の比較: `M11_FIX_450560=0 bash m11_gen_ir2.sh` → `M11_OV_450560=1 M11_ALLOW_450560_DISABLED=1 bash m11_build.sh` → 同 e2e (実時間 1 分 02 秒)

## 3. 既定を反転した理由

- 本番 wasm は今まで C 転記 (`m11_ov.c` の `function_450560`) で動いていた。IR 修復 (`fix_450560.py`) は `ldfix_e2e.sh` の測定でしか使われていなかった (#2502 REPORT §6)。
- 両者は機械語 26 命令と一致する同じ実行結果 (GetMem 16/17/24 → 本 run では 715 / 2041 / 391 で一致) を出す。IR 修復を本番に入れることで、C 転記 (手書き) への依存を外す。
- A/B 比較は §2 のとおり一致。よって既定の反転で本番の観測値は変わらない。

## 4. 受入 4: `44cb40` の引数 (LCMapStringW が 0 を返す経路)

機械語 (PE VA `0x450560`):
- `0x4505f4 call 0x423970` (LCMapStringW) → `0x4505f9 test eax,eax` → `0x4505fb jne 0x450602` → `0x4505fd call 0x44cb40`。
- `44cb40` 本体: `sub rsp,0x28; call 0x423540; mov ecx,eax; xor edx,edx; call 0x44cb60; add rsp,0x28; ret`。
- `0x423540` は `kernel32!GetLastError` の import thunk (IAT `0x19713c0` で確認)。引数を取らない。
- したがって `44cb40` は**入口の rcx/rdx を読まない**。`44cb60` の 2 引数 (`ecx`・`rdx`) は `44cb40` の内部で設定される。
- IR の `call @function_44cb40(zext arg3, 16777472)` の引数は、LCMapStringW 失敗経路の実行結果に影響しない。`fix_450560.py` の据え置き (base の値) は妥当。受入 4 は**確認済み・修正不要**。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `m11_e2e.sh --full` (全再生成) の実測が未実施。素材 `work-m11` に `lift_pe.sha256` / `ir_conditions.json` が無い | 受入 3 の `--full` 字義どおりの測定は未達 (lift 成果物からの再生成・指紋迂回で代替) | 本 issue #2556 (再投入時に素材を揃えて実施) |
| `m11_tolerant_gate` の期待値 873 と実測 875 の差 (旧既定でも同じ) | e2e の rc が 1 のまま。回帰ゲートとして機能していない | 別 issue (期待値の pin 更新は未実施) |
| 同類型 14 関数 16 deref 箇所 (REPORT_2502 §4) の IR 側確認 | 受入 2 の範囲 | #2555 (既存の子) |
