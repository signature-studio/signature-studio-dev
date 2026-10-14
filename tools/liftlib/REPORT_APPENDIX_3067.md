# liftlib #3067 — `legacy_p1` の repmap が挿入前の行番号で登録され、分岐の書換えが 0/19 件しか当たらない

- 既知類型との関係: **D1a (P1 同型)** (`docs/DEFECTS.md`)。comis 後の jcc が直前の comis 由来の cf/zf を使う欠陥の対策 (`fcmp`: CF=lt∨uno, ZF=eq∨uno, PF=uno) が OTT の legacy P1 で効いていなかった。
- 親: #2863 (`[PLG-F3-32]` p1_legacy の IR 一致ゲート)。本件の修正は #2863 の本 PR (#2947) では直さず、本 issue で行う (issue 本文の判断どおり)。
- 担当 dir: `tools/liftlib/`。`tools/m6/` (RetDec 路線・D5 凍結) は読取のみ。
- 測定 commit (コードを変えた最後の commit): **`81adaffa`**。修正前の基点: `origin/main` `718e90fb`。
- コード差分の確認 (差分 0 の証跡は本付録の commit 後に取る): `git diff 81adaffa HEAD -- tools/liftlib/liftlib tools/liftlib/tests tools/liftlib/liftlib_e2e.sh tools/liftlib/p1_repmap_census.py`

## 1. 原因 (2 点)

`tools/liftlib/liftlib/passes/p1_legacy.py` の `legacy_p1`:

1. **行番号のずれ**: repmap は挿入前の行番号 `j` で登録されるが、適用は挿入後の `out[j]` に対して行われていた。挿入した行数の分だけずれ、書換えが当たらない (issue 本文の実測 0/19 を再現)。
2. **`%%pc` の生成**: 旧名は `%` 無し (`cf.N`) で登録され、新名は `%pcNcf` (`%` 付き) である。`str.replace` で置換すると `%%pcNcf` になり、仮に行がずれていなくても不正な IR になる。

修正: repmap を挿入前の原行 `lines[j]` に適用してから挿入する。旧名は `%` 付き・後続文字の境界付き (`(?![\w.\-])`) で置換し、`cf.1` が `cf.18` に当たらないようにする。

## 2. 受入条件 1: 置換対象 19 組の適用 (実測)

入力: `tools/m6/work/ott_lift.ll` (挿入前の OTT lift IR, 25,338 行)。再現: `cd tools/liftlib && python3 p1_repmap_census.py [--module <旧 p1_legacy.py>]`

| 指標 | 修正前 (`718e90fb`) | 修正後 (`81adaffa`) | 期待 |
|---|---|---|---|
| entries (repmap の組数) | 19 | 19 | 19 |
| `br i1 %pcN<cf\|zf\|pf>` (書換え後) | 0 | **17** | br 系 17 |
| `or i1 %pcN.., %pcN..` の行 | 0 | **1** (2 組) | or 系 1 行 |
| `%%pc` | 0 | 0 | 0 |
| 書換えで残る `br i1 %<cf\|zf\|pf>.N` | 18 | **1** | 1 (下記) |
| difflib: 変更行数 | 0 | **18** | 18 (br 17 + or 1) |
| difflib: 変更行から消えた旧名トークン | 0 | **19** | 19 |
| difflib: 変更行で `%pc` を含まない行 | 0 | 0 | 0 |

- 修正前は `%pc` へ 1 件も書き換わらない (0/19 の再現)。修正後は 19 組すべてが適用される。
- 残る 1 件は `dec_label_pc_1801c966f` の分岐 (`%zf.1 = icmp eq i8 %2, 0` 直後)。`icmp` 由来で comis 挿入の窓 (直前 13 行) の外にあるため、対象外の分岐 (修正前から残る)。
- 挿入した定義が分岐を支配するか: 窓 (comis 行 → 分岐行) の間にラベル行が 0 件 (書換え 17 件すべて同一基本ブロック内)。
- 負の対照: 修正前のコード (`--module` に `718e90fb` 版) で `br_applied=0`・`diff_removed=0` となり、検出器が書換えの有無を区別することを確認。

## 3. 受入条件 2: e2e の結果 (実測)

測定: `bash tools/liftlib/liftlib_e2e.sh --quick` (load avg 0.55 / 0.77 / 0.53、所要 35〜40 秒・regress 内 32〜37 秒)。

| 項目 | 修正前 `718e90fb` | 修正後 `81adaffa` (参照は元のまま) | 修正後 + 参照再生成 (work/ のみ) |
|---|---|---|---|
| unit T2 (p1_legacy == `ir7e_p1/p2/p3.ll`) | PASS | **FAIL** (AssertionError: 参照は修正前の出力) | PASS |
| fa_gain / kh_gain (BIT-EXACT) | PASS (400/400, 366/366) | PASS (同) | PASS (同) |
| ott (既定 auto f7,p1) | PASS (census junkHi 104 ≤ 104) | PASS (同) | PASS (同) |
| ott_auto_none: IR 一致 O2a〜O4 | 6 件 不一致 (既存・#2863) | 6 件 不一致 (同じ) | 同じ 6 件 不一致 |
| ott_auto_none: 出力 SHA (vs m10 参照) | equal true・42/42 (f0 21/21, distinct 40) | **equal false** (f0 3/21, distinct 34) | equal false (同) |
| 全体 | FAIL | FAIL | FAIL |

- **修正前の全体も FAIL** (`ott_auto_none` の IR 一致 O2a〜O4 が #2863 由来で既に不一致)。修正により新たに落ちるのは unit T2 と SHA gate。
- **参照再生成** (work/ のみ・コミットしない): `ir7e_p1.ll`・`ir7e_p2.ll`・`ir7e_p3.ll` を修正後の `legacy_p1` で作り直した。元の参照との差は 3 本とも 36 行 (変更 18 行)。R2 の `work-m6-ott` は未更新のため、CI の再取得では旧参照に戻る (§6 の未解決 1)。
- **O2a〜O4 の不一致の原因は `%pc` 番号のみ** (修正の影響ではない): `ott` は `dump(strip=True)` で空行を除いた IR を入力にするため、`%pc<行番号>` の番号がずれる (空行除去 #1664 後の既知事象・#2863)。`work/ott/ott_lift.ll` を入力にした `legacy_p1` の出力は、`%pc\d+` → `%pcN` 正規化後に参照と一致 (True・生の比較は False)。

### 出力 census (`--auto none` の OTT 出力・修正前後)

| param=0x248 の振幅 | 修正前 normal / junkHi / absmax | 修正後 normal / junkHi / absmax |
|---|---|---|
| 0 | 69 / 175 / 1.67e20 | **140 / 104** / 1.67e18 |
| 1 | 254 / 252 / 1.13e36 | 258 / 248 / 1.13e34 |

- 既定 auto (`ott`) の census は修正前後で同一 (normal 140 / junkHi 104 / [1] normal 259・junkTiny 1)。
- 解釈 (推定): D1a の対策で junk 出力 (junkHi・absmax) が減った。方向は一致するが、**native 実機との一致は本測定では判定していない** (§6 の未解決 4)。

## 4. 受入条件 3: DEFECTS 類型の判定

- **D1a 同型 (既知)**。根拠: 修正後の書換えは `docs/DEFECTS.md` D1a の対策式そのもの (`cf = lt ∨ uno`・`zf = eq ∨ uno`・`pf = uno`、`p1_legacy.py` の `cf`/`zf`/`pf` 定義)。書換え対象は comis 直後 13 行の `br` と `or` で、D1a の検出信号「`__asm_(u)comis*` の後続 jcc の br 条件が comis 由来でない」に該当していた。
- 新しい類型は見つからなかった。`%%pc` 生成は同じ repmap 適用の不具合で、本件に含めて直した。

## 5. 再現

```sh
cd tools/liftlib
python3 p1_repmap_census.py                          # 修正後 (HEAD)
python3 p1_repmap_census.py --module <旧 p1_legacy.py> # 修正前 (git show 718e90fb:tools/liftlib/liftlib/passes/p1_legacy.py)
bash liftlib_e2e.sh --quick                          # 約 35 秒
```

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `tools/m6/work` の参照 IR (`ir7e_p1/p2/p3.ll`) と m10 SHA 基準 (42/42) は修正前の P1 出力。R2 `work-m6-ott` を再投入するまで、CI の `liftlib_e2e --quick` は T2 と SHA gate が FAIL のまま | e2e が FAIL のまま。参照は work/ のみで commit 不可 | PM / 依頼者 (`docs/WORKFLOW.md` §11 の R2 再投入) |
| O2a〜O4 の IR 一致 FAIL (`%pc` 行番号) | 修正前から FAIL。正規化すると一致 | #2863 (既存・PR #2947 が gate で正規化) |
| `tools/m6/ir6_pass.py` (vendored) に同じ repmap の欠陥。RetDec 路線 (D5 凍結) のため未修正 | m6 路線の出力は修正前と同じ | #2863 へのコメント (既存) |
| 修正後の OTT 出力 (SHA 3/21 f0) の正しさは native 実機と未照合 | SHA gate の基準を新しい出力へ置き換える判断が必要 | PM 判断 (#3067 の完了コメント) |
