# M11 qstore REPORT (#516) — 64bit スタック局所の即値 store が 4B に縮む欠陥 (DEFECTS.md D17)

**判定: 達成** (#516 の受入条件 5 項目)。機械語 `mov qword ptr [rbp|rsp+d], imm32` (8B) が RetDec IR で
`store ptr null` / `store i32 imm` (wasm32 では 4B) に縮み、上位 4B が未初期化のまま残る欠陥を全 closure で数え、
capstone 突合で確定した 279 site を `store i64` に戻す pass (`m11_qstore.py`, `m11_build.sh` に常設) を入れた。
idx 87 は ok に戻り (survey 816/79 → 817/78, 変化した unit は idx 87 のみ)、idx 898 も同修正で ok に戻る (OOM を除いた条件, §4)。

既知類型との関係: **新規** (`docs/DEFECTS.md` D17)。D1 系 (旧値 load の脱落) と同じ `_UStrClr` 系の症状だが、こちらは **store 側の幅**。
D11 (VA リテラルの wasm32 切り捨て) と同じく「wasm32 化で 64bit が 32bit に縮む」系。
検証起点 commit: コード `46eb303` (base `6a0a8c8` = main, PR #411 merge)。以降の commit は docs / `crosscheck_bytes.py` のみ。
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

## 4. idx 898 の帰属 (受入条件 3) — `unit_probe.mjs` (survey と同手順, idx 101 / 144 を skip)
idx 101 (暴走 unit: GetMem 23,056,285 回・1,477.2 MB) と idx 144 (InitTable 破壊) は PR #411 レビューの指摘 (#513)。skip しないと idx 898 は **OOM** (`[m11][VA] OOM want=1.3MB used=1490.0MB` → Halt0) で trap し、どの変更でも同じ trap になるため帰属が見えなかった。

| 構成 (qstore は最後の行のみ有効) | idx 87 | idx 898 |
|---|---|---|
| main `6a0a8c8` 相当 (転記 2 本とも有効) | trap (OOB) | trap (OOB) |
| `function_412d60` 転記のみ無効 | trap (OOB) | **ok** |
| `function_418190` 転記のみ無効 | **ok** | trap (OOB) |
| 412d60 + 418190 転記とも無効 | ok | ok |
| **qstore 有効 (本修正)** | **ok** | **ok** |

→ **idx 87 = `function_418190` の転記、idx 898 = `function_412d60` の転記**が、それぞれ 4B 初期化の局所 slot を `Q()` で読むことが原因 (各 n=1)。PR #411 レビューの「NC 3 種でも idx 898 が trap」は、NC が OOM を伴う無 skip の survey だったため (無 skip の probe は qstore 有効でも idx 898 が OOM の Halt0: 実測)。
無 skip の survey では idx 898 は修復後も trap のまま (OOM, #513) = survey の ok の増分は idx 87 の +1 だけ。

## 5. ネガティブコントロール (受入条件 5) と実測 — `bash tools/m11/qstore/qstore_e2e.sh` (HEAD `46eb303`)
| 構成 | idx 87 (probe, skip) | idx 898 (probe, skip) | survey ok/trap/miss/noproc | 通常起動 units_run |
|---|---|---|---|---|
| NC: `M11_QSTORE=0` | trap (OOB) | trap (OOB) | 816 / 79 / 46 / 1 | 22 (main の `m11_e2e.sh`) |
| 修復: `M11_QSTORE=1` | ok | ok | **817 / 78 / 46 / 1** (unit 別の差は idx 87 のみ) | 22 (`m11_e2e.sh`) |

- 同一結果の再現: NC の survey 4 回 (main の `m11_e2e.sh` 1 + 単独 survey 1 + qstore_e2e 2) が全て 816/79、修復の survey 4 回 (qstore_e2e 2 + `m11_e2e.sh` 1 + 未コミット作業ツリーの `m11_e2e.sh` 1) が全て 817/78。
- 所要 / load average: qstore_e2e 126.9 s (開始 0.95 → 終了 1.33; gen_ir2 ×2 + build ×2 + probe ×2 + survey ×2 を含む)。`m11_e2e.sh` は main `6a0a8c8` が 66.8 s (gen_ir2 込み, 開始 0.58)、修復後 HEAD が 47.7 s (増分, 1.33 → 1.14)。
- `m11_e2e.sh` の reached_stage は 4/6 のまま (本修正は stage を進めない。stage 5 は #490 / #513 / #132)。

## 6. 検証範囲 / 範囲外・未解決
範囲: 上記の機械語突合・NC・probe。範囲外: `--full` 再生成、idx 87 / 898 以外の unit の意味的な正しさ、`machine_narrow` 140 件の個別検証。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 無 skip survey で idx 898 は OOM trap のまま (idx 101 が 1,477 MB 消費, idx 144 が InitTable を破壊) | survey の ok が +1 にとどまる | #513 (暴走 unit の特定・VA 巻き戻し) |
| 機械語 qword-imm store のうち IR に直接 store が無い 1,053 件 (alloca 無し 1,024 は SSA 昇格 / dead store 除去と推定のみ) | callee が lea 経由で読む slot なら別型の store 脱落 | #132 にコメント (全数監査の子チケットは PM 判断) |
| qstore は即値 store のみ。非定数の 4B 縮み (`store ptr %x` 等) は対象外 (reg 経由で 0 を 8B 書いていた 3 件は `fix_slot` で拾っただけ) | 非定数ポインタ store でも同型の縮みがありうる | #132 にコメント (D17 の検出信号拡張) |
| `fix_slot` 3 件・`machine_narrow` 140 件は機械語との 1:1 対応が無い (前者は書換え済み、後者は非書換え) | 後者に qword と dword が混在する slot があれば取りこぼし | 本 REPORT (個別未検証) |
| `alloca/m11_alloca.py` の `SZ['ptr']=8` は datalayout `p:32` (4B) と不整合 | 現 IR で 4B alloca への 8B 直接 access は 0 件 (実測: qstore 前の `store/load i64\|double\|i128`) なので実害なし | `alloca/REPORT.md` 残置 |
| AGENTS.md / WORKFLOW.md §4 の「D1〜D16」表記が D17 追加で古くなる | 表記のみ | PM が整合 |
