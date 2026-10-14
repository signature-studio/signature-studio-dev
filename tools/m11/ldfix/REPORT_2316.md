# #2316 (LD-108): #1091 の残り — 41a670 の head 解除 store の修復・実測・DEFECTS 追記

親: #2038 (LD-75)。前段: #1091 (LD-33、CLOSED)。

**判定: 部分達成**。修復 (**検証用の手作業パッチ。本番の IR 生成経路には未配線**)・wasm 直接呼び実測・DEFECTS 追記は達成。検出信号は既存の `audit_lsf_disp.py` で実装済みだが、`audit_lsf.py` への統合は未達。本番 build の wasm は 41a670 が未修復のまま (§3・§5)。

測定 commit: `f0c721e4` (コードを変えた最後の commit)。

**追記 (#2402)**: 本番配線 (`m11_gen_ir2.sh` への組込み・`ir_conditions` の記録・通常 build の wasm での実測) は [REPORT_2402.md](REPORT_2402.md) で達成した。§4 の ok 絶対値の差の原因も同 §5 に移した (build 条件の差ではなく IR の出所。136 は再現せず)。以下は #2316 時点の記述で、§3 の「本番非配線」は現在は当てはまらない。

## 1. 受入条件

| 受入条件 | 結果 |
|---|---|
| 検出信号を定義して `audit_lsf.py` に追加 | **未達 (部分)**。検出信号は `audit_lsf_disp.py` (#911 で定義済み) として実装され、41a670 を検出する。`audit_lsf.py` 本体は未変更 (§2) |
| 修復を実装し、wasm 直接呼びで head=0x2222 を実測 | **部分達成**。`fix_ld108.py` (検証用パッチ) で修復前 head=0x3333 (FAIL) → 修復後 head=0x2222 (PASS) を実測 (§3)。パッチは `ld108_e2e.sh` だけが適用し、`m11_gen_ir2.sh` / `m11_build.sh` には未配線。通常の build の wasm は未修復 (→ #2402) |
| DEFECTS.md に新規類型を追記 | **達成** (新規行は作らず、既存 D20 行の検出信号・修復・観測欄を更新。DEFECTS 側は結論 1 行とリンクだけで、測定値は本 REPORT だけに置く。修復欄は「検証用の手作業パッチ (非本番)」と明記) |

## 2. 検出信号

`audit_lsf_disp.py` (機械語の argN+disp の load 値を store する site に対し、IR の store 値の出元 `load (argN+c)` の c が、機械語の同じ (argN, width) の disp 集合に無いものを SUSPECT とする)。

測定 (素材 work-m11 の `boot_final.ll`、修復前・修復後の IR に対して実行):

| IR | 関数 / SUSPECT 件数 | SUSPECT VA |
|---|--:|---|
| 修復前 | 7421 / 4 | 41a670 6677a0 d237e0 de1da0 |
| 修復後 (fix_ld108) | 7421 / 3 | 6677a0 d237e0 de1da0 |

41a670 が消えた。残る 3 件は未突合 (`6677a0` の `arg2+36`、`d237e0` の `arg2+36`、`de1da0` の `arg1+244`)。機械語の列挙漏れか誤検出かの判定が未了で、DEFECTS の検出信号欄には「未突合」と明記した。

**未達の理由**: `audit_lsf_disp.py` は `audit_lsf.py` と別ファイル。統合 (件数・判定の既存出力への組込み) は既存判定 (SUSPECT_VAS / SUSPECT_USE_VAS) の再測定を伴うため、本 run の範囲を超える。→ 未解決 (§5)。

## 3. 修復と動的確認

修復: `tools/m11/ldfix/fix_ld108.py`。機械語 41a69c〜41a6a3 (`mov rax,[rbp+0x50]; mov rax,[rax]; mov [head],rax`、rax = arg1、変位 0) に対し、IR の head 解除ブロック `dec_label_pc_41a69c` の store 値 `%2` (= `load [arg1+8]`) を、新たに挿入した `load i64 [arg1+0]` に置換する。変更は 41a670 の 1 関数・4 行。

**適用範囲 (本番非配線)**: `fix_ld108.py` を呼ぶのは `ld108_e2e.sh` だけである。`tools/m11/m11_gen_ir2.sh` は ldfix 段で `ldfix/ldfix.py` だけを適用し、`m11_build.sh` も `fix_ld108` を呼ばない。したがって本節の修復後 wasm は `ld108_e2e.sh` が作る検証用の build で、通常の build (`m11_gen_ir2.sh` → `m11_build.sh`) の wasm ではない。配線 (`m11_cond.py` の記録と IR の sha256 が組込み後の IR と一致することの確認を含む) は未実施で、#2402 に移した。

動的確認 (`dyn_ld108.mjs`。修復前 / 修復後の wasm を直接呼ぶ):

| 関数 | 期待 (機械語から決定) | 修復前 | 修復後 |
|---|---|---|---|
| 41a670 (head=N, N.next([N+0])=0x2222, N.child([N+8])=0x3333) | head = 0x2222 | 0x3333 FAIL | 0x2222 PASS |

## 4. survey 前後 (942 unit)

同一 build 条件で修復前後を測定 (`ld108_e2e.sh`、commit `f0c721e4`):

- 修復前: ok 136 / oob 8 / miss 797 / halt0 1
- 修復後: ok 136 / oob 8 / miss 797 / halt0 1
- unit 単位の突合: ok 退行 0、kind 以外を含む差分 unit 0、icall sites・targets の差 0

ok の絶対値 (136) は REPORT_509 (ok 852) や、同 image を別 build 条件で測った値 (869) と一致しない。これは build 条件 (`ir_conditions.json` の ldfix/qstore/PE 記録) の差による。本 PR の判定は**修復前後の差**のみで行う。絶対値の不一致の原因は未特定 (§5)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `audit_lsf_disp.py` を `audit_lsf.py` に統合 (受入条件 1 の残り) | 検出信号が既存の SUSPECT 集計に入らない | #2396 (LD-111) |
| 残る SUSPECT 3 件 (6677a0 / d237e0 / de1da0) の機械語突合 | 誤検出か、機械語の列挙漏れか未判定 | #2396 (LD-111) |
| `666a60` のループ内 store (`store i64 %29`) の修復 | 同型の誤りが残る (REPORT_911 §2) | #1091 の残件 (LD-33) に含む。本 PR は未着手 |
| RetDec 段 16 の変換規則の発火確認 (分岐の実行) | 根本原因の機構が未確定 | #1967 / #2038 の既存経路 |
| `fix_ld108.py` の本番配線 (`m11_gen_ir2.sh` の ldfix 直後への組込み、`m11_cond` 記録と IR sha256 の一致確認、通常 build の wasm での実測) | 通常の build の wasm は 41a670 が未修復 | #2402 (LD-112) |
| survey の ok 絶対値 (136 / 869) の build 条件差 | 測定の再現に build 条件の固定が要る | #2402 (LD-112。`ld108_e2e.sh` の前提 (ir_conditions) を揃える) |
| `fix_ld108.py` が挿入する `%arg1` と関数の仮引数の一致 assert (レビュー minor) | 想定と違う IR で気付けない | #2402 (LD-112。コード変更になるため、測定済みの本 PR では触らない) |

## 6. 再現

```
FL_WIN64_DIR=<fl-win64 の展開先> bash tools/m11/ldfix/ld108_e2e.sh
```

前提: `tools/m11/work` に work-m11 の展開 (boot_final.ll ほか)、`[EMSDK]` (`docs/REFERENCES.md`)。所要 62.4 秒 (commit `f0c721e4`、load 0.38 → 0.78)。
スクリプトは終了時に `work/boot_final*.ll` と `ir_conditions.json` を元に戻す。
