# REPORT_2141 — 旧監査と dest 版の site 集合の突き合わせ・置換判断 (#2141 / 親 #1866)

## 1. 測定条件

- 測定 commit: `6444b186` (main)。本 PR は REPORT・結果 JSON・DOC_MAP の索引追加のみ。
  `git diff 6444b186 HEAD -- tools/m11` は 0 行 (監査スクリプト・ldmach/ldframe 無変更)。
- 入力: `tools/m11/work/boot{0,1,2,3,4}.norm0.ll` (5 入力)。`boot5.norm0.ll` は `work/` に無く、
  全体 (`find /`) 検索も時間切れで所在不明のため**除外**した。
- PE: 素材 `fl-win64` の `extracted/block00031_PE.bin` (`tar --zstd -xf` で `/home/runner/work/_temp/fl` に展開)。
- 実行: `audit_undefload.py` 69.7 秒 (rc 0)、`audit_undefload_dest.py` 70.1 秒 (rc 0)。load average 0.97 (4 vCPU)。
- 結果 JSON: `results/audit_undefload_2141_old.json` / `results/audit_undefload_dest_2141.json` /
  `results/audit_undefload_union_2141.json`。

## 2. 再現性の確認

#1866 の committed 結果 (`results/audit_undefload_1866.json`・`audit_undefload_dest_1866.json`) と、
今回の 5 入力での再実行を比べた。

| 監査 | 今回 (5 入力) | #1866 committed (6 入力) | FRAME_IN_ESCAPED 関数集合 |
|---|---|---|---|
| 旧 `audit_undefload.py` | sites 2,846 / FRAME_IN_ESCAPED 56 site・53 関数 | sites 2,854 / 56 site・53 関数 | 差 0 |
| dest 版 `audit_undefload_dest.py` | sites 2,729 / DEST_FRAME_IN_ESCAPED 18 site・18 関数 | sites 2,737 / 18 site・18 関数 | 差 0 |

sites の差 (2,854 → 2,846、2,737 → 2,729) は、`boot5` 入力の欠落によるものと推定する (未確認)。
関数集合は両監査とも完全に一致したので、`boot5` 欠落は以下の集計の結論を変えない。

## 3. 和集合 (受入条件 1)

| 集合 | 関数数 |
|---|---|
| 旧監査 FRAME_IN_ESCAPED | 53 |
| dest 版 DEST_FRAME_IN_ESCAPED | 18 |
| 両方で検出 (積集合) | **6** (441730, 639c70, 6c7ca0, 7e45e0, 81bfd0, bf8b40) |
| **和集合** | **65** |
| 旧監査のみ | 47 |
| dest 版のみ | 12 (1312080, 407800, 4425f0, 45ce40, 5afe30, 607620, 652b90, 783d00, 81a710, 843ad0, 865020, e9d8a0) |

- 積集合は 6 関数だけで、両監査は**相補的**。片方だけを残すと、もう片方だけが見つけた関数が脱落する
  (旧のみ 47 件・dest のみ 12 件)。
- 和集合 65 関数が、本件型 (escape 済み stack_var 内部の frame read が undef load 化する) の検出候補の上限。
  ただし各関数の真偽 (修復要否) はこの REPORT では判定していない (§5 の受入条件 4 は本 issue の範囲外)。

## 4. 判断 (受入条件 2)

**並列で使う (旧監査は削除・置換しない)。** 理由:

1. 積集合が 6 関数しかなく、どちらも他方の代替にならない (§3)。
2. dest 版は consumer が直接 memop を持つ site を `continue` で集計から外すため、旧監査の
   MEMREAD / FRAME_IN_ESCAPED 直接 read の site を数えない。置換すると直接 read の検出が消える。
3. 旧監査の結果は #564 / #1866 の経緯の参照点として残す必要がある。

運用: 検出件数は **和集合 (65 関数)** を正とし、両 JSON を併記する。`audit_undefload.py` は削除しない。

## 5. 未解決

本 issue の受入条件 (1)(2) は満たした。以下は #1866 REPORT の残件であり、既存の子 issue に含まれる。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FRAME_IN_ESCAPED 和集合 65 関数の真偽判定・修復要否 (旧 48 関数の判定を含む) | 本件型の脱落が残る可能性 | #2144 [LD-80] |
| F4 偽陰性の検出 (132e8e0 / 44d1c0 / 69c360 / 977e40) とネガコン | 偽陰性の残存を確定できない | #2143 [LD-79] |
| `boot5.norm0.ll` の所在確認と再実行 (本 REPORT は 5 入力) | 件数の sites が 8 少ない (関数集合は不変) | 本 PR 内で記録のみ (追加の子 issue は起票しない) |

## 6. 参照

- `REPORT_1866.md` (dest 版の再実行・F4 検出 1/5)
- `REPORT_564.md` (旧監査の 56 site・F4 修復 10 関数)
- `REPORT_1647.md` (dest 版の新設)
