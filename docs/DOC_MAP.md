# DOC_MAP — 全 `tools/**/REPORT.md` の索引

全 `REPORT.md`・主要ドキュメントの索引。**何がどこに書かれているか**の一覧。
行数は 2026-10-12 時点の概数。

- **測定値の正本・各ファイルの「書いてはいけないもの」の割り当ては §4 が正本** (本書のそこだけで定める)。
- 衝突時: 同じ対象の数値が複数ファイルにあったら、**より新しい検証起点の REPORT** を正本とし、
  他方は「結論 1 行 + リンク」に縮める。

---

## 1. 行数上限ルール

| 種別 | 上限 | 超過時の扱い |
|---|---|---|
| `REPORT.md` (日本語) | **250 行** | 超過分は付録 `.md` (例 `REPORT_APPENDIX.md`) または `results/` に分割。**内容は削除しない。Git 履歴に残るように分割移動する** |
| `README.md` / 設計文書 (`PROTOCOL`・`FORMAT`・`ABI`・`MANIFEST` 等) | 300 行 | 分割または `/docs` 同種文書への統合を検討 |
| 自動生成 (`results/TABLES.md`・`IMPORTS.md`・`inventory.md`・`PLUGIN_MATRIX.md` 等) | 上限なし | 先頭 1 行に `自動生成: <cmd>` を必須化。**人手編集禁止** |
| `BACKLOG.md`・未解決一覧 | 300 行 | 解決済み項目は削除してよい |

超過ファイルには先頭にナビゲーション注記を入れる:

```markdown
> **正本**: `tools/xxx/REPORT.md`。詳細は §n / 付録 `tools/xxx/REPORT_APPENDIX.md`。
```

## 2. 自動生成ドキュメント一覧

| ファイル | 生成元 |
|---|---|
| `tools/perf/results/TABLES.md` | `tools/perf` の計測 driver |
| `tools/perf/results/compress.md` | 同上 |
| `tools/perf/p8/results/TABLES.md` | `tools/perf/p8/tables.mjs` (入力 `results/p8.jsonl`) |
| `tools/icall/disp_size/results/TABLES.md` | disp_size 監査 driver |
| `tools/icall/disp_size/results/consumers.md` | 同上 |
| `tools/liftdiff/results/*.md` | `liftdiff` 採点名 driver |
| `tools/m11/shimx_link/results/*.md` | `shimx_link` 計測 |
| `tools/gui/IMPORTS.md` | import 抽出 driver |
| `tools/gui/integ/INTEGRATION_XCHECK.md` | 突合 driver |
| `tools/assets/PACKAGE_STATS.md` | pack 統計 |
| `tools/assets/bootset/BOOTSET.md` | bootset tier 推定 driver |
| `tools/m2/delphi_inventory.md` | `delphi_inventory.py` |
| `tools/m2/SHIM_INVENTORY.md` | shim 照合 |
| `tools/shim/inventory.md`・`tools/shimx/inventory.md`・`tools/audio/INVENTORY.md` | 各照合 |
| `tools/shared/data/ipp_inventory.md` | IPP 実測 |
| `tools/plugins/PLUGIN_MATRIX.md` | plugin-matrix driver |
| `docs/LEGAL_TERMS_LEDGER.md` | `pnpm terms-watch` (正本は同 `.json`) |
| `tools/startup/license_obs/results/{FLAG_SITES,CASES}.md` | `scan_consumers.py`・`run_cases.py` (license_obs) |
| `tools/python/analysis/{flapi/FLAPI,mcp/MCP_TOOLS}.md` | 抽出 driver (repo 内 `tools/python/analysis/`) |

## 3. REPORT.md 索引

`tools/misc/` は `loader_smoke.mjs` のみでドキュメントが無いため**索引対象外**。

### 全体・デプロイ

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `deploy/REPORT.md` | ~120 | deploy/ を Workers Static Assets 構成へ改修した実測レポート |
| `deploy/README.md` | ~100 | デプロイ構成 (案 S) の正本・stage/deploy/access/verify 各 script |
| `deploy/RUNBOOK.md` | ~50 | 実デプロイの具体手順と確認項目 |
| `deploy/EDGE-SIM.md` | ~30 | edge-sim の調整一覧 |
| `tools/e2e/REPORT.md` | ~120 | ブラウザ E2E ハーネスと配信構成の実測 |
| `tools/hosting/REPORT.md` | ~135 | 既定ホスト名だけで COOP/COEP を成立させる配信構成 (案 S の根拠) |
| `tools/legal/REPORT.md` | ~216 | LGL-6 (#89) / LGL-10 (#2498): Massive X の同梱 EULA (実測: 同梱なし。Inno Setup 6.4.2 形式・CRC 不一致の記録・再確認と `.dmg` の件数)・Fresh Air の同梱 EULA (ファイル名判定と User Guide PDF 本文の検索で無し・件数の定義)・Xfer 公式規約ページの取得結果・公開 FAQ hub の取得結果。LEGAL.md §7 の実測値の正本 |
| `tools/legal/release-guard/REPORT.md` | ~75 | release guard (LGL-2): 公開前に dist を走査し FL/プラグイン由来バイト列を検出して失敗させる deny-list ゲート |
| `tools/legal/terms-watch/REPORT.md` | ~145 | terms-watch (LGL-5): 各社 EULA/ToU の取得 (Xfer は NSIS インストーラのヘッダから)・正規化ハッシュ比較・台帳更新・差分時非ゼロ終了 |
| `tools/legal/notices/REPORT.md` | ~110 | THIRD_PARTY_NOTICES 自動生成 (LGL-3): OSS 再ビルド記録 (upstream 版・configure 引数・パッチ) + FL 同梱表記 15 本 + フォント一覧から NOTICES を生成し、記録なしの同梱 OSS を CI/stage ゲートで検出 |
| `tools/perf/REPORT.md` | ~150 | wasm 実時間性能・compile 時間・巨大 wasm 実験 |
| `tools/perf/REPORT_APPENDIX.md` | ~85 | perf REPORT §12 全文 (PERF-P9 #168: bit-exact OTT の RTF を node / Chrome Worker / 実 AudioWorklet / native 実機械語で再測) |
| `tools/perf/PERF.md` | ~150 | 性能の設計メモ (bit-exact 版の実測は `tools/perf/REPORT.md` §2.1・完走路の正本は `tools/ott/REPORT.md`) |
| `tools/perf/REPORT_P15.md` | ~180 | PERF-P15 (#990): 実 OTT の Chrome Memory 本数上限 (124〜125) に対する instance 数の設計。1 Memory に plugin 処理オブジェクトを畳み込む方式 (a) を採り、M=130 を 1 instance で駆動 (署名 130/130 一致)。AudioWorklet 上の M=130 駆動を §7 で実測 (#1259)。異なる plugin の同居は #2963 [PERF-P20] |
| `tools/perf/REPORT_P8.md` | ~189 | PERF-P8 (#166): plugin 別 module/instance/memory vs MAIN/SIDE_MODULE 動的リンクの合成カーネル比較 (node + Chrome 154 Worker)。`tools/perf/REPORT.md` §5 項目 7 から参照 |
| `tools/perf/REPORT_P7.md` | ~60 | PERF-P7 (#165, 部分達成): Chrome headless/headful(Xvfb)/Firefox 157 の compile・上限・code cache・AudioWorklet 駆動の実測 + 実機未測の起票依頼 |

### 解析・lift 基盤

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/m2/REPORT.md` | ~230 | M2: function boundary 合意 / Delphi lift 品質 / shim inventory / wasm PoC |
| `tools/m3/REPORT.md` | ~100 | M3: 中規模 lift → wasm (純計算 4 関数 bit-exact) |
| `tools/m5/REPORT.md` | ~120 | M5: Delphi lift → wasm E2E + native bit-exact |
| `tools/liftlib/REPORT.md` | ~221 | 共通 lift 修復基盤の統合 (CAB-49/54/55/220/239/LIFTLIB-2)。§21 は DIR64 補正境界の全数列挙と修正 (#593)。§10〜§12 は `REPORT_APPENDIX_A.md`・§13〜§16 は `REPORT_APPENDIX_B.md`・§17 (iargs)・§18 (#241 ymm/pcmpistri/F2 xmm 戻り) は `REPORT_APPENDIX.md`・§19 (PERF-P1 #155 標準ビルド設定 + 署名ガード)・§20 (#478 ott_auto_none) は `REPORT_APPENDIX_C.md` に分割。§22 (LIFTLIB-9 #668) は要約のみで全文は `REPORT_APPENDIX_D.md` |
| `tools/liftlib/REPORT_APPENDIX_A.md` | ~240 | liftlib §10〜§12 全文 (lowbase 取り込み CAB-220 / mini-lifter 語彙 + leaf spec CAB-239 / LIFTLIB-2 CAB-256) |
| `tools/liftlib/REPORT_APPENDIX_B.md` | ~250 | liftlib §13〜§16 全文 (LIFTLIB-3 CAB-264 / LIFTLIB-4 CAB-272 / LIFTLIB-1 #224 検収 / 環境パス置換 #386) |
| `tools/liftlib/REPORT_APPENDIX.md` | ~266 | liftlib §17 全文 (HB-H3 #93 iargs pass)・§18 全文 (LIFTLIB #241 ymm(i256) helper ABI / pcmpistri / F2 xmm 戻り搬送) |
| `tools/liftlib/REPORT_APPENDIX_448.md` | ~60 | liftlib CI-8 (#448) の付録: work-* 絶対 symlink の張り直し実測、素材 `libottnative.so` が HEAD と不整合で `lowbase_e2e.sh` [3] が FAIL した件と、[3] で `build.sh` から再生成する修正 (2f1b76fc) の実測。測定値の正本。本文は REPORT §24 |
| `tools/liftlib/REPORT_APPENDIX_898.md` | ~35 | liftlib #898 (HB-H22) iargs 未対応 3 site の bind の付録 (REPORT_APPENDIX §17 の #898 節を分割移動)。`movzx` 合成 (1801a3117 解決)、残り 2 site は main の HB-H25 #1158 で bind 済み。高バイト unbound (T16b)。測定値は REPORT_APPENDIX_898.md が正本 |
| `tools/liftlib/REPORT_APPENDIX_2128.md` | ~60 | liftlib #2128 (部分達成): ott_getparam leaf への icall runtime 配線の実測 (測定 commit `f8bd2ea0`・変更前 `df2eebde` との比較・unit T1〜T5・未解決の起票先)。測定値の正本 |
| `tools/liftlib/REPORT_APPENDIX_2181.md` | ~89 | liftlib #2181 (HB-H45, 部分達成): ott_getparam F=281 の SSA dominance 欠陥 (iargs の支配しない bind) の修復と emcc 成功の実測 (測定 commit `b1c2d148`・変更前後の比較・ネガティブコントロールの未達・子 #2859/#2861)。測定値の正本 |
| `tools/liftlib/REPORT_APPENDIX_883.md` | ~213 | liftlib #883 (HB-H21) ott_getparam の BLK 配線と this 仮引数化の付録 (REPORT_APPENDIX §17.9・§17.10 の追跡)。測定値は REPORT_APPENDIX.md §17.9 が正本。未解決は #883 に残す。#1583 (HB-H33) の受入判定と実測 (§「#1583 の受入判定と実測」) を含む。route 側の張り替えは #2865 |
| `tools/liftlib/REPORT_APPENDIX_C.md` | ~95 | liftlib §19 全文 (PERF-P1 #155 標準ビルド設定 + 出力 bit 署名ガード + fail-open 封じ込め)・§20 (LIFTLIB-7 #478 ott_auto_none fail-closed + census 再計算) |
| `tools/liftlib/REPORT_APPENDIX_2094.md` | ~90 | liftlib #2094 (movntps 変更 #1581 の回帰測定): `--quick` の変更前 (`0d9b5385`)・単独 (`2e2f1dfe`)・HEAD (`26f90ada`) の実測、#1664 (`52ad0ce1`) で ott --auto none が FAIL する切り分け、OTT の movntps 変更前後の store / call 件数。測定値の正本 |
| `tools/liftlib/REPORT_APPENDIX_2863.md` | ~89 | liftlib #2863 (親 #2094): p1_legacy の一時名 `%pc<行 index>` が #1664 の空行除去で変わり IR 一致ゲートが FAIL した原因 (名前のみ・分岐は不変) と、`ott.same` の全単射な改名正規化 (T26)。`--quick` は `dce097af` で ALL PASS (FA/KH/T6 を含む)。測定値の正本 |
| `tools/liftlib/REPORT_APPENDIX_1560.md` | ~50 | liftlib CI-28 (#1560) の決定: raw `drc.ll` は比較に使わず正規化後 `base.ll` で判定 (b)。k80 の再実測 (base 4/4 一致・raw 2 種)。`REPORT_APPENDIX_D.md` は 250 行上限のため別置き |
| `tools/liftlib/REPORT_APPENDIX_D.md` | ~214 | liftlib §22 全文 (LIFTLIB-9 #668: RetDec raw lift 出力の非決定性 = uselistorder・ASLR 依存、A7 後は決定的、回帰 gate `lift_determinism_e2e.sh`)。§23 (LIFTLIB-10/11 #695・#887: k80 の alloca 並び = `canon_alloca_order` で決定化、gate 組込み)。本体 §22 は要約のみ |
| `tools/flelift/REPORT.md` | ~155 | x64c を FLEngine 向けに汎用化 |
| `tools/flelift/boot/REPORT.md` | ~350 | FLE-2〜FLE-5: x64c lift による FLEngine boot 連鎖 |
| `tools/flelift/boot/REPORT_APPENDIX_2700.md` | ~40 | FLE-8 (#2698) の詳細 (REPORT §9 から移動: E-1 工程の実測・E-2 検証)。FLE-9 の shard 化の実測は REPORT §9 |
| `tools/qfclift/REPORT.md` | ~100 | T-SH-12 (#154 部分達成): QuickFontCache_x64.dll の x64c lift (6,347 関数・unsup 0) + SSSE3 handler 注入 (pshufb/pmulhrsw/phaddw) + native-vs-wasm の SSSE3 spot diff。ILTools は `tools/iltools/REPORT.md` 参照。FruityPlug は未着手 |
| `tools/iltools/REPORT.md` | ~36 | T-SH-12 (#154): ILTools_x64.dll の x64c lift 測定 (11,747 関数・unsup 1,236 は全て x87 → 未達)。x87 命令一式が x64c 未対応 |
| `tools/fruityplug/REPORT.md` | ~60 | T-SH-12 (#154): SGv2 の win 対応の検証。classify.py の block24353 (FruityPlug_x64.dll 名) は VERSIONINFO で Maximus と判明し SGv2 の根拠にならない。export 名は 133 本で非一意。mac 素材との突合は未達 |
| `tools/liftdiff/REPORT.md` | ~250 | flelift (x64c) 全数採点 + native 全起動の参照化 (§5/§6.1/§6.2 は `REPORT_APPENDIX.md` に分割)。§12 (被覆拡大 vm0/u16) は要約のみで全文は `REPORT_APPENDIX.md` §12 |
| `tools/liftdiff/REPORT_APPENDIX.md` | ~385 | liftdiff REPORT の分割移動節の全文: §5/§5.1/§5.2 (回帰 A/B・Ablation)・§6.1/§6.2 (検収・再現性)・§8/§9 (wasm_trap)・§10 (OTT 旧 chain)・§11 (比較系偽陽性)・§12 (被覆拡大 vm0/u16)。250 行上限のため無変更で分割移動 |
| `tools/liftdiff/REPORT_APPENDIX_LD27.md` | ~70 | liftdiff LD-27 (#1034) の型 B 候補 34 件の完全 trace 再検証: 類型 X (xmm0 入力の脱落)・M (MXCSR 戻り値 0)・R (未特定) の分析、0x40a3d0 の rax の導出、再現手順。件数の正本は `results/m11_typeb_cause.md` の集計行。本体 §9 は参照 1 行 |
| `tools/liftdiff/REPORT_APPENDIX_LD44.md` | ~75 | LD-44 (#1313): OTT 旧 chain の `1801c67a0` の再確認 (他 7 関数は未実施)、m11 sample:800 の e2e 条件 3 回の再測定 (測定 commit `be017fb1`・件数 360/230/210 で一致・verdict 変化 0) と `92a145a5` 比較、`m8_fail` の発火経路の仮説。命令単位 trace は子 issue (LD-57) |
| `tools/liftdiff/REPORT_APPENDIX_LD16.md` | ~172 | liftdiff REPORT §10 (OTT 旧 chain 前回比) の全文と、§7 (LD-32 / #1070: 8 関数のパターン別観測・m11 sample:800 の n=3)・§8 (LD-32 追補: m11 sample:800 の case outcome 揺れ 3 関数 = `tests/ld32_verdict_cmp.py` の tsv、8 関数の entry・call 単位 trace。命令単位は #1313)。集計差分 (38→35 main・HEAD。うち cases.py で 38→40) の原因切り分け・前回比の基準 (同一 HEAD で n=3 採点・PM 判断 #1069)・n=3 非決定性。関数単位の突合は `tools/liftdiff/tests/ott_delta.py` (LD-16 / #825) |
| `tools/liftdiff/REPORT_WIN7_2718.md` | ~60 | WIN-7 (#2718) 参照実行 spike: hybrid の到達状態の native で `CreateFruityInstance` を 1 回呼ぶ実測 (import 列・S19 到達・その後の未同定の段で null 読みの segv・KPI 前後)。手順は `spike_cfi.py` |
| `tools/liftdiff/REPORT_APPENDIX_LD25.md` | ~80 | liftdiff REPORT §12 末尾の LD-25 行 (InitUnits の空振り一致・InitTable 充足の boot 状態) の全文: 機械語で確定した原因・units/hybrid の precondition 実測・sample:800 の判定遷移。検査は `tools/liftdiff/tests/check_initunits.py` (LD-25 / #977) |
| `tools/liftdiff/REPORT_APPENDIX_LD42.md` | ~50 | liftdiff LD-42 (#1248) の実測: units/hybrid の sample:800 判定遷移 (関数単位の突合は `tests/ld42_transition.py`)、TLS precondition、既定 batch を units に据え置く判断 (保留・子 #1464 で判断)。方式決定は DECISIONS D13 |
| `tools/liftdiff/REPORT_APPENDIX_LD40.md` | ~34 | liftdiff LD-40 (#1199) の既存コード確認 (native `ld_fake_ptr` の thunk・wasm `ott_dispatch` 捕捉・fvm VMT 0 埋め)、未達理由 (1 run の上限内で完結せず)、子 issue #1398 (LD-48) への分割 |
| `tools/liftdiff/REPORT_APPENDIX_865.md` | ~20 | liftdiff LD-18 (#865) 新規節: trace_head 外 27 件の 414ad0 到達確認 (26/27)・OOB 最上位 frame 集計 (239 件、件数定義と 222 件との差)。`REPORT_APPENDIX.md` は 250 行上限のため増やさず別置き |
| `tools/liftdiff/REPORT_APPENDIX_LD28.md` | ~26 | liftdiff LD-28 (#1035) の型 C・D 原因候補 (P1〜P3)・0x417b70 の idiv/udiv 仮説の節全文 (REPORT_APPENDIX §9 から分割移動)。測定 commit・鮮度の証跡・数値例 (count = 1 の反例を含む) |
| `tools/liftdiff/REPORT_APPENDIX_LD62.md` | ~50 | liftdiff LD-62 (#1767) の実測: 0x417b70 の除算 trap 入力 8 件 (native 全件 segv・U1〜U4 未解決) と、予測式の境界値 (旧 float 除算 vs 整数除算、96 件) の計算。生成物は `results/m11_417b70_trap_inputs.md`・`results/m11_417b70_div_boundary.md` |
| `tools/liftdiff/REPORT_APPENDIX_LD96.md` | ~168 | liftdiff LD-96 (#2258): sample:800 shard 1 の件数揺れの切り分け (部分達成)。高水位外の heap 残存の計測は §8 (測定値は `results/ld96_heap_residue*.tsv`)。未解明の残作業は #2258 |
| `tools/liftdiff/REPORT_APPENDIX_LD122.md` | ~104 | liftdiff LD-122 (#2682): 0x959a40 の全体 run 限定 diff の出所 (同 runner で先行する 0x50abe0 の case 列の切り分け)。切り分け表は `results/ld122_959a40_origin.tsv` (driver `ld122_origin.py`)。機構は #2723 へ移管。要否・揺れの残件は PM agent の判断待ち (§5) |
| `tools/liftdiff/REPORT_APPENDIX_LD121.md` | ~84 | liftdiff LD-121 (#2681): shard 1 の 19 関数の揺れの原因分類。runner 作り直し実験で、揺れは wasm 側の持ち越し (18 関数) と両側の持ち越し (`0x5d19e0`) と分類。高水位外の heap 残存は単独原因でない。測定値は `results/ld121_restart_probe.tsv`。driver は `tools/liftdiff/ld121_restart_probe.py`。残りは #2723 |
| `tools/liftdiff/REPORT_APPENDIX_LD68.md` | ~90 | liftdiff LD-68 (#1907): 計装版 block trace の既定 build 比較 (12 case 差 0・測定時の記録)、1801c5e84 vm0 の wasm block 列、native `1c0b6f`・`1c0b82` の並び。IR 由来の対応 (`ott.ll` 依存) は本 run で未検証。命令単位 trace は子 #2192 (LD-83)、残り 5 関数は #2193 (LD-84) |
| `tools/liftdiff/REPORT_APPENDIX_LD83.md` | ~104 | liftdiff LD-83 (#2192): wasm 側の site trace (block 内の conditional br・import call の直前の記録)。既定 build と 12 case 差 0。native `1c0b6f`・`1c0b82` は site 単位で対応 (vm0 は native の je 成立と一致)。命令単位の完全 trace は #2801 (LD-131)。shim の block_ok の範囲外 trap は #2802 (LD-132) で main 解消済み |
| `tools/liftdiff/REPORT_APPENDIX_LD84.md` | ~110 | liftdiff LD-84 (#2193): 残り 5 関数 (1801ab1d0・1ab258・1c621c・1c682c・1c69cc) の native 実行トレースと wasm 計装 block 列の対応表 (入口単位の一致と最初の分岐)。分岐の原因は HeapFree import 応答の契約差 (ld_core.h と shim heap.c)。LD-57 の vm0 早期 return 記述の訂正を含む。対応表の TSV は `results/ld84/` |
| `tools/liftdiff/REPORT_APPENDIX_LD67.md` | ~70 | liftdiff LD-67 (#1906): ld_blk 計装が OTT 旧 chain の vm0 戻り値を変える件の切り分けと修正。12 case の既定 build との比較 (LD-64 の baseline) |
| `tools/liftdiff/REPORT_APPENDIX_LD41.md` | ~20 | liftdiff LD-41 (#1238) の新規追記: 0x417b70 の機械語 (idiv 符号付き) と IR (udiv 符号なし) の静的対応。LD-28 付録の 0x417b70 節の補足 (件数は results 参照)。動的確認は #1576 |
| `tools/liftdiff/REPORT_LD24.md` | ~70 | liftdiff LD-24 (#976) 節: m11 closure `unsupported_sig` 50 件の内訳と #1193 / #1194 への分割 (署名内訳は IR 未照合)。REPORT.md §12 から参照 |
| `tools/liftdiff/tests/ld24_sig_breakdown.py` | ~110 | LD-24 (#976) の署名内訳スクリプト: `unsupported_sig` 50 行の va/name を IR (`boot_final3.ll`) の define/declare 行から引き、署名形ごとの件数と #1193/#1194 振り分けを出力 (IR 必須・IR 無しは終了コード 1) |
| `tools/liftdiff/REPORT_LD39.md` | ~75 | liftdiff LD-39 (#1194) 節 (途中報告): i128 / %tagPOINT の 11 関数の振り分けと機械語入口の実測。i128 の渡し方は 2 候補とも未決。case 生成・runner は未実装 |
| `tools/liftdiff/REPORT_APPENDIX_LD53.md` | ~120 | liftdiff LD-53 (#1546) 節: i128 引数の呼出し側全件 (命令境界の線形走査) と呼び先の判定。(a)/(b) は 691dd0 を含め棄却 (§7)。IR 型誤りの修正は #1479 (§7.4) |
| `tools/liftdiff/tests/ld39_abi_dump.py` | ~80 | LD-39 (#1194) の ABI 入口ダンプ: 11 関数の PE 先頭命令列を capstone で並べ、jmp thunk の IAT 先を解決する。ABI は断定せず、判定は REPORT_LD39.md で人が行う |
| `tools/icall/REPORT.md` | ~245 | 間接 call/jmp 落ち監査 + 復元 pass。§10.1 (#530)・§11 (ICALL-6 #361)・§12 (ICALL-16 #1023) は要約のみで全文は `REPORT_APPENDIX.md` §14 に分割。§13 (#1026 Fresh Air 残落ち 6 件) は結論 1 行のみで全文は `REPORT_APPENDIX_1067.md` §13 |
| `tools/icall/REPORT_APPENDIX.md` | 242 | icall REPORT §10.1 (#530 OTT 回帰再実行)・§11 (ICALL-6 #361)・§12 (#229 FLEngine 分割 lift・§12.1 ICALL-9 #847)・§14 (ICALL-16 #1023 stack 引数の実測。REPORT §12 から分割移動)・§15 (#851 の結論 1 行)・§16 (#852 FLEngine jump table) の全文 (250 行上限のため分割移動) |
| `tools/icall/REPORT_APPENDIX_1014.md` | 104 | icall #1014 (ICALL-15): FLEngine 2 関数の落ち 366 site のブロック単位 before / after 分類 (全て消失・別関数への移動 0)。stub を含むブロックは SCCP で stub を失い、Jump Threading で消える。受入条件 3 (修正と kept 実測) は未達で #1014 に継続。測定値の正本 (段ごとの stub 数は `REPORT_APPENDIX.md` §12.1 が正本) |
| `tools/icall/REPORT_APPENDIX_2083.md` | ~47 | icall #2083 (ICALL-58): crash 残り 3 件の切り分け。`0x1803b3fc0`・`0x1803b5b60` は未実装 import `KERNEL32!RtlPcToFileHeader` (idx 64) の thunk 由来の stack 不整列、`0x1803b9ff0` は `rcx=0xa0001440` 書込みで落ちる切り分けのみ (原因未確定)。idx 64 の確認は `tools/icall/diff/fa_import_names.py` (要 `plugins-freshair`) |
| `tools/icall/REPORT_APPENDIX_1025.md` | ~229 | icall #1025 (ICALL-17): Kilohearts Gain icall 経路の wasm 化と build・実行段の切り分け (REPORT §15 の全文)。差分ゼロの節は `REPORT_APPENDIX_1025_FIX.md`。 |
| `tools/icall/REPORT_APPENDIX_1025_FIX.md` | ~64 | icall #1025: runner が `_ott_data_install()` を呼んでいなかった原因の修正と、wasm/native の bit 一致 (61 シナリオ / 366 step・差分 0)。REPORT §15 から参照。 |
| `tools/icall/REPORT_APPENDIX_2009.md` | ~61 | icall #2009 (ICALL-55): wasm 側 encoded slot 初期化 (`FA_ENC_INIT=1`) の試行と、crash 残り 3 件の切り分け (未達。受入条件 1・2・3 は未達で #2083 へ) |
| `tools/icall/REPORT_APPENDIX_2120.md` | ~70 | icall #2120 (ICALL-59): SlateCore encoded slot の実行時トレース (closure 131 関数の zero-fill 読出し VA 7 個・既知 12 slot のうち 3 件)。53 関数の SIGSEGV と `0x1810806a0` の因果は推定 (未実測)。表の境界・entry 数・OTT 比較は #2148 (ICALL-60) へ移管 |
| `tools/icall/REPORT_APPENDIX_2148.md` | ~80 | icall #2148 (ICALL-60): `0x1810806a0` を迂回した再トレースと読出し VA の追加採取 (部分)。`0x1307100`・`0x13071a0` 起点の 2 系統テーブルを読むディスパッチャ `0x18105de80` の確認。表の境界・entry 数・OTT 比較は子 #2197 (ICALL-62) へ移管 |
| `tools/icall/REPORT_APPENDIX_2197.md` | ~70 | icall #2197 (ICALL-62): T1 `0x181307100`・T2 `0x1813071a0` の index 域と既知 12 slot の判定 (12 中 7 件が T1/T2 内、5 件は起点未満)。表の終点・OTT 比較は未達 (子 issue へ移管) |
| `tools/icall/REPORT_APPENDIX_2170.md` | ~84 | icall #2170 (ICALL-61): `slot_trace.sh` の fatal RIP 採取 (`work/slot_trace_fatal.txt`)、fatal RIP の群別集計 (baseline 53 件・stub 47 件)、table 2 本 (`0x181307100`・`0x1813071a0`) の静的参照範囲。受入条件 3 のみ部分達成。表の終点・既知 12 slot 判定・OTT 比較は #2197 (ICALL-62)、fatal RIP 原因は #2198 (ICALL-63) へ移管 |
| `tools/icall/REPORT_APPENDIX_2198.md` | ~90 | icall #2198 (ICALL-63): fatal RIP の群 (9 種)・rc 内訳と既知 12 の 3/12・4/12 の実測、fatal 経路の ACC 計上漏れの修正 (`c2f52068`・`slot_trace.c`)。`0x..96f` 形 9 件は harness の `missing_import` (`slot_trace+0x296f`)。群 B〜H の引数由来・群 C の因果は #2231 (ICALL-67) へ移管 |
| `tools/icall/REPORT_APPENDIX_2225.md` | ~245 | icall #2225 (ICALL-65): SlateCore 符号化表と OTT api-set 表 `0x18026c9f0` の形式比較。cookie・decode 式・zero-fill 配置・entry 数 (T1 20・T2 34) が両 PE で一致。OTT の `APISET_N` 32 は 2 entry 不足、既知 12 slot は T1/T2 の外。CRT の初期化ループから終点を静的確定 (`tools/icall/diff/dispatcher_ids.py`)。OTT の PE 直読みは `ott_apiset_cmp.py`。動的な最大 index は #2226 |
| `tools/icall/REPORT_APPENDIX_2226.md` | ~110 | icall #2226 (ICALL-66): T1 `0x181307100`〜`0x1813071a0` (20 entry)・T2 `0x1813071a0`〜`0x1813072b0` (34 entry) の境界の再確認。動的に読まれた最大 index は既定条件で T2 6 (静的上限 33 との差 27・下限)、T1 0 件。stub・T2 初期化 (`SLOT_T2_INIT`) でも T2 の最大は 6。dispatcher の decode 0 で T1 を読む経路 (機械語で確認)。測定値の正本 |
| `tools/icall/REPORT_APPENDIX_2231.md` | ~113 | icall #2231 (ICALL-67): fatal RIP 群 B/C/D/E/G/H の引数由来 (D・G は heap 引数の直接使用、B・E・H は未追跡)、群 C の `SLOT_ENC_INIT` 因果、群 I の整列違反 (thunk 呼出し元の `rsp` 不整列)。`slot_trace.sh` の fatal 抽出に `regs`/`heap_args` を含める修正。測定 commit と差分 0 の証跡を §5 に記載 |
| `tools/icall/REPORT_APPENDIX_2224.md` | 160 | icall #2224 (ICALL-64): 既知 12 slot のうち 5 件 (`0x1813068d0`〜`0x181306910`) を読む表の特定 (部分達成)。5 件は個別変数 (RIP 相対の直接参照 10 命令・含む関数 7 個)。表は、RIP 直接参照の全数と disp 範囲内の添字参照の形に限ると見つからない (範囲外の形は列挙していない)。添字候補は届かないか上限未確定 (4 命令・#2900 へ移管)。再現スクリプト `tools/icall/diff/known12_readers.py`。`SLOT_ENC_INIT=1` が `0x181306910` (バイトフラグ) に cookie を書く所見 |
| `tools/icall/REPORT_APPENDIX_2081.md` | ~78 | icall #2081 (ICALL-57): SlateCore encoded slot の静的解析 (`slatecore_fptr_table.py`)。受入条件 1・3 は未達で #2120 へ。受入条件 2 は部分達成 (12 slot は zero-fill 部の参照として確認) |
| `tools/icall/REPORT_APPENDIX_2262.md` | ~70 | icall #2262 (ICALL-69): site `0x1810553e6` の target `0xb77e88c8000` の由来 (= `ror(cookie,50)` の下位 44 bit。lifted IR が cookie を `load i32` で読むことが原因)。`fa_sweep.sh 8 60` の再測定 (131 関数 artifact・bit 一致 47)。表への包含判定と cookie 幅の修復は子 issue へ移管 |
| `tools/icall/REPORT_APPENDIX_2394.md` | ~120 | icall #2394 (ICALL-75): `function_181057b38` の値 `0x400000004` は元の機械語に無い。真因は RetDec が frame 上の 2 store を IR から脱落させること (段の特定・回復実験・census・D24 行案は付録)。再現は `tools/icall/frame_slot_2394.sh` |
| `tools/icall/REPORT_APPENDIX_2427.md` | ~120 | icall #2427 (ICALL-77): 脱落 frame slot store を IR に戻す pass `frame_slot_restore.py` (機械語の census 定義で検出し、値を lea から解決して alloca を 16B に結合) と、`fa_route_build.sh` の `FA_FRAME_SLOT=1` 組込み (既定 OFF)。181057b38 の 8 入力 TRAP 8→0・BLK+0 emsc 8→0、fa_sweep は同関数の wasm_err 8→0 の 1 件のみ変化。残件は ICALL-78 (#2508) |
| `tools/icall/REPORT_APPENDIX_2508.md` | ~223 | icall #2508 (ICALL-78): 0x181057b38 の不一致は harness 由来 (xmm0 の出力スロット BLK+0x88 未初期化)。`fa_cmp.py` で修正。sweep の数値と残件は付録 §3.4・§6 が正本。0x180da6e60 の候補は部分分類。受入 3 (plugins-freshair) は #2675 (`REPORT_APPENDIX_2675.md`) で解決・受入 4 (merge 規則の他関数での検証) は §8 で実施 (再現手順は §8.4) |
| `tools/icall/REPORT_APPENDIX_2674.md` | ~130 | icall #2674 (ICALL-79): `fa_cmp.py` のユーザ空間ポインタの PTR 正規化 (0x18105d9fc 0/8→8/8)。0x180da4030 の xmm0 脱落は RetDec の data 区分誤分類による後続命令の欠落 (新類型案 D24)。0x180da6e60 の SIGSEGV は global でなく rcx の構造体未用意 (2508 §4.3 を訂正)。残件は #2695・#2708 |
| `tools/icall/REPORT_APPENDIX_2675.md` | ~70 | icall #2675 (ICALL-80): `SlateCore.core_64` 205 B の sha256 照合 (rw.dll と一致)。測定値・再現は付録が正本。`#2508` 付録 §6 の受入 3 を解決 |
| `tools/icall/REPORT_APPENDIX_2695.md` | ~249 | icall #2695 (ICALL-81): 0x180da6e60 の native harness 初期化 (件数 0 経路で SIGSEGV を解消)。§10 で件数 1 の hang を解消 (`node[0].next = nil`)。候補 6 件は判定 0 件 (受入 2 未達。残件は state 2・8 の harness)。0x1803dee20 の native 既定出力は測定ごとに異なる (7763 は 0/8、6973P-C は入力素通し 8/8・未解決)。結論・数値・未解決は付録が正本 |
| `tools/icall/REPORT_APPENDIX_2565.md` | ~110 | icall #2565 (PLG-P0b-20): BLK (0x8A1000) を再配置範囲の外へ。BLK の VA は据え置き、`icall_rewrite.py` の `place()` が関数・stub を BLK 域 `[blk, blk+0x280)` の後ろへ送る。成果物の交差 1 件 → 修正後 0 件・PE の BLK 域 0 埋め。検算は `check_blk_domain.py`、F.ranges は `mk_franges.py` |
| `tools/icall/REPORT_APPENDIX_2696.md` | ~129 | icall #2696 (ICALL-82): closure 関数のうち dsm の data 区分に実コードを含む関数の実測 (件数は候補。非コード対照でも一部が通るため確定ではない)。修復と受入 3 は子 #2708 (ICALL-83)。測定値・定義・negative control の正本 |
| `tools/icall/REPORT_APPENDIX_2310.md` | ~180 | icall #2310 (ICALL-72): BLK+0 (0x36319008) 書込み store の wasm オフセット対応の付録。route/lift 分類は §6 で完了 (受入条件 2)。脱落 store の修復は #2427 → #2514 (merge 済み)、残件は #2508。`fa_sweep.sh 8 60` の実測 (bit 一致 46 / 値の不一致 10) は 1998 §4 の 47 / 9 が正本で、±1 揺れは #2302 で追跡 |
| `tools/icall/REPORT_APPENDIX_2079.md` | ~62 | icall #2079 (ICALL-56): closure 外 indirect target `0x1810806a0` の扱い (closure root に追加・152 関数)。`fa_sweep.sh` の実測と、`0x1810553d0` の値の不一致が未解消であること (#2120 で追跡) |
| `tools/icall/REPORT_APPENDIX_1921.md` | ~72 | icall #1921 (ICALL-51): SlateCore の encoded 関数ポインタ表・cookie の特定と、native loader の enc(NULL)=cookie 初期化 (`FA_ENC_INIT=1`)。受入条件 1・2 は部分達成 (wasm 側と api-set 表は #2009・#1922 へ移管)。`fa_sweep.sh 8 60` の件数変化の実測を含む |
| `tools/icall/REPORT_APPENDIX_1838.md` | ~50 | icall #1838 (ICALL-41): CHAININFO 断片による Fresh Air 範囲の伸長 (`prep_targets.py` の `chain_end`・親同一性チェック)。実 PE での伸長件数・roundtrip の再測定は素材待ち (本付録 §3 に状態を記す) |
| `tools/icall/REPORT_APPENDIX_1067.md` | ~71 | icall REPORT §13 (#1026: Fresh Air 残落ち 6 件) の全文 (`REPORT_APPENDIX.md` §13 から分割移動) と、#1067 (ICALL-20) の段別切り分け。段別の主張は推定・既存記録のみで、dump 再生成は未実施 (素材 `work-icall`・`plugins-freshair` が要る) |
| `tools/icall/REPORT_APPENDIX_1451.md` | ~70 | icall #1451 (ICALL-28): Fresh Air SlateCore closure 131 関数の wasm route (`fa_route_build.sh`) と native xmm0 bit 比較の付録。内訳 bit 一致 41 / native crash 66 / wasm のみ err 15 / 値不一致 9 (`fa_sweep.sh` 出力が正本)。未了は子 #1606・#1632・#1633 |
| `tools/icall/REPORT_APPENDIX_1298.md` | ~56 | icall #1298 (ICALL-24): Fresh Air 残落ち 6 件の RetDec 段欠落の切り分け (素材 dump の再解析・段は推定、pass 未特定。dump 生成 commit は未確定)。REPORT §13 の段別主張の根拠 |
| `tools/icall/REPORT_APPENDIX_1454.md` | ~75 | icall #1454 (ICALL-29): Fresh Air 残落ち 6 件の切り分け。lock/xadd の IR diff (空)・--backend-no-opts 比較 (間接 call 検出不能のため未確定)・pass 別計測の未達。子 #1612 |
| `tools/icall/REPORT_APPENDIX_1206.md` | ~23 | icall #1206 (ICALL-21) の全文 (旧 `REPORT_APPENDIX.md` §17 の分割移動・無変更)。jump table の cmp/je 展開の効果の実測。`REPORT_APPENDIX.md` §17 は 1 行要約とリンクのみ |
| `tools/icall/REPORT_APPENDIX_1573.md` | ~42 | icall #1573 (ICALL-31): OTT F の jt_dropped 8 件の展開後残件数の実測 (before 1 件 → after 8 件・8 VA の before/after 対応表)。素材 `analysis-ott-binaries`。解釈の未解決は #1763 (ICALL-38)。鮮度の証跡 (測定 commit と `git diff` の空出力) を含む。OTT F の数値の正本 |
| `tools/icall/REPORT_APPENDIX_851.md` | ~40 | icall #851 (`0x128c320` の関数境界誤認 = decode 範囲分割) の全文。`REPORT_APPENDIX.md` §15 の別置き (250 行上限のため)。現 HEAD の A〜D 実測と、前回 `adc7f577` の chunk 実測 (未再現) を含む |
| `tools/icall/REPORT_APPENDIX_1592.md` | ~67 | icall #1592 (ICALL-33): 警告 10 件の出所 (段の帰属は #1456 の BIR 段記述と未突合) と 366 site 落ちの独立性 (A〜D 再現・`roundtrip.sh` 書換え後 C/D 集合とも 366 落ち)。DEFECTS 行案は保留。未了は子 #1776 |
| `tools/icall/REPORT_APPENDIX_1776.md` | ~82 | icall #1776 (ICALL-39): 警告 10 件の段の帰属 (LLVM→HLL の CFG 構築 2 件・copy-propagation 系の再構築 8 件) と `addEdgeFromVector()` の発生箇所 (upstream v5.0 で確認)。statement 単位の出所と最終出力への影響は未了 (子 #1861 `[ICALL-46]`)。DEFECTS 行案は保留 |
| `tools/icall/REPORT_APPENDIX_1763.md` | ~59 | icall #1763 (ICALL-38): OTT F の jt 比較列 8 site の jt_present→jt_dropped 遷移の切り分け。rewrite 側の展開は 8 site とも生成済み。after IR で比較列区間の `insn.addr` が 0 件 (RetDec の switch 畳み込みが有力だが未確定)。before 段階で落ちていた 1 件 (0x1801a31fb) は未切り分け。未解決は子 #1839 (ICALL-42) |
| `tools/icall/REPORT_APPENDIX_1589.md` | ~80 | icall #1589 (ICALL-32): jmp [mem] 走査 (現 HEAD: 250 関数 / 267 site。前 run の 265 / 288 は再現できず) と block24412 の before/after 分類変化 (lost 2→0、現 HEAD で再測定)。jt_dropped>0 の件数は現 audit 未確認 (旧 audit 記録のみ)。RetDec 復元か rewrite 計数かは未切り分け。受入条件 1 は未達 (次 run で実施。素材: plugins-ott / plugins-freshair) |
| `tools/icall/REPORT_APPENDIX_1402.md` | ~21 | icall #1402 (ICALL-26) の jmp [mem] 形 jump table の cmp/je 展開 (jtm) の実装と、FLEngine 0x40d210--0x40d31b の before/after 実測 (dropped 0→0・未解決 → #1589)。REPORT_APPENDIX.md は 250 行上限のため増やさず別置き |
| `tools/icall/disp_size/REPORT.md` | ~160 | capstone `disp_size` 誤り (D9) の水平展開監査 |
| `tools/icall/landing/REPORT.md` | ~165 | Delphi unwind landing pad の抽出と lift |

(ターゲット別の REPORT は下記「ターゲット別プラグイン」を参照)

### OTT (Xfer) 完走路

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/ott/REPORT.md` | ~185 | junk 根本原因の特定・修復 + native 実機械語 bit-exact 参照 (完走路の正本) |
| `tools/ott/avx/REPORT.md` | ~190 | OTT-T3: AVX/VEX 命令の lift 対応と FMA 経路の bit-exact 検証 |
| `tools/ott/crtinit/REPORT.md` | ~180 | OTT-T5: CRT 初期化の等価置換 + override 4 件の実機械語 lift 置換 |
| `tools/ott/entry/REPORT.md` | ~120 | OTT-T4: x64c lift の入口拡張 (bit 突合) |
| `tools/ott/f7eval/REPORT.md` | ~180 | CAB-238 評価: `ott --auto f7,p1` 既定化 |
| `tools/ott/ACCEPTANCE_CAB137_CAB138.md` | ~210 | OTT CRT/entry 検収記録 |
| `tools/ott/ACCEPTANCE_CAB238_CAB135.md` | ~210 | OTT f7 既定化・AVX 検収記録 |
| `tools/m6/REPORT.md`・`tools/m7/REPORT.md`・`tools/m8/REPORT.md`・`tools/m9/REPORT.md`・`tools/m10/REPORT.md` | ~280/210/160/115/105 | 旧 RetDec 路線 M6〜M10 の経緯 (歴史) |

### FLEngine 起動

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/m11/REPORT.md` | ~229 | FLEngine_x64.dll 部分起動 PoC (stage 4/6・残 trap・次の一手)・§11 (#572, 要約のみ)・§12 survey の OOM/clobber 分離 (#513)・§13 (#516 qstore D17, 要約のみ)。§8 (LB_BASE #222)・§9 (sigfix #131)・§10 の commit 別測定表 (#132, §10a)・§10 の一部 (真因・修正 4 点・NC・次 blocker, §10b) は `REPORT_APPENDIX.md` に分割 |
| `tools/m11/REPORT_N2778.md` | ~74 | #2778 (M11-N157, 部分達成): run・survey の ptrcheck に基準付きゲート (`M11_PTRCHECK_MAX_NEW`・`M11_PTRCHECK_SURVEY_MAX_NEW`・既定は情報出力のみ) を追加。ネガコン (`m11_ptrcheck_negctl.sh`) の実測・survey 未実行の理由・基準を ratchet とした理由 |
| `tools/m11/REPORT_N2768.md` | ~185 | #2768 (M11-N155): 寛容起動で skip した unit が trap までに heap へ書いた範囲 (72 unit の表)・上位のリスク評価 (推定)・PR #2752 との環境差。heap 範囲の結論は REPORT §0 を参照。集計は `m11_tolerant_heap.py`・測定は `m11_tolerant.mjs` の `M11_HEAP_FROM`/`M11_HEAP_OUT` |
| `tools/m11/REPORT_N2714.md` | ~150 | #2714 (WIN-3): m11 寛容起動 (tolerant boot) の実測 (942 試行・ok 874・skip 67 の種類別・DllMain 戻り値 1)・skip unit の状態欠落リスク順位 (推定)・既存経路の回帰 (strict 56・survey 872) とネガコン。実装は `m11_tolerant.mjs`・`m11_tolerant_gate.py`・§4-2 の区間内訳は `m11_tolerant_sections.py` |
| `tools/m11/REPORT_N15.md` | ~16 | m11 REPORT §16 (#490 main HEAD の 4c3baa4 / faee5b6 状態の実測・ネガコン) の付録 (250 行上限のため分割) |
| `tools/m11/REPORT_APPENDIX_1430.md` | ~60 | m11 #1430 の基準 (before) 節の全文 (`REPORT_APPENDIX.md` §9 の後続。xmm 引数の callee 署名復元の前測定 (survey 基準 ok/trap/miss/noproc の実測)・`work-m11` 由来の 7 カテゴリ (和 1,963)。全再生成 IR の測定は #1532) |
| `tools/m11/REPORT_APPENDIX.md` | ~238 | m11 REPORT §8 (LB_BASE=0x10000 適用 #222)・§9 (sigfix 0 詰め #131)・§10a (#132 commit 別測定表と注記)・§10b (#132 真因・修正 4 点・NC・次 blocker・外した内容)・§12 の一部 (#513 新規類型の行案)・§12b (#513 巨大 VirtualAlloc の n の出所) の全文 (250 行上限のため本体から無変更で分割移動) |
| `tools/m11/REPORT_N1318.md` | ~69 | #1318 (N82): 10 進 inttoptr 4364 件の VA→LVA 仕分け表 (分類件数・判定規則・QPF 整数定数 1 件の誤 remap)・再現 `m11_inttoptr_class.py` |
| `tools/m11/REPORT_N54.md` | 108 | #954: xmm を読む callee の IR 署名復元 (opt-in `M11_XMM_ARGS=1`)・34/49 件復元・survey 差 0・全件復元時の退行の二分探索表・`fix_xmm_args.py` の呼出し引数個数検査 |
| `tools/m11/REPORT_N154.md` | 94 | #2762: arity 不一致 callee の xmm 呼出し引数の復元 (i128 placeholder を float/double へ変換)・復元 39 件・survey 差 0・`function_40c650` の退行による保留 |
| `tools/m11/REPORT_N55.md` | 74 | #955: sigfix 0 詰め site 1,049 件の liftdiff 差分ハーネス判定 (一致 174 / 不一致 289 / 未到達 586)・判定表 `results/sigfix_zeropad_liftdiff.tsv`・再現 `m11_zeropad_liftdiff.py` |
| `tools/m11/REPORT_N53.md` | ~49 | #953: sigfix 0 詰め引数の理由別 (why) 内訳・未復元件数 (kind 件数の正本は REPORT_APPENDIX §9)・`M11_SIGFIX_RECOVER=1` の退行検査 (#131 子) |
| `tools/m11/REPORT_N21.md` | ~35 | M11-N21 (#572): m11_data_gen.py の DIR64 補正境界 off-by-one の全数照合・参照経路・修正・ネガコン・実測 (REPORT §11 は要約のみ) |
| `tools/m11/REPORT_N1904.md` | ~70 | #1904 (親 #1702): 新規 12 site (引数 20) の発生段の切り分け。`m11_post.py` の 7e149974/392d8ba5 間の pad 一覧・post 出力が一致 (後段は原因でない)・新規 caller が素材 IR に無い (上流 lift/範囲段)・残りの二分探索は子 issue へ |
| `tools/m11/REPORT_N2045.md` | ~65 | #2045 (親 #1997・#1904): 依存を含む範囲 129 commit・二分探索 1 段の駆動 (`m11_bisect_step.sh`)・段 1〜4 (順序 65・33・17・9) の実測 (いずれも 1,061 / 2,084)。基線 `7e149974` の同手順測定は未実施で、原因 commit は未特定 (子 #3011) |
| `tools/m11/REPORT_N1835.md` | ~70 | #1835 (PR #1868): argrecover_verify の stack 引数位置 (pos ≥ 4) 検算の実測 (match 33 / mismatch 0・ネガコン 30/3)・join 点越えの限界・再現手順。再測定は work-m11 素材が要るため本 run では未実施 |
| `tools/m11/REPORT_N1176.md` | ~45 | #1176 (M11-N71): work-m11 同梱の古い obj/rt.o・win.o が build を落とす件の再現 (rc・所要の実測)・`m11_build.sh` の mtime 判定の穴を source sha256 判定に変えた修正・`--full` の未検証範囲 (Ghidra 素材不足) |
| `tools/m11/REPORT_N715.md` | ~70 | #715: m11_e2e.sh 回帰ゲートの期待値 fail-closed 化・判定分岐の実測・e2e 再現試行 (`work-m11` 不足で fail-closed 停止)・PR 作成者の報告値 (未再現) の所在 |
| `tools/m11/REPORT_N27.md` | ~238 | #680: survey 測定基準の固定化 (ldfix/qstore の fail-closed・PE パス env 化・IR 生成条件と指紋の記録・同一 runner の n=3 再現・NC 試験・`--full` は入力 CSV 欠落で未成功 (§10)・レビュー指摘の扱い・§13 73532f8 (c) 数値の切り分け) (環境間一致は未実測)。§14 (#960 `--full` 2 回実行の段の切り分け) は要約のみで全文は `REPORT_APPENDIX_960.md` |
| `tools/m11/REPORT_SHX-T26.md` | ~49 | #1629 (SHX-T26): trap stack の `wasm-function[1352]` = `function_4133f0` (ガード版のみ)。`function_8c5eb0` は stack に出ず D19 とは別原因と判定 |
| `tools/m11/REPORT_N1598.md` | ~60 | #1598 (M11-N104): `m11_e2e.sh` 既定経路を HEAD `4c3f7458` で rc 0 まで再通し (623 秒・judge PASS)。Ghidra 12.1.4 (sha256 一致・JDK 21) で `functions_dll.csv` 59,010 行を作成。trap (stage 4) は残存 |
| `tools/m11/REPORT_N1415.md` | 218 | #1415: snapshot IR (`69c774de…`) と再生成 IR の段ごとの sha256 切り分け (merge・asmfix までは一致)。`alloca [N x i64]` 54 件は R8 導入前 pass (`159d9fc0~1`) で再現。ldfix の `ldfxc` 差 54 件と (b)(d) は未解決 (子 issue)。§8 (#1597・#2163 の二分結果) と §8-4 (ldfix 有りの再測定) |
| `tools/m11/REPORT_APPENDIX_2163.md` | ~68 | m11 #2163 (REPORT_N1415.md §8-4) の全文: ldfix 有りの再測定表 (`035274be`・`5ee72b93`・`03692a0c`・`9952e605`・`9af7827f`・`3bdae05d` 等)・merge `9952e605` の親の向きと 862→866 (`03692a0c`) の `git diff --stat`・§8-1〜§9 の値の扱い・測定手順・未解決 |
| `tools/m11/REPORT_N1165.md` | ~110 | #1165: 旧 IR (818/21/56/77) の再現 (`d6a17b64` 手順で ok 818・oob 21・halt0 56)・ldfix の有無による差 (818 ↔ 828)・ldfix 無し build の opt-in 経路 (`M11_ALLOW_LDFIX_DISABLED=1`)・HEAD の 2×2 測定。lift 段の起点と e2e 全体は未解決 (#1165) |
| `tools/m11/REPORT_APPENDIX_960.md` | 238 | m11 REPORT_N27 §14 (#960: `--full` を同一 HEAD・同一 PE で 2 回実行し、IR の差の段を切り分け) の全文 (250 行上限のため無変更で分割移動) と、#960 追補 §15・#1664 の §16〜§19 (RetDec drc.ll の `uselistorder` 非決定の切り分け・A7 の空行残りの特定と修正・修正後の `--full` n=3 の `ir_sha256` 一致)・#2456 の §20 (指示行の差が書き出し前の状態にあること・アドレス依存の観測。§18 の writer 段の推定は訂正) |
| `tools/m11/rtl/REPORT.md` | ~248 | Delphi RTL の VA 範囲確定 + RTL 帯 (System/Types/SysUtils 1,172 関数) の lifter 別 liftdiff 採点 (#129) + x64c 不一致の主因タグ分類 (§9・集計は `classify_x64c_mismatch.py`・結果は `results/x64c_mismatch_classify.txt`・#410)。§7-4 は `REPORT_APPENDIX_129.md`・§9-4 は `REPORT_APPENDIX_1721.md`・§9-5 は `REPORT_APPENDIX_1936.md` に分割 (250 行上限) |
| `tools/m11/rtl/REPORT_APPENDIX_129.md` | ~17 | m11/rtl REPORT §7-4 全文 (`ff28834` レビュー指摘対応の後処理検証・ネガコン・ImageBase 化の注記)。REPORT.md から分割移動 |
| `tools/m11/rtl/REPORT_APPENDIX_1721.md` | ~22 | m11/rtl REPORT §9-4 全文 (`0x44a4d8` の wasm probe 実測と表)。REPORT.md から分割移動 |
| `tools/m11/rtl/REPORT_APPENDIX_1936.md` | ~59 | m11/rtl REPORT §9-5 全文 (vtable `0x42f670` の native/wasm 実測・敷設経路・退行 5 件の分類)。REPORT.md から分割移動 |
| `tools/m11/alloca/REPORT.md` | ~150 | alloca 縮退修正 (CAB-129) |
| `tools/m11/qstore/REPORT.md` | ~90 | 64bit スタック局所の即値 store が 4B に縮む欠陥 (DEFECTS D17) の検出・修復・idx 87/898/58–63 の帰属・#513 取り込み後の実測 (#516) |
| `tools/m11/trap_triage/REPORT.md` | ~228 | M11 survey trap の個別原因切り分け (#130)・halt0 20 の原因 (#417)・OOB 分類 (#419、§8.2 = 旧 tree の実測。現 main の ON/OFF 比較は REPORT_595) |
| `tools/m11/trap_triage/REPORT_2212.md` | ~115 | #2212: rt.o の静的データ配置 (`g_dest_h`・`g_rec_*`・pad) と関数有無の対照 (NODATA 2012・PRE/POST の 2006・既定 2008)・リンク後の実アドレス・n=3 の決定性 (生値 `table_2212.tsv`・`addr_2212.txt`)・再現 `repro_1952_rt_mech.sh` |
| `tools/m11/trap_triage/REPORT_714.md` | ~246 | #714: OOB 呼出し鎖・計測器の影響・実値採取の再試行 (§12〜§13)。#1602 r4 の要約は末尾。全文は `REPORT_APPENDIX_1602.md` |
| `tools/m11/trap_triage/REPORT_APPENDIX_2785.md` | ~73 | #2785: 304/555/923 の obj 生成元。詳細は付録 |
| `tools/m11/trap_triage/REPORT_APPENDIX_2203.md` | ~115 | #2203: unit 158 の j=12 の 2 区間 (A/B) の OFF/ON 比較。ON は 412c20 前後の指紋、OFF は IR 挿入で dest/len を記録。判定は clean ON/OFF とも ok・観測版 ON の trap は観測副作用。len 差の上流は未追跡 (#2152) |
| `tools/m11/trap_triage/REPORT_APPENDIX_1602.md` | ~191 | #1602: C 版内 stderr 計測 (§13)・hook 変種 (§14)・範囲内常時出力版 (§15) の不採用試行と、V8 inspector (`inspect_trap.mjs`、build 不変) による trap 時点の wasm local 採取 (§16、判定不変・304/555/923 の実値) |
| `tools/m11/trap_triage/REPORT_1352.md` | ~50 | #1352: 計測 build (`M11_INSTR_413060=1`) の OFF は HEAD `1be53b3f` で既定と同じ 870/24/0 (871/23 は再現せず)・`M11_DEST_READ=0` でも 870/24/0。3 点切り分けは未実施・再現 `repro_1352.sh` |
| `tools/m11/trap_triage/REPORT_2672.md` | 125 | #2672: unit 477 の `0x10a9f910` 下位 4B 書込みの主体 (C 版 `function_4133f0` の shadow stack 局所、`m11_ov.c:340`)。wasm 側 store 計装 (`watch_store_2672.mjs`・`store_sites_2672.py`) の陰性対照 (942 unit の kind 差分 0)・陽性対照 (OLD=0 で unit 1 hit)・類型案 (管理型局所のゼロ初期化欠落、仮説) |
| `tools/m11/trap_triage/REPORT_2780.md` | 114 | #2780: unit 492 OOB の `4473f0` 乗算 (`0x92492493`) の戻り値を実測 (原因ではない)・OOB 入力 `dest=0x10aa1160` の旧値 `0x1_00000003` の値遷移 (unit 432・477・484)・gated probe (`M11_PROBE_2780=1`) |
| `tools/m11/trap_triage/REPORT_882.md` | 212 | #882: M11 survey trap の p-144 再現・40ffe0 入口 probe の本体 (§0 結論・§1〜§11)。§12・§13 は `REPORT_882_APPENDIX.md` に分割移動 (250 行上限) |
| `tools/m11/trap_triage/REPORT_882_APPENDIX.md` | ~89 | #882 の §12 (7 回目 run: p-144 再現測定) と §13 (8 回目 run: 40ffe0 入口 probe の実測) の全文。REPORT_882.md の 250 行上限のため分割移動 |
| `tools/m11/trap_triage/REPORT_2373.md` | ~90 | #2373: unit 895 の `60a270` (this=0) の caller は `e3ef60` (9 箇所)。`60a270` の caller 列挙・経路の静的確認・`e3ef60` の 9 箇所の this のフィールド。再現 `callers_of.py` |
| `tools/m11/trap_triage/REPORT_2408.md` | ~115 | #2408 (親 #2369、REPORT_1676 §14): list B `+8/+16` の書込み主体。全 store 計装が unit 106 で止まる原因 (`m11_sw` の `-O0`)・IR 全関数の計装結果 (`+16` は `function_50a830` の 1 件、`+8` は IR の store 0 件)・欠落 IR (`50a830` の仮想 Grow/Notify、D15 同類型)・DEFECTS 行案。再現 `store_watch_2408.sh` / `reach_2408.py` |
| `tools/m11/trap_triage/REPORT_1317_APPENDIX.md` | ~241 | #1317 の §10 (#1786 run: 計装の試行) と §12 (8 回目 run: `b36d3b5f..e7c5c062` の 6 ファイル diff 全文)。REPORT_1317.md の 250 行上限のため分割移動 |
| `tools/m11/trap_triage/REPORT_134.md` | ~120 | #134: unit 56 (VA 0x16fde0) の fail-fast 辺の guard 入力の trap 時実測 (arg2 dl=1・R (410320 戻り)・list (8c67a0(R) 戻り) の件数 0・[vt-0x50] = ret stub)、基準 survey の再測定 (870/24/47/1)、機械語照合、IR probe (`probe134_ir.py`・`M11_PROBE_134`)・再現 `probe_134.sh` |
| `tools/m11/trap_triage/REPORT_1542.md` | ~90 | #1542: 計測 build の getmem −4 (既定 2012 / 計測 OFF 2008) は post の 3 点 (probe・改名・宣言) に帰属せず、IR 同一でも残る (C 側の計測 flag が候補)。C 側の切り分けは #1701。A〜D 再現 `repro_1542_split.sh` |
| `tools/m11/trap_triage/REPORT_1275.md` | ~110 | #1275: `function_535c2e` は `function_535bf0` 内の `ret` (VA 0x535c2e) で、RetDec が call に変えた lift 起因の機械語突合・ClassCreate ON/OFF/転記 ON の 304/555 kind 遷移・再現 `n78_measure.sh` |
| `tools/m11/trap_triage/REPORT_419.md` | ~58 | #419 の合流前 (fa918df 基準) の OOB 修正試行・旧 ON 構成 (410360 + 8cbda0/8cbce0) の測定 (REPORT §8 から無変更で分割移動) |
| `tools/m11/trap_triage/REPORT_679.md` | ~110 | icall site 0x41037d の hit 23,053,861 の内訳 (unit 101 = #513 の暴走 loop に 99.999% が集中)・既定 ON の 0x41032e 併記・再現手順と検査スクリプト `icall_41037d_679.py` (#679) |
| `tools/m11/trap_triage/REPORT_418.md` | ~70 | 409470 転記ハングの原因特定 (#418) |
| `tools/m11/trap_triage/REPORT_595.md` | ~90 | ClassCreate ON (`M11_OV_CLASSCREATE=1`) の ok 退行の原因切り分けと C 転記 (`41c130` / `413060`)・残る unit 415 の原因・既定 OFF のネガコン (#595) |
| `tools/m11/trap_triage/REPORT_1157.md` | ~50 | #1157 の二分探索の前提の実測・判定基準の未確定 (基点 `5ff73ff` と現 main の OFF/ON 測定・PM 判断事項) |
| `tools/m11/trap_triage/REPORT_704.md` | ~60 | unit 415 の `9b4b00` (と `9b5450`) の C 転記 (ON 時のみ) と、現 IR での ON 退行 4 件 (101/190/291/296) の再測定 (#704) |
| `tools/m11/trap_triage/REPORT_474.md` | ~100 | 410320 補完後の unit 114 ハング = 5c0270 の unlink deref 脱落 (#474)・409470/410320 再採用 |
| `tools/m11/trap_triage/REPORT_699.md` | ~150 | `8c5eb0` の件数 0 ループ先頭ガードの IR 復元 (unit 56 の trap→ok・ネガコン)・全 IR 関数の jcc↔IR 後続突合の走査 (候補件数は未検証) と、ガード辺の値・未確定事項 (#699)。測定値は本文 §3 |
| `tools/m11/trap_triage/REPORT_482.md` | ~100 | `5c03d0` の node 差替え通知 `call [rbx+0x18]` の D15 脱落を復元 (#482)・survey 不変の実測 |
| `tools/m11/trap_triage/REPORT_594.md` | ~95 | 8cc190 系 OOB は入力不正ではなく `417b70` の `Q(a)` 上位 4B 未初期化 (D17 型)・#552 での解消の実測・unit 56 の別原因・`negctl_594.sh` gate (#594) |
| `tools/m11/trap_triage/REPORT_495.md` | ~115 | `SV_TRACE_AT` 付き survey で unit 134 が ok→oob になる原因 (trace の fprintf が残す stack 残骸 × `function_413870` の引数脱落) と trace の透過化 (#495) |
| `tools/m11/trap_triage/REPORT_663.md` | ~158 | survey の oob frames が最上位 wasm frame を 1 段捨てる (`.slice(1)`) 欠陥の修正・filter の `/^\s*at /` アンカー化・annotate の最上位集計の再計算 (#663、基準 (c) は未実施。最終 HEAD の再測定は REPORT_663 §8) |
| `tools/m11/trap_triage/REPORT_861.md` | ~70 | unit 189 (409470 ReallocMem) の IR↔逆アセンブル突合・既存 C 転記 (#474) のネガコン (転記なしで 189 は halt0、ok→非 ok 24 件)・転記あり/なしの回帰 (unit 368 のみ)・未解決の起票先 (#861) |
| `tools/m11/trap_triage/REPORT_1043.md` | ~60 | unit 368 の 409470 VA-big 確保の原因 (`function_980ed0` の 10 進 `inttoptr` 1 件の VA→LVA remap 漏れ)・`pass_m2q_fn980ed0` による修復・ネガコン/修復の survey (ok 869→870, 変化は 368 の halt0→ok のみ)・残件 (#861 受入 4) |
| `tools/m11/trap_triage/REPORT_1046.md` | ~67 | #1046 unit 492 OOB 途中経過 (`4133f0` の入力値は未実測・受入 4 のみ達成・受入 1–3 は #1288) |
| `tools/m11/trap_triage/REPORT_1620.md` | ~204 | #1620: unit 477 の `0x10a9f910` 下位 4B 上書きの書込み元 (IR store 経路ではない見込み・書込み主体は未特定)。埋め値依存の位置 (unit 134) は §10 で検証不能と訂正。C 呼出し計装の副作用 (unit 304)・計装 `trap_w1620.py`。§10: `0x10a9f910` への書込みは初期 SP の配置 (C 側の静的データ量) で消える (HEAD で前提が再現しない)・埋め実験の訂正 |
| `tools/m11/trap_triage/REPORT_596.md` | ~125 | work-m11 snapshot 基準の OOB 21 unit の最上位 frame 分類・4f9f40 系/414ad0 系の観測・#307 の OOB との同軸突合 (#596) |
| `tools/m11/trap_triage/REPORT_494.md` | ~125 | survey の per-unit JSON に間接 call の site / target 別 hit 数 (`icall` 欄) を常設・#482 の復元を hit 数だけで検収 (#494) |
| `tools/m11/trap_triage/REPORT_683.md` | ~110 | function_414ad0 (SetLength) の `[arg1]` deref 復元の C 転記 (gate `M11_OV_414AD0`) と IR 版の A/B。結論・測定値は REPORT_683 (#683) |
| `tools/m11/trap_triage/REPORT_483.md` | ~205 | oob→halt0 12 unit の Error() 原因 = TDictionary 比較器チェーンの D4/D15 脱落 (#483)・merge 後 head の再測と ok→非 ok の原因分類 |
| `tools/m11/trap_triage/REPORT_682.md` | ~200 | 4f9f40 系 5 unit の TList items 書込み元 = `function_47b260` (D4 の新事例) の特定と C 転記修復 (`M11_FIX_682`)・全 store 計装・ネガコン・notify (D15) の unit 別実測 (#682) |
| `tools/m11/trap_triage/REPORT_862.md` | ~79 | #862 unit 492 の再測定: `410630` は現 main で到達 0 (前提消失)。unit 492 は OOB (`4133f0`)。HEAD の 3 回反復 (ok 869 / halt0 8 / oob 16) |
| `tools/m11/trap_triage/REPORT_684.md` | ~184 | #684 単発 OOB 4 unit (95/275/477/895) の個別原因: §8.2 の OOB 最上位 frame の訂正 (survey の `slice(1)` 不具合)・477 の D11 変種 (10 進 `inttoptr` の VA 未変換)・95/275/895 の最上位命令 |
| `tools/m11/trap_triage/REPORT_662.md` | ~141 | unit 56: `8c7710` の D4 型 1 段 deref 脱落の転記 (#662)・`8c5eb0` の件数 0 ループ先頭ガード脱落の特定 (IR 状態 Q の範囲。修復と N 状態の原因は #699)・negctl (base/cur/guard/ng) の n 回再現レンジと IR 状態 Q/N の対照 |
| `tools/m11/ldfix/REPORT.md` | ~165 | load 取り違え (値↔アドレス / 1 段 deref 脱落) IR 修復 pass |
| `tools/m11/ldfix/REPORT_484.md` | ~130 | ldfix が 5c0270 の D4 脱落を検出できなかった理由 (F3c の門 G1〜G5) と load→store 脱落の全数監査 (#484) |
| `tools/m11/ldfix/REPORT_509.md` | ~165 | F3c 門の拡張と LSF 脱落 8 関数 / 11 site の IR 修復、消費者形 (`fix_f3c_use`) の監査、残存誤り (41a670 / 666a60) (#509) |
| `tools/m11/ldfix/REPORT_510.md` | ~150 | base が引数由来でない load→store (370 site / 169 関数) の判定軸: SSA 対応の静的判定 vs liftdiff 動的差分の実測比較と脱落数 (#510) |
| `tools/m11/ldfix/REPORT_564.md` | ~60 | escape 済み stack_var 内部 read の undef 化 (AllocateHWnd 52a7f0 の `cmp [TempClass.lpfnWndProc]`)。ldfix F4 の修復 10 関数と RegisterClassW 到達の実測・全数走査 (#564) |
| `tools/m11/ldfix/REPORT_968.md` | ~50 | D17 修復 pass (rip 相対セルの 2 段 deref 潰れ) の部分達成: 単一 load の 24 関数を修復、残りは子 issue (#968) |
| `tools/m11/ldfix/REPORT_930.md` | ~100 | 消費者形 pure 残 23 関数 (24 引数) の残件分類 (first-deref-not-entry 18 関数 ほか) とネガコン。survey 到達数は再現未了 (#930) |
| `tools/m11/ldfix/REPORT_1134.md` | ~50 | 消費者形 pure 残の部分達成 (原因の記録のみ): tracker-no-deref 3 関数 (75a180・db6480・dc27c0) の機構 (引数 slot のループ内書き換え・2 段 deref)、5c44b0 (none) の理由の一部。修正・修復・再測定は未着手で #1324 (LD-45)・#1325 (LD-46) (#1134) |
| `tools/m11/ldfix/REPORT_1290.md` | ~80 | LD-43 (#1290): `ldfix_509_e2e.sh` の修復前 wasm (明示 opt-in `M11_ALLOW_LDFIX_DISABLED=1`) と修復後 wasm (正規 `ldfix.py --pe` + `ldfix=applied` + bind) の作り方。fail-closed gate は弱めず、step 6/7 の完走と dyn 5/5 を実測。決定は DECISIONS D12 |
| `tools/m11/ldfix/REPORT_1169.md` | ~70 | D17 spill 宛 CELL_COLLAPSED 37 site の判定対応 (#1161 の全数分類との突合・判定内訳・担当付け)。修復 pass を見送った判断 (IR と機械語の対応が取れない site の観察)。修復 pass は子 issue #2794 (LD-130) へ |
| `tools/m11/ldfix/REPORT_2794.md` | ~158 | LD-130 (#2794): spill 宛 TRUE_DROP 24 site の 1 対 1 判定 (機械語の読み出し数 M と IR の K 出現数 I の照合)。1 対 1 の 9 site を修復 (`fix_spill_2794.py`・突合 `check_spill_2794.py`)、spill 宛 CELL_COLLAPSED 37→28、ネガコン。読み出し欠落 6 site は子 #2940 (LD-141)、対応未決 9 site は子 #2910 (LD-137) |
| `tools/m11/ldfix/REPORT_1161.md` | ~59 | LD-35 (#1161): 範囲縮小の完了分。spill 宛 178 site の分類表を HEAD で再測定し、未判定・判定不能を担当 issue (#2245・#2288・#2679・#2583・#2253・#2660) に対応づけた (内訳は REPORT §3)。独立再計算・ネガコン (NC0〜NC7) も再測定で一致 |
| `tools/m11/ldfix/REPORT_2389.md` | ~51 | LD-110 (#2389): cf3790 の spill 宛 3 site (cf3c7a・cf3cbb・cf3d20) の reg2mem 結線 (frame F=472・`stack_var_-(F-disp)`) で TRUE_DROP を確定。ld105 突合表の slot 名 `-(disp+8)` の誤りの訂正とネガコン |
| `tools/m11/ldfix/REPORT_2316.md` | ~75 | LD-108 (#2316) の部分達成: 41a670 の head 解除 store (D20) の検証用パッチ (`fix_ld108.py`、本番 IR 生成経路には未配線) と wasm 直接呼びの修復前後の実測、`audit_lsf_disp.py` の検出と残 SUSPECT、survey 前後の差。`audit_lsf.py` 統合は #2396、本番配線は #2402 (REPORT_2402) |
| `tools/m11/ldfix/REPORT_2447.md` | ~146 | LD-115 (#2447): 666a60 のループの修復 (回数の初期値 `[N]` とループ内 store `*arg1`)。機械語と IR の対応表、`fix_ld115.py` の検証用単独パッチ、wasm 直接呼びの 3 版 (修復前 TRAP / 回数のみ FAIL(slot.f16) / 修復後 PASS)、survey 942 unit 突合 (ok 869 → 869、退行 0)。本番配線は #2527、回数 0 の早期脱出は #2513 |
| `tools/m11/ldfix/REPORT_2405.md` | ~151 | LD-113 (#2405): RetDec 2019-03 版 (`6edcaaea`) の gv 分岐 (constants.cpp L163〜168) の発火実測。2019-03-03 の share (retdec-support) は入手不可として扱い (v3.3 同梱 share も 2019-03-03 と確認できず)、代用 share で 41a6a0・41a6d3・666b10 の発火を v5.0 と件数・root まで一致で確認。一時ログ付きビルドの所要。再現は `retdec2019_gv_2405.sh` (gv 分岐)、`share_check_2405.sh` (share・tag の照合) |
| `tools/m11/ldfix/REPORT_2396.md` | ~120 | LD-111 (#2396): `audit_lsf_disp.py` の変位形を `audit_lsf.py` に統合 (既存 3 判定は byte 不変、SUSPECT_DISP_VAS を並べて出力)。残 SUSPECT 3 件 (6677a0・d237e0・de1da0) を機械語 `movs` の列挙漏れ (誤検出) と確定し、列挙を拡張して 4 → 1 件 (41a670 のみ、修復後 0)。独立算法 `triage_ld111.py` の突合と NC 5 本 |
| `tools/m11/ldfix/REPORT_2438.md` | ~106 | LD-114 (#2438): #2264 §8.3 から移管された spill 宛 未判定 12 site の消費者分類 (OK_LOAD 5・UNDETERMINED 7)。入口の memory 読みの `xor i64 0, 0` (新類型候補・3009 関数) を記録 |
| `tools/m11/ldfix/REPORT_2921.md` | ~77 | LD-138 (#2921): `ddf630` の spill 宛 未判定 4 site (ddf6b5・ddf6c6・ddff5a・de0bfe) を機械語と IR の段数で TRUE_DROP と分類。判定根拠は `results/candidate_verdicts_2921.jsonl`、再現は `ld138_ddf630_dis.py` |
| `tools/m11/ldfix/REPORT_2922.md` | ~65 | LD-139 (#2922): #2838 の残り 12cb680 の 3 site (12cb8e1 判定不能 → 再分類・12cba4d・12cbab4 未判定) を TRUE_DROP に分類 (消費者 = 間接 call 先のコールバックの読み、IR 脱落)。脱落関数の和集合は REPORT §1 の実測値。動的 callback 経路と書き戻しは未解決 (PM) |
| `tools/m11/ldfix/REPORT_2838.md` | ~50 | LD-135 (#2838): #2245 の群 B 残りのうち 466af0 の 3 site (2 段参照の 1 段脱落) を TRUE_DROP に分類。残り 9 site は #2921・#2922・#2923 (LD-138〜140) に起票 (範囲縮小) |
| `tools/m11/ldfix/REPORT_2923.md` | ~42 | LD-140 (#2923): spill 宛 1046a30 の 2 site を再判定。10479c7 は判定不能 (OK_LOAD は撤回。IR 側の確認は #2958)、1047556 は段数は一致するが cell 番地が VA 表記 (22946304) の VA 漏れの疑いで判定不能のまま (修復は #2958 (LD-142))。上流 X の段数は未確認 |
| `tools/m11/ldfix/REPORT_2245.md` | ~70 | LD-93 (#2245): #2227 の群 B (32 site) の部分達成。10 site を分類 (6bb3f0 4・1046a30 4 を TRUE_DROP、1046a30 1047556・12cb680 12cb8e1 を UNDETERMINED)。残りは #2837・#2838 へ移管。脱落関数の和集合 73 |
| `tools/m11/ldfix/REPORT_2837.md` | ~72 | LD-134 (#2837): 10c7cd0 の未判定 12 site を分類。8 site を TRUE_DROP (2 段参照の V 側 deref 脱落。count を K-8 から読む)、4 site を OK_LOAD。脱落関数の和集合 76。e2e 7/7 は測定 commit 9b7ddcc7 で実測 (§1) |
| `tools/m11/ldfix/REPORT_2402.md` | ~110 | LD-112 (#2402): `fix_ld108.py` を `m11_gen_ir2.sh` の ldfix 直後に常設配線 (`ld108` 記録・`m11_build.sh` の拒否・`%arg1` 型 assert)。`ir_conditions` と IR diff (41a670 の 1 関数だけ)、通常 build の wasm での直接呼び、survey 942 unit の突合 (ok 退行 0)、ok 絶対値 869 / 870 の差は IR の出所まで特定 (どの変更が差を生むかは未特定)、136 型は再現せず原因未特定。`666a60` の修復は #2447 |
| `tools/m11/ldfix/REPORT_2502.md` | ~130 | CI-100 (#2502): `function_450560` の 2 段 deref 脱落 (DEFECTS D4) を機械語 26 命令照合付きの IR 修復 `fix_450560.py` で直す。4 変種の e2e 実測 (GetMem/icall は C 転記と一致、トラップ OOB は不変)、同類型の機械語走査 `scan_spill_deref_2502.py` (候補 14 関数 16 箇所)、ネガティブコントロール 4 本。IR 側確認は #2555、本番配線は #2556 |
| `tools/m11/ldfix/REPORT_2660.md` | ~70 | LD-119 (#2660): spill 宛 判定不能 9 site を再検証。4 site は上流 `xor i64 0,0` (型タグ読みの置換) が作る死んだ辺に依存するため TRUE_DROP を取り下げ、判定不能のまま (`ir_reach_2660.py` で到達性を検査)。脱落関数の和集合は 72 (未確定・#1161 残) |
| `tools/m11/ldfix/REPORT_2388.md` | ~75 | LD-109 (#2388): cf3790 の spill 宛 未判定 15 site を全て OK_LOAD と判定 (機械語・IR の行を `ld109_cf3790_verify.py` が照合して生成)・slot 名の式の独立確認 (#2389 と同じ `stack_var_(disp-0x1d8)`)・基底が上流の脱落値由来で汚染される注意。静的突合のみ |
| `tools/m11/ldfix/REPORT_2679.md` | ~106 | LD-120 (#2679): spill 宛 未判定 `128f9e0` の 12 site を UNDETERMINED と判定 (frame slot `stack_var_-760〜-1336` が IR 本体・RetDec の lift/drc に無い根拠・`ld120_frame_128f9e0.py` が生成・`ld120_controls.py` が対照と F の数値)。欠落の起点 (lift 段の block `0x1290610` の打ち切り) は子 #2705 (LD-125) |
| `tools/m11/ldfix/REPORT_942.md` | 248 | #942 (CI-22) stage4 の memory access out of bounds の切り分け (部分達成)。trap 9 件の unit 別最上位 frame・boot threw の入口・bin 表の観測 (§9)・サイズ→bin 表 (§10 は要約)。§8-3 の全表と §10 の詳細は付録 |
| `tools/m11/ldfix/REPORT_942_APPENDIX.md` | 209 | #942 REPORT の付録。§8-3 (trap 最上位 frame 表)・§10〜§14 (bin 表・通常 boot の trap 位置・lift 誤り候補) の全文 (250 行上限のため分割移動) |
| `tools/m11/ldfix/REPORT_942_TRAPSITE.md` | 102 | #942 (CI-22): stage4 survey の trap 9 件の発生箇所 (unit 別) と引き金の実測。上流の書込み元は未特定 (次 run) |
| `tools/m11/shimx_link/REPORT.md` | ~165 | M11 × shimx リンク |
| `tools/m11/shimx_link/REPORT_APPENDIX_179.md` | ~49 | M11 closure の旧 main link 失敗 (`sxt_*` export) の修正前後・`--midi` / `--ws --midi` の e2e 実測・起動 KPI (#179 SHX-T6)。REPORT §11 の全文を分割移動 (250 行上限のため) |
| `tools/m11/shimx_link/REPORT_APPENDIX_2839.md` | ~70 | midiOutShortMsg の HMIDIOUT が IR で i64 になる根因 (SHX-T31 #2839): 機械語・IR・署名 DB (`windows.json` の HMIDIOUT = unknown) の突合、HANDLE 系の対照 (CloseHandle = i64*)、修正方針 (正規化 pass の恒久化)。測定値の正本。再現は `hmo_rootcause.py` |
| `tools/m11/shimx_link/REPORT_APPENDIX_1628.md` | 61 | M11 × shimx: midiOutShortMsg の HANDLE 幅正規化 (#1628 SHX-T25) の全文 (旧 REPORT §12)。修正前の出典と IR 同一性の限界・旧版への fail-closed 非採用 (§12.4)・未解決の起票先 (#2839・#2877)。合成 IR 検査は `test_sx_handle_norm.py`。測定値の正本 |

### shim / 起動

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/shim/README.md` | ~50 | Win32 shim コア (53 export) のナビゲーション |
| `tools/shim/REPORT.md` | ~80 | shim heap の範囲外ポインタ検査 (LD-132 / #2802): `block_ok` の範囲検査・取り込み元 29 件の影響範囲・shim 単体テストと negative control の測定値。u16 の e2e と KPI は #2841 (LD-136) |
| `tools/shimx/REPORT.md` | ~199 | Win32/CRT shim 拡張。§9〜§12 は `REPORT_R1-R8.md`・`REPORT_CAB-214.md`、§15 は `REPORT_SHX-T8.md`・§16 は `REPORT_SHX-T7.md` に分割 (#584) |
| `tools/shimx/REPORT_R1-R8.md` | ~78 | shimx §9 (CAB-211: M11 リンク フィードバック R1〜R8) + §10 (CAB-177: cbtrans R2/R3 実体接続) 全文 (REPORT.md から分割, #584) |
| `tools/shimx/REPORT_CAB-214.md` | ~141 | shimx §11 (CAB-214: vreg reg.c 取込 + username 統一) + §12 (follow-up 後始末 3 件) 全文 (REPORT.md から分割, #584) |
| `tools/shimx/REPORT_SHX-T8.md` | ~60 | SHX-T8 (#175): 序数 import・Crypt・CP932 (REPORT.md §15 から分割) |
| `tools/shimx/REPORT_SHX-T7.md` | ~84 | SHX-T7 (#173): 署名正規化 IR pass + ゲート (REPORT.md §16 から分割) |
| `tools/shimx/REPORT_SHX-T9.md` | ~84 | SHX-T9 (#177): DllMain 経路の SHIMX_TRACE 収集と残一覧 (REPORT.md §6 の付録。数値は commit 済み results の引用) |
| `tools/shimx/REPORT_SHX-T9h.md` | ~49 | SHX-T9h (#2489): 現行 `m11_ov.c` から baseline を再生成して unit 23 を shimx 版と比較。測定値の正本。REPORT_SHX-T9.md の旧 §3.3.5 から分割移動 (250 行上限のため) |
| `tools/shimx/REPORT_SHX-T9i.md` | ~45 | SHX-T9i (#2491): unit 23 の GetModuleHandleW/GetProcAddress の呼出し元 site と戻り値の実測 (§3.3.5)・survey 942 unit の回帰確認 (§3.3.6)。REPORT_SHX-T9.md §3.3.5・§3.3.6 から分割 (250 行上限) |
| `tools/shimx/REPORT_SHX-T9j.md` | ~80 | SHX-T9j (#2533): unit 23 の GetLastError を再生成 baseline と shimx `--trace --soft --fix` の両版で実測 (REPORT_SHX-T9.md §3.3.4 の追補) |
| `tools/shimx/REPORT_SHX-T9k.md` | ~76 | SHX-T9k (#2593): unit 22 の GetLastError=126 の発生元 (GetProcAddress の 1 回目) と、IR 行番号 ↔ wasm バイトオフセットの対応 (REPORT_SHX-T9j.md §2.4 の後続) |
| `tools/shimx/REPORT_SHX-T35.md` | ~118 | SHX-T35 (#3023): HeapFree の範囲外ポインタを M4 契約に揃えた判断と測定 (REPORT.md は 250 行上限のため付録) |
| `tools/shimx/BACKLOG.md` | ~540 | shimx の未解決一覧 |
| `tools/shimx/pathreg/REPORT.md` | ~200 | パス写影/レジストリ永続化の shimx 側インタフェース接続 |
| `tools/shimx/pathreg/REPORT_CAB-271.md` | ~230 | CAB-271: default mount table の遅延ロード |
| `tools/startup/REPORT.md` | ~160 | FL 起動シーケンス / 子プロセス / ゲート / レジストリ / スタブ計画 |
| `tools/startup/helpviewer/REPORT.md` | ~185 | FL の Help 起動経路 (静的解析) + Help を sandbox iframe に出す viewer / error-offline.html 差替 |
| `tools/startup/glue/REPORT.md` | ~200 | THostInstance + CreateFruityInstance 呼出 + 終了処理 |
| `tools/startup/keyfix/REPORT.md` | ~165 | vreg low-key 112 エントリ確定 + username 二重表記の統一 |
| `tools/startup/loadpaths/REPORT.md` | ~245 | ST-T14 (#39): 言語 .moe (暗号化 .mo) の形式・復号・ロード経路、スキン/Artwork/Help の読み手関数と起動/操作時の判定、VFS 配置 group と tier 差分、§8 (#590) 言語検索パス服務の実体・不在時挙動の静的確定 |
| `tools/startup/uilang/REPORT.md` | ~160 | ST-T19 (#591): GetUserPreferredUILanguages の FL 側呼び方・分岐 (zh のみ Program language 自動書込み) と shimx 返値の実測、lang-svg の参照元 (TToolbarForm.FlagBtnPaint)、Windows 標準フォントの要求一覧と代替案 |
| `tools/startup/pump/REPORT.md` | ~110 | user32 ポンプ shim (C) + runtime RING ABI 結線 |
| `tools/startup/vreg/REPORT.md` | ~145 | 仮想レジストリ shim + 登録済み seed |
| `tools/startup/vreg/ilreg/REPORT.md` | ~85 | 0x10c7cd0 登録パーサ / ILRegKey 書式解読 |
| `tools/startup/license_obs/REPORT.md` | ~235 | 登録フラグ byte[0x14f84a8] の全サイト列挙 + gradeChar のサイト列挙 (連続形/レジスタ追跡形; 下限) + 0x10c7cd0 の実機械語実行 (ST-T11 #107) + unit 初期化後の ILRegKey 非空観測 (ST-T15 #525) + gradeChar 確定手段の選定 (ST-T16 #526 §8) |
| `tools/startup/license_obs/REPORT_786_APPENDIX_1492.md` | ~48 | REPORT_786 §13・§14 全文 (#1492 callee 越し解析の表・未追跡の内訳・限界・未解決表)。REPORT_786 本体は 250 行上限のため分割移動 |
| `tools/startup/license_obs/REPORT_786_APPENDIX_1640.md` | ~54 | #1640 間接 call 0x40944e の行き先 (静的スロット 0x13a5c98 → 0x407e20)・再帰打切り 10 件の不動点・`--no-rec-summary` アブレーション (345 件) の付録。測定 commit は本文に記載 |
| `tools/startup/winstubs/REPORT.md` | ~100 | 起動 critical Win32 API の fail-soft stub |

### host / gui / audio / assets

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/runtime/REPORT.md` | ~155 | ブラウザ実行基盤 |
| `tools/runtime/REPORT_APPENDIX_127.md` | ~65 | RT-9 (#127) の追補: 音声込み Firefox 測定の手順と実測表、Playwright WebKit 26.0 (Linux) の参考値 (Safari 実機ではない) |
| `tools/runtime/REPORT_APPENDIX_2552.md` | ~15 | RT-15 (#2552): memload real の派生 loader `PoolBridge` 撤去 (共有 hb_bridge.mjs の HostBridge に接続)。memload real の実測は OTT DLL 素材待ち (REPORT §RT-6 の追補) |
| `tools/runtime/rt10/REPORT.md` | ~190 | 実 FLEngine x64c lift (126MB wasm) の Chrome 起動時間・帯域・tier-up・boot ループ soak (RT-10 #128) |
| `tools/hostbridge/REPORT.md` | ~95 | Fruity Wrapper の VST2 ロード経路解析 + wasm 同梱プラグイン表 |
| `tools/hostbridge/cb/REPORT.md` | ~145 | shimx R2 コールバック変換の実体接続 |
| `tools/hostbridge/h10/REPORT.md` | ~182 | Fruity Wrapper の wrapper chunk reader 解析 (record 1/30–32 の要否・id 57 の正体・212 flags) |
| `tools/hostbridge/h2/REPORT.md` | ~150 | hostbridge surrogate の駆動と ott_run 接続 |
| `tools/hostbridge/h6/REPORT.md` | ~80 | web UI G1: OTT .rsrc PNG 抽出 + 宣言的ノブ UI + effEdit* 結線 |
| `tools/hostbridge/lowbase/REPORT.md` | ~125 | VA 敷設 base 可変化 (+ `x64c/` に x64c ラッパ 3 本目: `x64c/lb_x64c.py` は `tools/ott/lift/x64c.py` を無改変 import) |
| `tools/hostbridge/nfo/REPORT.md` | ~148 | Plugin database (`.nfo`/`.fst`) 書式解読 + 合成 DB 生成器。§10〜§12 は `REPORT_APPENDIX_A.md`・§13〜§14 は `REPORT_APPENDIX_B.md` に分割 |
| `tools/hostbridge/nfo/REPORT_APPENDIX_A.md` | ~112 | nfo §10〜§12 全文 (実機 OTT.fst / `.Plugins.ini`+VerifiedIDs 照合 / VST3 path 規則・KH magic・Massive X CID。#437 で無変更分割移動) |
| `tools/hostbridge/wrapper_lift/REPORT_APPENDIX_2071.md` | ~110 | #2071 (HB-H42): 引数・代入・初期化の `L"..."` (`int[N]` → `int16_t *`) 型不一致の判定 (呼出側の wide literal・宣言側は正) と `retdec_repair.py --wide` の代入・初期化への拡張。修復前後の emcc exit 0・error 行の実測 (測定 commit `f70faf97`)。修復後 literal の PE 一致は `wide_literal_check.py` (§7)。残件は #1954 (HB-H41)・#2853 (HB-H47)・#2653 (HB-H46) |
| `tools/hostbridge/wrapper_lift/REPORT_APPENDIX_829.md` | ~88 | #829 (HB-H20): x64c wasm build の中間物サイズ (C・`.o`)・unsup 内訳と CreatePlugInstance (0x86ab10) 入場ログ・最初に失敗する関数の実測。表に無い値の正本。exit・秒・load・wasm サイズは REPORT §14 の表が正本 |
| `tools/hostbridge/nfo/REPORT_APPENDIX_B.md` | ~150 | nfo §13〜§14 全文 (generateDb→wvfs 結線 e2e CAB-216 + 検収。#437 で無変更分割移動) |
| `tools/gui/flengine/REPORT.md` | ~244 | GUI-3 (#174) 実 FLEngine lift × GUI shim 結合: 自然起動・survey で shim に実到達した API、指向呼出、gate 12 + ネガコン 5。§8 = GUI-12 (#566) `__pe_image` の m11_data_gen 方式統合 (実 FLEngine PE parity・ネガコン) |
| `tools/gui/flengine/REPORT_APPENDIX.md` | ~205 | GUI-3 (#174) REPORT の付録。§6i = S1 (soft) の unit 304/555 調査 (#1442)、§6j = GetMonitorInfoW / EnumDisplayMonitors の重複定義 (#1559)、§7 = WIN-4 (#2715) の closure 取込と呼出し (部分達成)、§8 = WIN-13 (#2905) の open 系 trace、§9 = WIN-11 (#2880) の要約 (全文は `REPORT_APPENDIX_2880.md`) |
| `tools/gui/flengine/REPORT_APPENDIX_2880.md` | ~87 | flengine #2880 (WIN-11, 部分達成): `CreateFruityInstance` の `EnterCriticalSection` の失敗 CS (`0x12bd390`)・boot の停止 (`unreachable`)・init 列の登録と解放の対の実測。REPORT_APPENDIX §9 の全文 (測定 commit `ae963e28`) |
| `tools/gui/REPORT.md` | ~235 | gui-shim (Win32 user32/gdi32 → OffscreenCanvas)。§9 = GUI-4 (#180) の要約 (全文は `REPORT_APPENDIX.md`)。§10 = GUI-5 (#181) 24/8/4/1bpp DIB・mono DDB と wasm SIMD128 行カーネルの実測。§11 = GUI-9 (#186) FreeType テキスト (要約のみ・全文は `REPORT_APPENDIX_B.md`)。§12 = GUI-12 (#489) headless host surface 画素 UAF の修正と 50 回連続 + ネガコン。§13 = GUI-13 (#615) gui_wasm.sh への FreeType 組込み + ブラウザ上テキスト描画 e2e。§14 = GUI-7 (#183) popup/tooltip z 順・NC 領域・無効領域複数矩形・DPI (FL 非依存部; 要約のみ・全文は `REPORT_APPENDIX_C.md`)。§15 = GUI-8 (#184) e2e の agent-browser/puppeteer 載せ替え・長時間ストレス・Firefox 取込み (要約のみ・全文は `REPORT_GUI8.md`)。§16 = GUI-5 続き (#181) e2e 全体の全試行と wasm shim 全体の SIMD/scalar 比較 (要約のみ・全文は `REPORT_APPENDIX.md` §16)。§17 = GUI-6 (#182) 入力品質 (キー配列 US/DE/FR・IME・タッチ/ZOOM・Pointer Lock/ClipCursor; 要約のみ・全文は `REPORT_APPENDIX.md` §14) |
| `tools/gui/REPORT_APPENDIX.md` | ~222 | gui REPORT の付録。§9 = GUI-4 (#180 WebGL2 present / 複数矩形 / rAF / seqlock) 全文 (250 行上限のため無変更で分割移動)。§14 = GUI-6 (#182 入力品質: キー配列 US/DE/FR・IME・タッチ/ZOOM・Pointer Lock/ClipCursor) の仕様・検証表・ネガコン実測・範囲外と起票先。§16 = GUI-5 続き (#181): RetDec 付き e2e.sh 全体の全試行と wasm shim 全体 (API 単位) の SIMD128/scalar 比較 |
| `tools/gui/REPORT_GUI8.md` | ~35 | GUI-8 (#184): e2e の agent-browser/puppeteer ドライバ載せ替え・50,000 フレーム長時間ストレス・ネガコン 3 本・Firefox 取込み (REPORT §15 の要約からの参照先・新規記述) |
| `tools/gui/REPORT_APPENDIX_B.md` | ~28 | gui REPORT §11 (GUI-9 #186 FreeType テキスト) の全文 (250 行上限のため無変更で分割移動)。§13 (GUI-13 #615) の追補 (c4b293d の再確認・RetDec 不在のブロッカー実測) |
| `tools/gui/REPORT_APPENDIX_C.md` | ~42 | gui REPORT §14 (GUI-7 #183 popup/tooltip・NC・複数矩形・DPI) の全文 (250 行上限のため無変更で分割移動)。§14 内の検証表 (HEAD 63cfe0f / 67d5cb7 / 87c20fc 等) を含む |
| `tools/gui/shimx_coexist/REPORT.md` | ~110 | shimx weak × gui 強定義の共存リンクと Web 実装接続 (ShellExecute/ファイルダイアログ/D&D) (#172) |
| `tools/audio/REPORT.md` | ~100 | ASIO/WASAPI/DirectSound → AudioWorklet + SAB リング |
| `tools/audio/REPORT_MIDI.md` | ~65 | AU-3 (#188) Web MIDI shim の検証全文 (REPORT.md §13 から分割) |
| `tools/audio/REPORT_AU10.md` | ~30 | AU-10 (#191) 30 分ソーク (`--soak30`) の検証全文 (REPORT.md §16 から分割) |
| `tools/audio/REPORT_AU6.md` | ~38 | AU-6 (#190) 遅延ポリシー: T の減衰の全文 (REPORT.md §17 から分割)。減衰テスト・quick 全体の実測値の正本 (§2) |
| `tools/audio/REPORT_AU2_CI.md` | ~195 | AU-2 (#187) CI 代理指標: Chrome 行列 (2 回目 run・null-sink 接続確認済み・NC・再採取 n=1 の FAIL 1 件・§8 の clock_jump 差分)、Firefox 行列 (WebDriver BiDi, §9・AU-23 #2540)、未解決 (§4・§6)。1 回目 run の記録は §1 (§5 で解消)。quick ベースライン 43/44。実機分は [AU-22] (#2366) |
| `tools/audio/REPORT_APPENDIX_863.md` | ~20 | AU-15 (#863) 現 HEAD (`2f235a0a`) での再試行 15 run 全 PASS の全文 (REPORT.md §20 から分割移動。250 行上限のため)。§19 (旧 HEAD の失敗 1 件) は REPORT.md 本体 |
| `tools/audio/asio/REPORT.md` | ~200 | IASIO COM アダプタ + 120s soak |
| `tools/audio/asio/REPORT_APPENDIX_998.md` | ~23 | asio REPORT §12-2 全文 (#998 負荷下の再現試験 L1〜L3)。250 行上限のため無変更で分割移動 |
| `tools/audio/asio/REPORT_APPENDIX_2777.md` | ~115 | asio #2777 (#998 残件): 初期目標充填 T (burst probe 由来の depth 4/6) と com_ramp_b256_d2 underrun の実測 16 回・全 e2e (測定 commit `e137c4a8`)。測定値の正本。対処は #2934 ([AU-26]) |
| `tools/audio/wl/REPORT.md` | ~75 | AU-8 (#194): ring 方式 vs worklet 直走行の遅延比較 (テスト音ミキサ代役) + FLEngine スレッド/待機面の静的見積り |
| `tools/assets/REPORT.md` | ~125 | 314MB 級 wasm asset の chunk ローダ + 二段キャッシュ |
| `tools/assets/wvfs/REPORT.md` | ~145 | 書込可能 OPFS VFS |
| `tools/assets/serum2/REPORT.md` | ~70 | SR-6 (#70): Serum 2 コンテンツの manifest + LazyVfs 配信 + wasm libFLAC 復号の node 層 e2e (検証範囲と未解決) |
| `tools/assets/deploy-manifest/REPORT.md` | ~60 | 配備 manifest 生産側 (05-stage 契約) |
| `tools/python/REPORT.md` | ~250 | CPython wasm + flapi/MCP 解析 + ブリッジ設計。§7c (ilmcp, PY-3 #82)・§9 (下流チケット案 T1〜T9) は要約のみで全文は `REPORT_APPENDIX.md` に、§PY-12 (#587) は要約のみで全文は `REPORT_PY12.md` に、§PY-13 (#588)・§12/§13 (#81 kwargs 署名の静的復元)・§14 (#79 Piano roll) は要約のみで全文は `REPORT_APPENDIX.md` に、§15 (#654 PY-16) は要約のみで全文は `REPORT_PY16.md`、§16 (#653 PY-15 省略引数) は要約のみで全文は `REPORT_PY15.md` に分割 |
| `tools/python/REPORT_CHROME.md` | ~55 | python REPORT §14b: Piano roll scripts の Chrome (headless, agent-browser) 上の実行と node との出力一致 (#466 PY-11)。250 行上限のため分離 |
| `tools/python/REPORT_PY41_APPENDIX.md` | ~165 | PY-41 REPORT の付録。`REPORT_PY41.md` の PY-49 (#1828)・PY-52 (#1875)・PY-64 (#2033)・PY-88 (#2788) の節の全文 (250 行上限のため分割移動) |
| `tools/python/REPORT_PY159.md` | 134 | PY-159 (#3086): PY-88 の 65 件の `[rbp+0x5b8]` 書込みの全件表 (VA・式・未確定印)。手計算突合 (SLOT 非依存の 7 件) とネガティブコントロールを実施。結果は `REPORT_PY159.md` §4。残りの SLOT 依存 55 件と ACC 合流は #2874 (PY-99) |
| `tools/python/REPORT_PY56.md` | ~70 | PY-56 (#1934): playlist 38 関数のうち `selectTool` (書式 `i`)・`scrollTo` (書式 `iiii`) の引数確定。残り 36 関数は子 #1971 (PY-57) |
| `tools/python/REPORT_PY57.md` | ~75 | PY-57 (#1971): playlist 残り 36 関数のうち 8 件の逆アセンブル骨格 (戻り値・範囲 code は未確定)。未読 26 件は #2026 (PY-61) |
| `tools/python/REPORT_PY61.md` | ~130 | PY-61 (#2026): playlist 未読 26 関数の引数・戻り値の型・範囲 code を VA 付きで確定。`-4` ↔ `RANGE` は文言で対応 (数値は非対応)。操作コアと残り helper は子 #2809 (PY-91) |
| `tools/python/REPORT_PY113.md` | ~100 | PY-113 (#2943): playlist.setTrackColor の格納式を VA 付きで確定 (R/B 入替え + `0xffffff` で `+0x2c` へ)。getTrackColor との食い違いの原因 (C 側の素通し格納) と修正。テスト期待値は子 #2949 (PY-114)、mixer 側は子 #2951 (PY-115) |
| `tools/python/REPORT_PY91.md` | 181 | PY-91 (#2809): playlist 操作系 inc 4 件の更新式・getLive 系の状態 helper・書式 5 件を VA 付きで確定。trigger・zone のコア本体、時間変換、solo/select の副作用、例外型は子 #2906・#2908・#2909 |
| `tools/python/REPORT_PY124.md` | 88 | PY-124 (#2999): general.saveUndo の書式 `si\|i`・kwlist・既定値 updateHistory=1・戻り値 None・準備不可 -2 (文言付き例外か None かは未確定の報告判定に依存)・核の job 配置を VA 付きで確定。履歴 record の本体 (`0x101b780`・`0x1016ca0`) は子 `[PY-137]` (#3026) へ |
| `tools/python/REPORT_PY115.md` | ~100 | PY-115 (#2951): mixer.setTrackColor の格納先 (track 要素 +0 フラグ・+4 値、`swap_rb(v)|0xff000000`) と mixer.getTrackColor の取得式を VA 付きで確定し、C/mock を合わせる。フラグ無し track の既定色は実行時値で未確定 (子 #2975 PY-118) |
| `tools/python/REPORT_PY109.md` | ~100 | PY-109 (#2919): 静的版 subinterp の 12 check を headless Chrome で実行 (wasm32 は 12/12 PASS・node 版と一致、MEMORY64=1 は 11/12)。失敗 1 件 (反復で線形メモリが増える) は #2918 へ |
| `tools/python/REPORT_PY58.md` | ~57 | PY-58 (#1973, 部分・未達): `+0x794` 書込み候補 16 件の分類 (chan ではないと判断 11・保留・未確定 4)。chan 上の書込み元は未特定 |
| `tools/python/REPORT_PY66.md` | 70 | PY-66 (#2078, 部分・未達): `+0x794` の未確定 2 件 (`0x1306dbf`・`0x130760f`) は同一 global `0x196eba0` 経由と確定。その書込み元と chan の対応は未特定 |
| `tools/python/REPORT_PY67.md` | 242 | PY-67 (#2159, 部分・未達): `0x196eba0` (g) への書込み元を `0x86a4e1` (関数 `0x86a470`) と特定。PY-71 (#2501, §5): g の値 P の型 (TGraphEditorForm) と `0xffe370` の所属 (TPublicChannel) を特定 (値は REPORT_PY71.md)。受入条件 2b・3・4 は子 #2701 |
| `tools/python/REPORT_PY67_2159.md` | ~100 | PY-67 (#2159) 3 回目: 受入 3 (`0xec60ae` の対象) を TPlugListForm (非 chan) と確定し除外。受入 4 (`0x8ed012` の Self の出所) は呼出し元 5 件を列挙し未確定。残りは子 #2701 |
| `tools/python/REPORT_PY71.md` | ~95 | PY-71 (#2501, 完了単位 1・2a): VMT (RTTI) の配置を 3 クラスで検証 (ネガティブコントロール 6/6 NG)。受入 1 (P = TGraphEditorForm・非 chan。全親鎖を実測)・2a (`0xffe370` = TPublicChannel のスロット 52、親 TChannel) を確定。2b (`call [reg+0x1a0]` 37 件の受け手)・3・4 は子 #2701 へ移した |
| `tools/python/REPORT_PY116.md` | 105 | PY-116 (#2952): flapi 表の kwlist 無し引数 (flags=1) の書式を wrapper の出力ポインタ数と照合 (304 件中 302 件一致。`screen.addTextLine`・`screen.addMeter` の 6 個目は解析されない余剰で、表の個数 5 は正)。`plugins.getPresetCount` は kw 形式の唯一の flags=1 として書式 `i\|ii` を照合 (表の kwsig 1 件のみ変更)。名前の新規確定 0 件 (未確定 42 位置は `arg{i}` のまま) |
| `tools/python/REPORT_PY123.md` | 122 | PY-123 (#3028): boot 停止時点 (unit 209) の undo 管理 global `0x15e1c78`・安全判定 global `0x15e4790`・singleton `0x16b82e0` が全て 0 (shim 有無で同じ)。敷設直後は PE 値 (`0x16bb068`・`0x141d6b8`) を読めるが、boot 本体の途中で 0 に戻る (戻す箇所は未特定) |
| `tools/python/REPORT_PY12.md` | ~46 | PY-12 (#587): `_flhost` の per-module state 化・サブインタプリタ採用判断の実測 (REPORT.md の PY-12 節の全文。250 行上限のため分離) |
| `tools/python/REPORT_PY31.md` | ~50 | PY-31 (#1329): mixer 残り 57 関数の扱い決定 (今回非実装・根拠は MCP 利用 0 件と mock 定義 0 件)、未実装 57 件の一覧、分割先 #941、検証 (provider_check / mixer_diff / all_tools) |
| `tools/python/REPORT_PY39.md` | ~220 | PY-39 (#1527): channels 操作 7 関数の PE ハンドラ位置・PyArg 書式・引数の確定。他関数の戻り値・範囲外 code は未確定。`analysis/flapi/pe_handler_probe.py` の測定と selectAll 等 4 件の表エントリの扱い。PY-69 節は `REPORT_PY69.md`、#2548 の節は `REPORT_PY39_2548.md`、8 回目 run 節は `REPORT_PY39_2668.md` へ分割移動 (250 行上限) |
| `tools/python/REPORT_PY69.md` | ~109 | PY-69 (#2499): `selectOneChannel` の PE 意味論。排他選択 (`0x11e84a0`→setter `0xff8a90`)・stack 引数の出所・前提ゲート `0xd5af58`・後段ゲート `0xd82c6a`・選択ゲート `0xffac20` の読解と未解決 ([PY-82] #2642)。`analysis/flapi/pe_scan_store.py` の書込み箇所列挙 |
| `tools/python/REPORT_PY39_2548.md` | ~80 | PY-39 追補 (#2548): setStepParameterByIndex の呼出し経路・status 表 (範囲外 `-4`)・param 3〜8 の副作用を PE で確定 (REPORT_PY39.md の節の分割移動)。param 0〜2・item 列挙・述語の型は未確定 (子 #2581) |
| `tools/python/REPORT_PY39_2668.md` | ~100 | PY-85 (#2668): channels.selectAll の選択値 `*p` (`0x154528c`) の書込み元 4 関数の所属関数と、selectAll 閉包 (直接 call・566 関数) からの非到達 (間接 call 191 箇所は未解決)、段 6 の status → 例外文言の写像 (`0xd82c20`) を PE で確定。選択値・ゲートは未確定 (実装なし)。測定は `analysis/flapi/pe_callgraph.py` (直接 call 元の逆引き `callers` を含む)。8 回目 run 節 (REPORT_PY39.md からの分割移動) を含む |
| `tools/python/REPORT_PY41_1514.md` | ~75 | PY-41 追補 (#1514): channels.getChannelType を公開 stub の型定数 (CT_Sampler 0・CT_GenPlug 2) で実装した根拠と測定。残り 12 関数の分割 (子 #2805・#2808 と #1514 に残す 6 関数) |
| `tools/python/REPORT_PY118.md` | ~86 | PY-118 (#2975): mixer.getTrackColor の既定色の初期値 `.bss` 0x15f6774 = `0xff636c71` を逆アセで確定 (初期化 0x770830 / 0x770ba6・取得核 0x12c18f0・wrapper 0xd5ec60)。実行時の間接書込み (0x111ed10 → 0x78b8e0 → 0x783810) と flpy 部の未実行は #3059 (PY-157) に残す |
| `tools/python/REPORT_PY110.md` | ~112 | PY-110 (#2927): flapi 表の引数個数を FLEngine 書式 (kwsig の required/max) に合わせ、stub と不一致の 24 関数を 0 件にした生成器 `pe_arity` の規則・個数検査 `tests/sig_arity_probe.mjs`・未解決 (子 #2950・#2952) |
| `tools/python/REPORT_PY70.md` | ~95 | PY-70 (#2500): flapi 表の生成器が stub の位置専用引数 (`/`) を読み落としていた不具合の修正 (`channels.processRECEvent` 0→3 引数)。引数個数が変わった 15 関数と未解決 (stub/PE の個数不一致 24 件) の一覧。残りの 4 関数の意味論は子 #2544・#2547・#2548 |
| `tools/python/REPORT_PY35.md` | ~61 | PY-35 (#1345): patterns 未実装 31 関数の意味論は repo 内に根拠無し (実装 0・コード変更 0)。読み取り 14 件 #1667 (PY-42)・選択/移動/書き込み 17 件 #1668 (PY-43) に分割 |
| `tools/python/REPORT_PY40.md` | ~90 | PY-40 (#1529): channels グラフ/CS エディタ系 5 関数 (closeGraphEditor / updateGraphEditor / showGraphEditor / showCSForm / focusEditor) の PE 解析。引数形式・内部経路・callback は確定、範囲外 code と戻り値は未確定 (実装は保留)。親 #1515 |
| `tools/python/REPORT_PY38.md` | ~80 | PY-38 (#1525): channels の reroll 3 関数 (rerollLoopStarter{Loop,Sample,Steps}) / setSwing / getSwing の PE 上の位置・引数書式・index -1 の扱い・値の変換式 (実装なし)。未確定は helper `0x1046a30` と status 写像。親 #1515 / 分割先 #1554 |
| `tools/python/REPORT_PY72.md` | ~145 | PY-72 (#2542): channels.setChannelPitch (`0xd5aa30`) の PE 意味論。書式・委譲 `0xd843d0`・callback `0xd5a720` の判定順 (index → NaN 検査 → pitchUnit 0/1/2)・status → 例外文言 (-1/-2/-3/-4)。効果関数・guard・一覧 A/B・N の既定値は未確定 (実装なし)。測定は `analysis/flapi/pe_disasm.py`・`pe_rip_consts.py`。「追加解析 (PY-75 / #2562)」節 (callback `0xd5a720` の guard・値検査・pitchUnit 0/1/2、効果関数 `0x1051d20` の 7 引数。本体の未確定は子 #2576 [PY-77]) を含む。REPORT_PY39.md の 250 行上限のため分離 |
| `tools/python/REPORT_PY73.md` | 250 | PY-73 (#2547・途中記録): channels.incEventValue (`Ii|d`) の戻り値の型 (flags bit1 で int / float ビット列)・`0x1051330` 本体の範囲外 code (例外経路なし)・本体の副作用 (スタック書込みのみ) を PE で確定 (§7)。事象表は eventId の初回参照で要素を作る遅延キャッシュと確定 (§8)。事象 flags の分類器 `0x104d0d0` の PE 確定 (§9): B 経路 (A 以外) の flags は 0x00/0x04 のみ。未確定は A 経路の flags (getter)・`0x1046a30` の lo・hi・cur・表挿入 `0x664090` (子 #2887) と channels.midiNoteOn (`iii|i`) の副作用。文言は `analysis/flapi/pe_errmsg_probe.py`、参照箇所は `analysis/flapi/pe_xref.py`、RIP スロットの実バイトは `analysis/flapi/pe_flag_slots.py` で再現 |
| `tools/python/REPORT_PY73_APPENDIX_2817.md` | ~85 | PY-93 (#2817・部分): `0x11d1430` のゲート参照鎖 (G3 → スロット → Q → T)・T の書込み元 2 箇所・T の vptr (`0x125b1c0`。`0x40fb40` の `mov [rsi],rdi`)・vtable 先 `0x1262a90`・-2 ゲートの条件 (フラグ 3 byte の実行時値は未確定)。測定は `analysis/flapi/pe_slot_writers.py` で再現。`REPORT_PY73.md` §8-4 の付録 |
| `tools/python/REPORT_PY73_APPENDIX_2547.md` | ~65 | PY-73 (#2547・5 回目 run・縮小後の受入 1 の付録): `0x1046a30` (lo・hi・cur の共通 getter) の eventId 種別振り分け表 (`0x1047424` の compare チェーン 7 分岐先・根拠 VA 付き)、mode `0x240` の直行条件、`0x10476f9` 系の mode 0x20 経路。RetDec の `return` 誤読の注意。値源は #2887 (PY-103)。測定は `analysis/flapi/pe_disasm.py`・`analysis/flapi/pe_retdec.sh` で再現 |
| `tools/python/REPORT_PY74.md` | ~50 | PY-1 ilmcp 意味論の整合 (#74, PR #763): getBrowserNames 木・getHighlightNames 21 件・addChannel/addEffect/storePRScript 検証の実測表、`tests/ilmcp_diff.mjs` の結果、NC (addEffect 検証を外して 2 件差分)、非 ASCII 空白の未解決。REPORT.md §7b-3 の実測表の全文 |
| `tools/python/REPORT_PY8.md` | ~45 | PY-8 (#80): MIDI 1 イベント flapi 呼出し数・所要時間と遅いモード切り分け (REPORT.md の分割ではなく新規。250 行上限とは無関係) |
| `tools/python/REPORT_PY100.md` | ~150 | PY-100 (#2879): channels.getStepParam・getCurrentStepParam の PE 確定 (書式 `iiii\|i`/`iii\|i`・kwlist・padsStride 既定 16・`[global]` = patternNumber と同じ slot・param 0〜8 の写像・-1/-3/-4 の経路) と C provider・mock の実装、`channels_diff` diffs 0 (実測は REPORT_PY100 §11)。構造体 (note) の生成経路と既定値は未確定 (子 issue) |
| `tools/python/REPORT_PY84.md` | ~183 | PY-84 (#2663): fl-win64 の DATA block から chord progression の pyscript 2 本 (cpt / stack) と drum_patterns.json を抽出する同定規則 (内容一致・件数 fail-closed)。e2e 41/41 PASS (3 回)・NC・所要/load。run_all 全体は fl-win64 と toolchain-emsdk だけで rc=0 (`41d9c3b9` で実測、mac 側 step は SKIP) |
| `tools/python/REPORT_PY15.md` | ~130 | PY-15 (#653): 省略引数のホスト受け渡し方式・kwlist 103 関数の誤束縛 0 検証・挙動変更の内訳・ネガコン (REPORT.md §16 の全文。250 行上限のため分離) |
| `tools/python/REPORT_APPENDIX.md` | ~216 | python REPORT の分割移動節の全文: §7c (ilmcp 9 関数 PY-3 #82: 引数規約・検証・仮定・未解決)・§7b-2 (ilmcp.getBrowserNames 固定バッファ修正 #74 の全文)・§9 下流チケット案 T1〜T9・§PY-13 (build_flpy.sh の env 化 #588)・§12/§13 (PY-9 b kwargs 署名復元・wasm 回帰・未解決 #81)・§14 (Piano roll scripting #79 の全文) (250 行上限のため無変更で分割移動) |
| `tools/python/REPORT_PY97.md` | 129 | PY-97 (#2856 / 親 #2633, REPORT_PY80.md §4 の子): `--enable-wasm-pthreads` の静的版 `flpy_static_pthread` の rc 0 リンク、単一スレッド 48 tool が stock と 0/48 差、2/4 スレッドからの同時 tool 呼出しが基準と 104/104 一致 (§9 で main 取り込み後に再測定)。#2633 の記録は REPORT_PY80.md |
| `tools/python/REPORT_PY2.md` | ~221 | PY-2 (#83/#115, REPORT §7d 本体の全文): CPython と flapi provider の同一 wasm 静的リンク・往復コスト・`Py_*` 動的束縛 110 名の対応表・スレッド/GIL 方針。§7f (PY-81 #2634): 静的版の Worker 内実行と headless Chrome での SAB 版との 48 tool 比較・run_all.sh 全体の未達理由。§7g (#2649): fl-win64 + toolchain-emsdk だけの run_all.sh rc=0 (本体は付録 `REPORT_APPENDIX_2649.md`) |
| `tools/python/REPORT_APPENDIX_2649.md` | ~142 | python REPORT §7g (#2649 run_all.sh を fl-win64 + toolchain-emsdk だけで rc=0 にする) の全文。main 取り込み後の再測定 (HEAD `6bec0214`、step 別所要・負のコントロール・未解決) (250 行上限のため分割移動) |
| `tools/python/REPORT_APPENDIX_2858.md` | ~114 | PY-98 (#2858): main の経路 (`build_cpython_wasm64.sh`) で作った MEMORY64=1 の静的版 `flpy_static64` を headless Chrome で読込・smoke 実行 (validate・init・print・subinterp 1+160 回・heap 測定) と負のコントロール。旧経路 (撤回) の測定は git 履歴。MEMORY64=2 の heap 増加は子 #2918、12 check 版は子 #2919 |
| `tools/python/REPORT_APPENDIX.md` | ~50 | python REPORT §PY-13 (build_flpy.sh の env 化 #588) と §12/§13 (PY-9 b kwargs 署名復元・wasm 回帰・未解決 #81) の全文 (250 行上限のため無変更で分割移動) |
| `tools/python/REPORT_PY16.md` | ~100 | PY-16 (#654): stubs 既定値 `midi.*` の評価 (eval 撤去・許可式の評価器・検証・ネガコン) の全文 (REPORT.md §15 の分割移動) |
| `tools/python/REPORT_PY80.md` | 93 | PY-80 (#2633): 静的版 (flpy_static) のサブインタプリタは達成。Memory64 は部分 (validate は node 22.23 で不可・headless Chrome 154 で可、実行検証は未了)。`_PyInterpreterState_GetRefTotal` は FL PE が呼ばない。結論の正本は REPORT の結論表。pthread+GIL は子 #2856 (PY-97)、Memory64 実行は子 #2858 (PY-98) |
| `tools/python/REPORT_PY27.md` | ~70 | PY-27 (#1138): ui / general / screen / arrangement / launchMapPages の mock 対応状況・`tests/ui_diff.mjs` の結果・保留 150 件 |
| `tools/python/REPORT_PY87.md` | ~61 | PY-87 (#2738): general の状態読出しゲッター 4 件 (getChangedFlag / getUseMetronome / getPrecount / getRecPPQ) の PE 根拠・mock/C 差分 0・値は未実測の仮置き。残り 146 件は #2830・#2831・#2832 |
| `tools/python/REPORT_PY96.md` | ~88 | PY-96 (#2832): arrangement の選択範囲読出し 4 件 (selectionStart / selectionEnd / liveSelectionStart / selectionIsActive) の PE 根拠 (変換スロット 0x15e4280 は PY-87 と同じ)・mock/C 差分 0・値は未実測の仮置き。残りは親 #2832 の子 #2984・#3021・#3022・#3025・#3041 |
| `tools/python/REPORT_PY152.md` | ~203 | PY-152 (#2983): arrangement 8 件のうち 6 件 (currentTime / addAutoTimeMarker / jumpToMarker / liveSelection / selectionClear / selectionSet) の PE 根拠・mock/C 差分 0・値と副作用は未確定。jumpToMarker の必須個数は PE (1) と表 (2) が不一致で PM 判断待ち。変換スロット 0x15e4280 = PyLong_FromLong を同定。残りは子 #3041 (PY-143)・#3043 (PY-144) |
| `tools/python/REPORT_PY120.md` | 120 | PY-120 (#2981): ui の操作・キー・ジョグ・編集 27 関数の PE 呼出し契約 (書式・既定値・op code・経路)。PE 確定 0 件 (作用先・戻り値の値が未確定) で保留。0xd81740 は関数ではなく型記述子、0x15e1e58 は PyArg_ParseTuple スロットと訂正。mock/C 差分 0 (実装なし) |
| `tools/python/REPORT_PY119.md` | ~87 | PY-119 (#2980): ui の状態・フォーカス・文字列ゲッター 6 件 (getFocused / getFocusedFormID / getFocusedFormCaption / getFocusedPluginName / getHintMsg / isInPopupMenu) の PE 根拠・mock/C 差分 0・値は仮置き。保留 12 件は #3005・#3006・#3007 |
| `tools/python/REPORT_PY119_2977.md` | ~100 | PY-119 (#2977): general の setter 6 件 (setRecPPQ / setNumerator / setDenominator / setUndoHistoryPos / Count / Last) の PE 確定 (範囲・status 文言の VA・undo 書込み先)・mock/C 差分 0・ゲート (G = 0x15e4790)・例外型・既定値は未確定 (親 #2830 にコメント)。解析補助 `analysis/flapi/pe_cstr.py` |
| `tools/python/REPORT_PY121.md` | 72 | PY-121 (#2979): general の log・rec 系 4 件 (clearLog・dumpScoreLog・processRECEvent・getRecPPB) の PE 根拠 (entry・fn VA・書式・呼出し鎖)。戻り値の意味は未確定で実装なし。残りは #3001・#3002・#3003 |
| `tools/python/REPORT_PY121_2985.md` | 89 | PY-121 (#2985): screen 状態の 5 関数 (isBlanked / isUnBlank / getScreenActiveCounter / setScreenActiveCounter / unBlank) の PE 根拠・mock/C 差分 0 (int・bool・float・str の入力まで)・値は未実測の仮置き。残り 23 件は子 #3021 (PY-134)・#3022 (PY-135)・#3025 (PY-136) |
| `tools/python/REPORT_PY23.md` | ~85 | PY-23 (#1054): `enveditor` (Edison API・仕様は block24447) の実装と Audio scripts 12 本の import/実行検証。数値 oracle 6 本・NEG-d・未解決 |
| `tools/python/REPORT_PY19.md` | ~57 | PY-19 (#792): `Score.loadScoreFromFile` (仮想 FS・JSON) と `ScriptDialog.DialogParams` (MOCK)・数え方の定義 (母集団 64) と再計算・実測・未解決 |
| `tools/flp/REPORT.md` | ~120 | FLP/FST パーサ・ライタ・往復コーパス |
| `tools/plugins/REPORT.md` | ~115 | Fruity プラグイン 141 種 wasm 化マップ (カウントの正本) |
| `tools/plugins/f2/REPORT.md` | ~250 | PLG-F2 eq-filter 11 本: 固有閉包 lift の再現と間接 call 脱落の監査 (#199)、icall 復元の batch_lift 接続と回帰ゲート (#514, §7)、leaf 23 関数の関数単位差分試験の結論 (#515, §8)、xmm 引数復元 pass の結論 (#547, §9)、ldfix の接続 (#613, §10)、0x6f1650 の原因切り分け (#871 部分, §10.1)。§8・§9 の詳細は `REPORT_APPENDIX.md`、§10 (#613) の全文は `REPORT_APPENDIX_613.md`、§10.1 の詳細は `REPORT_APPENDIX_871.md`、§11 (#2726: 残 6 関数の原因・pass on/off の ablation 再定義) は `REPORT_APPENDIX_2726.md` |
| `tools/plugins/f2/REPORT_APPENDIX.md` | ~241 | f2 REPORT §8 全文 (PLG-F2-3 #515: 23 関数表・ARTIFACT 表・NC 詳細・限界・再現・実測時間) と §9 全文 (PLG-F2-4 #547: xmm 引数復元 pass の実測と未解決)。250 行上限のため無変更で分割移動 |
| `tools/plugins/f2/REPORT_APPENDIX_871.md` | ~15 | f2 REPORT §10.1 全文 (PLG-F2-6 #871 部分: 0x6f1650 の原因切り分け = image 配置と絶対 VA 定数のずれ、確定。修正と残 5 関数は未解決で #871)。検証 HEAD `9c6f8c91` |
| `tools/plugins/f2/REPORT_APPENDIX_613.md` | ~30 | f2 REPORT §10 全文 (PLG-F2-5 #613: `ldfix` の接続 (opt-in `PLUG_LDFIX=1`)、受入 1 未達・受入 3 部分判定)。250 行上限のため無変更で分割移動 (#2726)。末尾に #2726 の追補節 |
| `tools/plugins/f2/REPORT_APPENDIX_2726.md` | ~108 | f2 REPORT §11 全文 (PLG-F2-8 #2726: 残不一致 6 関数の原因 (no_placeholder / slot_occupied / 引数の割当て)、`p.xa.json` の skip 理由の数値、pass on/off の ablation 再定義 (IR 差分と判定)、0x6b0ef0・0x6ca5c0 の xmm1・xmm3 が届かない経路、再現)。子 #2850、起票先 #2762 |
| `tools/plugins/f2/REPORT_APPENDIX_514.md` | ~75 | PLG-F2 (#514) icall waiver 18979 0x741035 の機械検証: `waiver_proof.py` の V1〜V5 (参照の一意性・間接 jmp・フレーム書込み・述語の int32 全数評価)、ネガコン (jae→jb・cmp 0x14) の DETECTED、全数検査 540 s の実測。測定 commit `8eddfb09` |
| `tools/plugins/f2/REPORT_2492.md` | ~100 | PLG-F3-29 (#2492): `fptr_callers.py` の VA 自身の参照検索の追加 (0x407a20 は 4 種すべて 0 件)、ネガティブコントロール (`.data` 0x867e78 に 0x407a00・0x407a20 を埋めた PE)、capstone 非依存の生バイト検算 `rawref_scan.py`。PLG-F3-29 の正本 (REPORT_1305.md は 250 行上限に達したため本件の節を置かず、本ファイルを指す)。測定 commit 5c25928b |
| `tools/plugins/f2/REPORT_APPENDIX_2468.md` | ~150 | f2 PLG-F3-28 (#2468 受入 1 達成・残件は #2574): 0x5da070 の間接 call 先 (= [0x28]・this=NULL) の実測、NULL this の連鎖 (0x5d9f50 ← 0x83cbbe ← グローバル [0x8cd068] = 0、slot 0x8bd7f8 経由の読取り)、`-z` による書込み違反の位置 (0x412613)、DllMain 経路の 0x8c3ca8 最終値。測定 commit `62636cd4` |
| `tools/plugins/reverb_delay/REPORT.md` | ~246 | PLG-F4 reverb-delay 9 本: 固有閉包 lift・gate 付き e2e・host/kernel/IPP 依存・T3 engine の到達性 (#201)。§12 に #523 追補 (engine 再測定・E6 修復)、§13 の詳細は `REPORT_APPENDIX.md` |
| `tools/plugins/reverb_delay/REPORT_APPENDIX.md` | ~37 | reverb_delay REPORT §13 全文 (#523 追補): engine 19000 (`PLUG_F80_LOWER=1`) と 19165 (IPPCODE + AVX 78 除外) の再測定表、19165 の segfault と新類型 E7 (f80 ビット操作の lowering 漏れ)、再現手順、#523 受入条件への対応。§12 との run の違いを明記 |
| `tools/plugins/modulation/REPORT.md` | ~247 | PLG-F5 modulation 8 本: 固有閉包 lift の再現・exit code 付き判定・間接 call 脱落の判定・閉包境界 (frontier の先) の監査・C++ engine 4 本の到達性 (#202)。§4.1 に殻と engine の結合方式 (受入 5) の実測 |
| `tools/plugins/modulation/REPORT_APPENDIX_527.md` | ~170 | PLG-F5-2 (#527) の engine 到達性 gate (`engine_judge.py`) の NC と 4 本の判定結果 (§I)、殻の動的ロード呼出の静的特定 (§J、`engine_shell_gpa.py`)、殻の engine 名参照と呼出経路 (§K、`engine_shell_entry.py`。§L で `engine_shell_chain.py` により再確認)、VST 入口解決の経路 (§M: `engine_shell_vst.py`、§N: 名前表 26 件・入口 thunk・関数ポインタ表・GetProcAddress 経路。`engine_shell_ripref.py` / `engine_shell_func.py` / `engine_shell_names.py`)。 |
| `tools/plugins/modulation/REPORT_APPENDIX.md` | ~62 | PLG-F5-2 (#527) の付録。§A〜§F は f80 段 (`p0c/f80_lower.py`) の経緯・失敗内容・実行条件・未実装 helper の経緯。§G は殻と engine の結合方式の結論 1 行 (測定値は REPORT §4.1)。§H は判定 (gate) 設計の表 (REPORT §5 から分割移動) |
| `tools/plugins/hostx/REPORT.md` | ~145 | PLG-X host 統合 / big3p 12 本の方針決定 (lift する 6 / しない 2 / ユーザ判断 4) と閉包 lift の再現・間接 call 脱落の監査 (#210) |
| `tools/plugins/g1/REPORT.md` | ~250 | PLG-G1 synth-simple + drum-synth 14 本: 閉包 lift・host/kernel/間接 call 監査・C++ DLL 7 本・gate とネガコン (#206) |
| `tools/plugins/g1/REPORT_APPENDIX.md` | ~30 | g1 REPORT §9 旧版 (検証起点 86ca2d5、#539 取り込み前の 3 run・NC 詳細) の全文 (250 行上限のため分割移動) |
| `tools/plugins/framework/REPORT.md` | ~207 | TFruityHost shim 実装 (§0-§9・§11)。§10・§12・§13 (検収記録・CAB-269 修正) は `REPORT_APPENDIX.md` に分割移動 |
| `tools/plugins/framework/REPORT_APPENDIX.md` | ~318 | framework REPORT §10 (2026-10-11 検収)・§12 (CAB-194 検収)・§13 (CAB-269 修正) 全文。分割移動のみで内容は変更なし |
| `tools/plugins/framework/REPORT_985.md` | ~50 | PLG-P0b-1 (#985, 部分達成): hs_e2e 判定の是正 (Phase B 例外 = FAIL・誤 PASS の実測) と RTL fold deref の現状。`plug != 0` は未達で子 #1229 へ |
| `tools/plugins/framework/REPORT_2115_APPENDIX.md` | ~50 | framework REPORT_2115 §10 (TLS index 未設定の確認・未採用の stand-in 版の実験・n=1 の実測と対照) を REPORT_2115.md から分割移動 (250 行上限・本文は改訂済み)。測定値の正本 |
| `tools/plugins/framework/REPORT_2571.md` | ~75 | PLG-P0b-22 (#2571): hs_e2e Phase B に TLS 初期化 (`[0x7162d8]=1` → `0x418120`) を CreatePlugInstance の前に通す方式・対照との実測 (n=1)・注釈 `0x4181e0` の判定 (外せない)。Phase B は依然 OOB |
| `tools/plugins/framework/REPORT_2425.md` | ~130 | PLG-P0b-16 (#2425): smoke 判定を InitUnits 完走基準 (`runerr=0 ff=0 init_reach=288`) に再定義し、旧 `dispatch=38` が idx 16 の RunError 終端だった事実・IR の fold 位置 (`function_40ea20` 38146 行〜) と n=3 の実測 (増分 23.94〜24.55 秒) を記録。修復は子へ移管 |
| `tools/plugins/framework/hostshim/REPORT_DISPATCHER_APPENDIX.md` | ~229 | PLG-P0b-24 (#2782): `REPORT_DISPATCHER.md` §10 の詳細表。応答スロット `[rbp+0x11a0]` の書き込み命令 69 件 (A-1)・最後の書き込み 28 行 (A-2)・出口 27 と callee 戻り値への依存 (B-2)・未収載 7 ID の個別結果・スタック埋め感度試験 (`HS_DISP_STACK_FILL`) の実測。REPORT_DISPATCHER.md の 250 行上限のため分割 |
| `tools/plugins/framework/REPORT_2510.md` | ~180 | PLG-P0b-18 (#2510): stage-2 の idx 16 RunError の `"$"` fold の有力な原因を特定 (因果は未確認。BLK 領域 `0x8A1000` が `icall_rewrite.py` の relocate 範囲 `[0x7A1000, 0xD01E8D)` と重なり、RetDec がコードバイトを BLK の `constant` 初期値にする)。修復は未着手 (子 #2565・#2566 へ移管)。上流経路 (stage-1 IR の 4 辺) を §2.1 で特定。n=1 の実測 (5 分 40 秒) と重なりの反事実検査を記録 |
| `tools/plugins/framework/REPORT_P0c9.md` | ~36 | P0c-9 (#610) stage-1 成果物の素材化 (`fw_pack_stage1.sh` pack/verify・`work-fw-stage1` allowlist)。REPORT.md から分割移動 |
| `tools/plugins/framework/REPORT_995.md` | ~130 | PLG-P0c-14 (#995): FW_EXT_FUNCS 指定経路の入力差替え。`hs_e2e.sh` に `HS_WFW` を追加し、ext 版 canon3 で hs_e2e を実行 (Phase B OOB のまま FAIL)。fw_269_verify ext の smoke 検査 gate FAIL (既存 #2510) |
| `tools/plugins/framework/hostshim/REPORT_DISPATCHER_APPENDIX_2886.md` | 130 | PLG-P0b-25 (#2886): Dispatcher 応答スロット `[rbp+0x11a0]` の格納元 19 ID の機械語確定 (VA 付き)・仮想呼出し出口 27 ID の分類 (A 3 / B 13 / C 11)・hostshim 応答表 3 ID 追加と Phase A 回帰 (dispatch=38 PASS)・callee 依存の格納分類 (§3.4。0x40fe90 の数値は `REPORT_DISPATCHER_APPENDIX.md` B-2)・再測定 (§6)。`REPORT_DISPATCHER.md` §11 から参照。新規 (分割移動なし) |
| `tools/plugins/framework/REPORT_2426.md` | ~78 | PLG-P0b-17 (#2426): hs InitUnits の OOB 1 件目 `function_414390` の入力定数化 (`hs_irfix.py` `fix_414390`) の原因・修復・実測と、次の OOB `function_40c4d0` の記録。新規 (分割移動なし) |
| `tools/plugins/p0c/REPORT.md` | ~139 | kernel 表妥当性検証 + f80 assessment (§1〜§7)。§8〜§16 は `REPORT_APPENDIX_A.md`〜`F.md` に分割し、本体末尾に付録索引 (#378) |
| `tools/plugins/p0c/REPORT_APPENDIX_A.md` | ~164 | p0c §8 (P0c-2 CAB-241 f80→f64 lowering)・§9 (P0c-3 CAB-251 x87 スタック模型修復) 全文 (#378 で無変更分割移動) |
| `tools/plugins/p0c/REPORT_APPENDIX_B.md` | ~189 | p0c §10 (P0c-4 CAB-196 ext-emulation mode) 全文 (同上) |
| `tools/plugins/p0c/REPORT_APPENDIX_C.md` | ~203 | p0c §11 (P0c-4 CAB-253 ARG pass ABI 推定強化) 全文 (同上) |
| `tools/plugins/p0c/REPORT_APPENDIX_D.md` | ~159 | p0c §12 (P0c-5 #269)・§13 (P0c-7 #310) 全文 (同上) |
| `tools/plugins/p0c/REPORT_APPENDIX_E.md` | ~222 | p0c §14 (P0c-6 #277)・§15 (環境パス置換 #346)・§15.4 (#360 full e2e before/after) 全文 (同上・§15.4 は main 追記分)。§14.6〜§14.8 (#983・#982・#331 残件の現況) は `REPORT_APPENDIX_E2.md` に分割移動 |
| `tools/plugins/p0c/REPORT_APPENDIX_E2.md` | ~95 | p0c §14.6 (#983 残差 3 kernel の原因と修復)・§14.7 (#982 0x5de3e0 の上位 dword store 復元)・§14.8 (#331 残件の現況) の全文 (`REPORT_APPENDIX_E.md` から分割移動・無変更) |
| `tools/plugins/p0c/REPORT_APPENDIX_F.md` | ~62 | p0c §16 (P0c-8 #311 ext IR の wasm32 検証 + framework 統合) 全文 (同上・E の 250 行上限のため分割) |
| `tools/plugins/dynamics/REPORT_APPENDIX.md` | ~102 | dynamics §E ([PLG-F3-15] #1778): 19252 の残 helper `vmovsd` store の宛先 (spill → B1 の 0 埋め) の原因実測。 方式は DECISIONS D16。 dynamics REPORT §4 の「脱落の原因 (#1412)」の全文 (250 行上限のため分割移動。 静的検出 (`statically linked function`) による `.pdata` define 脱落 208 件の内訳と切替実測) |
| `tools/plugins/sampler/REPORT.md` | ~245 | PLG-G3 (#208) sampler 8 本: lift 前提の実測。 engine lift 鎖の根本原因と `emcc -c` gate・NC。 §2b (#537 推移閉包) は REPORT_INDIRECT.md (#208 / #540) |
| `tools/plugins/sampler/REPORT_APPENDIX.md` | ~60 | sampler REPORT §6 の旧版 (§A 検証起点 53c2eb6、§B 82a99ac/7de96e0、§C 7ffab50) と §D (RetDec C 出力段の経緯) の全文 (250 行上限のため分割移動) |
| `tools/plugins/sampler/REPORT_UNREACHED_APPENDIX.md` | ~37 | sampler REPORT_UNREACHED の分割移動節: §A (§2d-7 の改訂前 b36fef5 系の NC 表)・§B (§2g #879 別案: NC2a/NC2b 合成入力の全文)。 250 行上限のため無変更で分割移動 |
| `tools/plugins/sampler/REPORT_INDIRECT.md` | ~80 | sampler REPORT §2b の付録: #537 推移閉包 (間接呼出の到達先) の算出・lift・ネガコン |
| `tools/plugins/sampler/REPORT_APPENDIX_1582.md` | ~12 | sampler REPORT §7b の分割移動節の全文 ([PLG-F3-12] #1582: engine_lift の実測 19252/19048・19048 の `emcc -c` 回帰の疑い・VEX comis/ucomis の flag 方式の検討 2 案)。 方式の決定は DECISIONS D15 |
| `tools/plugins/sampler/REPORT_ENGINE_LINK.md` | ~55 | sampler REPORT §5 の付録: Fruity Slicer 2 殻 (23663) と engine (23664) の結線。 `engine_x64.dll` のロード経路・`DispatchToEngine` の case 表 (#540 受入条件 4 の部分達成) |
| `tools/plugins/sampler/REPORT_ENGINE_LINK_APPENDIX_3009.md` | ~148 | REPORT_ENGINE_LINK §10 の (a)(b)(c) の再解析 (#3009): sel 2・4 の戻り値 (sel 2 は常に 0、sel 4 は int32・bool・`const char*`)、wrapper の呼出し元 (sel 2 11 件・sel 4 12 件・0x843930 6 件。 付録 540 の件数の訂正)、0x84bd8f の内側 id {3,7}、0x84bc30 の参照 (8 byte 絶対 VA で `.text` 内の表 1 件・参照元は未確定)。 検証は `dispatch_selectors.py` (NC 付き) |
| `tools/plugins/sampler/REPORT_ENGINE_LINK_APPENDIX_540.md` | ~64 | REPORT_ENGINE_LINK §10 の分割移動: #540 受入条件 4 の残り (a)(b)(c) の再解析 (sel 2・4 の呼出し元 17 件と内側 id の表)。 §11: 受入条件 5 (VEX の SSE 固定) の静的判定 (vex_reach.py・vex_pin.py の実測)。 §12: 固定後の VEX 8 命令の経路 (値依存の NaN 判定分岐・vex_nan_branch.py)。 250 行上限のため別置き |
| `tools/plugins/slayer_x86/REPORT.md` | ~132 | FL Slayer x86 engine (Slayer_Engine.dll) の結合方式 (ilbridge.exe 経由) と lift 方針 (#536) |
| `tools/plugins/slayer_engine_ia32/REPORT.md` | ~238 | FL Slayer x86 engine (block22434 = Slayer_Engine.dll) の ia32 decode 基準値 (#674 中間): 線形掃引の実測・gate C1〜C4・ネガコン N1〜N3・objdump 検算。§9 は AEffect marshal 表の実測 (store 列・gate・ネガコン) |
| `tools/plugins/slayer_engine_ia32/REPORT_APPENDIX_894.md` | ~62 | slayer_engine_ia32 REPORT §9.5・§9.6 (#894 events[] 探索) の全文を分割移動した付録。 `scan_events.py` の所要 (n=3 min–max)・load・鮮度証跡 (`git diff` 実出力) を含む。 REPORT.md は 250 行上限のため分割 |
| `tools/plugins/slayer_engine_ia32/REPORT_APPENDIX_1098.md` | ~95 | Slayer_Engine.dll (block22434) の .text の ia32 lift (#1098、測定 commit `fc2e70be`): 関数境界の根拠、被覆、jump table・IAT の実データ照合、x64 回帰、未被覆域の区間内訳と未解決 (子 #2814)。 測定値の正本は付録 §2・§3 |
| `tools/plugins/slayer_engine_ia32/REPORT_APPENDIX_1099.md` | 116 | x87 subset の ia32 lowering (#1099、測定 commit `ce0f0872`)。 実 x87 との差分試験 (`x87_diff.py`)・ネガコン・lift の before/after・x64 回帰。 測定値の正本 |
| `tools/plugins/slayer_engine_ia32/MARSHAL.md` | ~80 | 殻 (x64) ↔ Slayer_Engine.dll (ia32) の VST2 構造体 marshal 表の仕様 (#674 受入 3)。測定値は REPORT.md §9 |
| `tools/shared/REPORT.md` | ~212 | FL Shared ライブラリの分類・IPP 実測・OSS wasm 再ビルド・プロプラ lift PoC。win freetype.dll = 2.4.10 確定 (#145, §3.1) |
| `tools/shared/elastique/REPORT.md` | ~140 | élastique 2.2.15 (win x64) の静的 IPP 入口 197 件の API 同定 (T-SH-40 / #2613): 線形走査の入口再現・dsp_ippv2 の本体照合 (一意名 8・族候補 26・未同定 163)・tools/ipp の stub 名 28 (stub のみ 18・混在 16 入口。#2613 受入 2)・間接経路の静的確認。対応表は `data/entries.csv` |
| `tools/shared/REPORT_APPENDIX.md` | ~110 | shared REPORT の分割移動節の全文: §A win freetype.dll の版判定 (#145, 上流 VER-2-4-{10,11,12} 照合の実測)・§10 ライブラリのビルド詳細 (libFLAC/LAME/WavPack/FFmpeg/ILSvg)・§12 検収記録 (2026-10-11)。250 行上限のため無変更で分割移動 |
| `tools/shared/elastique/REPORT_152.md` | ~155 | élastique 2.2.15 (win `elastique_x64.dll`) の静的 IPP 入口と dispatch 層 (thunk・表の飛び先) の実測と lift 前提 (D20 の side module 方針)。測定値は本 REPORT §0。T-SH-10 (#152)。同定は子 T-SH-43 (#2667)、lift 本体は子 T-SH-41 (#2614) |
| `tools/shared/oss/sidemod/REPORT.md` | ~60 | FFmpeg/LAME を差し替え可能な side module として再ビルド + GPL 混入検出 (LGL-4) |
| `tools/shared/oss/ilsvg/REPORT.md` | ~50 | ILSvg の版の組 probe (#877): svgdom 0.4.7 は emcc 26/26 cpp OK、svgren 0.6.3 / 0.5.9 は svgdom 0.4.7 と enum 名不一致で版の組は未確定 (未解決 #927) |
| `tools/shared/oss/blend2d/REPORT_SIMD.md` | ~60 | Blend2D wasm `-msimd128` 試験 (T-SH-02, #146) の実測詳細・ネガティブコントロール・前版の実測・未解決の起票先 (`tools/shared/REPORT.md` §3.3 から分割移動) |
| `tools/shared/oss/blend2d/REPORT_AGG2D.md` | ~195 | Agg2D glue 棚卸し (T-SH-02/#146): FL Blend2D.dll (block24339) の vtable 規模 (§5)・x64c lift 可否の実測 (§9)・CFG 間接 call の扱い (§10)・判断材料と未解決 (§11)。§12・§13 は結論のみで、測定値は付録 |
| `tools/shared/oss/blend2d/REPORT_APPENDIX_AGG2D.md` | ~75 | `REPORT_AGG2D.md` の付録 (250 行上限のための分割移動): Blend2D.dll と dsp_ippv2 の vtable の slot 単位比較 (§12)・AggCreateInstance の loader と呼び出し元の手がかり (§13) |
| `tools/shared/lift/libreverb/REPORT.md` | ~60 | libreverb (win `Reverb.dll`) lift + 差分テスト (T-SH-15 #161 部分達成)。ildsp は §6 で一行参照のみ |
| `tools/shared/lift/ildsp/REPORT.md` | ~150 | ildsp (`block24360_PE.bin`) 規模調査 (§1–3: 命令数・call 数・export closure 表・SIMD 比の未解決) と GeneralPitchShifter_CreateInstance の instance vtable (§4: 6 slot の種別・間接 call のスロットと宛先・生バイト検算とネガティブコントロール・実測) (T-SH-19 #791 / #2483)。測定値の正本 |
| `tools/shared/lift/ildsp/REPORT_CLOSURE.md` | ~140 | ildsp vtable 経由の実体 closure (10 export・`.pdata` の無い先を含む・推移閉包・間接 call 内訳と末尾 jmp 内訳・objdump 検算) (T-SH-15 #161)。分離元は `REPORT.md` §2 の下限表 (§4 は GPS vtable)。測定値の正本 |
| `tools/shared/lift/rex/REPORT.md` | ~75 | REX Shared Library (win `block24351_PE.bin`) の export 14 本の閉包測定 (T-SH-11 #153): 関数数・命令数・間接 call・import・`.pdata` 無しの近似。lift は未実施 (#2733・#2734)。測定値の正本。再現は `rex_closure.py` |

### IPP

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/ipp/REPORT.md` | ~150 | Intel IPP 再現要否の評価と最小実装 PoC |
| `tools/ipp/shim/REPORT.md` | ~445 | `dsp_ippv2` ローダ shim + 署名 thunk 自動生成 |
| `tools/ipp/shim/fft/REPORT.md` | ~100 | IPP FFT の pffft 差替え |

### ターゲット別プラグイン

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/targets/serum2/REPORT.md` | ~200 | Serum 2 インストーラ解析 + lift 可否評価 |
| `tools/targets/serum2/REPORT_SR3d.md` | ~90 | SR-3d (#867): 窓外 muParser 6 関数の VA 参照走査 (abs8・RVA4・RIP lea)・呼出元の cut 照合・名前表の所在。帰属は未確定 (#71) |
| `tools/targets/serum2/host/REPORT.md` | ~240 | Serum 2 最小 VST3 host |
| `tools/targets/serum2/host/REPORT_SR1c.md` | ~222 | SR-1c (#256) 付録: controller ゲート (+0x10c / +0xdc) の静的 writer 走査と API 突合 (import 327 / 呼出 110 / 未呼出 217)。API 名一覧は `host/sr1c_api_surface.tsv` |
| `tools/targets/serum2/host/REPORT_SR23.md` | ~78 | SR-23 (#1545) 付録: 書込元 `0x1800acf70` の所属 class (`SerumController`・vtable slot 3) と、wrapper IID (`IVst3ToAUWrapper`/`AAX`) に応答する host 根拠 (SDK 参照 host は応答しない) |
| `tools/targets/serum2/host/REPORT_SR5.md` | ~120 | SR-5 (#73) / SR-47 (#2414): 参照音源 (wine64 上の実 Serum2 DLL) の WAV 生成と dB 誤差ハーネス。決定性 (file SHA-256 一致)・content dir 条件 (既定 installer 全展開 / variant 空 dir) ごとの参照 pin・ネガコン・測定 commit の対応・stub による補助確認 (再測定ではない)・content 条件の判断 (§4) |
| `tools/targets/serum2/license/REPORT.md` | ~160 | Serum2 認可機構の呼出点マップ |
| `tools/targets/serum2/license/authstub/REPORT.md` | ~232 | authorization stub 設計・実装。§13b・§14 の詳細は付録 `REPORT_APPENDIX.md` §13b・§14b (250 行上限のため分割移動) |
| `tools/targets/serum2/license/authstub/REPORT_APPENDIX.md` | ~95 | authstub REPORT の分割移動節: §13b (L1 脱落条件の突合・census の数え方) と §14b (L1 復元 pass の census・ネガコン・e2e 実測、LF 束縛の詳細) |
| `tools/targets/serum2/license/authstub/REPORT_APPENDIX_1009.md` | 49 | authstub #1009 (SR-12) の受入 2・3: L1 復元 pass の前後 census の再計算手順 (`l1_recompute.py`)・ネガコン (pass 無し = 脱落状態・二重適用の拒否)・実測と未解決 (§14f) |
| `tools/targets/serum2/sr4/REPORT.md` | ~110 | SR-4 (#75) DSP 段階 lift 第 1 段: vtable root 56 関数の対象表 + pilot lift 9 本 (実機 vs wasm 差分) + strict gate + ネガコン |
| `tools/targets/serum2/gui/REPORT.md` | ~76 | SR-7 (#68, 部分達成): Splice 3 テンプレートの実体化分岐は未特定 / overlay_demo_version は template 定義 0 件 (静的確認のみ) |
| `tools/targets/serum2/gui/REPORT_SR24.md` | ~111 | SR-24 (#1710): Splice テンプレート実体化分岐の静的解析。sub-controller 振り分け `0x1804a1950` まで特定、demo bit 書込元・demo ダイアログ呼出元を列挙。分岐の特定は未達 (子 #1917) |
| `tools/targets/serum2/gui/REPORT_SR28.md` | ~110 | SR-28 (#1917): Splice テンプレートの選択経路 (vtable 0x180a86b88 の設定元まで)・demo ダイアログ呼出元の vtable 位置。選択関数と demo bit 結線は未達 (SR-30 で訂正) |
| `tools/targets/serum2/gui/REPORT_SR30.md` | ~100 | SR-30 (#2000): REPORT_SR28 の vtable 0x180a86b88 前提の訂正 (RTTI は SerumEditor の sub-object)。Splice 生成の直接呼出元と demo bit 読書 (0x1800c2b50 / 0x1800c6090) を列挙。選択 state 条件と間接経路は未達 (子 #2053〜#2055) |
| `tools/targets/serum2/gui/REPORT_M7_CANVAS.md` | ~120 | SR-7 (#68) の M7 接続照合 (静的): CanvasFrame を tools/gui の surface・out ring の記号と照合 (`gui/m7_canvas_connect.py`)。設計上は接続可・実装は一部のみ・画素形式が不一致。数値の正本は本体 §0・§2 |
| `tools/targets/serum2/gui/REPORT_APPENDIX_1350.md` | ~197 | #1350 付録: VSTGUI 14.3 除外 (setMouseCursor の jump table 範囲検査 `cmp eax,0xa`)・14.0 確定と 14.1〜14.3 除外 (`call_once` 構造・`callonce_probe.py`)・再現手順と実測 |
| `tools/targets/massivex/REPORT.md` | ~160 | Massive X 事前解析 + ライセンス呼出点マップ |
| `tools/targets/massivex/REPORT_APPENDIX.md` | ~248 | Massive X MX2-3 (#830) N5/N6 実測の付録 (REPORT §12 の分割移動・未達の起票先 #1017) |
| `tools/targets/massivex/REPORT_APPENDIX_2151.md` | ~70 | Massive X §12.12〜§12.14 (#1976・#2108・#2151 MX-31) の分割移動全文。§12.14 の `.pdata` 訂正は未確定 |
| `tools/targets/massivex/dsp/REPORT.md` | ~220 | Massive X DSP closure 特定と lift 計画 |
| `tools/targets/massivex/dsp/REPORT_MX6.md` | ~130 | MX-6 (#1123): vectorcall 静的検出・.pdata unwind census・FH3 funclet 一覧と #228 同型判定。測定値の正本 |
| `tools/targets/kilohearts/REPORT.md` | ~200 | Kilohearts インストーラ解析 + snap-in lift 可否 |
| `tools/targets/kilohearts/REPORT_KH19.md` | 70 | KH-19 (#782) ホスト 3 種 (Snap Heap / Multipass / Phase Plant) の vtable 間接 call 込み closure 再計算 (下界・過大評価の参考値・限界) |
| `tools/targets/kilohearts/REPORT_APPENDIX_3064.md` | ~36 | KH-37 (#3064): 対照 Gain の x64c 閉包 148 と `gain_before_160.tsv` 160 行の数え方の差 12 件 (iat_thunk 2・tail_absorbed 9・SEH 着地点 1) と、`0xfd0995` が SEH の `__except` 着地点である実測 |
| `tools/targets/kilohearts/license/REPORT.md` | ~125 | HeartCore ライセンス層の呼出点特定 |
| `tools/targets/kilohearts/license/KH9_REPORT.md`・`KH10_REPORT.md`・`KH11_REPORT.md`・`KH249_REPORT.md`・`KH656_REPORT.md`・`VERIFY_CAB247.md` | ~125/105/115/115/80/185 | KH-9/10/11 実施記録・#249 (ブラウザ分類 lift・ctor 47 vs 46 同定)・#656 (分類 module F の閉包展開) と CAB-247 検証 |
| `tools/targets/kilohearts/snapins/REPORT.md` | ~200 | KH 共通基盤 lift + SnapinMasterDsp ホストハーネス |
| `tools/targets/kilohearts/ui_eval/REPORT.md` | ~135 | KH-7 Kilohearts UI (Skia CPU ラスタ) → M7 HUD 接続可否評価 |
| `tools/targets/freshair/REPORT.md` | ~145 | Fresh Air インストーラ解析 + lift 可否 |
| `tools/targets/freshair/REPORT_APPENDIX_FA5.md` | ~237 | freshair REPORT §11 (FA-5 #52) の付録: 最大値の除外基準 (§A1)・`.rdata` 不一致 20 関数の分類詳細 (§A2)・Gain の意味同一性の差分実行 (§A3)・FA-18 の切り分け (§A3-2)・meter 更新式の照合 (§A3-3, #1467)・ramp 逐次 cur の照合 (§A3-4, #1617)・丸め形だけを差し替えたモデルの LRS 再現 (§A3-5, `ks_gain_model.py`)・`value` 17 件の参照内訳 (§A4, `ks_rdata_detail.py`)・語単位切り分け (§A5, `ks_rdata_value.py`)・RVA 候補の指す先の切り分け (§A5-3, `ks_rdata_rva_table.py`)。§A1〜§A3 は 250 行上限のため無変更で分割移動、§A4・§A5 は #52 残件として追加 |
| `tools/targets/freshair/REPORT_APPENDIX_FA22.md` | ~60 | freshair FA-22 (#1578) の付録。FA_NODE1=1 時の setter 0x180c9d74c の失敗形 (逆アセンブル・実測)。部分達成で、判定は子 #1789・#1791 に分割 |
| `tools/targets/freshair/REPORT_APPENDIX_FA32.md` | ~95 | freshair FA-32 (#2306) の付録。`FA_NODE1=1` の setter ERR 8 行の原因は harness の注入 node 配線 (値オブジェクト Z が 0x40 のため `Z+0x2c0` を guard・非正準アドレスで読む)。issue 本文の `rip=74c addr=50` は ALT9 の署名。偽オブジェクト (`FA_NODE1_ZOBJ`) で ERR 0/8。実機の `C+0x2b0` の中身は未判定 (#2207) |
| `tools/targets/freshair/REPORT_APPENDIX_FA30.md` | ~60 | freshair FA-30 (#2187) の付録。2 回目の `ca1480` 呼出 (C=Z) の呼出元は setter 0x180c9d700 の再帰 (0x180c9d827)。注入 node (`FA_NODE1=1`) の found 経路でのみ発生。実機 map の観測は未解決 |
| `tools/targets/freshair/REPORT_APPENDIX_FA29.md` | ~50 | freshair FA-29 (#2145) の付録。`ca1480` の out[0]=Z+0x2b0 の由来 (key 無し分岐 `C+0x2b0`・2 回目の呼出 C=Z)・full probe が 2 回目で ERR する理由。部分達成で、呼出元の特定は #2187 |
| `tools/targets/freshair/REPORT_APPENDIX_FA16.md` | ~50 | freshair REPORT §12-5 (未解決: 非空 controller map による 0x180da6c00 到達) の静的読み付録 (FA-16 #1182)。0x180ca1480 の分岐・0x180ca7db0 の map lower_bound ノード配置・0x180c9d700 / 0x180da6c00 の入口条件。実行による検証は含まない。REPORT §12-5 から分割移動 |
| `tools/targets/freshair/lift2/REPORT.md` | ~210 | Fresh Air Compressor/Filter/制御層 lift (§12 は `REPORT_APPENDIX_FA4.md` に分割移動) |
| `tools/targets/freshair/lift2/REPORT_APPENDIX.md` | ~180 | lift2 FA-10 (#666): ctrl 工程 FAILED の epf 素材切り分け (同一コード A/B)・rep movs/stosw の実装と e2e 未実行の実測・未解決 FA-11/FA-12 (REPORT §12 から参照)。FA-14 (#907): §7 回帰セットの seed 依存実測・§8 受入の未達と起票先 (#1105)・§9 lift2_e2e 実測 (実測 commit `c531a0cb`) |
| `tools/targets/freshair/lift2/REPORT_APPENDIX_FA4.md` | ~50 | lift2 REPORT §12 全文 (FA-4 #51: チェーン構成 / マクロ→子パラメタ ID 写像)。250 行上限のため無変更で分割移動 |
| `tools/targets/freshair/lift2/REPORT_FA7.md` | ~70 | FA-7 (#452): macro 子 param ID 0x157/0x158/0x15a の Filter descriptor 同定 (model 層 setter 実測) |
| `tools/pm/REPORT_APPENDIX_2349.md` | ~95 | PM Worker の日次 digest (#2349・CI-70・`oc-pm kind=digest ref=0`): 24 時間の起点・2 回目の抑止・1 日 1 件・dry-run・送信失敗の枠・rolling issue の launch 除外の実測 (測定 commit `5726e190`・main 取り込み後の再測定 §7)、24 時間ガードと rolling 除外の mutation で FAIL を確認、pm.md の digest / user_answered 節の検査。REPORT.md が 250 行上限のため別置き |
| `tools/pm/REPORT_APPENDIX_2461.md` | ~64 | PM Worker の `user_answered` の回答を MEMBER / OWNER / COLLABORATOR のコメントに限る (#2461)。変更の要点・件数・テスト a〜c・測定 (`npm test` 163 件・`test:workers` 3 件・所要)・ネガコン A/B・未解決。`REPORT.md` は 250 行上限のため本体へ追記しない |
| `tools/pm/REPORT_APPENDIX_2469.md` | ~77 | PM Worker の降格 (#2340・PR #2469・REPORT §20): 降格中の oc-pm digest の降格ゲート (round 3)・降格の組を Worker と個人の `/oc` に限る (round 4・ADR D26)・ネガコンの組み直し (round 5・6)・main (#2783) の取り込みと競合の解消 (round 9)・pnpm 手順の測定 (測定 commit `7c7bcc74`: `npm test` 336 件 5 回連続 pass・`test:workers` 4 件・`test:unit` 45 件・build)・変異 (a)〜(e) のネガコン・差分 0 の証跡。REPORT.md が 250 行上限のため別置き |
| `tools/pm/REPORT_APPENDIX_2591.md` | ~60 | #2591 (pm.md の `needs_decision` の PR 起点化・`rule=skip`・投稿・質問の前の確認) の検証記録。修正本体は #2603 で main に入った。main の版の検査・ネガコンの測定 (測定 commit と検査件数・結果は付録 §2)。`REPORT.md` は 250 行上限のため本体へ追記しない |
| `tools/pm/REPORT_APPENDIX_2652.md` | ~110 | PM Worker の保存値の版 (`SIGNAL_VER`) による補完 (#2652・PR #2671・`Closes #2652`): 版が保存値と違う最初の tick で全体同期する修正の実測 (テスト・vitest・ネガコン・本番 `/status`・保存 outcome の REST 再計算) と、根因 (子 #2757) の未解決。運用の正本は `infra/pm-worker/README.md`。REPORT.md が 250 行上限のため別置き |
| `tools/pm/REPORT_2795.md` | ~99 | PM Worker の launch の安全装置 (#2795・PR #2854): `IMPORT_REQUIRED` の既定の反転、launch の停止 (`launch_halted`・`launch_halted_overdue`) と PM agent への通知 (digest ref 0) の実測。テスト件数 (node:test・vitest unit・workers)・変異テスト (件数は §3)・測定 commit と差分・本番 `/status` の観測時刻 (読み取りのみ・未 deploy)。REPORT.md が 250 行上限のため別置き |
| `tools/pm/REPORT.md` | ~250 | PM 運用の実測 (PR 件数・PR とチケットの対応・Project Status・Actions run 集計・PM Worker のコメント同期 #2380 (全文は付録)・`idle_report.sh` の検証 #2354 (全文は付録)・PM Worker の live 切替前の突き合わせ #2443・R2 素材投入の頻度 #2434・`pm_wake.sh` の判定テストと live 確認 #2347・PM Worker の同時実行の上限の推定 #2381・main の Ruleset の実測 #2648 は §19 (参照のみ。本体は `REPORT_2648.md`))。RETRO・DIRECTIVES の数値の正本 |
| `tools/pm/REPORT_APPENDIX_2600.md` | ~13 | 実装 App の自己 merge の実測 (#2600・PR #2624) の全文。REPORT.md は 250 行上限のため本節を持たず、測定値の正本は本付録 |
| `tools/pm/REPORT_APPENDIX_2380.md` | ~32 | tools/pm REPORT §10 (PM Worker のコメント同期 #2380) の全文。250 行上限のため REPORT.md から分割移動 (#2434) |
| `tools/pm/REPORT_2416.md` | ~140 | PM Worker の build 表示 (#2416、PR #2477 の差し戻し round 1・5): `npm test`・`npm run test:unit`・`npm run test:workers` の n=3 実測 (測定 commit と件数は本付録が正本。wall と vitest Duration を分けて記録)、wrangler `--define` / `--var` の dry-run 結果 (README『再デプロイ』手順 4 の根拠)。`REPORT.md` は無変更 |
| `tools/pm/REPORT_2799.md` | 73 | PM Worker の VM 状態の取り込み手順の是正 (#2799・CI-134): 補助スクリプト `infra/pm-worker/scripts/build_import.mjs` の検証 (素材行の正規化・200 KiB の上限・Worker の `parseVmState` を通ること)、整形出力と `jq -c` と補助スクリプトの比較 (合成データ)、`npm run test:unit` / `npm test` の実測と negative control。REPORT.md が 250 行上限のため別置き |
| `tools/pm/REPORT_3047.md` | ~50 | PM Worker の率制限 alert を watchdog から `oc:rate-limit` の issue に出す (#3047・CI-142): 判定 (fresh・`rate_limit_alert`・`rest_remaining` < 1500)、追記の 60 分の間隔、採番の共有、テスト 40a〜40t と変異 M1・M3・M5・M6・M7 (閉じた issue の確認を外す) の FAIL、本番 `/status` の読み取り。REPORT.md が 250 行上限のため別置き |
| `tools/pm/REPORT_3050.md` | 59 | PM Worker の launch の素材行の和集合 (#3050・CI-143): PM の行と本文の行の素材名を足す規則の実測。node:test・vitest unit・workers・変異テストの件数、測定 commit と差分、排他実装に戻したときの FAIL (negative control)、issue 本文の実例 (#2716・#2880) の再計算。REPORT.md が 250 行上限のため別置き |
| `tools/pm/REPORT_2336.md` | ~98 | PM Worker の規則 A (merged PR を持つ親 issue の自動 close・#2336) の実データ dry-run の実測 (Worker の判定と別実装の再計算の照合・候補の内訳・ネガコン・判定条件を外したときの FAIL)。運用の正本は `infra/pm-worker/README.md` |
| `tools/pm/REPORT_2648.md` | ~50 | main の Ruleset `main-require-review` (#2648・ADR D27) の実測: 設定 (API)・merge の窓の件数・実装 App の merge 前承認の件数 (数値は付録 §3)・取得コマンドと jq 式。REPORT.md §19 から分割移動 (250 行上限) |
| `tools/pm/REPORT_APPENDIX_2354.md` | ~62 | tools/pm REPORT §11 (`idle_report.sh` の検証 #2354) の全文。250 行上限のため REPORT.md から分割移動 (#2381 の PR のレビュー指摘への対応)。fake gh の判定 41 件・実データの検算・未解決 (soak の合格ライン) |
| `tools/pm/REPORT_APPENDIX_2337.md` | ~60 | tools/pm REPORT §16 の全文 (oc-pm の refs_orphan 検出 #2337・PR #2478: 測定・ネガコン・Refs のみ判定の差)。250 行上限のため REPORT.md から分割移動。測定値の正本は本付録 |
| `tools/pm/REPORT_APPENDIX_2645.md` | ~25 | tools/pm REPORT §17 の未解決 (#2645・PR #2655) の実装記録の全文: 観測済み launch の `recent` を、観測した run の完了から数える。取り込み後の再測定 (node:test 293・vitest 29・workers 4 件)、ネガコン M1〜M10。250 行上限のため REPORT.md から分割移動 |
| `tools/targets/freshair/lift2/REPORT_FA15.md` | ~60 | lift2 FA-15 (#1105): ctrl closure の ymm (AVX2 256bit) lowering (`vpcmpeqw`/`vpxor`/`vpmovmskb` ymm・`vzeroupper`)。`build_ctrl.sh` の `failed` 1→0、`lift2_e2e.sh` ALL PASS の実測 |
| `tools/targets/freshair/lift2/REPORT_FA13_REACH.md` | ~46 | lift2 FA-13 (#905): rep movsb/stosw の実行到達の再探索。結論: 受入 1 (実行到達 scenario)・2 (ネガコン FAIL) は未達のまま。測定値は本 REPORT のみ |
| `tools/targets/freshair/lift2/REPORT_FA8.md` | ~60 | FA-8 (#648): Filter setter の native/wasm bit-exact・型別 ID 感度・FA-7 probe 測定バグ修正 |

## 4. ドキュメント責務 (単一責任の正本)

**「何をどこに書くか」の割り当て。** 鉄則: 測定値・実測数値は `tools/<area>/REPORT.md` だけに書き、
同じ数値を 2 ファイルに書かない。外側は「結論 1 行 + リンク」に縮める。
`AGENTS.md` は本表の原則要約と導線のみを持つ。

| ファイル | 単一責任 | **書いてはいけないもの** |
|---|---|---|
| `README.md` | 何のプロジェクトか (1〜2 行) / **docs・tools の地図と索引** / 開発コマンド / デプロイ 3 行要約 | 測定値・実測数値・repo 外絶対パス・進捗の詳細 |
| `AGENTS.md` | エージェント規約の**要約と導線** (規約の本文は `docs/WORKFLOW.md`・本表) | 測定値・技術的な手順・状態の詳細・他ファイルの規約の複製 |
| `docs/ARCHITECTURE.md` | パイプライン全体像 (x64c → liftlib → wasm → shim → runtime → deploy) | 測定値・個別バグ・issue 個別の経緯 |
| `docs/STATUS.md` | **技術進捗の正本** (MS 番号・サブシステム 1 行ステータス・次の一手・直近 merge の自動要約 (`tools/pm/status_sync.py` が更新する節)・その写像表)。チケット状態は issue の open/closed + ラベル + PR が正本 (`docs/WORKFLOW.md` §3) | 測定値・数値の詳細 (REPORT へのリンクにする) |
| `docs/DECISIONS.md` | ADR: 方式決定・理由・日付 | 測定値・手順の詳細 |
| `docs/WORKFLOW.md` | subagent 運用・PR・レビュー・検収・自己点検・**AREA 一覧** | 技術的な実装手順・測定値 |
| `docs/REFERENCES.md` | 外部ソース・素材・ツール・**vendored 台帳**。**repo 外絶対パスはここだけ** | repo 内パス・技術内容 |
| `docs/pm/DIRECTIVES.md` | 依頼者 (user) 指示の**逐語原文**と PM の解釈・反映先 | 原文の改変 (追記のみ)・測定値 |
| `docs/pm/RETRO_2026-10-13.md` | Actions 移行後 2 日間のショートレトロ (事実・原因・対策。依頼者指示 121) | 測定値 (正本は `tools/pm/REPORT.md`。本書は結論と link のみ)・指示の逐語原文 (`DIRECTIVES.md` が正本)・repo 外絶対パス |
| `tools/pm/REPORT.md` | PM 運用の実測の**正本** (PR 件数・PR とチケットの対応・Project V2 Status (参考値)・Actions run 集計。基準時刻と取得方法を併記) | 技術実装・指示の逐語原文・チケット状態の判断 (`STATUS.md`・issue/PR の状態 (`docs/WORKFLOW.md` §3) が正本) |
| `tools/pm/REPORT_2416.md` | PM Worker の build 表示 (#2416) の測定値の**正本** (付録。`npm test`・`npm run test:unit`・`npm run test:workers` の n=3 実測と取得方法、wrangler `--define` / `--var` の dry-run 結果) | 技術実装の手順 (README が正本)・指示の逐語原文・チケット状態の判断・repo 外絶対パス |
| `tools/pm/REPORT_2799.md` | PM Worker の VM 状態の取り込み (#2343) の補助スクリプト (#2799) の測定値の**正本** (付録。合成データの大きさ・Worker の検証の結果・`npm run test:unit` / `npm test` の実測・negative control) | 取り込みの手順と値域 (`infra/pm-worker/README.md` が正本)・PM の実データの件数・repo 外絶対パス |
| `tools/pm/REPORT_2648.md` | main の Ruleset `main-require-review` (#2648・ADR D27) の測定値の**正本** (付録。設定の API 値・merge の窓の件数・取得コマンドと jq 式) | 方式の決定 (DECISIONS.md D27 が正本)・手順 (WORKFLOW.md §2 が正本)・bypass の値を手順書に複製すること |
| `tools/pm/REPORT_2795.md` | launch の停止と通知 (#2795) の測定値の**正本** (付録。テスト件数・変異テスト・測定 commit と差分・本番 `/status` の観測時刻) | 停止の規則と運用 (`infra/pm-worker/README.md` が正本)・deploy の判断 (PM)・未解決の表 (PR 本文が正本) |
| `tools/pm/REPORT_3050.md` | launch の素材行の和集合 (#3050) の測定値の**正本** (付録。テスト件数・測定 commit と差分・negative control・実例の再計算) | 素材行の規則 (`infra/pm-worker/README.md` が正本)・deploy の判断 (PM)・未解決の表 (PR 本文が正本) |
| `tools/pm/REPORT_APPENDIX_2380.md`・`tools/pm/REPORT_APPENDIX_2354.md` | REPORT §10・§11 の分割移動先 (無変更の全文)。測定値の正本は付録側 | 本体 `REPORT.md` へ戻す追記・同じ節の要約の重複 (本体は要約とリンクだけ) |
| `tools/pm/README.md` | PM 運用ツールの一覧・『VM 退役後の扱い』(全ファイルの後継・廃止の表)・VM の状態ファイルの扱いの決定 (取り込み or 破棄と影響)・前提・環境変数・運用の約束 | 測定値 (`tools/pm/REPORT.md` が正本)・認証情報・状態ファイルの中身や件数 (決定と影響だけを書く) |
| `infra/pm-worker/README.md` | PM Worker (Cloudflare) の構成・デプロイ・**再デプロイ (wrangler の OAuth)**・ロールバック・OAuth 失効時の手順・`[未確認]` のチェックリスト | 測定値 (`tools/pm/REPORT.md`・付録 `tools/pm/REPORT_2416.md` が正本)・認証情報 (token・OAuth の保存ファイルの中身)・repo 外絶対パス |
| `tools/pm/status_sync.py` (+ `test_status_sync.py`) | `docs/STATUS.md` の自動節 (`status-auto` マーカーの内側) を、直近 24 時間の merge PR を MS / サブシステムに写像した件数と代表 PR 番号で更新する決定的スクリプト (REST のみ)。写像表は `docs/STATUS.md` の `status-map` ブロックが正本。テスト: `python3 -m unittest tools/pm/test_status_sync.py` | 測定値 (自動節にも書かない。正本は各 `REPORT.md`)・自動節の外の編集・認証情報 |
| `docs/pm/README.md` | `docs/pm/` の索引 (3 ファイルの役割のみ) | DIRECTIVES の内容の繰り返し・分析内容 |
| `docs/pm/PREDECESSOR_ANALYSIS.md` | 解任された前任 PM セッションの分析 (混乱の原因・証拠・再発防止ルールへの反映) | 指示の逐語原文 (`DIRECTIVES.md` が正本)・状態や未解決事項 (`STATUS.md`・`HANDOFF` が正本)・repo 外絶対パス |
| `docs/LEGAL.md` | ライセンス/規約上の運用制約と事実整理 | 技術実装・数値実測 |
| `docs/LEGAL_TERMS_LEDGER.{json,md}` | 各社規約の取得台帳 (取得日・版表記・正規化テキストの SHA-256)。`.json` が正本、`.md` は自動生成 | 規約本文・手編集 (`pnpm terms-watch` が更新) |
| `docs/DOC_MAP.md` | 本書。REPORT.md 索引・行数上限ルール・自動生成一覧・本章 | 技術内容・測定値 |
| `docs/DEFECTS.md` | lift silent miscompile 類型 D1a〜D23 (横断正本) | 個別ケースの詳細 (report 側) |
| `docs/HANDOFF/<日付>.md` | 引継ぎ要約 (方針・ブロッカー・次の一手)。最新のみ保持 | 状態の正本 (STATUS.md へ)・数値の羅列 |
| `tools/<area>/REPORT.md` | **測定値・実測数値・検証結果の単一の正本** (日本語/英文を問わず) | なし (ここが正本) |
| `tools/<area>/README.md` | **ナビゲーションのみ** (何をする dir か・E2E コマンド・関連ファイル) | 測定値・状態表 |
| `tools/<area>/{PROTOCOL,FORMAT,ABI,MANIFEST,STARTUP,GATES,BACKLOG,inventory}.md` | 仕様・台帳 (現状は良い設計・維持) | 測定値 |
| `tools/<area>/results/*.md`・inventory 系 | **自動生成**。先頭 1 行に `自動生成: <cmd>` | **人手編集禁止** |
| `deploy/` | デプロイ単独 (README からは 3 行 + リンクだけ残す) | 測定値 |

