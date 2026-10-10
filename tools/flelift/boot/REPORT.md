# tools/flelift/boot — FLE-2: x64c lift による FLEngine boot 連鎖 (DllMain → _InitLib → InitUnits)

## 0. 結論 (先出し)

- **判定: 部分達成 (boot 連鎖は Delphi unit init まで実働、unit#17 で停止)**。
  x64c lift (tools/flelift) の産物だけで `fle_data_install` → `.text` 窓敷設 → TEB 敷設 →
  `fle_run(0x1376820 = DllMain, DLL_PROCESS_ATTACH)` → `_StartLib(0x41d8f0)` → `_InitLib(0x412160, 8 引数)` →
  `InitUnits(0x4120c0)` の連鎖が完結し、**Delphi memory manager table (0x13a5c90) が実 FastMM 実装
  (0x407a50/0x407e20/0x408040) に設定され、unit init が実行される**ところまで到達した。
  `bash tools/flelift/boot/boot_e2e.sh` (1 コマンド) / `iterate_roots.sh` (収束ループ) / `survey_drive.sh`
  (hang 対策 survey) / `gen_verdict.py` (FORMAT v1 記録) を整備。
- **boot 実測**: unit 17 本を dispatch (**16 本完走**) 後、**17 本目 (i=16, proc 0x454090) の body 内で停止**。
  停止原因は Delphi レベルの `raise 0xEEDFADE` (`System.@Error` → `@RaiseExcept` 0x411d20 → `RaiseException`)。
  直接 cause: unit#17 が呼ぶ `@DynArraySetLength` (0x414ad0, call site 0x45440a) の**旧 block FreeMem が
  FastMM invalid pointer を返した** (guest stack 復元で特定、§3)。
  RetDec route baseline は「17 本完走後 unit#18 (0x455790) で OOB」(原因 = RetDec の 0x188 record `rep stosq`×49
  を 8B alloca に潰す欠陥 = CAB-129/231 クラス)。**x64c はその欠陥を構造的に持たない** (0x188 record は
  正しく lift 済、unit#18 の leaf 群 `_UStrAsg`/`Move` は bit-exact 実証済 — tools/flelift/REPORT.md §5.4)。
  なお連鎖の進行は **RetDec route より 1 unit 少ない** (x64c: 16 完走 / RetDec: 17 完走) — unit#17 は
  連鎖状態依存の課題 (§4-1)。
- **survey 942 unit 隔離実行 (実施)**: **ok 808 / oob 66 / unlifted 12 / halt0 9 / empty 46 / noproc 1**。
  RetDec baseline (m11 sx 純リンク, ok 800 / oob 50 / halt0 44 / closure外 46 / abort 1 / noproc 1) と
  unit 単位で照合した結果: **halt0 → ok 20 本 / oob → ok 7 本を回復、非 ok は正味 7 本減 (95 → 88)**。
  一方で新規 oob 増 (ok→oob 14, halt0→oob 13) と **unlifted 12 本** (新クラス) が残る (§4)。
- **liftdiff FORMAT v1 で記録済み**: `results/verdict_boot.jsonl` (943 行 = boot 連鎖 1 + survey 942、
  `gen_verdict.py` が再生成可能。baseline を native 側、x64c を wasm 側に対応付け)。
- **前回 session (ses_eda67897cffe, insufficient_credits で中断) の残骸は正常と判定し全て採用**:
  boot/ スクリプト群 + `rt/fle_cpu.{c,h}` (fail-fast hook / dispatch probe) + `x64c.py`
  (delay import 同一扱い + thunk の dispatch case 追加) — いずれも 23:40 の lift+build が成功しており
  実測データ (results/) と整合。

## 1. 成果物 (tools/flelift/boot/)

| パス | 役割 |
|---|---|
| `boot_e2e.sh` | 1 コマンド検証: gen → lift (boot entries + override) → data gen → shimx obj → 4 link variant (plain/strict/nosx/chk) → 実行 |
| `gen_boot.py` | entries (コミット済み fle_entries.json + entry_point 0x1376820 / longjmp 断片 0x1376840 + boot_roots.json 累積 + VMT harvest)、`.text` 全域データ窓 (#embed 16.4MB)、imp bridge (shimx thunk / soft stub / curated) |
| `fle_boot.c` | boot ドライバ: 敷設 + shimx wiring (cbtrans / proc resolver / LB_BASE=0x10000) + 計数 + `--override` C 実装 (longjmp 0x4126f0 / GetMem 0x409410 / FreeMem 0x409440 / InitUnits 0x4120c0) + curated import (RaiseException/ExitProcess/GetProcAddress/LoadStringW/memset/MessageBox*/VirtualAlloc) |
| `fle_boot.mjs` | runner: boot 実行 + 分類 + survey (942 隔離, FLE_SURVEY_FROM/TO) + summary/JSONL 出力 |
| `iterate_roots.sh` | 収束ループ: lift → build → boot → 実行時 unlifted target / address-taken を boot_roots.json へ累積 |
| `boot_roots.json` | 実行時発見 roots 76 本 (累積)。本次で 0xd0e680 (unit#667 survey target, .pdata 開始) を追加 — **次回 lift で反映** |
| `survey_drive.sh` + `merge_survey.py` | survey を 180s セグメントで実行 (timeout 再開つき) → results/survey.json に統合 |
| `gen_verdict.py` | survey 差分 → liftdiff FORMAT v1 JSONL (results/verdict_boot.jsonl) |
| `dbg_u18.mjs` | boot 停止点の guest stack 復元 (再ビルド不要の診断ツール) |
| `results/` | boot_summary.json / survey.json / survey_seg_*.{json,jsonl} / verdict_boot.jsonl |

link 実績 (plain): signature mismatch 0 / undefined 0 / duplicate 0。wasm 142.9MB (work/, gitignore)。
**全 import が shimx/curated で応答 (soft stub 発火 0)** — `soft_uniq=0`。

## 2. boot 連鎖 実測 (plain variant, 2026-10-11 時点の lift)

| 項目 | x64c (本 ticket) | RetDec baseline (m11 REPORT §実測) |
|---|---|---|
| 到達 stage | DllMain → _StartLib → _InitLib → InitUnits → unit#17 body 内 | DllMain → _StartLib → _InitLib → InitUnits → unit#18 冒頭 |
| unit 進行 | **17 dispatch / 16 完走**、17 本目 (i=16, **0x454090**) で raise | **17 完走**、#18 (**0x455790**) で OOB trap |
| 停止原因 | `@DynArraySetLength` (0x414ad0 @ 0x45440a) の旧 block **FreeMem 失敗** → `@Error` → raise 0xEEDFADE | RetDec が 0x188B record (`rep stosq`×49 @ 0x44bb70) を 8B alloca に潰し stack 破壊 → `_UStrAsg` OOB |
| FastMM | table 実装 0x407a50/0x407e20/0x408040、GetMem 59 / FreeMem 1 (失敗) / VirtualAlloc 1 回 1,310,704B | GetMem 13 / FreeMem 1 / VirtualAlloc 1 回 1,310,704B (= FastMM4 MediumBlockPoolSize、両 route 一致) |
| longjmp / halt0 | 0 (Halt0 経路未発火; raise は SEH 経由) | Halt0 → longjmp は JS ハックで実証 (m11_ov.c) — x64c では lift された 0x4126f0 が直接動く |
| exit / getproc / soft | 0 / 4 (GetProcAddress=0 stub) / 0 | — |

計数位置の注記: x64c の GetMem 計数は `System._GetMem` (0x409410 override)、m11 の 13 は FastMM 実体
(0x407a50) 計数で測定点が異なる (直接比較は非対応)。

## 3. unit#17 停止点の特定 (dbg_u18.mjs — guest stack 復元, 3 回実行すべて同一)

raise 時の emulated RSP = 0x1159c440。stack 上の `.text` qword から復元した live chain (下 = 内側):

```
@RaiseExcept 0x411d20 → RaiseException(0xEEDFADE)          [ret 0x411e4d = 通報地点]
 ← 0x411e60 ← 0x449c10 (call 0x411e60 @ 0x449c8d)
 ← @Error 0x409730 (System.Error, ret 0x409741) ← 0x4096d0
 ← _FreeMem 0x409440 の失敗経路 (fle_ov_freemem が push した ret 0x409461 が stack 上に 6 個)
 ← FreeMem wrapper 0x412d60 (lock xadd 減算 → 0 → FreeMem, call @ 0x412d94)
 ← @DynArraySetLength 0x414ad0 (旧 block 解放, ret 0x414b9c)
 ← unit#17 body (proc 0x454090, call @ 0x45440a, ループ内で SetLength((n-2)/2))
 ← InitUnits 0x4120c0 (ret 0x412129 = fle_ov_initunits の unit 呼出点)
 ← _InitLib 0x412160 (ret 0x41229a) ← _StartLib 0x41d8f0 (ret 0x41d989)
 ← DllMain 0x1376820 (ret 0x1376875) ← fle_run (ret 0xdead0000 = stack 底)
```

- 実行中 unit は `units_run` 番目 (1-based) = **i=16 = 0x454090 (unit#17)**。
  旧 `fle_boot.mjs` の `stopped_at_1based = units_run + 1` は off-by-one だった (units_run は開始計数) — 修正済み。
- survey の隔離実行では unit#17 (i=16) は **ok** (悪い分類に出ない)。つまり本停止は unit 単体の欠陥ではなく
  **16 unit 分の FastMM heap / global 状態が絡む連鎖状態依存** (旧 block の refcount / header 破壊の疑い、未特定)。

## 4. survey (942 unit 隔離) — baseline との unit 単位照合

方法: boot を 1 回実行した後、同一インスタンス上で unit を 1 本ずつ `fle_run` (新 stack) で実行し
ok / oob / trap / halt0 (raise 0xEEDFADE) / unlifted / empty / noproc に分類。
baseline = `tools/m11/work/shimx_link/baseline/m11_boot.survey.json` (m11 sx 純リンク, per-unit 付き)。
照合スクリプト: `gen_verdict.py` (全 942 unit 突合, unexec 0)。

| 分類 | x64c | baseline (m11 sx 純リンク) | 差 |
|---|--:|--:|--:|
| ok | **808** | 800 | +8 |
| oob | 66 | 50 | +16 |
| halt0 (raise 0xEEDFADE) | **9** | 44 | **-35** |
| unlifted (新クラス) | 12 | — | +12 |
| empty (対象外 filler: proc 先が 0) | 46 | closure外 46 (同一 46 unit) | 0 |
| noproc (i=941) | 1 | 1 | 0 |
| abort | 0 | 1 (unit#115 EnterCriticalSection) | -1 |
| **非 ok 合計 (empty/noproc 除く)** | **88** | **95** | **-7** |

unit 単位の遷移 (baseline → x64c): ok→ok 781 / **halt0→ok 20** / **oob→ok 7** (回復計 27) /
oob→oob 38 / halt0→halt0 8 / ok→oob 14 / halt0→oob 13 / →unlifted 12 (ok 5 + oob 4 + halt0 3) /
abort→oob 1 / oob→halt0 1。outcome 集計: equal 781 / both_fault 47 / native_fault 27 / wasm_trap 19 / diff 68。

halt0 9 本の内訳: すべて `raise 0xEEDFADE` (i = 291, 296, 492, 493, 555, 584, 745, 923, 935)。

### 4-1. unlifted 12 本の内訳 (FLE-2 の新知見)

dispatch 先 VA の実体: **.pdata 開始と一致するのは 1 件のみ** (0xd0e680, i=666 → boot_roots.json に追加済、次回 lift 反映)。
残り 11 件は .text 内でも .pdata 範囲外 (0x403582 / 0x43307e / 0x477e86 / 0xc99f10 / 0xda0a08 / 0x928db0) または
image 外 / .bss の garbage (0x11eac770 / 0x11e4f440 / 0x81485356 / 0xa88d8b48) — つまり **root 追加で解決する
被覆不足ではなく、boot が unit#17 で止まったために unit#18 以降が作るはずの runtime 構造 (VMT 登録等) が
無いことによる未初期化 dispatch** が主体。root として lift すると命令境界でない可能性が高く危険 → 追加せず。

## 5. 未解決・限界 (実測ベース)

1. **unit#17 (0x454090) の FreeMem invalid pointer が次の blocker**。`@DynArraySetLength` の旧 block 解放で
   FastMM が invalid を返す。refcount 二重減算 / header 破壊 / 非ヒット block free のいずれか。隔離では ok なので
   連鎖状態依存。FastMM 実装 (0x407e20) の block header 検査ログ実装が最短の特定路。
2. oob 66 本 (baseline 50 から +16) の内訳は未掘削。ok→oob 14 本は x64c 側の新規課題
   (例: i=17 = 0x455790 も隔離では oob — m11 の alloca 縮退とは別原因の可能性、未特定)。
3. strict / nosx / chk variant の link は boot_e2e.sh に実装済みだが、**結果ファイルは未生成**
   (前回 session は plain の収束を優先)。shimx 寄与の対照計測 (nosx) は未実施。
4. D12 (Delphi landing pad, 879 site) は未対応 (CAB-227 管轄)。SEH 巻き戻しは raise → JS 例外化で代用中。
   Halt0→longjmp (0x4126f0 override) は lift 関数として実働するが、boot では未発火 (survey halt0 も longjmp
   ではなく raise 経由)。
5. GetProcAddress = 0 返却 stub (m11 旧挙動の踏襲) のまま — 4 回呼ばれたが unit init は続行した。
6. survey は boot 中断後の状態 (unit#17 部分実行含む) を引き継ぐ。完全な連鎖貫通後の再 survey が本来の形。
7. survey を 1 プロセスで通し実行すると **unit i=283 で状態依存 hang** (seg_0 が 180s timeout で停止した
   地点と同一; i=283 の隔離実行では oob で即終了する)。このため survey は `survey_drive.sh` (セグメント実行 +
   timeout 再開) で実施し、`boot_e2e.sh` の実行系は --boot-only 化した (FLE-2 で修正)。

## 6. CAB-129/231 (RetDec route 修正) の x64c での要否 — 確認結果

**m11 の unit#18 OOB の直接原因 (0x188B record の alloca 縮退) は x64c に構造的に存在しない。**
x64c は `rep stosq` を正しく展開し (tools/flelift REPORT §2, §5.4: Move/`_UStrAsg` 経路は bit-exact 実証)、
定数折畳み最適化を持たないため 8B alloca への潰れが発生し得ない。ただし **0x44bb70 自身は x64c の boot では
未実行** (unit#18 未到達) であり、実証は「unit#17 が同規模の stack record frame (rbp+0x28..0x1b0) を
`@DynArraySetLength` 経由で破壊なく使用した」ことと lift 産物の静的確認にとどまる。
したがって CAB-129 (alloca 縮退系) / CAB-231 (RetDec artifact fixup 系) の適用は x64c route では不要。
零定数折畳み (D7) / jump table (D10) / chained .pdata (D11) も x64c 非依存 (tools/flelift/REPORT.md §4)。

## 7. 引継ぎ (CAB-101 / CAB-233 / 次担当)

1. unit#17 の FreeMem 失敗特定 (§5-1) — 連鎖貫通の最短路。
2. `boot_roots.json` に 0xd0e680 追加済み → 次回 `iterate_roots.sh` / `boot_e2e.sh` の lift で反映される。
   survey unlifted 12 本の残りは boot 貫通後の再 survey で再分類すること (§4-1)。
3. liftdiff 本格採点 (CAB-232/233): `results/verdict_boot.jsonl` の unit row と liftdiff の関数 row は
   `function.va` が同じ PE VA 空間 (恒等写像) — summary 集計にそのまま混在可能 (target 名 `flelift-boot`)。
4. strict/nosx/chk の対照実験 (§5-3) と、連鎖貫通後の survey 再実行 (`survey_drive.sh` → `merge_survey.py`
   → `gen_verdict.py` の 3 点で記録更新)。

## 8. 再現

```sh
bash tools/flelift/boot/boot_e2e.sh          # 全 variant (lift 込み, 数十分)
bash tools/flelift/boot/boot_e2e.sh --fast   # lift 済なら lift skip (plain 実行のみ)
bash tools/flelift/boot/iterate_roots.sh 3   # root 収束ループ (unlifted 累積 → 再 lift)
bash tools/flelift/boot/survey_drive.sh      # survey 942 (セグメント実行) → results/survey.json
python3 tools/flelift/boot/merge_survey.py   # survey 統合のみ
python3 tools/flelift/boot/gen_verdict.py    # baseline 突合 → results/verdict_boot.jsonl
node tools/flelift/boot/dbg_u18.mjs <boot.cjs>   # boot 停止点の stack 復元 (診断)
```
前提: tools/flelift/fle_lift.sh と同一 (python3 capstone/pefile, emsdk 6.0.12, node)。PE = block00031_PE.bin。
生成物 (wasm 142.9MB / text.bin 16.4MB 等) は work/boot/ (gitignore)。20MB 超 blob は git に入れない。
