# élastique 付録 #4535: pdata の無い `.text` 関数の範囲の比較 (本文 REPORT.md §3 から移動)

本文の結論は REPORT.md §3 の「pdata の無い `.text` 関数の範囲の決め方」。測定 commit `7fe2ea865`。

「対 main」は main `ab4b94258` の `data/entries.csv` との差 (`513791f11` の `entries.csv` と同一 md5 `131a303a`)。参考版は `ipp_entries.py` の `fn_span` を一時的に差し替えて実行し、コミットしていない (`git checkout -- data/entries.csv` で戻した)。

| 版 | `.text` (pdata 無し) の範囲 | IPPCODE (pdata 無し) の範囲 | 族候補 | `identified` | `exact_dsp_internal_no_export` | 対 main: 区分変化 / 名前変化 / depth 変化 |
|---|---|---|---|---|---|---|
| main (`ret` で停止) | `ret` まで | 次の先頭・0x2000 | 98 | 34 | 24 | — |
| **採用 C** | 次の先頭まで (上限なし) | 次の先頭・0x2000 | 108 | 34 | 14 | 10 / 76 / 62 |
| 参考 B: `.text` を 0x2000 で打ち切り | 次の先頭・0x2000 | 次の先頭・0x2000 | 108 | 34 | 14 | 10 / 76 / 62 |
| 参考 F: IPPCODE だけ 0x400 | 次の先頭まで | 次の先頭・0x400 | 108 | 34 | 14 | 10 / 76 / 62 |
| 参考 G: `.text` だけ 0x400 | 次の先頭・0x400 | 次の先頭・0x2000 | 100 | **40** | 16 | 8 / 69 / 49 |
| 参考 D: 全節 0x400 | 次の先頭・0x400 | 次の先頭・0x400 | 100 | **40** | 16 | 8 / 69 / 49 |

- **`entries.csv` の変化 (採用 C 対 main)**: 197 入口のうち `class` が変わったのは 10 (`exact_dsp_internal_no_export` → `family_candidates`)、`names` が変わったのは 76、`dsp_depth` が変わったのは 62、`dsp_rva` が変わったのは 56。`names` の増加は 848 件 (54 名・`ippsConvCyclic4x4_32f32fc`・`ippsFIR_32f`・`ippsConv_32f` 等が多い)、減少は 42 件 (7 名)。`identified` は 34 のまま (入口の集合は不変)。
- 採用 C と参考 F は `entries.csv` が完全一致 (区分・名前・depth とも 0 件差)。IPPCODE 側の上限 (0x400 か 0x2000) は入口の結果に効かない。
- 採用 C と参考 B は区分・depth は一致するが、名前集合が 58 入口で違う。`.text` の 0x2000 打ち切りは名前を変える。
- `identified` 34→40 (参考 G・D) を起こすのは `.text` 側の 0x400 で、採用 C との差は区分 8・名前 67・depth 13。
- 採用 C は `.text` の範囲を上限なしにした。末尾の命令は `nop` 2,244・`int3` 149・`ret` 106 (2,528 本体のうち命令境界一致 2,523)。`.text` の上限を 0x400 にした G は `identified` を 40 にするが、0x400 は範囲を任意に切った値で、根拠 (次の先頭以外の境界) が無いので採らない。
- 採用 C の `entries.csv` は、main から区分が 10 入口動く (`exact_dsp_internal_no_export` → `family_candidates`)。`identified` は 34 のまま。

