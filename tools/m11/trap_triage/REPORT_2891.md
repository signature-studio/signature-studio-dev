# #2891: unit 492 OOB の `4473f0` 配列 dest2 の旧値 (`0x1_00000003`) の書込み主体 (現 build での特定)

親: #2780 (経緯は `REPORT_2780.md`)。測定 commit: `ed70adf5a` (origin/main。本 PR は計測スクリプトと本 REPORT を足すだけで、build 入力 (IR・C・build スクリプト) は変えていない。§8)。
既知類型との関係: D17 (DEFECTS.md) に似るが未確定 (§5)。D1a〜D23 の既存類型には当てはまらないと判定した (§5)。

## 0. 結論

- **REPORT_2780 の番地 `0x10aa1160` は、現 build (`ed70adf5a`) では同じ役割の番地ではなかった。** 現 build の unit 492 では、`4473f0` の i=2 の `dest2` は `0x10aa1430` (arg2 = `0x10aa12f0`)。REPORT_2780 の `arg2 = 0x10aa1020` との差 `0x2d0` だけ番地がずれている (build の配置差。§3)。`0x10aa1160` は現 build では別用途 (shadow stack 局所) の番地で、同番地への書込みは unit 15〜898 に散在する (§4)。
- **受入 1 (書込み主体) は、現 build の `0x10aa1430` で達成した。** 書込みは 4 unit (432・477・484・492) のみ。主体は次のとおり (§4.2)。
  - unit 432: `InitializeCriticalSectionAndSpinCount` → `InitializeCriticalSection` (`function_423940` 経由) の CRITICAL_SECTION 初期化 (4B 書込み 3 件)。上位 dword `1` はこの 4B 書込み (`0x10aa1434` の値 1) 由来。
  - unit 477・484: `function_4133f0` (C 版 `System._UStrAsg`) の shadow stack 局所 (+48 の 4B `len`)。REPORT_2672 の `u32 len` と同じ機構。
  - unit 492: `function_4133f0` の `*dest = s` (8B、`s = 0`)。旧値を読んだ後の書込み (OOB 入力そのものは書込み主体ではなく、unit 432 以降の残骸)。
- **受入 2 (`4473f0` 配列の native 0 初期化の箇所) は未達。** 呼出し元の逆アセンブルは本 run で行わなかった (§6・未解決 1)。
- **受入 3 (類型判定) は未確定。** 観測: 同じ 8B 番地 `0x10aa1430` を、別の寿命の 3 種 (CRITICAL_SECTION の初期化・UStrAsg の局所 `len`・4473f0 の配列 `dest2`) が共有している。これは残骸型の機構で、D17 に似る。ただし native 側で配列が 0 初期化されるかは未確認なので、類型は確定しない (§5)。

## 1. 素材と再現

- 素材 (`$ARTIFACTS_DIR`): `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`extracted/block00031_PE.bin` 確認)。`work-m11` を `tools/m11/work/`、`work-liftdiff` を `tools/liftdiff/work/` に展開 (worktree 内)。`toolchain-retdec` / `toolchain-emsdk` は `/opt/retdec`・`/opt/emsdk` が既に存在し (`/opt/emsdk/upstream/bin/wasm-opt` version 133) これを使った。
- 既定 build: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/m11_gen_ir2.sh` rc 0 (51.2 s、490,761 行) → `bash tools/m11/m11_build.sh` rc 0 (24.8 s)。
- 計装 build: `M11_PROBE_2780=1 bash tools/m11/m11_build.sh` rc 0 (probe 用。計測後に既定 build へ戻して §2 の survey を取り直した)。

## 2. 基準 survey (既定 build、`ed70adf5a`)

- `survey_units.mjs` 3 回: 3 回とも `ok 873 / miss 47 / halt0 7 / oob 14 / noproc 1` (計 942)。per-unit JSON は `cmp` で 3 回一致。
- REPORT_2780 §2 の基準 (`ok 872 / miss 47 / other 1 / halt0 7 / oob 14 / noproc 1`) との差: `other 1` が現 build では `ok` になっている (unit は未特定。REPORT_2780 に per-unit JSON が無い)。oob 14 は一致。
- 計装版 (`wasm-opt --instrument-memory`、§4) の全 942 unit の kind は既定 build と差分 0 件 (`watch_store_2891.mjs` の出力と `survey` の per-unit 比較)。
- 所要時間: survey 1 回 12.25 s (n=1。load average は未記録。並列数 1)。

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

- `wasm-opt --instrument-memory` (version 133) で既定 build の `m11_boot.cjs.wasm` の全 store に hook (`store_ptr` / `store_val_i32|i64`) を入れた `instr.wasm` を作る (`work/trap_2891/`、commit しない)。hook は JS import で線形メモリに書かない。
- `store_sites_2891.py` が `store_ptr` の import 番号を wat から引き、store 計装 id → (wasm 関数 index・wat 行・bytes・offset) の表を作る (59,360 id・重複 0)。REPORT_2672 の `store_sites_2672.py` は import 番号 (`$fimport$32`) を固定していたため、この build では使えない (`$fimport$34`)。
- `watch_store_2891.mjs` は監視番地 (既定 `0x10aa1430`) と重なる全 store を記録する (8B 同値の store も含む。値 `val`・store 直前の 8B `old8`・wasm frame)。frame は `WATCH_LOG_UNITS` で絞る (全 hit の frame 取得は 1 hit あたり約 27 ms で、全 unit だと 7 分超)。
- wasm frame の `wasm-function[N]` は V8 の絶対 index。wat の defined index は `N − 39` (import 39 本)。exports 表で名前に戻す。

### 4.2 `0x10aa1430` の書込み (unit 0〜492、計装版)

| unit | store id | bytes | 書込み (addr) | 値 (old → new) | 書込み主体 (wasm 関数 ← 呼出し元) |
|---|---|---|---|---|---|
| 432 | 133408 | 8 | `0x10aa1430` | `0xf960` → `0xf960` (同値) | `m11_icall` (wat 14822) ← `function_410320` ← `function_9f2d80` |
| 432 | 136247 | 4 | `0x10aa1434` | `0xf960` → `0x1_0000f960` | 無名 wasm 14978 ← `InitializeCriticalSectionAndSpinCount` (14977) ← `InitializeCriticalSection` (14979) ← `function_423940` (275) |
| 432 | 136250 | 4 | `0x10aa1430` | `0x1_0000f960` → `0x1_00000000` | 同上 (14978) |
| 432 | 136264 | 4 | `0x10aa1430` | `0x1_00000000` → `0x1_102a00f8` | 同上 (14978) |
| 477 | 133986 | 4 | `0x10aa1430` | `0x1_102a00f8` → `0x1_00000002` | `function_4133f0` (wat 14850、`m11_ov.c` の C 版 UStrAsg、store +48) ← `function_abeef0` ← `function_abfd60` |
| 484 | 133986 | 4 | `0x10aa1430` | `0x1_00000002` → `0x1_00000003` | `function_4133f0` (+48) ← `function_acf650` ← `function_ad0680` |
| 492 | 134001 | 8 | `0x10aa1430` | `0x1_00000003` → `0x0` | `function_4133f0` (+0、`*dest = s`、`s = 0`) ← `function_4473f0` (2688) ← `function_446400` (2686) ← `function_446ad0` (2693) |

- 上位 dword `1` は unit 432 の 4B 書込み (`0x10aa1434` の値 1) 由来。下位 dword `2`・`3` は unit 477・484 の `function_4133f0` の局所 `len` (+48) の 4B 書込み由来。`0x1_00000003` は、この 2 つの書込みと unit 432 の CRITICAL_SECTION 初期化の残骸が重なった値。これは REPORT_2780 §5 の `0x1_1029fe28 → 0x1_2 → 0x1_3` と同じ形 (番地と値は build で変わる)。
- unit 432 の 8B 書込み (`0x10aa1430`、値 `0xf960` 同値) は変化を生まない。REPORT_2780 の「8B 書込み (上位 dword = 1)」は、この unit 432 の下位 4B 書込み (`0x10aa1434`、値 1) に当たる。
- 0x10aa1430 の hit 総数は 2,548,226。大半は unit 304 (2,546,099) と unit 298・369 (260・625)。unit 432・477・484・492 は各 1〜4 件。

### 4.3 `0x10aa1160` (REPORT_2780 の番地) の現 build での扱い

- 旧番地 `0x10aa1160` への書込みは unit 15・17・101・184・189・190・246・280・291・492・616・745・830・895・898 にあり (読取りのみの probe でも同じ)、REPORT_2780 §5 の unit 415〜492 の遷移は現 build では再現しない。
- unit 291 の書込みは `VirtualAlloc` (wat 14886、`function_407770` ← `function_407a50`) の 4B 2 件 (`0x10aa1164` ← `0x7d50000`、`0x10aa1160` ← `0x101000`)。値の出所は未確認。
- 旧番地の unit 492 の書込みは `function_4133f0` の shadow stack 局所 (`0x10aa1160 = frame + 32`) で、dest2 とは別物。

## 5. 類型判定 (仮説・未確定)

- 既知類型: D17 (`DEFECTS.md`: 64bit 局所の 0 初期化が 4B store に縮み、上位 4B が残る) に**似る**。ただし本件は、上位 dword の残骸が 4B store (unit 432) で作られ、下位 dword も別の 4B store (unit 477・484) の残骸。D17 の機構 (1 つの 8B 初期化の縮退) とは一致しない。
- 観測: `0x10aa1430` は寿命の異なる 3 つのもの (CRITICAL_SECTION の初期化・UStrAsg の局所 `len`・`4473f0` の配列要素 `dest2`) が共有している。native で `arg2+0x100..+0x170` が 0 に初期化されていれば、i=2 の旧値は 0 になるはずで、この観測と整合する。ただし native の 0 初期化は**未確認** (§6)。
- 類型案 (仮説・未検証): 「`4473f0` の配列 (`arg2+0x100..+0x170`) の初期化 (呼出し元の系列) が lift で欠け、同番地の残骸 (CRITICAL_SECTION・UStrAsg 局所) を旧値として読む」。DEFECTS への登録は PM 判断 (`WORKFLOW.md` §5)。

## 6. 未達・未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1. `4473f0` の配列 `arg2+0x100..+0x170` を native がどこで 0 初期化するか (呼出し元 `446ad0`・`446400`・`ad5700` の逆アセンブル。native の配置は `arg2` = `0x10aa12f0` 相当の構造体の中身で確かめる) | 受入 2。修復の方針 | #2891 (残り。本 issue は open のまま) |
| 2. CRITICAL_SECTION (`0x10aa1420`) と `4473f0` 配列 (`dest2` i=2 = `0x10aa1430`) の重なりが native の配置か、lift の配置ずれか | 受入 3 の根拠 | #2891 |
| 3. 類型 (D17 / 別類型) の判定と DEFECTS 登録案 | DEFECTS の登録 (PM 判断) | #2891 |
| 4. 基準の差 (`other 1` → `ok`) の unit 特定 | 基準 survey の鮮度 | 本 REPORT §2 (再測定の子は起票しない) |
| 5. unit 304 の 2,546,099 hit (0x10aa1430 の周辺の反復書込み) の意味 | 計測の読み (本件の書込みには影響しない見込み) | #2891 の範囲外。未解決 |

- 1 run に収まる範囲で、受入 1 (書込み主体) を完了させた。受入 2・3 は調査の残りで、実装・修復の作業ではないため子 issue は起票しない (`WORKFLOW.md` §3)。

## 7. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
bash tools/m11/m11_gen_ir2.sh && bash tools/m11/m11_build.sh            # 既定 build (§1)
node tools/m11/trap_triage/survey_units.mjs tools/m11/work/trap_triage/base1.json   # §2
export PATH="/opt/emsdk/upstream/bin:$PATH"
mkdir -p tools/m11/work/trap_2891
wasm-opt --instrument-memory tools/m11/work/m11_boot.cjs.wasm -o tools/m11/work/trap_2891/instr.wasm
wasm-dis tools/m11/work/trap_2891/instr.wasm -o tools/m11/work/trap_2891/instr.wat
python3 tools/m11/trap_triage/store_sites_2891.py tools/m11/work/trap_2891/instr.wat tools/m11/work/trap_2891/sites.json
WATCH_W=0x10aa1430 WATCH_UNITS=$(seq -s, 0 492) WATCH_LOG_UNITS=432,477,484,492 \
  node tools/m11/trap_triage/watch_store_2891.mjs tools/m11/work/trap_2891/watch_w1430_log.json   # §4.2 (約 3 s)
```

- 注: `watch_store_2891.mjs` は `work/m11_boot.cjs` (既定 build の glue) を読む。`M11_PROBE_2780=1` の build の後は既定 build を作り直すこと。

## 8. 測定 commit からの差分 (差分 0 の証跡)

- 測定 commit: `ed70adf5a` (origin/main)。計測に使った build 入力 (IR・C・build スクリプト・`survey_units.mjs`・`probe_2780_units.mjs`) は、この commit と同一。
- 本 PR の差分は `tools/m11/trap_triage/` の計測スクリプト 2 本 (`store_sites_2891.py`・`watch_store_2891.mjs`) と本 REPORT、`docs/DOC_MAP.md` の索引 1 行だけ。`git diff ed70adf5a HEAD -- tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/m11_rt.c tools/m11/m11_ov.c tools/m11/trap_triage/survey_units.mjs tools/m11/trap_triage/probe2780_ir.py tools/m11/trap_triage/probe_2780_units.mjs` の出力は空 (コミット後に確認)。
