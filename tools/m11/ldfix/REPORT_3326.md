# REPORT_3326 — 同類型の誤り deref 箇所の site 単位 IR 修復 (#3326 / CI-148、親 #2555)

既知類型との関係: **DEFECTS.md D4** (引数 reg 経由の disp=0 deref 脱落 → 値がアドレスのまま使われる)。
REPORT_2555 §2 の判定表 (誤り 13 箇所) の修復。新規類型ではない。

## 0. 結論

- 誤り 13 箇所のうち、**本 PR で site 単位の修復を入れたのは 5 箇所** (0x413340・0x44fb40・0x450420・0x4506e0・0x7888f0)。
  機械語照合付きの `tools/m11/ldfix/fix_site_3326.py` (step 1c)。
- **既存 pass で直る 4 箇所**: 0x450560 の 3 箇所 (`fix_450560.py`・#2502)、0x6074b0 (`ldfix.py` が `%ldfxu24` の load を挿入済み。REPORT_2555 の base IR 判定 ADDR は ldfix 後に LOAD へ変わる)。
- **未修復 4 箇所** (比較・GEP・null 経路の複雑型。単純な argK の load 挿入では直せない): 0x44f040・0x47b4a0・0x47cf10・0xc40770。子 issue #3372 [CI-151]。
- ネガティブコントロール NC1〜NC4 は **4/4 拒否** (§3)。
- `ldfix_e2e.sh` (測定 commit `de3b0d03f`): 修復後も stage4 と unit survey は base と**一致** (変化なし。§4)。
  stage4 の `memory access out of bounds` は base・fix の両方に残る。修復 5 箇所がその経路に無いのか、経路上にあって未解消なのかは本 run では未確認。
- 0x413340 の 3 番目引数 (§5): deref 脱落ではなく値の取り違えの疑い。修復対象には含めず、子 #3372 で判定する。

## 1. 数え方・再現

- 入力 IR: `tools/m11/work/boot_final3.ll` (base)。pipeline: `ldfix.py` (1) → `fix_450560.py` (1b) → `fix_site_3326.py` (1c) の順。
- 一次分類 (`verify_deref_sites_2555.py`) は ldfix 後 IR で行う。最終判定は窓の人手読み (REPORT_2555 §2 と同じ基準)。
- PE: `block00031_PE.bin` (fl-win64 26.1.7.5653)。素材 `fl-win64` `work-m11` `work-liftdiff` `toolchain-emsdk` `toolchain-retdec` を `docs/WORKFLOW.md` §11 の手順で展開して使った (fl-win64 の展開先は `FL_WIN64_DIR`、他は `tools/m11/work/`・`tools/liftdiff/work/`)。
- 再現: `bash tools/m11/ldfix/ldfix_e2e.sh` (step 1c を含む)。`python3 tools/m11/ldfix/fix_site_3326.py tools/m11/work/boot_final3.ll /dev/null --pe <PE> --negctl` でネガティブコントロール。

## 2. 13 箇所の状態 (REPORT_2555 §2 の表の番号)

| 表# | 関数 | 呼出し先 (argpos, k) | 状態 | 所在 |
|---|---|---|---|---|
| 1 | 0x413340 | 0x412fc0 (1, k=2) | **修復 (本 PR)** | site A |
| 5 | 0x44f040 | 0x44aeb0 (1, k=1) | 未 (子 #3372) | IR は `zext load [arg2-4]`。*arg1 の load が無い複雑型 |
| 7 | 0x44fb40 | 0x414850 (1, k=2) | **修復 (本 PR)** | site B |
| 8 | 0x450420 | 0x4503c0 (2, k=1) | **修復 (本 PR)** | site C |
| 9〜11 | 0x450560 ×3 | 0x4133f0 / 0x414850 ×2 | 既存 (本 PR 外) | `fix_450560.py` (step 1b)。一次分類 LOAD |
| 12 | 0x4506e0 | 0x4133f0 (2, k=1) | **修復 (本 PR)** | site D |
| 13 | 0x47b4a0 | 0x409c80 (2, k=1) | 未 (子 #3372) | 基底が `%24`。GEP 型 |
| 14 | 0x47cf10 | 0x409c80 (2, k=1) | 未 (子 #3372) | `rbx*8` の二重 mul |
| 15 | 0x6074b0 | 0x4256c0 (1, k=1) | 既存 (本 PR 外) | `ldfix.py` が `%ldfxu24` を挿入。一次分類 LOAD |
| 16 | 0xc40770 | 0x409c80 (2, k=1) | 未 (子 #3372) | 非 null 経路のみ誤り。MISMATCH |
| + | 0x7888f0 | 0x4133f0 (2, k=1) | **修復 (本 PR)** | site E (rbx 複写経由。走査の取りこぼし) |

本 PR: 5 箇所 / 既存 pass: 4 箇所 / 未修復: 4 箇所 (合計 13)。

## 3. 機械照合と修復 pass (`fix_site_3326.py`)

- 各 site の機械語 (スピル・argK の再読込み・1 段 deref・call) を capstone で照合。mnemonic と operand 文字列が完全一致しなければ assert で止める。合計 **22 命令** を検証 (commit `e14a5a405`)。
- IR は base 形 (対象行が 1 件だけ一致) のときだけ書き換える。argK の 1 段 load を呼出しの直前に挿入し、引数をその値に差し替える。
  仮引数が `ptr` 型の関数 (0x4506e0・0x7888f0) は `inttoptr` を挟まない (commit `de3b0d03f`。`inttoptr i64` を使った初版は emcc が型エラーで落ちたため修正)。

ネガティブコントロール (`--negctl`、修復前の `boot_final3.ll` を入力):

| NC | 内容 | 結果 |
|---|---|---|
| NC1 | 適用済みの IR に再適用 (二重適用) | 拒否 OK (base 行 0 件) |
| NC2 | 機械語 0x4133aa の operand を `[rax + 8]` に改変 | 拒否 OK (機械照合で不一致) |
| NC3 | 機械語 0x450458 (存在しない VA) を期待 | 拒否 OK (逆アセンブルできない) |
| NC4 | 対象 IR 行の引数を `%arg1` に改変 | 拒否 OK (base 行 0 件) |

`NG 0 件` (4/4 拒否)。

## 4. 一次分類 (ldfix 後 IR) と e2e 実測

一次分類 (`verify_deref_sites_2555.py`・候補 17 行: 走査 16 + 取りこぼし 1):

| 段 | LOAD | ADDR | OTHER | MISMATCH | SCAN_MISS |
|---|---|---|---|---|---|
| ldfix 後 (fix_450560 まで) | 4 | 3 | 7 | 2 | 1 |
| + fix_site_3326 (本 PR) | **8** | 3 | 3 | 2 | 1 |

LOAD 8 = 0x413340・0x44fb40・0x450420・0x450560 ×3・0x4506e0・0x6074b0。ADDR 3 は偽陽性 (0x413c00・0x414c70・0x44f240。REPORT_2555 §2)。
0x7888f0 は走査が拾わないため一次分類の対象外 (SCAN_MISS)。site E は機械照合と IR 行の差し替えで確認 (§3)。

`ldfix_e2e.sh` (測定 commit `de3b0d03f`・rc 0・所要 57 s・終了時 load average 0.83 / 0.52 / 0.30):

| 項目 | base (修復前) | fix (修復後) | 判定 |
|---|---|---|---|
| stage4 到達 (reached_stage_probe) | 4/6 | 4/6 | 一致 |
| stage4 `units_run` / `units_total` | 17 / 942 | 17 / 942 | 一致 |
| stage4 `GetMem` / `FreeMem` / `init_count` / `icall_ok` | 16 / 6 / 18 / 24 | 16 / 6 / 18 / 24 | 一致 |
| stage4 `threw` | memory access out of bounds | memory access out of bounds | 一致 (OOB は両方に残る) |
| stage4 `wasm_size` | 6025281 | 6025495 | 差 +214 B (修復の IR 差) |
| unit survey ok / miss / trap | 136 / 14 / 9 | 136 / 14 / 9 | 一致 |
| survey trap 内訳 | OOB 8・Halt→longjmp 1 | OOB 8・Halt→longjmp 1 | 一致 |
| emcc 構文検証 (step 2) | — | 通過 | — |
| STAGE4_JUDGE | | | pass: true |

変化が無かった理由 (推定。未確認): 修復 5 箇所は 942 unit の実行経路に入らないか、OOB の原因が別の箇所にある。どちらかは本 run では判定していない。

## 5. 0x413340 の 3 番目引数 (受入条件 4)

- 機械語 0x4133af `mov r8, qword ptr [rsp + 0x38]`。`[rsp+0x38]` は entry の rdx (= arg2) の spill で、この 1 命令で r8 は **arg2 そのもの**を受ける (deref 無し)。
- base IR (`%21 = call 412fc0(i32 %20, i32 %18, i64 %14)`) の 3 番目は `%14 = and i64 %rsi.0, 65535` (16 bit の語)。
- したがって「アドレスを渡すべきところで *arg を渡す」(D4) ではなく、「arg2 を渡すべきところで語の値を渡す」型。値の取り違えの疑い。
  deref 脱落の検出 (verify_deref_sites_2555) の対象外。**修復対象には含めない。** 最終判定は子 #3372 で行う。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 複雑型 4 箇所 (0x44f040・0x47b4a0・0x47cf10・0xc40770) の site 修復 | 同類型の残り。stage4 の OOB との関係は未確認 | 子 #3372 [CI-151] |
| 0x413340 の 3 番目引数 (機械 arg2 / IR 語) の判定 | 別類型の疑い。修復対象か未定 | 子 #3372 [CI-151] |
| stage4 の `memory access out of bounds` が base・fix に残る原因 | 起動の到達段 (stage 4) で止まる。修復 5 箇所との関係は未確認 | 子 #3372 [CI-151] (実測の追加) |
| 0x439f90 の判定不能 (IR に対応呼出し無し) | 1 箇所 | REPORT_2555 §6 の子 #3328 [CI-149] |

## 7. 検証範囲・測定

- 範囲内: 修復 5 site の機械照合 (22 命令)・NC 4 件・ldfix 後 IR の一次分類・`ldfix_e2e.sh` (step 1〜5) の base/fix 比較。
- 範囲外: 複雑型 4 箇所の修復、0x413340 の 3 番目引数の判定、stage4 OOB の原因、survey 136 unit の個別結果、flelift/boot の起動 KPI (本 run では動かしていない)。
- 測定 commit: `de3b0d03f` (コード差分の最終 commit)。`git diff de3b0d03f HEAD -- tools/m11/ldfix/fix_site_3326.py tools/m11/ldfix/ldfix_e2e.sh` の出力は 0 行 (この REPORT の commit は文書のみ)。
- 既知類型: DEFECTS.md D4 (REPORT_2555 と同じ)。新しい類型は見つけていない。
