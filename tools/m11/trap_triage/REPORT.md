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

## 6. OOB 44 件の分類と最多分類 (`8cc190` 系 11) の調査 (#419)

素材: work-m11 スナップショット + `m11_build.sh` + `survey_units.mjs` (PE 無しで実行可。逆アセンブルは PE の代わりに
`work/m11_image.bin` を読む `disasm_img.py`)。ベースライン = #414 HEAD `fa918df` の m11_ov.c を build し直した survey:
ok 830 / oob 44 / halt0 20 / abort 1 / miss 46 / noproc 1 (§1 の 829/66 とは halt0 21→20・ok 829→830 が 1 unit 違う。原因未調査)。

### 6.1 最上位 frame 別の分類 (実測、unit 番号)

| 最上位 frame | unit 数 | 原因の状態 |
|---|--:|---|
| `8cc190` (←`8c7a10`←`8c5cc0`) | 11 (53 54 56 58 59 60 61 62 63 307 311) | **原因特定 (§6.2)**: TObject.Create の VMT 間接 call 脱落 |
| `410730` (←`4fb8a0`/`4fb910`) | 6 (101 291 296 304 555 923) | 未調査 |
| `414bb0` (←`652500`←`653660`←`6539e0`) | 5 (144 149 158 280 659) | 未調査 |
| `904190` | 4 (477 484 513 520) | 未調査 |
| `409470` ReallocMem | 4 (830 884 898 936) | §3-2 (転記でハング) |
| `47d460` (←`92d4f0`) | 4 (876 880 891 935) | 未調査 |
| 各 1 unit | 12: `446400`(17) `5b53f0`(95) `407e20`(138) `8674a0`(275) `8dfd70`(314) `96ef10`(365) `417fc0`(503) `6664c0`(547) `407a50`(745) `40ffe0`(895) ほか | 未調査 |

(abort 1 = unit 114 `EnterCriticalSection` shim_unimplemented は OOB ではない。)

### 6.2 `8cc190` 系の原因

`8cc190` 内の OOB 地点は `8cbcb0` の `[[rcx+8]-8]` (wasm offset 0x271497)。`rcx` は `8c7a10` が
`[g+0x410]` (= `8cbfa0` が作った TDictionary 様オブジェクト) から取り出した値。unit 53 で実測すると
`g+0x410 = 0x4c70c0` は **インスタンスではなくコードバイト列** (`[+0]=0x68ec834853565800` は機械語) だった。
`8cbfa0 → 40f9e0 (TObject.Create) → 410320 (ClassCreate stub) / 410360 (AfterConstruction stub)` で、
RetDec は 410320 / 410360 の **VMT 間接 call (`call [rax-0x30]` NewInstance / `call [rbx-0x50]`) を落とし `ret arg1` だけの関数**にしていた
(DEFECTS D15 型。call site は IR 上 410320 が 493、410360 が 492)。このため TObject.Create は確保せず VMT/コード領域を `this` として扱う。

**修正の試行** (`m11_ov.c` に `-DM11_OV_CLASSCREATE=1` で有効化する形で保存、既定 OFF):
`410320`/`410360` を C に転記し、NewInstance 実体 `40f960`(GetMem→InitInstance) と `40fb40`/`40fac0` (InitInstance・管理フィールド初期化) を
逆アセンブル (`disasm_img.py`) から C で再実装。加えて `8cbda0`/`8cbce0` (TDictionary の comparer 間接 call 脱落) も転記。

| 構成 | ok | oob | halt0 | miss | 備考 |
|---|--:|--:|--:|--:|---|
| ベースライン (既定 OFF) | 830 | 44 | 20 | 46 | |
| 410320/410360 のみ | 830 | 30 | 31 | 49 | unit 114 が**ハング** (abort→hang、`5c00e0`→`439670` の探索ループ) |
| + 8cbda0/8cbce0 | 830 | 41 | 20 | 49 | 8cc190 系 11 unit は**全て OOB のまま** |

unit 遷移 (+8cbda0/8cbce0): oob→ok 4 / ok→miss 3 (42 45 415) / ok→oob 2 (85 719) / abort→hang 1 / oob→halt0 1 / halt0→ok 1。
**trap 総数は減っていない (ok 830 のまま、退行 5 件が改善 4 件を相殺)** → 受入条件「最多 1 分類を修正し trap が減る」は **未達**。
退行 5 件は 410320 転記が実際にオブジェクトを確保するようになった副作用で、確保後に別の欠陥 (85: `409470` 経由, 719: `409410` 内 `407a50`) が顕在化した。
8cc190 系 11 unit が OOB のままなのは、確保後もなお `8c7a10` の入力 (`rcx` 先) が不正なため (unit 53 でも `8cbcb0` で OOB)。
次の調査対象は NewInstance 後の `[g+0x410]` の中身と `8cbfa0` の `cls` 引数 (VA 0x4bd878→LVA 同値) の VMT 内容。

**ネガコン**: 既定 OFF で build し直した survey は ベースラインと unit 単位で完全一致 (差 0、ok 830 / oob 44 / halt0 20 / abort 1 / miss 46)。
OFF のまま e2e 入口 (`m11_run.mjs`) は不変、units_run 17/942。

### 6.3 #307 (liftdiff OOB 222) との関係

liftdiff は hybrid closure の per-case 採点 (#307 は `414ad0` 系 68 が最多)、本調査は m11 の 942 unit survey で最多は `8cc190` 系 11。
**`414ad0` は m11 survey の OOB 最上位 frame に現れない** (最上位 frame は上表 16 種)。重なるのは 410360 カスケード
(liftdiff `results/cascade_410360.md`: innermost `f_410360` 573 case、`f_410360<40f9e0` 100 case) と本件の根因 (410320/410360 の VMT 間接 call 脱落) で、
**同一欠陥の別症状である可能性が高い (未検証)**。ただし両者の trap 件数は比較軸 (case と unit) が違うため数値の突合はしていない。
