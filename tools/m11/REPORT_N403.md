# M11 LB_BASE=0x10000 の残差調査 (#403, 部分達成)

親: #222 (PR #303)。素材: fl-win64 (`block00031_PE.bin` 22,227,016 B)・work-m11・toolchain-emsdk・toolchain-retdec (2026-10-13 runner, HEAD `64d09590`)。
実行は各 1 回ずつ直列 (ただし同一条件の再実行 2 回で結果が一致したものを記す)。

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

### LB=0x10000 だけの通常起動 Halt0 (新規観測)

LB=0x10000 では `units_run=37` で Halt0 により早期終了し、`probes.Halt0=1`。LB=0 は 53 unit 実行後 OOB。
unit 40 の trap (上表) はこの Halt0 と同じ経路。**LB 依存で Halt を呼ぶ分岐が増えている可能性がある。** 未確定。

## 3. 全 IR の remap 件数・実行後の guest ポインタ assert (受入 3: 未着手)

本 run では着手せず。`lb_check.py` と IR 指紋 (`ir_sha256`) は LB 別に記録済み (LB=0: `9a9e223e…`、LB=0x10000: `451ecd03…`)。
全 IR の remap 件数は未計測。

## 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 40 / 153 / 158 / 745 の LB 依存差の原因 (特に unit 40 の Halt 経路と通常起動の Halt0 早期終了) | LB=0x10000 の通常起動が 37 unit で止まる。受入 2 未達 | 本 issue (#403) で継続 |
| REPORT_APPENDIX の旧 HEAD 集計 (812/83) と現 HEAD (870/25) の差 | 既存の数値の根拠が現 HEAD で再現しない | PM が起票 (#222 系) |
| 全 IR の remap 件数・実行後 guest ポインタ assert | 受入 3 | #403 で継続 |
