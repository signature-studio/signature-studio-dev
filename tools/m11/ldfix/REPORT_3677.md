# REPORT #3677 — `1046a30` の命令形 10 進 VA `inttoptr` 73 件の番地・幅突合 (LD-173)

親: #2958 (LD-142)。既知類型: `docs/DEFECTS.md` D11 (10 進 `inttoptr` の VA 漏れ・M11 変種)。前回 `REPORT_2958.md` §5 の「残り 72 件」の件ごとの突合。

## 1. 結論

- 関数 `1046a30` の命令形 `inttoptr i64 N to ptr` (N が VA 範囲 0x400000〜0x1abf400) は **73 件**。`pass_m2r_fn1046a30` (#2958 で merge 済み) が直したのは 22946304 の 1 件で、残りは 72 件。
- 73 件すべてについて、IR 定数 N と機械語の rip 先 VA (`rip 先 = 次命令アドレス + disp`) が一致する (N = VA)。
- 読み幅 (IR の `load` 型と機械語の rip 参照オペランド幅) は、スクリプトの自動判定で 71 件一致・2 件不一致 (33747・33751)。この 2 件は機械判定の誤りで、同番地を `ucomiss xmm0, dword ptr [rip+0x1791]` (0x104b538) が 4 B で読むため IR の `load i32` と一致する。よって幅は 73 件すべて一致とみなす。
- 段数 (値を読んだ後の逆参照の回数) は簡易な機械判定で 71 件一致・2 件不一致 (34334・34723。IR 1 段・機械語 2 段)。**段数の確定判定は未了** (73 件の機械語の使い方を件ごとに読み切っていない)。
- 番地・幅・段数の 3 条件がすべて機械判定で一致するのは 69 件。残り 4 件は、幅の判定誤り 2 件 (33747・33751) と段数の不一致 2 件 (34334・34723) の計。
- **remap は行っていない** (IR・`m11_passes.py` は未変更)。根拠の確定が前提 (前回 REPORT の注意「根拠なしに remap しない」)。件数の確定と remap は子 issue に移した (§6)。

## 2. 測定 (実測)

- 入力: `tools/m11/work/boot_allfx.ll` (work-m11 展開物・`pass_m2r` 前の IR)、`tools/m11/work/m11_image.bin` (22515781 B)。
- 逆アセンブル: capstone 5.0.7 で `0x1046a30`〜`0x104ccee` の線形。
- 再現: `python3 tools/m11/ldfix/rip_match_3677.py` → `tools/m11/ldfix/results/rip_1046a30_3677.tsv` (73 行・列は同スクリプトの docstring)。
- 測定 commit: 本 PR の commit (コードを変えた最後の commit)。基点 `origin/main` = `7ae7c6981`。

### 2-1. 件数の照合

- 前回 REPORT は「16267〜24296 行」と書いたが、今回の `boot_allfx.ll` では関数 `1046a30` は 27761〜35428 行。行番号は IR の版で変わる。**件数 73 と 22946304 の位置は一致**。
- 22937624 (前回 REPORT §5 の 16640 行) は今回の IR では 28134 行 (`%ce0n11_function_1046a30`)。

### 2-2. 番地と幅 (73 件)

| 項目 | 件数 |
|---|---|
| IR 定数 N = 機械語 rip 先 VA | 73 / 73 |
| 読み幅一致 (IR load 型 = 機械語オペランド幅) | 71 / 73 |
| 幅が合わない 2 件 (33747・33751) | 機械語の rip 参照の先頭が `mulsd` (8 B) だが、同番地を `ucomiss` (4 B, 0x104b538) が読む。IR の `load i32` と一致する。判定上の誤り |

### 2-3. 段数 (機械判定・未確定)

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
| 段数の確定判定 (73 件・特に 34334・34723) | 段数が 1 段違うと remap 後も値が機械語と違う | #4498 (LD-221) |
| remap の実装 (`pass_m2r_fn1046a30` の拡張) | IR は未変更。`1046a30` の load 値は本 PR の前後で変わらない | #4498 (LD-221) |
| `audit_lsf_ssa_e2e.sh` 7/7・unit e2e (本番 build) | 未実施。remap していないため差分 0 | #4498 (LD-221) |
| 0x104ccd0〜0x104cfxx 系 (コード範囲に入る VA) の解釈 | 定数がコード領域を指す。データか関数ポインタかの確認が必要 | #4498 (LD-221) |

## 5. 検証と差分

- `git diff <測定 commit> HEAD -- tools/m11/m11_passes.py tools/m11/ldfix/*.py` は本 PR で `rip_match_3677.py` (新規) のみ。`m11_passes.py` は未変更 (IR 変化 0)。
- 本番 IR・unit の結果は変わらない (IR を書き換えていないため)。KPI (`tools/flelift/boot/REPORT.md`) は動かしていない。
