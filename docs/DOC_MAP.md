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
| `tools/legal/release-guard/REPORT.md` | ~75 | release guard (LGL-2): 公開前に dist を走査し FL/プラグイン由来バイト列を検出して失敗させる deny-list ゲート |
| `tools/legal/terms-watch/REPORT.md` | ~145 | terms-watch (LGL-5): 各社 EULA/ToU の取得 (Xfer は NSIS インストーラのヘッダから)・正規化ハッシュ比較・台帳更新・差分時非ゼロ終了 |
| `tools/legal/notices/REPORT.md` | ~110 | THIRD_PARTY_NOTICES 自動生成 (LGL-3): OSS 再ビルド記録 (upstream 版・configure 引数・パッチ) + FL 同梱表記 15 本 + フォント一覧から NOTICES を生成し、記録なしの同梱 OSS を CI/stage ゲートで検出 |
| `tools/perf/REPORT.md` | ~150 | wasm 実時間性能・compile 時間・巨大 wasm 実験 |
| `tools/perf/REPORT_APPENDIX.md` | ~85 | perf REPORT §12 全文 (PERF-P9 #168: bit-exact OTT の RTF を node / Chrome Worker / 実 AudioWorklet / native 実機械語で再測) |
| `tools/perf/PERF.md` | ~150 | 性能の設計メモ (bit-exact 版の実測は `tools/perf/REPORT.md` §2.1・完走路の正本は `tools/ott/REPORT.md`) |
| `tools/perf/REPORT_P8.md` | ~120 | PERF-P8 (#166): plugin 別 module/instance/memory vs MAIN/SIDE_MODULE 動的リンクの合成カーネル比較 (node + Chrome 154 Worker)。`tools/perf/REPORT.md` §5 項目 7 から参照 |
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
| `tools/liftlib/REPORT_APPENDIX.md` | ~220 | liftlib §17 全文 (HB-H3 #93 iargs pass)・§18 全文 (LIFTLIB #241 ymm(i256) helper ABI / pcmpistri / F2 xmm 戻り搬送) |
| `tools/liftlib/REPORT_APPENDIX_C.md` | ~95 | liftlib §19 全文 (PERF-P1 #155 標準ビルド設定 + 出力 bit 署名ガード + fail-open 封じ込め)・§20 (LIFTLIB-7 #478 ott_auto_none fail-closed + census 再計算) |
| `tools/liftlib/REPORT_APPENDIX_D.md` | ~160 | liftlib §22 全文 (LIFTLIB-9 #668: RetDec raw lift 出力の非決定性 = uselistorder・ASLR 依存、A7 後は決定的、回帰 gate `lift_determinism_e2e.sh`)。本体 §22 は要約のみ |
| `tools/flelift/REPORT.md` | ~155 | x64c を FLEngine 向けに汎用化 |
| `tools/flelift/boot/REPORT.md` | ~350 | FLE-2〜FLE-5: x64c lift による FLEngine boot 連鎖 |
| `tools/qfclift/REPORT.md` | ~100 | T-SH-12 (#154 部分達成): QuickFontCache_x64.dll の x64c lift (6,347 関数・unsup 0) + SSSE3 handler 注入 (pshufb/pmulhrsw/phaddw) + native-vs-wasm の SSSE3 spot diff。ILTools / FruityPlug は未着手 |
| `tools/liftdiff/REPORT.md` | ~230 | flelift (x64c) 全数採点 + native 全起動の参照化 (§5/§6.1/§6.2 は `REPORT_APPENDIX.md` に分割) |
| `tools/icall/REPORT.md` | ~237 | 間接 call/jmp 落ち監査 + 復元 pass。§10.1 (#530)・§11 (ICALL-6 #361) は要約のみで全文は `REPORT_APPENDIX.md` に分割 |
| `tools/icall/REPORT_APPENDIX.md` | ~88 | icall REPORT §10.1 (#530 OTT 回帰再実行) と §11 (ICALL-6 #361: FMA3 CRT 経路 600/600・`_handle_errorf` override・rax scratch 根拠) の全文 (250 行上限のため無変更で分割移動) |
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
| `tools/m11/REPORT_APPENDIX.md` | ~238 | m11 REPORT §8 (LB_BASE=0x10000 適用 #222)・§9 (sigfix 0 詰め #131)・§10a (#132 commit 別測定表と注記)・§10b (#132 真因・修正 4 点・NC・次 blocker・外した内容)・§12 の一部 (#513 新規類型の行案)・§12b (#513 巨大 VirtualAlloc の n の出所) の全文 (250 行上限のため本体から無変更で分割移動) |
| `tools/m11/REPORT_N21.md` | ~35 | M11-N21 (#572): m11_data_gen.py の DIR64 補正境界 off-by-one の全数照合・参照経路・修正・ネガコン・実測 (REPORT §11 は要約のみ) |
| `tools/m11/REPORT_N27.md` | ~130 | #680: survey 測定基準の固定化 (ldfix/qstore の fail-closed・PE パス env 化・IR 生成条件と指紋の記録・同一 runner の n=3 再現・NC 試験・`--full` は入力 CSV 欠落で未成功 (§10)・レビュー指摘の扱い) (環境間一致は未実測) |
| `tools/m11/rtl/REPORT.md` | ~175 | Delphi RTL の VA 範囲確定 + RTL 帯 (System/Types/SysUtils 1,172 関数) の lifter 別 liftdiff 採点 (#129) |
| `tools/m11/alloca/REPORT.md` | ~150 | alloca 縮退修正 (CAB-129) |
| `tools/m11/qstore/REPORT.md` | ~90 | 64bit スタック局所の即値 store が 4B に縮む欠陥 (DEFECTS D17) の検出・修復・idx 87/898/58–63 の帰属・#513 取り込み後の実測 (#516) |
| `tools/m11/trap_triage/REPORT.md` | ~228 | M11 survey trap の個別原因切り分け (#130)・halt0 20 の原因 (#417)・OOB 分類 (#419、§8.2 = 旧 tree の実測。現 main の ON/OFF 比較は REPORT_595) |
| `tools/m11/trap_triage/REPORT_419.md` | ~58 | #419 の合流前 (fa918df 基準) の OOB 修正試行・旧 ON 構成 (410360 + 8cbda0/8cbce0) の測定 (REPORT §8 から無変更で分割移動) |
| `tools/m11/trap_triage/REPORT_418.md` | ~70 | 409470 転記ハングの原因特定 (#418) |
| `tools/m11/trap_triage/REPORT_595.md` | ~90 | ClassCreate ON (`M11_OV_CLASSCREATE=1`) の ok 退行の原因切り分けと C 転記 (`41c130` / `413060`)・残る unit 415 の原因・既定 OFF のネガコン (#595) |
| `tools/m11/trap_triage/REPORT_474.md` | ~100 | 410320 補完後の unit 114 ハング = 5c0270 の unlink deref 脱落 (#474)・409470/410320 再採用 |
| `tools/m11/trap_triage/REPORT_482.md` | ~100 | `5c03d0` の node 差替え通知 `call [rbx+0x18]` の D15 脱落を復元 (#482)・survey 不変の実測 |
| `tools/m11/trap_triage/REPORT_495.md` | ~115 | `SV_TRACE_AT` 付き survey で unit 134 が ok→oob になる原因 (trace の fprintf が残す stack 残骸 × `function_413870` の引数脱落) と trace の透過化 (#495) |
| `tools/m11/trap_triage/REPORT_596.md` | ~125 | work-m11 snapshot 基準の OOB 21 unit の最上位 frame 分類・4f9f40 系/414ad0 系の観測・#307 の OOB との同軸突合 (#596) |
| `tools/m11/trap_triage/REPORT_494.md` | ~125 | survey の per-unit JSON に間接 call の site / target 別 hit 数 (`icall` 欄) を常設・#482 の復元を hit 数だけで検収 (#494) |
| `tools/m11/trap_triage/REPORT_483.md` | ~205 | oob→halt0 12 unit の Error() 原因 = TDictionary 比較器チェーンの D4/D15 脱落 (#483)・merge 後 head の再測と ok→非 ok の原因分類 |
| `tools/m11/trap_triage/REPORT_662.md` | ~141 | unit 56: `8c7710` の D4 型 1 段 deref 脱落の転記 (#662)・`8c5eb0` の件数 0 ループ先頭ガード脱落の特定 (IR 状態 Q の範囲。修復と N 状態の原因は #699)・negctl (base/cur/guard/ng) の n 回再現レンジと IR 状態 Q/N の対照 |
| `tools/m11/ldfix/REPORT.md` | ~165 | load 取り違え (値↔アドレス / 1 段 deref 脱落) IR 修復 pass |
| `tools/m11/ldfix/REPORT_484.md` | ~130 | ldfix が 5c0270 の D4 脱落を検出できなかった理由 (F3c の門 G1〜G5) と load→store 脱落の全数監査 (#484) |
| `tools/m11/ldfix/REPORT_510.md` | ~150 | base が引数由来でない load→store (370 site / 169 関数) の判定軸: SSA 対応の静的判定 vs liftdiff 動的差分の実測比較と脱落数 (#510) |
| `tools/m11/shimx_link/REPORT.md` | ~165 | M11 × shimx リンク |

### shim / 起動

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/shim/README.md` | ~50 | Win32 shim コア (53 export) のナビゲーション |
| `tools/shimx/REPORT.md` | ~199 | Win32/CRT shim 拡張。§9〜§12 は `REPORT_R1-R8.md`・`REPORT_CAB-214.md`、§15 は `REPORT_SHX-T8.md`・§16 は `REPORT_SHX-T7.md` に分割 (#584) |
| `tools/shimx/REPORT_R1-R8.md` | ~78 | shimx §9 (CAB-211: M11 リンク フィードバック R1〜R8) + §10 (CAB-177: cbtrans R2/R3 実体接続) 全文 (REPORT.md から分割, #584) |
| `tools/shimx/REPORT_CAB-214.md` | ~141 | shimx §11 (CAB-214: vreg reg.c 取込 + username 統一) + §12 (follow-up 後始末 3 件) 全文 (REPORT.md から分割, #584) |
| `tools/shimx/REPORT_SHX-T8.md` | ~60 | SHX-T8 (#175): 序数 import・Crypt・CP932 (REPORT.md §15 から分割) |
| `tools/shimx/REPORT_SHX-T7.md` | ~84 | SHX-T7 (#173): 署名正規化 IR pass + ゲート (REPORT.md §16 から分割) |
| `tools/shimx/BACKLOG.md` | ~540 | shimx の未解決一覧 |
| `tools/shimx/pathreg/REPORT.md` | ~200 | パス写影/レジストリ永続化の shimx 側インタフェース接続 |
| `tools/shimx/pathreg/REPORT_CAB-271.md` | ~230 | CAB-271: default mount table の遅延ロード |
| `tools/startup/REPORT.md` | ~85 | FL 起動シーケンス / 子プロセス / ゲート / レジストリ / スタブ計画 |
| `tools/startup/helpviewer/REPORT.md` | ~185 | FL の Help 起動経路 (静的解析) + Help を sandbox iframe に出す viewer / error-offline.html 差替 |
| `tools/startup/glue/REPORT.md` | ~200 | THostInstance + CreateFruityInstance 呼出 + 終了処理 |
| `tools/startup/keyfix/REPORT.md` | ~165 | vreg low-key 112 エントリ確定 + username 二重表記の統一 |
| `tools/startup/loadpaths/REPORT.md` | ~245 | ST-T14 (#39): 言語 .moe (暗号化 .mo) の形式・復号・ロード経路、スキン/Artwork/Help の読み手関数と起動/操作時の判定、VFS 配置 group と tier 差分、§8 (#590) 言語検索パス服務の実体・不在時挙動の静的確定 |
| `tools/startup/uilang/REPORT.md` | ~160 | ST-T19 (#591): GetUserPreferredUILanguages の FL 側呼び方・分岐 (zh のみ Program language 自動書込み) と shimx 返値の実測、lang-svg の参照元 (TToolbarForm.FlagBtnPaint)、Windows 標準フォントの要求一覧と代替案 |
| `tools/startup/pump/REPORT.md` | ~110 | user32 ポンプ shim (C) + runtime RING ABI 結線 |
| `tools/startup/vreg/REPORT.md` | ~145 | 仮想レジストリ shim + 登録済み seed |
| `tools/startup/vreg/ilreg/REPORT.md` | ~85 | 0x10c7cd0 登録パーサ / ILRegKey 書式解読 |
| `tools/startup/license_obs/REPORT.md` | ~209 | 登録フラグ byte[0x14f84a8] の全サイト列挙 + gradeChar のサイト列挙 (連続形/レジスタ追跡形; 下限) + 0x10c7cd0 の実機械語実行 (ST-T11 #107) + unit 初期化後の ILRegKey 非空観測 (ST-T15 #525) |
| `tools/startup/winstubs/REPORT.md` | ~100 | 起動 critical Win32 API の fail-soft stub |

### host / gui / audio / assets

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/runtime/REPORT.md` | ~155 | ブラウザ実行基盤 |
| `tools/runtime/rt10/REPORT.md` | ~190 | 実 FLEngine x64c lift (126MB wasm) の Chrome 起動時間・帯域・tier-up・boot ループ soak (RT-10 #128) |
| `tools/hostbridge/REPORT.md` | ~95 | Fruity Wrapper の VST2 ロード経路解析 + wasm 同梱プラグイン表 |
| `tools/hostbridge/cb/REPORT.md` | ~145 | shimx R2 コールバック変換の実体接続 |
| `tools/hostbridge/h10/REPORT.md` | ~182 | Fruity Wrapper の wrapper chunk reader 解析 (record 1/30–32 の要否・id 57 の正体・212 flags) |
| `tools/hostbridge/h2/REPORT.md` | ~150 | hostbridge surrogate の駆動と ott_run 接続 |
| `tools/hostbridge/h6/REPORT.md` | ~80 | web UI G1: OTT .rsrc PNG 抽出 + 宣言的ノブ UI + effEdit* 結線 |
| `tools/hostbridge/lowbase/REPORT.md` | ~125 | VA 敷設 base 可変化 (+ `x64c/` に x64c ラッパ 3 本目: `x64c/lb_x64c.py` は `tools/ott/lift/x64c.py` を無改変 import) |
| `tools/hostbridge/nfo/REPORT.md` | ~148 | Plugin database (`.nfo`/`.fst`) 書式解読 + 合成 DB 生成器。§10〜§12 は `REPORT_APPENDIX_A.md`・§13〜§14 は `REPORT_APPENDIX_B.md` に分割 |
| `tools/hostbridge/nfo/REPORT_APPENDIX_A.md` | ~112 | nfo §10〜§12 全文 (実機 OTT.fst / `.Plugins.ini`+VerifiedIDs 照合 / VST3 path 規則・KH magic・Massive X CID。#437 で無変更分割移動) |
| `tools/hostbridge/nfo/REPORT_APPENDIX_B.md` | ~150 | nfo §13〜§14 全文 (generateDb→wvfs 結線 e2e CAB-216 + 検収。#437 で無変更分割移動) |
| `tools/gui/REPORT.md` | ~204 | gui-shim (Win32 user32/gdi32 → OffscreenCanvas)。§9 = GUI-4 (#180) の要約 (全文は `REPORT_APPENDIX.md`)。§10 = GUI-5 (#181) 24/8/4/1bpp DIB・mono DDB と wasm SIMD128 行カーネルの実測。§11 = GUI-9 (#186) GDI テキストの FreeType 描画 (内蔵 8×8 → FreeType 2.7)。§12 = GUI-12 (#489) headless host surface 画素 UAF の修正と 50 回連続 + ネガコン |
| `tools/gui/REPORT_APPENDIX.md` | ~69 | gui REPORT §9 (GUI-4 #180 WebGL2 present / 複数矩形 / rAF / seqlock) 全文 (250 行上限のため無変更で分割移動) |
| `tools/gui/shimx_coexist/REPORT.md` | ~110 | shimx weak × gui 強定義の共存リンクと Web 実装接続 (ShellExecute/ファイルダイアログ/D&D) (#172) |
| `tools/audio/REPORT.md` | ~100 | ASIO/WASAPI/DirectSound → AudioWorklet + SAB リング |
| `tools/audio/REPORT_MIDI.md` | ~65 | AU-3 (#188) Web MIDI shim の検証全文 (REPORT.md §13 から分割) |
| `tools/audio/asio/REPORT.md` | ~200 | IASIO COM アダプタ + 120s soak |
| `tools/audio/wl/REPORT.md` | ~75 | AU-8 (#194): ring 方式 vs worklet 直走行の遅延比較 (テスト音ミキサ代役) + FLEngine スレッド/待機面の静的見積り |
| `tools/assets/REPORT.md` | ~125 | 314MB 級 wasm asset の chunk ローダ + 二段キャッシュ |
| `tools/assets/wvfs/REPORT.md` | ~145 | 書込可能 OPFS VFS |
| `tools/assets/serum2/REPORT.md` | ~70 | SR-6 (#70): Serum 2 コンテンツの manifest + LazyVfs 配信 + wasm libFLAC 復号の node 層 e2e (検証範囲と未解決) |
| `tools/assets/deploy-manifest/REPORT.md` | ~60 | 配備 manifest 生産側 (05-stage 契約) |
| `tools/python/REPORT.md` | ~240 | CPython wasm + flapi/MCP 解析 + ブリッジ設計。§7c (ilmcp, PY-3 #82)・§9 (下流チケット案 T1〜T9) は要約のみで全文は `REPORT_APPENDIX.md` に、§PY-12 (#587) は要約のみで全文は `REPORT_PY12.md` に、§PY-13 (#588)・§12/§13 (#81 kwargs 署名の静的復元)・§14 (#79 Piano roll) は要約のみで全文は `REPORT_APPENDIX.md` に分割 |
| `tools/python/REPORT_PY12.md` | ~46 | PY-12 (#587): `_flhost` の per-module state 化・サブインタプリタ採用判断の実測 (REPORT.md の PY-12 節の全文。250 行上限のため分離) |
| `tools/python/REPORT_APPENDIX.md` | ~216 | python REPORT の分割移動節の全文: §7c (ilmcp 9 関数 PY-3 #82: 引数規約・検証・仮定・未解決)・§9 下流チケット案 T1〜T9・§PY-13 (build_flpy.sh の env 化 #588)・§12/§13 (PY-9 b kwargs 署名復元・wasm 回帰・未解決 #81)・§14 (Piano roll scripting #79 の全文) (250 行上限のため無変更で分割移動) |
| `tools/python/REPORT_PY2.md` | ~76 | PY-2 (#83/#115, REPORT §7d 本体の全文): CPython と flapi provider の同一 wasm 静的リンク・往復コスト・`Py_*` 動的束縛 110 名の対応表・スレッド/GIL 方針 |
| `tools/python/REPORT_APPENDIX.md` | ~50 | python REPORT §PY-13 (build_flpy.sh の env 化 #588) と §12/§13 (PY-9 b kwargs 署名復元・wasm 回帰・未解決 #81) の全文 (250 行上限のため無変更で分割移動) |
| `tools/flp/REPORT.md` | ~120 | FLP/FST パーサ・ライタ・往復コーパス |
| `tools/plugins/REPORT.md` | ~115 | Fruity プラグイン 141 種 wasm 化マップ (カウントの正本) |
| `tools/plugins/f2/REPORT.md` | ~239 | PLG-F2 eq-filter 11 本: 固有閉包 lift の再現と間接 call 脱落の監査 (#199)、icall 復元の batch_lift 接続と回帰ゲート (#514, §7)、leaf 23 関数の関数単位差分試験の結論 (#515, §8)。§8 の詳細は `REPORT_APPENDIX.md` |
| `tools/plugins/f2/REPORT_APPENDIX.md` | ~140 | f2 REPORT §8 全文 (PLG-F2-3 #515: 23 関数表・ARTIFACT 表・NC 詳細・限界・再現・実測時間)。250 行上限のため無変更で分割移動 |
| `tools/plugins/hostx/REPORT.md` | ~145 | PLG-X host 統合 / big3p 12 本の方針決定 (lift する 6 / しない 2 / ユーザ判断 4) と閉包 lift の再現・間接 call 脱落の監査 (#210) |
| `tools/plugins/g1/REPORT.md` | ~250 | PLG-G1 synth-simple + drum-synth 14 本: 閉包 lift・host/kernel/間接 call 監査・C++ DLL 7 本・gate とネガコン (#206) |
| `tools/plugins/g1/REPORT_APPENDIX.md` | ~30 | g1 REPORT §9 旧版 (検証起点 86ca2d5、#539 取り込み前の 3 run・NC 詳細) の全文 (250 行上限のため分割移動) |
| `tools/plugins/framework/REPORT.md` | ~520 | TFruityHost shim 実装と検収 |
| `tools/plugins/p0c/REPORT.md` | ~665 | kernel 表妥当性検証 + f80 assessment |
| `tools/plugins/slayer_engine_ia32/REPORT.md` | ~130 | FL Slayer x86 engine (block22434 = Slayer_Engine.dll) の ia32 decode 基準値 (#674 中間): 線形掃引の実測・gate C1〜C4・ネガコン N1〜N3・objdump 検算 |
| `tools/shared/REPORT.md` | ~295 | FL Shared ライブラリの分類・IPP 実測・OSS wasm 再ビルド・プロプラ lift PoC |
| `tools/shared/oss/sidemod/REPORT.md` | ~60 | FFmpeg/LAME を差し替え可能な side module として再ビルド + GPL 混入検出 (LGL-4) |
| `tools/shared/oss/blend2d/REPORT_SIMD.md` | ~60 | Blend2D wasm `-msimd128` 試験 (T-SH-02, #146) の実測詳細・ネガティブコントロール・前版の実測・未解決の起票先 (`tools/shared/REPORT.md` §3.3 から分割移動) |

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
| `tools/targets/serum2/host/REPORT.md` | ~110 | Serum 2 最小 VST3 host |
| `tools/targets/serum2/license/REPORT.md` | ~160 | Serum2 認可機構の呼出点マップ |
| `tools/targets/serum2/license/authstub/REPORT.md` | ~125 | authorization stub 設計・実装 |
| `tools/targets/serum2/sr4/REPORT.md` | ~110 | SR-4 (#75) DSP 段階 lift 第 1 段: vtable root 56 関数の対象表 + pilot lift 9 本 (実機 vs wasm 差分) + strict gate + ネガコン |
| `tools/targets/massivex/REPORT.md` | ~160 | Massive X 事前解析 + ライセンス呼出点マップ |
| `tools/targets/massivex/dsp/REPORT.md` | ~220 | Massive X DSP closure 特定と lift 計画 |
| `tools/targets/kilohearts/REPORT.md` | ~200 | Kilohearts インストーラ解析 + snap-in lift 可否 |
| `tools/targets/kilohearts/license/REPORT.md` | ~125 | HeartCore ライセンス層の呼出点特定 |
| `tools/targets/kilohearts/license/KH9_REPORT.md`・`KH10_REPORT.md`・`KH11_REPORT.md`・`VERIFY_CAB247.md` | ~125/105/115/185 | KH-9/10/11 実施記録と CAB-247 検証 |
| `tools/targets/kilohearts/snapins/REPORT.md` | ~200 | KH 共通基盤 lift + SnapinMasterDsp ホストハーネス |
| `tools/targets/kilohearts/ui_eval/REPORT.md` | ~135 | KH-7 Kilohearts UI (Skia CPU ラスタ) → M7 HUD 接続可否評価 |
| `tools/targets/freshair/REPORT.md` | ~145 | Fresh Air インストーラ解析 + lift 可否 |
| `tools/targets/freshair/lift2/REPORT.md` | ~210 | Fresh Air Compressor/Filter/制御層 lift (§12 は `REPORT_APPENDIX_FA4.md` に分割移動) |
| `tools/targets/freshair/lift2/REPORT_APPENDIX.md` | ~120 | lift2 FA-10 (#666): ctrl 工程 FAILED の epf 素材切り分け (同一コード A/B)・rep movs/stosw の実装と e2e 未実行の実測・未解決 FA-11/FA-12 (REPORT §12 から参照) |
| `tools/targets/freshair/lift2/REPORT_APPENDIX_FA4.md` | ~50 | lift2 REPORT §12 全文 (FA-4 #51: チェーン構成 / マクロ→子パラメタ ID 写像)。250 行上限のため無変更で分割移動 |
| `tools/targets/freshair/lift2/REPORT_FA7.md` | ~70 | FA-7 (#452): macro 子 param ID 0x157/0x158/0x15a の Filter descriptor 同定 (model 層 setter 実測) |
| `tools/pm/REPORT.md` | ~120 | PM 運用の実測 (PR 件数・PR とチケットの対応・Project Status・Actions run 集計)。RETRO・DIRECTIVES の数値の正本 |
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
| `docs/STATUS.md` | **技術進捗の正本** (MS 番号・サブシステム 1 行ステータス・次の一手)。チケット状態は Project V2 が正本 | 測定値・数値の詳細 (REPORT へのリンクにする) |
| `docs/DECISIONS.md` | ADR: 方式決定・理由・日付 | 測定値・手順の詳細 |
| `docs/WORKFLOW.md` | subagent 運用・PR・レビュー・検収・自己点検・**AREA 一覧** | 技術的な実装手順・測定値 |
| `docs/REFERENCES.md` | 外部ソース・素材・ツール・**vendored 台帳**。**repo 外絶対パスはここだけ** | repo 内パス・技術内容 |
| `docs/pm/DIRECTIVES.md` | 依頼者 (user) 指示の**逐語原文**と PM の解釈・反映先 | 原文の改変 (追記のみ)・測定値 |
| `docs/pm/RETRO_2026-10-13.md` | Actions 移行後 2 日間のショートレトロ (事実・原因・対策。依頼者指示 121) | 測定値 (正本は `tools/pm/REPORT.md`。本書は結論と link のみ)・指示の逐語原文 (`DIRECTIVES.md` が正本)・repo 外絶対パス |
| `tools/pm/REPORT.md` | PM 運用の実測の**正本** (PR 件数・PR とチケットの対応・Project V2 Status・Actions run 集計。基準時刻と取得方法を併記) | 技術実装・指示の逐語原文・チケット状態の判断 (`STATUS.md`・Project V2 が正本) |
| `docs/pm/README.md` | `docs/pm/` の索引 (3 ファイルの役割のみ) | DIRECTIVES の内容の繰り返し・分析内容 |
| `docs/pm/PREDECESSOR_ANALYSIS.md` | 解任された前任 PM セッションの分析 (混乱の原因・証拠・再発防止ルールへの反映) | 指示の逐語原文 (`DIRECTIVES.md` が正本)・状態や未解決事項 (`STATUS.md`・`HANDOFF` が正本)・repo 外絶対パス |
| `docs/LEGAL.md` | ライセンス/規約上の運用制約と事実整理 | 技術実装・数値実測 |
| `docs/LEGAL_TERMS_LEDGER.{json,md}` | 各社規約の取得台帳 (取得日・版表記・正規化テキストの SHA-256)。`.json` が正本、`.md` は自動生成 | 規約本文・手編集 (`pnpm terms-watch` が更新) |
| `docs/DOC_MAP.md` | 本書。REPORT.md 索引・行数上限ルール・自動生成一覧・本章 | 技術内容・測定値 |
| `docs/DEFECTS.md` | lift silent miscompile 類型 D1a〜D17 (横断正本) | 個別ケースの詳細 (report 側) |
| `docs/HANDOFF/<日付>.md` | 引継ぎ要約 (方針・ブロッカー・次の一手)。最新のみ保持 | 状態の正本 (STATUS.md へ)・数値の羅列 |
| `tools/<area>/REPORT.md` | **測定値・実測数値・検証結果の単一の正本** (日本語/英文を問わず) | なし (ここが正本) |
| `tools/<area>/README.md` | **ナビゲーションのみ** (何をする dir か・E2E コマンド・関連ファイル) | 測定値・状態表 |
| `tools/<area>/{PROTOCOL,FORMAT,ABI,MANIFEST,STARTUP,GATES,BACKLOG,inventory}.md` | 仕様・台帳 (現状は良い設計・維持) | 測定値 |
| `tools/<area>/results/*.md`・inventory 系 | **自動生成**。先頭 1 行に `自動生成: <cmd>` | **人手編集禁止** |
| `deploy/` | デプロイ単独 (README からは 3 行 + リンクだけ残す) | 測定値 |

