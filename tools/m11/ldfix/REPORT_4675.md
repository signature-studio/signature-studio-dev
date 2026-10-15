# REPORT #4675 — `1046a30` の上流 X の 1 段不足を機械語に合わせる IR 修復 (LD-236・#3675 子)

## 1. 結論

- 機械語の段数 (cell → C → [C] → …) と IR の段数の不一致は**実測で再現**した。`1046a30` の上流 X は IR で 1 段足りない。
- 修復 pass `ldfix/fix_ld236.py` を追加した。`%351` の 1 行を 2 段の load に置き換える (1 関数限定・想定外は assert)。
- 生成パイプラインには**既定 OFF** (`M11_FIX_LD236=1` で opt-in)。本番 IR は変えていない。
- 受入 2 (`10479c7` の再判定) と受入 3 (本番 unit e2e) は未達。fl-win64 の unit 実行を要するため、既存の子 #4676 (LD-237) に残す (§6)。

## 2. 機械語と IR の段数 (実測)

測定 commit: `325cf6a4d` (origin/main 基点)。素材: `work-m11.tar.zst` (`m11_image.bin`・`boot_final3.ll`) を `$RUNNER_TEMP` に展開。

逆アセンブル (capstone・`m11_image.bin`・VA 0x400000 起点):

```
10474a6 mov rax,[rip+0x59ad6b]     ; C = [cell]    (cell = LVA 18752024 = VA 0x15e2218)
10474ad mov rax,[rax]              ; S = [C]
10474b6 cmp ecx,[rax+0x10]         ; [S+16]
10474bf mov rax,[rip+0x59ad52]     ; C = [cell]
10474c6 mov rax,[rax]              ; S = [C]
10474c9 mov rax,[rax+8]            ; [S+8]
10474d4 mov rax,[rax+rcx*8]        ; [[S+8]+idx*8]
```

現行 IR (`boot_final3.ll` 17405〜17431 行):

```
%351 = load i32, ptr inttoptr (i64 18752024)   ; C の下位 32 bit (1 段)
%352 = sext %351
%353 = add %352, 16 ; %355 = load i32 [%353]   ; [C+16]  ← 機械語は [S+16]
%357 = add %352, 8  ; %359 = load i64 [%357]   ; [C+8]   ← 機械語は [S+8]
```

- 機械語は cell の値 C を 1 段 deref した S を基底にする。IR は C をそのまま基底にする。段数が 1 つ足りない。
- 静的 image では `C = 0x12bafc8` の先 (`[C]`) は 0 で、実行時の値は辿れない (REPORT_2923 と同じ)。段数の一致は逆アセンブルの構造から判定した。

## 3. 修復内容

`ldfix/fix_ld236.py` は `%351 = load i32 [cell]` の 1 行を次に置き換える。`%352` 以降は変えない。

```
%fx236c = load i64, ptr inttoptr (i64 18752024)   ; C
%fx236p = inttoptr i64 %fx236c to ptr
%fx236s = load i64, ptr %fx236p                   ; S = [C]
%351 = trunc i64 %fx236s to i32
```

IR 差分 (`function_1046a30` のみ・`diff` の結果):

```
< %351 = load i32, ptr inttoptr (i64 18752024 to ptr), align 4
> %fx236c = load i64, ptr inttoptr (i64 18752024 to ptr), align 8
> %fx236p = inttoptr i64 %fx236c to ptr
> %fx236s = load i64, ptr %fx236p, align 8
> %351 = trunc i64 %fx236s to i32
```

- `llvm-as-18` で修正後の `boot_final3.ll` のパースに成功 (`PARSE_OK`)。
- 本番経路の `boot_final.ll` (`pass` 前の入力) にも、同じ `%351` 行が `function_1046a30` に 1 件あることを `pass` の assert で確認 (`rc=0`)。
- fail-closed を確認: 二重適用 (`適用済み`)・cell 行 0 件・関数なし は AssertionError で止まる。

注: `%352` は S の下位 32 bit になる。wasm32 の linear memory は 32 bit のポインタで、切り詰めは許容範囲。

## 4. 監査 (`audit_lsf_ssa_e2e.sh`) の結果

測定 commit `325cf6a4d`。`TMPDIR=$RUNNER_TEMP M11_WORK=<展開先> LD_WORK=<展開先> bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh`。

| 条件 | 時間 | load (終了時) | 結果 |
|---|---|---|---|
| 修正前 (`boot_final3.ll` 原本) | 時間は未計測 (`time` を付けていない) | 未計測 | rc=0・7/7 完走 |
| 修正後 (`fix_ld236.py` 適用) | real 2m58.5s | 0.95 0.59 0.31 (uptime) | rc=0・7/7 完走 |

- 修正前後の監査の出力 (`audit_base.log` と `audit_fixed.log`) は**完全に一致した** (`diff` 0 行)。
- 理由: 判定表 (`candidate_verdicts`・`spill178_1161.tsv`) は `(fn, site)` で引き、IR の番地を見ない (REPORT_2958 §7 と同じ)。この監査は本修正の効果を検出できない。
- 監査が 7/7 完走すること (壊していないこと) の確認にはなる。効果の確認は §5 の IR 差分と §2 の段数照合による。

## 5. 残り (未達の受入条件)

| 受入 | 状態 | 理由 |
|---|---|---|
| 1. 修復経路を決め、1 関数の IR 修正として入れる・IR 差分を示す | **達成** (本 PR) | §2〜§3。既定 OFF で opt-in |
| 2. `10479c7` を再判定し `candidate_verdicts_4675.jsonl` と `spill178_1161.tsv` を再生成 | **未達** | (ii) `%492` と slot の対応 SSA 根拠・(iii) `stack_var_16` の後続の読みの確認が要る。本 run では未着手 |
| 3. 本番影響の実測 (`m11_gen_ir2.sh` → `m11_build.sh` → unit e2e・fl-win64) | **未達** | fl-win64 の展開・build・unit 実行が 60 分に収まらない |

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 2: `10479c7` の再判定 ((ii)(iii)) と `spill178_1161.tsv` の再生成 | `10479c7` は判定不能のまま | #4676 (LD-237・既存の子) |
| 受入 3: 本番 unit e2e (`M11_FIX_LD236=1` で build → unit の ok/halt0 の変化) | 修正が unit 結果に効くかは未測定。既定 OFF のまま | #4676 (LD-237) |
| 監査 (`audit_lsf_ssa_e2e.sh`) が本修正の効果を検出できない | 判定表が IR の番地を見ないため | 既知 (REPORT_2958 §7)・本 PR では扱わない |
| `%352` の 32 bit 切り詰め | wasm32 では許容・画像外の S では誤る可能性 | 受入 3 の unit 結果で確認 |

## 7. 再現

```sh
TMPDIR=$RUNNER_TEMP M11_WORK=$RUNNER_TEMP/m11w/tools/m11/work LD_WORK=$RUNNER_TEMP/ldw/tools/liftdiff/work \
  bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
python3 tools/m11/ldfix/fix_ld236.py IN.ll OUT.ll     # IN = boot_final3.ll 相当
M11_FIX_LD236=1 bash tools/m11/m11_gen_ir2.sh          # 生成経路 (既定 OFF)
```
