# REPORT #3677 — `1046a30` の命令形 10 進 VA `inttoptr` 73 件の番地・幅突合 (LD-173)

親: #2958 (LD-142)。既知類型: `docs/DEFECTS.md` D11 (10 進 `inttoptr` の VA 漏れ・M11 変種)。前回 `REPORT_2958.md` §5 の「残り 72 件」の件ごとの突合。

## 1. 結論

- 関数 `1046a30` の命令形 `inttoptr i64 N to ptr` (N が VA 範囲 0x400000〜0x1abf400) は **73 件**。`pass_m2r_fn1046a30` (#2958 で merge 済み) が直したのは 22946304 の 1 件で、残りは 72 件。
- 73 件すべてについて、IR 定数 N と機械語の rip 先 VA (`rip 先 = 次命令アドレス + disp`) が一致する (N = VA)。
- 読み幅 (IR の `load` 型と機械語の rip 参照オペランド幅) は、スクリプトの自動判定で 71 件一致・2 件不一致 (33747・33751)。この 2 件は機械判定の誤りで、同番地を `ucomiss xmm0, dword ptr [rip+0x1791]` (0x104b538) が 4 B で読むため IR の `load i32` と一致する。よって幅は 73 件すべて一致とみなす。
- 段数 (値を読んだ後の逆参照の回数) は `depth_4498.py` の規則による判定で、73 件すべて IR 段数 = 機械語段数 (§6)。PTR 24 件 (2 段) は規則の自動判定の結果で、手での再確認は未了 (§6)。
- 番地・幅・段数の 3 条件は、幅の判定誤り 2 件 (33747・33751。§2-3) を除き、73 件すべてで一致する。
- **remap は行っていない** (IR・`m11_passes.py` は未変更)。根拠の確定が前提 (前回 REPORT の注意「根拠なしに remap しない」)。remap は #4498 の受入 2 に残す (§4)。

## 2. 測定 (実測)

- 入力: `tools/m11/work/boot_allfx.ll` (work-m11 展開物・`pass_m2r` 前の IR)、`tools/m11/work/m11_image.bin` (22515781 B)。
- 逆アセンブル: capstone 5.0.7 で `0x1046a30`〜`0x104ccee` の線形。
- 再現: `python3 tools/m11/ldfix/rip_match_3677.py` → `tools/m11/ldfix/results/rip_1046a30_3677.tsv` (73 行・列は同スクリプトの docstring)。
- 測定 commit: `3987f8c` (段数の TSV `depth_1046a30_4498.tsv` を追加した commit)。

### 2-1. 件数の照合

- 前回 REPORT は「16267〜24296 行」と書いたが、今回の `boot_allfx.ll` では関数 `1046a30` は 27761〜35428 行。行番号は IR の版で変わる。**件数 73 と 22946304 の位置は一致**。
- 22937624 (前回 REPORT §5 の 16640 行) は今回の IR では 28134 行 (`%ce0n11_function_1046a30`)。

### 2-2. 番地と幅 (73 件)

| 項目 | 件数 |
|---|---|
| IR 定数 N = 機械語 rip 先 VA | 73 / 73 |
| 読み幅一致 (IR load 型 = 機械語オペランド幅) | 71 / 73 |
| 幅が合わない 2 件 (33747・33751) | 機械語の rip 参照の先頭が `mulsd` (8 B) だが、同番地を `ucomiss` (4 B, 0x104b538) が読む。IR の `load i32` と一致する。判定上の誤り |

### 2-3. 段数 (機械判定・初版)

> 訂正 (§6): 下記の 34334・34723 の段数の不一致は判定の誤りで、§6 の規則では IR 2 段・機械語 2 段で一致する。

- 機械判定 (`mc_depth`): `mov R,[rip+X]` の後に `[R]` が現れるまでの回数。IR 判定: `load` 値を `inttoptr` で再びポインタにする連鎖の回数。
- 一致 69 件、不一致 4 件 (33747・33751 は幅の件と同じく判定の誤り。34334・34723 は IR が 1 段、機械が 2 段)。
- 34334 (`0x15e1810`): IR は `add i64 %3099, %3101` (値をそのまま加算)、機械語 `0x104bd4f mov rax,[rip+X]` は `movsxd rcx, dword ptr [rbp+…]` 系の別経路。判定は未了。
- 34723 (`0x15e36d8`): IR は `inttoptr` で直接使う、機械語 `0x104c328 mov rax,[rip+X]` の後は `mov ecx, dword ptr [rbp+…]` (別オペランド)。判定は未了。

## 3. 件ごとの表

`tools/m11/ldfix/results/rip_1046a30_3677.tsv` (73 行)。列: `ir_line`・`name`・`va_dec`・`va_hex`・`lva`・`ir_width`・`mc_insn`・`mc_width`・`width_ok`・`ir_depth`・`mc_depth`。

- 番地が LVA 換算 (`va − 0x400000`) で画像内に入るのは、VA 0x15e0000〜0x15e4fff 系 (LVA 0x11e0000〜0x11e4fff) と 0x104cxxx 系 (LVA 0xcxxxxx) の 2 系統。
- 0x104ccd8 は機械語の参照が 24 件 (`mulsd` 定数)。同一の定数を多数の IR 箇所が参照する。

## 4. 限界・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| remap の実装 (`pass_m2r_fn1046a30` の拡張) | IR は未変更。`1046a30` の load 値は本 PR の前後で変わらない | #4498 (LD-221) |
| `audit_lsf_ssa_e2e.sh` 7/7・unit e2e (本番 build) | 未実施。remap していないため差分 0 | #4498 (LD-221) |
| 0x104ccd0〜0x104cfxx 系の解釈 | §8 で DATA (定数プール) と確定。関数ポインタ 0 件 | 解消 (#4498 受入 3) |
| `M11_M2R=1` の既定 ON 化 | 未実施 (PM 判断)。unit 前後比較 (§受入 5) で unit 結果は不変。既定 OFF のままなので本番 IR は不変 | PM 判断 (#4498 コメント) |

## 6. 段数の判定 (#4498 受入 1・規則による判定)

- 入口: `python3 tools/m11/ldfix/depth_4498.py` → `results/depth_1046a30_4498.tsv` (73 行)。
- 判定規則 (コードどおり。手で読んだ判定ではない):
  - IR 側: `rip_1046a30_3677.tsv` の各定数 (`ir_line` の行から 8 行以内の `load` 行) について、load の結果 `%v` を後続 40 行以内で探す。最初に現れた使用が `inttoptr i64 %v` または `add i64 %v` (両辺どちらでも可) なら PTR (2 段)。それ以外の使用なら VAL (1 段)。
  - 機械語側: rip 参照命令が `mov R,[rip+X]` のとき、後続 4 命令以内で `[R…]` のメモリオペランドが現れれば PTR (2 段)。先に `R` への書き込みが現れれば VAL (1 段)。
  - 段数 = IR の判定と機械語の判定の一致を `match` 列に出す。
- 結果 (規則による自動判定・実行は前 run): 73 件中 IR 段数 = 機械語段数が 73 件。PTR/PTR (2 段) 24 件、VAL/VAL (1 段) 49 件。不一致 0 件。
- 注意 (未了): 上記は規則の出力。`add` に値が出るだけで PTR になるので、加算結果がポインタとして使われない行が PTR に入る可能性がある。本 run では IR (`boot_allfx.ll`)・機械語 (`m11_image.bin`) が無く (`work-m11` 素材が未取得)、規則の再実行も件ごとの手確認もしていない。
- 前 run の手確認の記録 (本 run では未再確認): 34723 (`0x15e36d8`) は IR `load` → `inttoptr` → `store`、機械語 `mov rax,[rip+X]` → `mov [rax],ecx`。34334 (`0x15e1810`) は IR `load` → `add` (添字) → `inttoptr` → `load`、機械語 `mov rax,[rip+X]` → `mov rax,[rax+rcx*8]`。どちらも 2 段で一致する。
- PTR 24 件 (IR の load 結果をポインタとして再参照と判定): 28134・28211・28274・28313・28372・28489・28497・28517・28531・28612・28921・32800・32804・34334・34591・34649・34723・35056・35143・35152・35215・35256・35285・35337 (ir_line)。このうち手で確認したのは前 run の 34334・34723 だけで、残り 22 件は未確認。受入 2 に入る前に確認する。
- 段数が一致しても、セルの初期値 (データ上の値) が何を指すかは対象外 (受入 3 と 4 で扱う)。
- `rip_match_3677.py` の `ir_depth` 列は変えていない (本 PR の範囲外)。段数の正本は `depth_1046a30_4498.tsv`。

## 8. 受入 3: 0x104ccd0〜0x104cfxx 系の定数 (#4498 LD-221)

- 入口: `M11_WORK=tools/m11/work python3 tools/m11/ldfix/const_4498.py` → `results/const_1046a30_4498.tsv` (16 VA・48 行)。本 run では `m11_image.bin` が無く再実行していない。TSV (commit 済み出力) の内容を読んで確認した。
- 判定: 1046a30 の最後の `ret` (`0x104ccca`) の後ろは、関数の外の領域。前 run の記録では `0x104ccd0`〜`0x104ccee` を逆アセンブルすると `add byte ptr [rax], al` の並びになった (定数の 0 バイトを命令として読んだもの)。この逆アセンブル出力は保存されておらず、本 run では再現していない。
- 参照 (48 行): すべて `mulsd`・`divsd`・`addsd`・`movzx`・`mov` のメモリ読み。関数ポインタ (call/jmp の間接先) は 0 件。ただし kind 判定は mnemonic の allowlist なので、`mov reg,[rip+X]` で読んだ値を後で `call reg` する間接先は検出できない。そのため次の値域の確認で補う。
- 値域の確認 (本 run で実施): 16 VA それぞれについて、8 B 値とその下位 4 B・上位 4 B (計 48 値) を見た。いずれもコード範囲 `[0x400000, 0x1abf400)` に入らない。よって間接 call/jmp の先として使われうる code 番地は含まれない。
- 中身: 13 VA (`0x104ccd0`〜`0x104cd30`) は倍精度として妥当な値 (`0x104ccd0` = `0x408f400000000000` = 1000.0、`0x104ccf0` = 1.0、`0x104cd18` = 64.0 など)。残り 3 VA (`0x104cea6`・`0x104cf24`・`0x104cf25`) は参照が 1〜4 B の `movzx`・`mov` で、8 B の値は参照幅と整合しない (倍精度としての意味は持たない)。3 件とも値域の確認 (コード範囲外) は満たすので、DATA の判定は変えない。
- **結論: 16 VA すべて DATA (定数プール)。** 関数ポインタは 0 件。remap の対象にするかは、受入 2 と同じく「段数一致の件だけ」で決める。0x104cxxx 系の 48 行は段数 1 段 (VAL) なので、`pass_m2r_fn1046a30` の PTR 系の remap 対象には入らない。本 PR では IR を変えない。

## 9. 受入 4: audit 7/7・spill178 差分 (#4498 LD-221)

- 入口: `M11_WORK=tools/m11/work LD_WORK=tools/liftdiff/work bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (exit 0・8 段)。
- 結果: 1〜8 段すべて完走。段 7 の `spill_classify_1161.py` は「results/spill178_1161.tsv と一致」を出力。段 8 (LD-143 修復後 IR) の `spill178 (修復後 IR)` も「results/spill178_1161.tsv と一致」。
- 差分: `results/spill178_1161.tsv` の差分 0 行 (`git status` で変更なし)。
- 注記: 段 6 の動的 verdict の `mismatch` 等は既存の判定語で、失敗ではない。`M11_M2R` は既定 OFF なので、本番 IR は本 PR で変わらない。
- 「1046a30 の IR 差分」: 既定 OFF の本 PR では 0 行。`M11_M2R=1` 時の IR 差分 24 行は PR #6151 (§7) の synthetic 検証に加え、実 IR の差分は未測定 (受入 5 で扱う)。

## 5. 検証と差分

- 段数・番地・定数 (§6・§8) の測定 commit: `db897aecc` (コードを変えた最後の commit)。測定対象 (`tools/m11/ldfix/depth_4498.py`・`rip_match_3677.py`・`results/*.tsv`・`tools/m11/m11_passes.py`) は `db897aecc` から head まで差分 0 (`git diff db897aecc HEAD -- tools/m11/ldfix/depth_4498.py tools/m11/ldfix/rip_match_3677.py tools/m11/ldfix/results tools/m11/m11_passes.py` が空)。`db897aecc..HEAD` の `tools/m11` の差分は `const_4498.py` の未使用 import 1 行の削除のみ。
- `m11_passes.py` は `3987f8c` 以降に `8f3760e86`・`4b2d1a703` で変わったが、どちらも測定 commit `db897aecc` より前。`origin/main` と同一 (`git diff origin/main HEAD -- tools/m11/m11_passes.py` が空・IR 変化 0)。
- 測定 commit 以降に変えたのは、`const_4498.py` の未使用 import の削除と、本節・§8 の文言のみ (コードの挙動は変わらない)。`const_4498.py` は `m11_image.bin` が無く再実行していない。構文検査 (`python3 -m py_compile`) のみ行った。
- 本番 IR・unit の結果は変わらない (IR を書き換えていないため)。KPI (`tools/flelift/boot/REPORT.md`) は動かしていない。

## 7. 受入 2 の remap (#4498 LD-221・`pass_m2r_fn1046a30` 拡張)

- 対象: 段数一致 (§6・`depth_1046a30_4498.tsv` の match=yes) かつ VA 0x15e0000〜0x15e4fff の cell 25 件 (22946304 を含む)。0x104cxxx 系 (コード範囲・受入 3) は含めない。
- 既定 (`M11_M2R` 未設定): 完全一致 `%ce12n11_function_1046a30 = inttoptr i64 22946304 to ptr` の 1 行だけを置換する (旧版 `origin/main` と同じ範囲)。`%ceNn11` の他の名前は触らない。
- `M11_M2R=1`: `%ceNn11_function_1046a30` のうち VA が 25 件の集合 (`M2R_FN1046A30_VAS` + 22946304) に入るものを置換する。変換は `VA − 0x400000`。
- 突合の検証: 25 件の VA 集合 = `depth_1046a30_4498.tsv` の 0x15e 系・match=yes と差分 0 (`set` の比較)。
- synthetic IR の再現 (入力: `%ce12n11` と `%ce3n11` と `%ce5n11` (22937624) と `%ce7n11` (22946280) と `%ce9n11` (1234) に定数行を置いた IR。`origin/main` の `m11_passes.py` と head を同じ入力で比較):
  - main 既定: `%ce12n11` → 18752000、`%ce3n11`・`%ce5n11`・`%ce7n11` は変わらず、`%ce9n11` は変わらず。
  - head 既定: main と出力が完全一致 (`==` True)。`%ce3n11` は 22946304 のまま。
  - head `M11_M2R=1`: `%ce12n11`・`%ce3n11`・`%ce5n11`・`%ce7n11` の 4 件を置換 (22946304 の 2 行 + 22937624 + 22946280)、`%ce9n11` は変わらず。
  - 検証スクリプト: repo 外の一時スクリプト (未コミット・PR の成果物ではない)。
- **未実施 (実 IR)**: 実 IR (`boot_allfx.ll`) での `cmp` (既定) と行数差 (`M11_M2R=1`) は未測定。入力の `work/boot_allfx.ll` は本 run の runner に無い (`fl-win64` のみ展開可能)。`work-m11` 素材は `oc_artifacts` 指定が要り、その素材の IR が現 main の生成手順と一致するかは `docs/WORKFLOW.md` §11 の注記どおり `[未確認]`。
- 既定 OFF の理由: 本番 IR (`m11_gen_ir2.sh`) を変えるため、unit e2e で前後比較するまで既定にしない (M2s・M2v と同じ扱い)。

### 受入 5: unit e2e 前後比較 (#4498 LD-221)

- 入口: `bash tools/m11/ldfix/unit_before_after_4498.sh` (既定と `M11_M2R=1` で `m11_gen_ir2.sh` → `m11_build.sh` → `m11_run.mjs` / `m11_survey.mjs` / `m11_tolerant.mjs`。出力は `work/unit_4498/`・commit しない)。
- IR: 既定 `b202c157a80807f2`、`M11_M2R=1` `325b086322a29aee`。IR 差分は 24 行 (変更行 24 × 両側 = スクリプト出力 48。`grep -c '^[<>]'` の値)。build はどちらも rc 0 (wasm 6,033,657 B)。
- unit 結果 (既定 = `M11_M2R=1`): 通常起動 units_run 109・skipped 5・icall_ok 435・icall_miss 7・init_count 111・boot_stage 1、survey ok 873、寛容起動 ok 871・icall_ok 2131。`image_va_words_new` は run 69721・survey 70977・寛容 72042 で両条件とも同じ。
- 観測: `image_va_words_new` の survey・寛容は実行ごとに 0〜2 ずれる (survey 70977〜70979、寛容 72042〜72044)。手動 1 回で 70979 / 72044、再実行 1 回で寛容 M2R=1 が 72043 と出た。unit の結果 (units_run・skipped・icall・ok) はどの回も同じ。ずれの原因は未確定 (ptrcheck の計数の揺れで、unit 結果には影響しない)。
- 測定 commit (コードを変えた最後の commit): `38be89e99`。`unit_before_after_4498.sh` の実行は HEAD `442e8a53b` で行った (rc 0・所要 3 分 51 秒。この 1 回だけを記録する)。`38be89e99` は実行スクリプトから repo 外の PATH 行を 1 行削除しただけで、挙動は変えていない。`442e8a53b` 以降 HEAD `445b83b17` までの `tools/m11` の差分は本ファイルの記述のみ (`git diff 38be89e99 445b83b17 -- tools/m11` で本ファイルの 2 行追加・1 行削除だけ)。
- 結論: `M11_M2R=1` で unit の結果は変わらない。既定は OFF のまま (本番 IR を変えるのは PM 判断)。
- 注: `m11_e2e.sh` 全体は回していない。`lift_pe.sha256` が素材に無く、全再生成 (Ghidra + RetDec) に入るため。

### 未実施

- なし (受入 1〜5 は本節・§6〜§9 で実測)。`M11_M2R` の既定 ON 化だけは PM 判断として残す。
- 受入 3 は次節 §8 で確定。受入 4 は §9 で確認 (audit 8 段完走・spill178 差分 0)。
