# Massive X MX-63 (#5908) run 7: 制御フローの再帰降下による非境界 G の判定 (U3e 残件 2 の続き)

- REPORT_APPENDIX_5908.md §9 の分割移動 (250 行上限のため)。本文の結論は REPORT_APPENDIX_5908.md §9 に残す。移動に伴い、§9.1 の call の記述と終端の定義を script の実装どおりに訂正した (判定結果の数値は不変)。
- 測定 commit: `2d1e52a43` (新規 script `mx63_g_recdesc.py` を含む commit)。本 fix run の commit 以外の差分は、この commit では docstring のみ。
- 素材: `plugins-massivex` → `parse_setup_headers.py` → `extract_massivex.py <exe> work key`。`Massive X.vst3` = 95,356,824 B・md5 `622993e76565f49c094063a2b717d6ca` (一致)。PE は repo 外。
- 本 commit (fix run) では素材 `plugins-massivex` が無く、`mx63_g_recdesc.py` を再実行していない。§9.2 の表は測定 commit `2d1e52a43` の出力のまま。本 commit は docstring のみで script のロジックは不変。

| 実行 (HEAD `2d1e52a43`) | 結果 | 経過 | load (start → end) |
|---|---|---|---|
| `mx6_e2e.sh` | rc 0・PASS 32・FAIL 1 (既知の負例) | 42 s | 終了後 `uptime` の 1 分値 0.71 (開始・終了の load は未採取) |
| `mx63_u3e_split.py` | population 604・E 43・D 825・C 1549・G0 351・G 26 | — | — |
| `mx63_g_containment.py` | 途中・命令境界 7 / 途中・非境界 35 / 範囲外 1 | — | — |
| `mx63_g_cs_stop.py` | n 35・cs_stop_before_G 23・cs_full 12 | — | — |
| `mx63_g_recdesc.py` (新規) | n 35・reached_from_fn_start 4・self_closed_no_bad 12・self_ret_with_bad 14・undetermined 5 | 0.5 s | — |

### 9.1 `mx63_g_recdesc.py` の方法

- pdata 関数の先頭から、fallthrough と直接の jmp/jcc の飛び先だけをたどる (RVA 単位・関数範囲内)。`call` は飛び先を追わず、fallthrough (戻り先) のみをたどる。間接 jmp・call の飛び先・関数外への飛び先は追わず、件数に数える。
- 終端は `ret`・`ud2`・`int3`・`hlt` の 4 種。`self_ret` と出力キー名は、この 4 種への到達を指す (`ret` のみではない)。
- 判定 (非境界 G 35 件):
  - `reached_from_fn_start`: 関数先頭から fallthrough・直接 jmp/jcc で G に到達する (G は実行経路上の命令境界)。call 経由の到達は含まない。
  - `self_closed_no_bad`: G 起点で復号すると終端 (ret 等) に到達し、(bad) に当たらない。
  - `self_ret_with_bad`: G 起点で終端に到達するが、途中の経路に (bad) がある。
  - `undetermined`: G 起点で終端に到達せず、(bad) か間接分岐で止まる。

### 9.2 結果

| 非境界 G 35 件の内訳 | capstone 停止 (`cs_stop_before_G`・(bad) 手前) 23 | 関数末尾まで復号 (`cs_full`) 12 |
|---|---|---|
| `reached_from_fn_start` | 4 | 0 |
| `self_closed_no_bad` | 5 | 7 |
| `self_ret_with_bad` | 13 | 1 |
| `undetermined` | 1 | 4 |

- `reached_from_fn_start` の 4 件 (`0x850d80`・`0x86d66c`・`0xa2e5d0`・`0xd0c546`) は、§6 に記録された objdump の境界 4 件と同じアドレス。照合は §6 の記録との文字列比較のみで、本 run では objdump を再実行していない (比較に使った出力: REPORT_APPENDIX_5908.md §6 の表・測定 commit `b5bf50fb0` の `mx63_g_objdump_check.py` 出力)。
- 残りの 31 件は、先頭からの到達は確認できない。`self_closed_no_bad` は「G から先の復号が閉じる」だけで、G が入口であることの証拠にはならない。

### 9.3 判定 (受入 1 の G 側)

- **本 script の規則で確認**: 非境界 G のうち 4 件は、関数先頭から fallthrough・直接 jmp/jcc だけで到達する。途中の入口として成立し得る。call 経由の到達は見ていないため、この 4 件は確定ではない。
- **確定しない**: 残り 31 件。G が途中の入口か、埋め込みデータ・復号誤りかを区別できない。特に capstone の (bad) 停止の 23 件のうち 19 件は、先頭から G に到達する経路を制御フローで示せていない。
- 4 件が入口でも、F の入口値が G の入口 livein に届くことの証拠 (経路上で xmm4/5 が定義されないこと) は、この script では確認していない。よって U3e の判定 (MX-6 の入口 livein 0 の陰性が過小検出か) は、本 run でも確定しない。
- 件数の正 (47 / 42) は決めない (R7 (a))。本 run で件数は変えない。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 非境界 G 31 件の先頭からの到達が未確認 (埋め込みデータ・復号誤りか途中の入口か) | U3e の判定が確定しない | #5908 (残件) |
| `reached_from_fn_start` 4 件について、経路上で xmm4/5 が未定義かの確認 (入口値の同一性) | 4 件を U3e の証拠にできるか未確定 | #5908 (残件) |
| 件数の正 (47 / 42) | 両方記録。正は PM 判断 | #5908 |
| `mx63_g_recdesc.py` の再実行 (`plugins-massivex` が無く未実施。開始の load も未採取) | §9.2 の表は測定 commit の記録のまま | #5908 (残件) |

## 10. run 8: 転送 site の xmm4/5 生存判定 (`mx63_g_xmm_live.py`)

- **測定 (HEAD 実測)**: 測定 commit = 本 fix の HEAD (`mx63_g_xmm_live.py` は `a725746bc` から pdata 範囲フィルタを追加)。素材 `plugins-massivex` から再生成した `Massive X.vst3` (95,356,824 B・md5 `622993e76565f49c094063a2b717d6ca` 一致) に対して実行した。
  - 素材: `tar --zstd -xf plugins-massivex.tar.zst` → `parse_setup_headers.py` → `extract_massivex.py <exe> <work> key` (extract の `md5-ok 0/125` は既知事象)。PE は repo 外。
  - 対象 G: `mx6_e2e.sh` (rc 0・57 s・load 0.86 → 0.95) の vectorcall.json から `mx63_u3e_split.py` を実行し、E 43 件の転送先 G (RVA。`cat == "E"` の site の `G`・重複 0)。
  - 実行: `mx63_g_xmm_live.py <PE> <out.json> <G 43 件>` rc 0・5.3 s・load 0.41 → 0.41。
  - 測定 commit `6740f0b02` (コードを変えた最後の commit)。同 commit で再実行し、出力 JSON は前回と `cmp` で同一 (md5 `09306b687e073e2dd00c3f643a3c2f30`)。
  - `git diff 6740f0b02 HEAD -- tools/targets/massivex/dsp` の差分は、本 REPORT の commit の後に追加する (下記)。
- **script の修正 (本 fix)**: pdata に `.text` 外へ広がる不正な範囲が 100 件あり (最大約 4 GB)。それを関数として採ると `insn_starts` が範囲全体を復号してメモリを使い切った (修正前の script で E 43 件を一括実行すると rc 137 で kill)。`.text` 外の pdata 範囲は関数として採らないよう直した。
  - 影響: 43 件のうち 1 件 (G `0x180cdfa85`) のみ結果が変わった。修正前は不正範囲 `0x180123920` 内と判定して `G_livein_read=True` としていたが、修正後は pdata 外として未判定にした。残り 42 件は修正前後で同一 (同じ入力で比較)。
- 検算: `mx63_u3e_split.py` population 604・E 43・D 825・C 1549・G0 351・G 26 (`mx6_e2e.sh` の vectorcall.json から再実行・HEAD で一致)。
- 旧 commit `4beb1179b` の 43/43・40/43・3/43 は HEAD の結果ではないため、この表から外した。

| 判定 (HEAD・E 43 G) | 件数 |
|---|---|
| 転送 site (命令先頭の call/jmp・G へ直接) | 43 (候補 43・命令境界外 0・pdata 外 0) |
| 入口から site まで到達しない (`F_reach_no`) | 0 |
| F の入口 xmm4/5 が転送 site まで全経路で未定義 (`F_undef`) | 43 / 43 |
| G の先頭から xmm4/5 を書かずに G へ届く (`G_reach_undef=True`) | 32 / 43 |
| G が書き込み前に xmm4/5 を読む (`G_livein_read=True`) | 39 / 43 |
| G が pdata 外で `G_livein_read` 未判定 | 1 / 43 (`0x180cdfa85`) |

- `G_livein_read=True` の 39 件は、G の入口から書き込みより前に xmm4/5 を読む経路がある。転送された値を入口で要求し得る。
- `G_livein_read=False` の 3 件 (`0x180a2b0d0`・`0x180c92cf2`・`0x180e91af5`) は、先頭が `hlt`・`jmp qword ptr [rsi+0x66]`・`pop rcx` で、読みが終端 (終端命令・間接 jmp・pop) まで届かない。**「依存なし」とは読まない**。命令としては復号できる。
- 先頭から到達する 4 件 (`0x180850d80`・`0x18086d66c`・`0x180a2e5d0`・`0x180d0c546`) は `G_livein_read=True`・`G_reach_undef=False`。先頭から G までの経路で xmm4/5 が書かれるため、G 入口の値が F の入口値と同一とは言えない。
- レビュー側の 7 G の実測 (head `a725746bc`) と、本 HEAD の値は、転送 site・`G_reach_undef`・`G_livein_read` が全 7 件で一致する。

### 判定 (受入 1)

- 源側 (F の入口値が転送 site に届く): 43 件すべて `F_undef` = 43 (到達も確認: `F_reach_no` = 0)。
- G 側: 39 件で G が入口から書き込み前に xmm4/5 を読む。3 件は読みが終端命令まで届かず判定不能。1 件は pdata 外のため判定不能。
- 受入 1 の判定 (MX-6 入口 livein 0 の陰性が過小検出か) は、G 側の 4 件 (`0x180a2b0d0`・`0x180c92cf2`・`0x180e91af5`・`0x180cdfa85`) が残るため確定しない。

### 未解決 (run 8)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| G 4 件 (`0x180a2b0d0`・`0x180c92cf2`・`0x180e91af5`・`0x180cdfa85`) の入口 livein が未確定 | 4 件の U3e 判定 | #5908 (残件) |
| pdata 外の不正範囲 100 件 (script は除外。その範囲に入る関数を正しく読めるかは未確認) | 不正範囲に G が入る場合の判定 | #5908 (残件) |
| 件数の正 (47 / 42) | 両方記録。正は PM 判断 | #5908 |
