# 付録: icall #1589 — `jmp [mem]` 形の jump table 監査 (ICALL-32)

## 結論

- fl-win64 の PE (313 本) で `jmp [base+idx*s+d]` を持つ関数を走査した。before 監査 (153 PE) の `jmptable` 149 site は全て `jt_present`、`jt_dropped > 0` の関数は **0 件**。
- switch 形の間接 tail jump `jmp qword ptr [rax + rcx*8]` を持つ関数 (block24412、2 関数) は before で `tail-jmp lost 2`、rewrite 後は `lost 0` (`kept_indirect 2`)。
  ただし `audit_icall.py` は IR に call 系命令があれば `kept_indirect` と数え、`icall_rewrite.py` は tail `jmp` を `call __icall_dispatch` + `ret` に書き換える。
  そのため「RetDec が jmp を復元した」のか「rewrite 後の call が数えられた」のかは **未切り分け**。復元の実証は未了。
- 受入条件 1 (`jt_dropped > 0` の `jmp [mem]` 関数の特定) は未達。残りは `plugins-*` 素材の監査。
- 受入条件 2 は「rewrite 経由の分類変化 (lost 2 → 0) の記録」としてのみ達成。「indexed tail jump の drop 改善」とは主張しない。

## 測定

測定 commit: `4efa6820` (`tools/icall` のコード変更なし。HEAD 時点の `roundtrip.sh` / `audit_icall.py` を使用)。
素材: `fl-win64` (`block*_PE.bin` 313 本)、`toolchain-retdec`。

### 1. 走査 (`.pdata` 関数単位・capstone)

- `work/scan_jmpmem.py` (gitignore 対象・未 commit)。`.pdata` 関数 (8 KiB 以下) ごとに
  `jmp` の MEM オペランドで index ありかつ rip 相対でないものを抽出。
- 結果: **265 関数 / 288 site**、**154 PE** に分布 (site が 1 つ以上ある PE 数)。
- 内訳 (上位): block24356 103 関数 / 123 site、block24433 9 / 9、block24412 2 / 2、ほか 151 PE は各 1 関数。
- 所要 8 分 16 秒 (foreground、load 0.9〜2.0)。

### 2. RetDec before 監査 (元 PE・decode のみ・`--select-decode-only`)

- 153 PE = 154 PE から block24356 を除いたもの (block24356 は前 run の実測 `99 jt_present / 0 dropped` を参照し、本 run では再監査していない)。
- 4 並列、`timeout 240` 付きで 2 分 31 秒。全 153 件 rc=0。
- 集計: `jmptable` 149 site = `jt_present 149 / jt_dropped 0 / jt_folded 0`。
- indexed (`jmp [mem]` の tail jump): 10 site = `other_insn:ret 9` + `dropped 1`。

#### 288 site の対応

| 区分 | site 数 | 備考 |
|---|---|---|
| block24356 (監査対象外) | 123 | 前 run 実測を参照 |
| 残り 153 PE の走査 site | 165 | 走査 288 − 123 |
| before 監査で分類された site | 159 | `jmptable` 149 + indexed 10 |
| 未突合 | 6 | 走査と監査の分類の対応は未確認。次 run で `scan_jmpmem` 出力と監査 JSON を突合する |

### 3. 対象 PE block24412 の before / after (`roundtrip.sh`、`F = 0x1800bc760-0x1800bc78c, 0x1801f7e00-0x1801f7e60`)

RetDec 出力の命令種は、この run では RetDec 未配備のため **未測定**。

| 項目 | before | after | after の RetDec 出力命令種 |
|---|---|---|---|
| `jmp qword ptr [rax + rcx*8]` 0x1800bc788 (fn 0x1800bc760) | `dropped` | `kept_indirect` | 未測定 (call / br / ret の別は未確認) |
| `jmp qword ptr [rax + rcx*8]` 0x1801f7e24 (fn 0x1801f7e00) | `other_insn:ret` | `kept_indirect` | 未測定 (同上) |
| `call` 系 `dropped` | 0 | 0 | — |
| `tail-jmp` (lost) | 2 (2) | 2 (0) | — |
| `jmptable` (present/dropped) | 0 / 0 | 0 / 0 | — |

- `roundtrip.sh` の rewrite: `rewrote 2 funcs, 2 sites ... comis 0, jt-chain 0`。cmp/je 展開 (`jt-chain`) は適用されていない。
- 所要 6.8 秒、load 0.9。上の表は前 run で得た 1 回の実行結果。同一 commit での再実行による一致確認は本 run では記録が残っておらず、未確認。

### 4. 測定 commit と差分

- 測定 commit: `4efa6820` (HEAD 時点で `tools/icall` 変更なし)。
- `git diff 4efa6820 HEAD -- tools/icall` は本 commit で追加する本付録のみ。

## 前 run との差分

- 前 run (`60932d35`) の `block24356` 実測 (`jmptable 99 / before dropped 0 / after dropped 51`) は未再測定。
  rewrite 後の 51 drop は未切り分けで、下の未解決に残す。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `jt_dropped > 0` の `jmp [mem]` 関数が fl-win64 に無い。`plugins-ott` / `plugins-freshair` の `audit_*.json` では `jmptable_dropped` が出ているが、`jmp r9` 等の reg 形で `jmp [mem]` ではない | 受入条件 1 の未達 | #1589 (plugins 素材で再監査) |
| block24412 の `dropped → kept_indirect` が RetDec の jmp 復元か rewrite 後の call の計数か未切り分け。after IR で `call @__icall_dispatch` と元 `jmp` の別を確認し、RetDec 出力命令種の列を埋める | 受入条件 2 の復元の実証 | #1589 (RetDec・work-icall 素材のある run) |
| 走査 site (165) と before 分類 (159) の差 6 | 監査カバレッジの把握 | #1589 |
| block24356 の rewrite 後 `jt_dropped` 0 → 51 (前 run 実測) | `#1402` の cmp/je 展開の副作用の疑い | #1589 |
| indexed tail jump の `other_insn:ret` 9 site の意味 (RetDec が jmp を ret に変換していないか) | 監査定義上は良性。未検証 | #1589 |
