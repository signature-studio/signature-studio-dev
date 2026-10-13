# 付録: M11 REPORT §8 (LB_BASE=0x10000 適用 #222) / §9 (sigfix 0 詰め #131) / §12 の一部 (#513 新規類型の行案) — tools/m11/

> **正本**: `tools/m11/REPORT.md`。本書は 250 行上限 (`docs/DOC_MAP.md` §1) のため、本体から**そのまま分割移動**した §8・§9 の全文と §12 の一部
> (節見出し・表・数値は無変更。節番号は本体の参照と一致)。§8 の移動元: PR #411 (#132) の REPORT 整理 / §9 の移動元: #513 の REPORT 追記 (§9 は #131 の記録) / §12 の一部の移動元: #513 と main の §11 (#572) の統合時。

## 8. LB_BASE=0x10000 適用 (#222, 達成: 静的層 + `m11_e2e.sh` 実行で LB=0 と同水準を確認)

既知類型との関係: 該当なし (関連: DEFECTS.md D11 = PE VA リテラルの wasm32 切捨て。本件は VA→LVA 規約の変更で別件)。

`M11_LB_BASE` (既定 0 = 従来 LVA=RVA / `0x10000` で LVA=RVA+0x10000) で全層を切替可能にした。既定 0 は従来と byte 一致。

| 層 | 変更 |
|---|---|
| `lb_base.py` | `M11_LB_BASE` の単一定義 (64KiB 境界を assert) |
| `m11_image_gen.py` / `m11_data_gen.py` | reloc 補正 `-0x400000` → `-0x400000+LB`、image 先頭に LB 分の 0 領域 / data の memcpy 先に +LB |
| `m11_passes.py` | IR の VA→LVA remap (M1/M2/M2b) の差分 `BASE_VA = 0x400000 - LB` |
| `m11_ov.c` `m11_rt.c` `shimx_link/trace_rt.c` | 手書き RVA 定数 (`R()` 経由)・icall 表引き `target+(0x400000-LB)`・`hinst` を `-DM11_LB_BASE` で補正 |
| `ldfix/ldfix.py` `ldfix/halt0_map.py` `shimx_link/analyze.py` `run_trace.mjs` | LVA↔VA 換算に LB を反映 |
| `m11_build.sh` / `m11_e2e.sh` | `-DM11_LB_BASE`・stamp 不一致時の再生成/拒否・GLOBAL_BASE 衝突 assert・`lb_check.py` 実行 |

`m11_bounds.py` / `m11_tail.py` / `m11_icall_audit.py` は VA 空間 (LB 非依存) なので変更不要。GLOBAL_BASE 0x10000000 は image 終端 0x18c0000+0x10000 より後ろで変更不要 (assert 済み)。initial 288MiB / max 1.8GiB も未変更。

### 実測 静的層 (コミット済み HEAD `95054de`, FLEngine_x64.dll 22,227,016 B)

| 項目 | 実測 |
|---|---|
| DIR64 reloc 総数 / 指す先 RVA<0x10000 (LB 適用前) | 278,531 / 55,929 (`lb_check.py` が別実装で再計算し `audit_va.py` と一致) |
| LB=0x10000 適用後 linear<0x10000 の reloc 先 | **0** (全 278,531 が >=0x10000; 値は `v-0x400000+0x10000` と全件一致, 不一致 0) |
| 非 reloc バイト不一致 / 先頭 64KiB の非 0 バイト | 0 / 0 |
| LB=0 の image | 旧 `m11_image_gen.py` 出力と `cmp` 一致 (22,515,781 B) |
| LB=0x10000 の image | 22,581,317 B (+65,536 B) |
| 実行 (HEAD, n=3, load 0.17–0.36, 直列) | image_gen + lb_check: 8.21–8.40 秒, 3/3 PASS |
| ネガティブコントロール | reloc 1 件の LB 補正を落とすと `dir64_value_mismatch=1` で FAIL; LB=0 image を LB=0x10000 で検査すると FAIL (長さ不足) |
| IR remap pass 単体 | 試料 IR で store 即値 4096 (LB=0) → 69632 (LB=0x10000) を確認 (全 IR での件数は未計測) |

再現: `M11_LB_BASE=0x10000 python3 tools/m11/m11_image_gen.py <PE> && uv run --with pefile python tools/m11/lb_check.py <PE> work/m11_image.bin 0x10000`

### IAT 738 スロット (要確認項目 4)
全 738 スロットは `.idata` 内の hint/name RVA を持ち (IAT==ILT 738/738, by-name 738)、`.reloc` に載るのは 0 件、image 範囲値に見えるのは RVA を VA と誤認しているだけ。m11 の image は `.idata` を敷設せず (`KEEP` に無し)、`m11_genstubs.py` / `m11_win.c` は IAT を参照しない (grep 0 件; Win32 は IR の declare 名で stub 化)。**LVA 化への追従は不要**。`audit_va.py` の IAT 判定 (exit 1) は Delphi 側ではなく PE 標準の bound 前 IAT の誤検知で、FLEngine には不適。

### 実測 `m11_e2e.sh` (LB=0 vs LB=0x10000; コミット済み HEAD `3162415`)
GitHub Actions runner (4 core, load 0.6–0.9)。素材は work-m11 スナップショット (lift 成果物 `boot*.lift.ll` は LB 非依存で再利用; `gen_ir2` で IR の VA→LVA remap・data/image・emcc 増分ビルド・実行 A/B を再実行)。各 1 回, 直列。

| 項目 | LB=0 | LB=0x10000 |
|---|---|---|
| `m11_e2e.sh` 所要 (実行 A/B 込み) | 38 秒 (boot/data 等の全 obj を emcc; gen_ir2 は直前の失敗実行で済) | 61 秒 (gen_ir2 + 全 obj を emcc) |
| lb_check | PASS | PASS (linear<0x10000 の reloc 先 0) |
| 到達 stage | 4/6 | 4/6 |
| 通常起動 | unit 17/942 完走後 `memory access out of bounds` | 同 |
| FastMM4 (通常起動) GetMem / FreeMem / VirtualAlloc | 13 / 1 / 3 | 13 / 1 / 3 |
| survey ok / noproc / miss / trap | 812 / 1 / 46 / 83 | 812 / 1 / 46 / 83 |
| trap 内訳 (OOB / Halt0 / abort) | 34 / 48 / 1 | 34 / 48 / 1 |
| wasm サイズ / image | 6,010,298 / 22,515,781 B | 6,010,681 / 22,581,317 B |

**stage 進行・survey 集計は一致**。unit 別 (942 本) に結果種別 (ok / noproc / miss / trap 種別) を比較すると差 0 (frame idx は unit 477 の `5385`→`5386` のみ。LB 依存の関数番号ずれで、同一 unit 477 の trap 種別は OOB のまま)。unit 別の副次カウンタ (GetMem / VirtualAlloc / stub 呼出) の差は 2 unit のみ:
* unit 745 (VA 0xacb3b0, `function_ebb3b0`): LB=0x10000 だけ `SelectObject` stub が 3 回追加で呼ばれる (stub は 0 を返して継続; どちらも後続で OOB trap し種別は同一)。呼出元は未特定。原因 (LB 依存の分岐か、未初期化読みの値差か) は未調査。
* unit 873 (VA 0xe61210): LB=0 は `VirtualAlloc` 1914MB 要求が 2GiB 上限で OOM → NULL → `Halt0`、LB=0x10000 は VirtualAlloc 要求自体が無く `Halt0` (どちらも Halt0→longjmp で種別同一)。要求サイズが LB で変わる原因は未調査。
どちらも終了種別は不変で、集計 (ok 812 / trap 83) には影響しない。

ネガティブコントロール (wasm と image の LB 不一致が実行で検出できること = 比較が鈍感でないこと):
| 組合せ | 通常起動 | survey |
|---|---|---|
| wasm LB=0x10000 + image LB=0 | `init_count` 0, `units_run` 0, icall_miss 717 | ok 0 / miss 920 / noproc 21 |
| wasm LB=0 + image LB=0x10000 | `units_run` 8, icall_miss 12,213, OOB | ok 2 / miss 939 |

再現 (m11_build.sh は `llvm-nm` を PATH から引くので `export PATH=/opt/emsdk/upstream/bin:$PATH` 相当が要る。runner では emsdk_env.sh が `llvm-nm` を PATH に載せず build が rc=127 で FAILED になるため `llvm-nm` の symlink を PATH に置いた): `M11_LB_BASE=0x10000 bash tools/m11/m11_e2e.sh` (PE パスは `/home/ubuntu/work/...` ハードコードのため symlink で回避)。

### 軽微修正 (本 PR の同梱)
* `lb_check.py`: image が `LB + 節末` より短いとき `struct.error` になっていたのを、先に長さを判定して `errors` を出し FAIL (exit 1) するよう修正 (長さ 1000 B の image で FAIL 出力を確認)。
* `ldfix/ldfix.py` / `ldfix/halt0_map.py`: `M11_LB_BASE` の個別 parse をやめ `lb_base.py` (`LB`, `IMG_BASE`) を使う。`M11_LB_BASE=0x10000` で `ldfix.BASE == 0x3f0000` を確認。

### 未検証 / 範囲外
* 全 IR での remap 件数・実行後の guest ポインタ assert は未計測 (stage / survey が一致することで代替確認)。IR の VA→LVA remap の regex (`m11_passes.py` M2b) は VA 側を見るので LB 非依存の見立ては、e2e 結果と整合 (補正漏れがあれば上記ネガティブコントロールのように崩れる)。
* `#221` (liftlib `dataimage.py:37` フィルタ) は別 issue のまま。
* 上記 unit 745 / 873 の副次差の原因調査は未実施 (集計に影響しないため本 PR の範囲外)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 745 / 873 の副次カウンタ差 (SelectObject 3 回 / VirtualAlloc 要求有無) の原因 | 集計には無影響。LB 依存の分岐が残っていないかの確認 | #222 コメントに記録 (未起票。要なら PM が起票) |
| `audit_va.py` の IAT 判定が FLEngine で常に exit 1 | CI 検査に使えない | #91 にコメント (PE 標準 IAT は除外すべき) |

---

## 9. sigfix 0 詰めの計測・機械語分類・定数復元 (#131, 部分達成)

既知類型との関係: 該当 (icall §4 の `callsite_arg_drop` = liftdiff 分類、`ldfix/REPORT_APPENDIX_AB.md` 優先 1)。`docs/DEFECTS.md` D1〜D16 に直接の行は無く、D7 (stack 引数のずれ) は別件 (新規行案は下記)。

### 計測 (コミット済み HEAD `3e49295`, `bash tools/m11/m11_sigfix_stats.sh`, 3.50 / 3.49 / 3.48 秒, load 0.52, n=3 直列)
単位: **0 詰め site** = `m11_post.py` sigfix が「call site の実引数数 < callee 定義の引数数」で書換えた call (分母: sigfix 書換え 6,675 site)。**0 詰め引数** = 補われた引数の総数。集計は `m11_post.py --pads`。

| 項目 | 実測 |
|---|---|
| 0 詰め site / 0 詰め引数 | **1,049 site / 2,064 引数** (217 callee / 475 caller。位置 0..3 = 1,892、位置 4 以降 (stack) = 172) |
| 既定出力 | 従来の `work/boot_final3.ll` と `cmp` byte 一致 (計測追加で出力不変) |
| 機械語と突合できた site | 1,004 / 1,049 (`no_pdata` 23 = caller が .pdata 区間外、`unmatched` 22 = IR の callee 呼出し数と機械語の直接 call 数が不一致で k 番目の対応が取れない) |

突合済み 1,004 site の 0 詰め引数 1,963 の分類 (`m11_argrecover.py`, capstone の線型 disasm。Win64: rcx/rdx/r8/r9 → `[rsp+0x20+8(i-4)]`):

| 分類 | 引数数 | 意味 |
|---|---:|---|
| callee_unused | 313 | callee 入口の直線部で読む前に全幅書込み (stack 引数は callee 全体に読出し無し)。**0 詰めは無害** |
| set_const | 18 | caller の直前窓 (同一基本ブロック) で定数代入。**復元済み** (`M11_SIGFIX_RECOVER=1`) |
| set_const_xmm_callee | 48 | 定数代入だが callee が xmm0..3 を引数に読む。復元しない (下記退行) |
| set_other | 378 / stack_set_other 32 | 窓内で非定数 (reg/メモリ由来) を代入。SSA 値との対応づけが必要で**未復元** |
| inherit | 1,172 | 窓内で未代入 (caller 引数の素通し/遠方 def)。**未復元** |
| callee_nopdata | 2 | callee が .pdata 外 |

**削減**: 0 詰め引数 2,064 のうち 18 (0.87%) を実値に置換、313 (15.2%) は無害と判定。残り (set_other 378 + stack_set_other 32 + inherit 1,172 + xmm 48 + nopdata 2 + 未突合 101) は意味未保証のまま。残りの site 別一覧: `results/sigfix_zeropad_remaining.tsv` (1,049 行, 引数ごとの分類付き)。1 site が全引数 callee_unused or set_const で**完全解決**するのは 31 site。

### 検証 (実測)
| 項目 | 結果 |
|---|---|
| 別アルゴリズム検算 `m11_argrecover_verify.py` (capstone の regs_access を使わず op_str の文字列で後ろ向き走査) | 復元 18 件が 18/18 一致 (初版 63 件では xor r9,r9 の 64bit 形を検算側が拾えず 10 件不一致 → 検算側の誤りと機械語で確認して修正し 63/63) |
| ネガティブコントロール (値を 3 件 +1) | 15/18 一致・不一致 3 で exit 1 |
| `m11_e2e.sh` (HEAD `3e49295`, `M11_SIGFIX_RECOVER=1`, 31.3 秒 (増分), load 0.88) | stage 4/6, 通常起動 17/942, survey **ok 812 / trap 83 / miss 46 / noproc 1** = 復元なし (60.6 秒, 全 obj 再生成) と同一。trap 内訳 OOB 34 / Halt0 48 / abort 1 も同一。unit 別 (942 本) 比較で差 0 |
| 初版 (定数 63 件復元) | survey **ok 809 / trap 86** に**退行** (unit 838, 882, 885: ok → OOB)。二分探索で `function_c349a0` → `function_6a3d50` の 1 site (rcx=`lea` の ptr 定数) に特定。callee は xmm1..3 を引数に読むが IR に xmm 引数が無く 0 になる (推定: 実在オブジェクトへ xmm=0 で書込みが進み OOB)。xmm 引数を読む callee は部分復元しない規則を追加し、同等に戻った |

つまり**定数復元は survey の数値を改善しなかった** (18 件は ok/trap どの unit にも影響しない)。意味補完の本体 (set_other / inherit の 1,550 引数) は未達。

### 使い方・成果物
* `m11_post.py --pads P.json` (0 詰め site 一覧出力) / `--fixes F.json` (復元適用)。`m11_argrecover.py` (分類+fix 生成)、`m11_argrecover_verify.py` (検算)、`m11_sigfix_stats.sh` (1 コマンド再現)。
* `M11_SIGFIX_RECOVER=1 bash m11_e2e.sh` で復元を有効化 (既定 0 = 従来と byte 一致)。`M11_SURVEY_UNITS=<path>` で survey が unit 別結果 JSON を出す。
* runner では `m11_e2e.sh` の PE パスが `/home/ubuntu/work/analysis/win64/extracted` ハードコードのため symlink で回避 (`m11_build.sh` は `FL_WIN64_DIR` 参照)。

### 新規類型の行案 (DEFECTS.md 形式; 直接編集は PM 判断)
| 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| 0 詰め引数を一部だけ実値化すると退行 | callee が xmm 引数 (IR に現れない) を読むのに整数引数だけ実値化し、callee が実オブジェクトを触って OOB | unit 838/882/885 ok→OOB (survey) | survey の unit 別差分 + 二分探索 | xmm 引数を読む callee は復元対象外 (本 PR) |

### 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| set_other 410 / inherit 1,172 引数の復元 (機械語 reg → IR SSA 値対応のデータフロー; #90 の間接 call 復元と共通基盤) | 0 詰めの大半が意味未保証のまま | #131 に残 (Refs)。新規子チケットは PM 起票 |
| xmm 引数 (xmm_arg_drop) の復元 (IR に xmm 引数が無い) | xmm を読む callee では整数引数だけ復元できない (48 引数) | #131 コメントで PM に提案 |
| `unmatched` 22 / `no_pdata` 23 site | 突合不能 | 同上 |
| #122 差分ハーネスで 0 詰め箇所を優先検証 | 未実施 (本 PR は survey の unit 比較まで) | #131 コメント |

## 12. (REPORT.md §12 から分割移動) #513: 新規類型の行案

### 新規類型の行案 (DEFECTS.md 形式; 直接編集は PM 判断)
| 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| 1 プロセス通算 survey で後続 unit が OOM→Halt0 / 破壊 unit が OOM で隠れる | hog unit 1 本 (無限 alloc ループ) が wasm 上限を使い切る測定バイアス | unit 101 が VA の 99.14%・巻き添え 54 unit; unit 144 の image 破壊が旧測定で不可視 | unit 別 VA/GetMem (`M11_SURVEY_COST`)・oom/clobber 分類 | unit 別上限 + InitTable 検査 + image 巻戻し (本 PR) |
