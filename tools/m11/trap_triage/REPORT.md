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
- `409470` ReallocMem の転記でハングする原因 (unit 884) と、`409470 → 408040/407e20` OOB 11 unit。
- OOB 44 の個別原因 (`8cc190` 系 9 unit は上流 `8c5cc0`/`8c7a10`)。
- 完了条件 (trap < 20) は未達 (66)。

## 6. halt0 残 20 unit の原因特定 (#417)

前提: PR #414 (`130-m11-survey-trap`, fa918df) の上。#414 HEAD を build した `survey_units.mjs` の実測は ok 830 / oob 44 / halt0 **20** / abort 1
(PR #414 本文は「halt0 21」。`m11_e2e.sh` は PE (fl-win64) が runner に無く実行できなかったため、差 1 の原因は未確認)。
分類は `halt0_classify.py` (Error() 呼出元で集計)、呼出経路は `survey_units.mjs` の wasm frame を `annotate.py` で名前解決して実測した。

### 6-1. base の 20 unit の分類 (Error() 呼出元別) と結果

| Error() 呼出元 | unit | 原因 (逆アセンブルと IR の突合) | 結果 |
|---|---|---|---|
| `40a1c0` (FP 例外送出) | 162/184/185/190/370/888/905 (7) | `function_40a3b0` (GetMXCSR: `stmxcsr [rsp]; pop rax; ret`) の IR が `__asm_stmxcsr(0); ret 0` で **pop rax 脱落**。MXCSR マスクが 0 = 全 FP 例外アンマスク扱いになり送出 | `m11_ov.c` で 0x1f80 を返す: 6 unit が ok、190 は OOB へ前進 |
| `4159e0` InitializeArray | 232/492/616 (3) | 型 kind バイト `movzx rcx,[rax]` の load 脱落で kind=0 固定 → default 分岐 `Error(2)` | C 転記: 232/616 は ok、492 は次の `410630` で停止 |
| `416db0` CopyArray | 86/357/496 (3) | 同上 (+ kind 12 の `call [mem]` (416720) が脱落 = D15 型) | C 転記: 3 unit とも ok |
| `411d20` raise | 22/245/279/509/647 (5) | 例外送出。呼出元 `814d30` が `arg3&1` の分岐から `Exception.Create(...)` を呼ぶ。同関数の IR 定数は `inttoptr i64 <10進 VA>` で LVA 未変換 (§6-2) | 未修正 |
| `409470` ReallocMem | 189 (1) | §3-2 の deref 脱落 (転記はハングで revert) | 未解消 |
| `410630` | 493 (1) | `GetCurrentThreadId` と `[obj+8]` の不一致 → `Error(0x19)` (CheckSynchronize 系) | 原因未特定。493 は他修正後に `411d20` 系へ移り、代わりに 492 が `410630` で止まる |

類型対応 (`docs/DEFECTS.md`): GetMXCSR / InitializeArray / CopyArray は RetDec が pop / load を落とす **deref・load 脱落** (§3-1 の 417b70 と同族)、
CopyArray kind 12 は **D15** (メモリ間接 call 脱落)。`411d20` 系は **D11** (PE VA リテラルの座標未変換) の変種の疑い。
DEFECTS.md への採番は PM に委ねる (本 PR は触らない)。

最終 HEAD の halt0 残 8 (`halt0_classify.py`): `411d20` 6 (22/245/279/493/509/647)、`409470` 1 (189)、`410630` 1 (492)。

### 6-2. 10 進 inttoptr 命令形の VA→LVA 未変換 (D11 変種の疑い)

`m11_passes.py` の M2 は `inttoptr i64 0x… to ptr` (16 進) だけを remap する。RetDec は絶対アドレスを `%x = inttoptr i64 <10進> to ptr` でも出し、
`boot_allfx.ll` に 4449 件、うち VA 範囲 (0x400000..0x1ac0000) が **4364 件**残る。`814d30` の `inttoptr i64 200376` / `154720` は LVA ではなく VA 側の値。
`pass_m2p_dec_inttoptr` を実装し 4364 件を全て remap して再 build すると:
- 単体実行 (`SV_ONLY=<unit>`, 25 s timeout): unit 22 / 509 は ok、189/245/279/647 は oob、492/493 は halt0 のまま (halt0 6 → 2 ではなく、oob が増える)
- 全 unit の survey は **unit 503 でハング** (300 s タイムアウト)、503 を除いても 200 s 以内に完走しなかった

全件 remap は副作用が大きく、どの定数が VA のままで正しいか (例: Delphi の RTTI/VMT ポインタ) の仕分けが要るため、`M11_M2P=1` の opt-in とし **既定は OFF**。
本 PR の数値 (§6-3) は M2p OFF のビルド。ハング原因と仕分けは未調査。

### 6-3. 実測 (コミット済み HEAD `0312204`、M2p OFF)

`bash tools/m11/m11_build.sh` (約 9 s) 後に `node tools/m11/trap_triage/survey_units.mjs` (約 16 s) と `node tools/m11/m11_survey.mjs` (0.47 s):

| 項目 | base (#414 HEAD) | 本 PR |
|---|--:|--:|
| ok | 830 | **841** |
| trap 計 (oob + halt0 + abort) | 65 | **54** |
| └ halt0 | 20 | **8** |
| └ oob | 44 | 45 |
| └ abort | 1 | 1 |

unit 遷移 (per-unit JSON 比較): halt0→ok 11 / halt0→oob 1 (unit 190)。`m11_survey.mjs` も ok 841 / trap 54 (oob 45 / halt0 8 / abort 1)。
wasm-ld signature mismatch 0 / undefined 0。

**ネガコン** (HEAD の `m11_ov.c` から該当 override だけ `static nc_*` に改名して無効化 → 再 build → survey。実測):

| 無効化 | ok | oob | halt0 |
|---|--:|--:|--:|
| なし (HEAD) | 841 | 45 | 8 |
| GetMXCSR (`40a3b0`) のみ | 835 | 44 | 15 |
| InitializeArray + CopyArray (`4159e0`/`416db0`) のみ | 836 | 45 | 13 |

いずれも無効化で halt0 が増え (+7 / +5)、有効化で復帰する。

### 6-4. 再現

```sh
bash tools/m11/m11_build.sh
node tools/m11/trap_triage/survey_units.mjs tools/m11/work/trap_triage/head.json
python3 tools/m11/trap_triage/halt0_classify.py tools/m11/work/trap_triage/head.json   # survey 直後に実行 (wasm index は build 依存)
```

M2p の opt-in 検証は `M11_M2P=1 python3 tools/m11/m11_passes.py work/boot_allfx.ll work/boot_final.ll --init-list work/inits_text.txt` の後に
`m11_genstubs.py` と `m11_gen_ir2.sh` 末尾の dotfix を同条件で適用し、`rm work/boot_final3.ll work/obj/boot.o` で再 build する。

## 7. 未解決 (#417 後)

- halt0 残 8: `411d20` 系 6 (§6-2 の座標未変換と M2p のハング)、`409470` 1 (unit 189)、`410630` 1 (unit 492)。
- OOB 45 (unit 190 が halt0→oob で +1)。
- 完了条件 (trap < 20) は引き続き未達 (54)。
