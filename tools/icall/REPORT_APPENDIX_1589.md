# 付録: icall #1589 — `jmp [mem]` 形の jump table 監査 (ICALL-32)

## 結論

- (前 run 記録) fl-win64 の PE (313 本) で `jmp [base+idx*s+d]` を持つ関数を走査した。before 監査 (153 PE) の `jmptable` 149 site は全て `jt_present`、`jt_dropped > 0` の関数は **0 件**。
- switch 形の間接 tail jump `jmp qword ptr [rax + rcx*8]` を持つ関数 (block24412、2 関数) は before で `tail-jmp lost 2`、rewrite 後は `lost 0` (`kept_indirect 2`)。
  ただし `audit_icall.py` は IR に call 系命令があれば `kept_indirect` と数え、`icall_rewrite.py` は tail `jmp` を `call __icall_dispatch` + `ret` に書き換える。
  そのため「RetDec が jmp を復元した」のか「rewrite 後の call が数えられた」のかは **未切り分け**。復元の実証は未了。
- 受入条件 1 (`jt_dropped > 0` の `jmp [mem]` 関数の特定) は未達。残りは `plugins-*` 素材の監査。**#1589 の範囲からは外し、下の未解決表に「次 run で実施」として残す** (再測定のため子 issue にしない)。
- 本 PR は #1589 の範囲を受入条件 2・3 に縮めて閉じる (受入条件 1 は未解決表へ移動)。縮めた範囲での判定: 受入条件 2 は **部分達成** (rewrite 経由の分類変化 lost 2 → 0 の記録のみ。「indexed tail jump の drop 改善」とは主張しない)。受入条件 3 は達成。

## 測定

測定 commit: **§1〜§3 は特定できない**。前 run の記録で、実行 commit が記録されていない。前 run の block24356 実測は `60932d35` 時点として引用されている (下の「前 run との差分」)。`60932d35..4efa6820` の間で `tools/icall/audit_icall.py` が変わっている (`09ed7bbc` で jt_folded 分類を追加、+32/-3 行)。jt_folded の有無で jt_dropped の値が変わりうるため、§2 の `jt_dropped 0` がどちらの audit で出たかは未確認。よって §1〜§3 の数値は **前 run 記録・現 HEAD では未再測定** として扱う。
素材: `fl-win64` (`block*_PE.bin` 313 本)、`toolchain-retdec`。

**provenance**: 以下 §1・§2・§3 の数値は **前 run の記録値**。本 run では RetDec ([RETDEC]) と `work/` (scan・監査 JSON) が無く、再現できなかった。本 run で実測した項目は「代替の確認」(下の §0) だけ。

### 0. 本 run での確認

- [RETDEC] (`docs/REFERENCES.md`) の実行環境と `tools/icall/work/` が本 run に無いため、§1〜§3 の再実行は不可。
- `git diff 4efa6820 HEAD -- tools/icall` のコード差分 0 (付録 1 ファイルのみ)。
- `git diff 60932d35 4efa6820 -- tools/icall/audit_icall.py` は +32/-3 行 (`09ed7bbc`)。§1〜§3 の測定 commit を特定できない理由。

### 1. 走査 (前 run 記録値・`.pdata` 関数単位・capstone)

- `work/scan_jmpmem.py` (gitignore 対象・未 commit)。`.pdata` 関数 (8 KiB 以下) ごとに
  `jmp` の MEM オペランドで index ありかつ rip 相対でないものを抽出。
- 結果: **265 関数 / 288 site**、**154 PE** に分布 (site が 1 つ以上ある PE 数)。
- 内訳 (上位): block24356 103 関数 / 123 site、block24433 9 / 9、block24412 2 / 2、ほか 151 PE は各 1 関数。
- 所要 8 分 16 秒 (foreground、load 0.9〜2.0)。

### 2. RetDec before 監査 (前 run 記録値・元 PE・decode のみ・`--select-decode-only`)

- 153 PE = 154 PE から block24356 を除いたもの (block24356 は前 run の実測 `99 jt_present / 0 dropped` を参照し、本 run では再監査していない)。
- 前 run で 4 並列、`timeout 240` 付きで 2 分 31 秒 (前 run の記録。本 run の実測ではない)。全 153 件 rc=0。
- 集計: `jmptable` 149 site = `jt_present 149 / jt_dropped 0 / jt_folded 0`。
- indexed (`jmp [mem]` の tail jump): 10 site = `other_insn:ret 9` + `dropped 1`。

#### 288 site の対応

| 区分 | site 数 | 備考 |
|---|---|---|
| block24356 (監査対象外) | 123 | 前 run 実測を参照 |
| 残り 153 PE の走査 site | 165 | 走査 288 − 123 |
| before 監査で分類された site | 159 | `jmptable` 149 + indexed 10 |
| 未突合 | 6 | 走査と監査の分類の対応は未確認。次 run で `scan_jmpmem` 出力と監査 JSON を突合する |

### 3. 対象 PE block24412 の before / after (前 run 記録値・`roundtrip.sh`、`F = 0x1800bc760-0x1800bc78c, 0x1801f7e00-0x1801f7e60`)

RetDec 出力の命令種は、この run では RetDec 未配備のため **未測定**。

| 項目 | before | after | after の RetDec 出力命令種 |
|---|---|---|---|
| `jmp qword ptr [rax + rcx*8]` 0x1800bc788 (fn 0x1800bc760) | `dropped` | `kept_indirect` | 未測定 (call / br / ret の別は未確認) |
| `jmp qword ptr [rax + rcx*8]` 0x1801f7e24 (fn 0x1801f7e00) | `other_insn:ret` | `kept_indirect` | 未測定 (同上) |
| `call` 系 `dropped` | 0 | 0 | — |
| `tail-jmp` (lost) | 2 (2) | 2 (0) | — |
| `jmptable` (present/dropped) | 0 / 0 | 0 / 0 | — |

- `roundtrip.sh` の rewrite: `rewrote 2 funcs, 2 sites ... comis 0, jt-chain 0`。cmp/je 展開 (`jt-chain`) は適用されていない。
- 前 run の所要 6.8 秒、load 0.9。上の表は前 run で得た 1 回の実行結果。同一 commit での再実行による一致確認は記録が無く、未確認。

### 4. 測定 commit と差分

- §1〜§3 の測定 commit: 特定不可 (上の「測定」節)。前 run の記録値のため、現 HEAD での再測定は未実施。
- `git diff 4efa6820 HEAD -- tools/icall` は本 commit 群で追加した本付録のみ (コード差分 0)。

## 前 run との差分

- 前 run (`60932d35`) の `block24356` 実測 (`jmptable 99 / before dropped 0 / after dropped 51`) は未再測定。
  rewrite 後の 51 drop は未切り分けで、下の未解決に残す。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `jt_dropped > 0` の `jmp [mem]` 関数が fl-win64 に無い。`plugins-ott` / `plugins-freshair` の `audit_*.json` では `jmptable_dropped` が出ているが、`jmp r9` 等の reg 形で `jmp [mem]` ではない。受入条件 1 は本 PR の範囲外 (plugins 素材の監査は再測定) | 受入条件 1 の未達 | 次 run で実施 (素材: `plugins-ott` / `plugins-freshair`、`toolchain-retdec`) |
| block24412 の `dropped → kept_indirect` が RetDec の jmp 復元か rewrite 後の call の計数か未切り分け。after IR で `call @__icall_dispatch` と元 `jmp` の別を確認し、RetDec 出力命令種の列を埋める | 復元の実証 (本 PR では「分類変化の記録」止まり) | 次 run で実施 (RetDec・`work-icall` 素材) |
| 走査 site (165) と before 分類 (159) の差 6 | 監査カバレッジの把握 | 次 run で実施 (`scan_jmpmem` 出力と監査 JSON の突合) |
| block24356 の rewrite 後 `jt_dropped` 0 → 51 (前 run 実測) | `#1402` の cmp/je 展開の副作用の疑い | #1402 配下 |
| indexed tail jump の `other_insn:ret` 9 site の意味 (RetDec が jmp を ret に変換していないか) | 監査定義上は良性。未検証 | 次 run で実施 |
