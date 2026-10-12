# 付録: liftdiff 回帰 A/B・Ablation・検収・再現性 (CAB-232/233) — tools/liftdiff/

> **正本**: `tools/liftdiff/REPORT.md` (結論・§1〜§4・§6 成果物・§7 未解決)。本書は 250 行上限 (`docs/DOC_MAP.md` §1) のため
> 本体から**そのまま分割移動**した §5 / §5.1 / §5.2 / §6.1 / §6.2 の全文 (節番号は本体の参照と一致)。

## 5. 回帰 — fresh HEAD との A/B (本チケットで実測)

HEAD (= f555629) の tools/liftdiff を作業ツリー外に展開し (REPO を実リポジトリに差し替え、入力 IR は共有)、
**同じ IR・同じ手順**で A/B した (CAB-232 の手法を再現・検証)。
検収では **b8e762d (HEAD) から `liftdiff_e2e.sh` をまるごと再実行**して同じ値を再現した
(実測 1 分 2.4 s / load average 開始 3.08・終了 2.47, 12 shard):

| 指標 | HEAD (fresh A/B) | CAB-233 | 検収再実行 (HEAD) | 判定 |
|---|---|---|---|---|
| OTT closure (212 関数) | 39 / 106 / 67、D1〜D6 全検出 | **38 / 108 / 66、D1〜D6 全検出** (D3 callsite_arg_drop 12→14) | 38 / 108 / 66、D1〜D6 全検出 | 検出維持・感度向上 |
| unit#18 check 1 / check 2 | PASS / PASS | PASS / PASS | PASS / PASS | 維持 |
| unit#18 check 3 (4123c0) | **FAIL (native 53 / wasm 25)** | FAIL (67 / 46) | FAIL (67 / 46) | **HEAD でも同一 FAIL** = CAB-131 由来 (§5.1) |
| unit#18 case 追加所見 | 446370 = wasm_trap / 455790 = unexec | **446370 = diff / 455790 = match** | 同 | 改善 |
| m11 closure sample:800 | 355 / 198 / 247 | **353 / 217 / 230** | **353 / 217 / 230** (93 s) | match −2・unexec −17・mismatch +19 は全て深部乖離型 (callee_divergence 10・wasm_trap 5・import_call_seq 5・icall_drop 4・memory_semantics 2。leaf 自己欠陥 45→49) = 充実状態で深部まで到達し wasm lift 欠陥が可視化されたもので検出器の劣化ではない |

判定基準 (m11 sample:800 356/205/239 非劣化) に対し、一致は 355→353 (−0.6%)・実行不能は 247→230 (−6.8%)。
**OTT 欠陥検出・unit#18 の既有 2 チェックは完全維持**。

## 5.1 check 3 (4123c0) の FAIL は既存 (CAB-131 由来)

`check 3` は **CAB-233 以前から FAIL**。A/B 取りした fba272c (CAB-232) 側でも同一条件で FAIL し、
HEAD (b8e762d) でも FAIL (native 67 / wasm 46)。原因は tools/m11/work/boot_final3.ll が CAB-131 の再生成
(10-10 20:48) で resourcestring 初期化ループの wasm トレースが 25 → 46 に増えたこと。
**本チケット (liftdiff) とは無関係**で fix 対象外。
`liftdiff_e2e.sh` は check 3 で exit 1 になるため、検収时は [4/4] を別途手動実行した (§6 参照)。

## 5.2 Ablation (規則 41)

主要な効果に対して、その修正だけを外した対照を 3 つ実施した (いずれも `work/abl/` にビルド、
結果は本節の実測):

| ablation | 操作 | 結果 |
|---|---|---|
| 旧 rt (fba272c) 全体 | CAB-233 の rt 変更を全部戻した ld_native で m11 bootstate | **units_run=17、unit #17 が segv** (rip_rva=0x1d15a) = CAB-233 前の挙動を再現 |
| **GetProcAddress 仮 proc 応答の除去** | `GetProcAddress` を `return 0` に差し替え (TLS/その他は温存) | flelift entry が **InitCount=246 → 17** (rip_rva=0xffffffffffc00000、rcx=-1 で proc 0 を call) → **仮 proc 応答が起動延伸の主因** |
| **TLS 配列の heap 移送だけ revert** | `TlsGetValue/TlsSetValue` を旧 `ld_tls_vals[]` 実装に戻す | m11 units_run は **22 のまま** (不変) → 17→22 は TLS 変更由来**ではない** |

→ CAB-233 の stub 拡充が native boot 延伸に効いているのは **GetProcAddress の仮 proc** (実測 +229 unit)。
TLS 配列の heap 化は native 起動には影響せず、**状態移送 (SHEAP) で wasm 側にも TLS 値が写る**効果
(m11 unit #17 が wasm 側でも完走) として働く。**

## 6.1 検収 (CAB-233) で実施した独立検証

| 検証 | 手法 | 結果 |
|---|---|---|
| unit 到達/完走 | `tests/recheck_boot_units.py` (自前 PE パーサ + ldlib 非依存のランナ駆動 + 0x4120c0 の逆アセンブル) | 到達 **928** (一致)。完走 **890** (§2.1) |
| f_410360 カスケード | stored batch jsonl を別アルゴリズムで再分類 | 246 / 327 / 368 / case 941 / 関数 211 — **すべて実装値と一致** |
| flelift 全数再採点 | `batch --set closure --shards 14` を HEAD から再実行 (585 s) | 一致 4,092 / 不一致 767 / 実行不能 **2,562** (§6.2) |
| m11 sample:800 A/B | e2e [4/4] を HEAD から再実行 (93 s) | **353 / 217 / 230** = CAB-233 値と完全一致 |
| 残 3 unit の原因 | `boot_probe.py` + 0x4e0fab/0x4e1a3c/0x513da9 の逆アセンブル + block25158 検証 | `default.moe`・magic check・VMT 間接 call を確認。フレーム破壊は experiment revert 済みで HEAD では未再現 |
| ⑤ limit 外の変数 | `ld_tls_next` の unbounded 性をコード/実測で確認 | TlsAlloc **1 回** (index 0)。1025 回目で slot 0 に折り返す設計だが未発火 |

## 6.2 全数採点の再現性について (負荷依存・規則 38)

同じ boot_state.json で `batch --set closure --shards 14` を再実行 (585 s) すると verdict 合計が
**4,092 / 767 / 2,562** となり、REPORT の 4,182 / 741 / 2,498 とは **一致 90・不一致 26・実行不能 64 の差**。
(bootstate 24.4 s・batch 585 s の所要自体は完全再現)。原因は **native ランナの `badjson` (88 case) /
timeout (native 248 / wasm 346) が負荷で変動**することで、同一 boot 状態・同一 wasm でも verdict がぶれるため
(小規模 sample:200 を 3 回回すと 102/22/76 で完全安定 = 規模依存の Shot noise)。

**結論: 全数採点の絶対値 (2,498 / 941 / 4,182 / 741) は 1 run の snapshot で数十オーダー変動する。**
下流の判断は (a) `compare_bootstate.py` の遷移 (旧→新) の方向性、(b) `cascade_410360.py` の
case 単位分類 (完全再現) を基準にすること。「実行不能 2,498」は target 値に使えない。
