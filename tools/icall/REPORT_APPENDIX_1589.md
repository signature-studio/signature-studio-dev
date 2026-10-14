# 付録: icall #1589 — `jmp [mem]` 形の jump table 監査 (ICALL-32)

## 結論

- **現 HEAD で再測定したのは block24412 の 2 関数だけ** (下の §3)。fl-win64 全 PE の走査・before 監査は本 run で再実行できなかった。
- `jt_dropped > 0` の `jmp [mem]` 関数の件数は **現 audit で未確認**。前 run 記録の「0 件」は旧 audit での値で、現 HEAD の `audit_icall.py` (jt_folded 分類を含む) では再監査していない。
- 走査の 265 関数 / 288 site は **本 run で再現できなかった** (§1)。
- switch 形の間接 tail jump (block24412、2 関数) は、現 HEAD で before `tail-jmp lost 2` → after `lost 0` (`kept_indirect 2`) を再現した。ただし `audit_icall.py` は IR に call 系命令があれば `kept_indirect` と数え、`icall_rewrite.py` は tail `jmp` を `call __icall_dispatch` + `ret` に書き換える。そのため「RetDec が jmp を復元した」か「rewrite 後の call が数えられた」かは **未切り分け**。復元の実証は未了。
- 受入条件 1 (`jt_dropped > 0` の `jmp [mem]` 関数の特定) は未達。plugins 素材の監査も未着手 (未解決表へ)。

## 測定

- 測定 commit: `69598b07` (§3 の block24412 の測定時の HEAD)。以後の `aaedb47d` は `tools/icall/scan_jmpmem.py` の追加のみで、監査コードは変えていない。§1・§2 は未再測定。
- 監査コード (`audit_icall.py` / `roundtrip.sh` / `icall_rewrite.py`) は `69598b07` から `aaedb47d` まで無変更 (`git diff 69598b07 aaedb47d -- tools/icall/audit_icall.py tools/icall/roundtrip.sh tools/icall/icall_rewrite.py` は空)。
- 素材: `fl-win64` (`block*_PE.bin` 313 本、`$FL_WIN64_DIR/extracted/` = [WIN64])、`toolchain-retdec` ([RETDEC])、`work-icall` (`tools/icall/work/`)。展開を確認済み。

### 0. 実行環境

- `toolchain-retdec` → [RETDEC] (`/opt/retdec`)。RetDec 実行可を確認。
- `work-icall` → `tools/icall/work/` (5.6 GiB。`rt_*` や `audit_*.json` 等の前 run の中間物を含む)。
- `fl-win64` → `$FL_WIN64_DIR/extracted/` ([WIN64]。`*_PE.bin` 313 本)。

### 1. 走査 (現 HEAD で再実行。REPORT 前 run 値とは一致しない)

- 再現コマンド (1 行): `python3 tools/icall/scan_jmpmem.py $FL_WIN64_DIR/extracted --json tools/icall/work/scan_jmpmem.json` (`FL_WIN64_DIR` は [WIN64]。所要 2m56s)。
- 条件: `.pdata` 関数のうち、8 KiB 以下 かつ `jmp` の MEM オペランドで index あり・rip 相対でないもの。
- 本 run の実測: **PE 313 / 関数 250 / site 267 / site を持つ PE 154**。
- 前 run 記録の **265 関数 / 288 site とは一致しない**。同じ 1 回の走査 (`scan_all.json`) から切り分けた結果は次のとおり。
  - `jmp` のみ・8 KiB 以下: 250 関数 / 267 site
  - `jmp` のみ・サイズ上限なし: 266 関数 / 290 site
  - `jmp`+`call`・8 KiB 以下: 1585 関数 / 2656 site (`call` を含めると桁が違う)
  - 前 run の 265 / 288 は、どの条件とも一致しない。前 run の走査条件は記録されていない。
- よって「265 関数 / 288 site」は **再現できない値**。本付録では前 run 記録値として扱い、本 run の実測値 (250 / 267) を採る。

### 2. RetDec before 監査 (前 run 記録値・未再測定)

- 前 run の集計 (旧 audit 版・未再測定): `jmptable` 149 site = `jt_present 149 / jt_dropped 0 / jt_folded 0`。indexed (tail jump) 10 site = `other_insn:ret 9` + `dropped 1`。
- 現 HEAD の `audit_icall.py` (`09ed7bbc` で jt_folded を追加) での再監査は、153 PE の RetDec 実行が必要で本 run の上限に収まらないため未実施。
- 結論の「jt_dropped > 0 の関数は 0 件」は **現 audit では未確認**。旧 audit での前 run 記録として扱う。

### 3. block24412 の before / after (現 HEAD で再測定)

- 対象 F: `0x1800bc760-0x1800bc78c`, `0x1801f7e00-0x1801f7e60` (`tools/icall/work/F_24412.txt`)。
- 実行: `bash tools/icall/roundtrip.sh $HOME/analysis/win64/extracted/block24412_PE.bin work/F_24412.txt r24412` (6.4 秒、load 1.0)。
- 結果 (本 run 実測):

| 項目 | before | after |
|---|---|---|
| `jmp indexed` 2 site | `dropped=1` + `other_insn:ret=1` | `kept_indirect=2` |
| `tail-jmp` (lost) | 2 (2) | 2 (0) |
| `call` 系 `dropped` | 0 | 0 |
| `jmptable` (present/dropped/folded) | 0 / 0 / 0 | 0 / 0 / 0 |
| rewrite | — | `rewrote 2 funcs, 2 sites`, `comis 0, jt-chain 0` |

- 前 run 記録 (before `dropped` / `kept_indirect`) と一致する。
- after の RetDec 出力命令種 (call / br / ret の別) は未測定。復元か計数かは未切り分け。

### 4. 測定 commit と差分

- 測定 commit: `aaedb47d` (§3 のみ)。§1・§2 は現 HEAD で未再測定。
- `git diff 4efa6820 aaedb47d -- tools/icall` の全差分は `REPORT_APPENDIX_1589.md`・`scan_jmpmem.py` (新規) のみ (コード差分は `scan_jmpmem.py` の追加だけで、既存監査コードは不変)。
- 受入条件 3 の判定: **部分達成** (§3 は現 HEAD で再測定。§1・§2 は前 run 記録のまま)。

## 前 run との差分

- 前 run (`60932d35`) の `block24356` 実測 (`jmptable 99 / before dropped 0 / after dropped 51`) は未再測定。rewrite 後の 51 drop は未切り分けで、下の未解決に残す。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 現 HEAD の `audit_icall.py` で 153 PE の before 監査を再実行し、`jt_dropped > 0` の件数を確定する (旧 audit の「0 件」の検証) | 受入条件 1 の判定と「0 件」結論の鮮度 | 子 issue (次 run) |
| 走査 265 関数 / 288 site の定義を特定する (現 HEAD の走査は 250 / 267) | 走査数値の再現性 | 次 run で実施 |
| plugins-ott / plugins-freshair の `jmp [mem]` 監査 (受入条件 1 の本体) | 受入条件 1 の未達 | 次 run で実施 (素材: `plugins-ott` / `plugins-freshair`) |
| block24412 の `dropped → kept_indirect` が RetDec の jmp 復元か rewrite 後の call の計数か未切り分け | 復元の実証 (本 PR は分類変化の記録止まり) | 次 run で実施 (after IR の命令種) |
| block24356 の rewrite 後 `jt_dropped` 0 → 51 (前 run 実測) | `#1402` の cmp/je 展開の副作用の疑い | #1402 配下 |
| indexed tail jump の `other_insn:ret` 9 site の意味 | 監査定義上は良性。未検証 | 次 run で実施 |
