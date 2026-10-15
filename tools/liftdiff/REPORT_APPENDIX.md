# 付録: liftdiff 回帰 A/B・Ablation・検収・再現性 (CAB-232/233) — tools/liftdiff/

> **正本**: `tools/liftdiff/REPORT.md` (結論・§1〜§4・§6 成果物・§7 未解決)。本書は 250 行上限 (`docs/DOC_MAP.md` §1) のため
> 本体から**そのまま分割移動**した §5 / §5.1 / §5.2 / §6.1 / §6.2 / §8 / §9 の全文 (節番号は本体の参照と一致)。

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

### 5.1.1 check 3 の判定条件更新と Actions 上の再現 (#122)

`check 3` の閾値 `wasm_trace <= 6` は boot_final3.ll 再生成前 (wasm 4〜6) の値で、現 IR (native 67 / wasm 46) では FAIL し
`liftdiff_e2e.sh` が exit 1 になっていた。欠陥 (callee 0x41c820 arg1 が wasm で 0 = `callsite_arg_drop`、heap への 7 件の
resourcestring 書込み欠落 = mem diff) は同じ形で残っているため、判定を `native_trace > wasm_trace` ∧ `callsite_arg_drop` ∧ `mem diff > 0` に変更した。
あわせて `liftdiff_e2e.sh` に `--m11-only` (OTT 旧 chain の ott.ll が無い環境用)・入力/依存 (numpy capstone pefile) の事前検査を追加した。

Actions runner (4 core, 実測 2026-10-12): 素材 `oc_artifacts: fl-win64 toolchain-emsdk work-m11 work-liftdiff`、`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。
`bash tools/liftdiff/liftdiff_e2e.sh --m11-only` が **exit 0 / 128 s** (load average 開始 0.91 → 終了 4.72、batch は 12 shard で 81 s)。
unit#18 check 1-3 PASS、m11 sample:800 = **一致 353 / 不一致 217 / 実行不能 230** (§5 の CAB-233 値と同一)。
(別に 4 shard で走らせた batch は 346/224/230 = shard 数・負荷によるぶれ、§6.2。)
OTT 旧 chain (D1〜D6) は `tools/ott/work/ott.ll` (`work-m6-ott`) と OTT_vst2_win64.dll (`analysis-ott-binaries`) が必要で、この run では**未実施**。

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

## 8. m11 wasm_trap 578 関数のトリアージ (LD-5 / #236)

集計 = `python3 tools/liftdiff/tests/triage_wasm_trap.py > tools/liftdiff/results/m11_wasm_trap_triage.md` (cwd 非依存。表・内訳はそちらが正本)。
入力は既存 closure の batch jsonl (`work/m11/batch_closure.jsonl`、再走なし)。Refs #236 / 個別原因は #307 (LD-7) へ。

再現済み (スクリプトが `results/` に出力。TSV を 1 行壊すと 578 → 577 になることを確認):

- **unreachable 218 は全件 `function_4128b0__lifted` で trap**。frame 名に signature / thunk を含むものは 0。
  wasm 側 import 呼出列には全件 `ExitProcess` があり、native 側は 0 件。
- 連鎖は `__lifted < function_4128b0 < function_412a40 < {function_4096b0 (144) | function_412a60 (74)}`。
  frame [3] = **`function_412a40` の呼出元** (旧版は `function_412a60` の呼出元と誤表記していた)。
- OOB 222 は最上位 frame が 71 種に分散 (`function_414ad0` 68 件が最多)。hang 39・badjson 25・indirect_sig 3・arith/stack/other 計 4。個別原因は未確定 (#307)。
- TSV 578 のうち 67 件は今の jsonl に wasm_trap case が無い (jsonl 側のみ 71 件)。TSV と jsonl は別 run のため (§6.2)。

現スナップショット (`work/m11/` の wasm / IR / build.json) での観測 (`results/` §6 に出力。**jsonl を作った build と同一かは未確認**。
スナップショットの mtime は jsonl より新しい):

- wasm バイナリ中に `signature_mismatch` / `sig_mismatch` / `thunk` は 0 件、`build.json` の wasm-ld `signature mismatch` 警告も 0 件。
  M11 §2.4 の thunk は sigfix 済みと整合するが、jsonl 取得時点の build での確認ではない。
- IR の `function_4128b0__lifted` では `ExitProcess` 呼出 (`dec_label_pc_4129f7`) の直後が `unreachable` (1 箇所)。
  stub `ExitProcess` が戻る wasm でここに落ちる、という推論は**未検証** (stub の挙動を変えた再走はしていない)。
- 分岐点 (native では `ExitProcess` に入らず wasm だけが入る理由) は上流にあり**未特定** → #307。

## 9. wasm_trap の個別原因 (LD-7 / #307、#305 上に積んだ分)

集計 = `tests/trace_diverge_unreachable.py` → `results/m11_unreachable_diverge.md`、`tests/oob_414ad0.py` → `results/m11_oob_414ad0.md` (数値・表はそちらが正本)。
入力は §8 と同じ既存 batch jsonl (再走なし) と PE (`LD_M11_PE` または `--pe`)。
- LD-41 (#1238): 型 C・D の P3 の 0x417b70 の静的確認 (idiv/udiv 対応・次 entry 組) は `REPORT_APPENDIX_LD41.md` に分割移動 (動的確認は未達)。

- **unreachable (最初の trap が unreachable の 220 関数)**: うち trace_head 内で native/wasm の食い違いを観測した 212 件を対象に、
  最初に食い違う直前の関数 L を数える。trace_head が両側で完全一致し食い違い未観測の 8 件 (trace_head は最大 12 件で打切り) は分岐点集計から除外した。
  `function_410320` が最多 (82 件)。機械語は `test dl,dl; jl; call qword ptr [rax-0x30]` (VMT 間接 call) だが、lift 後 IR は `ret %arg1` のみで call が無い。
  native は 410320 の次に 0x409410 へ進み (例 0x6ae290)、wasm は 0x40f9e0 へ進む。
  同型の **D15 型候補** (メモリ間接 call を持ち、IR の call 数 ≤ 機械語の直接 call 先 distinct 数) は 0x40f9e0・0x1253610・0x678480 を含め合計 86/212。
  この判定は call site / block を対応づけておらず (直接 call の脱落でも成立しうる)、D15 の**確定ではない**。
  410320 については IR が `ret %arg1` のみで call 0 件、機械語は間接 call 1 件 (上記) であり、候補としては強い。残り 126 件は別の分岐 (0x417b70 32 / 0x40a3d0 24 / 0x418be0 20 ほか)。**未特定**。
- ExitProcess へ至る連鎖 (例 0x6ae290: wasm のみ `409470 → 409730 → 4096d0 → 4096b0 → 412a40 → 4128b0`) は「alloc 失敗を示す Delphi の runerror 経路」と読めるが、
  410320 の call 脱落からその経路に入るまでの因果は trace_head (最大 12 件) に収まらず**直接確認していない** (推定)。
- **分岐の型 (LD-17 / #864)**: 残りを排他的に型 B (L が ret まで call 無し・tail jump 無し) / C (L の直接 call 先で分岐) / D (直接 call 先に無い) に分類した。件数は `results/m11_unreachable_diverge.md` §2 が正本。
  型 B は「L の内部では食い違わず、L の戻り後の呼出元で次 entry が現れる」と読める (推定)。根拠は B に入る L の機械語を ret まで読んで jmp 先 (tail jump) が無いことを確認した点のみ (`tail_jmps`)。戻り後の実際の呼出元は未確認。個別原因は未特定 → 子 issue #1034 (型 B)・#1035 (型 C・D)。
- **型 B の再検証 (LD-27 / #1034)**: 完全 trace での再検証・X/M/R の類型・rax の導出と再現手順は `REPORT_APPENDIX_LD27.md` に記録 (件数の正本は `results/m11_typeb_cause.md`)。受入条件は部分達成 (R 類の個別原因・rax の直接計測が未完) で、残りは #1034 に残す。
- **OOB function_414ad0 系 (68 件)**: 機械語は入口 rcx (var 文字列のアドレス) の 1 段 deref `mov r,[rbx]` が 4 箇所 (0x414af3/0x414b49/0x414b64/0x414b78)。
  lift 後 IR には `%arg1` を ptr とする load が 0 件で、`%arg1` を値のまま `icmp`/`add` に使っている (ldfix F3a/F3b 型の値↔アドレス取り違え)。
  68 件は全て最上位 trap frame が `function_414ad0` (= wasm は 414ad0 に到達している)。wasm trace_head に 414ad0 が現れるのは 41 件で、
  残り 27 件は trace_head (最大 12 件) に位置が保持されていないだけで、**非到達・別原因とは言えない** (原因は 41 件と同じか否か未確認)。 27 件の到達確認 (25/27 到達) と OOB 他の最上位 frame 集計 (LD-18 / #865) は `REPORT_APPENDIX_865.md` (新規節・件数の定義もそこ)。

### 手動実測 (単体 run、スクリプト非対応・第三者再現不可)

次は `tools/liftdiff/work/` 配下の未 commit 成果物に基づく手元観測で、**受入条件 2 の根拠には含めない** (AGENTS §4-4: `work/` は commit 対象外)。
再現用のパッチ・再生成スクリプトは commit していない (起票先は下表)。
- 単体 `run --fn 0x414ad0 --pattern q0`: callee 0x414850 の arg0 が native=0x22479388 / wasm=0x5 (※ 本 run では再実行していない)。
- 4 箇所に `load` を足した IR (`work/ld7/`) で再ビルドした単体実行: callee_divergence タグが消え memory_semantics になり、
  z / s / p0 は wasm=trap/ok → wasm=ok (native_fault) になった。p1 / p01 / pall / pall2 / qall は native・wasm とも fault のまま。

### 検証範囲 / 範囲外
- 範囲内: 2 スクリプトの出力 (`results/*.md`) の再計算、ネガティブコントロール (`m11_unreachable_diverge.md` §5: 候補 4 関数の IR に call を足すと全て非候補に変わる)。
- 範囲外: 上記 手動実測、`liftdiff_e2e.sh`・batch 再走、`mach()` の線形走査 (最初の `ret`/`int3` まで) による早期 return 関数の間接 call 数え落とし。

### 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| unreachable の 410320 以外 126 件の分岐 | 原因未特定 | #307 に残す + 子 issue 起票を PM に依頼 (PR コメント) |
| 27 件のうち 0x6525b0 (414ad0 非到達) と 0x66ea90 (再走で trap 無し)・414ad0 系で他パターンの fault | 原因未確認 | 同上 |
| OOB 他の最上位 frame (上位 5 種以外) の種類数・内訳 | 未集計 (`oob_top_frames.py` は種類数を出力しない。旧記述の「70 種」は出典なしのため撤回) | 同上 |
| `load` 追加 IR の再現手段 (patch / 再生成スクリプト) — 受入条件 1 | 手動実測が検証不能 | #683 (共通。重複起票しない) |
| D15 候補の call site 対応づけ (機械語 call ↔ IR block) | 候補止まり | 同上 |
| `targets/m11.json` の `pe` が環境固有の絶対パス固定 (`[WIN64]` 相当) | `--pe` / `LD_M11_PE` が必須 | #294 |

### 再現手順
素材は `work-m11` (`tools/m11/work/`)・`work-liftdiff` (`tools/liftdiff/work/`)・`fl-win64` (`[WIN64]`、`docs/WORKFLOW.md` §11 の展開手順)。
```
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
export LD_M11_PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"
pip install numpy capstone pefile
python3 tools/liftdiff/tests/trace_diverge_unreachable.py > tools/liftdiff/results/m11_unreachable_diverge.md
python3 tools/liftdiff/tests/oob_414ad0.py > tools/liftdiff/results/m11_oob_414ad0.md
```
LD-17 (#864) の型分類は `results/m11_unreachable_diverge.md` §2 (同じスクリプトの出力)。PE 展開は `block00031_PE.bin` 1 ファイルで足りる (実測 22227016 bytes)。スクリプトの入力は `work-liftdiff` (batch_closure.jsonl) と `work-m11` (boot_final3.ll) を要するため、これら素材が無い環境では再生成できない。
単体実行 (手動実測) は `[WIN64]` の PE を指す `pe` に書き換えた `targets/m11.json` の複製で `python3 liftdiff.py run <target.json> --fn 0x414ad0 --state auto --nobuild -v` (`targets/m11.json` 自体の固定パスは #294)。

#### 型 C・D の原因候補 (LD-28 / #1035)
全文・測定 commit・鮮度の証跡・数値例は [`REPORT_APPENDIX_LD28.md`](REPORT_APPENDIX_LD28.md) (分割移動)。結論: 型 C・D は原因候補 P1・P2・P3 に分類 (候補であり確定ではない)。0x417b70 の idiv/udiv 仮説は動的未確認 → #1238 (LD-41)。

## 10. OTT 旧 chain (D1〜D6) の Actions 再現 (LD-8 / #406)

既知類型との関係 (DEFECTS.md): 新規類型なし (D1〜D6 は OTT 旧 chain の既存分類 = `check_ott.py`)。

### 実測 run (受入条件 1 の再実行)

- **Actions run ID**: `38430714782` (`GITHUB_RUN_ID`。本節の実測 run)。ログは commit 済みの [`results/liftdiff_e2e_run38430714782_9cadda79.log`](results/liftdiff_e2e_run38430714782_9cadda79.log) (`results/` は gitignore 対象外)。Actions 上の run ログには `liftdiff_e2e.sh` の stdout を残していないため、この commit 済みログが根拠。
- **検証 HEAD**: `9cadda79` (PR の最終 head。`main` `909cf37b` を merge した後の commit。merge 後も e2e を再実行)
- **実行**: `bash tools/liftdiff/liftdiff_e2e.sh` (`--m11-only` なし・既定 `sample:800`)。`ANALYSIS_DIR=$HOME/analysis`・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`・`PLUGINS_DIR=$HOME/analysis/plugins`・`TMPDIR=$RUNNER_TEMP`。素材は `oc_artifacts` の 6 件を `$HOME/artifacts` で実在確認してから展開。

| 検証 HEAD | 結果 | 所要 (wall clock) | load (1 分平均) | [2/4] 212 関数 (一致 / 不一致 / 実行不能) | D1 / D2 / D3 / D4_D5 / D6 |
|---|---|---|---|---|---|
| `9cadda79` (本節・最終 head) | exit 0・`LIFTDIFF_E2E PASS` | 179 s | 終了時 6.05 (開始時は未取得) | **35 / 112 / 65** | 4 / 6 / 14 / 20 / 26 |

- **ネガコン**: 無加工 exit 0 + NC[D1] / NC[D2] / NC[D3] / NC[D6] が各 exit 1 = 5/5 PASS
- **ログ抜粋** (commit 済みログの該当行をそのまま):
  ```
  OTT_SUMMARY {"functions": 212, "match": 35, "mismatch": 112, "unexec": 65, "defects": {"D1_indirect_call_drop": 4, "D2_short_global": 6, "D3_callsite_arg_drop": 14, "D4_D5_c_defined_ports": 20, "D6_body_layer": 26}, ...}
  PASS positive: 無加工 batch → exit 0
  PASS NC[D1]: タグ除去 → check_ott.py exit 1
  PASS NC[D2]: タグ除去 → check_ott.py exit 1
  PASS NC[D3]: タグ除去 → check_ott.py exit 1
  PASS NC[D6]: タグ除去 → check_ott.py exit 1
  PASS _UStrAsg: 旧値(dest が保持する文字列)の解放が native と異なる (mem diff)
  PASS Delphi Move(409c80): [rcx] が spill alloca を直接読む (spill_slot_deref)
  PASS 4123c0: resourcestring 初期化が wasm で脱落 (native entry 67 > wasm 46, callsite_arg_drop, mem diff 7)
  関数数 800: 一致 361 / 不一致 229 / 実行不能 210
  LIFTDIFF_E2E PASS
  ```
- **注意**: 以前の記録 (run `38423629378` の 33/110/69 と 35/112/65 など) は、ログが残っておらず run との対応を確認できないため、受入の根拠にしない。前回比の差分の原因切り分けは #825。
- **他段 (本 run)**: [0/4] 単体 23 tests OK (`Ran 23 tests`・`OK`) / [1/4] build ・ネガコン 5/5 / [3/4] unit #18 3 件 PASS (`UStrAsg` mem diff・`Move(409c80)` spill_slot_deref・`4123c0` 脱落 native 67 > wasm 46) / [4/4] `sample:800` 一致 361 / 不一致 229 / 実行不能 210 (batch 105 s)。boot は unit 22 で native segv (`units_run=22/942`、判定条件外)。
- **素材 (`oc_artifacts`)**: `fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff work-m6-ott analysis-ott-binaries` (PR 本文と同一)。`$HOME/artifacts` の 7 件の実在を確認して展開:
  - `fl-win64` → `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`)
  - `work-m11` / `work-liftdiff` / `work-m6-ott` → repo 直下の `tools/{m11,liftdiff,m6}/work/` 他 (gitignore・commit なし)
  - `analysis-ott-binaries` → `$HOME/analysis/plugins/ott/binaries/` (`ANALYSIS_DIR=$HOME/analysis`)
  - `toolchain-retdec` → [RETDEC]・`toolchain-emsdk` → [EMSDK] (展開済み。`docs/REFERENCES.md`)
  - python 依存: `numpy capstone pefile` は本 run 前に `pip install` で導入 (素の runner では要導入。未解決表を参照)
- **前回比**: 旧 3 回実測 (`59eea5c`) 38 / 108 / 66 との差分 (D3・D4_D5 の変化) は #825 で切り分ける。上の表の 35/112/65 は本 run の実測値。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 旧実測 (38/108/66) から本 run (35/112/65) への OTT 集計変化 (D3 14・D4_D5 18→20) の原因切り分け | D3・D4_D5 の変化理由が不明。受入判定 (D1〜D6 検出) には影響しない | #825 |
| runner に numpy/capstone/pefile が無く e2e 前に `pip install` が必要 | 素の Actions で e2e が exit 2 (`missing python deps`) | PM に起票依頼 (agent-setup への追加) |
| `fl-win64` / `analysis-ott-binaries` が agent-setup で自動展開されず手動展開が必要 | 同上 | PM に起票依頼 (agent-setup の別 issue) |

### 旧 3 回実測 (`59eea5c`・前回比の基準)

素材 (run 3 で全展開): `fl-win64 toolchain-emsdk work-m11 work-liftdiff work-m6-ott analysis-ott-binaries`。展開先: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`・`ANALYSIS_DIR=$HOME/analysis`・`tools/{m11,liftdiff,m6,ott}/work/` (repo 直下、gitignore)。

- **PE パス解決**: `targets/ott_old.json` の `pe` = `${PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll`。`PLUGINS_DIR` 未設定・`ANALYSIS_DIR=$HOME/analysis` で
  `ldlib/build_wasm.py` と同じ展開式 (`tools/shared/paths.py` 既定 `$ANALYSIS_DIR/plugins`) が `$HOME/analysis/plugins/ott/binaries/OTT_vst2_win64.dll` (3,146,752 B, 実在) に解決。
- **D1〜D6 検出** (`ld_native` + `build ott_old` + `batch --set closure --shards 4` + `tests/check_ott.py`、クリーン worktree で 3 回): 3 回とも exit 0・出力同一。
  212 関数 = 一致 38 / 不一致 108 / 実行不能 66。D1 icall_drop 4 / D2 short_global 6 / D3 callsite_arg_drop+arg_drop 14 / D4_D5 C 定義 port 18 / D6 body 層 26 (分母 = 212 関数、タグは複数重複あり)。
  ctor `18011d400` = mismatch (icall_drop, callsite_arg_drop, callee_divergence, import_call_seq, zero_init_drop, fp_flag_unreflected)。
  §5 の旧実測 (38/108/66) と完全一致。ott_old build は wasm 931,471 B (sig_mismatch 0, undefined 0)。
- **所要 (実測、4 vCPU runner)**: build+batch+check 20.2 / 22.7 / 21.8 s (load 0.67 / 1.16 / 1.24)。単独 build 6.4 s・batch 15.0 s・nc 0.37 s。
- **ネガコン** (`tests/nc_check_ott.sh`、新規・`liftdiff_e2e.sh` [2/4] から呼ぶ): batch 複製から D1 / D2 / D3 / D6 のタグを 1 系統ずつ除去 → `check_ott.py` は 4/4 とも exit 1、無加工は exit 0 (計 5/5 PASS)。
  1 つでも期待外なら nc は exit 1 で e2e が落ちる。
## 11. 比較系の偽陽性 2 類型の修正 (LD-11 / #548) — 全文

既知類型との関係: 該当なし (DEFECTS.md の lift 欠陥ではなく比較器側の偽陽性。f2 REPORT §7 起点)。本体 [`REPORT.md`](REPORT.md) §11 の要約から分割移動。

- `cmp_mem`: 部分上書きされた ptr 入りワードを byte 単位で比較 (変化 byte は生値、未変更 byte のみ ptr 正規化)。`ldlib/compare.py` `eq_block_bytewise`。
- wasm timeout: target JSON `wasm_timeout_ms` (既定 1000・正の整数) と `wasm_slowdown_bound` (既定 20・正の数) を `compare.wasm_timing_params` で検証 (0・負数・非数は ValueError)。検証済み値を `ld_runner.mjs`/`fle_runner.mjs` の `--timeout-ms=` に渡す。native ランナが case 所要 `ms` を出力し、`ms × wasm_slowdown_bound ≥ wasm_timeout_ms` なら `wasm_trap` でなく `wasm_timeout_native_long` (verdict は unexec 側)。
- 単体テスト `tests/test_compare_ld11.py` 23 件 (ネガコン込み。修正前 15 件 + 検証のネガコン 6 件 + 正例 2 件) は e2e の [0/4] で実行。

### 実測 (本 run・Actions runner)

素材: `fl-win64` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`work-m11`・`work-liftdiff` 展開、`toolchain-emsdk` 展開。コマンド: `bash tools/liftdiff/liftdiff_e2e.sh --m11-only` (HEAD = f694ef0)。

| run | exit | 所要 | [0/4] 単体テスト | sample:800 一致 / 不一致 / 実行不能 | wasm_timeout_native_long |
|---|---|---|---|---|---|
| 1 | 0 | 148 s | 23 OK | 358 / 212 / 230 | 0 件 |
| 2 | 0 | 149 s | 23 OK | 357 / 213 / 230 | 0 件 |
| 3 | 0 | 143 s | 23 OK | 357 / 213 / 230 | 0 件 |

[4/4] の不一致の主因は run 1 で callee_divergence 52・wasm_trap 35・memory_semantics 25・callsite_arg_drop 24 ほか (全文は run ログ)。

### origin/main との比較 (レビュー run の実測を引用・本 run では未再実測)

oc-reviewer の review (c002821 対象・同素材) で origin/main と PR head を各 3 run。main は 3 run とも 353 / 217 / 230。
PR head は 358 / 212 / 230 ×2 と 357 / 213 / 230 ×1 (本 run の 3 回と一致)。

- mismatch → match に変わった 4 関数: 0x1062200・0x1266e70・0x441500・0x9cecc0 (3/3 で安定)。いずれも main 側の差分は arena の ptr 1 ブロック (delta=0x400000 のずれ・部分上書き)。`cmp_mem` の変更の意図どおり。
- 0x959a40 は run 依存: main では 3/3 で `ret`・`trace` 差分あり、PR head では 2/3 で差分ゼロ (1/3 は差分あり)。`ret`/`trace` は `cmp_mem` の対象外のため、この変化は PR と無関係の非決定性。
- main 同士でも case outcome は run ごとに 3〜6 件揺れる (hang ↔ both_fault)。件数の変化を説明するときはこの揺らぎを前提にする。
- 閾値 `native_ms × 20 ≥ wasm_timeout_ms` は native が 50 ms を超える case の wasm 無限ループも unexec 側に入る。設計として受け入れ、件数は sample:800 で 0 件。

### 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入条件 1: 0x6cd8a0 の 9 パターン実 PE 実測 (sample:800 に含まれない・f2 系素材が必要) | #548 を Closes できない | f2 系素材の許可名追加 = #293 (PM 判断) |
| 非決定性: main 同士の case outcome の揺らぎ・0x959a40 の ret/trace 差分の run 依存 | 「+5」ではなく「安定 +4 + 揺らぎ 1 件」として扱う必要 | PM 判断: #548 へのコメントか新規 issue (未起票) |

## 12. 被覆拡大 2 パターン (LD-4 / #235、部分達成) — 全文

`cases.PATTERNS` に 2 pattern を追加 (`ldlib/cases.py`・`ldlib/session.py`)。どちらも既存 9 pattern の case 生成には影響しない。

- `vm0`: this 疑似オブジェクト。arena+0x1000 に VMT (arena+0x2000) への fixup ptr を置き、0 埋めの VMT を指す。
- `u16`: UTF-16 文字列 blob。arena+0x1000 に Delphi UnicodeString ヘッダ (refcnt=1, len) を置き、本文 UTF-16LE は +8 (arena+0x1008) に置く。引数はヘッダ先頭 (arena+0x1000) を渡す (`PATTERNS` の `('u16', {0}, 'u16', 0, 'small')`・加算 0)。

実測 (m11, sample:800, `--shards 12 --state auto`、base = origin/main 97f28539 / 新 = 本ブランチ):

| 項目 | base (9 pattern) | 新 (11 pattern) |
|---|---|---|
| 一致 / 不一致 / 実行不能 | 358 / 212 / 230 | 361 / 229 / 210 |
| 所要 (batch) | 1m39s (load 0.76) | 1m49s (load 0.31→1.35) |

関数単位の遷移: unexec→match 7 / unexec→mismatch 13 / match→mismatch 4 / match→match 354 / mismatch→mismatch 212 / unexec→unexec 210。
match→mismatch の 4 件 (0x8445b0・0x6681f0・0xfe8e80・0x528680) は新 pattern (vm0/u16) の case だけが diff/wasm_trap で、既存 9 pattern は変わらない (深部経路の露出)。
`liftdiff_e2e.sh --m11-only` は exit 0 (単体テスト・unit #18 の 3 検査 PASS・closure 361/229/210)。

(本体 REPORT §12 の要約元: `vm0`・`u16` 追加は sample:800 で 一致 358→361 / 不一致 212→229 / 実行不能 230→210 (base 97f28539 比)。)

### 12.1 fault 由来 this 疑似 pattern `fvm` (LD-23 / #975、部分達成)

- 実装: `cases.fvm_candidates` が `'s'` の native fault addr から this 候補の引数 index を推定 (`SMALL[i] ≤ addr-SMALL[i] < 0x40`)。
  `session._fvm_cases` は **全 pattern が未実行 (equal/diff/wasm_trap 無し) の関数に限り**、候補引数だけを `vm` blob の疑似オブジェクトにした case `fvm<arg>` を追加する。既存 pattern の case 生成は変えない (fvm は追加のみ)。既存 pattern の関数単位 verdict は全関数で不変だが、**case 単位の outcome は 7 関数で変化している** (下記・未検証)。
- 集計: `tests/fvm_transitions.py BASE.jsonl NEW.jsonl` が verdict 遷移と「既存 pattern が変わった関数」を出す。
- 実測 (m11 sample:800・`--shards 12 --state auto`・同一 worktree で base / 新を連続実行):
  - base (fvm 追加直前の親 `2f235a0a` の tree): match 360 / mismatch 230 / unexec 210 (1m42s, load 0.46→5.70)
  - 新 (`0596772f`): match 360 / mismatch 230 / unexec 210 (1m41s, load 1.27→ ※終了時 load は未採取)
  - 関数単位の遷移: match→match 360・mismatch→mismatch 230・unexec→unexec 210 (**遷移 0 件**)。
  - `fvm` case は 437 件走り、native_fault 193 / both_fault 243 / hang 1。**1 件も equal/diff/wasm_trap にならなかった**。
  - **測定 commit の注意**: §12 の vm0/u16 の「新 361」は `ecb45fee` 時点の測定で、本節の base (`2f235a0a`) とは commit が異なる。`2f235a0a` は `ecb45fee` 以降の main 取り込みを含む。361 と 360 の 1 件差は**未切り分け** (§6.2 で記録した 0x959a40 の run 依存が候補だが、本 PR では確認していない)。
  - **case 単位の outcome 変化 7 関数は未検証**: `tests/fvm_transitions.py` の `EXISTING_PATTERN_CHANGED` が 7 関数を出力したが、対象 VA・base/new の outcome・native 実行時間の raw jsonl を保存していないため、根拠を記録できない。「timeout の揺らぎ」は仮説であり、断定しない。検証として再実行 (`tests/fvm_transitions.py BASE.jsonl NEW.jsonl` で VA を出力) を子 issue に残す。
    本 PR で主張できるのは**関数単位 verdict の不変** (match→match 360 / mismatch→mismatch 230 / unexec→unexec 210) だけ。case 単位の outcome 不変は主張しない。
  - **base と新の測定 commit**: §12 の vm0/u16 の「新 361」(`ecb45fee`) を fvm の base として引用しない。fvm の比較は同一 worktree で連続実行した base (`2f235a0a`) と新 (`0596772f`) のみを使う。
- **原因 (未達の根拠)**: fvm の fault 位置 (rip 0x41a7xx・0xd2b1 等、または addr 0xb) は、this の VMT slot が 0 埋めのため仮想 call 先で落ちる。
  引数 this を正しく指しても、VMT の slot を解決しない限り native は仮想 call を完走できない。受入条件 (2) の「一致/不一致への遷移」は現設計では 0 件。
- **残り (子 issue へ)**: VMT slot に ret stub (または wasm 側で解決可能な関数) を置く設計。これは wasm 側の仮想 call 解決と整合させる必要がある。

**未達 (受入条件)**: 実行不能 2,261 (closure) の内訳の大半 (native fault / null deref) は今回の 2 pattern では解消しない。
UTF-16 blob は 1 pattern 1 本の固定で、長さや内容の変化を試していない。this/VMT は VMT の slot を埋めないため、仮想 call 先で native が落ちる。
「native 失敗 RVA からの引数補正」「署名未対応 (vector/struct) の扱い」「状態前提 (InitTable/TLS) の case 生成」は未着手。
flelift closure (fle_lift.sh 生成物 tools/flelift/work/lift/* が素材に無い) は未実測。
起票先: 本 issue #235 (部分達成のため Refs)。

### 12.1.1 LD-48 (#1398): VMT slot への仮 proc 番地配置 (部分達成)

- 実装 (review 1744 対応後): `rt/ld_core.h` の VMT 用仮 proc は静的 index 域 `LD_VMT_IDX0 (256)..263` (`?vmslot0..7`) に置く。`ld_nfakeproc` は増やさない (GetProcAddress 側の index 0..255 は不変)。`ld_fakeproc_valid` / `ld_fakeproc_name` が域を判定し、`fle_ldbridge.c` の `ott_dispatch` は両域を解決する。`ld_snapshot` 前の `ld_fakeproc_vmt_init` が番地式 `LD_FAKEPROC_BASE+i*SZ` の不一致を abort で検出する。仮 proc 上限超過も abort (旧: 0x50010000 を無言で返し proc 0 と衝突)。`ldlib/cases.py` `make_blob_vmt` は VMT slot k に `0x50010000+(256+k)*32` を書く (既存 `make_blob_vm` は 0 埋めのまま)。
- **根本原因 (修正前 `8ac5b169` の副作用)**: 既存 pattern `vm0` は `make_blob_vm` の blob を使うが、VMT slot に仮 proc 番地を書いたため `vm0` の入力そのものが変わっていた。index 域の分離 (`LD_VMT_IDX0`) だけでは `vm0` の変化は消えなかった。
- **修正 (commit `7d7259ec`)**: fvm 専用 blob `vmt` (`make_blob_vmt`) を新設し、VMT 仮 proc 番地は `vmt` にだけ置く。既存 `vm` blob (`make_blob_vm`) は元の 0 埋めに戻す。`fvm_line` は `blob=vmt`。`rt/ld_core.h` の index 域分離と abort 化は前 commit のまま。
- **測定 commit**: `7d7259ec` (コードを変えた最後の commit)。base = `origin/main` `025bdd8a`。
- **証跡** (差分 0): `git diff 7d7259ec HEAD -- tools/liftdiff ':!tools/liftdiff/REPORT*'` の出力は空。`REPORT*` を除外するのは、文書だけの commit を範囲から外すため。
- 検証: `liftdiff_e2e.sh --m11-only` (測定 commit `7d7259ec`) rc 0・`LIFTDIFF_E2E PASS`・2m57s (4 vCPU、load は未採取)。
- sample:800 (`--shards 12 --state auto`)。出所は「実装者」(本 PR の測定) と「reviewer」(PR review で別途実測) で分けて記す:

| run | match / mismatch / unexec | 関数単位の遷移 (base 比) |
|---|---|---|
| base `025bdd8a` 実装者 | 360 / 230 / 210 | - |
| base `025bdd8a` reviewer 1 回目 | 361 / 229 / 210 | - |
| base `025bdd8a` reviewer 2 回目 | 360 / 230 / 210 | - |
| `7d7259ec` 実装者 1 回目 | 360 / 233 / 207 | match→match 360・mismatch→mismatch 230・unexec→mismatch 3・unexec→unexec 207 |
| `7d7259ec` 実装者 2 回目 | 360 / 233 / 207 | 遷移の内訳は未記録 |
| `640fec3c` (=同コード) reviewer 1 回目 | 360 / 233 / 207 | 同上 (内訳は未記録) |
| `640fec3c` (=同コード) reviewer 2 回目 | 361 / 232 / 207 | 同上 (内訳は未記録) |

- **base 同士の揺らぎ**: base `025bdd8a` の 2 回で verdict が 1 件動く (reviewer 1 回目 361/229/210、2 回目 360/230/210)。`0x959a40` は base 1 回目で match、2 回目で mismatch。case 単位でも `0x5c14d0`・`0x43a3f0`・`0x959a40` などの outcome が base 同士で揺れる。この揺らぎは PR 由来ではない。
- **head と base の差の帰属**: head の mismatch は base より 3 件多い (232〜233 対 229〜230)。実装者測定の遷移では、この 3 件はすべて unexec→mismatch (`0x1024830`・`0x132f6a0`・`0x5c1030`) である。base の 2 回とも unexec、head の 2 回とも mismatch で、3 回とも安定している。fvm 新規 case の進捗であり、既存 pattern の回帰ではない。
- **判定**: 既存 pattern の件数は、base 同士の揺らぎ幅の内側に収まるかどうかで判断する。「増減 0」とは断言しない。case 単位の outcome は base 同士でも揺れるため、判定は「不能」(増減 0 の証明にはならない)。

- **既存 pattern の case 単位の変化 (実装者測定・base 比)**: `7d7259ec` の 1 回目で hang 系 6 件 (`z` hang→both_fault 2・`p0` native_fault→hang 1 ほか)、2 回目で 5 関数 (`p0` native_fault→hang 1・`p1` hang→both_fault 1・`z` hang→both_fault 2・`u16` hang→both_fault 1・`pall` both_fault→hang 1)。同一 commit 内でも run ごとに揺れる。
- **`vm0` の case 単位 (reviewer 実測)**: head の 2 回のうち、`0x5c14d0` が both_fault→native_fault になった (1 回目・2 回目とも)。`0x43a3f0` は diff→wasm_trap (1 回目)、`0x5c5500` は hang→both_fault (2 回目)。同種の変化は base 同士でも出るため (`0x5c14d0`・`0x43a3f0` が base 1 回目と 2 回目で異なる)、`vm0` の変化 0 とは書けない。判定は上の「判定」に従う。
  case 単位の hang 揺らぎを 0 にすることは、この PR では達成していない (既存の性質で、本 PR の変更とは切り分けていない)。
- **fvm の件数 (`7d7259ec` 1 回目)**: 437 件 = native_fault 189 / both_fault 245 / diff 3。**equal / wasm_trap は 0 件**。受入条件 (2) (fvm の equal/diff/wasm_trap 化) は部分達成 (diff 3 件のみ)。diff 3 件 (`0x1024830`・`0x132f6a0`・`0x5c1030`, arg 0) は、関数 verdict が unexec→mismatch に変わった 3 関数と一致する。diff の中身 (`native_extra_call` 等) はこの PR では未切り分け。native は `rip=0xb` で segv し、VMT slot の仮 proc まで到達していない (引数値を関数ポインタとして呼ぶ経路)。

### LD-24 (#976) 署名未対応 50 関数の内訳 (REPORT §12 から移動)

m11 closure の `unsupported_sig` 50 件は未実装。分割先は #1193 と #1194。詳細・件数の注記・受入条件: [`REPORT_LD24.md`](REPORT_LD24.md)。

## 13. flelift closure の再採点 (LD-26 / #978、部分達成) — 参考値 (未確定)

素材 (fl-win64・work-m11・work-liftdiff) から `tools/flelift/fle_lift.sh` で lift 生成物 (`tools/flelift/work/lift/*`) を作り直し、`targets/flelift.json` で全数採点した。方式は「fl-win64 からの再生成」(allowlist 追加なし)。issue は方式を PM 判断としているため、この選択は PM の確認対象。

| 工程 | 実測 (本 run・4 core・load 約 0.8) |
|---|---|
| `fle_lift.sh` (x64c lift → emcc) | 合計 **67.2 s** (lift 36 s・emcc 31 s)。functions 7018 / insns 340,761 / unsup {} / imports 354 |
| `liftdiff.py build targets/flelift.json` | **29.0 s**。`sig_mismatch` 0・`undefined` 0 |
| `bootstate --mode hybrid` | **10.9 s**。units_run **928/942** (InitCount 246 で segv・first_fail 830) |
| `batch --set closure --shards 4` 前半 (5600 関数) | 1500 s の foreground timeout で打ち切り (rc 124)。JSONL は 400 件ごとに書出済み |
| 同 後半 (残 1821 関数, `--set file:`) | **653 s** (10 m 53 s)・rc 0 |

> **未検証 (レビュー指摘 1・最重要)**: 前半 JSONL の行数・一意アドレス数は本 run で**確認していない** (打切り後の前半 JSONL が 5,600 件あったことを示す記録が無い)。後半 1,821 件は `--set file:` で別途流した。このため下表の「7,421 関数」は前半の欠損を含む可能性があり、**全数 7,421 の値として扱わない**。前半 JSONL の一意数を確認するか、欠けた関数を再実行して一意数を揃えるまで、下表は参考値。
>
> **測定 tree (レビュー指摘 1・3)**: この値は commit 1795f8ff の tree (base a5adb2fc 系) のもので、現 HEAD (7242709f = main 取り込み merge) の値ではない。`git diff 1795f8ff 7242709f --stat -- tools/liftlib/liftlib tools/liftdiff/ldlib` は 5 files, +174 / -1 (`passes/l1_restore.py` +79・`passes/iargs.py` +19/-1・`passes/fp_bind.py` +13・`ldlib/session.py` +35・`ldlib/cases.py` +29)。この差分の上に載せた値は**未検証**。再測定 (fle_lift.sh / liftdiff build / bootstate / batch) は素材不足で本 run では不可。

参考値 (未確定・前後半の合算・前半 JSONL の一意数未確認・重複確認なし。全数 7,421 として扱わない):

| verdict | 件数 |
|---|---|
| match (一致) | 4,280 |
| mismatch (不一致) | 805 |
| unexec (実行不能) | 2,336 |

実行不能の内訳: native_fault 1,183 / native_null_deref 460 / no_wasm_definition 402 / hang 241 / unsupported_sig 50。

§12 までの値 (17 unit の旧 boot、CAB-232 相当) との遷移: unexec→match 240 / match→mismatch 220 / unexec→mismatch 167 / mismatch→match 142 / mismatch→unexec 73 / match→unexec 25。
(比較元 `results/flelift_closure_verdicts.tsv` は旧 boot 4,143 / 633 / 2,645。)

**REPORT §1 (928 unit 到達状態の値 4,182 / 741 / 2,498) との不一致**: 本 run は 4,280 / 805 / 2,336 で、
差は +98 / +64 / −162。§6.2 が示す負荷依存の揺らぎ (native badjson 等) の範囲を超える。原因は未切り分けで、
候補は shards 4 (REPORT は 14)・前後半の 2 プロセス分割・native 側の状態 (`--state auto`)。
「本 run の値が正」とは扱わず、再現性の確認を未解決として残す。

未達 (受入条件):
- `FL_WIN64_DIR=... bash tools/liftdiff/liftdiff_e2e.sh` の PASS は **未実行**。既定の [1/4] が `work-m6-ott` (ott.ll) を要するため、
  `--m11-only` の確認も本 run の時間内では行えなかった。起票先: 本 issue #978 (部分達成のため Refs)。
- 48 分の run 内で全数採点を完了したが、shards 数と再現性の差は上記のとおり未解決。
- 素材の実在確認 (レビュー非ブロッカー): `ARTIFACTS_DIR` (`/home/runner/artifacts`) には `fl-win64.tar.zst` のみ。`work-m6-ott` は無い。
  本 run の再実行 (前半 batch・lift 再生成) に必要な `work-m11`・`work-liftdiff` も無く、`tools/liftdiff/work`・`tools/flelift/work` は存在しない。
  このため前半の再実行・一意数確認は本 run では不可能。
