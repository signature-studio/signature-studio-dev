# icall REPORT 付録: Fresh Air 残落ち 6 件 (#1026 §13 全文・#1067 ICALL-20 段別の切り分け)

> 正本: `tools/icall/REPORT.md` §13。`REPORT_APPENDIX.md` §13 から分割移動した (250 行上限・全文の置き場は本ファイルだけ)。見出し番号は §13 のまま。

## 13. #1026 (ICALL-18): Fresh Air SlateCore の復元後残落ち 6 件の分類

既知類型との関係: 該当なし (新規類型は未確定。残 6 件は RetDec の vtable 呼出し落ちで、icall §4 D1 の残存形)。
数値の出所: 既存 `work-icall` 監査 JSON (`rt_freshair-core/`) の再集計。その監査を生成した HEAD はリポジトリに記録が無いため、本節では特定しない。本 run では `work-icall` が無く再実行していない (未検証)。素材 `plugins-freshair` (`Fresh Air.Win.zip` → `SlateCore.core_64`, 36,285,952 B) からの機械語確認は、本 run では再実行していない (初回 PR の記載のみ)。

### 13.1 残 6 件 (復元後 IR に call が無い非 IAT 間接 call)

再現: `python3 tools/icall/diff/fa_residual.py tools/icall/work/rt_freshair-core` (`sites_after.json` を読むだけ, 即時)。
出力 (実測): `non-IAT call sites 91 / lost 6 (audit call_lost_non_iat=6)`、`by IR status: {'other_insn:br': 1, 'dropped': 5}`。

| 関数 | 落ち site (VA) | 命令 | IR 状態 |
|---|---|---|---|
| `0x180c97aa0` (参照解放 + 2 段 vtable) | `0x180c97e17` | `call [rax+0x10]` | other_insn:br (call 以外の br のみ残る) |
| 同 | `0x180c97e38` | `call [rax+0x20]` | dropped |
| 同 | `0x180c97e56` | `call [rax+0x8]` | dropped |
| 同 | `0x180c97e71` | `call [rax+0x20]` | dropped |
| `0x180da6e60` (本体 ~1.4k 行) | `0x180da7261` | `call [rax+0x30]` | dropped |
| 同 | `0x180da72fc` | `call [rax+0x30]` | dropped |

- 残 6 件は全て `kind=vtable` (`call qword ptr [rax+disp]`)。reg / rip_data / IAT は復元後 0 落ち。
- `0x180c97aa0` は `lock xadd` で参照を落とした後 `mov rax,[rcx]` → `call [rax+0x10]` (`0x180c97e14`〜`0x180c97e17`) の形。
- `0x180c97aa0` の IR は before 118 行・call 0 件、after 139 行・call 5 件 (PR 初版時の記載・本 run で未再測)。
- 原因 (推定, 未検証): 復元 pass の対象外の vtable 直接 call 形 (`call [rax+disp]`、rax は直前の `mov rax,[rcx]`)。decode 段で捨てられる経路 (icall §3.1-1) と同じと見られるが、IR 上の捨て位置は未確定。
- `0x180c97e17` は call の後に br だけが残り、call のみが消えた形。

### 13.2 未実施 (受入条件 1)

- Fresh Air SlateCore closure の wasm 実行と native 差分: **未実施**。`tools/ott/native/ottnat.py` と `diff/matrix.py` は OTT 専用 (`OTT_vst2_win64.dll` 固定) で、Fresh Air 用の native 実行ハーネスと入力 matrix が無い。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Fresh Air SlateCore closure の wasm 化・native 差分 (受入条件 1) | 監査のみ。出力 bit 一致は未確認 | 子 #1299 (ICALL-25、親 #1067 / #1026) |
| 残 6 件 (vtable 直接 call の decode 段落ち) の真因特定と修復 | 2 関数 (`0x180c97aa0` / `0x180da6e60`) の復元不完全 | 子 #1298 (ICALL-24、親 #1067 / #1026) |

### 13.3 #1067 (ICALL-20): 段別の切り分け (推定を含む・未検証)

本節の記述は、§13.1 の表 (VA・命令・IR 状態) を前提にする。表は再掲しない。

**区分の凡例**: 「実測」= 本 run で再現した値 / 「既存記録」= 過去 run の記録で、本 run では再現していない / 「推定」= 根拠が不足し、確認できていない。

| 主張 | 区分 | 根拠・状態 |
|---|---|---|
| 6 件はいずれも RetDec dsm に `call qword ptr [rax+disp]` として存在する | 既存記録 | 生成元の `before.0.drc.dsm` は本 run に無い (`work/` は gitignore・素材 `work-icall` 不在)。命令の読み落としではない、という判断の根拠は再確認できない |
| `0x180c97aa0` の 4 件は `br i1 undef` 由来の分岐に囲まれ、call を含むブロックが before IR に無い | 既存記録 | `before.0.drc.ll` の行番号 2885〜2921 は旧 dump の記録で、再確認不能 |
| `0x180da6e60` の 2 件は分岐・load・比較が残り、call の IR 命令だけが無い | 既存記録 | 行番号 5114〜5165 は旧 dump の記録で、再確認不能。`undef` でない具体比較を持つという点も未確認 |
| 復元 pass (`icall_rewrite.py`) は 6 件を含まない | 既存記録 (未確認) | `rewrite.txt` の `rewrote 131 funcs, 98 sites` は出力書式 (`icall_rewrite.py` の print 行) と一致するが、この値の出所 (どの HEAD・どの素材の run か) は未確認 |
| 欠落は RetDec 段で既に生じている | **推定** | 上の既存記録と「復元 pass が含まない」を組み合わせた推定。RetDec 段と後段の境界を実測で切り分けていない |
| `br i1 undef` になった条件 (どの load・比較が分岐条件か) | **未確定** | 特定していない。RetDec の undef 化の条件も未特定 |

**再現手段の現状**:

- 既存 dump への grep: 不可。dump (`before.0.drc.dsm` / `before.0.drc.ll` / `rewrite.txt`) は `tools/icall/work/` (gitignore) にあり、本 run に存在しない。
- RetDec 再実行: 不可。Fresh Air の入力は `plugins-freshair` と `work-icall` (`rt_freshair-core`) を要する。本 run の素材は `fl-win64` のみ。
- したがって本節の段別の主張は、素材を揃えた run で dump を生成し直すまで「既存記録・推定」のままとする。

**本 run で再現できた実測**: §13.1 の表と `non-IAT call sites 91 / lost 6` のみ (いずれも PR 初版の記録。本 run は `fa_residual.py` を実行できなかった)。

| 指標 | 復元前 `audit_before.json` | 復元後 `audit_after.json` | 区分 |
|---|--:|--:|---|
| `call_total` | 123 | 123 | 既存記録 |
| `call_lost_non_iat` | 87 | 6 | 既存記録 |
| `call_dropped` | 80 | 5 | 既存記録 |
| `call_other` (`other_insn`) | 7 | 1 | 既存記録 |

測定 HEAD: `c4e93550` (`tools/icall/*.py` は `origin/main` `ca0f59a1` まで差分 0 (本 PR の `git diff c4e93550 HEAD -- 'tools/icall/*.py'` も 0 行))。

**未解決** (子 issue): 段別の切り分けの再現 (素材 `work-icall`・`plugins-freshair` を揃えた run で dump を生成し直す) → 子 #1298 の受入条件に含める。
