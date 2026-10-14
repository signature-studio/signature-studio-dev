# #1231: M11_FIX_652500=1 時の unit 888 退行の原因特定 (M2q 欠落) と survey 2 系統の食い違い

既知類型との関係: `function_980ed0` の定数 10 進 VA (22954112) が LVA に remap されない漏れ (VA→LVA 漏れ)。M2q pass (#1043) で既に修正済み。`docs/DEFECTS.md` の新類型は確定しない。

**判定: 受入条件 1・2 を達成 (原因特定)。受入条件 3 (REPORT 記録) を達成。**
- 退行の原因は VA 上限ではなく論理差 (M2q 欠落で unit 368 が 832MB を確保し、後続の unit 888 が上限超過)。
- survey 2 系統の食い違いは、`m11_survey.mjs` が unit ごとに VirtualAlloc 予算 (既定 256MB) を掛けることによる。
- REPORT_1019 時点の `a5adb2fc` でのみ退行が再現する。main (`5a45be80`) では再現しない。

親: #1019 (M11-N58) / 前提: PR #1018 (gate `M11_FIX_652500`)。前回 PR #1460 (測定 commit `2b2faf52`) は退行が再現せず判定不能だった。本 REPORT はその続きで、REPORT_1019 の測定 commit `a5adb2fc` に戻して再現・切り分けした。

## 0. 測定環境

- 素材: `fl-win64` (`$RUNNER_TEMP/fl` に展開、`FL_WIN64_DIR`)、`work-m11` / `work-liftdiff` (各 commit の `tools/m11/work/`・`tools/liftdiff/work/` に展開)、`toolchain-retdec` / `toolchain-emsdk` は runner の [RETDEC]・[EMSDK] を使用。
- 測定 commit:
  - `a5adb2fc` (REPORT_1019 の測定 commit、detached worktree): `m11_gen_ir2.sh` rc=0 / 34 s / `ldfix=applied` / `ir_sha256=f5b27a23…` (REPORT_1019 と一致)。
  - `2b2faf52` (前回 PR の測定 commit): `ir_sha256=2c68ceae…`。
  - `5a45be80` (現 `origin/main`): `ir_sha256=2c68ceae…` (2b2faf52 と同一 IR)。本 REPORT の判定はこの commit で確認した。
- build (`m11_build.sh`): qstore 適用版 (既定)。`a5adb2fc` は OFF rc=0 20 s / ON rc=0、`5a45be80` は両方 rc=0。
- 注意: qstore 適用で `ir_sha256` が変わる (`a5adb2fc` の ON build で `39008e7f…` / `2b2faf52` の ON build で `16d1bae6…`)。

## 1. 退行の再現 (`a5adb2fc`、REPORT_1019 と同じ commit)

`survey_units.mjs` (既定):

| 構成 | ok | oob | halt0 | miss | other | noproc | 計 |
|---|--:|--:|--:|--:|--:|--:|--:|
| OFF (gate=0) n=1 | 869 | 16 | 8 | 47 | 1 | 1 | 942 |
| ON (gate=1) n=1 | 869 | 15 | 9 | 47 | 1 | 1 | 942 |

REPORT_1019 の n=3 (OFF 869/16/8、ON 869/15/9) と完全一致。unit 別の遷移 (OFF→ON) も REPORT_1019 と一致: 368 (halt0→ok) / 659 (oob→halt0) / **888: ok→halt0 (退行を再現)**。

888 の ON 側: `[m11][VA-big] #32 size=74776576 (71.3 MB) live=1626.9MB` の直後に `WebAssembly.Memory.grow(): Maximum memory size exceeded` (2 回)。OFF 側は同じ 888 が `live=1280.7MB` で ok。

## 2. 退行の原因: unit 368 の 832MB 確保 (M2q 欠落)

| unit 368 (`0x5810f0`) | OFF | ON |
|---|---|---|
| kind | halt0 | ok |
| VirtualAlloc | 832.1 MB (`live=1259.4MB`) → `Cannot enlarge memory, requested 2427797504 bytes ... limit 2147483648` | 832.1 MB (`live=754.4MB`) で成功 |

`a5adb2fc` の IR では `%ce0n11_function_980ed0 = inttoptr i64 22954112 to ptr` (VA 0x15e4080 のまま)。`2b2faf52` 以降の IR では M2q pass (`9af7827f`, #1043) が `inttoptr i64 18759808` (LVA 0x11e4080) に remap している。

切り分け実験: `a5adb2fc` の IR (`boot_final.ll`) の `22954112` を `18759808` に 1 箇所だけ置換して ON build → survey。

| 構成 | 368 | 888 | 集計 ok/oob/halt0 |
|---|---|---|---|
| `a5adb2fc` ON (remap なし) | ok (832MB) | halt0 (grow 上限) | 869/15/9 |
| `a5adb2fc` ON + remap 1 箇所 | ok | **ok (74.8MB)** | 870/17/6 |

ON で 888 を単独 (368 を `SV_SKIP`) で評価すると ok (live=775.7MB) になり、368 の確保が後続の上限超過の原因であることも確認した。

## 3. survey 2 系統の食い違いの理由

`m11_survey.mjs` は unit ごとに VirtualAlloc 累計上限 `M11_VA_UNIT_BUDGET_MB` (既定 256MB、`m11_rt.c:89`) を掛ける。`survey_units.mjs` はこの予算を掛けない。

`m11_survey.mjs` (`M11_SURVEY_STACK=888`、`a5adb2fc`):

| 構成 | 888 | 368 | va_denied |
|---|---|---|---|
| OFF (既定 256MB 予算) | returned 1 (ok) | 832MB 要求 → OOM 扱い (trap_oom) | 1 |
| ON (既定 256MB 予算) | returned 1 (ok) | 同上 (trap_oom) | 1 |
| ON (`M11_VA_UNIT_BUDGET_MB=0`) | Error (halt, grow 上限) | 832MB 確保に成功 (ok) | 0 |

つまり `m11_survey` の 888 が ok になるのは、368 の 832MB 確保が予算で拒否されて 888 の前の live が膨らまないため。`survey_units` (予算なし) では 368 が確保に成功 (ON) または上限超過 (OFF) し、888 の結果が変わる。両者の食い違いは「予算の有無」で説明できる (論理差ではない)。

## 4. 現 main (`5a45be80`) での再測定

| 構成 | ok | oob | halt0 | miss | other | noproc | 計 |
|---|--:|--:|--:|--:|--:|--:|--:|
| OFF (gate=0) | 870 | 16 | 7 | 47 | 1 | 1 | 942 |
| ON (gate=1) | 870 | 17 | 6 | 47 | 1 | 1 | 942 |

888 は OFF/ON とも ok (74.8MB)。368 は OFF/ON とも ok (M2q 込み)。OFF→ON の unit 別 kind 差は unit 895 (halt0→oob) のみ。`2b2faf52` (前回 PR の測定) と `5a45be80` の survey 結果は一致。

`git diff --stat 2b2faf52 5a45be80 -- tools/m11/trap_triage tools/m11/m11_passes.py tools/m11/qstore tools/m11/m11_build.sh` = 22 files / +984 / -16 (fix912・#1389 系の追加。survey 結果は変わらない)。

## 5. 結論と判定

- 受入条件 1 (888 の退行が VA 上限か論理差か): **論理差 (M2q 欠落)**。VA 上限は直接の原因ではない (上限超過は 368 の 832MB が引き金)。
- 受入条件 2 (survey 2 系統の食い違いの理由): **VA 予算 (`M11_VA_UNIT_BUDGET_MB`) の有無**。
- 受入条件 3 (REPORT 記録): 本 REPORT。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `survey_units.mjs` の OFF→ON 差 (unit 895 halt0→oob) | survey 数値の信頼性 | 本 issue #1231 (数値は main で確認済み、差は 1 unit) |
| `survey_units.mjs` に VA 予算を入れるか (統一) | 2 survey の判定基準が揃わない | 本 issue #1231 の PM 判断 |
| `function_980ed0` 以外の VA→LVA 漏れの全件確認 | 同類の 10 進 inttoptr が残る可能性 | 既存 #1043 の範囲。新規起票は行わない (PM 判断) |
| REPORT_1019 の受入条件 1・2 (unit 149 の原因、gate 既定 ON 化) | #1019 の残り | #1230 (M11-N75) |
