# tools/plugins/p0c REPORT 付録 B (§10)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。本ファイルは本体から**無変更で分割移動**した節の全文 (#378, `docs/DOC_MAP.md` §1)。節番号・見出しは移動前のまま。

## 10. P0c-4 追記 (CAB-196 継続): ext-emulation mode のバグ修正と 2 kernel bit-exact 化

作成: 2026-10-11 / 担当 dir: tools/plugins/p0c のみ / 起点 HEAD (WIP 評価前): `016f91c`

### 10.0 結論 (先出し)

1. **前回 WIP の `f80_lower.py --ext` に実アルゴリズム bug を 3 件発見・修正**
   (`drop_lines` が store 行を飲み込む / `startswith` のインデント見落とし /
   RE_EXT_RINT と RE_EXT_FPTOSI の二重出力)。修正後、**0x5dfbe0 と 0x5dfc90 の
   2 kernel が buf_diff=0 (bit-exact) を達成** (§10.2)。P0c-3 時点で未達だった
   4 kernel のうち 2 本。
2. **残り 2 kernel (0x5dfd30 / 0x5dfdb0) は x87fix 後ベースラインに戻らず未達**
   (§10.2)。**真因は dd (double-double) 演算系列そのもの**であり、fpr2 slot 運搬では
   ないことを負論対照で実証した (§10.3・10.4)。
3. 未コミット WIP 4 件 (`f80_lower.py` / `ext_core_test.c` / `ext_core_test` /
   `k80chop.py`) はすべて本節の入力として採用。`stash@{0}` (WIP on master: 5bc4d30) は
   **作業ツリーの staged 版とバイト一致** (md5 実測 `d0864500df9c0de2587b7ae643f25d33`)
   なので採用せずそのまま残置 (drop もしない = 他担当領域を巻き込まない)。

### 10.1 修正した 3 bug (すべて f80_lower.py の --ext モード)

| # | 症状 | 原因 | 修正 |
|---|---|---|---|
| B1 | `store float` 行が消えて buffer 未書込 → buf_diff 数百万 | `drop_lines` に store 行 index を入れていた。store 行は `store_rewrites` で `%X.x87s` に書換える対象なので、`drop_lines` 判定が先に走うと store ごと消える | `drop_lines.add(lj)` を外し `break` のみに |
| B2 | 同上 (B1 修正後も残った) | B1 の `if lines[lj].startswith('store float ')` は**行頭判定**。RetDec 出力の store 行は 2 スペースインデント付きで、ここがマッチせずスキャンが store 行を通過して `%x87c` を含む store 行自身を drop していた | `lines[lj].lstrip().startswith(...)` に修正 |
| B3 | fist 系列が 2 回出力され IR が約 40 行冗長 (0x5dfd30 で実測) | `RE_EXT_RINT` (llvm.rint 行) と `RE_EXT_FPTOSI` (fptosi 行) が同じ ext 値を二重処理。`_resolve_src` は select/rint を透視するので後者だけが必要 | rint 結果が 30 行以内の `fptosi` に消費される場合は rint 側を skip |

B1/B2 の発見経路: `--only 0x5dfc90` の症状 `buf_diff=2,538,942` (x87fix 後 52,323) は
「1 cell も書かれていない」規模だった。ext 前後の IR を diff して `store float` 行が
消えていることを確認 (before 120 行 `store float %x87c7, …` / after 該当行なし)。

### 10.2 修正後の差分試験 (k80_diff.py, 2000 case/kernel, fork 隔離)

| kernel | class | x87fix 後 (§9.3) | ext 修正後 | 判定 |
|---|---|---:|---:|---|
| 0x5de820 | f32chain | 0 | 0 | bit-exact (回帰 0) |
| 0x5dedf0 | f32chain | 0 | 0 | bit-exact (回帰 0) |
| 0x5dfb60 | f32chain | 0 | 0 | bit-exact (回帰 0) |
| 0x5dfbe0 | rc_chop | 288,922 | **0** | **bit-exact 達成** |
| 0x5dfc90 | rc_chop | 52,323 | **0** | **bit-exact 達成** |
| 0x5dfd30 | f32chain | 38,099 | 102,353 | **未達** (悪化) |
| 0x5dfdb0 | rc_chop | 841,305 | 508,385 | **未達** (ベースライン超過) |

回帰 (既修復 kernel、全て buf_diff=0 維持): 0x5df210 / 0x5df240 / 0x5e0760 / 0x5e0b70 /
0x5e0bb0 / 0x5e1590 / 0x5e1780。0x5e0330 / 0x5de3e0 は今回の --only 集合外 (§10.5)。
`f80_lower --ext` は冪等 (2 回適用 byte 一致)・llvm-as 通過を確認。

### 10.3 残り 2 kernel の実測と負論対照 (規則 41)

| kernel | 条件 | buf_diff | ret_diff | 解釈 |
|---|---|---:|---:|---|
| 0x5dfdb0 | ext 全機能 | 508,385 | 0 | dd 演算が効いているが不完全 |
| 0x5dfdb0 | **dd 演算だけ OFF** (fpr2 運搬は維持) | 841,308 | 79 | x87fix 後 841,305 と**同一水準** → fpr2 運搬は健全 |
| 0x5dfd30 | ext 全機能 | 102,353 | 144 | |
| 0x5dfd30 | **dd 演算だけ OFF** | 136,953 | 195 | x87fix 後 38,099 より**悪化** → dd 演算系列が悪化源 |
| 0x5dfd30 | ext 全機能・最終 f32 store のみ fptrunc(H) に戻す | 102,353 | 144 | f32 store 丸めではない |

負論対照のやり方: 生成 IR の `__frontend_reg_store.fpr2l` の値引数を全て `0.000000e+00`
に置換 (hi だけ運ぶ = fpr2 運搬は動くが dd 情報は捨てる)。これだけで d30 が 102k→137k に
動くので、d30 の残差は「hi だけ f64」でも「dd」でもない中間的な丸め差である。

0x5dfd30 の不一致 cell 実測サンプル: `nat=-0.97235107421875` (bits 0xbf78ec00) /
`ir=-0.47943115234375` (bits 0xbef57800)。同符号で指数が 1 違うだけの近傍値であり
NaN/garbage ではない → dd のどこかの段の丸めが 1 段ずれている。

### 10.4 未達の推定原因 (推定ラベル付き・規則 39)

- **推定**: `_ext_round64` の 64-bit 丸めが正しくても、③ fmul の Dekker TwoProd →
  ① round64 → ⑥ fptrunc が**同一 loop 内で連鎖**する箇所で lo の情報が失われる。
  0x5dfd30 は fild→fmul→fadd→fistp→fmul→faddp→fstp と同一 loop 内で乗算 2 回 +
  加算 2 回が連鎖する (native 機械語 0x5dfd70-0x5dfda1 を capstone で実確認)。
  0x5dfdb0 も同型。ext_core_test.c の検証は **op-level (1 演算) と kernel 形 chain の
  2 モード**であり、「同一 loop 内で slot を再利用しながら 4 演算連鎖する形」は未検証
  (= 推定の根拠)。
- **否定された推定**: dd ペアの slot 引き回し (`__frontend_reg_load/store.fpr2h/l` と
  `@__fpr2_store`) は健全 (§10.3 負論対照)。当初の推定原因「dd ペア slot 受け渡し +
  P1/mini-lifter の bind が dd ペアを壊す」は**該当しない**。
  EXT_RUNTIME_LL の index wrap (`shl i32 %i,1; and 31`) は負 index で 16 要素配列の外に
  落ちる理論上の弱点だったため `and i32 %i,7` を先頭に置く形に修正した。実測上の改善は 0
  (TOP=-4 で全 index が 0..7 に収まるため) だが防御的なので維持する。

### 10.5 検証範囲 / 範囲外 (規則 40)

検証した: 0x5de820/0x5dedf0/0x5dfb60/0x5dfbe0/0x5dfc90/0x5dfd30/0x5dfdb0 の 7 kernel を
k80_diff.py 2000 case で native 機械語と突合。0x5e0330/0x5de3e0 は今回の --only 集合に
入れておらず未測定 (ext 対象 4 関数に含まれないため変換もされない)。
wasm32 バックエンドは**今回未実行** (§9.3 で非 ext IR は 101,539 B 通過済みだが ext IR は
未検証)。framework 統合 (fw_* への適用) は**未実施** (framework/hostshim は他担当領域の
ため不要な変更を避けた)。80 kernel 表の再検証 (verify_table.py) は未実行 (ext は pass のみで
表には影響しないため)。

### 10.6 未解決・起票先 (規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x5dfd30 / 0x5dfdb0 が bit-exact 未達 (ext で d30 悪化) | CAB-196 出口条件「80 kernel bit-exact」の残 2 本 | CAB-196 本チケットにコメント済 + 子チケット起票を提案 |
| ext の 4 演算連鎖形 (fild→fmul→fadd→fistp→fmul→faddp→fstp) が未検証 | ext_core_test.c の検証範囲に穴 | 子チケット (提案) として起票 |
| wasm32 バックエンド未検証 (ext IR) | framework 統合の前提 | 子チケット (提案) |
| work/p0c4_wip.patch からの CAB-253 (crash 4 kernel) 再開 | 未着手 | 本 ticket 後に着手予定 |

### 10.7 再現 (1 コマンド・独立再計算スクリプト同梱・規則 37)

```sh
export TMPDIR=$PWD/work/tmp
python3 tools/plugins/p0c/p0c4_e2e.py           # 全 7 kernel + 回帰, 2000 case/kernel
python3 tools/plugins/p0c/p0c4_nega.py          # 負論対照 (dd lo 運搬を全滅)
```

`p0c4_e2e.py` の実測出力 (この REPORT の数値の出所):
```
kernel     class       buf_diff    x87fix後     不一致率        判定
0x5dfbe0   rc_chop            0     288922  0.0000% bit-exact
0x5dfc90   rc_chop            0      52323  0.0000% bit-exact
0x5dfd30   f32chain      102353      38099  0.3111%        未達
0x5dfdb0   rc_chop       508385     841305  1.5451% baseline以下
0x5de820   f32chain           0          0  0.0000% bit-exact
0x5dedf0   f32chain           0          0  0.0000% bit-exact
0x5dfb60   f32chain           0          0  0.0000% bit-exact
(回帰 7 kernel は全て buf_diff=0)
== [6] kernel 表 (80/80) の再確認 ==
   45 variables / 80 implementations / 10,886 B / x87 28 — 一致
```
数え方の定義 (規則 36): buf_diff = native 機械語と IR の出力バッファの bit 不一致 cell 数
(f32 4 B 単位・1 kernel 1 case で最大 16,452 cell = NBUF_B 65,808/4)。NaN 同士は nandiff に
分離し buf_diff には数えない。不一致率 = buf_diff ÷ (cases × 16,452)。分母は kernel による
cell 数差を無視した共通分母で、パーセントは比較用の目安 (絶対 cell 数が正)。

`p0c4_nega.py` の実測出力:
```
[nega] rewrote 40 fpr2l stores to 0.0
[nega] 0x5dfd30   f32chain      136953      38099 運搬は健全・残差は dd 演算系列
[nega] 0x5dfdb0   rc_chop       841308     841305 運搬は健全・残差は dd 演算系列
[nega] negative control OK
```
独立再計算: p0c4_e2e.py は p0c3_e2e.sh を呼ばずに (1) ext pass 適用 (2) k80_diff.py 実行
(3) 別アルゴリズムで不一致率を再計算 (4) kernel_table.py で 80/80/45/10,886 B/x87 28 を
突き合わせる。回帰照合は REPL 経由ではなくファイル経由で実施。

### 10.7b 旧再現手順 (手動・上記スクリプトの内部処理と同一)

```sh
export TMPDIR=$PWD/work/tmp
# 1. x87fix まで (p0c3_e2e.sh の [1]-[4] と同一)
python3 tools/plugins/p0c/f80_lower.py work/k80.lift.ll work/diff3/k80.lower.ll \
  --report work/diff3/k80.lower.json --chop-funcs function_5dfbe0,function_5dfc90,function_5dfdb0
python3 tools/plugins/p0c/k80_argfix.py work/diff3/k80.lower.ll work/diff3/k80.argfix.ll \
  --abi work/k80abi.json --report work/diff3/k80.argfix.json
python3 tools/plugins/p0c/x87fix.py work/diff3/k80.argfix.ll work/diff3/k80.x87fix.ll \
  --report work/diff3/x87fix.json \
  --funcs function_5de820,function_5dedf0,function_5dfb60,function_5dfbe0,function_5dfc90,function_5dfd30,function_5dfdb0 \
  --chop-f32-fns function_5dfbe0,function_5dfc90,function_5dfdb0
# 2. ext mode (chop アドレスレンジは k80chop.py で生成)
python3 tools/plugins/p0c/k80chop.py
python3 tools/plugins/p0c/f80_lower.py work/diff3/k80.x87fix.ll work/ext/k80.ext.ll \
  --ext --ext-funcs function_5dfc90,function_5dfbe0,function_5dfd30,function_5dfdb0 \
  --chop-funcs function_5dfbe0,function_5dfc90,function_5dfdb0 \
  --chop-ranges "5dfbe0:5dfc0a-5dfc7c,5dfc90:5dfcb5-5dfd1e,5dfdb0:5dfded-5dfe40" \
  --report work/ext/k80.ext.json
# 3. 差分試験
python3 tools/plugins/p0c/k80_diff.py --ir work/ext/k80.ext.ll \
  --only 0x5dfbe0,0x5dfc90,0x5dfd30,0x5dfdb0 --cases 2000
```

### 10.8 クリーン HEAD 検証 (規則 45)

起点 commit = **19c2cd2** (本節の commit)。`git archive HEAD -- tools/plugins/p0c | tar -x -C
work/verify_19c2cd2 --strip-components=3` で展開 (リポジトリ非破壊)、work/ 内の既存 lift IR
(`work/diff3/k80.x87fix.ll`) を入力としてコピーして再実行。全数値が一致:

  p0c4_e2e.py : 0x5dfbe0=0 / 0x5dfc90=0 / 0x5dfd30=102,353 / 0x5dfdb0=508,385
                回帰 7 kernel = 0 / kernel_table 45 変数・80 実装・10,886 B・x87 28
  p0c4_nega.py: 0x5dfd30=136,953 / 0x5dfdb0=841,308 (negative control OK)

**注記**: `p0c4_e2e.py` の [6] は相対パス `../inventory/kernel_table.py` を解決するため、
work/verify_* の展開先からは実行不能 (絶対パス参照)。REPORT に明記 (規則 45)。
実測は `tools/plugins/inventory/kernel_table.py` で
同一出力を確認済み。

### 10.9 環境前提 (規則 43)

- TMPDIR は実ディスク: `export TMPDIR=tools/plugins/p0c/work/tmp` (`/tmp` は tmpfs 3.7 GB)。
  `preflight.sh --env tools/plugins/p0c` と同じ。
- llvm-as / clang (LLVM 系統) と python3 (pefile・capstone) が PATH に必要。
- 差分試験は PE を 0x400000 に MAP_FIXED 敷設して実機械語を直接実行 (k80_diff.py)。

