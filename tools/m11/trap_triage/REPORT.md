# M11 survey trap 個別原因切り分け (#130) — tools/m11/trap_triage/

**判定: 部分達成 (trap 83 → 66、目標 < 20 は未達)**。halt0 48 unit の発生源を wasm スタックで全数特定し、
最大の原因 `function_417b70` (System.DynArraySetLength) の 1 段 deref 脱落を C 転記 (`m11_ov.c`) で修正した。

## 1. 実測 (HEAD `1eccbfa`、`bash tools/m11/m11_e2e.sh`、16.1 s、load average 0.45)

| 項目 | 修正前 | 修正後 |
|---|--:|--:|
| survey ok | 812 | **829** |
| survey trap 計 | 83 | **66** |
| └ oob / halt0 / abort | 34 / 48 / 1 | 44 / 21 / 1 |
| reached_stage / units_run (通常起動) | 4/6 / 17 | 4/6 / 17 (不変) |
| wasm-ld signature mismatch / undefined | 0 / 0 | 0 / 0 |

unit 遷移 (per-unit JSON 比較): halt0→ok 16 / **halt0→oob 11** / oob→ok 1。halt0→oob の 11 件は、
修正で Halt0 を抜けて先へ進み、次の欠陥 (下記 §3-2) に当たったもの。trap 総数の減少は 17 (= 83−66)。

## 2. halt0 48 unit の原因 (`survey_units.mjs` の Halt0 例外スタックから全数集計)

48 件全てが `Error(reOutOfMemory/reInvalidPtr)` = `function_409730` (または 412a60 経由) → `Halt0` の経路。
CAB-129 REPORT §5 の「GetLocaleInfoW / LoadStringW 相関」は不採用 (halt0 unit が呼ぶ stub は 3 件のみ)。

| Error() 呼出元 | unit 数 | 内容 |
|---|--:|---|
| `417b70` DynArraySetLength | 17 | 引数 `a` と `lengths` の 1 段 deref (`mov rax,[rax]`) が IR で脱落。lengths(スタック addr) が配列長になり GetMem が失敗 |
| `409410` GetMem (内側 `417b70` 経由) | 14 | 上記の波及 (巨大 size 要求 → `VirtualAlloc` が calloc 失敗 → NULL → Error(1))。unit 87 で 559 MB, 245 で 178 MB を要求 |
| `40a1c0` | 6 | 未調査 |
| `416db0` / `4159e0` | 3 / 3 | 未調査 |
| `411d20` (→ `411e80` → `814d30` / `45a2a0`) | 4 | 未調査 |
| `409470` ReallocMem | 1 | 未調査 |

`417b70` の転記後、17 + 14 のうち **16 unit が ok、11 unit が OOB** になった (残りは別経路の Error で halt0 のまま)。

## 3. 修正と残存

1. **`function_417b70` を C 転記** (`m11_ov.c`、逆アセンブル 417b70..417fa2 と突合)。
2. **`function_409470` (ReallocMem) の転記は revert**: 同じ 1 段 deref 脱落 (`cmp [rbx],0` / `mov rcx,[rbx]`) と
   4094da の `llvm.trap` 化けを確認し転記したが、boot 中の unit 884 (`1268010` → `12df090` → `409470`) が
   戻らなくなり survey が完走しなかった (60 s 超でハング。原因は未特定)。転記は採用せず revert。
   → 原因は 409470 ではなく 410320 の脱落 (#418 `REPORT_418.md`) と 5c0270 の deref 脱落 (#474 `REPORT_474.md`)。#474 で再採用済み。
   `409470` 経由の OOB 11 unit (`409470 → 408040 → 407e20`) は残っている。
3. 残 OOB 44 の最上位 frame: `8cc190` ×9 (#130 §6 の通り上流 `8c5cc0` のポインタ破壊)、`414bb0` ×5、`904190` ×4、
   `4fb090`/`410730` ×3、`47d460` ×4 ほか (unit 一覧は `annotate.py` 出力)。個別原因は未調査。

## 4. 再現手順

```sh
# 前提: bash tools/m11/m11_e2e.sh 済み (work/m11_boot.cjs, work/m11_image.bin)
node tools/m11/trap_triage/survey_units.mjs tools/m11/work/trap_triage/after.json    # 942 unit の per-unit JSON (kind / frames / stub / va_mb)
python3 tools/m11/trap_triage/annotate.py tools/m11/work/trap_triage/after.json [unit...]   # export 名で注釈・halt0 の Error() 呼出元集計
python3 tools/m11/trap_triage/disasm_fn.py 417b70 ...   # PE (.pdata 区間) の capstone 逆アセンブル (LD_M11_PE で PE 指定)
```

環境変数: `SV_ONLY=884` (unit 限定)・`SV_TRACE_AT=884` (その unit だけ trace)・`SV_PROG=1` (進捗を stderr)。
`capstone` / `pefile` (pip) が要る。この runner では `/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin`
と `/home/ubuntu/work/webstudio` を symlink / 展開して実行した (PR #301 の方法)。

## 5. 未解決 (下流)

- halt0 残 21 (`40a1c0` 6 / `416db0` 3 / `4159e0` 3 / `411d20` 4 ほか) の個別原因。
- `409470` ReallocMem の転記でハングする原因 (unit 884) と、`409470 → 408040/407e20` OOB 11 unit。 → ハング原因は解決 (#474 `REPORT_474.md`)。
- OOB 44 の個別原因 (`8cc190` 系 9 unit は上流 `8c5cc0`/`8c7a10`)。
- 完了条件 (trap < 20) は未達 (66)。
