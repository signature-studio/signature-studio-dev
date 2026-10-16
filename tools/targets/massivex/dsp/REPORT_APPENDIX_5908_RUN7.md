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

- **状態 (round 1 fix)**: 下の表と判定は測定 commit `4beb1179b` の旧 script の出力。round 1 で script を次のとおり直した。直後の HEAD は未測定で、表は HEAD に対して無効。
  - (a) 転送 site は、pdata 関数を先頭から線形復号して命令先頭と一致する `call`/`jmp` のみ採る (`not_insn_boundary` に分ける)。
  - (b) 入口から site への到達性 (`F_reach_no`) を別に数え、到達する site だけを `F_undef` / `F_defined` に分ける。到達しない site は未判定。
  - (c) docstring の regs_read/regs_write の記述を、実装の明示オペランド access に合わせた。
  - 線形復号は、関数内にデータが混ざると命令境界がずれ得る。その場合は `not_insn_boundary` に出る。
- 再測定: 未実施。`plugins-massivex` が R2 素材として取得されていない (`$ARTIFACTS_DIR` に `fl-win64` のみ)。`Massive X.vst3` md5 `622993e7…` は確認していない。PR 本文の `oc_artifacts: fl-win64 plugins-massivex` で review run に再測定を任せる。
- 旧出力の md5 は記録していない (旧出力ファイルが残っていない)。「cmp で同一」は REPORT にも PR 本文にも書かない。
- 検算 (旧 run の記録): `mx63_u3e_split.py` population 604・E 43 (前 run と一致)。
- 方法: E 43 件の転送先 G について、(a) 転送元 F の入口から転送 site まで、全経路で xmm4/5 が未定義か (`F_must_undef`)、(b) G の入口から書き込み前に xmm4/5 を読む経路があるか (`G_livein_read`)。capstone の `regs_read`/`regs_write` は VEX 命令で空を返す (25/25 件) ため使わず、明示オペランドの access で読む。

| 判定 | 件数 |
|---|---|
| F の入口 xmm4/5 が転送 site まで全経路で未定義 | 43 / 43 |
| G が書き込み前に xmm4/5 を読む (G 入口で値を要求) | 40 / 43 |
| G の入口が命令として読めない (`hlt`・`jmp [mem]`・`pop` 等で始まる) | 3 / 43 (`0x180a2b0d0`・`0x180c92cf2`・`0x180e91af5`) |

- 40 件の G は入口から読む命令があり、転送された値を入口で要求する。**F の入口値が G の入口 livein に届く**ことの証拠になる。
- 3 件は G の先頭がデータ・非命令境界のため判定不能。`livein_read=False` を「依存なし」と読んではならない。
- 先頭から到達する 4 件 (`0x180850d80`・`0x18086d66c`・`0x180a2e5d0`・`0x180d0c546`) は、先頭から G までの経路上で xmm4/5 が書かれる (`G_reach_undef=False`)。G 入口の値が F の入口値と同一とは言えない。ただし G の入口からの livein は読まれる。

### 判定 (受入 1)

- 源側 (F の入口値が転送 site に届く): 43 件で確認。
- G 側: 40 件で G が入口で値を読むことを確認。3 件は G が関数入口でないため未判定。
- 受入 1 の判定 (MX-6 入口 livein 0 の陰性が過小検出か) は、3 件の G の同定が残るため確定しない。

### 未解決 (run 8)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| G 3 件 (`0x180a2b0d0`・`0x180c92cf2`・`0x180e91af5`) の入口が命令として読めない | 3 件の U3e 判定 | #5908 (残件) |
| 件数の正 (47 / 42) | 両方記録。正は PM 判断 | #5908 |
