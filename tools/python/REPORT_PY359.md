# PY-359 (#4703): py88 式の手計算照合 (G8 の 2 地点)

親: #4696 (PY-355)。前段: `REPORT_PY41_APPENDIX.md` (PY-64・PY-88 節)・`REPORT_PY159.md`・`REPORT_PY161.md`。親 #3101 (PY-161) の受入 1 の残り。

## 1. 結論 (`Closes #4703`・親 #3101 の受入 1 は残り)

- #4703 の受入 (G8 の 2 地点 0x104c51a・0x104c56d の py88 式の手計算照合・mismatch 0): **達成**。既存の式文法で手計算式と一致した。
- 親 #3101 の受入 1 (G2〜G6・G8 の 11 地点の py88 式の手計算照合): 残りは G2〜G6 の **9 地点** (0x104aba9・0x104ad2e・0x104af7f・0x104b093・0x104b305・0x104b5aa・0x104b94e・0x104bebf・0x104bffa)。分岐合流・`shl`/`imul`・`CALL`・配列添字を含み、この run では式を確定できなかった → 子 PY-360 (#4712)。
- 受入 2 (不一致があれば VA と手計算式を書く): **不一致 0**。手計算式を確定できた地点はすべて機械式と一致した。

## 2. 測定

- 測定 HEAD: `ed462de49` (main 取り込みの merge。`tools/python/analysis` の最後のコード変更)。load average 0.90 (1 分平均・測定開始時)。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (`oc_artifacts: fl-win64`) から `block00031_PE.bin` を展開。`tar --zstd -xf ... --wildcards '*block00031_PE.bin'` 2.428 秒 (real)。
- 逆アセンブル: `python3 analysis/py53_dispatch.py work/py64/extracted/block00031_PE.bin work/py53` → `fn=4664 dispatch=13 r8d_tests=174` (0.082 秒 real・exit 0)。
- 突合: `python3 analysis/py64_check_expr.py work/py53/fn.txt` → `# n=8 mismatch=0 ACC?⚠合流 (機械側・ACC と同一視) = 4`・exit 0 (0.031 秒 real。HAND 6 点 + G8 2 点)。
- ネガティブコントロール: `--negctl p2` → exit 1 (修正前の 2 段の P は不一致になる。既存どおり)。
- 機械式の全件: `python3 analysis/py88_writes.py work/py53/fn.txt 0x104aba9 0x104ad2e 0x104af7f 0x104b093 0x104b305 0x104b5aa 0x104b94e 0x104bebf 0x104bffa 0x104c51a 0x104c56d` → 11 件とも式が出た。0x104c56d は印なし。0x104c51a は `ACC?⚠合流@0x104c3f6` を含み、それ以外の 9 件は SLOT?・CALL・ACC?⚠合流 のいずれかを含む。
- 測定 commit: `ed462de49` (コードを変えた最後の commit)。鮮度: `git diff ed462de49 HEAD -- tools/python/analysis` の出力は 0 件。旧測定 commit `53b9e3a73` からの差分は main 取り込み分 (329 行・`tools/python/analysis` 内の他 PY の変更) で、G8 の式の照合 (`py64_check_expr.py`) には影響しない。

## 3. G8 の手計算 (一致)

| VA | store | 手計算式 | 機械式 | 判定 |
|---|---|---|---|---|
| 0x104c51a | `mov [rbp+0x5b8], ecx` | `*(*(*(0x15e14a0))+0x808)` を基準とした F 式 (`*(p+0x3b8) + rint(*(0x104ccd8) · ACC · (*(p+0x3bc) − *(p+0x3b8)))`) | 同一 (ACC は `ACC?⚠合流@0x104c3f6` を ACC と同一視) | 一致 (ACC の値は未照合) |
| 0x104c56d | `mov [rbp+0x5b8], eax` | `*(*(0x15e3290))` | `M32[M64[G[0x15e3290]]]` | 一致 |

0x104c51a の基準ポインタ鎖は `0x104c4af`〜`0x104c4c0` で `[rip+0x594fea]`→`[rax]`→`[rax+0x808]` を `[rbp+0x398]` に保存し、`0x104c4f2`〜`0x104c512` でその `[rbp+0x398]` を読む。ACC (`[rbp+0x5b8]` の書込み前の値) は 0x104c3f6 で合流し、その値は本 run では照合していない (`py64_check_expr.py` の方式どおり ACC と同一視)。

## 4. 未確定 9 地点 (子 PY-360 へ)

| VA | 未確定の原因 |
|---|---|
| 0x104aba9 (G2) | `SLOT[rbp+0x574]` (`shl`/`and` 由来)・`ACC?⚠合流@0x104a9cd`・`SLOT[rbp+0x578]` |
| 0x104ad2e (G2) | `imul`・`SLOT[rbp+0x578]`/`[rbp+0x574]` の配列添字 |
| 0x104af7f (G3) | `SLOT[rbp+0x574]`・`ACC?⚠合流@0x104ad34` |
| 0x104b093 (G3) | `imul`・配列添字 `[rbp+0x574]*8` |
| 0x104b305 (G4) | `CALL[0x10469f0]` の戻り値 (ecx = `ACC?⚠合流`) |
| 0x104b5aa (G4) | `SLOT[rbp+0x3e0]`・`SLOT[rbp+0x580]` (`0x104b2aa` で `[rbp+0x580]` を `mov` で定義) |
| 0x104b94e (G5) | `SLOT[rbp+0x578]`・`SLOT[rbp+0x580]` (`0x104b744`)・`imul` |
| 0x104bebf (G6) | `SLOT[rbp+0x3b0]` (`0x104bd61` の `mov [rbp+0x3b0],rax` の値 `[rax+rcx*8]`)・`ACC?⚠合流@0x104b954` |
| 0x104bffa (G6) | `SLOT[rbp+0x568]`・`SLOT[rbp+0x580]`・`imul`・`shl` |

この run では式を確定していない。残り 9 地点は子 #4712 (PY-360) へ移す。SLOT 解決の道具は #2874 (PY-99) の `py99_slot_paths.py` に既にある (使えるかは PY-360 で確認する)。

## 5. 再現

```
cd tools/python
mkdir -p work/py64 work/py53
tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py64 --wildcards '*block00031_PE.bin'
python3 analysis/py53_dispatch.py work/py64/extracted/block00031_PE.bin work/py53
python3 analysis/py64_check_expr.py work/py53/fn.txt          # n=8 mismatch=0・exit 0
python3 analysis/py64_check_expr.py work/py53/fn.txt --negctl p2   # exit 1
```

## 6. PY-4909 (#5800): SLOT・CALL の展開を突合に接続 (0x104b305 の 1 地点)

親 #5313 の 5 地点のうち、0x104b305 (G4) だけを機械照合に接続した。

- 展開: `analysis/py99_slot_paths.py` に `ExpSlicer` と `expand()` を追加した。py88 の式の `SLOT[rbp+X]?` は、届く store が 1 件・入口へ届かない・到達不能なしの 3 条件を満たすときだけ、その store の値で置き換える。`CALL[0x10469f0]` は `edx + rint(M64[G[0x1046a20]] · ecx · (r8d − edx))` (`py99_call10469f0.py` で PASS 済みの式) に置き換える。
- 0x104b305 の展開結果: `(0 + rint(M64[G[0x1046a20]] · (d_in)@0x1046d6b · (0x3e80 − 0)))@0x104b300`。未解決印は 0。
- 手計算の式: `0 + rint(*(0x1046a20) · d_in · (0x3e80 − 0))`。`ecx` は `[rbp+0x5b8]` の読み (0x104b2f2) で、届く store は `0x1046d6b` の 1 本だけ (機械側の到達定義 `analysis/py160_reach.py work/py53/fn.txt` で `0x104b2f2` → `{0x1046d6b}`・`stores=1`)。`d_in` は入口の edx。範囲 0x104b099〜0x104b2f2 に `[rbp+0x5b8]` の書込みは無い。この範囲の 3 件 (0x104b0cf・0x104b16b・0x104b1e1) は `mov edx/r8d, dword ptr [rbp + 0x5b8]` の読みである。最も近い書込み 0x104b093 (`mov dword ptr [rbp + 0x5b8], eax`) が届かない理由: 0x104b2f2 の入口 0x104b1fd へ飛ぶ枝は 0x104ab1d の `jb` だけで、0x104b099 以降の枝 (0x104b0a4・0x104b0b1・0x104b132・0x104b14d・0x104b188・0x104b19d) はいずれも 0x104b1fd・0x104b2f2 に入らず、0x104caae へ抜ける。`edx` は 0x104b2f8 の `xor` で 0 になるため、式の `edx` は 0。
- 突合: `analysis/py64_check_expr.py` の `expanded_check()` で 0x104b305 を比べた。`mismatch=0`。ネガティブコントロール (手計算式の `d_in` を定数 `0x3e80` に置換) では `mismatch=1`・関数の戻り値 1。
- 注意: 手計算の `d_in` と機械側の `d_in` は同じ記号の名前一致で、値の一致は示していない (入口の edx が `0x1046d6b` の store で `[rbp+0x5b8]` に入る、という関係の手計算による確認まで)。機械側の展開が正しいかの独立検算は未了。

残り 4 地点 (0x104b5aa・0x104b94e・0x104bebf・0x104bffa) は展開しても `SLOT`・`…` (深さ上限) が残る。分岐を越える経路を手で追う必要があり、本 run では式を確定していない。親 #5313 の本文に残す (新しい子 issue は作らない)。

## 7. RMW store の式化 (PY-5399 / #5904・#5312 の単位 A)

- 対象: 直前の store が同じスロットへの ARITH の RMW (`shr dword ptr [rbp+0x31c], 0x10` at 0x104aaae) のとき、`py88_writes.py` の `mem_read` は `SLOT[rbp+0x31c]?` で止まり、`py99_slot_paths.py` の `store_value` は `OP:shr` を返していた。
- 変更: `py88_writes.Slicer.rmw_expr` を追加し、分岐合流がないときは RMW 直前の値 `op(prev, imm)` を式にする。`py99_slot_paths.store_value` も同じ `rmw_expr` を使う。コミット `53ab89b54`。
- 測定 commit: `53ab89b54` (コードを変えた最後の commit)。入力: `work/py53/fn.txt` (`fl-win64` の `block00031_PE.bin`・`py53_dispatch.py` で 4664 命令)。
- 0x104aaa8〜0x104aacd の式 (修正後): `0x104aaae` の store は `0x10`、`0x104aabe` は `shr(shr((SLOT[rbp+0x5b0]?@0x1046d65 - 0x70000000), 0x10), 6)`、`0x104aacd` は `and(shr((SLOT[rbp+0x5b0]?@0x1046d65 - 0x70000000), 0x10), 0x3f)`。`SLOT[rbp+0x31c]?` は式に残らない。
- 残る `SLOT[rbp+0x5b0]?@0x1046d65` は RMW とは別件 (入口の edx 相当の store 1 件への SLOT 参照)。本 PR の範囲外。
- 既定 65 件 (`py88_writes.py`): 修正前後で差は 0x1049f24 の 1 行のみ (`SLOT[rbp+0x570]?`・`SLOT[rbp+0x564]?` の RMW 連鎖の式化)。対象 11 件 (G2〜G8) は変わらず。
- py99 の突合 (修正前 → 修正後): `py99_slot_paths.py` 既定: `U n=55 match=55 mismatch=0; forward n=170 mismatch=0` → `U n=57 match=57 mismatch=0; forward n=172 mismatch=0`。`reads` は 170 → 172。mismatch は 0 のまま。
- 受入条件の `U n=6 match=6`・`forward n=14` は再現できなかった。0x104aaa8〜0x104aacd の 4 点を対象にすると `U n=3 match=3 mismatch=0; forward n=6 mismatch=0` (修正後)。修正前は `U n=0`・`forward n=4` (読みは全部 T)。`U n=6`/`forward n=14` の対象集合は issue に書かれていないため、ここでは同じ数字を作れていない。
- 依存スクリプトの出力差 (修正前 → 修正後・`py99_closure.py` 既定): 閉じた frame 葉の SLOT? 104 → 100・X の種数 24 → 23。`py99_merge_sets.py` は 49 件のまま、mismatch 0。
- 依存スクリプトの突合 (修正後): `py64_check_expr.py` `n=8 mismatch=0`・展開版 `expanded n=1 mismatch=0`・`py159_check_hand.py` 一致・`py163_vcall.py` 全件一致・`py161_movabs_check.py` `mismatch=0`。
- 実時間: `py88_writes.py` 4 点 0.02 秒・`py99_slot_paths.py` 既定 0.35 秒。load average 0.25 (`uptime`・測定直前)。
- 未解決: 4 地点 (0x104b5aa・0x104b94e・0x104bebf・0x104bffa) の展開は本 PR の範囲外 (既存の未解決として §6 の残り 4 地点と同じ)。

## 8. G2・G3 の 4 地点の手計算照合 (PY-5400 / #5905・#5312 の単位 B)

- 文法: `py64_check_expr.py` の `TOKEN`・`Parser` に `shl(` `imul(` `and(` `shr(` (1〜2 引数の関数形)・`c_in`・`,` を加えた。`machine_norm` は `&M64[`/`&M8[` の `&` を落とす。
- 手計算式 (展開版 `EXPANDED`): 0x104aba9・0x104af7f は `F` 型 (`[P+0x3b8] + rint(*(0x104ccd8) · d_in · ([P+0x3bc] − [P+0x3b8]))`)、0x104ad2e・0x104b093 は表引き (M8 型・M32 型)。`c_in` は入口の ecx (0x1046d65 の store)、`[rbp+0x574]`・`[rbp+0x578]` は 0x104aacd・0x104aabe の式 (`and(shr(X,0x10),0x3f)`・`shr(shr(X,0x10),6)`、X = c_in − 0x70000000)。
- 測定 commit: 本 PR の code commit (`tools/python/analysis/py64_check_expr.py`)。入力: `work/py53/fn.txt` (`fl-win64` の `block00031_PE.bin`・`py53_dispatch.py` で 4664 命令)。
- 結果 (実測): `python3 analysis/py64_check_expr.py work/py53/fn.txt` → 既存 HAND 8 点 `mismatch=0` (受入 1 を満たす)。展開版 `expanded n=5 mismatch=4`・exit 1。

| VA | 結果 | 原因 |
|---|---|---|
| 0x104aba9 (G2・F 型) | 不一致 (parse error) | base は py88 の 400 字上限 (`py88_writes.py` の `res[:400]`) で式が `…` に切れ、parse error。上限を 4000 にした scratch では py64 の展開照合が一致する (下の「再現手順」の 2 行目)。py88 の上限修正が必要 (#5926) |
| 0x104af7f (G3・F 型) | 不一致 (parse error) | base は 0x104aba9 と同じ `…` で parse error。上限を 4000 にした scratch では一致する。py88 の上限修正が必要 (#5926) |
| 0x104ad2e (G2・M8 型) | 不一致 | py88 の `ARITH` は 2 オペランドのときだけ源を出す。`imul rcx, rcx, 0x28f` (3 オペランド) が `imul((…)*8)` になり 655 (0x28f) が落ちる。手計算式は 655 を保持 |
| 0x104b093 (G3・M32 型) | 不一致 | 0x104ad2e と同じ (`imul` の 0x28f 欠落) |

- 手計算式の確からしさ: 0x104ad2e の `imul` を落とした形の手計算式は機械式と一致しないままだった (`hand-without-0x28f == mach` が False)。0x104aba9 は展開の `…` を超えて比べられない。このため手計算式そのものの正しさは本 run では確定していない。
- 不一致の VA と手計算式: 上の 4 点。受入 3 (不一致があれば VA と手計算式を REPORT に書く) を満たす。
- 未解決の追跡 (本 PR の範囲外): (1) `py88_writes.ARITH` の 3 オペランド `imul` の源欠落、(2) `resolve()` の 400 字上限による `…` 切れ (0x104aba9・0x104af7f)、(3) py88 の生の出力に `SLOT?`・`ACC?⚠合流` が残る (ExpSlicer 経路では照合を妨げない。上限 4000 の scratch の py64 出力に `SLOT` は 0 件)。(1)(2) は `py88_writes.py` の修正になり、py88・py99 の既存測定値 (§6・§7・REPORT_PY99 系) が動く。子 #5926 で扱う。

#### 再現手順 (§8 の `…` 検証・測定 commit `c9430d6a2`)

scratch は `work/scratch/` (gitignore) に複製し、本体は変えない。結果は 2 経路で分けて書く。

- (a) py88 の生の出力 (`py88_writes.py` を直接実行): 本体 (変更なし) の 0x104aba9・0x104af7f は `…` 0 件・`SLOT?` 6 件。上限 4000 (`sed -i 's/if len(res) > 400:/if len(res) > 4000:/; s/res\[:400\]/res[:4000]/'`) でも、`DEPTH_LIMIT` を外す (`sed -i 's/if depth > DEPTH_LIMIT:/if depth > 10**6:/'`) でも `…` 0 件。`SLOT?` は残る。
- (b) py64 の展開照合 (`py64_check_expr.py work/py53/fn.txt`、ExpSlicer を通る):
  - 本体: `n=8 mismatch=0`・`expanded n=5 mismatch=4`・exit 1。0x104aba9・0x104af7f の機械式に `…` が入り、未解決 `['…']`。
  - 上限 4000 の scratch: `expanded n=5 mismatch=2`・exit 1。0x104aba9 と 0x104af7f は **一致**。残る不一致は 0x104ad2e・0x104b093 (`imul` の源欠落・#5926)。py64 出力に `SLOT` は 0 件。
  - `DEPTH_LIMIT` を外した scratch: `expanded n=5 mismatch=4`。`…` は本体と同じ 6 件が残る (py64 経路の `…` は深さ上限とは別で、上限 400 字の切れによるもの)。
- つまり上限 4000 で F 型 2 点は py64 の照合が通る。`SLOT?` は py88 の生の出力 (a) にだけ残り、py64 の照合を妨げない。
- 既存点への影響: `py99_slot_paths.py` と `py88_writes.py` は変更していない。`py159_check_hand.py` は `py64_check_expr` の `parse_canon`・`machine_norm` を使うが、文法追加は既存式の解釈を変えない。

### 差分 (測定 commit から HEAD まで)

測定 commit は `c9430d6a2` (`tools/python/analysis` を変えた最後の commit)。鮮度: `git diff c9430d6a2 HEAD -- tools/python/analysis` は 0 行 (本 PR の検証 HEAD 時点)。`e54706dec` (PY-5361 の `flapi/plugins_getcolor_facts.py`) は測定 commit より前の commit で、G2・G3 の式照合 (`py64_check_expr.py`・`py88_writes.py`・`py99_slot_paths.py`) の入力には影響しない。

`git diff 53ab89b54 HEAD -- tools/python/analysis` は本 PR の commit 後の差分 (本 §7 の追記時点で 0 行)。


## 9. PY-5404 (#5926): `imul` の源と `resolve()` の 400 字切れ (受入 1・2・4 の部分)

- 測定 commit: `6f9c59646` (`analysis/py88_writes.py` のコードを変えた最後の commit)。入力: `fl-win64` の `block00031_PE.bin` → `py53_dispatch.py` (`fn=4664 dispatch=13 r8d_tests=174`)。load average 0.12 (測定時 17:02 UTC)。
- 原因 1 (受入 1): `def_value` の ARITH 分岐は 2 オペランドしか見ず、`imul rcx, rcx, 0x28f` (0x104abce ほか 3 オペランド形) の源 `0x28f` を捨てていた。修正: 3 オペランドを `op(a, b)` で出す。0x104ad2e・0x104b093 の式に `imul(SLOT[rbp+0x578]?@0x104aabe, 0x28f)` が出る。
- 原因 2 (受入 2): `resolve()` の上限 `res[:400] + "…"` を `RES_LIMIT = 4000` (定数化) に上げた。0x104aba9 (式 417 字)・0x104af7f (426 字)・0x104bebf (474 字) の展開 (`py99_slot_paths.expand`) から `…` が消えた。0x104bffa (544 字) も `…` は消えるが、`⚠合流@0x104bd49`・`⚠合流@0x104be63` が残る (分岐合流は別件・本 PR の範囲外)。
- 残る印: 0x104aba9 の展開式 (`py99_slot_paths.expand`) に `SLOT[`・`ACC?⚠`・`…`・`⚠` は 0 件。`left=[]`。0x104bffa は `left=['⚠']` (上記の合流 2 件)。
- 変化 (測定 commit から前後比較): `py88_writes.py` 既定 65 件の出力差は 5 行 (0x1049f24 は `shr` 連鎖・0x104ad2e/0x104b093/0x104b94e/0x104bffa は `imul` の源が出た分)。`py88_writes.py` 11 件の category 数は変わらず (SLOT? 5・SLOT?+ACC?⚠ 3・CALL+ACC?⚠ 1・ACC?⚠ 1・直接式 1)。65 件の category: 修正前後で同一。
- 依存スクリプト (前後比較・同 fn.txt): `py99_slot_paths.py` 差分 2 行 (`store 0x104b2de` の式で `imul` の源が出た分)・`py99_merge_sets.py` 差分 2 行 (同)・`py64_check_expr.py` 差分 0・`py159_check_hand.py` 0・`py160_reach.py` 0・`py161_movabs_check.py` 0・`py99_closure.py` 0・`py163_vcall.py` 差分 2 行 (`式:` の `imul` 源)。
  - `py99_slot_paths.py` の突合は不変: `U check n=57 match=57 mismatch=0`・`forward cross-check n=172 mismatch=0`。
  - `py64_check_expr.py`: `n=8 mismatch=0`・`expanded n=1 mismatch=0`・exit 0 (不変)。
- 未完 (受入 3・4 の残り): py64 の HAND 表に 0x104aba9・0x104ad2e・0x104af7f・0x104b093 を入れるには、手計算式を `shl`・`and`・`imul` を含む文法で書く必要がある (`py64_check_expr.py` の文法は `+ - * · rint f64 ACC d_in` のみ)。この run では文法を拡張しなかった (Refs #5926 の残り)。
