# tools/flelift/boot — FLE-2〜FLE-5: x64c lift による FLEngine boot 連鎖 (DllMain → _InitLib → InitUnits)

> 正本: `tools/flelift/boot/REPORT.md`。boot 連鎖 (FLE-2〜FLE-5) の測定値・成果物・引継ぎ。
> 行数上限 (250 行, `docs/DOC_MAP.md` §1) 超過のため、ラウンド別の経緯と停止原因の逆引きは
> `REPORT_APPENDIX.md` に**分割移動**した (内容は削除していない)。#2719 (x64c 寛容起動・942 unit 逐次試行・CreateFruityInstance 観測): 942 試行、CFI は入口 (0x1375990) まで dispatch され、本体内で oob trap (trap 地点は未特定・soft 呼出し 0 件) → `REPORT_APPENDIX_2719.md`。

## 0. 結論 (先出し)

- **判定 (累積, FLE-5 末): unit 進行は 209 止まり、survey は全 942 unit で functional**
  (FLE-1 17 → FLE-2 40 → FLE-3 209 → FLE-4 OOB 修正 → FLE-5 **survey 非 ok 7 → 3**)。
  **unit 進行は 209 で横ばい**。FLE-5 の「`f_653f40` の早期 return は VCL リソース読み出し失敗」は誤認 (訂正は `REPORT_APPENDIX_672.md` §A): 原因は `dsp_ippv2_x64.dll` の LoadLibraryW 失敗 (host shim の欠落)。
  **FLE-672 (#672)**: fill (`0x6a7b70`) の buf = 0 の呼出しを戻す診断 (`FLE_DIAG_NULLFILL=1`) で GetMem・undo slot の 0 化が消え、停止点は `unlifted 0x6bbc20` へ移る (units は 209 のまま・§11)。
- ラウンドごとの詳細 (FLE-2〜FLE-5 の成果・修正 3 件・FLE-4/5 の逆引き 5 段) は `REPORT_APPENDIX.md` §A・§B。**FLE-12 (#3090)**: unit 209 直後の `0x6a7b70` の呼出元は `0x6c7923` ← `0x815920` (`f_815050`)、幅 r8 = 矩形の幅 = 2^20 (即値 `0x4130000000000000` 由来の推定)、修復は未了 (`REPORT_APPENDIX_3090.md`)。
- **FLE-9 (§9, #2700) の結果**: lift → 8 shard clang (cap 内・計 89 s) → link (mismatch/undefined/dup 0) → boot まで到達。units_run は shim 有・ネガコンとも 209 のまま (停止点: `MessageBoxA` → `exit(0)`)。shim 有の IPP 判定は NG (終了時の 0x15F34A0 は 0。FLE-10 (§10, #2702): shim 有でも units は前進せず 209)。
- **PERF-P14 (#970)**: boot closure を -O0 / -O2 / -O2 -flto で build・実行 (node n=10)。3 変種の署名は計数と ipp 状態が一致 (出力メモリは未比較)・units 209 据え置き。ネガコン (`FLE_IPP=0`) で署名は変わる。LTO の結論は shim (-O1 固定) を含まない範囲に限る。実測値・範囲は `REPORT_APPENDIX_970.md`。


## 1. 成果物 (tools/flelift/boot/)

| パス | 役割 |
|---|---|
| `boot_e2e.sh` | 1 コマンド検証: gen → lift (boot entries + override) → data gen → shimx obj → 4 link variant (plain/strict/nosx/chk) → 実行 |
| `build.sh` | **単一 variant 再 build** (診断・反復用。lift 済み C を再利用し fle_boot.c 等の差分だけ link) |
| `gen_boot.py` | entries (+entry 0x1376820 / longjmp 断片 / boot_roots 累積 / VMT harvest)、`.text` 全域データ窓 (#embed 16.4MB)、imp bridge (shimx thunk / soft stub / curated)。**FLE-2: ポインタ typedef 解析を修正** |
| `fle_boot.c` | boot ドライバ: 敷設 + shimx wiring (cbtrans/resolver/LB_BASE=0x10000) + 計数 + `--override` C 実装 (longjmp/GetMem/FreeMem/InitUnits) + curated import。**FLE-2: FreeMem 判定と RSP 釣合を修正** |
| `fle_boot.mjs` | runner: boot 実行 + 分類 + survey (942 隔離, FLE_SURVEY_FROM/TO) + summary/JSONL 出力 |
| `blkdiag` (fle_boot.c 内) | System._GetMem/_FreeMem トラッキング (alloc/free 時系列・16B snapshot canary・二重解放/未追跡/header dump・FastMM dispatch カウント)。`fle_boot_set_blkdiag(int)` / `fle_blkdiag_stat(int)` で外部操作 |
| `boot_roots.json` | 実行時発見 roots **110 本** (累積)。0x403579/0x403582/0x40358b (jump table thunk)・0x40fb40/0x40f960・0x527b5b 等を追加。**0x6a7b70 は意図的に除外** (付録 §B 3-4) |
| `survey_drive.sh` + `merge_survey.py` | survey を 180s セグメント実行 (timeout 再開) → results/survey.json に統合 |
| `gen_verdict.py` | survey 差分 → liftdiff FORMAT v1 JSONL (results/verdict_boot.jsonl) |
| `gen_mixed.py` | **関数級 (liftdiff) + unit 級 (boot) verdict を 1 ファイルに混在**させて `liftdiff.py summary` で採点。32MB 超のため JSONL は work/boot/ (gitignore)、採点結果は results/mixed_summary.md |
| `iterate_roots.sh` / `dbg_u18.mjs` | root 収束ループ (`FLE_ROOT_BLOCKLIST` で root 化禁止 address を除外) / boot 停止点の guest stack 復元 (再ビルド不要) |
| `dbg_lift.py` | **FLE-5: 任意 guest VA を lift 生成 C の行に埋め込む診断ツール** (`--at 0x8157c1,f_6c7610`)。`/* <VA>: <asm> */` コメントの 1 行対応を利用し `grep -n` で即座に C 行を引き、`fprintf` を挿入して実測する (FLE-4 の `__LINE__` 逆引きを汎用化) |
| `results/` | boot_summary*.json / survey.json / survey.jsonl / verdict_boot.jsonl |

link 実績 (4 variant 全て): signature mismatch 0 / undefined 0 / duplicate 0。wasm 145.8MB (chk) / 126.1MB (その他) (work/, gitignore)。
**全 import が shimx/curated で応答 (soft stub 発火 0)** — `soft_uniq=0`。

## 2. boot 連鎖 実測 (plain variant, closure 2 + switch harvest)

| 項目 | FLE-2 | FLE-3 | FLE-4 | **FLE-5** |
|---|---|---|---|---|
| unit 進行 | 40 dispatch / 39 完走 | 209 dispatch / 208 完走 | 209 / 208 | **209 / 208 (横ばい)** |
| 停止原因 | unlifted 0x527b5b | oob @ `f_816e80` | unlifted `0x6a7b70` | **unlifted `0x6a7b70` (真因は 付録 §B 3-5)** |
| 関数数 | 29,420 | 29,902 | 29,902 | **29,907** |
| unlifted callees | 1,678 | 1,684 | 1,684 | **1,681** |
| roots (entries) | 20,899 | 21,307 | 21,307 | **21,309** |
| GetMem / FreeMem | 662 / 209 | 1,886 / 776 | 1,890 / 776 | 1,890 / 776 |
| import 数 | 680 | 680 | 680 | 680 |

unit 進行の推移 (FLE-3 中の実測): 40 (FLE-2 末) → **43** (0x403579/582/58b jump table root 化)
→ **93** (0x433051/075/07e/087 系) → **111** (0x527592/59b/5a4/589 系 + closure) →
**126** (0x5274c0 + `cs_null_ok`) → **197** (0x642e* 20-entry table) → **209** (0x707000 + harvest 32 化)。


## 3. unit 停止原因の特定

→ `REPORT_APPENDIX.md` §B に移動 (3-1 3 バグ修正 / 3-2 closure 比較 / 3-3 unit#209 OOB / 3-4 次 blocker / 3-5 真因の 5 段逆引き)。

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

outcome (`gen_verdict.py`): **equal 800 / native_fault 92 / diff 49 / both_fault 1** (FLE-5 末)
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
関数数 8364: 一致 4943 / 不一致 776 / 実行不能 2645   (FLE-5 末)
  unlifted_callee  主因 379   <- 関数級 (closure 残り)
  x-route_diff     主因 142   <- unit 級 (native baseline が fault / x64c が ok = x64c 優位)
  callee_divergence 主因 119
  callsite_arg_drop 主因 66
  ...
```

**`x-route_diff` が native_fault 92 の内訳** (FLE-4 末は 89) で、unit 級の差分として
liftdiff の summary に混在する。`native_fault` = 92 は **x64c が ok / native 側が fault**
なので x64c 優位の証拠で、CAB-232/233 の本格採点にそのまま接続できる。

### 4-4. survey 非 ok の内訳と FLE-5 での解消

`boot/results/survey.json` の `details` = 非 ok unit の全明細。FLE-5 の変更前後:

| unit | FLE-4 末 (7 件) | target VA | FLE-5 末 | 備考 |
|---|---|---|---|---|
| 280 | oob | — | **unlifted `0x6a7b70`** | boot_roots 3 件追加で oob 解消 |
| 296 | unlifted | 0x477e73 | **ok** | root 化 (.pdata 開始点) |
| 659 | oob | — | **unlifted `0x6a7b70`** | 同上 |
| 666 | unlifted | 0xd122e0 | **ok** | root 化 |
| 830 | unlifted | 0x8dfff0 | **ok** | root 化 (3 unit が同一 target) |
| 895 | unlifted | 0x8dfff0 | **ok** | 同上 |
| 898 | unlifted | 0x8dfff0 | **ok** | 同上 |

FLE-5 末の残 3 件は `unlifted 280 / 659` (`0x6a7b70`, blocklist 対象) と `unlifted 895`
(`0x976da0`, 新たに露出)。
**手段: 実行時 unlifted target を boot_roots.json に追加 → 再 lift**。ただし
`FLE_ROOT_BLOCKLIST` に載る address は root 化すると survey が破裂するため除外する。

## 5. 未解決・限界 (実測ベース)

1. **unit#209 の次の blocker は `unlifted 0x6a7b70`** (fill、`f_6c7610` ← `f_815050`)。root 化すると fill が image を 0 埋めし survey が成立しないため `FLE_ROOT_BLOCKLIST` で除外。診断 (§11) では fill 後の停止点は `unlifted 0x6bbc20` (f_6c9280)。
2. **unit 進行 209 で横ばい**。次の一手は `0x6bbc20` の解消 (子 issue #3491 `[FLE-14]`)。fill の上流 (面 2^20) は #3112。
3. **残 survey 非 ok 3** = unit 280 / 659 (`0x6a7b70`, blocklist 対象) + unit 895
   (`0x976da0`、未調査)。`0x976da0` は次の調査対象。
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

1. **最優先: unit 209 の `unlifted 0x6bbc20` (f_6c9280 ← 0x6c9380)** (子 issue #3491 `[FLE-14]`)。0x15F34A0 の登録は shim で済んでいる (§11)。
2. **`boot/dbg_lift.py --at 0x...` を常用** — guest VA を直接指定して lift C に
   トレースを埋め込める。FLE-4 の `__LINE__` 逆引きより汎用的。
3. **`FLE_ROOT_BLOCKLIST` を尊重** — `0x6a7b70` は root 化すると survey が破裂する。
   自動累積で再投入されても除外される。
4. **verdict 混在** (`gen_mixed.py`) — unit 級 `x-route_diff 142` / `native_fault 92` を
   CAB-232/233 の本格採点に接続 (両 target は同一 PE VA 空間)。
5. **残 survey 非 ok 3** — unit 280 / 659 (`0x6a7b70`, blocklist) + unit 895 (`0x976da0` 未調査)。

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
# FLE-5 診断: 任意 guest VA を lift C に埋め込んで実測 (dbg variant link で実行)
python3 tools/flelift/boot/dbg_lift.py --src work/boot/lift/fle_lifted.c     --out work/boot/dbgout/fle_lifted_dbg.c --at 0x6c7610,f_653f40
bash tools/flelift/fle_e2e.sh                # 親チケットの回帰 (PASS)
```
前提: tools/flelift/fle_lift.sh と同一 (python3 capstone/pefile, emsdk 6.0.12, node)。
PE = block00031_PE.bin。生成物は work/boot/ (gitignore)。20MB 超 blob は git に入れない。

## 9. FLE-9 (#2700): lifted C を 8 本に分けて clang・link・boot を実測 (2026-10-14)

- **結論**: 単一 TU の clang は cap 11000MB 超で打ち切られていた (FLE-8・付録 E-1)。8 shard (`FLE_SHARDS=8`・`xargs -P3`・各 cap 5000MB) では全て cap 内で完走 (各ピーク 2,202〜2,666MB・clang 段 89 s)。link は mismatch/undefined/duplicate 0・wasm 127,078,695 B。**boot は両 variant とも unit 209 で停止**。shim 有の IPP 判定は NG (`ptr_15F34A0=0x0`)。最初のウィンドウは未到達。
- 測定 commit: `a741a0ca` (コードを変えた最後の commit。検証起点 `origin/main` `26f90ada`)。差分 0 の証跡: `git diff --stat a741a0ca HEAD -- tools/flelift/x64c.py tools/flelift/boot/build.sh tools/flelift/boot/fle6_measure.sh tools/flelift/boot/rss_cap.py` が空 (本節の commit は REPORT・付録のみ)。
- 出力同一性: `--shards 1` は旧 `x64c.py` (origin/main) と小入力 (roots 先頭 400・closure 2・386 関数) で `fle_lifted.c` / `lift_meta.json` が sha256 一致。N=8 は関数本体の集合が N=1 と一致し、`ott_dispatch`・`imp_tab` は shard 0 のみ。既知類型: 該当なし (`docs/DEFECTS.md` D1a〜D23)。
- 再現: `FL_WIN64_DIR=<fl-win64 展開先> bash tools/flelift/boot/fle6_measure.sh` (既定 `FLE_SHARDS=8`)。素材 `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff`。

### 9-1. 工程の実測 (HEAD `a741a0ca`・`fle6_measure.sh` 1 回。同内容の前回実行は lift 67 s / clang 105 s で、boot の数値は同一)

| 工程 | 結果 | 秒 | ピーク RSS |
|---|---|---|---|
| gen-A | rc 0 | 8 | - |
| lift (closure 2・root 0x6a7b70・cap 13800MB) | rc 0・29,908 関数・1,557,903 insn | 88 | 610MB |
| clang shard ×8 (-O0・-P3・cap 5000MB) | 8/8 OK・cap 超過 0 件 | 89 (工程計) | s0 2,666 / s1 2,243 / s2 2,406 / s3 2,345 / s4 2,202 / s5 2,363 / s6 2,387 / s7 2,487 MB |
| shard 別の秒 (s0〜s7) | 46 / 31 / 32 / 20 / 23 / 27 / 26 / 22 | - | - |
| link | mismatch 0・undefined 0・duplicate 0・wasm 127,078,695 B | - | - |
| boot shim (`FLE_IPP=1`) | units 209・stopped 209・IPP check NG | 24 | - |
| boot ネガコン (`FLE_IPP=0`) | units 209・stopped 209・IPP check OK | 25 | - |

### 9-2. 起動指標 (前後)

- **units_run**: 前 209 (FLE-5/6・§2) → 後 **209 のまま** (停止点=209)。shim 有・ネガコンとも同じ。
- shim 有の確保 `GetMem` 2,314 / `FreeMem` 1,199 (ネガコン 1,891 / 776)。`ipp.called` 全件は `ippsZero_8u` ×2 のみ。`ptr_15F34A0` は shim 有でも `0x0`。
- 停止: 両方とも unit 209 の後に `MessageBoxA` (text 空・自動 IDOK) → `exit(0)` (call site `0x412a12`)。最初のウィンドウは未達 (生成は未確認)。既定経路 (root 無し) は未測定。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| shim 有で `0x15F34A0` が 0 のまま (`ippsZero_8u` は 2 回呼ばれる)。登録経路が未解明 | FLE-6 の IPP 判定 NG・units 209 据え置き | 既存 #2702 [FLE-10] (`blockedBy: #2700`)。本 PR で事実を追記 |
| unit 209 の後の `MessageBoxA` → `exit(0)` の原因 | 次の blocker (最初のウィンドウ未達) | 既存 #2702 (同上) |
| 既定経路 (root 0x6a7b70 無し) の boot 未測定 | 209 据え置きの確認が未了 | 既存 #2702 作業 1 |

## 10. FLE-10 (#2702): dsp_ippv2 shim では units が前進しない (測定 commit `4869ad16`)

- **既知類型との関係: 該当なし** (DEFECTS.md D1a〜D23 を照合。IPP stub の fail-soft は類型に無い)。ただし既定経路では下記の no-op (`ippsZero_8u` 未適用) があり、#2702 が懸念した silent miscompile の一種。DEFECTS.md の類型 ID は付与していない (類型への追記の要否は #3060 の検証後に判断)。FLE-6 (#672) の旧 §10 全文は `REPORT_APPENDIX_2702.md` §E。
- **結論**: shim 有 (`FLE_IPP=1`) も `FLE_IPP=2` も units_run は **209** (ネガコンと同じ)。boot 209 までに呼ばれた IPP は `ippsZero_8u` の 2 回だけで、他は 0 件。fail-soft 依存の前進は**観測されない** (前進 0 unit)。
- **既定経路** (root 無し・`FLE_IPP` 未指定): units 209 / GetMem 1,890 / FreeMem 776 / 関数 29,907 で REPORT §2 FLE-5 列と**一致** (差 0)。停止は `unlifted 0x6a7b70`。
- **既定経路の no-op (`ippsZero_8u` 未適用)**: 既定経路では呼出点 0x67264b の `call` が `dispatch(0)` (icall-miss) となり、`ret 0` で戻る (ログ `[fleboot][ff] dispatch(0) -> ret 0 (m11 icall-miss 揃え, call site ret=0x67264d)`)。`ippsZero_8u` は実行されず、ゼロ埋めは未適用 (出力の内容は未確認)。`ipp.called` が空なのは IPP 関数に到達していないため。shim 有では同じ呼出点の target が `ippsZero_8u` (非 0) になる。units 209 と GetMem/FreeMem が FLE-5 列と一致するのは、この no-op の後も boot が進むためで、出力の一致を示すものではない。
- **停止点** (root 有の全 variant): unit 209 の後の `MessageBoxA` (text 空) → `ExitProcess(0)` (ret `0x412a12`)。最初のウィンドウは未達。次の blocker は #3060 [FLE-11]。

| route (lift closure 2) | units | GetMem / FreeMem | ipp.called (名 × 回数) | 停止 |
|---|--:|--:|---|---|
| shim `FLE_IPP=1` (root 有) | 209 | 2,314 / 1,199 | ippsZero_8u × 2 (初回 ret 0x67264d) | exit(0) @0x412a12 |
| ネガコン `FLE_IPP=0` (root 有) | 209 | 1,891 / 776 | なし | exit(0) @0x412a12 |
| mode 2 `FLE_IPP=2` (root 有) | 209 | 2,314 / 1,199 | ippsZero_8u × 2 | 非 ippsZero の IPP 0 件 → exit(0) |
| 既定 (root 無し・未指定) | 209 | 1,890 / 776 | なし (0x67264b が dispatch(0) = icall-miss で ret 0・`ippsZero_8u` 未適用) | unlifted 0x6a7b70 |

- **機構** (実測): `fle_lifted_s5.c` の `/* 672644 */ mov rax,[0x15e0a48]` の次が `/* 67264b */ call qword ptr [rax]` (`FF 10`・2 byte)。PE の逆アセンブルでも同じ。push される戻り番地は 0x67264d (summary の `ipp.called` の ret はこの値)。呼出時の target は shim 有で `ippsZero_8u` (非 0)、既定経路で 0 (`dispatch(0)`)。終了時の `[0x15e0a48]` は shim 有で 0、既定経路で 0x15F34A0 で、呼出時の値とは一致しない。shim 有で登録が呼出時には効いていたが終了前に 0 へ戻る経路は**推定** (書換え元は未特定)。よって `FLEBOOT_IPP_CHECK` (終了時の 0x15F34A0 を見る) の NG は呼出しの不発を示さない。
- shim 有と negctl の差: `getproc` 511 / 88、GetMem・FreeMem もともに +423。units は同じだが実行経路は同一ではない (+423 の内訳は未確認)。mode 2 (`FLE_IPP=2`) の停止経路 (`g_ipp_stop`) は未発火 (`ipp_stop`=null・発火の確認は未実施)。「非 ippsZero の呼出し 0 件」は `ipp.total` の計数 (停止判定より前) から有効。

測定は route ごと n=1 (変動の min–max は未測定)。測定 commit `4869ad16` (`fle_boot.mjs` の L101 コメントの訂正のみ。コードを変えた最後の commit)。経緯: `56e515e1` → main 取り込み merge `a0f659bf` (`fle_boot.mjs` に PY-123 の `undo_probe` 出力が入り、結果 JSON に `undo_probe` 項目が増えた。units・GetMem/FreeMem・停止点は不変) → `6b62f031` (REPORT と結果 JSON の再採取) → `4869ad16` (呼出点の訂正)。`4869ad16` で再測定した結果 JSON は `6b62f031` の版とバイト一致。コード差分 `git diff 4869ad16 HEAD -- tools/flelift/x64c.py tools/flelift/boot/fle_boot.c tools/flelift/boot/fle_boot.mjs tools/flelift/boot/build.sh tools/flelift/boot/fle6_measure.sh` は空 (差分 0)。工程秒・RSS・再現コマンドは `REPORT_APPENDIX_2702.md` §A・§B。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 209 後の `MessageBoxA` (text 空) の text 源と呼出元 | 最初のウィンドウ未達 (次の blocker) | #3060 [FLE-11] |
| 呼出時の `[0x15e0a48]`・`0x15F34A0` と、終了前に 0 へ戻す書込み元 | ippsZero 登録経路の確定。IPP_CHECK の観測点 | #3060 (受入条件に追加) |
| 既定経路で `ippsZero_8u` の呼出点 0x67264b の target が 0 (icall-miss) になる経路。出力のゼロ埋めが未適用 | 既定経路 (`FLE_IPP` 未指定) の出力内容 (silent miscompile の疑い) | #3060 (受入条件に追加) |
| 既定経路の survey 再実測・0x6a7b70 root 化の可否 | 0x6a7b70 を恒久 root にするかの判断 | #918 (親・PM 判断) |

## 11. FLE-672 (#672): buf = 0 の fill を戻す診断 (`FLE_DIAG_NULLFILL=1`・既定無効)

- 既定経路は不変 (units 209・GetMem / FreeMem は §9-2・§10 と一致)。診断ありは units 209 のまま、停止点が `unlifted 0x6bbc20` (f_6c9280 ← 0x6c9380) へ移る。判定 (①②③)・表・再現は `REPORT_APPENDIX_672.md`。
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 停止点 `unlifted 0x6bbc20` の解消 | 最初のウィンドウ未達 | #3491 [FLE-14] (親 #672) |
