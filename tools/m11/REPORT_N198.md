# M11 REPORT (#3916 / [M11-N198] / 親 #3140): set_other の CFG 実値化を独立に照合する

結論: 前提だった実値化 1 件 (`function_f6bb50` → `function_cd1c20` pos 1 = rdx = `0x0`) は、修正版の判定器 (PR #3919) では実値化 0 件のため照合対象が無い。前提の 1 件は誤りで、経路によって `0x0` と `0x1` になる (未決)。独立照合器 `m11_setother_nonimm_cfg_verify.py` (具体実行で呼出し点の全経路の値を列挙) で、同じ 1 件が **FAIL (経路で値が違う)** と判定されることを確認した。ネガティブコントロールは、この 1 件に `0x0` と `0x1` を当てて両方が FAIL になることで確認した。34 件中 33 件は未対応命令で判定不能 (PASS にしていない)。

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

- 測定 commit: 本 PR の最後のコード commit (下記 §5)。
- 入力: `block00031_PE.bin` sha256 `b2c64da4…`・`boot_final.ll` sha256 `69c774de…` (REPORT_N172 と一致)。
- 台帳の再生成: `m11_post.py` → `m11_argrecover.py` → `m11_argrecover_verify.py` (`fixes 33: match 33 / mismatch 0`)→ `m11_setother_ledger_verify.py` (`match 410`)→ `m11_setother_nonimm_class.py` (349 件)→ `m11_setother_nonimm_cfg.py` (34 件)。すべて rc 0。
- 判定器の区分 (34 件): 実値化 0 / 復元不能 0 / 未決 34 (REPORT_N172 §2-2 と一致)。非 imm 349 件: 0 / 0 / 349 (REPORT_N172 §2-4 と一致)。
- 照合器 (34 件を同じ台帳で判定):

| 判定 | 件数 | 内容 |
|---|---:|---|
| 実値化 (照合で値が 1 つ) | 0 | — |
| 未決 (経路で値が違う) | 1 | `function_f6bb50` → `function_cd1c20` pos 1 (`merge>chain>loop`) |
| 判定不能 (未対応命令・flags 等) | 33 | `shl`・`cvtsi2ss`・`cvtsi2sd`・`ucomisd`・`ucomiss`・`mulss`・`neg`・`shr`・`sete`・`jle` 結果 flags など |
| PASS / FAIL | 0 / 0 | — |

- **差し戻し後の再実行は未実施**: 素材ディレクトリ ($ARTIFACTS_DIR) には `fl-win64.tar.zst` のみあり、`work-m11` (`nonimm_cfg_rows.json`) が無い。このため 34 件の内訳 (実値化 0 / 未決 1 / 判定不能 33) は差し戻し前の版の実測値で、`call` の flags 修正後の値は未確認。次の回で `oc_artifacts: fl-win64 work-m11` を指定して再実行し、内訳を照合する。
- 照合器が未決にした 1 件の経路値 (実測・差し戻し前の版): `0x0` と `0x1`。REPORT_N172 §3 の機械語 (1 周目 rbx=0・2 周目 rbx=1) と一致。
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

| 判定不能の理由 | 件数 (修正前 `c6df3e147`) | 件数 (`07bae9afb`) |
|---|---:|---:|
| 未対応命令 (`shl`・`cvtsi2sd`・`mulss`・`jle` 結果 flags 等) | 33 | 0 |
| 未対応命令 `imul` | (上の 33 に含む) | 10 |
| 未対応命令 `cdq` | (上の 33 に含む) | 2 |
| 未対応命令 `not` | (上の 33 に含む) | 1 |
| 値が未知の経路がある | — | 16 |
| step 上限 (200000) | — | 15 |

- 受入 1 (判定不能 0) は **未達**。未対応命令による打ち切りは消えたが、残りは「値が未知の経路」(16 件)・「step 上限」(15 件)・`cdq` (2 件)。照合器は「値が未知」の経路がどの `call` 越えかを報告しないので、原因の特定は次の作業。
- 実値化の 1 件 (`function_f6bb50` → `function_cd1c20` pos 1) は未決のまま (経路で `0x0`・`0x1`)。前提の 1 件が誤りという REPORT_N172 §3 の結論と一致する。
- 台帳 (`nonimm_cfg_rows.json` 34 件) は `m11_sigfix_stats.sh` → `m11_setother_nonimm_class.py` → `m11_setother_nonimm_cfg.py` の再生成で得た (`work-m11` 単独には含まれない・§2-2 の手順)。`fixes 33: match 33 / mismatch 0`・`match 410`・非 imm 349 件・未決 349 は REPORT_N171 と一致。

## 4. 残り (未解決)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 照合器の未対応命令 (SSE 変換 `cvtsi2ss`/`cvtsi2sd`・`ucomisd`/`ucomiss`・`mulss`・`shl`/`shr`/`neg`・`sete`・結果 flags の条件分岐 `jle` 等) | 33 件が判定不能。実値化の自動照合は 0 件のまま | 起票 (子)・本 PR 本文 |
| 判定不能 33 件の手動照合 | 自動照合の対象外 | 同上 |

## 5. 測定 commit と差分

- 測定 commit: 差し戻し対応の commit (`call` の flags 修正・selftest K4・CLI ガード)。合成検査 (`--selftest`) はこの commit で再測定した (10 件・不一致 0・rc 0)。
- 差分 (コードのみ): `git diff <測定 commit> HEAD -- tools/m11 ':(exclude)*.md'` (PR 本文に出力を貼る)。

## 6. 差し戻し対応 (review round 1)

| 指摘 | 対応 |
|---|---|
| 1. `call` で flags が残り、`je` が誤って実値化 `0x0` | `call` で `fl = None`。K4 (call を挟む分岐) を追加。K4 は差し戻し前の版で `実値化 0x0` になることを確認し、修正後は `未決 (0x0,0x1)` |
| 2. `Closes #3916` と issue 本文の受入 1 の不整合 | issue #3916 本文から受入 1 を外し、原文を子 #4807 へ移す |
| 3. 実データの素材 (`work-m11`) が PR 本文に無い | PR 本文に `oc_artifacts: fl-win64 work-m11` を追加。ただし本 run では `work-m11` が取得できず、再実行は未実施 (§2-2) |
| minor: import 時に argparse が走る | CLI を `__main__` ガードの内側へ移動 |
