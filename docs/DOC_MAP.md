# DOC_MAP — 全 `tools/**/REPORT.md` の索引

全 `REPORT.md`・主要ドキュメントの索引。**何がどこに書かれているか**の一覧。
行数は 2026-10-12 時点の概数。

- 原則: 測定値・実測数値は **`tools/<area>/REPORT.md` だけ** が単一の正本。
  外側 (`README.md`・`docs/STATUS.md`) は結論 1 行 + リンク。
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
| `tools/python/analysis/{flapi/FLAPI,mcp/MCP_TOOLS}.md` | 抽出 driver (repo 内 `tools/python/analysis/`) |

## 3. REPORT.md 索引

### 全体・デプロイ

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `deploy/REPORT.md` | ~120 | deploy/ を Workers Static Assets 構成へ改修した実測レポート |
| `deploy/README.md` | ~100 | デプロイ構成 (案 S) の正本・stage/deploy/access/verify 各 script |
| `deploy/RUNBOOK.md` | ~50 | 実デプロイの具体手順と確認項目 |
| `deploy/EDGE-SIM.md` | ~30 | edge-sim の調整一覧 |
| `tools/e2e/REPORT.md` | ~120 | ブラウザ E2E ハーネスと配信構成の実測 |
| `tools/hosting/REPORT.md` | ~135 | 既定ホスト名だけで COOP/COEP を成立させる配信構成 (案 S の根拠) |
| `tools/perf/REPORT.md` | ~150 | wasm 実時間性能・compile 時間・巨大 wasm 実験 |
| `tools/perf/PERF.md` | ~150 | 性能の設計メモ・読み替え注記 |

### 解析・lift 基盤

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/m2/REPORT.md` | ~230 | M2: function boundary 合意 / Delphi lift 品質 / shim inventory / wasm PoC |
| `tools/m3/REPORT.md` | ~100 | M3: 中規模 lift → wasm (純計算 4 関数 bit-exact) |
| `tools/m5/REPORT.md` | ~120 | M5: Delphi lift → wasm E2E + native bit-exact |
| `tools/liftlib/REPORT.md` | ~530 | 共通 lift 修復基盤の統合 (CAB-49/54/55/220/239/LIFTLIB-2) |
| `tools/flelift/REPORT.md` | ~155 | x64c を FLEngine 向けに汎用化 |
| `tools/flelift/boot/REPORT.md` | ~350 | FLE-2〜FLE-5: x64c lift による FLEngine boot 連鎖 |
| `tools/liftdiff/REPORT.md` | ~270 | flelift (x64c) 全数採点 + native 全起動の参照化 |
| `tools/icall/REPORT.md` | ~125 | 間接 call/jmp 落ち監査 + 復元 pass |
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
| `tools/ott/ACCEPTANCE_CAB138_CAB137.md` | ~210 | OTT CRT/entry 検収記録 |
| `tools/ott/ACCEPTANCE_CAB238_CAB135.md` | ~210 | OTT f7 既定化・AVX 検収記録 |
| `tools/m6/REPORT.md`・`tools/m7/REPORT.md`・`tools/m8/REPORT.md`・`tools/m9/REPORT.md`・`tools/m10/REPORT.md` | ~280/210/160/115/105 | 旧 RetDec 路線 M6〜M10 の経緯 (歴史) |

### FLEngine 起動

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/m11/REPORT.md` | ~110 | FLEngine_x64.dll 部分起動 PoC (stage 4/6・残 trap・次の一手) |
| `tools/m11/alloca/REPORT.md` | ~150 | alloca 縮退修正 (CAB-129) |
| `tools/m11/ldfix/REPORT.md` | ~165 | load 取り違え (値↔アドレス / 1 段 deref 脱落) IR 修復 pass |
| `tools/m11/shimx_link/REPORT.md` | ~165 | M11 × shimx リンク |

### shim / 起動

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/shim/README.md` | ~50 | Win32 shim コア (53 export) のナビゲーション |
| `tools/shimx/REPORT.md` | ~330 | Win32/CRT shim 拡張 |
| `tools/shimx/BACKLOG.md` | ~540 | shimx の未解決一覧 |
| `tools/shimx/pathreg/REPORT.md` | ~200 | パス写影/レジストリ永続化の shimx 側インタフェース接続 |
| `tools/shimx/pathreg/REPORT_CAB-271.md` | ~230 | CAB-271: default mount table の遅延ロード |
| `tools/startup/REPORT.md` | ~85 | FL 起動シーケンス / 子プロセス / ゲート / レジストリ / スタブ計画 |
| `tools/startup/glue/REPORT.md` | ~200 | THostInstance + CreateFruityInstance 呼出 + 終了処理 |
| `tools/startup/keyfix/REPORT.md` | ~165 | vreg low-key 112 エントリ確定 + username 二重表記の統一 |
| `tools/startup/pump/REPORT.md` | ~110 | user32 ポンプ shim (C) + runtime RING ABI 結線 |
| `tools/startup/vreg/REPORT.md` | ~145 | 仮想レジストリ shim + 登録済み seed |
| `tools/startup/vreg/ilreg/REPORT.md` | ~85 | 0x10c7cd0 登録パーサ / ILRegKey 書式解読 |
| `tools/startup/winstubs/REPORT.md` | ~100 | 起動 critical Win32 API の fail-soft stub |

### host / gui / audio / assets

| パス | 行数目安 | 何が書かれているか |
|---|---:|---|
| `tools/runtime/REPORT.md` | ~90 | ブラウザ実行基盤 |
| `tools/hostbridge/REPORT.md` | ~95 | Fruity Wrapper の VST2 ロード経路解析 + wasm 同梱プラグイン表 |
| `tools/hostbridge/cb/REPORT.md` | ~145 | shimx R2 コールバック変換の実体接続 |
| `tools/hostbridge/h2/REPORT.md` | ~150 | hostbridge surrogate の駆動と ott_run 接続 |
| `tools/hostbridge/lowbase/REPORT.md` | ~125 | VA 敷設 base 可変化 |
| `tools/hostbridge/nfo/REPORT.md` | ~375 | Plugin database (`.nfo`/`.fst`) 書式解読 + 合成 DB 生成器 |
| `tools/gui/REPORT.md` | ~100 | gui-shim (Win32 user32/gdi32 → OffscreenCanvas) |
| `tools/audio/REPORT.md` | ~100 | ASIO/WASAPI/DirectSound → AudioWorklet + SAB リング |
| `tools/audio/asio/REPORT.md` | ~200 | IASIO COM アダプタ + 120s soak |
| `tools/assets/REPORT.md` | ~125 | 314MB 級 wasm asset の chunk ローダ + 二段キャッシュ |
| `tools/assets/wvfs/REPORT.md` | ~145 | 書込可能 OPFS VFS |
| `tools/python/REPORT.md` | ~120 | CPython wasm + flapi/MCP 解析 + ブリッジ設計 |
| `tools/flp/REPORT.md` | ~120 | FLP/FST パーサ・ライタ・往復コーパス |
| `tools/plugins/REPORT.md` | ~115 | Fruity プラグイン 141 種 wasm 化マップ |
| `tools/plugins/framework/REPORT.md` | ~520 | TFruityHost shim 実装と検収 |
| `tools/plugins/p0c/REPORT.md` | ~665 | kernel 表妥当性検証 + f80 assessment |
| `tools/shared/REPORT.md` | ~295 | FL Shared ライブラリの分類・IPP 実測・OSS wasm 再ビルド・プロプラ lift PoC |

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
| `tools/targets/massivex/REPORT.md` | ~160 | Massive X 事前解析 + ライセンス呼出点マップ |
| `tools/targets/massivex/dsp/REPORT.md` | ~220 | Massive X DSP closure 特定と lift 計画 |
| `tools/targets/kilohearts/REPORT.md` | ~135 | Kilohearts インストーラ解析 + snap-in lift 可否 |
| `tools/targets/kilohearts/license/REPORT.md` | ~125 | HeartCore ライセンス層の呼出点特定 |
| `tools/targets/kilohearts/license/KH9_REPORT.md`・`KH10_REPORT.md`・`KH11_REPORT.md`・`VERIFY_CAB247.md` | ~125/105/115/185 | KH-9/10/11 実施記録と CAB-247 検証 |
| `tools/targets/kilohearts/snapins/REPORT.md` | ~200 | KH 共通基盤 lift + SnapinMasterDsp ホストハーネス |
| `tools/targets/freshair/REPORT.md` | ~145 | Fresh Air インストーラ解析 + lift 可否 |
| `tools/targets/freshair/lift2/REPORT.md` | ~200 | Fresh Air Compressor/Filter/制御層 lift |

## 4. 横断正本 (`docs/`)

| ファイル | 単一責任 |
|---|---|
| `README.md` | 何のプロジェクトか / docs・tools の地図と索引 / 開発コマンド / デプロイ 3 行要約 (測定値なし) |
| `AGENTS.md` | エージェント規約・ドキュメント責務マップ・命名規則・禁止事項 |
| `docs/ARCHITECTURE.md` | パイプライン全体像 |
| `docs/STATUS.md` | **状態の唯一の正本** (MS 番号再定義・サブシステム 1 行ステータス・次の一手) |
| `docs/DECISIONS.md` | ADR (方式決定と理由) |
| `docs/WORKFLOW.md` | subagent 運用・PR・レビュー・検収 |
| `docs/REFERENCES.md` | 外部ソース・素材・ツール・vendored 台帳 (絶対パスはここだけ) |
| `docs/LEGAL.md` | ライセンス/利用規約上の運用制約 |
| `docs/DOC_MAP.md` | 本書。REPORT.md の索引と行数上限ルール |
| `docs/DEFECTS.md` | RetDec lift の silent miscompile 類型 D1〜D16 (横断正本) |
| `docs/HANDOFF/<日付>.md` | 日付付き引継ぎ (最新のみ保持) |

