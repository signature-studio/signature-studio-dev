# M11 qstore REPORT (#516) — 64bit スタック局所の即値 store が 4B に縮む欠陥 (DEFECTS.md D17)

**判定: 達成** (#516 の受入条件 5 項目)。機械語 `mov qword ptr [rbp|rsp+d], imm32` (8B) が RetDec IR で
`store ptr null` / `store i32 imm` (wasm32 では 4B) に縮み、上位 4B が未初期化のまま残る欠陥を全 closure で数え、
capstone 突合で確定した 279 site を `store i64` に戻す pass (`m11_qstore.py`, `m11_build.sh` に常設) を入れた。
**#513 (PR #521) 取り込み後の HEAD** で survey は NC 856/38/46/1 (clobber 1) → 修復 864/31/46/1 (clobber 0)、ラベルが変わる unit は **9 本** (idx 58–63 の 6 本 / 87 / 898 が trap→ok、144 が clobber→trap)。#513 前の「816/79 → 817/78、変化は idx 87 のみ」は #513 の OOM 巻き添えを含む旧測定で、HEAD では成り立たない (§5)。

既知類型との関係: **新規** (`docs/DEFECTS.md` D17)。D1 系 (旧値 load の脱落) と同じ `_UStrClr` 系の症状だが、こちらは **store 側の幅**。
D11 (VA リテラルの wasm32 切り捨て) と同じく「wasm32 化で 64bit が 32bit に縮む」系。
検証起点 commit: §1–§3・§4 の転記個別無効化表は旧 `46eb303` (base `6a0a8c8`, #513 取り込み前) の実測。**§4 (58–63 の帰属)・§5 は #513 取り込み後のコード HEAD `8e5f760` (= `3eb8701` main 取り込み + PE 既定パスの env.sh 化のみ) で再測定**。
環境: GitHub Actions 4 vCPU runner, capstone 5.0.7 + pefile の venv (ldfix 有効), node v22.23.3, work-m11 / work-liftdiff / fl-win64 の `block00031_PE.bin`。

## 1. 原因 (実測)
- idx 87 (VA 0x59f9a0 = `function_59f9a0`): 機械語 `0x59f9d7 mov qword ptr [rbp+0x48], 0` → IR `store ptr null, ptr %stack_var_-16`。
  `target datalayout` が `p:32` のため `ptr` は 4B。直後の `function_418190(&slot, ..)` (PR #411 の C 転記) が `Q(dest)` (8B) で読み、上位 4B のゴミを旧値と解釈 (`old=0x32_00000000`) → OOB。
- idx 898 (VA 0x1306110, `function_12f98f0` → `function_412d60`): 機械語 `mov qword ptr [rbp+0x28], 0` → IR `store i32 0, ptr %stack_var_-48` (RetDec が imm32 を i32 で出す)。同型 (`old=0x08788d8b_00000000`)。
- 旧 RetDec 版 412d60 / 418190 は旧値 load を落としていて slot を読まなかったため症状が出なかった (PR #411 の転記で顕在化)。

## 2. 検出 (受入条件 1) — `m11_qstore.py --detect-only`
- 母集団: gen_ir2 直後・qstore / alloca pass 前の IR の `define @function_*` 7,421 本。うち .pdata に区間がある 6,969 本を capstone で線型逆アセンブル (452 本は .pdata 無しで走査不可; うち幅不足 imm store は 0 件)。
- 機械語側: `mov qword ptr [rbp|rsp+d], imm32` (index 無し) **3,528 件 (imm==0 は 3,428)**。slot は entry rsp 基準 (RetDec の `%stack_var_N` 命名) に換算 (prologue の push / sub rsp / `mov rbp,rsp` / `lea rbp,[rsp+K]` を追跡、後方 jcc の stack probe ループは読み飛ばす)。
- IR 側: `store (i32 <imm> | ptr null), ptr %stack_var_N` (直接・bitcast 別名) **419 件**。`%stack_var_N.k.reg2mem` (phi 退避 slot = メモリ上の局所ではない) は除外。
- 判定 (slot, 値ごと): 同 slot に 8B 未満の機械語 store が無く 8B store がある → 修復対象。

| verdict | 件数 | 意味 |
|---|---|---|
| `fix` | 276 | IR の幅不足 store の個数 == 機械語 qword-imm store (同 slot・同値) の個数 |
| `fix_slot` | 3 | 個数/値の 1:1 は取れないが、同 slot の機械語 store が全て 8B (function_101b780 / 6a4c50 / 785220; 785220 は reg 経由の 8B store) |
| `machine_narrow` | 140 | 同 slot に dword 以下の機械語 store がある = 幅が正しい or 判別不能 → 触らない |
| `no_machine_store` | 0 | |

**修復対象 279 site / 158 関数** (`store ptr null` 209 + `store i32 0` 70; 値は全て 0)。site 一覧は `results/qstore_sites.tsv` (`function / slot / 値 / verdict / IR 行 / IR 文`)、集計は `results/qstore_detect.json`。idx 87 は function_59f9a0 の slot -16 / -24 / -32 の 3 site、idx 898 は function_12f98f0 の slot -48 の 1 site を含む。
機械語 3,528 件の内訳: IR で既に `store i64` 2,197 / 幅不足 IR store と対応 278 (対応は (slot, 値) 単位の個数 min のため 279 と 1 件ずれる) / **IR に直接 store が無い 1,053** (alloca が無い 1,024 [SSA 昇格 or dead store 除去と推定, 未検証] / alloca 有り別形 27 / 大 alloca の内部 2)。
**別算法検算** `crosscheck_bytes.py` (capstone 不使用, バイト列パターン `48 C7 45/85/44 24/84 24 ..`): 3,537 件 (imm==0 は 3,434)。capstone 版との集合差は only-bytes 9 / only-capstone 0 (9 件は命令境界外の偽一致と**推定**)。

## 3. 修復 (受入条件 2) と選択理由
IR 側で直す (qstore pass): 確定 site を `store i64 <imm>, align 8` に書換え、alloca が 8B 未満 (`alloca ptr` / `i32`) なら `alloca i64, align 8` に拡幅 (274 alloca)。idempotent (出力を再入力して `cmp` 一致を実測)。
- 採らなかった案: C 転記側を 4B 読み (`D(dest)`) にする — `_UStrClr` / `_LStrArrayClr` の 2 関数にしか効かない。欠陥は IR の store 幅で、8B で読む他の C 転記・lift の `load i64`・callee にも潜在するため、原因側を直す。
- alloca pass の規則 (R9) として足さなかった理由: 一律に `store ptr null` を i64 化すると、機械語が dword で書いている slot まで広げる。機械語突合が要るため ldfix と同じ capstone 突合の独立 pass にした。
- 順序: `m11_build.sh` で alloca pass の**前**に適用。`M11_QSTORE=0` で無効化 (ネガコン)。capstone / pefile が無いと WARNING でスキップ (gen_ir2 の ldfix と同じ)。

## 4. idx 87 / 898 / 58–63 の帰属 (受入条件 3) — `unit_probe.mjs` (survey と同手順, idx 101 / 144 を skip)
### 4.1 idx 87 / 898 (転記の個別無効化: `46eb303` 時点の実測, 各 n=1。HEAD では未再測)
idx 101 (暴走 unit: GetMem 23,056,285 回・1,477.2 MB) と idx 144 (InitTable 破壊) は PR #411 レビューの指摘 (#513)。当時は skip しないと idx 898 が **OOM** (`[m11][VA] OOM want=1.3MB used=1490.0MB` → Halt0) で trap し、帰属が見えなかった。

| 構成 (qstore は最後の行のみ有効) | idx 87 | idx 898 |
|---|---|---|
| main `6a0a8c8` 相当 (転記 2 本とも有効) | trap (OOB) | trap (OOB) |
| `function_412d60` 転記のみ無効 | trap (OOB) | **ok** |
| `function_418190` 転記のみ無効 | **ok** | trap (OOB) |
| 412d60 + 418190 転記とも無効 | ok | ok |
| **qstore 有効 (本修正)** | **ok** | **ok** |

→ **idx 87 = `function_418190` の転記、idx 898 = `function_412d60` の転記**が 4B 初期化の局所 slot を `Q()` で読むことが原因。
**HEAD (#513 取り込み後) の追加確認** (`QS_EXCLUDE` で qstore の対象関数だけ除外する一時パッチ。コミットなし, 各 probe n=1): qstore 有効のまま `function_8cbb00` (§4.2) + `function_59f9a0` (idx 87) + `function_12f98f0` (idx 898) の 3 関数 (6 site, fixed_stores 279→273) を除外すると idx 87 / 898 / 58–63 は全て **trap (OOB)**。`8cbb00` だけ除外 (§4.2) では 87 / 898 は ok のままなので、87 / 898 の trap 復帰は `59f9a0` / `12f98f0` の除外によるもの = HEAD でも 87 / 898 は qstore の効果 (この 2 関数だけの除外は未実施)。
**#513 後の idx 898**: per-unit VA 上限で OOM 巻き添えが無くなり、無 skip の survey でも idx 898 は ok (OOM は idx 101 = 0x1de960 の 1 本のみ)。旧記載「無 skip survey では idx 898 は OOM のまま」は HEAD では不成立。

### 4.2 idx 58–63 (6 本) が修復で ok になる理由 = qstore の効果 (HEAD, 確定)
- NC (`M11_QSTORE=0`) の probe (skip 101,144, n=1): 6 本とも **同一スタック** で OOB — `function_417b70` ← `417fc0` ← `8cbb00` ← `8cbcb0` ← `8cc190` ← `8c7a10` ← `8c5cc0`。(idx 58–63 = VA 0x177290 / 0x177fd0 / 0x179610 / 0x17fd50 / 0x180970 / 0x182230。共通の呼出し連鎖 `8cc190←8c7a10←8c5cc0` は旧 REPORT §4 の「`function_8cbcb0` 系 9 unit」と同じ系統。)
- `qstore_sites.tsv` に `function_8cbb00` の 2 site (slot -48 / -56, `store ptr null`, verdict `fix`) がある。IR は `%stack_var_-56` を `function_417fc0(ptr %stack_var_-56, ..)` の第 1 引数 (`var a: Pointer`) に渡しており、`417fc0` → `417b70` (`m11_ov.c` の `DynArraySetLength` C 転記) が `Q(a)` (8B) で読む = idx 87/898 と**同型の D17** (4B 初期化 slot の上位 4B ゴミ)。
- 個別無効化 (qstore 有効のまま `function_8cbb00` の 2 site だけ除外, fixed_stores 279→277): idx 58–63 が **全て trap に戻り**、idx 87 / 898 は ok のまま。survey **858/37/46/1 (clobber 0, OOM 1)** を 3 回 (各回 gen_ir2 から) すべて同じ結果で再現。この構成と修復 (864/31/46/1) のラベル差は idx 58–63 の 6 本だけ (6 + 858 = 864)。
- → 58–63 の ok 化はすべて `function_8cbb00` の 2 site の修復による (qstore 以外の要因は無い)。

### 4.3 idx 144 (clobber → trap) は 8cbb00 とは別 (帰属未了)
NC では idx 144 は InitTable 破壊 (clobber, OOM 巻き添えを隠していた #513 の対象) で、修復で trap になる。`8cbb00` だけ除外した survey (上) でも idx 144 は trap のままなので **8cbb00 の効果ではない** (他の qstore site のどれかで、unit 144 の暴走が 4B ゴミ由来の別経路に変わった)。どの site かは**未切り分け** (§6)。

## 5. ネガティブコントロール (受入条件 5) と実測 — `bash tools/m11/qstore/qstore_e2e.sh` (コード HEAD `8e5f760`, #513 取り込み後)
| 構成 | idx 87 (probe, skip) | idx 898 (probe, skip) | survey ok/trap/miss/noproc (clobber, OOM) | 通常起動 units_run |
|---|---|---|---|---|
| NC: `M11_QSTORE=0` | trap (OOB) | trap (OOB) | 856 / 38 / 46 / 1 (clobber 1 = idx 144, OOM 1 = idx 101) | 22 |
| 修復: `M11_QSTORE=1` | ok | ok | **864 / 31 / 46 / 1** (clobber 0, OOM 1) | 22 |
| 修復 − `8cbb00` の 2 site (§4.2) | ok | ok | 858 / 37 / 46 / 1 (clobber 0, OOM 1) | — |

- **ラベル差 (NC → 修復) は 9 unit**: idx 58–63・87・898 が trap→ok、144 が clobber→trap (qstore_e2e 3 回すべて同一)。ok の増分は **+8** (856→864)、trap は 38→31 (8 本が ok になって −8、144 が clobber から trap に加わって +1)。trap 内訳は NC が halt0 7 + OOB 31 → 修復が halt0 8 + OOB 23 (OOM の 1 本を含む)。
- **再現回数 n=3** (qstore_e2e 3 回, 各回 gen_ir2 から作り直し): NC survey 3 回すべて 856/38/46/1、修復 survey 3 回すべて 864/31/46/1。`m11_e2e.sh` 3 回 (修復状態) も `survey_ok 864 / trap 31 (oom 1) / clobber 0 / miss 46`, `reached_stage 4`, `units_run_full 22`, GetMem 33 / FreeMem 20 で 3 回一致。
- **所要 / load average** (1 分値, 開始→終了, 4 vCPU runner): qstore_e2e **108 / 106 / 106 s** (0.44→0.99, 0.99→1.06, 1.06→1.01; gen_ir2 ×2 + build ×2 + probe ×2 + survey ×2 を含む)。`m11_e2e.sh` **67 / 39 / 38 s** (1.01→1.12, 1.12→1.07, 1.07→1.03; 1 回目のみ gen_ir2 + data/image 再生成込み、2・3 回目は増分)。
- 旧 `46eb303` 時点 (#513 取り込み前, 参考): NC 816/79/46/1 → 修復 817/78/46/1 (変化 idx 87 のみ)。OOM の巻き添えで 58–63・898 が trap のまま、かつ 144 が OOM で隠れていた。HEAD の数値とは**比較しない**。
- `m11_e2e.sh` の reached_stage は 4/6 のまま (本修正は stage を進めない。stage 5 は #490 / #132)。

## 6. 検証範囲 / 範囲外・未解決
範囲: 上記の機械語突合・NC・probe。範囲外: `--full` 再生成、idx 87 / 898 以外の unit の意味的な正しさ、`machine_narrow` 140 件の個別検証。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| idx 144 が NC の clobber から修復で trap に変わる原因 site (8cbb00 ではない)。idx 101 (OOM 1 本) の暴走根因 | survey の trap 31 に残る / clobber の隠れ方が変わるだけで意味の改善ではない | #513 (idx 101 / 144。site 特定は #132 にコメント) |
| 機械語 qword-imm store のうち IR に直接 store が無い 1,053 件 (alloca 無し 1,024 は SSA 昇格 / dead store 除去と推定のみ) | callee が lea 経由で読む slot なら別型の store 脱落 | #132 にコメント (全数監査の子チケットは PM 判断) |
| qstore は即値 store のみ。非定数の 4B 縮み (`store ptr %x` 等) は対象外 (reg 経由で 0 を 8B 書いていた 3 件は `fix_slot` で拾っただけ) | 非定数ポインタ store でも同型の縮みがありうる | #132 にコメント (D17 の検出信号拡張) |
| `fix_slot` 3 件・`machine_narrow` 140 件は機械語との 1:1 対応が無い (前者は書換え済み、後者は非書換え) | 後者に qword と dword が混在する slot があれば取りこぼし | 本 REPORT (個別未検証) |
| `alloca/m11_alloca.py` の `SZ['ptr']=8` は datalayout `p:32` (4B) と不整合 | 現 IR で 4B alloca への 8B 直接 access は 0 件 (実測: qstore 前の `store/load i64\|double\|i128`) なので実害なし | `alloca/REPORT.md` 残置 |
| AGENTS.md / WORKFLOW.md §4 の「D1〜D16」表記が D17 追加で古くなる | 表記のみ | PM が整合 |
