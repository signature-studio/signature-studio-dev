# liftlib #3067 — `legacy_p1` の repmap が挿入前の行番号で登録され、分岐の書換えが 0/19 件しか当たらない

- 既知類型との関係: **D1a (P1 同型)** (`docs/DEFECTS.md`)。修正対象の 19 組 (分岐 17 + or 1 行の 2 組) は D1a 同型。残留の分岐 (§4) は **未判定**。
- 親: #2863 (`[PLG-F3-32]` p1_legacy の IR 一致ゲート・**CLOSED**)。本件の修正は #3067 で行う。残留は子 #3137 (`[LIFTLIB-22]`)。
- 担当 dir: `tools/liftlib/`。`tools/m6/` (RetDec 路線・D5 凍結) は読取のみ。
- 修正前の基点: `origin/main` `718e90fb`。**main 取り込み**: merge `15d01f87` (origin/main `4b81e78a`)。
- **測定 commit (コードを変えた最後の commit)**: `c8316dc7` (`fix(liftlib): align T2/T26 with pre-fix reference and run all unit tests (#3067)`)。以後の commit は REPORT のみ。

## 1. 原因 (2 点) と差分の確認

`tools/liftlib/liftlib/passes/p1_legacy.py` の `legacy_p1`:

1. **行番号のずれ**: repmap は挿入前の行番号 `j` で登録されるが、適用は挿入後の `out[j]` に対して行われていた。挿入した行数の分だけずれ、書換えが当たらない (issue 本文の実測 0/19 を再現)。
2. **`%%pc` の生成**: 旧名は `%` 無し (`cf.N.reload`) で登録され、新名は `%pcNcf` (`%` 付き)。`str.replace` で置換すると `%%pcNcf` になる。

修正: repmap を挿入前の原行 `lines[j]` に適用してから挿入する。旧名は `%` 付き・後続文字の境界付きで置換する。

差分 (測定 commit 以降、記録時点 HEAD = 本 REPORT の親 commit):
`git diff c8316dc7 HEAD -- tools/liftlib/liftlib tools/liftlib/tests tools/liftlib/liftlib_e2e.sh tools/liftlib/p1_repmap_census.py` = **0 行**。
(main 取り込みで変わった `p1_legacy.py` の 18 行は main 由来の `canon_tags` (#2863) で、本件の修正ではない。)

## 2. 受入条件 1: 置換対象 19 組の適用 (実測 @ `c8316dc7`)

入力: `tools/m6/work/ott_lift.ll` (挿入前の OTT lift IR, 25,338 行)。再現: `cd tools/liftlib && python3 p1_repmap_census.py [--module <旧 p1_legacy.py>]`

| 指標 | 修正前 (`718e90fb`, PR 本文の実測) | 修正後 (`c8316dc7`) |
|---|---|---|
| entries (repmap の組数) | 19 | **19** |
| 書換えの br (`br i1 %pcN<cf\|zf\|pf>`) | 0 | **17** |
| 書換えの or 行 (2 組) | 0 | **1** |
| `%%pc` | 0 | **0** |
| 書換えで残る `br i1 %<cf\|zf\|pf>.N` | 18 | **1** (窓外・`icmp` 由来、修正前から残る) |
| difflib: 変更行 / 消えた旧名トークン / `%pc` を含まない変更行 | 0 / 0 / 0 | **18 / 19 / 0** |

- 修正前は `%pc` へ 1 件も書き換わらない (0/19 の再現)。修正後は 19 組すべてが適用される。
- 残る 1 件は `dec_label_pc_1801c966f` の分岐。窓 (comis 直後 13 行) の外。
- 書換え 17 件は、comis 行から分岐行までの間にラベル行が 0 件 (同一基本ブロック内)。
- 負の対照: 修正前のコード (`--module` に `718e90fb` 版) では `br_applied=0`・`diff_removed=0` となり、検出器が書換えの有無を区別する。

## 3. 受入条件 2: unit と e2e の結果 (実測 @ `c8316dc7`)

### 3.1 単体テスト (`python3 tests/test_unit.py`・所要 159.7 秒・load avg 0.6)

結果: `ALL UNIT TESTS PASS (27)`。終了コード 0。各テストの結果:

T1 ok / T2 ok (修正前参照との差は repmap 18 行のみ・inserts=18 shift=38 gdata=400) / T3 ok / T4 ok / T5 ok / T6 ok / T7 ok / T8 ok / T9 ok / T10 ok / T11 ok / T12 ok / T13 ok / T14 ok / T15 ok / T16 ok / T16b ok / T17a ok / T17b **skip** (`LL_XRET_LL`/`LL_XRET_DLL` 未設定) / T18 ok / T19 ok (Serum2 PE 無しで add_func は skip) / T20 ok / T21 ok / T22 ok / T23 ok / T24 ok / T25 ok / T26 ok (改名 18 種・修正前参照との差は repmap 18 行)。

- ランナーの変更: 失敗があっても全テストを実行し、失敗を最後に一覧表示する (`FAIL n/27: ...`)。終了コードは失敗があれば 1。**失敗経路は本 run では未実測** (全件 PASS のため)。
- T2・T26 の前提: 修正前参照 (`tools/m6/work/ir7e_p*.ll`) との差は repmap の 18 行だけ (`repmap_delta`)。参照は work/ のみで commit 不可。R2 (`work-m6-ott`) 再投入で参照が修正後になったら `==` の完全一致に戻す。
- T26 は、参照に依らず修正後の出力同士で「空行除去による改名の不変性・ネガ (ult→ule) の検出・写像の一意性と単射」を検査する。

### 3.2 `bash tools/liftlib/liftlib_e2e.sh --quick` (`c8316dc7`・全体 3 分 28 秒・rc=1)

| 項目 | 結果 (実測) |
|---|---|
| (0) unit | PASS (27/27・上記) |
| fa_gain (BIT-EXACT) | PASS (400/400 steps・400 scenarios) |
| kh_gain (BIT-EXACT) | PASS (366/366 steps・61 scenarios) |
| ott (既定 auto f2,f7,p1) | PASS (census junkHi 104 ≤ 104・e2e checks 8 / broken 0) |
| ott_auto_none: IR 一致 | O1 true / **O2a・O2b・O2c・O3a・O3b・O4 false** |
| ott_auto_none: 出力 SHA | **未判定** (下記) |
| ott_auto_none | **FAIL** |

- IR 不一致 6 件の内訳: 修正前参照との差 (repmap 18 行) と、既存の `%pc` 行番号差 (#2863 の既知事象)。gate 側の比較は `canon_tags` で改名を無視する (T26 で確認)。repmap 18 行は改名では消えないため、参照再投入まで不一致になる。
- **SHA 突合は未判定** (起票先: #3145)。1 回の run で 2 モジュール × 42 組合せ (約 7 分/モジュール・PR 本文の実測) を走らせる必要があり、残り時間に収まらなかった。加えて、`node tools/liftlib/recipes/ott_outhash.mjs` の出力が JSON でなく失敗した (`outhash 実行失敗: Expecting value`・原因は未切り分け)。参照 `tools/m10/work/ott_m10.cjs` は `work-m6-ott` 素材から展開して用意した (`.wasm` は未展開)。
- 参考 (前回測定・`81adaffa`・PR 本文の表): 修正前 `718e90fb` は SHA 42/42 (f0 21/21)、修正後 `81adaffa` は 3/21 (f0)。`c8316dc7` では再測定していない。修正後の値が正しいかは native 実機と未照合 (§6)。
- 全体 3 分 28 秒 (総計・unit 込み)。regress 部分は 46.5 秒 (初回) / 22.0 秒 (キャッシュ後の再実行)。

## 4. 受入条件 3: DEFECTS 類型の判定

- **修正対象の 19 組: D1a 同型 (判定済み)**。根拠: 修正後の書換えは `docs/DEFECTS.md` D1a の対策式そのもの (`cf = lt ∨ uno`・`zf = eq ∨ uno`・`pf = uno`、`p1_legacy.py` の定義)。書換え対象は comis 直後 13 行の `br` と `or` で、D1a の検出信号「`__asm_(u)comis*` の後続 jcc の br 条件が comis 由来でない」に該当していた。
- **修正対象外の残留: 未判定** (`c8316dc7`・`stats.hits`):
  - `br_other` **17 件**: comis 直後の窓 (13 行) 内の最初の `br i1 %N` が cf/zf/pf の名前参照でない (条件値は `%28` 等の番号 SSA 値)。
  - `no_branch` **66 件**: 窓内で書換え対象が 0 件。うち 17 件は `br_other` と重なる (`br_other` で break して repl が空になるため両方に計上される)。残り **49 件**は窓 13 行内に br/or が無い (`__asm_comisd` 25・`__asm_comiss` 11 ほか)。
  - D1a 同型かどうかは本 PR では判定していない。起票先: **#3137** (`[LIFTLIB-22]`・親 #3067)。

## 5. 再現

```sh
cd tools/liftlib
python3 p1_repmap_census.py                           # 修正後 (HEAD)
python3 p1_repmap_census.py --module <旧 p1_legacy.py> # 修正前 (git show 718e90fb:tools/liftlib/liftlib/passes/p1_legacy.py)
python3 tests/test_unit.py                            # 約 160 秒 (T1〜T26)
bash liftlib_e2e.sh --quick                           # 約 3.5 分 (unit 込み)
```

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 参照 IR (`ir7e_p1/p2/p3.ll`) と m10 SHA 基準 (42/42) は修正前の P1 出力。R2 `work-m6-ott` を再投入するまで、T2・T26 は repmap 18 行の差を許容し、ott_auto_none の IR 一致 O2a〜O4 は不一致のまま | 参照は work/ のみで commit 不可。再投入後に `==` へ戻す | PM / 依頼者 (`docs/WORKFLOW.md` §11 の R2 再投入) |
| 残留分岐 (`br_other` 17 / `no_branch` 49) の D1a 同型判定と対策 | 修正対象外。件数は §4 | #3137 (`[LIFTLIB-22]`・子) |
| SHA 突合 (outhash) が `c8316dc7` で未判定 (node の JSON 出力の失敗・1 回約 14 分) | 修正後 OTT 出力の SHA gate が未判定 | #3145 (`[LIFTLIB-23]`・子。親 #3067 の受入条件から外した) |
| 修正後の OTT 出力 (SHA 3/21 f0 @ `81adaffa`) の正しさは native 実機と未照合 | SHA gate の基準を新しい出力へ置き換える判断が必要 | PM 判断 (基準差し替えは既定で行わない) |
| `tools/m6/ir6_pass.py` (vendored) に同じ repmap の欠陥。RetDec 路線 (D5 凍結) | m6 路線の出力は修正前と同じ | PM (D5 凍結の判断・新規作業なし) |
