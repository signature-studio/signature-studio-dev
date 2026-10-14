# 付録: icall #1573 — OTT F の jt_dropped 8 件の展開後残件数 (ICALL-31)

測定 commit `d16d7f5d` (以降の icall コード差分は下記鮮度の証跡を参照)。素材 `analysis-ott-binaries` (`OTT_vst2_win64.dll`)・`toolchain-retdec`・`work-icall` (`ott_F.txt`)。
再現: `tools/icall/roundtrip.sh <analysis-ott-binaries>/OTT_vst2_win64.dll work/ott_F.txt ott-F-1573 work/rt_ott-F-1573`。
foreground、rc 0、所要 32.7 s (`time` 実測)、開始時 load 0.87。関数集合は 282 関数 (`F.ranges`、`ott_F.txt` 由来)。

## 結果

| 形 | before (`audit_before.txt`) | after (`audit_after.txt`・`sites_after.json`) |
|---|--:|--:|
| `jmp jmptable` (8 site) | `jt_present=7`・`jt_dropped=1` | **`jt_dropped=8`** |

- 「展開後の残件数」は **8 件** (全 site が after で `jt_dropped`)。`rewrite.txt` は `jt-chain 8` (展開 pass は 8 site に掛かった)。
- サイト単位 (`sites_before.json` を `audit_icall.py --ir before.0.drc.ll` で再生成して突合):

| VA | 形 | 標的数 | before | after |
|---|---|--:|---|---|
| 0x18011e279 | `jmp r8` | 9 | jt_present | jt_dropped |
| 0x18011e5c2 | `jmp r8` | 17 | jt_present | jt_dropped |
| 0x18011e7d1 | `jmp rcx` | 3 | jt_present | jt_dropped |
| 0x18011e83d | `jmp rcx` | 20 | jt_present | jt_dropped |
| 0x180120b1d | `jmp r8` | 11 | jt_present | jt_dropped |
| 0x1801a2a4b | `jmp r9` | 16 | jt_present | jt_dropped |
| 0x1801a31fb | `jmp r9` | 17 | jt_dropped | jt_dropped |
| 0x1801ac729 | `jmp rcx` | 5 | jt_present | jt_dropped |

- 8 VA は `rt_ott-F` (#1206 時点の旧 run、`REPORT_APPENDIX_1206.md` §17) と完全一致。
- 標的数は before/after で全 site 一致 (展開で標的は失われていない)。

## 解釈 (未解決)

- before の `jt_present` 7 件が after で `jt_dropped` に変わっている。`jt-chain` 展開を掛けた 8 site の全てが、展開後の監査では表 (`jt`) として認識されなくなる。
- 「展開が効いて全件解消」ではない。展開後の IR を audit が `jt_dropped` と判定する機構 (rewrite 側の cmp/je 列か、`ir_icall_restore.py` 側か、audit 側の判定か) は本 run では切り分けていない。`#1403` で Fresh Air に見られた before/after 件数不一致と同型の疑い。
- 件数の結論: `jt_dropped` は before 1 件 / after 8 件。展開 pass が OTT F の 8 site に掛かった後も、監査上の `jt_dropped` は 8 件のまま。

未解決: `jt_present → jt_dropped` 遷移の機構の切り分け → #1763 (ICALL-38・親 #1573)。

## 鮮度の証跡 (`docs/WORKFLOW.md` §6)

- 測定 commit: `d16d7f5d`。
- `git diff d16d7f5d HEAD -- tools/icall ':(exclude)*.md'` の出力: 空 (コード差分 0)。
- よって測定値は現 head でも有効。再測定は不要。
