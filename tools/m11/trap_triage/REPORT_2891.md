# #2891: unit 492 OOB の `4473f0` 配列 dest2 の旧値 (`0x1_00000003`) の書込み主体 (現 build での特定)

親: #2780 (経緯は `REPORT_2780.md`)。測定 commit: `ed70adf5a` (build 入力の最後の変更。本 PR は計測スクリプトと本 REPORT を足すだけで、build 入力 (IR・C・build スクリプト) は変えていない。§8)。再測定: `6d978d485` (fix round 1。build 入力は `ed70adf5a` と同一)。受入 2・3 の測定 (§9): `58ed035cf` (origin/main)。
既知類型との関係: 該当なし (D17 (DEFECTS.md) と機構が一致しない。類型の登録は PM 判断。§5)

## 0. 結論

- **REPORT_2780 の番地 `0x10aa1160` は、現 build (`ed70adf5a`) では同じ役割の番地ではなかった。** 現 build の unit 492 では、`4473f0` の i=2 の `dest2` は `0x10aa1430` (arg2 = `0x10aa12f0`)。REPORT_2780 の `arg2 = 0x10aa1020` との差 `0x2d0` だけ番地がずれている (build の配置差。§3)。`0x10aa1160` は現 build では別用途 (shadow stack 局所) の番地で、同番地への書込みは unit 15〜898 に散在する (§4.3)。
- **受入 1 (書込み主体) は、現 build の `0x10aa1430` で達成した。** 全 942 unit の計装で `0x10aa1430` に hit したのは 130 unit (hit 2,548,513 件)。このうち frame と値を記録した unit 432・477・484・492 の 7 hit が、この 4 unit の中の値の遷移を全て説明する。主体は次のとおり (§4.2)。
  - unit 432: `InitializeCriticalSectionAndSpinCount` → `InitializeCriticalSection` (`function_423940` 経由) の CRITICAL_SECTION 初期化 (4B 書込み 3 件、wat 14978)。上位 dword `1` はこの 4B 書込み (`0x10aa1434` の値 1) 由来。
  - unit 477・484: `function_4133f0` (C 版 `System._UStrAsg`、wat 14850) の shadow stack 局所 (+48 の 4B `len`)。REPORT_2672 の `u32 len` と同じ機構。
  - unit 492: `function_4133f0` の `*dest = s` (8B、`s = 0`)。旧値を読んだ後の書込み (OOB 入力そのものは書込み主体ではなく、unit 432 以降の残骸)。
  - 未確認: unit 304 (hit 2,546,099 件) の値の内容は記録していない (§6 未解決 5)。
- **受入 2 (`4473f0` 配列の native 0 初期化の箇所) は達成 (§9)。** native の 0 初期化は `ad5700` の `call 415610` (RTTI による managed field の初期化) → `4159e0` → `40d210` (memset、112 B)。lift 版 `40d210` は n > 32 の本体 (`0x40d2d1..0x40d31a`) を関数範囲の外として落とし、そこへの分岐が no-op になる (§9.2・§9.3)。
- **受入 3 (類型判定) は達成 (§9.5)。** D17 ではない (8 B の 0 書込みは IR に残っていて、欠けているのは 112 B の memset 本体)。近いのは D13 (関数範囲の過小推定) の新事例。DEFECTS 登録は PM 判断 (未登録)。
- 修復 (`40d210` の転記) は実装作業なので子 issue に分ける (§9.6)。shim による検証は commit していない (§9.4)。

## 1. 素材と再現

- 素材 (`$ARTIFACTS_DIR`): `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`extracted/block00031_PE.bin` 確認)。`work-m11` をリポジトリ直下に展開 (`tools/m11/work/`、gitignore)。`toolchain-emsdk` は展開せず、`[EMSDK]` (`docs/REFERENCES.md` §4) の `upstream/bin/wasm-opt` (version 133) を使った。`toolchain-retdec` は本 round では使わない。
- `work-m11` の `m11_image.bin` は snapshot (2026-10-10 生成) のまま使う。`m11_gen_ir2.sh`・`m11_build.sh` は `m11_image.bin` を作らない (survey・watch が読む image は snapshot 由来)。
- 既定 build (fix round 1): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/m11_gen_ir2.sh` rc 0 (41.3 s、490,761 行) → `bash tools/m11/m11_build.sh` rc 0 (22.2 s)。
- 計装 build: `M11_PROBE_2780=1 bash tools/m11/m11_build.sh` rc 0 (probe 用。計測後に既定 build へ戻して §2 の survey を取り直した)。

## 2. 基準 survey (既定 build、`ed70adf5a`)

- `survey_units.mjs` 3 回: 3 回とも `ok 873 / miss 47 / halt0 7 / oob 14 / noproc 1` (計 942)。per-unit JSON は `cmp` で 3 回一致。
- fix round 1 の再測定 (HEAD `6d978d485`、n=1): `ok 873 / miss 47 / halt0 7 / oob 14 / noproc 1`。所要 9.5 s (並列 1、nproc 4、1 分 load average 0.91)。
- REPORT_2780 §2 の基準 (`ok 872 / miss 47 / other 1 / halt0 7 / oob 14 / noproc 1`) との差: `other 1` が現 build では `ok` になっている (unit は未特定。REPORT_2780 に per-unit JSON が無い)。oob 14 は一致。
- 計装版 (`wasm-opt --instrument-memory`、§4) の全 942 unit の kind は既定 build と差分 0 件 (`summary` の `kind diff vs survey: 0`)。

## 3. 番地の対応 (REPORT_2780 → 現 build)

| 項目 | REPORT_2780 (`9b8f133f` 系の build) | 現 build (`ed70adf5a`) | 根拠 |
|---|---|---|---|
| unit 492 の `arg2` (`4473f0` の第 2 引数) | `0x10aa1020` | `0x10aa12f0` | `probe_2780_units.mjs` の unit 492 の tag 5 |
| i=2 の `dest2` (= `arg2+0x100+8*(i-1)+0x38`) | `0x10aa1160` | `0x10aa1430` | tag 9 (現 build)。`0x10aa1160 + 0x2d0 = 0x10aa1430` |
| `dest2` の旧値 | `0x1_00000003` | `0x1_00000003` | tag 10 (現 build) |

- 現 build の unit 492 は `4473f0` を 1 回だけ呼び、i=1・2 の 2 反復 (記録 20 件) の後に OOB で止まる (`probe2780` の unit 492 `kind: oob`)。i=2 の旧値読みで `0x1_00000003` を得る。
- 使った probe: 既存の `probe_2780_units.mjs` (`M11_PROBE_2780=1` build)。計装は IR の読取りのみ。kind は survey と全 942 unit 一致。

## 4. 書込み主体 (計装 wasm の store 記録)

### 4.1 方式

- `wasm-opt --instrument-memory` (version 133) で既定 build の `m11_boot.cjs.wasm` の全 store に hook を入れた `instr.wasm` を作る (`tools/m11/work/trap_2891/`、commit しない)。hook は JS import で線形メモリに書かない。
- `store_sites_2891.py` が `store_ptr` の import 番号 (`$fimport$34`) を wat から引き、計装 id → (wat 関数 index・行・bytes・offset) の表を作る (59,360 id・重複 0)。REPORT_2672 の `store_sites_2672.py` は import 番号を固定していたため、この build では使えない。
- **番号の約束**: 本 REPORT の関数番号はすべて **wat の defined index** (`store_sites` の func、`wasm-dis` の `$N`)。frame の `wasm-function[N]` は V8 の絶対 index で、wat = V8 − 39 (import 39 本)。帰属の hit 7 件で一致を確認 (§4.2 の対照)。
- `watch_store_2891.mjs` は監視番地と重なる全 store の hit 件数を全 unit で数える。frame と値は `WATCH_LOG_UNITS` で指定した unit だけ記録する (frame 取得は hit ごとに `new Error().stack` を作るため重い。全 hit の frame を記録した計測は行っていない)。
- 実測 (全 942 unit、`WATCH_W=0x10aa1430 WATCH_LOG_UNITS=432,477,484,492`、fix round 1 · HEAD `6d978d485`): スクリプト内 `sec=333.3` (`Date.now` 差)、`time` の real 5 分 33.6 秒。並列 1 (単一 node プロセス、nproc 4)。1 分 load average は開始時 0.77、終了時 1.30。旧 §7 の「約 3 s」は再現せず、削除した。

### 4.2 `0x10aa1430` の書込み (全 942 unit、計装版)

hit の範囲: 全 942 unit = **2,548,513 件**。unit 0〜492 = 2,548,226 件、unit 493〜941 = 287 件。hit のあった unit は 130。unit 304 が 2,546,099 件、369 が 625 件、298 が 260 件。frame と値を記録したのは unit 432・477・484・492 の 7 hit だけ (`WATCH_LOG_UNITS`)。

| unit | store id | bytes | 書込み (addr) | 8B 値 (old → new) | 書込み主体 (wat 関数 ← 呼出し元) |
|---|---|---|---|---|---|
| 432 | 133408 | 8 | `0x10aa1430` | `0xf960` → `0xf960` (同値) | `m11_icall` (wat 14822) ← `function_410320` ← `function_9f2d80` |
| 432 | 136247 | 4 | `0x10aa1434` | `0xf960` → `0x1_0000f960` | 無名 wat 14978 ← `InitializeCriticalSectionAndSpinCount` (14977) ← `InitializeCriticalSection` (14979) ← `function_423940` (275) |
| 432 | 136250 | 4 | `0x10aa1430` | `0x1_0000f960` → `0x1_00000000` | 同上 (14978) |
| 432 | 136264 | 4 | `0x10aa1430` | `0x1_00000000` → `0x1_102a00f8` | 同上 (14978) |
| 477 | 133986 | 4 | `0x10aa1430` | `0x1_102a00f8` → `0x1_00000002` | `function_4133f0` (wat 14850、`m11_ov.c` の C 版 UStrAsg、store +48) ← `function_abeef0` ← `function_abfd60` |
| 484 | 133986 | 4 | `0x10aa1430` | `0x1_00000002` → `0x1_00000003` | `function_4133f0` (+48) ← `function_acf650` ← `function_ad0680` |
| 492 | 134001 | 8 | `0x10aa1430` | `0x1_00000003` → `0x0` | `function_4133f0` (+0、`*dest = s`、`s = 0`) ← `function_4473f0` (2688) ← `function_446400` (2686) ← `function_446ad0` (2693) |

- 値の遷移 `0xf960 → 0x1_0000f960 → 0x1_00000000 → 0x1_102a00f8 → 0x1_00000002 → 0x1_00000003 → 0x0` は、記録した 7 hit の旧値が直前の hit の新値と一致して連なる (検算: `watch_summary_2891.py`)。
- 上位 dword `1` は unit 432 の 4B 書込み (`0x10aa1434` の値 1) 由来。下位 dword `2`・`3` は unit 477・484 の `function_4133f0` の局所 `len` (+48) の 4B 書込み由来。`0x1_00000003` は、この 2 つの書込みと unit 432 の CRITICAL_SECTION 初期化の残骸が重なった値。これは REPORT_2780 §5 の `0x1_1029fe28 → 0x1_2 → 0x1_3` と同じ形 (番地と値は build で変わる)。
- unit 432 の 8B 書込み (`0x10aa1430`、値 `0xf960` 同値) は変化を生まない。REPORT_2780 の「8B 書込み (上位 dword = 1)」は、この unit 432 の下位 4B 書込み (`0x10aa1434`、値 1) に当たる。

**対照 (数値)**:
- 計装が挙動を変えない: 全 942 unit の kind は既定 build の survey と 0 件差 (計装版 `ok 873 / miss 47 / halt0 7 / oob 14 / noproc 1` = 既定)。
- 帰属の対照: 記録した 7 hit の frame 先頭関数を wat = V8 − 39 で引くと、store_sites の関数と **7/7** で一致する。ずらし (V8 − 38) では **0/7**。

### 4.3 `0x10aa1160` (REPORT_2780 の番地) の現 build での扱い

- 旧番地 `0x10aa1160` への書込みは unit 15・17・101・184・189・190・246・280・291・492・616・745・830・895・898 にあり (読取りのみの probe でも同じ)、REPORT_2780 §5 の unit 415〜492 の遷移は現 build では再現しない。
- unit 291 の書込みは `VirtualAlloc` (wat 14886、`function_407770` ← `function_407a50`) の 4B 2 件 (`0x10aa1164` ← `0x7d50000`、`0x10aa1160` ← `0x101000`)。値の出所は未確認。
- 旧番地の unit 492 の書込みは `function_4133f0` の shadow stack 局所 (`0x10aa1160 = frame + 32`) で、dest2 とは別物。

## 5. 類型判定 (§9 で確定)

- 既知類型: D17 ではない。D17 (`DEFECTS.md`: 64bit 局所の 0 初期化が 4B store に縮み、上位 4B が残る) は 8B の初期化が縮退する類型。本件は 8B の 0 書込みが IR に残っていて (`415610`)、欠けているのは 112 B の memset 本体 (書込みが 1 つも出ない)。残存の経路は縮みでなく no-op (§9.5)。
- 観測: `0x10aa1430` は寿命の異なる 3 つのもの (CRITICAL_SECTION の初期化・UStrAsg の局所 `len`・`4473f0` の配列要素 `dest2`) が共有している。これは wasm の shadow stack 上で unit 間に同じ番地が再利用されるためで、native の配置ずれではない (§9.4 の shim で旧値が消えることと整合)。
- 類型 (検証済み・§9): 「`4473f0` の配列 (`arg2+0x100..+0x170`) の 0 初期化 (`40d210` memset の 112 B) が lift で no-op になり、同番地に残っていた値 (前の unit の書込み) を旧値として読む」。DEFECTS への登録は PM 判断 (`WORKFLOW.md` §5)。

## 6. 未達・未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1. (解決: §9.2・§9.3) `4473f0` 配列の 0 初期化は `ad5700` → `415610` → `4159e0` → `40d210`。lift 版 `40d210` の n > 32 本体が欠落 | 受入 2 達成 | — |
| 2. CRITICAL_SECTION (`0x10aa1420`) と `4473f0` 配列 (`dest2` i=2 = `0x10aa1430`) の重なり | wasm の shadow stack 上の unit 間の共有 (§5)。native の配置ずれではない | — (§9.4 で確認) |
| 3. 類型判定 (D17 ではない・D13 系の新事例) と DEFECTS 登録案 | DEFECTS の登録 (PM 判断) | #2891 (PM 判断。未登録) |
| 6. `40d210` の n > 32 本体の転記 (`m11_ov.c`) と全 survey の再測定 | unit 492 の残存値の除去 | #3921 (`[M11-N200]`) |
| 7. unit 492 の次の trap (`412e40` ← `448490` ← `448350` ← `446400`。shim 試行後) | unit 492 が ok にならない | #3918 (`[M11-N199]`) |
| 4. 基準の差 (`other 1` → `ok`) の unit 特定 | 基準 survey の鮮度 | 本 REPORT §2 (再測定の子は起票しない) |
| 5. unit 304 の 2,546,099 hit (`0x10aa1430` の反復 hit) の内容。frame・値を記録していない (`WATCH_LOG_UNITS` の外) | 「値の遷移を作るのは記録した 4 unit の 7 hit」を全 unit に広げられない。本件の書込み主体の結論は記録した 4 unit の範囲に限る | 本 PR の未解決表 (再測定・計測の追跡の子は起票しない) |

- 1 run に収まる範囲で、受入 1 (書込み主体) を完了させた。受入 2・3 は調査の残りで、実装・修復の作業ではないため子 issue は起票しない (`WORKFLOW.md` §3)。

## 7. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64          # fl-win64 を展開した先 (§1)
bash tools/m11/m11_gen_ir2.sh && bash tools/m11/m11_build.sh          # 既定 build (§1)。m11_image.bin は作らない (snapshot を使う)
mkdir -p tools/m11/work/trap_triage tools/m11/work/trap_2891
node tools/m11/trap_triage/survey_units.mjs tools/m11/work/trap_triage/base1.json   # §2
export PATH="<EMSDK>/upstream/bin:$PATH"   # [EMSDK] (docs/REFERENCES.md §4) の upstream/bin。<EMSDK> は環境に合わせて置換する
wasm-opt --instrument-memory tools/m11/work/m11_boot.cjs.wasm -o tools/m11/work/trap_2891/instr.wasm
wasm-dis tools/m11/work/trap_2891/instr.wasm -o tools/m11/work/trap_2891/instr.wat
python3 tools/m11/trap_triage/store_sites_2891.py tools/m11/work/trap_2891/instr.wat tools/m11/work/trap_2891/sites.json
WATCH_W=0x10aa1430 WATCH_LOG_UNITS=432,477,484,492 \
  node tools/m11/trap_triage/watch_store_2891.mjs tools/m11/work/trap_2891/watch_w1430_full.json   # §4.2 (全 942 unit、sec=333.3)
python3 tools/m11/trap_triage/watch_summary_2891.py tools/m11/work/trap_2891/watch_w1430_full.json tools/m11/work/trap_triage/base1.json tools/m11/work/trap_2891/sites.json
```

- 注: `watch_store_2891.mjs` は `work/m11_boot.cjs` (既定 build の glue) を読む。`M11_PROBE_2780=1` の build の後は既定 build を作り直すこと。
- 注: `watch_summary_2891.py` は watch の出力・survey の JSON・sites.json を読んで、§4.2 の数値 (hit 範囲・kind 差・帰属の対照) を出す。

## 8. 測定 commit からの差分 (差分 0 の証跡)

- 測定 commit: `ed70adf5a` (origin/main)。計測に使った build 入力 (IR・C・build スクリプト・`survey_units.mjs`・`probe_2780_units.mjs`) は、この commit と同一。
- fix round 1 の再測定は `6d978d485` で行った。その後 (本 commit まで) の差分は、本 REPORT・`watch_summary_2891.py` (集計のみ、計測に使っていない) の追加。
- 検証: `git diff ed70adf5a HEAD -- tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/m11_rt.c tools/m11/m11_ov.c tools/m11/trap_triage/survey_units.mjs tools/m11/trap_triage/probe2780_ir.py tools/m11/trap_triage/probe_2780_units.mjs` の出力は **0 bytes** (`| wc -c` = 0)。本 PR で新規追加した計測スクリプト (`watch_store_2891.mjs`・`store_sites_2891.py`・`watch_summary_2891.py`) は測定 commit に無いため、この一覧に入れない (`git diff ed70adf5a HEAD -- <3 本>` は新規ファイル分の 7,011 bytes)。計測に使った 2 本は `git diff 6d978d485 HEAD -- tools/m11/trap_triage/watch_store_2891.mjs tools/m11/trap_triage/store_sites_2891.py` の出力が **0 bytes** (測定後に変わっていない)。

## 9. 受入 2・3: 0 初期化経路と lift の欠落 (本 run)

測定 commit: `58ed035cf` (origin/main、本 run の開始時点)。`ed70adf5a` から `58ed035cf` の間に `m11_build.sh`・`m11_ov.c`・`m11_rt.c` が変わっている (`git diff --stat ed70adf5a 58ed035cf` = 3 files、+61/-3)。§2 の基準 survey は `58ed035cf` でも一致した (§9.4)。

### 9.1 結論

- 受入 2: native の 0 初期化は `ad5700` → `415610` (RTTI で managed field を初期化) → `4159e0` (C shim) → `40d210` (memset、112 B)。lift 版 `40d210` は n > 32 の本体を落としている (§9.3)。
- 受入 3: D17 ではない (§9.5)。D13 (関数範囲の過小推定) の新事例。
- 修復 (`40d210` の転記) は実装作業なので子 issue に分けた (§9.6)。shim は検証にだけ使い、commit していない。

### 9.2 native の経路 (`tools/m11/trap_triage/native_zeroinit_2891.py`、読取りのみ)

- `ad5700` (unit 492 の入口): `ad570b: lea rcx,[rbp+0x28]` (obj はスタック上の局所レコード)、`ad5716: call 0x415610` (RTTI 駆動の初期化)。
- `415610`: RTTI の field 表を回る。string 系 (kind 10/11/15/17/18) は `mov qword ptr [rax], 0` (8 B)。static array (kind 13) は `4157d0` から `4159e0` を呼ぶ (IR の `call function_4159e0`)。
- `4159e0` (`m11_ov.c` の C shim): string 型で count == 1 なら `Q(p) = 0`、それ以外は `function_40d210(p, count << 3, 0, 0)`。count = 14 なら 112 B。
- `40d210` (memset、`rcx` = p、`rdx` = n、`r8b` = val): `cmp rdx,[rip+0xf97e2d]` (閾値は VA `0x13a5048` の qword = INT64_MAX。`jge 0x40d30b` は実行されない)。`test rdx,rdx; jle` で n <= 0 は何もしない。`cmp rdx,0x20; jg 0x40d2d1` (n > 32)。`40d2d1`: `movd xmm0,eax; pshufd; movups [rcx],xmm0; movups [rcx+rdx-0x10],xmm0; movaps` の 16 B ループ。
- `446400` は obj+0x170 (`418190`) と obj+0x180 (`412d60`) だけを先に解放し、+0x100..+0x170 には触れない (`446400` の `0x4464e2`・`0x4464f9`)。

### 9.3 lift 側の欠落

- `.pdata`: `40d210..40d31b` が 1 つの RUNTIME_FUNCTION (`native_zeroinit_2891.py` の出力)。RetDec は `function_40d210` を `0x40d210..0x40d2ba` で切る (`boot0.drc.dsm`)。最初の `ret` (`0x40d2b9`) で閉じ、`40d2d1`・`40d30b` は `data inside code section` 扱い。
- `boot_final.ll` の `function_40d210`: `%5 = icmp sgt i64 %arg2, 32` の分岐先は `dec_label_pc_40d2b9` (return)。`dec_label_pc_40d2d1` は IR 全体で 0 件。よって n > 32 の memset は no-op になり、`40d210` を経由する n > 32 の全呼出しで 0 初期化が起きない。

### 9.4 検証 (shim 試行。commit していない)

- 試行: `m11_ov.c` に `function_40d210` の転記を 1 関数足し、`m11_build.sh` のみ再実行 (IR は不変)。仕様は逆アセンブルどおり (n > 0 のとき n 個の byte を val で埋める)。

```c
unsigned long long function_40d210(void *p, unsigned long long n, unsigned long long val, unsigned long long x) {
    (void)x;
    if ((long long)n > 0) memset(p, (int)(val & 0xff), (size_t)n);
    return 0;
}
```

- 結果: survey `ok 873 / miss 47 / halt0 7 / oob 14 / noproc 1` (基準と同じ)。per-unit の kind 差は 0/942。unit 492 は `oob` のまま、trap の位置だけ移動した。基準 `function_4133f0 ← 4473f0 ← 446400 ← 446ad0 ← ad5700` → 試行 `function_412e40 ← 448490 ← 448350 ← 446400 ← 446ad0 ← ad5700`。`4473f0` の i=2 (`dest2` の旧値 `0x1_00000003`) による trap は消えた。
- 解釈: 残存値 (`dest2` の旧値) が trap の入力だったことを支持する。次の trap (`412e40`) は本件の範囲外で未調査 (§9.6)。
- 試行後は `m11_ov.c` を元に戻した (`git status` は空)。

### 9.5 類型判定

- D17 ではない理由: D17 は「8 B の 0 初期化が IR で 4 B に縮み、上位 4 B が残る」。本件では 8 B の 0 書込みが IR に残っている (`415610` の `store i64 0, ptr %78/%79/%81/%83`、shim は `Q(p) = 0`)。欠けているのは 112 B の memset 本体で、書込みが 1 つも出ない。残存の経路は縮みでなく no-op。
- 近い類型: D13 (`DEFECTS.md`: 関数範囲の過小推定、終端ヒューリスティック)。本件は「最初の `ret` で関数を閉じ、その後ろに置かれた同一関数の分岐先 (`40d2d1`) を落とす」。層は fe。効果は silent (分岐先が無いため `jg` が return に畳まれる)。
- 登録案 (PM 判断・未登録): D13 の事例追加、または新 ID (「関数本体の後ろに置かれた out-of-line 分岐先の脱落」)。

### 9.6 未解決・起票先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `40d210` の n > 32 本体の転記 (`m11_ov.c`) と全 survey の再測定 | unit 492 の残存値の除去 (修復) | #3921 (`[M11-N200]`) |
| unit 492 の次の trap (`412e40` ← `448490` ← `448350` ← `446400`) | unit 492 が ok にならない | #3918 (`[M11-N199]`) |
| RTTI の要素数 (14 は 0x100..0x170 からの推定。count 自体は未読) | 0x100..0x170 の範囲の厳密な確認 | 本 REPORT (子の修復の検証で確かめる) |

### 9.7 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64          # fl-win64 を展開した先 (§1)
python3 tools/m11/trap_triage/native_zeroinit_2891.py tools/m11/work/boot_final.ll   # §9.2・§9.3 (読取りのみ)
bash tools/m11/m11_gen_ir2.sh && bash tools/m11/m11_build.sh                          # 本 run: 52.0 s / 24.6 s (n=1)
node tools/m11/trap_triage/survey_units.mjs <out>.json                                 # 本 run: 12.3 s (n=1)
```

- 所要の環境: nproc 4、並列 1、開始時の 1 分 load average 0.15。終了時の load は未記録 (本 run の数値は n=1)。

### 9.8 差分 0 の証跡

- 測定 commit `58ed035cf` から本 commit までの build 入力の差分: `git diff 58ed035cf HEAD -- tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/m11_rt.c tools/m11/m11_ov.c tools/m11/trap_triage/survey_units.mjs` の出力は **0 bytes** (`| wc -c` = 0)。shim 試行 (§9.4) は commit していない。新規の `native_zeroinit_2891.py` は build 入力ではない。

## 10. `40d210` 転記の検証 (#3921、測定 commit `22c914300`)

- 変更: `tools/m11/m11_ov.c` に `function_40d210` を転記 (n <= 0 は何もしない。n > 0 のとき n byte を val で埋める)。`git diff 634d33214 22c914300 -- tools/m11/m11_ov.c` = 10 行追加のみ。
- 測定 commit `22c914300` の既定 build: `m11_gen_ir2.sh` rc 0 (32.9 s、490,761 行) → `m11_build.sh` rc 0 (18.2 s)。load average 0.66 (開始時、1 分)。
- 基準: 転記前の `m11_ov.c` (`origin/main` の `ee2883ab8` と同一) で既定 build と survey を取った (同じ `work-m11` snapshot・同じ PE から `m11_gen_ir2.sh` で IR を作り直した)。
- survey 集計 (`survey_units.mjs`): 基準 `ok 873 / miss 47 / halt0 7 / oob 14 / noproc 1`、転記後 `ok 873 / miss 47 / halt0 7 / oob 14 / noproc 1` (計 942、転記後は 3 回とも同一)。survey の所要 6.5 s / 6.7 s (並列 1、nproc 4)。
- per-unit の kind 差: 基準と転記後で **0/942**。ok → non-ok の unit は **0 件**。
- unit 492 (probe build `M11_PROBE_2780=1`、`probe_2780_units.mjs`): `4473f0` の i=2 の `dest2` (`0x10aa1430`) の旧値 (tag 10) が、基準の `0x1_00000003` から **`0x0`** になった。この trap (`4473f0` → `function_4133f0` の `*dest = s` で OOB) は消えた。
- unit 492 の frame の変化: 基準 `function_4133f0 ← function_4473f0 ← function_446400 ← function_446ad0 ← function_ad5700` → 転記後 `function_412e40 ← function_448490 ← function_448350 ← function_446400 ← function_446ad0 ← function_ad5700` (kind は oob のまま)。次の trap は #3918 で扱う。
- 呼出しの整合 (受入 4): `function_4159e0` の `count << 3` (kind 10/11/15/17/18、count > 1) と `count * 24` (kind 12) は、転記した `n` の単位 (byte) と一致する。`m11_ov.c` 内の `function_416db0` 周辺 (`nkeep * elsz`・`(len - oldlen) * elsz`) も byte 数で渡している。呼出しの引数の意味は変えていない。
- 製品 KPI (起動): **動かしていない**。`tools/flelift/boot/REPORT.md` の dispatch 数・通過 unit 数は測っていない (本 PR は m11 の unit survey の範囲)。

### 10.1 差分 0 の証跡

- 測定 commit `22c914300` 以降の build 入力の差分は無い (本 REPORT の追記のみ)。

## 10. unit 492 の `$2983` 入口の実行時値 (#4882、測定 commit `7cb5df311`)

- build: `m11_gen_ir2.sh` rc 0 → `m11_build.sh` rc 0。計装版は `wasm-opt --instrument-memory` (version 133) で `work/trap_2891/instr.wasm`、`wasm-dis` で `instr.wat` (`$2983` は 1304192 行、`call $161` は 1304857 行)。
- 入口 hook: `trap_triage/patch_entry_2983_4882.py` が `instr.wat` の `local.set $8` の直後に `dbg_entry_4882(i32 $2, i64 $0)` を足す (分岐・戻り値は変えない)。
- 組み立て: `wasm-as --all-features` で組んだ wasm は Node が `unknown import kind 0x7e` で読めなかった。`--enable-bulk-memory --enable-sign-ext --enable-mutable-globals --enable-nontrapping-float-to-int` で組むと読める。
- 実行: `trap_triage/entry_2983_4882.mjs` で全 942 unit を順に実行 (4 分 30 秒、rc 0)。kind は survey と一致 (`ok 873 / miss 47 / halt0 6 / oob 15 / noproc 1`)。記録は unit 492 のみ。
- 結果 (unit 492、`$2983` 入口 1 回): `$2` = `0x10f`、`*(s+280)` = `0x0`。`$8 = ($2 & 0xffff) - 256 = 15`、`$15 = ($8 < *(s+280)) = 0`。`block3` を抜けないため `call $161` (第 3 引数 `i64.const 1`) が実行される。
- 単独実行の注意: unit 492 だけを先に回すと `oob` になり、`$2983` に到達しない (測定 commit の base でも同じ)。前 run までと同じく、全 unit を順に回す必要がある。
- 未確定: 「`$2983` が 0x10aa1150 に値 1 を置く」の同一 run での照合は未実施 (watch と入口 hook は別の run)。`$2` の由来 (呼び出し元) は次の run の範囲。
