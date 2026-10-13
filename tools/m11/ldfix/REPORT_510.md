# #510 (LD-10): base が引数由来でない load→store (370 site / 169 関数) の判定軸と脱落数

**判定: 受入条件 1・4 達成、2 は「store 宛 192 site は確定、spill 宛 178 site は候補止まり」、3 は一覧化まで達成・起票は PM 依頼 (§8)**。
親 #130 / 先行 #484 (`tools/m11/ldfix/REPORT_484.md` §6 範囲外 (1))。検証起点 commit は §5。PR は `Refs #510` (Closes にしない)。

既知類型との関係 (`docs/DEFECTS.md`): **D4 (DEFECTS.md)** の変種。うち支配的な型 (86 site) は **新規類型案 D17 (§7)** =
rip 相対ポインタセルの 2 段 deref が 1 段に潰れる。`tools/icall/REPORT.md` §4 の D4 (別体系) とは無関係。

素材: `fl-win64` 無し (PE は無い)。入力は #484 と同じ `work-m11` (`boot_final3.ll`・`m11_image.bin`・`boot*.drc.config.json`) と、
動的差分の既存全数採点として `work-liftdiff` の `m11/batch_closure.jsonl` (読取のみ)。

## 1. 結論 (実測)

| 受入条件 | 結果 |
|---|---|
| 判定軸を小サンプルで実測して選ぶ | **達成 (§3)**: **SSA 対応の静的判定を選択**。liftdiff 動的差分は既知の脱落 8 関数のうち match 2 / unexec 3 と 5/8 で見えず、169 関数でも unexec 92 (54%) |
| 370 site / 169 関数の真の脱落数を確定 (独立再計算) | **store 宛 192 site は確定、spill 宛 178 site は候補止まり** (§4)。store 宛: **脱落 89 site / 51 関数** (目視 37 + 自動 52)、判定不能 2、正常 101。spill 宛: 目視 27 site 中 6 が脱落、oracle 候補 31 site / 18 関数は未確認 |
| 脱落があれば関数一覧を起票 | 一覧 = `results/drops_510.tsv` (126 行)。**起票は PM 依頼 (§8)** |
| ネガコン | **達成 (§6)**: 8 本 (NC0 基準 + NC1〜NC7) が全て期待どおり |

- 370 site の内訳 (定義: 機械語の `mov [m],rD` 命令 1 本 = 1 site。`mov rD,[rB]` (disp 0) の値が rD を壊さず store される形で、rB が argN に解決できないもの):
  **store 宛 (frame = rbp/rsp 以外) 192 / spill 宛 (`mov [rbp+X],rD`) 178**。base の由来 (store 宛 192): rip 相対セル 105 / lea 56 / 由来不明 12 / frame 6 / [reg+disp] 5 / sub 3 / 多段 deref 3 / call 戻り 2。
- **脱落の 97% (86/89 site) は一つの型**: 機械語 `mov rA,[rip+cell]; mov rD,[rA]` (cell = ポインタを入れた 8 バイトのグローバル) の 2 段 deref が、IR では
  `load iN, ptr inttoptr(cell の LVA)` の **1 段** になり、変数でなく **cell 自身** (ポインタ値) を読む (§2)。残り 3 site は base/定数 0 を書く従来型 (806820 ほか)。
- 副産物 (§5.3): **#484 の `audit_lsf.py` は偽陰性**があり、arg 解決済みなのに見落とした脱落が **14 site / 12 関数** (`ptrtoint` 別名の見落とし、load が定数 0 に化ける型ほか。§5.3)。

## 2. 新しい脱落型: rip 相対ポインタセルの 2 段 deref 潰れ (D17 案)

`525600` (`sub rsp,0x28 … 525619 mov rax,[rip+0x10befe0]; 525620 mov eax,[rax]; 525622 mov [rip+0x10cd028],eax`)。
- セル X = `0x525620 + 0x10befe0` = `0x15e4600`。image のセル内容 (reloc 済み LVA 座標) = **`0x11e60b4`** (実変数の LVA)。IR の定数アドレスは LVA = X − `0x400000` = `0x11e4600` (セル自身)。
- IR (`boot_final3.ll`): `%8 = load i32, ptr inttoptr (i64 18761216 to ptr)` (= `0x11e4600`)。正しくは `0x11e60b4` を読む 2 段 load。
- **段階の特定 (実測)**: `work/boot0.lift.ll` (RetDec stage-0 の出力) の `function_525600` が既に `%8 = load i32, ptr @global_var_15e4600` で 1 段。**RetDec 段で生じている**
  (525600 = boot0.lift.ll と 100be60 = boot3.lift.ll `%0 = load i32, ptr @global_var_15e3aa0` の 2 関数で確認。他関数の stage-0 は未確認)。
- 判定器: image の実データでセル内容 V を読み、IR の定数アドレス load に V があれば `FOLDED_OK` (RetDec の静的解決。正しい)、
  セル自身 K があれば `CELL_COLLAPSED`、それ以外 `CELL_DEEP` (2 段の連鎖が IR にある。正しい)。**`FOLDED_OK` は全数で 0 件** = 静的解決された例は無い。
- 実害の方向: 変数の値の代わりに **ポインタ値の下位ビット**が読まれる (flag/int/count/配列ポインタが誤値)。trap でなく silent に値が狂うため、動的差分では見えにくい (§3)。

## 3. 判定軸の選択: 静的 (SSA 対応) vs 動的 (liftdiff) — 実測

### 3.1 動的差分 (liftdiff `batch_closure.jsonl`: native vs wasm, 9 pattern × 7421 関数) の感度と被覆

出力: `dyn_xcheck.py` / `tally_510.py` [6]。**注意**: `batch_closure.jsonl` は 2026-10-10 08:54 生成、`boot_final3.ll` は同日 11:48 生成で、採点時の IR が現行と同一かは未検証 (弱い根拠)。

| 集合 | 関数数 | match | mismatch | unexec |
|---|--:|--:|--:|--:|
| #484 の既知 TRUE_DROP (感度の基準) | 8 | 2 (5c0270, 41a670) | 3 (66e080・7e5240・409c80) | 3 (806740・c62780・417b70) |
| base 解決不能 | 169 | 25 | 52 | 92 |
| 本 PR の脱落関数 (store 宛 51) | 51 | 5 | 18 | 28 |

- 既知 8 関数で**確実に脱落を指す**のは 409c80 (tag `spill_slot_deref`) の 1 本程度。5c0270 は 6 case `equal` で **match** と採点された。mismatch の 2 本 (66e080: `xmm_arg_drop`, 7e5240: `simd_helper`) は別原因のタグ。
- `unexec` = native が fault/hang で比較不能。169 関数の 54%、脱落関数でも 55% (28/51)。**動的方式は被覆と感度の両方が足りない**。

### 3.2 静的 (SSA 対応) の 3 層 + image oracle (`audit_lsf_ssa.py`)

機械語側は #484 の前向きデータフローに値の由来 (`rip-mem`/`lea`/`call-ret`/…) と deref 段数を足したもの (arg 解決 site の 90 / 解決不能 370 site / 169 関数は #484 と**一致**)。IR 側:
- **alg1 (関数単位の個数収支)**: `IR 内の「load 由来の値を store」行数 ≥ 機械語 LSF store 数` (幅別。spill 宛は除く)。load 由来 = 非 alloca の整数/ptr load、およびその cast・phi・select、reg2mem alloca を経由した値。
- **alg2 (site 単位の宛先照合)**: 機械語 store の (幅, disp) に合う IR store の値が load 由来か。
- **alg3 (deref 段数)**: 機械語の値の deref 段数 ≤ IR の値の load 入れ子 (reg2mem alloca は store 値の最大)。
- **cell oracle (§2)**: rip 相対セル経由の site を image の実データで判定。

目視判定 (§4.2) を正解として、store 宛 unk site 81 件 (脱落 37 / 正常 44) に対する各方式 (`tally_510.py` [3]):

| 方式 | TP | FP | FN | 感度 |
|---|--:|--:|--:|--:|
| alg2 (SUSPECT or NOCAND) | 5 | 29 | 32 | 5/37 |
| alg3 (SHALLOW or NOCAND) | 30 | 27 | 7 | 30/37 |
| **cell oracle** | **34** | **0** | 3 | **34/37** |
| alg3 SHALLOW のみ | 26 | 4 | 11 | 26/37 |
| **alg3 SHALLOW or cell oracle** | **35** | **4** | 2 | **35/37** |
| alg3 or cell oracle (NOCAND も含める) | 36 | 27 | 1 | 36/37 |

- alg2 単独は rip 相対セル型 (共通の「load 由来の値」を IR が持つので OK と誤判定) に弱い。**段数 (alg3) と image oracle が効く**。
- 既知 8 関数 (#484) への感度 (関数単位, alg1/2/3 の和): **7/8** (409c80 の 4B path のみ 3 方式とも見逃し。site 単位は 41a670 の 41a6d6 を alg1 のみが捉える)。
- NOCAND (IR に宛先形の store が無い) は FP が多い (スタックローカル宛で store が正当に消える)。「要目視」クラスとして使い、自動の脱落判定には入れない。

### 3.3 20 関数標本 (`random.Random(510).sample(169 関数, 20)`) での 3 者の比較

`tally_510.py` [5]。store 宛 site を持つ 10 関数と、spill 宛のみの 10 関数。

| 見るもの | 結果 |
|---|---|
| store 宛 site を持つ 10 関数: 目視で脱落 | 4 関数 (fe95a0・11d47c0・126e650・12e6720)。**静的は 4/4 を flag、残り 6 関数に flag 無し** (偽陽性 0) |
| その 4 関数の動的 verdict | unexec 3 / mismatch 1 (126e650) = **動的で脱落を見られたのは最大 1/4** |
| spill 宛のみの 10 関数 (目視 27 site) | 4 関数 (cf3790・f40840・ff8b60・100b890) に 6 site の脱落。cell oracle は 6 のうち 3 を捉えた (幅 64 の 2 段目は未検出) |
| 標本で脱落を持つ関数 | 8/20 (40%)。169 関数へ外挿すると約 68 関数 (推定。標本 20 の二項 95% 区間は約 19〜64%) — §4 の和集合 69 関数 (store 51 + spill 宛のみ 18) と整合 |

**選択: 静的 (SSA 対応) を主、動的は補助**。理由: 感度 35/37 (偽陽性 4) 対 動的は既知 8 で ≤3/8、被覆は 46% (unexec 54%)。動的は **修復後の回帰確認**
(修復した関数が unexec→match になるか) に使う。

## 4. 370 site / 169 関数の脱落数 (`tally_510.py`, 再現: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh`)

### 4.1 store 宛 192 site (確定)

最終判定 = 目視があれば目視、無ければ自動 (cell oracle = DROP / それ以外 OK):

| 判定 | 目視 | 自動 | 計 |
|---|--:|--:|--:|
| 脱落 (DROP) | 37 | 52 | **89 site / 51 関数** |
| 正常 (OK_LOAD / OK_ELIDED / 自動 OK) | 44 | 57 | 101 |
| 判定不能 (UNDETERMINED) | 2 | 0 | 2 (412680:412689 = 戻り番地の load が無関係な `store %arg2` に化ける別型。681760:681969 = load は IR に残るが store が消える) |

- DROP の型: cell 型 **86 site**、その他 3 site。DROP 関数 51 本の一覧は `tally_510.txt` [2]。
- **自動 52 site の確からしさ**: cell oracle が flag した store 宛 site のうち目視済みは 34 件で **TP 34 / FP 0** (§3.2。うち 14 件は残りの未確認 66 件からの無作為抽出 (seed 5100) で 14/14 脱落)。
- **自動 OK 57 site の取りこぼし (推定)**: 目視済み 81 site で「alg3 SHALLOW or oracle」の FN は 2 (ea8210・11d47c0:11d4ad4)。未 flag の目視済み 42 site 中 2 = 4.8% を未確認 57 site に当てると約 3 site (偏った標本からの推定。区間は広い)。

### 4.2 目視判定 (独立再計算の主柱)

subagent 7 本 (読取専用) が、機械語のデータフロー × IR を読み、site ごとに TRUE_DROP / OK_LOAD / OK_ELIDED / UNDETERMINED を判定。計 126 行 (`results/manual_verdicts_510.jsonl`、各行に機械語・IR の引用つき)。
G1〜G4 = alg2 が OK でない site 全部 (+ OK でも疑わしい数件)、G5 = 標本の残り関数の store 宛全 site (flag 無しも含む)、G6 = spill 宛 27 site の消費者、G7 = 自動判定の無作為抽出 + 55d810。
自動判定の誤り: 55d810:55d8e0 (alg3 SHALLOW だが IR は 2 段 load を正しく持つ。OK_LOAD)。
目視と自動の食い違いは全て本 REPORT の数値に反映済み (cell oracle の NOCAND 扱いは、目視 1311a2f の誤判定を受けて「幅 64 は SHALLOW 確定時のみ」に修正)。

### 4.3 spill 宛 178 site (候補止まり)

spill 宛 (`mov [rbp+X],rD`) の store は IR から消えるのが普通で、脱落は後続の消費者 (call 引数・cmp・算術・別 store) に現れる。
- cell oracle (幅 64 以外の load でセル自身を読む形のみ) が flag: **37 site / 22 関数**。目視済み 27 site の消費者判定: **TRUE_DROP 6 (4 関数)**、OK_LOAD 16、NO_CONSUMER 5 (死んだ値 1 + 別欠陥 4)。
  oracle は目視の脱落 6 のうち 3 を捉え、flag 6 のうち 3 が脱落 (適合率 50%)。
- 目視で確認できていない oracle 候補: **31 site / 18 関数** (`drops_510.tsv` の `source=candidate`)。cf3790 の `[rax-8]` による配列長取得など、幅 64 の 2 段目は oracle が見ない (FN)。
- したがって「370 site の真の脱落数」は **store 宛 89 site (確定) + spill 宛 ≥6 site (確認済) + 候補 31 site (未確認)**。関数の和集合は **69 / 169 関数** (store 宛 51 + spill 宛のみで加わる 18 = 目視確認 4 + 候補のみ 14)。

## 5. 検証

### 5.1 独立再計算
- **機械語側の列挙**: `window_recount.py` (データフロー無しの「同一基本ブロックで load→同幅 store」窓) の 420 対が全て audit_lsf_ssa の 460 site に含まれる (含まれない 0)。
  窓版 420 対のうち 219 が store 宛 (データフロー側 store 宛 230)。差の 40 site は reg コピー/spill 経由でしか繋がらない。
- **IR 側の判定**: 目視 (§4.2) が別算法。静的 3 方式の間の食い違いは §3.2 の表。
- 自己検査: `audit_lsf_ssa.py` の arg 解決 site 90 / 解決不能 370 / 169 関数は `audit_lsf.py` の `lsf_sites` 90 / `lsf_unresolved_base_sites` 370 / `fns_with_unresolved_base` 169 と一致 (e2e 1〜2/6)。

### 5.2 所要・再現性
検証起点 commit = `f02e846` (スクリプト・results 一式。以降の commit は REPORT・DOC_MAP・`audit_lsf_ssa.py` の docstring・`audit_lsf_ptrtoint_check.py` のみで、判定ロジックは無変更)。
コミット済み HEAD の worktree (`ws-510`) で `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (`M11_WORK` / `LD_WORK` = work-m11 / work-liftdiff の展開先、`PY` = capstone 入り venv、並列数 1) を **n=3**:
所要 **154 / 157 / 157 s** (min–max 154–157 s)、終了時 load average (1 分値) 0.97 / 1.13 / 1.20 (4 core、他に重い処理なし)。3 回とも rc=0・標準出力が **byte 一致**、
`tally_510.py` の出力と `drops_510.tsv` はコミット済み `results/` と一致 (e2e 5/6 が `cmp` で確認)。
個別実測 (各 1 回): `audit_lsf_ssa.py` 単体 14.0 s、`window_recount.py` 9.4 s、`negctl_510.sh` 113.4 s。目視判定 (§4.2) は subagent の読取結果をファイル化したもので、e2e は再実行せず突合のみ。

### 5.3 #484 `audit_lsf.py` の偽陰性 (副産物)
- 原因 1: `ir_stores` の別名に `ptrtoint ptr %argN to i64` が無い (`m11` の署名修復で引数が `ptr` 型になった関数。`%21 = ptrtoint ptr %arg1 to i64; store i64 %21`)。ここだけ直すと SUSPECT は **8 → 12 関数** (15 site。増分 412160・418700・de4120・10077a0。再現: `python3 audit_lsf_ptrtoint_check.py IR IMG CFG` 1 回実測、e2e には含めない)。10077a0 は本ツールでは OK (未目視)。
- 原因 2: 脱落が `store %argN` でなく **定数 0** (`xor i64 0,0`) や、無関係な値の store に化ける型 (c3ed10・ddde50・1064ed0)。
- 本ツールの目視で、arg 解決済みなのに #484 が SUSPECT にしなかった TRUE_DROP は **14 site / 12 関数**: 101d180・1064ed0・412160・418700・47a540・47b260・666a60・821370・a1edc0・c3ed10・ddde50・de4120。
  `audit_lsf.py` 本体は無改変 (REPORT_484 の数値の再現性を保つ)。

## 6. ネガティブコントロール (`negctl_510.sh`, 基準 = `alg1_fns=26 alg2_fns=38 alg3_fns=77 cell={COLLAPSED 123 (store 宛 86 + spill 宛 37), DEEP 85}`)

| 壊し方/直し方 | 期待 | 実測 |
|---|---|---|
| NC1 5c0270 の脱落 store 2 本に load を足す | 5c0270 の 2 site が OK、alg1 対象 −1 | alg2 SUSPECT 20→18、alg1 26→25、5c0270 の deficit 2→0 |
| NC2 100be60 (alg2 では OK の関数。D17 の脱落関数でもある) の store 値を `trunc %arg2` に差し替える | 100be69 が SUSPECT、alg1 +1 | alg2 OK→SUSPECT、alg1 26→27 (deficit 0→1) |
| NC3 image の 5c0270 区間を nop | 5c0270 の site が消える | lsf SUSPECT 20→18、列挙から消滅 |
| NC4 ablation `--no-alloca-prop` | 偽陽性候補が増える | alg1 26→31、alg2 38→42 (alloca 経由の由来伝播が要る) |
| NC5 525600 の cell 1 段 load を 2 段 load に直す | CELL_COLLAPSED −1 | 123→122、525622 は alg3 OK / CELL_DEEP |
| NC6 525600 の load を image のセル内容 V (0x11e60b4) 直読みにする | FOLDED_OK に動く | CELL_COLLAPSED 123→122 + FOLDED_OK 1、525622 = FOLDED_OK |
| NC7 52a750 (CELL_DEEP) の 2 段 load を cell 自身の 1 段 load に壊す | CELL_COLLAPSED +2 | 123→125 (DEEP 85→83)、52a7a8 / 52a7b1 とも alg3 SHALLOW / CELL_COLLAPSED |

## 7. 検証範囲 / 範囲外 / DEFECTS.md 行案

- 範囲: `work-m11` 時点 (2026-10-10 生成) の `boot_final3.ll` 7421 関数。IR・wasm は無変更 (`tools/m11` の既存ファイルは無変更。本 PR は `tools/m11/ldfix/` と DOC_MAP のみ)。
- 範囲外 (弱い主張): (1) spill 宛 178 site は消費者の追跡が目視 27 site 止まり。(2) 幅 64 かつ宛先が IR で照合できない site (ea8210) は oracle が見ない。(3) PE (fl-win64) 無しのため `FOLDED_OK` の根拠は image のセル内容のみ。実行時にセルへ書き込まれる変数 (例: 52a750 のセルは image 内容 0 = 実行時設定) では image 内容 V による FOLDED_OK 判定は成立しない (その型は CELL_DEEP として扱われ、脱落判定に入らない)。
  (4) 動的差分は既存 `batch_closure.jsonl` の再解析で、新規実行はしていない (PE が無く不可)。(5) 修復 (IR パッチ) は未実施 = wasm の再ビルド・survey も未実行。
- **DEFECTS.md 行案 (編集は PM 判断)**: `D17 | fe (RetDec stage-0) | 新規 (#510) | rip 相対ポインタセル (mov rA,[rip+cell]; mov rD,[rA]) の 2 段 deref が 1 段に潰れ、変数でなくセル自身 (ポインタ値) を読む | stage-0 の boot*.lift.ll で既に @global_var_<cell> の 1 段 load (525600・100be60 で確認) | store 宛 86 site / 49 関数 (spill 宛 oracle 候補 37 site / 22 関数を含む和集合は 67 関数)。image のセル内容 V ≠ IR の読み先 (FOLDED_OK 0 件) | 機械語の rip 相対 qword load の直後の deref × IR の定数アドレス load の幅・段数 (audit_lsf_ssa.py の cell oracle) | 2 段 load (cell を load ptr → deref) への IR 修復 pass`。
  D4 (DEFECTS.md) の観測例にも「arg 解決済みで定数 0 / 無関係値になる変種 (c3ed10・ddde50・1064ed0)」を追記する案。

## 8. 未解決 (起票依頼)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| D17 の IR 修復 pass (store 宛 89 site / 51 関数 + spill 宛 候補 31 site)。一覧 = `results/drops_510.tsv`。修復後の受入条件 = `audit_lsf_ssa.py` の CELL_COLLAPSED 0 と、動的差分での unexec→match 確認 | silent に変数値が狂う。#130 の halt0/trap の一部原因の可能性 | 新規子チケット (`[LD-n]`/`[M11-n]` は PM 採番)。または #LD-9 に統合 |
| #484 の 8 関数 + 本調査で見つかった arg 解決済み 12 関数 (§5.3) の IR 修復 | 5c0270 以外は IR が誤ったまま | #484 の起票依頼 (新規子チケット) に 12 関数を追記 |
| `audit_lsf.py` の偽陰性 (ptrtoint 別名・定数 0 型) | #484 の数値 (8 関数 / 11 site) が過小 | #484 にコメント。本体の修正は別 PR で REPORT_484 の数値と併記 |
| spill 宛 178 site の消費者追跡 (call 引数・cmp・算術・return) | 目視 27 site 止まり。候補 31 site 未確認 | 上の子チケットに含める。D4 の consumer 形 (F1〜F3) の全数監査として |
| 動的差分の再採点 (PE 取得時) | 本 PR の動的比較は既存 `batch_closure.jsonl` の再解析のみ | `oc_artifacts: fl-win64 ...` を付けた再実行。D17 修復後の回帰確認に使う |
| 目視中に見つかった別欠陥: swap 条件に ucomiss でなく整数 cmp のフラグを使う (6bed60・dd5a80・6be960。D1a (DEFECTS.md) 類)・vtable 間接 call 脱落 (de10c0 `de12e5`・55d810 `55d88c`。D15 (DEFECTS.md))・load が定数 0 化 (45e3c0 `45e3cc`)・callee へ渡す record の store 欠落 (cf3790 `cf398c`・f40840・126cad0)・d28b00 の修復パスが VA 形式 (22952608) の定数を混入 (LVA 18758304 と 0x400000 ずれ) | いずれも D17 とは別 | 該当 REPORT へのコメント。d28b00 の定数は ldfix の F 系 pass の起票へ |
| stage-0 の他関数での D17 の有無 | 段階の特定が 525600・100be60 の 2 関数のみ | 上の子チケットで全数確認 |

## 9. 成果物 (`tools/m11/ldfix/`)

| パス | 役割 |
|---|---|
| `audit_lsf_ssa.py` | 非 arg base を含む LSF 全 site の列挙 + alg1/alg2/alg3 + cell oracle。`--json` で site 詳細、`--no-alloca-prop` で ablation |
| `window_recount.py` | 機械語側 site 列挙の独立再計算 (データフロー無し) |
| `audit_lsf_ptrtoint_check.py` | #484 `audit_lsf.py` の ptrtoint 偽陰性の影響測定 (§5.3) |
| `site_dump.py` | 関数ごとの「機械語 + IR + site 一覧」ダンプ (目視用) |
| `dyn_xcheck.py` / `tally_510.py` | 動的差分 (batch_closure.jsonl) との突合 / 目視判定との突合・最終集計 |
| `negctl_510.sh` / `audit_lsf_ssa_e2e.sh` | ネガコン 8 本 / 1 コマンド再現 |
| `results/audit_510_ssa.json` / `manual_verdicts_510.jsonl` / `drops_510.tsv` / `tally_510.txt` | site 詳細 / 目視判定 126 行 / 脱落一覧 / 集計出力 |
