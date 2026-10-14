# REPORT_APPENDIX_944 — unit 158・j=12 の dest 値差の後続経路 (#1945・#1864 の残り)

REPORT_944.md の付録 (§1〜§4 は #1945、§5 は #2003、§6 は未解決、§7 は #1864 の旧 §9)。§1〜§4 の測定 commit: **`e5e3c7c2`** (origin/main。本節の作業ではコードを変えていない)。
コード差分 0 (文書のみ)。確認コマンド: `git diff --stat e5e3c7c2 HEAD -- tools/m11`。出力:

```
 tools/m11/trap_triage/REPORT_944.md          |  1 +
 tools/m11/trap_triage/REPORT_APPENDIX_944.md | 55 ++++++++++++++++++++++++++++
 2 files changed, 56 insertions(+)
```

文書以外を除いた差分 `git diff e5e3c7c2 HEAD -- tools/m11 ':!tools/m11/trap_triage/REPORT_944.md' ':!tools/m11/trap_triage/REPORT_APPENDIX_944.md'` は 0 行。

## 1. 再現 (受入条件 3・同一 build 内の決定性)

コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH=$HOME/.local/agent-py/bin:$PATH bash tools/m11/trap_triage/repro_1389.sh` (OFF → OFF 再実行 → ON・直列・単発)。判定 `PASS`。全体 1 分 49 秒 (`time` の real・load 開始 0.93 / 1.03 / 1.01)。
素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`)・work-m11 (gitignore 対象の作業領域)・`toolchain-emsdk` ([EMSDK]・`releases-6e9f6885`)。`m11_gen_ir2.sh` を 50 秒で実行 (ldfix F1=902 F3c=36 errors=0)。

| 構成 | 記録 (呼出し数) | 比較の結果 | survey elapsed |
|---|--:|---|--:|
| OFF | 227 | — | 16.243 s |
| OFF 再実行 | 227 | OFF と完全一致 (差 0) | 16.065 s |
| ON (`M11_OV_413060=1`・読出しあり) | 216 | unit・順番で揃った 216 件中、差 1 件: unit `0x26d1a0` j=12 (`st` `len` `rc` `h` の 4 フィールド) | 16.149 s |

差分の中身 (`cmp_1389.py` の出力): OFF `{st 0, len 0, rc 0}` / ON `{st 1, len 1, rc 1}`。ON 側の 11 件は片側のみ (ON は 216 件のため `k` の対応が 11 件分外れる)。

## 2. unit 158 の呼出し列 (OFF/ON・記録より)

unit `0x26d1a0` の f413060 呼出しは OFF 28 回・ON 17 回 (`cost_<label>.json`)。全体の k は 136〜163 (OFF)。
j=0〜11 は OFF/ON で一致 (`st` は j=1,3,6 のみ 1 (len 59)、他は len 0)。j=12 (k=148) で ON だけ `st=1 len=1` (OFF は `len 0`)。
j=13 (k=149) 以降は OFF/ON とも同じ値 (`len 59`) だが、ON はこの unit の呼出しが j=16 までしか無い (17 回)。

## 3. ON の trap (unit 158)

- ON の survey: unit 158 は `memory access out of bounds` で trap (`detail` の `trap` 種別)。OFF は ok。
- 同一 build (`M11_INSTR_413060=1 M11_OV_413060=1 M11_DEST_READ=1`・記録あり) の再実行で同じ trap (証跡は gitignore 対象の作業領域。repo には含まれない)。
- 最上位 frame は未取得 (detail は種別のみ。`top_frame_idx` は全体集計で unit 158 に紐付かない)。REPORT_684 の `414bb0` ←`652500` 系 (unit 158 は REPORT.md §最上位 frame 表の `414bb0` 群) と関係する可能性はあるが、**未検証**。
- **読出しのみの ON (`M11_DEST_READ=0`・記録なし) の再測定**: unit 158 は **ok** (survey 870/24、REPORT_944 §7.2 と一致)。呼出し 28・getmem 140 (OFF は 139)・freemem 94 (OFF は 92)。`m11_build.sh` の stamp (`M11_DEST_READ` を含む `work/neg_413060.stamp`) で build を切り替えて測定した。**実際に使った環境変数の組と実行手順は記録に残っておらず、repo にもこの測定を再現するスクリプトは無い** (`repro_1389.sh` は OFF/OFF/ON の 3 点のみで `M11_DEST_READ=0` を含まない)。下記は build 切替の仕組みからの再構成で、未検証: `M11_INSTR_413060=1 M11_OV_413060=1 M11_DEST_READ=0 bash m11_build.sh` → `M11_INSTR_413060=1 M11_SURVEY_COST=<out> node m11_survey.mjs`。証跡 (build ログ・survey 出力) は gitignore 対象の作業領域にあり repo には含まれない。本 PR の検証では再実行していない。
- 記録あり ON (`M11_DEST_READ=1`) の unit 158 は trap で、呼出し 17 で止まり getmem 23・freemem 16 (OFF 139/92 と大きく違う)。
- 以上から、観測を入れた ON で unit 158 が trap し、観測を止めた ON では ok になる。これは **記録側の読出し/書込みが unit 158 の実行を変えている**ことを示す。
- ただし `DEST_READ=0` では j=12 の値を観測していないため、「ON の値差 (`len 0→1`) が後続の結果に効かない」とは言えない。値差が後続の呼出し・読出しを変えるかは、IR で unit 158 の後続経路を追うまで未確定 (受入条件 1)。

## 4. 受入条件の判定 (#1945)

1. **値差が結果に効くか (後続の呼出し・読出し)**: **未達**。j=12 の値差後に ON で呼出しが 28→17 に減り trap するが、「値差が原因で後続が変わる」か「記録の副作用で trap する」かの切り分けは未了。後続経路の IR 突き合わせ (呼出し元・後続の読出し) は未着手。
2. **§7.3 追記・§4 (a) 更新**: 本付録へのリンクを §7.3 に追記。結論は「未確定」のまま。
3. **決定的な測定と実測値**: **達成**。§1 の OFF 2 回一致・所要・load を記録。

## 5. #2003 追記: 読出しなし ON の実測・unit 158 の trap frame・単独実行 (受入条件 2・4)

測定 commit: **`a22c1aef`** (HEAD で実測)。5.1〜5.3 の数値はすべて `a22c1aef` の `tools/m11` で取った。`c171b9dc` からの差分の扱いは 5.5。
`repro_1389.sh` の所要時間は測定 commit **`af65d115`** (検証 HEAD) で取り直した値 (5.0)。`a22c1aef..af65d115` の測定経路差分は 0 (5.5)。

### 5.0 `repro_1389.sh` の所要 (測定 commit `af65d115`・直列・単発・foreground)

- 全体 real 1m49.3 s・load 1.05 (OFF 開始時)。OFF: 16.356 s・OFF 再実行: 15.994 s・ON: 16.103 s。
- OFF 2 回: 記録 227 件が完全一致 (差 0)。OFF/ON: 216 件の突合で差 1 件 (unit `0x26d1a0` j=12・`st` `len` `rc` `h`)。判定 PASS。
素材: `fl-win64` (`$RUNNER_TEMP/fl-win64` に展開)・`work-m11` (展開後に `m11_gen_ir2.sh` で `ir_conditions.json` 再生成: F1=902 F3c=36 errors=0)。`toolchain-emsdk` は展開せず、既設の [EMSDK] を使った (`emcc` 確認済み)。直列・単発・foreground。

### 5.1 `M11_DEST_READ=0` の ON (読出しなし・HEAD 実測)

コマンド: `M11_INSTR_413060=1 M11_OV_413060=1 M11_NEG_413060=0 M11_DEST_READ=0 bash m11_build.sh` → `M11_INSTR_413060=1 M11_SURVEY_COST=<out> node m11_survey.mjs`。build real 18.679 s・survey real 16.307 s・load 1.02 (開始) / 1.01 (終了)。

- 結果: `{"units":942,"ok":870,"noproc":1,"miss":47,"trap":24,"clobber":0}`。unit 158 は ok で、`f413060_units` は `158:0x26d1a0:28` (呼出し 28)。
- 所見: 読出しなし ON では全体 survey の unit 158 は ok。c171b9dc での値と計数が一致する。

### 5.2 unit 158 の trap 最上位 frame (受入条件 2・HEAD 実測)

`SV_ONLY=158 SV_RAW=1 node trap_triage/survey_units.mjs <out>` (単独実行・計測 ON・読出しあり) で frame を取得した。同一構成を 2 回実行し、`kind` と `frames` の全列が一致した。

- kind `oob` (memory access out of bounds)。最上位 wasm frame: **`function_407a50__lifted`** ← `function_407a50` ← `function_409410__lifted` ← `function_409410` ← `function_412c20` ← `function_414ad0` ← `function_414bb0` ← `function_652500` ← `function_653660` ← `function_6539e0` ← `function_665bd0` ← `function_66d050` ← `function_66d1a0` ← `m11_tr_function_66d1a0` ← … (以降は `m11_icall` 経由。全列は run の JSON `frames` にある)。
- 注意: この frame は単独実行での値。記録あり ON の全体 survey では unit 158 の frame を取っていない (§6 の未解決表 (記録あり ON の全体 survey))。全体 survey の trap 位置と一致する保証はない (5.3)。

### 5.3 単独実行で unit 158 はすべての構成で trap (HEAD 実測)

`SV_ONLY=158` で unit 158 を単独実行した。各構成は build し直してから、2 回ずつ実行した。

| build | 1 回目 | 2 回目 | 最上位 frame 列 (1 回目と 2 回目) |
|---|---|---|---|
| 計測 ON (`M11_OV_413060=1`・`M11_DEST_READ=1`) | oob | oob | 一致 |
| 計測 ON (`M11_OV_413060=1`・`M11_DEST_READ=0`) | oob | oob | 一致 |
| 計測 OFF (`M11_OV_413060=0`・`M11_INSTR_413060=1`) | oob | oob | 一致 |
| 既定 ON (`M11_OV_413060=1`・`M11_INSTR_413060=0`) | oob | oob | 一致 |
| 既定 OFF (`M11_OV_413060=0`・`M11_INSTR_413060=0`) | oob | oob | 一致 |

- 5 構成すべてで unit 158 は `oob`、最上位 frame は `function_407a50__lifted`。同一構成の 2 回で frame 列も一致した。
- したがって **単独実行 (`SV_ONLY=158`) では unit 158 は計測 (記録の書込み・読出し) にも dest 値差にも依らず trap する**。全体 survey では ok (OFF・読出しなし ON) / trap (読出しあり ON) になるため、全体 survey の結果は計測構成に依る (5.1 と REPORT_944 の survey 結果)。
- 全体 survey の ok/trap は**先行 unit の実行による状態** (heap・shadow stack・先行 unit が残す値) に依存すると読むのが自然。§7.2 の「記録の副作用が trap を作る」推論は、単独実行の結果と整合しない。

### 5.4 この節で言えること・言えないこと

- 言える: 読出しなし ON で全体 survey の unit 158 は ok (5.1)。unit 158 の単独実行の最上位 trap frame は `function_407a50__lifted` (5.2)。unit 158 は単独では 5 構成すべてで trap し、同一構成の 2 回で frame 列が一致する (5.3)。
- 言えない: j=12 の値差 (`len 0→1`) が後続の結果を変えるか。全体 survey と単独実行で結果が違うため、「記録が trap を作る」「値差が trap を作る」のどちらも確定しない。
- 未解決: 全体 survey で先行 unit のどの状態が unit 158 の ok/trap を分けるか (受入条件 1 の IR 突き合わせに含める)。記録あり ON の全体 survey での unit 158 の trap frame。

### 5.5 測定 commit と鮮度 (WORKFLOW §6・#1268)

`c171b9dc` から `a22c1aef` までの `tools/m11` の差分は 15 files (463 insertions / 44 deletions) で 0 ではない。測定経路 (`m11_build.sh`・`m11_survey.mjs`) を含むため、HEAD `a22c1aef` で再測定した (5.1〜5.3)。再測定の計数は c171b9dc の値と一致した (repro_1389 PASS: OFF 227 件・OFF 再実行と完全一致・ON 216 件・差 1 件 `0x26d1a0` j=12。読出しなし ON の survey: `870/1/47/24/0`)。既定 build (`M11_INSTR_413060=0`) の全体 survey は HEAD で未実行。

| ファイル | c171b9dc からの差分 | 測定結果への影響 |
|---|---|---|
| `m11_build.sh` | `M11_RT_INSTR`・`M11_OV_INSTR`・`M11_LINK_INSTR` 追加、stamp 変更、EXPORTS の dest_obs 条件 | 測定経路。HEAD で build し直して再測定済み (5.1〜5.3 と repro_1389) |
| `m11_survey.mjs` | `dest_obs_n`・`dest_obs_hash` の出力を `mod._m11_dest_obs_n` の存在で条件化 | 測定経路。HEAD で survey を実行済み (計数 870/24 が c171b9dc と一致) |
| `shimx_link/build.sh`・`gen_link.py`・`trace_rt.c`・`probe_unit23.mjs` | 変更あり | 測定経路から呼ばれない (`m11_build.sh`・`m11_survey.mjs`・`m11_gen_ir2.sh`・`m11_ptrcheck.mjs`・`repro_1389.sh`・`cmp_1389.py`・`survey_units.mjs` に参照なし) |
| `ldfix/REPORT_911.md`・`REPORT_911_APPENDIX_1967.md`・`REPORT_942_APPENDIX.md`・`uprobe_1967.sh` | 変更・新規 | 測定経路から呼ばれない。`m11_gen_ir2.sh` が呼ぶ `ldfix/ldfix.py` は差分 0 |
| `trap_triage/repro_1701_rt_ov.sh`・`REPORT_1701.md`・`REPORT_882.md` | 新規・変更 | 測定経路から呼ばれない (文書・別測定の再現スクリプト) |
| `trap_triage/REPORT_944.md`・`REPORT_APPENDIX_944.md` | 文書 | — |
| `repro_1389.sh`・`cmp_1389.py`・`m11_gen_ir2.sh`・`m11_ptrcheck.mjs`・`survey_units.mjs` | 差分 0 | — |

- 測定経路 (列挙したファイル: `m11_build.sh`・`m11_survey.mjs`・`m11_gen_ir2.sh`・`m11_cond.py`・`ldfix/ldfix.py`・`trap_triage/repro_1389.sh`・`trap_triage/cmp_1389.py`・`trap_triage/survey_units.mjs`・`trap_triage/m11_ptrcheck.mjs`) の差分は 0 行 (`git diff --stat a22c1aef HEAD -- <列挙ファイル>` の出力が 0 行)。
- `a22c1aef..HEAD` の `tools/m11` 全体の差分 (`git diff --stat a22c1aef HEAD -- tools/m11`・30 files) は、main 取り込み由来の非測定ファイルを含む。非測定のコード: `ldfix/window_survey_1980.py`・`shimx_link/survey_frames.mjs`・`trap_triage/state_158.mjs`・`trap_triage/writers_2118.mjs`・`trap_triage/n139_writers.py`・`trap_triage/watch_range_2118.c`・`trap_triage/ablate_2131.py`・`trap_triage/mask9b_measure.py`・`trap_triage/probe1676_u114.mjs`・`trap_triage/probe1676_watch.mjs`・`trap_triage/ov_1602_probe_r2.patch`・`m11_sdiv_variant.py`。ほかは文書と結果ファイル。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 158・j=12 の値差の後続経路 (呼出し元・後続の読出し) の IR 突き合わせと、ON trap の最上位 frame の取得 | 値差が結果に効くかの確定 (受入条件 1) | #2003 ([M11-N132]) |
| 記録あり ON の全体 survey での unit 158 の trap frame (5.2 は単独実行の frame) | 全体 survey の trap 位置と単独 frame の一致の確認 | #2003 に含める (未起票) |
| issue 本文の `M11_DEST_GUARD=1` は repo に存在しない | 検証方法の記述が無効 | #1858 の merge で解消 (PM 判断済み) |

## 7. #1864 追記 (旧 §9・番号を通し直した): unit 158・j=12 の dest 値差の切り分け (部分)

測定 commit: **`576c4976`** (origin/main。本節の作業では m11 のコードを変えていない。一時の計測変更は全て破棄)。
`git diff 576c4976 HEAD -- tools/m11` は本節の文書追記のみ。

### 7.1 再現 (同一 build 内・決定性)

コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/trap_triage/repro_1389.sh` (OFF → OFF 再実行 → ON・直列・単発)。判定 `PASS`。全体 1 分 51 秒 (`time` の real・load 開始 0.87 / 0.93 / 0.96)。
- OFF 2 回: 記録 227 件が完全一致 (決定的)。
- OFF/ON: 記録 227 件に対し、ON は 216 件 (unit・順番で揃った 216 件中の差分 1 件)。差は unit `0x26d1a0` の j=12 のみ。OFF `{st 0, len 0, rc 0}` / ON `{st 1, len 1, rc 1}`。

### 7.2 読出しの副作用の切り分け (一時変更・測定後に破棄)

`m11_dest_obs` の読出し・記録を 3 通りに分けて、ON の survey を取った (全て `M11_INSTR_413060=1`・`M11_OV_413060=1`):

| 構成 | ok | trap | unit 158 | 読出し境界外 (st=3) | 備考 |
|---|--:|--:|---|--:|---|
| 記録あり (既定の計測) | 869 | 25 | trap | — | §8 と一致 |
| 記録あり・境界チェック付き (dest 範囲外を検出) | 869 | 25 | trap | 0 件 (216 件中) | dest の範囲外アクセスではない |
| 読出し 1 回のみ・記録なし | 870 | 24 | **ok** | — | 下表の比較で unit ラベル差 0 |

- `units_off.json` (OFF) と `units_readonly.json` (読出し 1 回のみ・記録なし) を 942 unit で比較: **差 0 unit**。
- よって ON の trap は、dest の読出しでも範囲外アクセスでもなく、**記録の書込み (`g_rec_*`・`g_dest_h` への書込み) が計測副作用として unit 158 の結果を変えている**と読める。
- この結論は「読出し 1 回のみ」の ON が 870/24 に戻ることからの推論。`g_rec_*` の線形メモリ上の配置は未確認 (`llvm-nm` で wasm のシンボル表を引けず、未切り分け)。

### 7.3 受入条件の判定 (#1864)

1. **値差が結果に効くか (未確定)**: 読出しのみの ON では unit ラベルに差が出ない (§7.2)。ただし、値差 (j=12 の `len 0→1`) が後続の呼出し・読出しを変えるかは、IR で `0x26d1a0` の後続経路を追うまで確定しない。**未達**。
   - #1945 (測定 commit `e5e3c7c2`): 観測副作用の可能性が高い (詳細は [REPORT_APPENDIX_944.md](REPORT_APPENDIX_944.md) §3)。
   - #2056 (付録 §8): unit 158 は先行 unit 1 (`0x1ce10`) の残す heap/global の 2 区間 (`0xfa5108`〜・`0x11e69b0`〜) の状態に依存する (最小集合で確認)。2 区間を書く関数と後続経路の IR 突合は未了。
2. **REPORT §7.3 追記・§4(a) 更新**: 本節 §7.3 で判定の材料を更新。意味的差か観測副作用かの結論は**未達** (上記 1 が未確定のため、§4 (a) は「観測の副作用が trap を作ることは確認。値差の結果への寄与は未確定」に留める)。
   - **#2003 による訂正**: 上の「副作用が trap を作ることは確認」は**撤回**する。unit 158 を単独 (`SV_ONLY=158`) で実行すると、計測 OFF・既定 OFF を含む全 5 構成で trap する (最上位 frame `function_407a50__lifted`・各構成 2 回)。全体 survey の ok/trap は先行 unit の状態に依存すると読むのが自然で、観測副作用は確認されていない。測定は [REPORT_APPENDIX_944.md](REPORT_APPENDIX_944.md) §5 (測定 commit `a22c1aef`)。
3. **決定的な測定と実測値**: 9.1 の OFF 2 回一致・所要時間・load を記録。**達成**。

## 8. #2056: unit 158 の ok/trap を分ける先行 unit の状態 (受入条件 1 の一部)

測定 commit: 本節の作業で `m11` のコードは変えていない (`trap_triage/state_158.mjs` を追加のみ)。
素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`)・`work-m11`・`toolchain-emsdk`。`m11_gen_ir2.sh` を 46 s で再実行 (ldfix F1=902 F3c=36 errors=0)。
既定 build: `env -u M11_INSTR_413060 M11_OV_413060=0 M11_NEG_413060=0 bash m11_build.sh` (21 s・`boot_final3.ll` md5 `baa100ff…`)。

### 8.1 結果 (実測)

| 構成 | unit 158 | 全体 (ok/trap) | 備考 |
|---|---|---|---|
| 既定・全 942 unit | ok | 870/24 | §0 の基準と一致 |
| 単独 `SV_ONLY=158` | oob (`function_407a50__lifted`) | — | 先行 unit なし |
| 先行 `0..n-1` + 158 (n=0〜157) | n=0,1 のみ oob・n=2〜157 は全て ok | — | 全 158 点で 1 分 07.8 s (直列・単発) |
| `SV_SKIP=1` (unit 1 だけ除外) | oob | 763/122 (oob) | unit 1 が必要 |
| `[0,158]` / `[1,158]` / `[0,1,158]` | oob / ok / ok | — | 先行は unit 1 で足りる |

- unit 1 (`0x1ce10`) は `getmem`・`freemem` が 0 で、heap は確保せず、**メモリ状態だけを残す**。
- boot+unit 0 の後と boot+unit 0+unit 1 の後の HEAPU8 を比較 (差分 2,421 dword)。差分は heap (`0x11e6xxx`)・globals (`0xfa5xxx`)・shadow stack 残骸 (`0x10a9f7xx`/`0x1029xxxx`) の 3 領域。
- 差分を連続区間にまとめると 18 区間 (20 KB)。全区間の重ね書きで unit 158 は ok。区間を 1 つずつ外す試験で、外すと trap に戻るのは 2 区間のみ:
  - `0xfa5108`〜`0xfa5c64` (2,908 B): 0x40 stride の list 状構造 (自己参照ポインタ・`0x73300b30` の sentinel)
  - `0x11e69b0`〜`0x11e6b94` (484 B): 4 バイト単位の ASCII 片 (`0x6c65746e`・`0x49656e69` の繰返し。リトルエンディアンで `"ntel"`・`"ineI"`。定数表か文字列片かは未確認)
- 最小集合は上の 2 区間の**両方**。片方だけでは trap。全域 (boot+0+1 の全域) の重ね書きで ok。
- 再現スクリプト: `trap_triage/state_158.mjs` (`dump <pre> <out.bin>` / `overlay <lo-hi,...> <dump.bin>`)。
  `node state_158.mjs dump 0,1 mem.bin` → `node state_158.mjs overlay fa5108-fa5c64,11e69b0-11e6b94 mem.bin` = `ok`、`overlay none` = `trap`。

### 8.2 未確定 (次の run へ)

1. **2 区間を書く関数の特定 (受入条件 1 の残り)**: `work/scan_index.json` の riprefs は wasm 相対オフセットで、VA との対応を未確認 (本節では対応付けを行っていない)。`0xfa5108` を参照する候補は `0x7a50`・`0x8970`・`0x90e0`・`0x9230`。
2. **unit 158 が 2 区間を読む経路 (受入条件 2)**: 未着手。j=12 の dest との関係も未確定。
3. **§9.2・§9.3 の訂正**: 「記録の副作用が trap を作る」と「値差が効く」のどちらが正かは未決。上の結果は、unit 158 が**先行 unit の残す 2 区間の状態に依存する**ことを示す。ON の記録 (`M11_DEST_READ=1`) が同じ 2 区間を書換えるかは未確認。書換えるなら、観測副作用は「heap/global の割付を変え、2 区間の状態を壊す」経路になる。
4. 既定 build (`M11_OV_413060=0`) は unit 158 が ok で、先行 unit 1 の状態に依存する。ON 版の trap 条件 (記録あり) の再現 (`repro_1389.sh` PASS・OFF 2 回一致・dest 差 1 件) は §8 のとおり。

### 8.3 決定性・所要 (受入条件 4・本 run で再実測)

`bash trap_triage/repro_1389.sh` (OFF → OFF 再実行 → ON・直列・単発): 全体 1 分 43.0 s (`time` の real)・判定 `PASS`。survey elapsed は OFF 15.176 s / OFF 再実行 15.000 s / ON 15.349 s、load 開始 1.52 / 1.29 / 1.17。
`cmp_1389.py`: OFF と OFF 再実行は記録 227 件が完全一致 (差 0)。OFF と ON は 216 件の突合で差 1 件 (`0x26d1a0` j=12、`st`・`len`・`rc`・`h` の 4 フィールド)。注: 本 run では `repro_1389.sh` の後に既定 build (`M11_OV_413060=0`) を再ビルドして §8.1 を測った。したがって §8.1 の 2 区間の結果は既定 build 上の値で、§8 の計測 build (`M11_INSTR_413060=1`) の値とは別物。
注: 既定 build の `boot_final3.ll` md5 は `baa100ff…` で、§0 の `4fd74f…` と一致しない。`m11_gen_ir2.sh` を本 run で再実行した IR から作ったため (§7 の `7304232a…` と同じ種類の差。原因は未切り分け)。計数 870/24 は §0 と一致。

## 9. #2118 追記: 2 区間を書く先行 unit 1 の関数 (M11-N139・部分・旧 本体 §10)

測定 commit: **`637b70de`** (origin/main。本節の作業では m11 の既存コードを変えていない。追加は `n139_writers.py`・`watch_range_2118.c`・`writers_2118.mjs` の 3 ファイル)。
素材: `fl-win64`・`work-m11` (`m11_gen_ir2.sh` で `ir_conditions.json` 生成 F1=902 F3c=36 errors=0)・`toolchain-emsdk`。既定 build の `boot_final3.ll` md5 `baa100ff37a790dc1103c26a2e648d12` (REPORT_944 §6 と一致)。

### 9.1 2 区間の再現 (既定 build・`state_158.mjs`)

`dump 0,1` → `overlay fa5108-fa5c64,11e69b0-11e6b94` = `ok`、`overlay none` = `trap:memory access out of bounds` (REPORT_944 §6.1 と一致)。

### 9.2 静的解析 (IR・直接 call のみ)

`n139_writers.py` は unit 1 (`function_41ce10`) から直接 call で到達する 19 関数を辿り、絶対定数 (`inttoptr (i64 N)`) で 2 区間に触れる関数を列挙する。
- 書込み: `function_4090e0` (0x11e6b88/0x11e6b90)・`function_41ca50` (0x11e6a30)・`function_41ce10` (0x11e6a28/2c/38)。
- 読込み: `function_409070`・`function_4090e0`・`function_409bf0`・`function_40d1f0`・`function_41ce10`。
- **限界**: 第 1 区間 (`0xfa5108`〜) への書込みは store の宛先が計算値で、定数では見えない。また indirect call 先は辿らない。下の実行時計装で補う。

### 9.3 実行時計装 (unit 0・1 の実行・store 直後の監視)

`watch_store_682.py` (全 54,041 store 計装) + `watch_range_2118.c` (範囲版 `m11_sw`) で、unit 0・1 の実行中に 2 区間へ書く store を site 単位で記録した (`writers_2118.mjs`・`M11_KEEP_BOOT_O=1`)。

| 区間 | 書込み件数 (unit 0 / unit 1) | 書込み関数 (IR 行) |
|---|---|---|
| A `0xfa5108`〜`0xfa5c68` | 0 / 321 | `function_4090e0` のみ (IR 行 109818〜109881・7 site) |
| B `0x11e69b0`〜`0x11e6b98` | 0 / 347 | `function_409070` 326 件 (行 109765・`store i8`)・`function_40f4b0` 15 件 (行 115082/115086)・`function_4090e0` 2 件 (行 109897/109899)・`function_41ca50` 1 件 (行 130213)・`function_41ce10` 3 件 (行 130275/130307/130308) |

- unit 1 だけが両区間を書く。unit 0 は書かない (REPORT_944 §6.1 の「unit 1 が必要」と整合)。
- 計装 build の unit 158 は trap する (A 版・B 版の両方で `trap`)。これは計装の副作用で、clean build (計装なし) の `0,1,158` = `ok`・`0,158` = `trap` と一致する。計装版の値は書込み元の特定にだけ使い、判定には使わない。
- 計装版の unit 158 が 2 区間の外に書く 2 件 (`0x11e6b88`/`0x11e6b90` = `10ab0000`) は、unit 158 自身の書込みで、先行 unit 1 の書込みとは別。

### 9.4 受入条件の進捗 (#2118)

1. **2 区間を書く関数の特定 (部分達成)**: 書込み元は §9.3 で unit 単位に特定した。**未達**: unit 158 の後続経路 (呼出し元・後続の読出し) と j=12 (`dest` k=148) が 2 区間に触れるかの突合は未了。
2. **ON 記録 (`M11_DEST_READ=1`) が 2 区間を書換えるか**: **未達**。`repro_1389.sh` (OFF・OFF 再実行・ON) は PASS (REPORT_944 §8 と一致) したが、ON の 2 区間への書込みの計装測定は未実施。
3. **REPORT_944 §4(a)・付録 §7.3 の結論**: 結論 (意味的差 / ビルド差 / 観測副作用) は**未決**のまま。本節の 9.3 は、先行 unit 1 の 2 区間書込みを関数単位で確定した材料。
4. **決定性・所要・load**: `repro_1389.sh` の全体 1 分 26.5 s (`time` の real)・load 開始 0.75 / 0.85 / 0.90・OFF 2 回の計数・dest 記録は REPORT_944 §8 と一致し PASS。

### 9.5 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 158 の後続経路 (読出し) と j=12 dest (k=148) が 2 区間に触れるかの IR 突合 | 意味的差か観測副作用かの判定 (REPORT_944 §4 (a)) | 子 issue (#2118 の残り・本 run で起票) |
| ON 版 (`M11_DEST_READ=1`) で 2 区間への書込みを計装測定する | ON が 2 区間を書換えるかの確定 (受入条件 2) | 同上 |
