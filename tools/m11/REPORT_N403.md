# M11 LB_BASE=0x10000 の残差調査 (#403, 部分達成)

親: #222 (PR #303)。素材: fl-win64 (`block00031_PE.bin` 22,227,016 B)・work-m11・toolchain-emsdk・toolchain-retdec (2026-10-13 runner)。
e2e の測定は HEAD `64d09590` で実施。c8b9ad75 との差は `audit_va.py` のみで e2e 結果に影響しない (§1 の audit 実測は c8b9ad75 で実施)。
実行は各 1 回ずつ直列 (ただし同一条件の再実行 2 回で結果が一致したものを記す)。
既知類型との関係: 該当なし (LB 依存差は未切り分けで、`docs/DEFECTS.md` の D1a〜D18 への帰属は未確認。近縁は D11 = PE VA リテラルの切り捨て)。

## 1. audit_va.py の IAT 判定 (受入 1: 原因特定 — 完了)

- 原因: IAT スロット 738/738 の値は **hint/name テーブルの RVA** (ILT と同値、例 `0x15721a4` = `PathUnExpandEnvStringsW`)。
  `[ImageBase, ImageBase+SizeOfImage)` の範囲に入るため VA と誤判定していた。
- 修正前: `iat_slots_holding_image_VA = 738` → exit 1。
- 修正後 (`tools/hostbridge/lowbase/audit_va.py`): hint/name RVA を別集計 (`iat_slots_holding_hint_name_rva = 738`) し、
  `iat_slots_holding_image_VA = 0` → exit 0。DIR64 の判定 (`dir64_targets_outside_image = 0`) は変更していない。
- 既存 REPORT (`REPORT_APPENDIX.md` の IAT 節) の結論「PE 標準の bound 前 IAT の誤検知」と一致。

## 2. LB=0 と LB=0x10000 の `m11_e2e.sh` 比較 (受入 2: 未達)

| 項目 | LB=0 (2 回) | LB=0x10000 (2 回) |
|---|---|---|
| e2e 所要 (再生成なし・build 増分) | 2m10s (初回) | 1m21s (初回) |
| units_run (通常起動) | 53 | 37 |
| 通常起動の終了 | OOB (`memory access out of bounds`) | Halt0 早期終了 (`halt0_early=true`) |
| survey ok / noproc / miss / trap | 870 / 1 / 46 / 25 | 868 / 1 / 46 / 27 |
| trap 内 oom | 1 | 1 |
| wasm_bytes | 6,042,784 | 6,043,167 |

**REPORT_APPENDIX の「stage / survey 集計は一致 (ok 812 / trap 83)」は本 HEAD (`64d09590`) では再現しない。**
LB=0 でも ok 870 / trap 25 で、旧記録 (812 / 83) と別の値になっている。旧記録の HEAD と現 HEAD の差は未切り分け。

### unit 別の結果差 (survey, LB=0 vs LB=0x10000)

全 942 unit のうち結果が食い違うのは 4 件。REPORT の「差 0」は成り立たない。

| unit (VA: LB=0 / LB=0x10000) | LB=0 | LB=0x10000 | 観測 |
|---|---|---|---|
| 40 (`0x105bd0` / `0x115bd0`) | ok | trap (Halt0 → longjmp) | `m11_throw_dllmain_done` 経由。unit 内の Halt 呼出し |
| 153 (`0x265b90` / `0x275b90`) | ok | trap (OOB) | |
| 158 (`0x26d1a0` / `0x27d1a0`) | ok | trap (OOB) | GetMem 139 → 2 |
| 745 (`0xabb3b0` / `0xacb3b0`) | trap (OOB, GetMem 34) | ok (GetMem 36) | REPORT の「SelectObject 3 回追加」は本実行の出力で確認できず |

- unit 873: 両 LB とも ok・VA 要求 0・GetMem 1 で、REPORT の「LB=0 は 1914MB 要求で OOM」は再現しなかった。
- 各 unit の VA 表示は LVA 基準 (LB ぶんずれる) のため、表の左右の VA 文字列は 0x10000 ずれている。

### 再現コマンド (リポジトリ root で実行。`FL_WIN64_DIR` は `tools/shared/env.sh` 経由)

- `M11_LB_BASE=0 bash tools/m11/m11_e2e.sh` — 表の LB=0 列 (survey / units_run / 終了理由)
- `M11_LB_BASE=0x10000 bash tools/m11/m11_e2e.sh` — 表の LB=0x10000 列
- `python3 tools/hostbridge/lowbase/audit_va.py "$FL_WIN64_DIR/extracted/block00031_PE.bin" 0x10000` — §1 の exit 0 / `iat_slots_holding_image_VA=0`

本 PR の作業 runner では work-m11・toolchain-emsdk・toolchain-retdec が無く、上の e2e 2 本は再実行していない (表の数値は HEAD `64d09590` 測定時の記録)。audit は fl-win64 で実行済み。

### LB=0x10000 だけの通常起動 Halt0 (新規観測)

LB=0x10000 では `units_run=37` で Halt0 により早期終了し、`probes.Halt0=1`。LB=0 は 53 unit 実行後 OOB。
unit 40 の trap (上表) はこの Halt0 と同じ経路。**LB 依存で Halt を呼ぶ分岐が増えている可能性がある。** 未確定。

## 3. 全 IR の remap 件数・実行後の guest ポインタ assert (受入 3: 件数は計測・guest ポインタ assert は未着手)

- 計測: `python3 tools/m11/m11_remap_count.py work/boot_final.ll` (未 remap の image VA 即値を数える)。
  ネガティブコントロール `bash tools/m11/m11_remap_count_negctl.sh` で、既知の未 remap 1 件を検出して非 0 になることを確認 (NEGCTL OK)。
- 実測 (LB=0x10000 で生成した `work/boot_final.ll`, ir_sha256 `5dfb1473…`): `inttoptr i64` 即値 4,470 件 (命令形 4,470 / 式形 0)、
  うち image VA 範囲 `[0x400000, 0x400000+0x1ac0000)` に残るもの (= 未 remap) **4,368 件**。
  `m2_inttoptr_remap = 0`・`m2b_remap = 0` (`ir_report.json`) と合わせ、#417 (10 進 inttoptr 命令の全件 remap 未解決) と同じ類型。
- 実行後の guest ポインタ assert (実行結果の VA 範囲検査) は未実装。残件は子 issue へ (下記)。
- `lb_check.py` と IR 指紋 (`ir_sha256`) は LB 別に記録済み (LB=0: `3a9ceb17…`、LB=0x10000: `5dfb1473…`。本 run の実測)。

## 4. 今回 run の再測定 (2026-10-13 runner, base main `73853ba2`, 各 1 回直列)

素材: fl-win64 (`$RUNNER_TEMP/fl-win64`)・work-m11 (`tools/m11/work`)・toolchain-emsdk・toolchain-retdec を展開。
`pip install capstone pefile` を runner に追加 (`m11_e2e.sh` の前提)。

| 条件 | 所要 (wall) | exit | M11_SUMMARY (要点) |
|---|---|---|---|
| `M11_LB_BASE=0` | 150 s | 0 | units_run 53 / survey ok 870 / trap 25 / miss 46 / wasm 6,042,920 |
| `M11_LB_BASE=0x10000` | 98 s | 0 | units_run 37 / survey ok 868 / trap 27 / miss 46 / wasm 6,043,303 / halt0_early=true |

- §2 の旧表 (HEAD `64d09590`) と同値。LB=0 / LB=0x10000 の差は再現。
- `m11_e2e.sh` 自体は exit 0 (未達は現在地を再現して報告する設計)。判定は各 SUMMARY の値で行う。
- 本 run の再測定は、既存 work-m11 の IR (LB=0x10000 で生成) と `m11_build.sh` 増分で行った。`--full` は未実行。

## 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 40 / 153 / 158 / 745 の LB 依存差の原因 (特に unit 40 の Halt 経路と通常起動の Halt0 早期終了) | LB=0x10000 の通常起動が 37 unit で止まる。受入 2 未達 | 本 issue (#403) で継続 |
| REPORT_APPENDIX の旧 HEAD 集計 (812/83) と現 HEAD (870/25) の差 | 既存の数値の根拠が現 HEAD で再現しない | PM が起票 (#222 系) |
| 実行後の guest ポインタ assert (未実装) | 受入 3 の後半 | 子 issue #1004 (M11-N57) |
| 未 remap の image VA 即値 4,368 件 (#417 と同類型) | 受入 3 の件数は計測済み。解消は #417 側 | #417 (既存) |
