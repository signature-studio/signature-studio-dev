# M11 REPORT (#3916 / [M11-N198] / 親 #3140): set_other の CFG 実値化を独立に照合する

結論: 前提だった実値化 1 件 (`function_f6bb50` → `function_cd1c20` pos 1 = rdx = `0x0`) は、修正版の判定器 (PR #3919) では実値化 0 件のため照合対象が無い。前提の 1 件は誤りで、経路によって `0x0` と `0x1` になる (未決)。独立照合器 `m11_setother_nonimm_cfg_verify.py` (具体実行で呼出し点の全経路の値を列挙) で、同じ 1 件が **FAIL (経路で値が違う)** と判定されることを確認した。ネガティブコントロールは、この 1 件に `0x0` と `0x1` を当てて両方が FAIL になることで確認した。34 件中 33 件は判定不能 (値が未知の経路 16・step 上限 15・cdq 2。PASS にしていない)。

## 1. 方式 (`m11_setother_nonimm_cfg_verify.py`)

- 判定器 (`m11_setother_nonimm_cfg.py`) と別系統: 逆向きの到達定義ではなく、関数入口から具体実行して probe (呼出し点) に届く全経路の値を集める。
- 分岐条件が未知なら両方の経路を辿る (過大近似)。probe で値が未知の経路が 1 つでもあれば判定不能。
- 命令の意味は `op_str` の文字列だけで読む (capstone の `regs_access`・`rw` を使わない)。
- 未対応命令・step 上限 (200000)・到達しない probe は判定不能。判定不能は PASS にしない。
- 区分: 値が 1 つ → 実値化、経路で値が違う → 未決 (`--claim` 付きなら FAIL)、未知 → 判定不能。

## 2. 測定

### 2-1. 合成検査 (`--selftest`・期待値と照合)

| ケース | 期待 | 実測 |
|---|---|---|
| K0 直線 (`xor ebx`・`movzx edx,bl`) claim 0x0 | PASS | PASS |
| K0 ネガティブ claim 0x1 | FAIL | FAIL (実測 0x0) |
| K1 未知分岐・両経路で同値 claim 0x0 | PASS | PASS |
| K1 ネガティブ claim 0x1 | FAIL | FAIL |
| K2 循環 (1 周目 0・2 周目 1) claim 0x1 | PASS | PASS |
| K2 ネガティブ claim 0x0 | FAIL | FAIL (実測 0x1) |
| K3 部分書込 (旧値未知) | 判定不能 | 判定不能 |
| K4 call を挟む分岐 (`xor ebx`・`cmp ebx,0`・`call`・`je`・`mov ebx,1`・`movzx edx,bl`) claim なし | 未決 | 未決 (経路 0x0,0x1) |
| K4 ネガティブ (同上・claim 0x0) | FAIL | FAIL (経路で値が違う) |
| K4 対照 (call なし・ZF 確定) claim なし | 実値化 | 実値化 0x0 |

結果: 10 件 / 不一致 0。K4 は差し戻し前の版では `実値化 0x0` になっていた (§6)。

### 2-1a. 差し戻し後の判定

- `call` では揮発レジスタに加えて flags (`fl`) も未知にする (§6 参照)。
- import 時に argparse を実行しないよう、CLI は `if __name__ == '__main__':` の内側へ移した。

### 2-2. 実データ (素材 `fl-win64` `block00031_PE.bin`・`work-m11`)

- 測定 commit: `07bae9afb` (コードを変えた最後の commit。§5)。
- 入力: `block00031_PE.bin` sha256 `b2c64da4…`・`boot_final.ll` sha256 `69c774de…` (REPORT_N172 と一致)。
- 台帳の再生成: `m11_post.py` → `m11_argrecover.py` → `m11_argrecover_verify.py` (`fixes 33: match 33 / mismatch 0`)→ `m11_setother_ledger_verify.py` (`match 410`)→ `m11_setother_nonimm_class.py` (349 件)→ `m11_setother_nonimm_cfg.py` (34 件)。すべて rc 0。
- 判定器の区分 (34 件): 実値化 0 / 復元不能 0 / 未決 34 (REPORT_N172 §2-2 と一致)。非 imm 349 件: 0 / 0 / 349 (REPORT_N172 §2-4 と一致)。
- 照合器 (34 件を同じ台帳で判定):

| 判定 | 件数 | 内容 |
|---|---:|---|
| 実値化 (照合で値が 1 つ) | 0 | — |
| 未決 (経路で値が違う) | 1 | `function_f6bb50` → `function_cd1c20` pos 1 (`merge>chain>loop`) |
| 判定不能 (値が未知の経路 16・step 上限 15・cdq 2) | 33 | `function_127a4a0`→`function_65f270` pos 1 ほか (内訳は下記) |
| PASS / FAIL | 0 / 0 | — |

- 台帳の再生成 (本測定・`work-m11` の `boot_final.ll` と `fl-win64` の `block00031_PE.bin` から): `m11_sigfix_stats.sh` 相当の手順で `fixes 33: match 33 / mismatch 0`、`m11_setother_ledger_verify.py` で `match 410`、`m11_setother_nonimm_class.py` で非 imm 349 (reg 123・mem 150・lea 76)・未決 349、`m11_setother_nonimm_cfg.py` で 34 件。`work-m11` 単独には `nonimm_cfg_rows.json`・`nonimm_class_rows.json`・`FIXES.json` は含まれないため、上の手順で都度生成する。`final3_base.ll` の sha は `c029ada4…` で、REPORT_N86 の `ecab191b…` と異なる (台帳の件数は一致)。
- 照合器 (`verify()` を 34 件に適用・測定 commit `07bae9afb`): 判定不能 33 (値が未知の経路 16・step 上限 15・cdq 2)・未決 1・実値化 0。判定不能の内訳は、`verify` の戻り値の理由を集計した実測値。
- 未決 1 件 (`function_f6bb50` → `function_cd1c20` pos 1) の経路値は `0x0` と `0x1` (`経路で値が違う: 0x0,0x1`)。REPORT_N172 §3 の機械語 (1 周目 rbx=0・2 周目 rbx=1) と一致。
- 実データのネガティブコントロール: 同じ 1 件に claim `0x0` → FAIL (経路で値が違う)。claim `0x1` も同じく FAIL。どちらの claim も経路の値の集合と一致しないため、一致と判定されない。

## 3. 判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. `nonimm_cfg_rows.json` の実値化 1 件 (`0x0`) が一致と判定される | **対象なし** (実値化 0 件・照合器で FAIL 相当の未決 1 件) | §2-2。前提の 1 件は誤り (REPORT_N172 §3) |
| 2. ネガティブコントロールで FAIL する | **達成** (合成 K0・K1・K2 と、実データ 1 件の両 claim) | §2-1・§2-2 |
| 3. 結果を REPORT に実測値で残す | **達成** | 本ファイル |

判定不能 33 件は、照合器の命令対応を広げれば判定できる。今回は範囲外 (§5 の未解決)。

### 3-1. #4807 (命令対応の拡張・測定 commit `07bae9afb`)

- 追加した命令: `shl`/`sal`/`shr` (即値・`cl`)・`neg`・`not`・`imul` (2・3 オペランド)・`set*`・`cvt*` (整数宛先は未知)・`ucomis*`/`comis*` (flags 未知)・XMM 宛先の命令 (整数状態は変えない)。結果 flags の `js`/`jns` を追加し、それ以外の結果 flags の条件分岐 (`jle` 等) は未知 (両経路を辿る)。
- 合成検査 (`--selftest`): 10 件 → 30 件 (S1〜S10 を追加、PASS とネガティブ控えの両方)。30 件・不一致 0。
- 実データ (`work-m11` の再生成と `block00031_PE.bin`): 34 件の判定は **判定不能 33・未決 1・実値化 0・PASS 0・FAIL 0**。

| 判定不能の理由 (`07bae9afb` の実測) | 件数 |
|---|---:|
| 値が未知の経路がある (`function_127a4a0`→`function_65f270` pos 1 の `merge>call_ret` 等) | 16 |
| step 上限 (200000) (`function_11d4df0`→`function_7e3af0` pos 0 の `merge>load_ptr` 等) | 15 |
| 未対応命令 `cdq` (`function_1280530`・`function_e9d8a0`) | 2 |
| 未対応命令 `imul`・`not` | 0 |

- 受入 1 (判定不能 0) は **未達**。残りは「値が未知の経路」(16 件)・「step 上限」(15 件)・`cdq` (2 件)。`imul`・`not` は実測で 0 件 (前版の表の「imul 10・not 1」は誤りで、本文を実測値に直した)。照合器は「値が未知」の経路がどの `call` 越えかを報告しないので、原因の特定は次の作業。
- 実値化の 1 件 (`function_f6bb50` → `function_cd1c20` pos 1) は未決のまま (経路で `0x0`・`0x1`)。前提の 1 件が誤りという REPORT_N172 §3 の結論と一致する。
- 台帳 (`nonimm_cfg_rows.json` 34 件) は `m11_sigfix_stats.sh` → `m11_setother_nonimm_class.py` → `m11_setother_nonimm_cfg.py` の再生成で得た (`work-m11` 単独には含まれない・§2-2 の手順)。`fixes 33: match 33 / mismatch 0`・`match 410`・非 imm 349 件・未決 349 は REPORT_N171 と一致。

## 4. 残り (未解決)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 照合器の未対応命令 (SSE 変換 `cvtsi2ss`/`cvtsi2sd`・`ucomisd`/`ucomiss`・`mulss`・`shl`/`shr`/`neg`・`sete`・結果 flags の条件分岐 `jle` 等) | 33 件が判定不能。実値化の自動照合は 0 件のまま | 起票 (子)・本 PR 本文 |
| 判定不能 33 件の手動照合 | 自動照合の対象外 | 同上 |

## 5. 測定 commit と差分

- 測定 commit: `07bae9afb` (コードを変えた最後の commit)。以降の `60d9da6a3` は本ファイルの追記のみ。
- 差分 (コードのみ): `git diff 07bae9afb HEAD -- tools/m11 ':(exclude)*.md'` の出力は 0 行 (下に貼る)。
  ```
  $ git diff 07bae9afb HEAD -- tools/m11 ':(exclude)*.md'
  (出力 0 行)
  ```

## 6. 差し戻し対応 (review round 1)

| 指摘 | 対応 |
|---|---|
| 1. `call` で flags が残り、`je` が誤って実値化 `0x0` | `call` で `fl = None`。K4 (call を挟む分岐) を追加。K4 は差し戻し前の版で `実値化 0x0` になることを確認し、修正後は `未決 (0x0,0x1)` |
| 2. `Closes #3916` と issue 本文の受入 1 の不整合 | issue #3916 本文から受入 1 を外し、原文を子 #4807 へ移す |
| 3. 実データの素材 (`work-m11`) が PR 本文に無い | PR 本文に `oc_artifacts: fl-win64 work-m11` を追加。本 run で `work-m11` と `fl-win64` を取得し、台帳を再生成して照合した (§2-2・§3-1) |
| minor: import 時に argparse が走る | CLI を `__main__` ガードの内側へ移動 |

## 7. #4807 の続き: cdq/idiv 対応と判定不能の残り (測定 commit `b368111b1`)

- 対応を追加: `cdq`/`cqo` (rdx を符号で埋める・flags 不変)、`idiv r/m32` (edx:eax を割り、商 eax・余り edx。除数が未知・メモリ・0・商のオーバーフローは判定不能)。
- `--all` を追加: 従来の `real()` は `実値化` 行のみを照合していた。台帳 34 件は全件 未決 のため、旧 CLI は「実値化 0 件」と報告して素通りしていた。`--all` で全行を照合する (claim なし)。
- 合成検査 (`--selftest`): 30 件 → 44 件 (C1〜C4・D1〜D5 を追加)・不一致 0。PASS・FAIL・判定不能 を各対応に入れた。
- 実データ (`work-m11` の再生成 → `m11_setother_nonimm_class.py` → `m11_setother_nonimm_cfg.py`・`block00031_PE.bin`): 34 件 → **判定不能 33・未決 1・実値化 0・PASS 0・FAIL 0** (rc 0・3.9 秒・load 0.22)。

| 判定 (`b368111b1` の実測・`--all`) | 件数 |
|---|---:|
| 判定不能: step 上限 (200000) | 16 |
| 判定不能: 値が未知の経路がある | 16 |
| 判定不能: 未対応命令 `sar` (`function_1280530` → `function_7e3af0` pos 0) | 1 |
| 未決 (経路で値が違う `0x0,0x1`・`function_f6bb50` → `function_cd1c20` pos 1) | 1 |

- 前版 (§3-1) の「未対応 `cdq` 2 件」は、`cdq` の直後の `idiv` (未対応) で止まっていた。`idiv` を入れて `Unsup` 2 件 → 1 件 (`sar`)。判定不能は 33 件のまま (`step 上限` が 15 → 16 に移った)。
- 受入 1 (判定不能 0) は **未達**。判定不能 33 件は次の 3 種。解消には命令対応ではなく、step 上限の扱いと「値が未知」の原因特定が要る。
  - 値が未知 16 件: 照合器は未知になった経路の call 越えを報告しない。
  - step 上限 16 件: 200000 step で打ち切り。ループ・探索の刈り込みが要る。
  - `sar` 1 件: 未対応命令。対応しても判定不能が 0 になるかは未測定 (`sar` の後に別の理由が出る可能性がある)。

## 8. #4807 の続き: sar 対応と step 上限の検証 (測定 commit `cbacec6fa`)

- 対応を追加: `sar` (符号付きで右シフト・シフト数は `shl`/`shr` と同じ規則)。合成検査 E1・E2 (PASS・FAIL の両方) を追加。
- 合成検査 (`--selftest`): 44 件 → **48 件・不一致 0** (rc 0)。
- 実データ (`fl-win64` `block00031_PE.bin`・`work-m11` 展開 233 件。台帳は `m11_sigfix_stats.sh` → `m11_setother_nonimm_class.py` → `m11_setother_nonimm_cfg.py` で再生成。`fixes 33: match 33 / mismatch 0`): 34 件を `--all` で照合。
  - 判定: **判定不能 33・未決 1・実値化 0・PASS 0・FAIL 0** (rc 0・5.78 秒・load 0.77)。
  - 判定不能の理由: step 上限 17・値が未知の経路 16 (前版は step 上限 16・未対応 `sar` 1)。`sar` の 1 件は step 上限に移った。判定不能の合計は 33 件のまま。
- step 上限の検証 (同じ台帳・同じコード): `MAX_STEPS` = 200,000 → 5.7 秒で step 上限 17 件・値が未知 16 件。2,000,000 → 54.6 秒で **同じ 17 件**。step 予算不足ではなく、探索が収束しない (ループ・未知の分岐が打ち切られない) ことを示す。
- 結論: 判定不能 0 は、命令対応ではなく次の 2 点が要る。(a) 探索の刈り込み (ループの不動点・未知の分岐の併合) で step 上限 17 件を収束させる。(b) 「値が未知の経路」16 件の原因 (どの call 越えか) を特定する。照合器は (b) の理由を報告しないため、未特定。

### 差分 (コードのみ・測定 commit 以降)

`git diff cbacec6fa HEAD -- tools/m11 ':(exclude)*.md'` の出力は 0 行 (本節の追記は REPORT のみ)。

## 10. #5553: 刈り込み (`--prune`) と step 上限 17 件の原因 (測定 commit `5cab29c51`)

- 規則: 分岐先 (未知分岐の fork・`jmp`・`jcc` の先) で、同じ状態 (ip・レジスタ・flags・スタック) を再訪した経路を切る。切った先は初回訪問で既に辿られているので値の集合は変わらない (健全)。切断は `刈り込み(ループ)` (後方の再訪) と `刈り込み(分岐の合流)` (前方の再訪) に分ける。既定 (`--prune` 無し) の判定は §8 と同じ。
- 合成検査 (`--selftest`): **67 件・不一致 0** (rc 0。既存 48 件 + 刈り込みの検査 9 件 (P1〜P4) + 類の検査 10 件 (§9 の L1〜L5))。刈り込みの検査 P1〜P4 を追加: P1 ループ (PASS・FAIL)、P2 分岐 1 つ (PASS・FAIL)、P3 未知分岐を出口に持つループ (PASS・FAIL・刈り込み無しは step 上限)、P4 出口なし無限ループ (刈り込みで実値化・無しは step 上限)。
- 実データ (`fl-win64` `block00031_PE.bin`・`work-m11` の台帳 `nonimm_cfg_rows.json` 34 件・`--all`):

| 判定 | 既定 (`--prune` 無し) | `--prune` |
|---|---:|---:|
| 判定不能 | 33 | 33 |
| 未決 | 1 | 1 |
| 実値化 | 0 | 0 |
| PASS / FAIL | 0 / 0 | 0 / 0 |
| 所要 (`time` の real・3 回の範囲) | 7.45〜7.53 s | 3.49〜3.73 s (load 0.82〜0.90) |

- step 上限 17 件の原因 (`--prune` の実測。件数は全て行単位 = 1 呼び出し (caller→callee pos) を 1 件として数える。`real()` の 1 反復に対応):

| 判定不能の理由 (`--prune` 後) | 件数 | 内訳 |
|---|---:|---|
| 刈り込み後も step 上限 (未知分岐が多く収束しない) | 5 | `function_1280530`→`function_7e3af0` pos 0・`function_dd5a80`→`function_6c3700` pos 0・`function_e391b0`→`function_6eeb40` pos 0・`function_e391b0`→`function_6ef3e0` pos 0・`function_11d4df0`→`function_7e3af0` pos 0 |
| 値が未知の経路がある (刈り込みの切断あり・理由文に件数を付与) | 25 | うち後方ループの切断を含むのが 5 件 (`function_dd5680`→`function_6bed60` 2 件・`function_ddcd00`→`function_6bed60` 3 件)・分岐の合流のみが 20 件 |
| 値が未知の経路がある (刈り込みの切断なし) | 2 | `function_6624a0`→`function_4420e0`・`function_9ce890`→`function_6774b0` (未知の源。刈り込みは効いていない) |
| 刈り込み後に未対応命令 `imul` (1 オペランド形) | 1 | `function_ddf630`→`function_6bed60` pos 1 |

- 件数の関係 (全て行単位): step 上限 17 件 = 刈り込み後も step 上限 5 件 + 刈り込みで収束した 12 件。12 件の内訳は値が未知 11 件 (既定の値が未知 16 件に加わる) と未対応命令 `imul` 1 件。よって値が未知の合計は 16 + 11 = 27 件 (表の 25 + 2 件)、判定不能の合計は 5 + 27 + 1 = 33 件。
- 後方ループの切断 (`刈り込み(ループ)`) の単位: 関数数は 3 (`function_1280530`・`function_dd5680`・`function_ddcd00`)。行数は 6 (step 上限群の `function_1280530` 1 行 + 値が未知群の 5 行)。値が未知 25 行のうち後方切断を含むのは 5 行で、残り 20 行は分岐の合流 (`刈り込み(分岐の合流)`) のみ。
- 値が未知 27 件 (表の 25 + 2 件) の原因 (どの call 越えの値か) は、照合器が報告しないため全件未特定。
- 理由文: 刈り込みを入れた判定不能は、理由文に切断の件数を付けた (`値が未知の経路がある (刈り込み ループ n・分岐の合流 m)`・`刈り込み後も step 上限 (未知分岐 n・刈り込み m)`)。`imul` の 1 件は刈り込みの有無と無関係に未対応命令。
- 未解決: (a) 刈り込み後も step 上限の 5 件 (未知分岐 6,672〜19,366・刈り込み 4〜8,036 件)。合流の刈り込みを、状態の一致ではなく併合 (同 ip の状態を値ごとに和集合) に変えれば収束しうるが未検証。(b) 「値が未知」27 件の原因 (どの call 越えの値か) は照合器が報告しない。(c) `imul` 1 オペランド形 1 件 (`function_ddf630`)。`imul r/m` は `edx:eax` を使う形で、`idiv` と同様に扱える。いずれも判定不能 0 には未達。
- 受入 1 (step 上限 17 件に原因が付き、件数が REPORT に載る): **達成** (上表)。受入 2 (規則ごとに PASS と FAIL の合成検査): **達成** (P1〜P4)。受入 3 (REPORT に実測値): **達成** (本節)。判定不能 0 は **未達** (33 件のまま)。残りは子 issue に切る。

### 差分 (測定 commit `5cab29c51` 以降のコード)

`git diff 5cab29c51 HEAD -- tools/m11 ':(exclude)*.md'` の出力は 0 行 (本節は REPORT のみ)。
測定は HEAD `7ba8b27fb` (コードは `5cab29c51` と同一) で、上の表と件数はこの HEAD で取り直した値。
素材は `fl-win64` `block00031_PE.bin` と `work-m11` を展開し、`m11_sigfix_stats.sh` → `m11_setother_ledger_verify.py` (`match 410`) → `m11_setother_nonimm_class.py` → `m11_setother_nonimm_cfg.py` (34 件) で台帳を再生成した (rc 0)。

## 9. #5552: 値が未知の経路 16 件の未知の源の類 (測定 commit `51df584bd`)

- 変更: `m11_setother_nonimm_cfg_verify.py` に未知の源の類を付けた (入力引数 / スタック slot / メモリ読込 / call 戻り値 / その他)。判定 (実値化・未決・判定不能) は変えていない。`verify` の判定不能の詳細に `類=` を付けた。
- 類の付け方: 入口から一度も書かれていない reg は 入力引数。`call` で壊れた揮発 reg は call 戻り値。オペランドがメモリ (`[...]`) なら、rsp/rbp を含むものは スタック slot、それ以外は メモリ読込。その他は上記以外。値が未知の reg は、未知になった時点の源を継ぐ。
- 合成検査 (`--selftest`): 48 件 → **58 件・不一致 0** (rc 0)。類ごとに PASS (正しい類) と FAIL (誤った類・ネガティブコントロール) を入れた (L1〜L5)。

### 9-1. 実データ (`fl-win64` `block00031_PE.bin`・`work-m11`・台帳は §2-2 と同じ手順で再生成)

- 台帳の再生成 (本 run): `m11_sigfix_stats.sh` → `m11_setother_ledger_verify.py` (`match 410`) → `m11_setother_nonimm_class.py` (349 件) → `m11_setother_nonimm_cfg.py` (34 件・実値化 0・未決 34)。
- 照合 (`--all`・測定 commit `51df584bd`): **判定不能 33・未決 1・実値化 0・PASS 0・FAIL 0** (rc 0・5.28 秒・load 0.21)。判定は類を付ける前 (`07bae9afb`・§8) と同一。

| 値が未知の経路 (16 件) の源の類 | 件数 | 対象 (caller → callee pos) |
|---|---:|---|
| 入力引数 | 7 | `function_6624a0`→`function_4420e0` pos 0・`function_9ce890`→`function_6774b0` pos 0・`function_9cf2e0`→`function_695e80` pos 0・`function_a97780`→`function_677f60` pos 0/1・`function_a97780`→`function_677fb0` pos 0/1 |
| メモリ読込 | 5 | `function_cc6ae0`→`function_6ef3e0` pos 0・`function_cc6ae0`→`function_6eeb40` pos 0・`function_cc6ae0`→`function_6ee8a0` pos 0 (2 回)・`function_cc6ae0`→`function_6ef3c0` pos 0 |
| call 戻り値 | 4 | `function_127a4a0`→`function_65f270` pos 1 (3 回)・`function_ff0600`→`function_a97410` pos 1 |
| スタック slot | 0 | — |
| その他 | 0 | — |
| 合計 | 16 | 判定不能の「値が未知の経路」16 件と一致 |

- 読み: 「直前の call が原因」(#5552 の前提の否定) は 16 件中 4 件だけ。残り 12 件は入力引数 (7) とメモリ読込 (5) で、#4807 の停止報告の推定 (入力引数・スタック・グローバル由来) と一致する。スタック slot は 0 件で、rsp 基準の読込はこの 16 件の未知の源には無い。
- 限界: 類は未知になった時点の源を継ぐ近似で、経路の途中で別の源が混ざっても最後の源を報告する。類は分類の補助で、判定 (PASS・FAIL) の根拠にはしない。入力引数 7 件の関数の引数の実体 (どの引数か) は未特定。

### 9-2. 測定 commit 以降の差分

`git diff 51df584bd HEAD -- tools/m11 ':(exclude)*.md'` の出力は 0 行 (本節の追記は REPORT のみ)。

## 10. #5563: 1 オペランド形 `imul r/m` の対応 (測定 commit `1f834b4f5`)

- 対応を追加: `imul r/m32`・`imul r/m64` (1 オペランド形)。`edx:eax` (`rdx:rax`) へ符号付き積を書く。宛先 reg の幅が 8/16 bit・メモリ・除数が未知は判定不能 (類付き)。
- 合成検査 (`--selftest`): 58 件 → **68 件・不一致 0** (rc 0)。I1〜I4 は PASS とネガティブ控え、I5・I6 は判定不能。
- 実データ (`fl-win64` `block00031_PE.bin`・`work-m11` 展開・台帳は `m11_sigfix_stats.sh` → `m11_setother_nonimm_class.py` → `m11_setother_nonimm_cfg.py` で再生成。`fixes 33: match 33 / mismatch 0`): 34 件を `--all` で照合。
  - 判定: **判定不能 33・未決 1・実値化 0・PASS 0・FAIL 0** (rc 0・5.15 秒)。対応前 (`origin/main` の照合器) も同じ判定 (5.22 秒)。判定は変わらなかった。
- `function_ddf630` → `function_6bed60` pos 1: 対応前は `判定不能 Stop: step 上限`、対応後も同じ。`Unsup` (未対応命令) は対応前後とも 0 件で、台帳 34 件のどれにも 1 オペランド `imul` で止まる経路は無い。`function_ddf630` 本体には 1 オペランド `imul` が 2 箇所 (`ecx`・`edi`) あるが、どちらも到達前の打ち切りで、未対応の理由にはならない。
- **結論**: issue #5563 の前提 (未対応の `imul` 1 オペランド形が原因) は実データで成り立たない。受入 1 (判定が未対応以外になる) は **未達**。原因は step 上限 (探索が収束しない) で、命令対応ではない。残件は #5553 の子 #5562 (step 上限 5 件の併合) と既存の step 上限の扱いに移す。

### 10-1. 測定 commit 以降の差分

`git diff 1f834b4f5 HEAD -- tools/m11 ':(exclude)*.md'` の出力は 0 行 (本節の追記は REPORT のみ)。

## 11. #5562: 分岐の合流を併合で収束させ、step 上限 5 件を解く (測定 commit `62a9f2e1b`)

- 規則 (`--merge`): 分岐先 (未知分岐の fork・`jmp`) に届いた状態を、同じ ip に既に届いた状態と併合する (`join`)。値が一致する reg は保ち、一致しない reg・flags は未知にして類を和集合にする。併合で状態が変わったときだけ再探索するので、有限回で止まる。既定 (`--prune` 無し) と `--prune` の判定は変えていない。
- 合成検査 (`--selftest`): **85 件・不一致 0** (rc 0)。既存 77 件に併合の検査 M1〜M4 を足した (PASS・FAIL の両方。M3 は出口なしループで実値化・ネガティブ FAIL)。M4 (カウンタ付きループ) は条件が確定しているので併合の対象外で PASS のまま。
- 実データ (`fl-win64` `block00031_PE.bin`・`work-m11` の台帳 `nonimm_cfg_rows.json` 34 件・`--all`。台帳は `m11_sigfix_stats.sh` → `m11_setother_ledger_verify.py` (`match 410`) → `m11_setother_nonimm_class.py` (349 件) → `m11_setother_nonimm_cfg.py` (34 件) で再生成):

| モード | 判定不能 | 未決 | 実値化 | PASS / FAIL | 所要 (`time` real・本 HEAD) |
|---|---:|---:|---:|---:|---:|
| 既定 | 33 | 1 | 0 | 0 / 0 | 7.37 s |
| `--prune` | 33 | 1 | 0 | 0 / 0 | 3.51 s |
| `--merge` | 33 | 1 | 0 | 0 / 0 | 0.49 s |

- 判定 34 行は、既定・`--prune`・`--merge` の 3 モードで **全行一致** (判定の変化 0)。
- 受入 1 (step 上限 5 件の判定): 5 件とも **step 上限は消えた** (併合で収束)。判定は PASS/FAIL にならず、いずれも「値が未知の経路がある」(判定不能)。残りの理由は下表。

| 対象 (caller → callee pos 0・既定 `--prune` で step 上限) | `--merge` 後の判定 | 類 |
|---|---|---|
| `function_11d4df0` → `function_7e3af0` | 判定不能 (値が未知・併合 ループ 4・合流 35) | メモリ読込 |
| `function_1280530` → `function_7e3af0` | 判定不能 (値が未知・併合 ループ 14・合流 517) | メモリ読込 |
| `function_dd5a80` → `function_6c3700` | 判定不能 (値が未知・併合 ループ 2・合流 168) | メモリ読込 |
| `function_e391b0` → `function_6eeb40` | 判定不能 (値が未知・併合 ループ 2・合流 58) | メモリ読込 |
| `function_e391b0` → `function_6ef3e0` | 判定不能 (値が未知・併合 ループ 2・合流 58) | メモリ読込 |

- 判定の内訳 (`--merge`・34 行): 判定不能 33 (うち step 上限 0・値が未知 33)・未決 1 (`function_f6bb50` → `function_cd1c20` pos 1・経路で値が違う `0x0,0x1`)・実値化 0・PASS 0・FAIL 0。
- 類 (経路単位): 併合後は `call 戻り値` 10・`メモリ読込` 15・`入力引数` 7・`スタック slot` 1。
- 件数の関係: step 上限 5 件 → 併合で値が未知 5 件へ移る。よって判定不能は 33 件のまま (`--prune` と同じ件数)。受入 1 の「判定 (PASS/FAIL/未決) が出る」は **未達**: 併合は step 上限を消したが、値を確定できる行はゼロ。残るのは併合で未知になった値 (メモリ読込・入力引数) の源の特定で、併合の精度ではなく入力・メモリの値の扱いに移った。
- 受入 2 (PASS と FAIL の合成検査): **達成** (M1〜M4)。受入 3 (実測値): **達成** (上表)。
- 限界: 併合は同じ ip の状態を 1 つに潰すので、ループのカウンタ (`ebx` など) は 1 周で未知になる (M4 の確定分岐は例外)。併合後の判定は上界で、未知の源は未特定のまま。

### 11-1. 測定 commit 以降の差分

`git diff 62a9f2e1b HEAD -- tools/m11 ':(exclude)*.md'` の出力は 0 行 (本節の追記は REPORT のみ)。
