# 付録: M11 REPORT §8 (LB_BASE=0x10000 適用 #222) / §9 (sigfix 0 詰め #131) / §10b (#132 真因・修正 4 点ほか) / §12 の一部 (#513 新規類型の行案) — tools/m11/

> **正本**: `tools/m11/REPORT.md`。本書は 250 行上限 (`docs/DOC_MAP.md` §1) のため、本体から**そのまま分割移動**した §8・§9・§10b の全文と §12 の一部
> (節見出し・表・数値は無変更。節番号は本体の参照と一致)。§8 の移動元: PR #411 (#132) の REPORT 整理 / §9 の移動元: #513 の REPORT 追記 (§9 は #131 の記録) / §10b の移動元: #516 の REPORT 上限対応 (§10 の「真因」〜「外した内容」を無変更で移動) / §12 の一部の移動元: #513 と main の §11 (#572) の統合時。

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

### 基準 (before) #1430: xmm 引数の callee 署名復元の前測定
既知類型との関係: 該当 (icall §4 の `callsite_arg_drop` = liftdiff 分類、本 §9 の xmm 退行行案の続き)。

測定 commit `7e149974` (origin/main, 本 branch の起点)。`work-m11` は `lift_pe.sha256`・`functions_dll.csv`・`ir_conditions.json` を含まないため `m11_e2e.sh --full` の全再生成経路に入った。`functions_dll.csv` は Ghidra 12.1.4 (公式 zip sha256 `ddac49f9…` 一致) + JDK 21 + `tools/m2/ghidra_scripts/DumpFunctions.java` で作成 (9 分 37 秒、59,010 行)。

| 項目 | 実測 |
|---|---|
| `m11_e2e.sh --full` (`7e149974`) | 626.99 秒 (10 分 27 秒), rc 0, load 0.68 |
| survey (全再生成直後, unit 別 942 本) | **ok 872 / trap 23 / miss 46 / noproc 1** (trap 内訳 OOB 15 / Halt0 7 / unreachable 1) |
| survey (増分再実行, unit 別 JSON 出力) | 46.94 秒, ok 872 / trap 23 / miss 46 / noproc 1 (全再生成直後と一致) |
| 0 詰め site / 引数 (`m11_sigfix_stats.sh`, 同 HEAD) | **1,061 site / 2,084 引数** (argrecover 突合 1,016 site, 突合済み引数 **1,983**。未突合 101 = 2,084 − 1,983。内訳は下表) |
| unit 838 / 882 / 885 | ok / ok / ok (基準の退行チェック対象) |

突合済み引数 1,983 の全カテゴリ (`m11_sigfix_stats.sh` の出力 `work/sigfix_stats/argrecover.txt` の値):

| 分類 | 引数数 | 備考 |
|---|---:|---|
| callee_unused | 313 | |
| inherit | 1,185 | |
| set_const | 18 | |
| set_const_xmm_callee | 49 | |
| set_other | **未取得** | 下記 |
| stack_set_other | **未取得** | 下記 |
| callee_nopdata | **未取得** | 下記 |
| 既知 4 項目の和 | 1,565 | 1,983 との差 418 は上記 3 項目で埋まる必要がある (未確定) |

**未取得の理由**: 本 run の runner には `work/` の入力 (`boot_final.ll`・`functions_dll.csv`) と RetDec・Ghidra・emcc が無く、`7e149974` の全再生成 (`m11_e2e.sh --full`) と `m11_sigfix_stats.sh` を再実行できなかった。上の 3 項目の値は**このファイルでは確定できない**。出力を取得してから表を埋め、和が 1,983 になることを確認すること (未達のまま本 PR を merge しない)。

注記:
* §9 (3e49295) の記録 (1,049 site / 2,064 引数 / set_const_xmm_callee 48 / survey ok 812) とは HEAD の差で数値が動いている。本表は `7e149974` の値で、比較の基準はこちら。
* **差の説明 (inherit 1,172 → 1,185、set_const_xmm_callee 48 → 49)**: `git diff 3e49295 7e149974 -- tools/m11/m11_argrecover.py` の分類ロジックは不変 (`classify_set` の戻り値に `why` を足し、`none` の判定条件は同一)。よって数値差は分類器ではなく**入力側**から来る (`work/boot_final.ll` を作る `m11_passes.py` / `m11_gen_ir2.sh` / `m11_post.py` の変更、または `m11_post.py --pads` の site 列挙の変化)。どの commit が 1,172→1,185 を生んだかは、3e49295 と 7e149974 で `m11_sigfix_stats.sh` を実行して site 単位に突き合わせるまで**未特定** (本 run では入力が無く未実施)。
* 統計スクリプトで `tools/m11/results/sigfix_zeropad_remaining.tsv` が 1,050 → 1,062 行に再生成された (未コミット。再生成物のため本 PR に含めない)。
* 再測定 (after) と `fix_xmm_args.py` の接続は本 run では時間が足りず未実施 (下記の子 issue)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| xmm 引数を読む callee の署名復元 (`fix_xmm_args` 接続 or 同等) と unit 別の after 測定 (unit 838/882/885 を含む) | set_const_xmm_callee 49 引数が未解決 | 子 issue (本 PR で起票) |

---

## 10a. (REPORT.md §10 から分割移動) #132: commit 別の測定表と注記

| commit | 内容 | units_run | 停止理由 (通常起動) | survey ok/trap/miss/noproc | trap 内訳 | GetMem/FreeMem | 所要 / load |
|---|---|---|---|---|---|---|---|
| `2c23bef` | 本 PR 初版 (旧 main 0a9e9d3 上) | 22/942 | DllMain attach 完走 (longjmp 経路) | 817/78/46/1 | halt0 39 + OOB 39 | 28/20 | 100 s / 1.06→1.26 (並行 2 本) |
| `0f22d9c` | main (#414/#447/#481 後) | 17/942 | OOB | 839/56/46/1 | halt0 32 + OOB 24 | 16/1 | 46 s / 1.06→1.65 (並行 2 本) |
| `6ad441d` | 0f22d9c + R8 + 3 override (410b10 無し) | 17/942 | OOB | 841/54/46/1 | halt0 32 + OOB 22 | 8/1 | 45.7 s / 0.26→0.72 |
| `a71a404` | 6ad441d + 410b10 転記 | 22/942 | DllMain attach 完走 | 809/86/46/1 | halt0 72 + OOB 14 | 33/20 | 50.6 s / 0.12→0.66 |
| `c1e4105` | main (#491/#496/#500 後 = 現 origin/main) | 17/942 | OOB | 849/43/49/1 | halt0 17 + OOB 26 | 16/1 | 43 s / 0.51→1.97 (手動 gen_ir2 と並行) |
| **`b760fa2`** | **最終 HEAD** (c1e4105 + 本 PR) | **22/942** | **DllMain attach 完走 (longjmp 経路)** | **816/79/46/1** | halt0 65 + OOB 14 | 33/20 | 50.5 s (gen_ir2+ldfix+alloca+build 込み) / 1.36→1.77; 以降 29.3 / 29.4 / 29.6 s / 1.77→1.54, 1.54→1.32, 1.32→1.20 |
| (NC) `b760fa2` − 410b10 | ネガティブコントロール | 17/942 | OOB | 850/45/46/1 | halt0 20 + OOB 25 | 8/1 | 49 s / 1.18→1.28 |

reached_stage は全行 4/6 (stage 5 未達)。最終 HEAD は 5 回測定 (gen_ir2 から 2 回 + 増分 3 回) すべて units_run 22 / survey 816/79/46/1 / halt0 65 + OOB 14 で一致 (変動なし)。

- 解消したのは **unit #18 の OOB** であり、unit #23 (0x467f00) の **Delphi 例外 (45a2a0, 0xEEDFADE) → Halt0 は未解消** (旧版の表の「例外なし」は誤り)。停止理由「DllMain attach 完走」は Halt0 → longjmp 経路の判定。
- PR 本文の「コードは 499bdfa と同一」は誤りだった。数値の測定コードは上表の commit ごとに別物 (`2c23bef` = 499bdfa と REPORT のみ差。最終は main merge + `410b10` 転記を含む)。
- 最終 HEAD の survey ok (816) は main (849) より少ない。survey は 942 unit を 1 プロセスで通算実行し `VirtualFree` が no-op (leak) のため、VirtualAlloc 累計が上限 (1,490〜1,502 MB) に達すると
  `[m11][VA] OOM` (calloc 失敗 → NULL) になる。この OOM の回数は NC 3 回 (VirtualAlloc 1,101 回) に対し最終 HEAD 55 回 (1,199 回)。`6ad441d` → `a71a404` の unit 別比較 (`M11_SURVEY_UNITS`) は
  ok→trap 33 本 / trap→ok 1 本で、ok→trap の 4 本 (unit 235/265/276/313) のスタックは 409410/409470 (GetMem/ReallocMem) → 409730 (Error) → 412a40 → 4128b0 (Halt0) = GetMem 失敗 → Error → Halt0 と整合。
  unit #18 が完走して消費が増えたためと**推定**するが、OOM を除いた意味の退行の有無は**未切り分け** (起票: #132)。

## 10b. (REPORT.md §10 から分割移動) #132: 真因・修正 4 点・NC・次 blocker・外した内容

**真因 (実測)**: 44bb70 の record (392B, CAB-129 で拡幅済) の +16 が、直前に呼ぶ `function_44bae0` の呼出し前後で 0 → 0x100000001 に変化
(`m11_site` を IR に埋めて前後値を実測)。44bae0 の `stack_var_-88` が `alloca i64` (8B) だが、`call 44ba50(ptr)` で escape し
callee が `[rcx+0x2c..0x3e]` (GetCPInfo の LeadByte 表) に書くため、呼出し元フレーム (= 44bb70 の record) を破壊していた。

修正 (4 点):
1. `alloca/m11_alloca.py` **R8**: escape する `stack_var_-N` を「次の stack_var までの間隔」に拡幅 (**サイズを供給しない推定型の規則**; 契約・数値・過大拡幅の注意は `alloca/REPORT.md` §2)。
   gen_ir2 の素の IR に適用して 4,077 サイト → 2,408 alloca / 1,347 関数, +1,153,849 B stack (最終 HEAD で実測)。R8 だけでは OOB 解消のみ (units_run 17 のまま, unit #18 が Halt0 へ)。
2. `m11_build.sh`: alloca pass を build 時に常設 (idempotent, 内容が同じなら mtime を触らない)。`m11_e2e.sh` の既定経路で pass が掛かる。
3. `m11_ov.c`: `function_412d60` (`_UStrClr`) / `418190` (`_LStrArrayClr` 系) を C 転記 (RetDec が `mov rax,[rbx]` 型の旧値 load を脱落, D1 系)。
   `_CopyArray` 416db0 も初版で転記したが (kind の `movzx rcx,[r8]` 脱落が unit #18 の Halt0 原因)、main の #417 (#496) が同関数を kind 12 (416720 の間接 call) 込みで転記したため、
   merge で本 PR 側を削除し main 版を採用した (kind 12 が src を渡さない Copilot 指摘は main 版で解消)。
4. `m11_ov.c`: `function_410b10` (TMonitor の GetMonitor 相当) を C 転記 (`a71a404`)。RetDec が `mov rax,[rcx]` (obj → VMT) を落とし `[obj-0x80]` を読む (D4)。
   旧 main は `_ClassCreate` が TClass 自身を返したため偶然 InstanceSize になっていた。40fb40 で実オブジェクトが作られると `[obj-0x80]` がヒープ上の任意値になり、
   `410820` (TMonitor.Enter) が LockCount=1 / Recursion=1 / Owner を FastMM の小ブロックプールヘッダ (0x10bd1990: BlockType 0xfa5148 → 0x100000001) に書き、後の `_UStrClr` → FreeMem が OOB (`6ad441d` の停止)。
   逆アセンブル 0x410b10〜0x410b81 と突合。

ネガティブコントロール (実測): (a) 本 PR 無しの main `c1e4105` = units_run 17 + OOB。(b) 最終 HEAD から 4 の `410b10` だけ外した (NC) = units_run 17 + OOB (停止は 455790 → 44bb70 → 446400 → 447860 → 412d60 → 409440 → 407e20; `6ad441d` で同じ停止を確認)。
修正 1〜3 を個別に外した切り分けは**現 main 上では未実施** (旧 main 上の実測: 3 点を外すと units_run 17 + OOB)。検証範囲外: 417b70 / 409470 / 410320 / 40fb40 / 416db0 の機械語突合 (main 側の転記; 本 PR の差分ではない)。

**次 blocker (unit #23 = 0x467f00)**: `467f00 → 467c40 → 45a640 → 45a2a0 → 411e80 → 411d20 → 412a60 → Halt0`。467c40 は
`call [rax]` (IAT 経由の Win32 API, `mov ecx,eax` で戻り値を 45a640 に渡す) の結果で `45a640(ecx, dx=11, r8w=8)` を呼び、ecx が 0 以外・
`0x7ffdfffb` 系でない値のとき 45a2a0 (例外送出, 0xEEDFADE) に進む。`467c40` の IR には間接 call が **0 件** (機械語 0x467cc9 `call [rax]` / 0x467d5d `call [rax]` が丸ごと脱落 = D15 型, `work/icall_audit.json` の
`capstone_fns_with_indirect_call` 系と同じ現象)。脱落した戻り値の代わりに `45a640` へ未定義値 (ecx) が渡り例外送出へ進む可能性が高い (推定)。
`[rip+0x117be27]` の指す IAT スロットの import 名は未特定。

外した内容 (4c3baa4 の 467c40 間接 call 復元・boot5 25 関数 lift・配線 / faee5b6 の 417b70・409470 転記・BSTR スタブ) は #414/#447/#481 と重複するため本 PR に含めない。**#490 ([M11-N15]) で追跡**。

## 12. (REPORT.md §12 から分割移動) #513: 新規類型の行案

### 新規類型の行案 (DEFECTS.md 形式; 直接編集は PM 判断)
| 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| 1 プロセス通算 survey で後続 unit が OOM→Halt0 / 破壊 unit が OOM で隠れる | hog unit 1 本 (無限 alloc ループ) が wasm 上限を使い切る測定バイアス | unit 101 が VA の 99.14%・巻き添え 54 unit; unit 144 の image 破壊が旧測定で不可視 | unit 別 VA/GetMem (`M11_SURVEY_COST`)・oom/clobber 分類 | unit 別上限 + InitTable 検査 + image 巻戻し (本 PR) |

## 12b. (REPORT.md §12 から分割移動 + 追記) #513 残件: 巨大 VirtualAlloc 2 件の n の出所 (確定)

### 旧記述 (PR #521 時点, 無変更で移動。「推定」「未確定」は下の実測で解消)
### 巨大 VirtualAlloc (355MB×2) の呼出元と必要性
現 HEAD では通常起動の VirtualAlloc は 1 回 (1.3 MB) で **355MB×2 は再現しない** (`alloca/REPORT.md` 残置 #5 は R8 等で解消済みの可能性。survey の 64MB 以上要求は下の 2 つだけ, `M11_VA_BIGTRACE=1`):
* unit 368 (0x5810f0=`function_9810f0`) → `980ed0` (ctor; 基底 ctor `6a3be0` は既定 44100 Hz) → `981000` (8 面バッファ確保: size = 8×((8n+31)&~31) ≈ 64n B, n = `*(int32*)(*(u64*)VA 0x15e4080)`) → `409470` → FastMM 大ブロック。**要求 700.7 MB (main) / 190.6 MB (PR)** と build で変わる = 値が不定。n の出所は**未確定** (image 静的値の指す先は 0、実行時の値は未観測。基底 ctor の `call [rbx]` 仮想呼出しの脱落 = D15 の疑いは**推定**)。
* unit 888 (0xeaea40=`function_12aea40`) → `129f140` → `417fc0` → `417b70` → `409470`: 71.3 MB (両 build 同値, 必要性は未確認)。
→ 実機の初期化でこの大きさは要らない (推定)。上限 256MB では unit 368 (main) の 700.7MB 要求が oom 扱いになるため, main と比較するときは 1024MB を使う。

### 実測 (HEAD `77703f6` = main `cf828e9` + 本 issue の probe/検証スクリプトのみ。4 vCPU, PE=fl-win64 `block00031_PE.bin`, capstone+pefile 入り venv)
道具: `m11_vabig_probe.mjs <unit> --pre=0-<unit-1>` (survey と同じ順序で unit 0..N-1 を実行 → 対象 unit 直前の linear 0 / slot / 変数を読み、unit の VirtualAlloc 要求を出す。`--watch=<addr>` `--poke=<addr>=<int32>`) / `m11_vabig_verify.sh` (IR を 1 箇所ずつ直した build 4 構成 + survey)。

**unit 368 (`981000` の n)**
1. 機械語 (`980ed0`): `mov rax,[rip+0xc63165]` = VA **0x15e4080** (RVA 0x11e4080), `mov edx,[rax]` → `981000(self, n=edx)`。image の RVA 0x11e4080 には 8B ポインタ (LVA 0x156ebe8) があり、その指す int32 は **0** (静的値)。survey 順に unit 0..367 を実行した直後 (unit 368 の直前) も `--watch` で **0** のまま (CORRECT_SLOT の n_int32)。正しく remap されていれば n=0。
2. IR (`work/boot_final3.ll`): `%ce0n11_function_980ed0 = inttoptr i64 22954112` = **VA 0x15e4080 のまま (LVA = VA−0x400000 に remap されていない)**。linear 0x15e4080 は image 末尾 (0x1579045) の外で、読むと 0 → rax=0 → `edx = *(int32*)linear 0`。
3. survey 順 (unit 0..367 を実行) で linear 0 の int32 は unit 15/17/22/35/37/95/135/220/232/233 が順に書き換える (書込み元の関数と理由は未特定。本件の n の出所の確定には要らない)、unit 368 直前は **0x2fa020 = 3,121,184**。`size = 8×((8n+31)&~31)` = 199,755,776 → 64KB 丸め **199,819,264 B = 190.6 MB** (PR build の実測 190.6 MB と一致)。
4. main `c1e4105` を、`m11_rt.c` / `m11_survey.mjs` / `m11_judge.py` を本 HEAD の版に差替え (+ `m11_rt.c` 末尾に `m11_trace_isolate` / `m11_stk_save` / `m11_stk_restore` の空定義を足して link) て再 build し、同手順: unit 233 以降 unit 235/265/291/314/365 が linear 0 を書き、unit 365 直後 **0x10af2ba8 = 279,915,432** → size 734,718,464 → 丸め **734,724,096 B = 700.7 MB** (probe の実測 `size=734724096` と一致、上の式の検算も一致)。**700.7MB と 190.6MB は同じ欠陥 (linear 0 を読む) が、そこに残っていた値の違いで変わっただけ**。build ごとに値が変わる理由はこれ (unit が書く null 近傍の値が build で違う)。
5. 因果の確認 (強い操作): (a) probe で linear 0 に 4096 / 100000 を poke すると要求は 64MB 未満 (va_big 0)。(b) 該当 1 行を LVA に直した build (`inttoptr i64 18759808`) では unit 368 の `va_big` 0, `va_calls` 842 (HEAD は 843: VirtualAlloc が 1 回減っただけで、減った理由 (n=0 で 409470 が確保しない等) は未確認)。(c) `M11_M2P=1` (10 進 `inttoptr` 命令の全件 remap, 4,364 件) で再生成した build でも unit 368 は `va_big` 0 (`va_used` 64MB, `va_calls` 19)。
6. 旧記述の「基底 ctor `6a3be0` の `call [rbx]` 脱落 (D15) の疑い」は**原因ではない** (上の 5(b) で 1 行直すだけで巨大要求が消える)。

**unit 888 (71.3 MB)**
1. 機械語 (`129f140`): `mov r9d,[rip+0x33259f]; add r9d,1; movsxd r9,r9d` = VA 0x15d1700 (RVA **0x11d1700**) の int32 + 1 を `417fc0(…, count)` に渡し、`417b70` が 4 B 要素の配列を確保する。
2. IR: `%ce0n11_function_129f140 = ptrtoint (inttoptr 18683649)` = **変数のアドレス 0x11d1701 そのもの (`mov r9d,[rip+x]` の load が落ち、IR は変数のアドレス+1 を渡している)**。18,683,649 × 4 = 74,734,596 → 丸め **74,776,576 B = 71.3 MB** (本 run の HEAD で再現。PR #521 報告では両 build 同値 = main 側は本 run では再測定していない)。
3. 正しく load した場合の値: unit 888 直前の wasm 上の `[0x11d1700]` = **64** (`--watch`) → count 65 → 260 B。
4. 因果: 該当 3 行を `load i32 [0x11d1700] + 1` に直した build で unit 888 の `va_big` 0 (`va_used` が 1,147,994,112 → 1,074,528,256 B)。poke (0x11d1700=7/100000) では要求が変わらない = 値ではなくアドレスを渡している証拠 (ネガコン)。

**構成別 (`m11_vabig_verify.sh`, コミット済み HEAD `77703f6`, 全体 104.48 秒, load 0.42→0.92)**
| 構成 | unit 368 va_big (要求) | unit 888 va_big (要求) |
|---|---|---|
| base (NC) | 1 (190.6 MB) | 1 (71.3 MB) |
| 888 のみ直す | 1 (190.6 MB) | **0** |
| 368 のみ直す | **0** | 1 (71.3 MB) |
| 両方直す | **0** | **0** |
両方直した build の survey: ok 852 / trap 42 / clobber 1 / big_units `[]` / `va_big` 0、unit 別ラベル 942 本が修正なし HEAD と**完全一致 (差 0)**。= この 2 箇所の巨大要求は survey の判定に影響しない (巨大要求が出るのが 2 unit だけで、どちらも ok のまま)。

**#516 / PR #552 (qstore) との関係**: PR #552 の検出結果 `qstore_sites.tsv` (420 行) に今回の 9 関数 (`980ed0` `981000` `129f140` `417fc0` `417b70` `409470` `6a3be0` `9810f0` `12aea40`) は **0 件** = 欠陥類型が別 (qstore = 4B に縮んだ 8B stack store。本件は 368 = 定数アドレスの VA→LVA 漏れ、888 = load 脱落)。#552 で本件の数値は変わらない。
**#418 (`409470` の unit 884 ハング)との関係**: 409470 (ReallocMem) は size を受けて確保するだけで、n / count は呼出元が決める。#418 の原因は `410320` の脱落 (REPORT_418.md) で本件と無関係。HEAD の survey で unit 884 は **ok** (確認済み)。
**同類の残り**: 10 進 `inttoptr` 命令形 4,449 件のうち image VA 範囲の 4,364 件 (942 関数) が未 remap (`M11_M2P` OFF = #417)。`M11_M2P=1` の survey は 90 秒で完走せず (`trap_triage/REPORT.md` §6-2 の unit 503 ハングと同症状。同一原因かは未切り分け) = 全件 remap は未解決で #417 に残る。

**必要性の判断**: unit 368 の 190.6 / 700.7 MB と unit 888 の 71.3 MB は**どちらも不要**。実際に要る大きさは、368 が 0 B (image の静的値 n=0)・888 が 260 B (count=65)。根拠は上の 5(b)(c) と 888 の再 build (要求が消え、survey の unit 別ラベル 942 本が不変)。
**対処**: 上限緩和ではなく IR 修正側の問題。368 は M2p の全件 remap (#417) と同じ類型。本 issue では IR を直さず、原因確定と検証スクリプトのみを入れる (個別パッチは verify スクリプトの `patch_ir` に再現用として持つ)。M11_VA_UNIT_BUDGET_MB の既定 256MB で main の unit 368 (700.7MB) が oom 扱いになるのは、この欠陥の症状。

## 15. (REPORT.md §15 から分割移動) #680: survey 測定基準の固定化 (ldfix/qstore の fail-closed・PE パス env 化)
ldfix/qstore の skip を非 0 終了にし、IR 生成条件と IR の指紋を `work/ir_conditions.json` に記録する fail-closed 化。qstore on / off の差は本 runner の n=2 で再現した。測定値・未解決・環境間一致 (未実測) は [REPORT_N27.md](REPORT_N27.md)。
