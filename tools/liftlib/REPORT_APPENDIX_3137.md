# liftlib #3137 — `legacy_p1` の残留分岐 (br_other 17 / no_branch 49) の D1a 同型判定

- 既知類型との関係: **D1a** (`docs/DEFECTS.md`)。残留のうち 13 件は **D1a 同型** (整数比較の折畳み形)、残り 4 + 49 件は **非同型** と判定した。
- 親: #3067 (CLOSED・PR #3098 MERGED・`origin/main` に修正あり)。本件は [LIFTLIB-22] (#3137)。書換えの実装は子 #3899 (LIFTLIB-24) (本 PR では行わない)。
- 担当 dir: `tools/liftlib/`。`liftlib/passes/p1_legacy.py` は変更していない。
- 入力: `tools/m6/work/ott_lift.ll` (`work-m6-ott` 素材の展開・挿入前の OTT lift IR)。
- **測定 commit (コードを変えた最後の commit)**: `2c46d6481` (`feat(liftlib): p1_repmap_census --residual で残留分岐を分類する (#3137)`)。以後は REPORT のみ。
  `git diff 2c46d6481 HEAD -- tools/liftlib/liftlib tools/liftlib/p1_repmap_census.py` = **0 行**。

## 1. 判定 (IR 上の静的判定。機械語とは未照合)

| 区分 | 件数 | 判定 |
|---|---|---|
| D1a 同型: `br_other` で、分岐条件の依存連鎖の葉が comis より前に定義 (間に関数呼出しなし) | **12** | 同型 (stale) |
| D1a 同型の疑い: 上と同じだが、間に `function_…` 呼出しが 1 件 (L6802) | **1** | 未確定 (callee がフラグを変えるか IR では決まらない) |
| 非同型: `br_other` で葉が全て comis より後 (comis 後の整数比較がフラグを作る) | **4** | 非同型 (fresh) |
| 非同型: `no_branch` で、窓の外の最初の分岐が comis 後の整数比較 | **15** | 非同型 (fresh) |
| 非同型: `no_branch` で、フラグを読む前に後続の comis がある | **32** | 非同型 (読まれない) |
| 非同型: `no_branch` で、関数末まで分岐が無い | **2** | 非同型 (読まれない) |

- 合計 84 = 実 call の comis 数 (census の `sites` 94 は宣言行 `declare void @__asm_comis…` 10 行を含む。`parse_call` が通らず census は数えない)。
- D1a 同型 13 件 (うち 1 件は判定保留) は、census の窓の書換えでも `br_named` でも拾えない。RetDec は comis で `@cf/@zf/@pf` を更新しないため、comis の後の jcc が、comis より前の整数 `cmp`/`test` のフラグを読む。LLVM が後者を `icmp` に畳んだので、名前参照 (`cf.N`) の検出器からは見えない。

## 2. 分類の手順 (`p1_repmap_census.py --residual`)

1. 窓 (comis 直後 13 行) は census と同じ規則で、最初の分岐・`or`・次の void asm 呼出しを探す。
2. `br_other` (cf/zf/pf の名前参照でない分岐) は、条件の定義を `icmp … i1` / `or|and|xor i1` で葉まで辿る。葉の定義行が comis より前なら stale、全て後なら fresh。
3. stale の場合、comis と分岐の間に `call … @function_…` または `@__asm_add|sub|cmp|test|and|or|…` (フラグを更新し得る呼出し) があれば `stale_call`、無ければ `stale_clean`。
4. `no_branch` は、窓の外で最初に現れる「分岐・次の comis・関数末」で分類する。分岐なら 2〜3 と同じ。

## 3. 実測 (commit `2c46d6481` の `--residual`)

```sh
cd tools/liftlib && python3 p1_repmap_census.py                  # 修正後の census (変化なし)
cd tools/liftlib && python3 p1_repmap_census.py --residual        # 残留の分類
```

- census (既存の指標・不変): `{"entries": 19, "br_applied": 17, "or_applied": 1, "double_pct": 0, "br_residual": 1, "diff_lines": 18, "diff_removed": 19, "diff_no_pc": 0}`
- `--residual`: `{"sites": 84, "br_named": 17, "br_other.fresh": 4, "br_other.stale_call": 1, "br_other.stale_clean": 12, "no_branch.beyond_br_fresh": 15, "no_branch.fn_end": 2, "no_branch.next_comis": 32, "or_named": 1}`

## 4. 代表例 (IR の確認)

- **D1a 同型 (stale_clean)**: L11595 `call void @__asm_comisd(i128 %3, i128 %48)` → L11596 `%49 = or i1 %44, %42` → L11597 `br i1 %49`。`%42 = icmp ult i64 %38, …` (L11588)・`%44 = icmp ne i64 %43, 0` (L11590) は comis より前。間の呼出しは `__asm_por`・`__asm_xorpd` のみで、フラグを変えない。jbe (cf∨zf) が comis 前の整数フラグを読んでいる。
- **判定保留 (stale_call)**: L6802 `call void @__asm_comisd` → 間に `call i64 @function_1801c0d00()`・`call i64 @function_1801aa1a0(…)` → L6811 `br i1 %53` (`%53 = icmp eq i1 %44, false`, `%44` は L6798 の `icmp eq i1 %43, false`, `%43 = icmp sgt i64 %15, -1`)。callee の最後のフラグ更新が分岐に効く可能性があり、IR だけでは決まらない。
- **非同型 (fresh)**: L6907 `call void @__asm_vcomisd` → L6908 `%99 = icmp ult i64 %59, …` → L6909 `br i1 %99`。分岐のフラグは comis の後の整数比較 (非同型)。
- **非同型 (next_comis)**: L1672 `call void @__asm_comiss` の後は `br label` を挟んで L1688 の `call void @__asm_comiss`。L1672 のフラグは L1688 の前に読まれない (L1689 の分岐は L1688 の comis のフラグを扱う)。

## 5. 修復に残る問題 (子 #3899 (LIFTLIB-24))

- 折畳み形 13 件の書換えには、jcc の種類 (je/jne/jb/jae/ja/jbe…) を決める規則が要る。葉の `icmp` の述語 (`eq/ne` → zf, `ult/uge` → cf, `ugt/ule` → cf∨zf 系) から導ける見込みだが、本 run では規則を実装・検証していない。
- 書換えは comis の位置に `%pcN…` のフラグを作って、stale の連鎖だけを差し替える必要がある。葉の値は他の分岐でも使われるため、葉を直接書き換えてはならない。
- 検証は `tools/liftlib/liftlib_e2e.sh`・`tests/test_unit.py`・SHA gate (#3145 と同じ outhash) が要る。本 run では時間内に収まらないため行わない。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 折畳み形 D1a 13 件 (stale_clean 12 + stale_call 1) の書換えと再測定 | OTT P1 出力で、comis 後の分岐が前の整数比較のフラグで決まる (silent) | 子 #3899 (LIFTLIB-24) (親 #3137) |
| `REPORT_APPENDIX_3067.md` §3.2 の SHA gate (outhash) 未判定 | 修正後の OTT 出力の SHA 基準 | #3145 (既存) |
| 機械語との突合 (13 件の分岐が実際に comis のフラグを読むか) | 静的判定の確度 | 子 #3899 (LIFTLIB-24) の受入条件 |
