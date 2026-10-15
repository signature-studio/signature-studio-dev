# LD-166 (#3602): negctl_510 の NC1 が現 IR で走らない原因と修復

既知類型との関係: DEFECTS D4 (既知・F7) の同型。`store i64 %arg2` は機械語 `[arg2]` の deref 脱落 (基底レジスタの値が store される)。その修復は ldfix F3c (store-arg) で、NC1 が人手で入れる修復と同じ形。

## 結論

- NC1 が評価されなかった原因は**回帰ではない**。NC1 の patch 対象 (`function_5c0270` の `store i64 %arg2, ptr X, align 8` 2 本) は、ldfix F3c (#509・commit `3f1d7b8b4`・2026-10-13) が同じ修復を入れた現 IR では **0 本** になり、`assert n == 2` が落ちていた。snapshot の `boot_final3.ll` (2026-10-10 生成・ldfix 前) では 2 本ある。
- 修復: `negctl_510.sh` の NC1 は、ldfix 済みの 2 本を脱落形に戻してから patch する。nc*.json が欠ければ `negctl_510.sh` は rc 1 を返す。e2e の手順 6 はその rc で止まる。前回の出力 (stale な `nc1.ll`) の再利用も止めた。
- 受入 3 は、negctl の既定の基準 (snapshot `boot_final3.ll`) で満たした: 5c0270 の SUSPECT 2 → 0・alg1 対象関数 26 → 25。

## 1. 現 IR の NC1 対象 (受入 1)

手順: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/m11_gen_ir2.sh` (rc 0・33.7 s・ldfix 内訳 F3c(store-arg)=46・出力 `work/boot_final.ll` 490,761 行)。

| IR | `function_5c0270` の `store i64 %arg2, ptr X, align 8` | 同 2 箇所の形 |
|---|---|---|
| snapshot `work-m11` の `boot_final3.ll` (ldfix 前・`ldfxn` 0 件) | 2 本 (`%13`・`%18`) | raw store |
| 現 IR `work/boot_final.ll` (`m11_gen_ir2.sh`) | **0 本** | `%ldfxn3_p = inttoptr i64 %arg2 to ptr` → `%ldfxn3 = load i64` → `store i64 %ldfxn3, ptr %13` (`%ldfxn4` 同様) |

- 旧 negctl (`091e4a7b6`) を現 IR (`$RUNNER_TEMP/w_cur` に `boot_final3.ll` として配置) で実行: `AssertionError: [0]`。`nc1.json` は出ず、`negctl_510.sh` の rc は 0 (失敗が rc に出ない)。
- 原因の commit: `3f1d7b8b4` (`feat(m11): ldfix F3c gates extended ... (#509)`)。`ldfxn` 命名の初出で、`tools/m11/ldfix/ldfix.py` の `fix_f3c_fn` が書く。
- issue の仮説の 5c43ea98a・68cd7b86b・4ec819122 は個別の diff を取っていない (未確認)。ただし、この store 2 本の形を変えたのは F3c (3f1d7b8b4) で、説明はこの 1 commit で完結する。

## 2. 修復 (受入 2)

`tools/m11/ldfix/` の変更 (commit `f8ec8e08f`・`f82675db4`):

1. NC1: ldfix 済みの 2 本 (`ldfxn` 形) を脱落形 `store i64 %arg2, ptr X, align 8` に戻してから patch する。戻した数は現 IR 2・snapshot 0。
2. 末尾: NC0〜NC7 の json のどれかが無ければ `[negctl_510] MISSING: <k>.json` を出して rc 1。
3. 起動時に `$RUNNER_TEMP/negctl_510/nc*.{ll,json,bin}` を消す。理由: 負の対照 (§3.3 N-b) の途中で、NC1 の補正が失敗した run に前の成功 run の `nc1.ll` が残り、そこから `nc1.json` が再生成されて失敗が隠れた (`f8ec8e08f` の時点)。
4. `audit_lsf_ssa_e2e.sh` 手順 6: `negctl_510.sh` が非 0 なら `[audit_lsf_ssa_e2e] FAIL` を出して rc 1。

## 3. 測定 (受入 3)

測定 commit: `f82675db4` (コードを変えた最後の commit)。以降の差分は §5。
環境: runner 4 vCPU・実行後の `/proc/loadavg` は `0.52 0.73 0.57` (run 中の load は未計測・各 run は単一プロセス)。

### 3.1 e2e (snapshot 基準 = `work-m11` の `boot_final3.ll`)

- `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` rc 0・1 分 43 秒 (実測 103.1 s)。`drops_510.tsv`・`spill178_1161.tsv`・修復後 `spill178` の 3 点は `results/` と一致。

| run | 5c0270 の alg2 (site) | alg1_deficit (5c0270) | alg1_fns | (alg1\|alg2) |
|---|---|---|---|---|
| NC0 無改変 | 5c0301 SUSPECT・5c032f SUSPECT | 64 → 2 | 26 | 41 |
| NC1 脱落 store を修復 | 5c0301 OK・5c032f OK | 64 → 0 | 25 | 40 |

→ 5c0270 の SUSPECT は 2 減 (2 → 0)、alg1 対象関数は 1 減 (26 → 25)。受入 3 を満たす。

### 3.2 現 IR (`m11_gen_ir2.sh` 出力) を基準にした NC0 / NC1

| run | 5c0270 の alg2 | alg1_fns | (alg1\|alg2) |
|---|---|---|---|
| NC0 無改変 | OK・OK (deficit 0) | 18 | 31 |
| NC1 脱落 store を修復 | OK・OK (deficit 0) | 18 | 31 |

- 現 IR では ldfix が NC1 と同じ修復を既に入れているため、NC1 の差分は 0。NC1 は評価される (`nc1.json` 生成) が、減少は現 IR の基準では示せない。減少を示せるのは脱落形の基準 (snapshot) だけ。
- NC2〜NC7 は現 IR でも従来どおり評価された (rc 0・json 8 本)。

### 3.3 ネガティブコントロール

- N-a (修正前の negctl・現 IR): `AssertionError: [0]`・`nc1.json` 無し・rc 0。修正後は同じ IR で `ldfix 済みの store を脱落形に戻した数: 2`・`patched stores: 2`・rc 0・json 8 本。
- N-b (`function_5c0270` の 2 本を `store i64 0, ptr X, align 8` に壊した基準 IR・`f82675db4`): NC1 は `AssertionError: [0]`、`[negctl_510] MISSING: nc1.json`、rc 1。
- 未確認: e2e 全体で手順 6 の fail-closed 分岐 (`|| { ...; exit 1; }`) を実際に通してはいない。確認したのは `negctl_510.sh` の rc 1 まで。

## 4. 関係する REPORT

- `tools/m11/ldfix/REPORT_2660.md` §10.3 の未解決 (「NC1 が評価されない・#3602」) は本件で解消。当該行を解決済みに更新した。

## 5. 鮮度

- 測定 commit: `f82675db4`。
- `git diff f82675db4 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/m11_gen_ir2.sh` は 0 行 (本 REPORT と `docs/DOC_MAP.md` の commit は、コードの範囲に含まれない)。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 現 IR を基準にした NC1 では「SUSPECT が 2 減る」を示せない (修復が既に入っているため差分 0) | NC1 の減少は脱落形の基準 (snapshot `boot_final3.ll`) でのみ測れる。negctl の基準の選び方は PM 判断 | 文言のみ (本 REPORT §3.2 に明記)。起票なし |
| issue 仮説の 5c43ea98a・68cd7b86b・4ec819122 の個別 diff は未確認 | 原因は F3c の 1 commit で説明が完結するため、除外の根拠を個別には取っていない | 文言のみ (§1)。起票なし |
| e2e 全体で手順 6 の fail-closed 分岐を通していない | negctl の rc 1 までは確認済み | 文言のみ (§3.3)。起票なし |
