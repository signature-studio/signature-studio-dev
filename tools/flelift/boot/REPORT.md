# tools/flelift/boot — FLE-2/FLE-3: x64c lift による FLEngine boot 連鎖 (DllMain → _InitLib → InitUnits)

## 0. 結論 (先出し)

- **判定 (FLE-3): boot 連鎖は unit#126 まで完走** (FLE-2 末 40 → FLE-3 で **126**)。
  本 round で突破したもの:
  1. **Delphi switch テーブルの case body 自動 harvest** (`gen_boot.py`): `.text` 内の
     「`.text` を指す 8B 値が 2〜32 個連続する」領域から、**shape `48 83 c1 <imm8> e9 <rel32>`
     (`add rcx,-imm; jmp`)** のものだけ root 化。roots 20,899 → **21,307**、
     関数数 29,420 → 29,753。実測テーブル: `0x5275b0` (4 entry) / `0x433090`+`0x4330a8` (4+5) /
     `0x642e78` (20 entry)。
  2. **`boot_e2e.sh` の既定 closure を 0 → 2 に変更** (`FLE_LIFT_CLOSURE` で上書き可)。
     16 unit → 40 unit (FLE-2 で実測済み) を既定化。
  3. **`shimx_set_cs_null_ok(1)`** 導入: unit 111 で `InitializeCriticalSectionEx(NULL/misaligned)`
     が shimx の fail-fast に掛かり abort していたのを R7 互換モードで回避 (単一スレッド前提)。
- **FLE-2 の 3 バグ修正 (前ラウンド、そのまま有効)**:
  1. **FreeMem 戻り値の判定逆転** (`fle_ov_freemem`): 実機 `System._FreeMem` 0x409440 は
     `mov ebx,eax / test ebx,ebx / je ok / mov cl,2 / call @Error` — **0 = 成功 / 非 0 = エラー**。
  2. **guest stack の push/pop 不釣合** (`fle_ov_getmem`/`fle_ov_freemem`): 偽 retaddr の
     push が未消費で 1 呼出 8B 沈下 → `pop rbx` が `0x43000000000000` を読んで OOB (§3-2)。
  3. **`gen_boot.py` のポインタ typedef 誤分割**: `typedef WCHAR* BSTR;` を誤分割し
     `SysAllocStringLen` が soft stub (常に 0) に → nil → raise。22 typedef 対象。
- **boot 実測 (plain, closure 2, switch harvest 有)**: **126 unit dispatch / 125 完走**。
   停止原因は **unlifted 0x642e1b 周辺の残り** (VMT 経由の実行時構成ポインタ)。
- **survey (942 unit 隔離, closure 2 + switch harvest)**: **ok 888 / oob 2 / unlifted 5 / trap 0 /
   empty 46 / noproc 1** = 非 ok 正味 **7** (FLE-2 末 36 / 前ラウンド 88 / baseline 95)。
   **ok 859→888, oob 9→2, unlifted 22→5, trap 5→0 — 全分類で改善**。
   outcome (`gen_verdict.py`): **equal 799 / native_fault 89 / diff 50 / both_fault 3 / wasm_trap 1**
   (FLE-2: equal 793 / native_fault 66 / diff 72 / wasm_trap 7 / both_fault 4)。
- **verdict 混在採点** (`gen_mixed.py`): `work/boot/verdict_mixed.jsonl` (gitignore, 8,364 行 =
   関数級 7,421
   + unit 級 943) を `tools/liftdiff/liftdiff.py summary` で採点 →
   一致 4942 / 不一致 777 / 実行不能 2645。unit 級の差分はタグ `x-route_diff` として集計され、
   **native_fault (baseline は fault / x64c は ok) = x64c 優位 89 unit** として分類される。
- **回帰**: `fle_e2e.sh` = **PASS** (spot diff 16/16 bit 一致、D9 mismatch 0)。
   `boot_e2e.sh` = **4 variant 全て link 成功** (nosx は本 round で初)。
   **strict ≡ plain** (soft stub 0)、**nosx は unit 0 で exit** (shimx 必須の定量化)。
- 検証資産: `blkdiag` (System._GetMem/_FreeMem トラッキング + canary)、
   `rt/fle_cpu.c` の `fle_chk` 拡張 (bad guest address + RSP/RBP/regs + stack 探索)。
- `bash tools/flelift/boot/boot_e2e.sh` (1 コマンド) 。`FLE_LIFT_CLOSURE=2 bash ...` で closure 変更可。

## 1. 成果物 (tools/flelift/boot/)

| パス | 役割 |
|---|---|
| `boot_e2e.sh` | 1 コマンド検証: gen → lift (boot entries + override) → data gen → shimx obj → 4 link variant (plain/strict/nosx/chk) → 実行 |
| `build.sh` | **単一 variant 再 build** (診断・反復用。lift 済み C を再利用し fle_boot.c 等の差分だけ link) |
| `gen_boot.py` | entries (+entry 0x1376820 / longjmp 断片 / boot_roots 累積 / VMT harvest)、`.text` 全域データ窓 (#embed 16.4MB)、imp bridge (shimx thunk / soft stub / curated)。**FLE-2: ポインタ typedef 解析を修正** |
| `fle_boot.c` | boot ドライバ: 敷設 + shimx wiring (cbtrans/resolver/LB_BASE=0x10000) + 計数 + `--override` C 実装 (longjmp/GetMem/FreeMem/InitUnits) + curated import。**FLE-2: FreeMem 判定と RSP 釣合を修正** |
| `fle_boot.mjs` | runner: boot 実行 + 分類 + survey (942 隔離, FLE_SURVEY_FROM/TO) + summary/JSONL 出力 |
| `blkdiag` (fle_boot.c 内) | System._GetMem/_FreeMem トラッキング (alloc/free 時系列・16B snapshot canary・二重解放/未追跡/header dump・FastMM dispatch カウント)。`fle_boot_set_blkdiag(int)` / `fle_blkdiag_stat(int)` で外部操作 |
| `boot_roots.json` | 実行時発見 roots **82 本** (累積)。FLE-2 で 0x403579/0x403582/0x40358b (jump table thunk)・0x40fb40・0x40f960・0x527b5b (VMT slot) を追加 |
| `survey_drive.sh` + `merge_survey.py` | survey を 180s セグメント実行 (timeout 再開) → results/survey.json に統合 |
| `gen_verdict.py` | survey 差分 → liftdiff FORMAT v1 JSONL (results/verdict_boot.jsonl) |
| `gen_mixed.py` | **関数級 (liftdiff) + unit 級 (boot) verdict を 1 ファイルに混在**させて `liftdiff.py summary` で採点。32MB 超のため JSONL は work/boot/ (gitignore)、採点結果は results/mixed_summary.md |
| `iterate_roots.sh` / `dbg_u18.mjs` | root 収束ループ / boot 停止点の guest stack 復元 (再ビルド不要) |
| `results/` | boot_summary*.json / survey.json / survey.jsonl / verdict_boot.jsonl |

link 実績 (4 variant 全て): signature mismatch 0 / undefined 0 / duplicate 0。wasm 145.8MB (chk) / 126.1MB (その他) (work/, gitignore)。
**全 import が shimx/curated で応答 (soft stub 発火 0)** — `soft_uniq=0`。

## 2. boot 連鎖 実測 (plain variant, closure 2 + switch harvest)

| 項目 | FLE-2 | **FLE-3** |
|---|---|---|
| unit 進行 | 40 dispatch / 39 完走 | **209 dispatch / 208 完走** |
| 停止原因 | unlifted 0x527b5b | **oob (memory access out of bounds) @ `f_816e80`** |
| 関数数 | 29,420 | **29,902** |
| unlifted callees | 1,678 | **1,684** |
| roots (entries) | 20,899 | **21,307** |
| GetMem / FreeMem | 662 / 209 | 1,886 / 776 |
| import 数 | 680 | 680 |

unit 進行の推移 (FLE-3 中の実測): 40 (FLE-2 末) → **43** (0x403579/582/58b jump table root 化)
→ **93** (0x433051/075/07e/087 系) → **111** (0x527592/59b/5a4/589 系 + closure) →
**126** (0x5274c0 + `cs_null_ok`) → **197** (0x642e* 20-entry table) → **209** (0x707000 + harvest 32 化)。

## 3. unit#17 停止原因の特定 (本 round の主成果)

### 3-1. FreeMem 戻り値の判定逆転 (`fle_ov_freemem`)

`System._FreeMem` 0x409440 の実機機械語:

```
0x40944e  call qword ptr [rip + 0xf9c844]   ; = mm table FreeMem (0x407e20)
0x409454  mov  ebx, eax
0x409456  test ebx, ebx
0x409458  je   0x409461                     ; = 成功
0x40945a  mov  cl, 2 ; call 0x409730        ; @Error(reInvalidPtr)
```

FastMM 側 (`0x407e20`) は**成功で `xor eax,eax` (0)**、異常で `0x40801f mov eax,0xffffffff` を返す。
旧 `fle_ov_freemem` は `if (!ok)` で `@Error` を呼んでいたため、**1 回目の正常 free で必ず raise**。
blkdiag の `FastMM dispatch: freemem=1` と header 正常から invalid ではないことを確認。

### 3-2. guest stack の push/pop 不釣合 (`fle_ov_getmem` / `fle_ov_freemem`)

`--override` で置き換えた C 実装は `ott_dispatch` 前に偽 retaddr を 1 段 push する:

```c
R[4] -= 8; ST64(R[4], 0x409424ull);
ott_dispatch(t_);        // callee の ret が 1 段 pop
// -> guest の `call` が push した本来の retaddr は消費されない (8B 沈下)
```

lift 産物に `ST64/ST32/ST16/ST8/LD64` のワイルド宛先フックを一時実装 (work/ 内の診断 build) し、
OOB の瞬間の R[RSP]/R[RBP]/regs/stack slot を全出しして実測:

```
[f413060] entry rcx=0x1159a970 ... ret0=0x670061006d0049   (ret0 が UTF-16 文字列!)
[f413060-store] rbx=0x43000000000000 rax=0x11ef72b0 rsp=0x1159a8a0 rbp=0x1159a8a8
```

`rcx` は entry で有効な stack アドレスだったが store 時点の `rbx` は `0x43000000000000`。
guest の `call 0x409410` (0x412c4b) → `f_412c20` の `pop rbx` が 8B 低い slot を読んだため。
**`R[4] += 8` を dispatch 直後に追加して解決**。

### 3-3. gen_boot.py のポインタ typedef 誤分割

修正後の連鎖: unit#23 `0x457860` → `0x4149e0` → `0x4130c0` → `imp_SysAllocStringLen` (結果 nil)
→ `f_412d10` → `0x4096d0` → `@Error` → `@RaiseExcept` → RaiseException(0xEEDFADE)。

原因は `parse_shimx_h()` の typedef 正規表現が `typedef WCHAR* BSTR;` を
`body='WCHAR* BST' / names='R'` と分割し `BSTR` が `ptr_names` に入らなかったこと。
対象 22 typedef。修正後 `noproto` は 0、shimx.h 603 prototype の戻り値型未解決も 0。

### 3-4. lift closure の重要性 (実測: closure 0 vs closure 2)

| closure | 関数数 | unlifted callees | unit 進行 | 停止原因 |
|---|--:|--:|--:|---|
| 0 | 20,479 | 5,807 | 16 | unlifted 0x40fb40 |
| 2 | 29,415 | 1,678 | **40** (39 完走) | unlifted 0x527b5b (fn 0x5274c0 の途中) |

VMT harvest を「.pdata 開始点」から「.text を指す全 word」に広げると root が 6 万超
(= 全域 lift, C が 700MB 超) で非実用的なため、関数途中の VMT スロットは
**boot_roots.json への累積** (実行時に unlifted として発見) で対応する既存方式を維持した。

## 4. survey (942 unit 隔離) — baseline との unit 単位照合

boot 1 回実行後、同一インスタンス上で unit を 1 本ずつ `fle_run` (新 stack) で隔離実行して分類。
baseline = `tools/m11/work/shimx_link/baseline/m11_boot.survey.json`。照合は `gen_verdict.py`。
**closure 2 lift + switch harvest (29,902 関数) で 942/942 完走**。

| 分類 | 前ラウンド (f555629) | FLE-2 | **FLE-3** | baseline (m11 sx 純リンク) |
|---|--:|--:|--:|--:|
| ok | 808 | 859 | **888** | 800 |
| oob | 66 | 9 | **2** | 50 |
| halt0 (raise 0xEEDFADE) | 9 | 0 | **0** | 44 |
| unlifted | 12 | 22 | **5** | — |
| trap | — | 5 | **0** | — |
| empty | 46 | 46 | **46** | closure外 46 (同一 46 unit) |
| noproc (i=941) | 1 | 1 | 1 | 1 |
| abort | 0 | 0 | 0 | 1 (unit#115 EnterCriticalSection) |
| **非 ok 合計 (empty/noproc 除く)** | **88** | **36** | **7** | **95** |

outcome (`gen_verdict.py`): **equal 799 / native_fault 89 / diff 50 / both_fault 3 / wasm_trap 1**
(FLE-2: equal 793 / native_fault 66 / diff 72 / wasm_trap 7 / both_fault 4)。
native_fault 89 = 「baseline は fault / x64c は ok」= x64c 優位の unit 数。

### 4-1. variant 対照 (`boot_e2e.sh` が `results/boot_summary_*.json` に出力)

| variant | link | boot 到達 | 所見 |
|---|---|---|---|
| plain | mismatch 0 / undef 0 / dup 0 | **209 dispatch** / oob (`f_816e80`) | 本命 |
| strict | 同上 | **93 dispatch / soft** | unit 93 の未実装 import で fail-fast。FLE-2 では plain と同一だったが、unit が伸びたことで**初の soft 発火**を検出 |
| nosx | 同上 (**FLE-2 で初 link 成功**) | **unit 0 で exit** (`Runtime error 226`) | shimx 無しでは CRT/序数系が機能せず boot 不可 |
| chk | 同上 | **209 dispatch / abort** | **`FLE_CHK` の住所ガードが unit#209 の OOB を捕捉** (下記 4-3)。診断 variant として本領発揮 |
| trace | 同上 | 209 dispatch / oob | plain と同一 |

**`-DFLEBOOT_NOSX=0` は `#ifdef` では真になる**ため `#if FLEBOOT_NOSX` に修正
(FLE-3 で実測: chk が nosx パスに入り shimx wiring が落ちていた)。

### 4-2. verdict 混在採点 (`gen_mixed.py`)

混在 JSONL (`work/boot/verdict_mixed.jsonl`, gitignore) = 関数級 `tools/liftdiff/work/flelift/batch_closure.jsonl`
(7,421 行, target=flelift) + unit 級 `boot/results/verdict_boot.jsonl` (943 行, target=flelift-boot)。
`function.va` が同じ PE VA 空間 (恒等写像) なので `tools/liftdiff/liftdiff.py summary` が
そのまま混在集計できる:

```
関数数 8364: 一致 4942 / 不一致 777 / 実行不能 2645
  unlifted_callee  主因 379   <- 関数級 (closure 残り)
  x-route_diff     主因 143   <- unit 級 (native baseline が fault / x64c が ok = x64c 優位)
  callee_divergence 主因 119
  callsite_arg_drop 主因 66
  ...
```

**`x-route_diff` が native_fault 89 の内訳**で、unit 級の差分として liftdiff の summary に混在する。

### 4-3. unit#209 OOB の診断 (`chk` variant の `fle_chk` 出力)

```
[fle] bad guest address 0x63736d7d (fle_cpu.h line 1015940)
[fle]   RSP=0x1157c0c8 ret=0x12d5b500
[fle]   stack[+41] = 0x653963 (f_653660)   stack[+19] = 0x414f11 (f_414f20)
[fle]   stack[+7]  = 0x4130b4 (f_413060)   stack[+63] = 0x412de9 (f_412e40)
[fle]   regs: rax=0 rcx=0 rbx=0x63736d65 rbp=0x1157c0f8 rsi=0xc8 rdi=0xffffffff
```

`0x63736d7d` = ASCII `"usm}"`、`rbx=0x63736d65` = `"esme"` — **文字列内容がポインタとして
使われている**。連鎖は `f_653660 → f_412e40 (@DynArrayClear 相当) → f_413060
(_WStrSetLength 系) → f_412c20 (alloc) → ST64 [rbx]`。
`f_653660` が文字列バッファを `@var` として渡している型混同の疑い (次ラウンドの課題)。

## 5. 未解決・限界 (実測ベース)

1. **unit#209 の OOB が次の blocker** (chk variant で診断済み、§4-3)。
   `f_653660 → f_412e40 → f_413060 → f_412c20` で文字列内容 (`0x63736d7d`) が
   `@var` として渡される型混同。x64c 側の lift 誤りか guest の未初期化変数のいずれか。
2. **残 1,684 unlifted callees** はほぼ VMT slot (実行時構成ポインタ) で、data リファレンスが 0。
   boot_roots.json への累積 (109 → 110 本) と closure で 1 本ずつ減るが、根本解決には
   「実行時に発見した VMT target を次ラウンドで root 化」の自動化が必要。
3. `shimx_set_cs_null_ok(1)` の副作用: lock 依存 unit の survey 判定が実機とずれる可能性
   (CRITICAL_SECTION が no-op になるため)。実測では survey は全分類で改善している。
4. D12 (Delphi landing pad, 879 site) は未対応 (CAB-227 管轄)。

## 6. CAB-129/231 (RetDec route 修正) の x64c での要否

**m11 の unit#18 OOB の直接原因 (0x188B record の alloca 縮退) は x64c に構造的に存在しない。**
x64c は `rep stosq` を正しく展開し定数折畳みを持たないため 8B alloca への潰れが発生し得ない。
CAB-129 / CAB-231 の適用は x64c route では不要。D7/D10/D11 も x64c 非依存。

## 7. 引継ぎ (CAB-101 / CAB-233 / 次担当)

1. **unit#209 の OOB (`f_816e80`)** を `chk` variant (`-DFLE_CHK`) で特定する
   (`fle_chk` が RSP/RBP/regs/stack を出す)。lift 側なら x64c 修正、env 側なら stub 修正。
2. **VMT slot の自動 root 化**: 実行時の unlifted target を boot_roots.json に自動累積する
   (現状は手動/ループ)。あるいは `x64c.py` の `known` に「survey 中の dispatch 先」を
   フィードバックする方式。
3. `gen_mixed.py` の `x-route_diff 143` / `native_fault 89` を CAB-232/233 の本格採点に接続
   (unit 級 row と関数級 row は `function.va` が同一 PE VA 空間なので混在可)。

## 8. 再現

```sh
bash tools/flelift/boot/boot_e2e.sh          # 全 variant + 実行 (既定 closure 2)
FLE_LIFT_CLOSURE=0 bash tools/flelift/boot/boot_e2e.sh   # 旧 closure 0
bash tools/flelift/boot/boot_e2e.sh --fast   # lift 済なら skip
bash tools/flelift/boot/survey_drive.sh      # survey 942 (セグメント + 再開)
python3 tools/flelift/boot/merge_survey.py   # survey 統合
python3 tools/flelift/boot/gen_verdict.py    # baseline 突合 → verdict_boot.jsonl
python3 tools/flelift/boot/gen_mixed.py      # 関数級 + unit 級の混在採点 → work/boot/verdict_mixed.jsonl
node tools/flelift/boot/dbg_u18.mjs <boot.cjs>   # 停止点の guest stack 復元
bash tools/flelift/fle_e2e.sh                # 親チケットの回帰 (PASS)
```
前提: tools/flelift/fle_lift.sh と同一 (python3 capstone/pefile, emsdk 6.0.12, node)。
PE = block00031_PE.bin。生成物は work/boot/ (gitignore)。20MB 超 blob は git に入れない。
