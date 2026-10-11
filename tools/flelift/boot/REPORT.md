# tools/flelift/boot — FLE-2/FLE-3: x64c lift による FLEngine boot 連鎖 (DllMain → _InitLib → InitUnits)

## 0. 結論 (先出し)

- **判定 (累積, FLE-4 末): unit 進行 209 止まりだが survey は全 942 unit で functional**
  (FLE-1 17 → FLE-2 40 → FLE-3 209 → FLE-4 は unit 209 で blocker 変更)。
  **FLE-2/FLE-3 で突破したもの** (累積):
  1. **Delphi switch テーブルの case body 自動 harvest** (`gen_boot.py`): `.text` 内の
     「`.text` を指す 8B 値が 2〜32 個連続」領域から shape `48 83 c1 <imm8> e9` のものだけ root 化。
     roots 20,899 → 21,307、関数数 29,420 → 29,753。実測テーブル: `0x5275b0`(4) /
     `0x433090`+`0x4330a8`(4+5) / `0x642e78`(20 entry)。
  2. **`boot_e2e.sh` の既定 closure を 0 → 2 に変更** (`FLE_LIFT_CLOSURE` で上書き可)。
  3. **`shimx_set_cs_null_ok(1)`** 導入 (`InitializeCriticalSectionEx(NULL)` の fail-fast 回避)。
- **FLE-4 の成果 (unit#209 OOB の原因特定と修正)**:
  1. **原因特定**: `chk` variant の `fle_chk` が報告する `__LINE__` は **lift 生成 C の行番号**
     (= 1015940) で、これを辿ると **`0x8157c1: call qword ptr [rbx + 0x18]`** (仮想呼出)。
     `f_815050` の実測: `obj = *(0x15F6F78)` (VMT 0x666fa0 を持つ正常ヒープオブジェクト) だが
     **`obj->field_8 == 0`**。`mov rbx,[rax]; call [rbx+0x18]` は **NULL 仮想呼出**になる。
     ネイティブ Windows では AV だが、wasm では linear address 0 に emscripten magic
     (`"emsc"` = 0x63736d65) があるため `call [0x63736d7d]` で OOB。
     **「文字列内容が @var として渡される型混同」という前ラウンド報告は誤りで、
     実際は NULL フィールドへの仮想呼出** (訂正)。
  2. **NULL ページ guard** (`fle_boot.c`): 初回 install 時に `[0, 0x1000)` を 0 埋めする。
     guest イメージは 0x400000 始まりで未使用領域。NULL 仮想呼出は `ott_unlifted(0)` →
     m11 と同じ icall-miss 規約 (ret 0) で graceful に継続する。
     `fle_boot_set_nullpage(1)` で無効化可能。
  3. **次の blocker も特定**: `unlifted 0x6a7b70` は `f_6a7f50` (unit 終了フック) が 0x15F4B80 に
     設定する **fill コールバック**。root 化すると `f_6c7900` の fill ループが未初期化幅
     (0xffffa = 1,048,570 回) で暴走して ExitProcess → survey が成立しない。
     **boot_roots.json からは除外** (unlifted で止める方が survey は functional)。
- **FLE-4 実測値**:
  - **survey (942 unit 隔離, closure 2)**: **ok 888 / oob 2 / unlifted 5 / empty 46 / noproc 1**
    (FLE-3 末 ok 888 / oob 2 / unlifted 5 / empty 46 / noproc 1 と同一 — NULL page guard は
    unit#209 の OOB を除く survey 結果を変えない)。
  - **verdict 混在採点** (`gen_mixed.py` の target 別レポート):
    関数級 (target=flelift) 7,421 行 + unit 級 (target=flelift-boot) 943 行 = 8,364 行。
    一致 4,942 / 不一致 777 / 実行不能 2,645。
    unit 級の **x-route_diff 143** のうち **native_fault = 89** (native 側 fault / x64c ok = x64c 優位)。
  - **variant 4 種 link**: plain / strict / nosx / chk 全て error 0
    (chk の `fle_chk` は `fle_cpu.c` も `-DFLE_CHK` でビルドする必要がある — boot スクリプト修正)。
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
| `boot_roots.json` | 実行時発見 roots **110 本** (累積)。0x403579/0x403582/0x40358b (jump table thunk)・0x40fb40/0x40f960・0x527b5b 等を追加。**0x6a7b70 は意図的に除外** (§3-4) |
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

### 3-1. (FLE-2 累積) 3 バグ修正の要点

1. **FreeMem 戻り値の判定逆転** (`fle_ov_freemem`): 実機 `System._FreeMem` 0x409440 は
   `mov ebx,eax / test ebx,ebx / je ok / mov cl,2 / call @Error` — **0 = 成功 / 非 0 = エラー**。
   (FastMM 0x40801f は `mov eax,-1`)。旧コードは `if (!ok)` で `@Error` を呼び正常 free を
   エラー扱いしていた。
2. **guest stack の push/pop 不釣合** (`fle_ov_getmem`/`fle_ov_freemem`): C override が
   `ott_dispatch` 前に独自の偽 retaddr を push して 1 呼出 8B 沈下。呼出元の `pop rbx` が
   8B 低い slot を読み `rbx = 0x43000000000000` → OOB。`R[4] += 8` を dispatch 直後に追加して解決。
3. **`gen_boot.py` のポインタ typedef 誤分割**: `typedef WCHAR* BSTR;` を
   `body='WCHAR* BST'` と誤分割 → `SysAllocStringLen` が soft stub (常に 0) → nil → raise。
   22 typedef 対象。修正後 `noproto` 0 / shimx.h 603 prototype の戻り値型未解決 0。

### 3-2. lift closure の重要性 (closure 0 vs closure 2 の実測)

| closure | 関数数 | unlifted callees | unit 進行 | 停止原因 |
|---|--:|--:|--:|---|
| 0 | 20,479 | 5,807 | 16 | unlifted 0x40fb40 |
| 2 | 29,415 | 1,678 | **40** (39 完走) | unlifted 0x527b5b (fn 0x5274c0 の途中) |

### 3-3. (FLE-4) unit#209 の OOB 原因と NULL ページ guard

`chk` variant の `fle_chk` が報告する `__LINE__` は **lift 生成 C の行番号** (= 1015940) で、
これを辿ると **`0x8157c1: call qword ptr [rbx + 0x18]`** (仮想呼出)。`f_815050` の実測:
`obj = *(0x15F6F78)` (VMT 0x666fa0 を持つ正常ヒープオブジェクト) だが **`obj->field_8 == 0**。
`mov rbx,[rax]; call [rbx+0x18]` は **NULL 仮想呼出**になる。
ネイティブ Windows では AV、wasm では linear address 0 の emscripten magic
(`"emsc"` = 0x63736d65) を読んで `call [0x63736d7d]` で OOB。
**前ラウンド報告の「文字列内容が @var として渡される型混同」は誤り** (訂正)。
対策: `fle_boot.c` が初回 install 時に `[0, 0x1000)` を 0 埋めし、NULL 仮想呼出は
`ott_unlifted(0)` → m11 と同じ icall-miss 規約 (ret 0) で継続。

### 3-4. (FLE-4) unit#209 の次の blocker

`unlifted 0x6a7b70` は `f_6a7f50` (unit 終了フック) が 0x15F4B80 に設定する **fill コールバック**。
root 化すると `f_6c7900` の fill ループが未初期化幅 (0xffffa = 1,048,570 回) で暴走して
ExitProcess となり **survey が成立しない**。boot_roots.json からは除外
(unlifted で止める方が survey は functional)。根本対策はループ幅
(`[rbp+0x48]-[rbp+0x40]`) が未初期化な理由の特定。

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

## 5. 未解決・限界 (実測ベース)

1. **unit#209 の次の blocker は `unlifted 0x6a7b70`** (fill コールバック、§3)。root 化しても
   `f_6c7900` の fill ループが未初期化幅 1,048,570 回で暴走 → ExitProcess となり
   **survey が成立しなくなる**ため、boot_roots.json には追加していない。
   根本対策は `f_6c7900` のループ幅 (`[rbp+0x48]-[rbp+0x40]`) が未初期化な理由の特定。
2. **unit 進行 209 で横ばい**。前ラウンド目標の 250+ には未達。unit#209 以降は
   上記 fill コールバックの lint が塞いでいる。
3. **VMT slot の自動 root 化 (RTTI/COL walk) は非適用**: 対象 0x6a7b70 は `.pdata` 整齊の
   実関数だが **image 内のあらゆるセクションに qword 参照を持たない** (実行時構築)。
   `.text` 内の連続 .text 参照 (VMT メソッド配列) の scan も実装したが拾えず、
   boot_roots.json への実行時累積が有効な手段と確認。
4. **chk variant のビルド**: `fle_chk` は `fle_cpu.c` の `A_()` マクロから呼ばれるため
   `fle_cpu.c` も `-DFLE_CHK` が必要 (boot_e2e.sh / build.sh で修正済み)。
5. `shimx_set_cs_null_ok(1)` の副作用: lock 依存 unit の survey 判定が実機とずれる可能性
   (CRITICAL_SECTION が no-op になるため)。実測 survey は FLE-3 末と同一値。

## 6. CAB-129/231 (RetDec route 修正) の x64c での要否

**m11 の unit#18 OOB の直接原因 (0x188B record の alloca 縮退) は x64c に構造的に存在しない。**
x64c は `rep stosq` を正しく展開し定数折畳みを持たないため 8B alloca への潰れが発生し得ない。
CAB-129 / CAB-231 の適用は x64c route では不要。D7/D10/D11 も x64c 非依存。

## 7. 引継ぎ (次ラウンド)

1. **unit#209 の次の blocker `unlifted 0x6a7b70`** — `f_6c7900` の fill ループ幅が
   未初期化 (1,048,570 回暴走) な理由を特定する。root 化は survey を壊すので非推奨。
2. **chk variant の `fle_chk` 活用** — `__LINE__` が lift 生成 C の行番号を指すので、
   次に OOB/trap が出たときは同じ手順で即座に命令を特定できる。
3. **verdict 混在** (`gen_mixed.py`) — unit 級 `x-route_diff 143` / `native_fault 89` を
   CAB-232/233 の本格採点に接続 (両 target は同一 PE VA 空間)。

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
