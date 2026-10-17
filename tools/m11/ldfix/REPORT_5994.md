# #5994 (LD-295): first-deref-not-entry 修復 関数群 B (10 関数) の survey 到達理由の記録 — 部分達成

**判定: 部分達成**。10 関数それぞれについて、survey で到達しない状況と直接呼び出し元を記録した (§2)。10 対象の入口は全 942 unit で 0 回 (§3.1)。10 対象の 1 段目の呼び出し元 11 件も全 unit で 0 回 (§3.1, r1)。47a250 の `function_` 形式の呼び出し元 41 件 (§5, r3) のうち 7 件が kind=ok で入口に到達した。10 対象が到達しない機構は未確定 (§3.2・§4)。

先行: #3194 (`REPORT_930.md`・`REPORT_1325.md`)・#3195 (`REPORT_3195.md`)。群 A は #5993。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 10 関数 (db6480・dc27c0・ddd4d0・41b8d0・41b970・449550・44fb40・784ed0・c40420・f552a0) について、survey で到達しない理由 (呼び出し元・計装の届かない経路) を関数ごとに REPORT に記録 | **一部**。呼び出し元 (IR の直接呼び出し元と、間接呼び出しの trampoline 経路) は §2 に関数ごとに記録した。10 対象の 1 段目の呼び出し元 11 件は全 942 unit で入口 0 回 (§3.1)。47a250 の `function_` 形式の呼び出し元 41 件のうち 7 件が kind=ok で到達した (§5)。10 対象の到達を妨げる機構は未確定 (§3.2) |

## 2. 関数ごとの記録 (旧 IR の結果)

**この節は前回 run の IR (sha256 先頭 16 桁 `010451add5147d37`・529468 行) の結果。本 run の IR (`a69dd5dace9384af`・529644 行) とは別物で、件数は §3.2・§5 の値を正とする。** survey の既存結果: `results/reach_930.json` (942 unit)・`results/reach_1325_head.json` (942 unit)。

「kind=ok で入口に hit」は、その関数の入口計装が kind=ok の unit で 1 回以上 hit したもの。

| 関数 | survey kind=ok hit | 他 kind の hit | 直接呼び出し元 (`caller X -> callers Y`: X の呼び出し元が Y) | 間接 call 経路 (trampoline・生成規則上の有無) |
|---|---|---|---|---|
| db6480 | 0 | — | caller dc25f0 -> callers dc27c0 | 有 (`m11_tr_function_db6480`) |
| dc27c0 | 0 | — | caller dbde10 -> callers 10348b0 | 有 |
| ddd4d0 | 0 | — | caller ddeca0 -> callers de10c0 | 有 |
| 41b8d0 | 0 | — | caller 41bd20 -> callers 41bff0・caller 41be80 -> callers 41c040 | 有 |
| 41b970 | 0 | — | caller 41bd20 -> callers 41bff0・caller 41be80 -> callers 41c040 (41b8d0 と同じ) | 有 |
| 449550 | 0 | — | caller 449600 -> callers 50a8c0・50aa70・50abe0・50ad30・528150・caller 47a250 -> callers 42 関数 (旧 IR の値) | 有 |
| 44fb40 | 0 | — | caller 44fab0 -> callers 44fce0 | 有 |
| 784ed0 | 0 | — | caller 785220 -> callers 7878c0・78bab0・78c110・caller 786180 -> callers 785a90 | 有 |
| c40420 | 0 | — | caller d341b0 -> callers d34290 | 有 |
| f552a0 | 0 | — | caller f3c7b0 -> callers f40840 | 有 |

- 関数ごとの hit 件数は、committed 2 本の survey で確認した。41b8d0・41b970・449550・44fb40・784ed0・c40420・f552a0・db6480・dc27c0・ddd4d0 は、どちらの JSON でも kind=ok の hit が 0。
- 40fe90 は reach_1325_head で oob (unit 745) と halt0 (unit 895) の hit だけ。この run の対象外。
- 間接 call 経路の「有」は、個別の IR 確認をしていない。`tools/m11/m11_post.py` は引数 8 以下の定義関数それぞれに `m11_tr_<fn>` (`m11_tr_function_<VA>`) を生成し、VA→トランポリン表に載せる (同ファイル 360〜371 行)。表の「有」はこの生成規則からの推定。どの unit がこの経路を通るかは未計測。
- 呼び出し元の 2 段目が多い 449550 (直接呼び出し元 449600・47a250。47a250 の呼び出し元は旧 IR で 42 件、本 run の IR で 43 件 (§3.2)) と 784ed0 (← 785220・786180) は、呼び出し元のうち survey で到達するものの有無を個別に見る必要がある (未実施)。

計算は `tools/m11/ldfix/callers_5994.py` (静的・計装なし)。出力:

```
python3 tools/m11/ldfix/callers_5994.py work/boot_final3.ll 101d180 db6480 dc27c0 ddd4d0 41b8d0 41b970 449550 44fb40 784ed0 c40420 f552a0
```

## 3. 測定 (HEAD から作り直した build)

前回 run の残件 (committed と同じ build での計装) は、同梱 obj を再コンパイルせず、HEAD の C から作り直した build で取った。

- 手順: `FL_WIN64_DIR` に `fl-win64` の `block00031_PE.bin` を置き、`m11_gen_ir2.sh` (rc 0・490790 行・`ir_conditions.json` 生成) → `m11_build.sh` (rc 0・wasm-ld signature mismatch 0・undefined symbol 0) → `ldfix/reach_509.sh` の順で実行。`EMSDK_ENV` に [EMSDK] の `emsdk_env.sh` を指定。
- 再生成した `work/boot_final3.ll` は sha256 先頭 16 桁 `a69dd5dace9384af`・529644 行。§2 の入力 (`010451add5147d37`・529468 行) とは一致しない。以後の結果は再生成した IR に対するもの。
- 計装: 21 関数 (10 対象 + 1 段目の直接呼び出し元 11)。`ldfix/results/reach_5994.json` (942 unit)。
- kind 分布: ok 873・miss 47・oob 15・halt0 6・noproc 1。committed (`reach_930.json`: ok 870・miss 47・halt0 7・oob 16・other 1・noproc 1) と近い。miss 47 は一致。
- 対照: 同じ build での計装の動作は、l2 run の unit 275 / key `12` (50aa70 の入口) の非ゼロ hit (3204504 回) で確認した。key `12` = 50aa70 は下記 VA 列挙順 (index 12) と一致する。
- 別 build の参考値 (本 build では未測定): 44f040 = 3 unit、47ad70 = 7 unit (`REPORT_1325` §4)。本 build の対照には使わない。

### 3.1 結果

| 関数 | 入口に hit した unit | 入口通過 総回数 |
|---|---|--:|
| 10 対象 (db6480・dc27c0・ddd4d0・41b8d0・41b970・449550・44fb40・784ed0・c40420・f552a0) | 0 | 0 |
| 1 段目の呼び出し元 (dc25f0・dbde10・ddeca0・41bd20・41be80・449600・44fab0・785220・786180・d341b0・f3c7b0) | 0 | 0 |

- r1 (`reach_5994.json`) の全ゼロは「計装が動かない」ではなく、「対象は全 942 unit で入口に来ない」と読む。計装が動くことは、同じ build の l2 run で unit 275 の key `12` (50aa70) が非ゼロになったことで確かめた (§3 対照)。
- 10 対象は全 942 unit で入口 0 回。1 段目の呼び出し元も全て 0 回。
- 2 段目 (`10348b0・de10c0・41bff0・41c040・44fce0・7878c0・78bab0・78c110・785a90・d34290・f40840・50a8c0・50aa70・50abe0・50ad30・528150・1016ca0・1017ad0・1016600・1019da0・101b780`。この順が計装の key 0〜20 で、key `12` = 50aa70) は、50aa70 だけ入口に入った (unit 275・kind=oob・通過 3204504 回)。残りは 0。結果は `ldfix/results/reach_5994_l2.json` (同じ 942 unit・同じ build)。
- 50aa70 は IR の 183900 行で 449600 を直接呼ぶ。ただし 50aa70 の入口 hit は kind=oob の unit 275 だけで、kind=ok では 0。449600 から先が 10 対象の入口へ届くかは未測定。

### 3.2 未確定

- 10 対象が survey で到達しない機構は、ここでも確定していない。kind=ok の unit で 1 段目の呼び出し元すら入らないため、到達しない分岐は 2 段目より上にある。
- 449550 の直接呼び出し元は 449600 と 47a250 の 2 件 (§2 の表)。
- 前回 run の記述 (誤り): 「47a250 は IR に定義 (`define`) が無く、入口を計装できなかった」。本 run の IR (§5) では `function_47a250` は `define weak` で定義されており、wrapper の入口は label を足したコピーで計装した (§5)。
- 本 run の IR で 47a250 の呼び出し元は 43 件 (`function_` 形式の定義 41 件・`function_4fa210__lifted`・`m11_tr_function_47a250`)。計装したのは `function_` 形式の 41 件。この数は 449550 の直接呼び出し元ではない。
- 前回 run の「l2 の計装 21 関数が 42 件のどれに当たるか」は、§5 の run 3 で IR を再生成して照合した (41 件を計装・全件)。
- 「同梱 obj の古さ」の問題は、HEAD から作り直すと出ない。ただし `_m11_call_unit_at` 等の export は同梱 obj では未定義で、再生成 build では定義がある (`m11_build.sh` の既定で rc 0)。

## 4. 未実施と残件

| 残件 | 影響 | 起票先 |
|---|---|---|
| 10 対象の到達を妨げる機構の特定 (上位側の分岐・間接 call 経路の kind 別の入口通過)。入口 hit が全 942 unit で 0 のため、呼び出し元の探索を続けるか、対象の入力条件を調べるかの判断が必要 | 10 関数の「到達しない理由」の機構が未確定 | #5994 (open・残件を保持) |

- 子 issue は起票しない。残件は open のままの #5994 に保持する (#3194 には、この残件に対応する受入条件が無い)。

## 5. run 3 の測定 (IR 再生成・同じ build)

- 手順: `FL_WIN64_DIR` に `fl-win64` の `block00031_PE.bin`・`EMSDK_ENV` に `toolchain-emsdk` の `emsdk_env.sh`・`work-m11` を展開 (`tools/m11/work/`)。`m11_gen_ir2.sh` rc 0 (490790 行) → `m11_build.sh` rc 0 (wasm-ld signature mismatch 0・undefined symbol 0) → `reach_509.sh`。
- 再生成した `work/boot_final3.ll` は 529644 行・sha256 先頭 16 桁 `a69dd5dace9384af` (§3 と同じ。§2 の入力 `010451add5147d37` とは一致しない)。以下はこの IR に対する結果。
- kind 分布 (全計装セット共通): ok 873・miss 47・oob 15・halt0 6・noproc 1。

| 計装セット | 関数 | 入口に hit した unit | 入口通過 総回数 |
|---|---|--:|--:|
| r1 `reach_5994_r3_l1.json` | 10 対象 + 1 段目の呼び出し元 11 | 0 | 0 |
| r2 `reach_5994_r3_l2.json` | 2 段目 21 関数 (10348b0・de10c0・…・101b780) | 50aa70 のみ unit 275 (kind=oob・3204504 回) | 3204504 |
| r3 `reach_5994_r3_l3.json` | 10 対象 + 47a250 + 呼び出し元 41 件 (計 52) | 呼び出し元 7 件 (key 15・17・18・20・21・22・25、VA は未記録) で hit。10 対象と 47a250 は 0 | 対象 0 |
| r4 `reach_5994_r3_l4.json` | 47a250__lifted・449600・50aa70・50a8c0・50abe0・50ad30・528150 | 50aa70 のみ | 3204504 |

- 47a250 は本体 (`function_47a250__lifted`) も wrapper (`function_47a250`) も入口に hit しない。「呼び出し元では hit するが 47a250 では 0」は、呼び出し元の入口に入ったことまでしか示さず、その呼び出し元が 47a250 の call 箇所を通ったかは未確認 (call 箇所の分岐は測っていない)。
- 呼び出し元の key → VA: 計装 key は `reach_5994_entry.py` の出力順 (0 = 47a250、1〜10 = 10 対象、11 以降 = 呼び出し元 41 件)。r3 で hit した呼び出し元 key は 15・17・18・20・21・22・25 (7 件。hit した unit は 95・101・291・296・304・555 で全て kind=ok)。key → VA の対応は、この run では IR (`work/boot_final3_w2.ll`) が残っていないため再生成できず、VA は未記録 (`4f9f40 ほか` の VA は未検証)。対応を出すには §5.1 の再現手順で IR を作り直し、`reach_5994_entry.py` の出力順と照合する。wrapper は本体が `call` だけのため、`reach_509.sh` の挿入位置 (定義直後の label) が無く、label 行を足したコピー (`work/boot_final3_w2.ll`・`ldfix/reach_5994_entry.py`) で計装した。
- 449550 の直接呼び出し元は、本体の `function_449600` (IR 152455 行) と `function_47a250__lifted` (176653 行) の 2 件。IR の `m11_tr_function_449550` (506998 行) と `m11_tr_function_449600` (507002 行) は間接経路の trampoline。
- 結論: 計装した範囲で、10 対象の入口に kind=ok で届く経路は見つからなかった。10 対象の到達を妨げる機構は未確定のまま。

### 5.1 検証
- `reach_509.sh` の出力は `ldfix/results/reach_5994_r3_l*.json` (942 unit)。
- 再現: `python3 ldfix/reach_5994_entry.py work/boot_final3.ll work/boot_final3_w2.ll > targets.txt` → `IR=work/boot_final3_w2.ll bash ldfix/reach_509.sh "$(cat targets.txt)" OUT.json`。
