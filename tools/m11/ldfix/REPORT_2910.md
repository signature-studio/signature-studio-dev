# REPORT #2910 — spill TRUE_DROP の C 分類 9 site: 機械語と IR の 1 対 1 根拠と修復 (LD-137)

既知類型との関係: #2794 (`REPORT_2794.md` §冒頭) と同じ。機構は `docs/DEFECTS.md` の D4 (disp=0 の 1 段 deref の脱落) と同型の「2 段 deref が 1 段に潰れる」に近い。同一とは確定しないため ID は付けない。

親: #2794 (LD-130)。本 issue は受入条件を満たした範囲に縮めて `Closes #2910` とする (`docs/WORKFLOW.md` §3)。残りは子 #3579 [LD-163] (局所スロット経由の 5 site) と #3580 [LD-164] (修復 cell の非 store 消費と audit 粒度) に移した。

## 0. 結論

- C 分類 9 site のうち **4 site に 1 対 1 の根拠が付いた**。根拠は「引数スロット `[rsp+0x20+8j]` への store → 直後の direct call → IR で同じ callee の同じ引数位置が、その K の load の値 (sext 1 段) に一致する」の 1 組。修復した 4 site: 100b8d0・ea7c61・ea7c97・ea7cc8。
- 残り 5 site (1046a30 104c769・104c9e6、1280530 12827e6、c589b0 c5d2df・c5d343) は局所変数 `[rbp+d]` への store 経由で、この根拠の型に当たらない → #3579 [LD-163]。直さない。
- spill 宛 CELL_COLLAPSED は **37 → 28** (#2794 と同じ。1 対 1 の 9 site が消え、根拠の付いた 4 site は audit 上まだ残る。§4)。修復した IR 上の site は 9 → **13** (1 対 1 の 9 + 根拠の 4)。
- 修復した cell に残る非 store 消費 (ea7ae0 の `icmp slt` の読み出し 3 本) は 2 段 deref の脱落の疑い (未検証) → #3580 [LD-164]。
- `fix_d17_e2e.sh` rc=0・突合 PASS・emcc rc=0 (コミット済み HEAD で n=2)。起動 (FLEngine boot) は動かしていない (§6)。

## 1. 測定条件

- 測定 commit: `170bc1639` (コードを変えた最後の commit: `fix(m11): repair spill TRUE_DROP sites by call-argument flow (#2910)`)。起点 `origin/main` = `4868fc52b`。作業 worktree `ws-2910` (branch `2910-spill-equal-read-repair`)。
- 素材: `work-m11` を `$RUNNER_TEMP/m11work` に展開し、`M11_WORK=<その tools/m11/work>` で指定 (`tools/m11/work/` への展開は行わない)。emcc は runner の `[EMSDK]` (`docs/REFERENCES.md`)。`work-liftdiff` は本 e2e では未使用 (受入の `oc_artifacts` 行には残す)。`work-m11` は #516 以前の snapshot なので、結論はこの IR に限る (`REPORT_1169.md` §1 と同じ)。
- 実行: `M11_WORK=... TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/fix_d17_e2e.sh` (foreground)。
- 実測 (測定 commit `170bc1639`、n=2): real **47.37 s / 47.63 s**、rc **0 / 0**、load average (1 分) 実行前 0.50、終了後 0.90。
- 基準 (修復前。`origin/main` の script で同じ e2e を 1 回): real 46.50 s、rc 0、load average (1 分) 終了後 0.91。
- 測定後のコード差分 (測定 commit から HEAD まで。この REPORT を追加する commit 以外は無い):

  ```
  git diff 170bc1639 HEAD -- tools/m11/ldfix/fix_d17.py tools/m11/ldfix/fix_d17_e2e.sh tools/m11/ldfix/audit_lsf*.py tools/m11/ldfix/ldmach*.py tools/m11/ldfix/spill37_1169.py tools/m11/ldfix/fix_spill_2794.py tools/m11/ldfix/check_spill_2794.py tools/m11/ldfix/results tools/m11/lb_base.py
  (空: 差分 0)
  ```

## 2. 判定 (受入 1): C 9 site の機械語と IR の照合

判定の軸は `REPORT_2794.md` §2 と同じ (M = 機械語で X に触れる rip 相対命令の数、I = IR 関数内の `i64 K to ptr` の出現数)。M = I の 9 site が C 分類。
行番号は `tools/m11/work/boot_final3.ll` の絶対行 (`grep -n 'i64 <K 10 進> to ptr' boot_final3.ll` で再現できる)。

| # | fn | site | K | M/I | 判定 | 根拠 (機械語 / IR の行) |
|--:|---|---|---|--:|---|---|
| 1 | 100b890 | 100b8d0 | 11e27f0 | 3/3 | **修復 (callarg)** | 機械語 100b8c7 `mov rax,[rip+..]` → 100b8ce `mov eax,[rax]` → 100b8d0 `mov [rsp+0x20],eax` → 100b8dd `call 0xe59e90`。IR 3881 `%6 = load i32 inttoptr (K)` → 3882 `%7 = sext` → 3883 `call @function_e59e90(i32 %3, i32 %4, i32 1, i32 %5, i64 %7, i64 0)` (引数 index 4 = %7) |
| 2 | 1046a30 | 104c769 | 11e2c50 | 2/2 | 残し (→ #3579) | 機械語 104c760 → 104c767 `mov eax,[rax]` → 104c769 `mov [rbp+0x5b8],eax` (局所)。IR 23856 `%3499 = load i32` → 23857 `store %3499, ptr %stack_var_16`。`%stack_var_16` と `[rbp+0x5b8]` の同一性が示せない |
| 3 | 1046a30 | 104c9e6 | 11e28c8 | 3/3 | 残し (→ #3579) | 機械語 104c9dd → 104c9e4 → 104c9e6 `mov [rbp+0x5b8],eax`。IR 24026 `load i32` → 24027 `store ..., ptr %stack_var_16`、24035 `load i32` → 24036 zext → 24037 select。局所の名前が結べない |
| 4 | 1280530 | 12827e6 | 11dfda8 | 7/7 | 残し (→ #3579) | 機械語 12827dd → 12827e4 → 12827e6 `mov [rbp+0xc4],eax`。IR 7 本 (ptr 3 本、i32 4 本: 66852・66860・66870・66874・66986・68644・71748) |
| 5 | c589b0 | c5d2df | 11e1f40 | 4/4 | 残し (→ #3579) | 機械語 c5d2d6 → c5d2dd → c5d2df `mov [rbp+0x48],eax`。IR i32 の load 4 本 (391049・391060・391077・391089) |
| 6 | c589b0 | c5d343 | 11e1f40 | 4/4 | 残し (→ #3579) | 機械語 c5d33a → c5d341 → c5d343 `mov [rbp+0x48],eax`。#5 と同じ K の 2 本目 |
| 7 | ea7ae0 | ea7c61 | 11e35c0 | 2/2 | **修復 (callarg)** | 機械語 ea7c58 `mov rax,[rip+..]` → ea7c5f `mov eax,[rax]` → ea7c61 `mov [rsp+0x20],eax` → ea7c65 `call 0xec35f0`。IR 460891 `%72 = load i32 inttoptr (K)` → 460892 `%73 = sext` → 460893 `call @function_ec35f0(i64 %55, i64 %66, i64 %69, i64 %71, i64 %73)` (index 4 = %73) |
| 8 | ea7ae0 | ea7c97 | 11e4a40 | 2/2 | **修復 (callarg)** | 機械語 ea7c89 `mov byte [rsp+0x20],4` → ea7c8e `mov rax,[rip+..]` → ea7c95 `mov eax,[rax]` → ea7c97 `mov [rsp+0x28],eax` → ea7c9b `call 0xec2150`。IR 460910 `%83 = load i32 inttoptr (K)` → 460911 `%84 = sext` → 460912 `call @function_ec2150(..., i8 4, i64 %84)` (index 5 = %84) |
| 9 | ea7ae0 | ea7cc8 | 11e1f98 | 2/2 | **修復 (callarg)** | 機械語 ea7cba `mov byte [rsp+0x20],5` → ea7cbf `mov rax,[rip+..]` → ea7cc6 `mov eax,[rax]` → ea7cc8 `mov [rsp+0x28],eax` → ea7ccc `call 0xec2150`。IR 460918 `%86 = load i32 inttoptr (K)` → 460919 `%87 = sext` → 460920 `call @function_ec2150(..., i8 5, i64 %87)` (index 5 = %87) |

集計: 修復 4 (#1・7・8・9) / 残し 5 (#2〜6)。#2〜6 は局所変数 `[rbp+d]` への store で、今回の根拠の型 (引数スロット + direct call) に当たらない。

### 2-1. 根拠の型 (`fix_spill_2794.py` の `callarg` gate)

次の 3 条件をすべて満たす site だけを直す (`judge_callarg`)。

1. 機械語: site が `mov dword ptr [rsp+0x20+8j], reg32` (outgoing 引数。argi = 4+j)。直前の rip 読み出し R から site まで分岐・call が無く (3 命令以内)、site の直後 4 命令以内に direct call (callee F)。
2. IR: K の `load iN` (N = 32 = 機械語 store 幅) の値 (`sext`/`zext`/`trunc` 1 段まで) が、F の呼び出しの引数 argi (0 始まり) と一致し、その組がちょうど 1 つ。
3. M = I (機械語の rip 読み出し数 = IR の K の出現数)。M > I (B 分類) は本 issue の範囲外なので除外する。

この型では、R と load の組を「値の流れ」で決めている。1 対 1 ゲート (M = I = 1) とは独立な根拠。

### 2-2. 修復 pass の差分

修復の型は `REPORT_2794.md` §4 と同じ 2 段分割。修復した load 4 本の差分 (`boot_spill.ll` と `boot_d17.ll` の比較):

```
-  %6 = load i32, ptr inttoptr (i64 18753520 to ptr), align 4
+  %cellps.11e27f0 = load ptr, ptr inttoptr (i64 18753520 to ptr), align 4
+  %6 = load i32, ptr %cellps.11e27f0, align 4
```

同様に `%72` (K=11e35c0)・`%83` (K=11e4a40)・`%86` (K=11e1f98) の 3 本。他の行は変わらない (diff は 4 組)。

## 3. 修復 (受入 2) と突合 (受入 3)

- 修復件数: `--gate both` (既定) で **13** (1 対 1 の 9 + callarg の 4)。`--gate 1to1` は 9 (#2794 と同じ)。`--gate none` は 24。
- 突合 `check_spill_2794.py`: **RESULT: PASS**。C1 (修復後の CELL_COLLAPSED が増えない) ✔、C2 (消えた site = 1 対 1 で修復した 9 site) ✔、C2b (callarg の 4 site は修復後も audit に残る) ✔、C3 (修復は TRUE_DROP だけ) ✔。
- TSV `results/spill_repair_2794.tsv` の `status` と `why` 列は、修復した site の根拠を示す (`1to1` / `callarg:read=... call=... argi=...`)。

## 4. audit 上の件数 (受入 3 の補足)

| 項目 | 修復前 | 修復後 |
|---|--:|--:|
| spill 宛 CELL_COLLAPSED site (`audit_lsf_ssa.py`) | 37 | 28 |
| うち TRUE_DROP 24 site の残数 | 24 | 15 (= 見送り 11 + callarg 修復 4。audit 上は残る) |
| 修復した IR 上の site | - | 13 |

callarg の 4 site は、修復後の audit で CELL_COLLAPSED のまま残る。`audit_lsf_ssa.cell_check` は site ごとでなく **関数 × K** で判定し、同じ K の i32 の const load が 1 本でも残ると CELL_COLLAPSED とする。ea7ae0 の 3 K と 100b890 の K (11e27f0) には、修復していない i32 読み出しが残る (§5、100b890 は %15・%23 の 2 本)。この粒度は本 issue の範囲外で、子 #3580 [LD-164] に移した。

## 5. ネガティブコントロール (受入 3)

| 対照 | 手順 | 結果 |
|---|---|---|
| N1 (修復を外した audit) | d17 のみの audit を突合に渡す | FAIL C2 (rc=1)。e2e で期待どおり FAIL を確認 |
| N2 (1 対 1 ゲートを外す) | `--gate none` | 24 件を書き換え (`spill fixed=24 skipped=0`)。e2e で assert |
| N3 (根拠のみ 1 対 1) | `--gate 1to1` | 9 件 (callarg の 4 件が増えないこと)。e2e で assert |
| N4 (引数位置を 1 つずらす) | `argi = 5 + ...` のコピーで実行 | 修復 9 件。callarg の 4 件はすべて見送り (`fixed=9 skipped=15`)。根拠の argi が効いている |
| N5 (M = I 条件を外す) | 条件を外して実行 (作業中の確認) | ff8b60 (B 分類、M=2・I=1) が根拠ありで修復され、計 14 件。M = I を入れる必要 |

## 6. 検証範囲 / 範囲外

- 範囲: `work-m11` の IR 1 本 (`boot_final3.ll`) に対する audit と修復・emcc 構文検証。
- 範囲外: 修復 IR を使ったビルド後の wasm の実行 (FLEngine の起動・boot の挙動)。本 issue ではやっていない。
- 起動・GUI に関わらない IR 修復のため、製品 KPI (FLEngine 起動の dispatch 数・通過 unit 数) は測っていない。
- callarg の根拠は「引数の値の流れ」の機械照合。同じセルを読むことの証明は、R と load の組が 1 つだけという条件に依る (他経路の読み出しは見えない)。

## 7. 未解決と起票先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 局所スロット `[rbp+d]` 経由の 5 site (C 分類の残り。§2 #2〜6) | spill 宛 CELL_COLLAPSED の残り 5 (根拠未決) | 子 #3579 [LD-163] |
| 修復した cell に残る非 store 消費 (ea7ae0 の `icmp slt` の 3 読み出し: IR 461130・461142・461157 ↔ 機械語 ea7e6d・ea7ea0・ea7ed6) の 2 段 deref 脱落の疑い (未検証) | 同じ関数の残存 miscompile の疑い。audit は store 単位で数えないため見えない | 子 #3580 [LD-164] |
| audit の判定粒度 (関数 × K) | 修復しても CELL_COLLAPSED の件数が減らない (callarg 4 件) | 子 #3580 [LD-164] |
| B 分類 6 site (IR の読み出しが機械語より少ない) | 修復しない (M > I) | #2940 [LD-141] (既存) |
| 判定不能 7 site (UNDETERMINED) | 修復対象外 | #2253 [LD-95] (既存) |
| 修復 IR の実行検証 (FLEngine 起動) | 意味の正しさは機械語照合のみ | PM 判断 (本 issue の範囲外) |
| `work-m11` が #516 以前の snapshot | 結論はこの IR に限る | `REPORT_1169.md` §5 と同じ扱い |

## 8. 再現

```
M11_WORK=<work-m11 展開先>/tools/m11/work TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/fix_d17_e2e.sh
```

素材: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff` (`work-m11` が必須。emcc は runner の `[EMSDK]`)。判定の入力は `results/spill37_1169.tsv`。修復後の突合の出力は `results/spill_repair_2794.tsv` (e2e が `cmp` で照合)。

## 9. 検収用の検算

- 機械語と IR の照合は、§2 の行番号で人手で確かめられる (`sed -n 3881,3883p boot_final3.ll`・`sed -n 460891,460893p boot_final3.ll`・機械語は `ldmach_img` の逆アセンブル)。
- `check_spill_2794.py` は audit の CELL_COLLAPSED 集合の差分で突合する。`fix_spill_2794.py` が出した修復リストと独立に、消えた site の集合だけから判定する (C2)。
