# REPORT — HB-H6 (#100): web UI G1 — OTT .rsrc PNG 抽出 + 宣言的ノブ UI + effEdit* 結線

親: #24 (HB-H13) / 設計: `HOSTBRIDGE.md` §2.6 G1 / 土台: #92 (H2, surrogate harness)・#91 (lowbase)。
既知類型との関係 (`docs/DEFECTS.md`): 該当なし (lift 欠陥ではなく host 側 UI 結線)。検証起点: main 086c18a。

## 0. 結論 (先出し)

- **判定: 部分達成 (Refs #100)。** タイトルの 3 項目はいずれも実装・検証したが、**実 lift 済み OTT guest 上での結線検証は未実施** (FakeOtt guest + 実 host wasm による検証。§4 未解決 1)。
- **検収 1 コマンド**: `bash tools/hostbridge/h6/h6_e2e.sh` → **37/37 PASS** (broken 0)。
- **(1) PNG 抽出**: `rsrc_extract.mjs` (依存なし, PE リソース木 3 階層) が `OTT_vst2_win64.dll` の .rsrc から全 8 resource を列挙、うち **PNG 4 件 / 377,397 B** (HOSTBRIDGE §2.6 の「~377 KB」を実測で確定)。
  内訳 `PNG/128` 620×880 RGB (背景) / `PNG/129` 80×9680 RGBA (**121 frame × 80×80 の針フィルムストリップ**) / `PNG/130` 80×102 RGBA (ノブ本体+影) / `PNG/131` 80×80 RGBA (ring)。
  他 4 件: `T8` TTF 1・`T7` bin 1・VERSION・MANIFEST。別算法 (`verify_rsrc.py`: 木を使わず DLL を生走査し PNG chunk を CRC 付きで IEND まで辿る) と PNG 集合 (件数・sha256) が一致。
- **(2) 宣言的ノブ UI**: `ott.ui.json` (manifest) + `ui_model.mjs` (表示リスト/ヒットテスト/ドラッグ) + 描画 2 種 (`soft_render.mjs` = e2e 画素検証用, `canvas_renderer.mjs` = ブラウザ Canvas2D)。
  control は **param 名**で束縛し effEditOpen 時に `effGetParamName` で index 解決 (index を焼かない)。knob 6 + 水平 slider 3 = **9 control / 20 param 中 9 束縛・11 未束縛** (§3)。
- **(3) effEdit* 結線**: `editor_g1.mjs` の `HostBridgeG1` (poc/hb_bridge.mjs を**継承のみ・無改造**) が dispatcher op 13/14/15/19 を guest に転送せず UI 側で処理し、proxy AEffect.flags に HasEditor を立てる。UI 操作は guest `setParameter` + `audioMasterAutomate(op 0)` upcall。
  editor 未登録の plugin は従来経路 (G0 互換) のまま。

## 1. 実測 (`h6_e2e.sh`, コミット済み HEAD `f655fff`)

runner 4 vCPU / node v22.23.3 / load average 0.03 (1 分値, 3 回実行直後に \`/proc/loadavg\` で 1 回測定)。

| 区分 | 検査 | 結果 |
|---|---|---|
| R1 | .rsrc 木の PNG | resources=8, PNG=4, 計 377,397 B |
| R2 | manifest pin | 4 資産の sha256 4/4・寸法 4/4 一致 |
| R3 | PNG 整合 | 全 chunk 20 の CRC 不一致 0、`png_lite` 全 4 件デコード |
| R4 | 別算法照合 | python 生走査 PNG 4 件と sha256 集合一致 |
| M1/M2 | モデル | 9 control 解決 (missing 0) / frame = round(v×120): 0→0, 0.25→30, 0.5→60, 1→120 |
| E1 | HasEditor | proxy flags=0x19 (guest は 0x18 のまま) |
| E2 | effEditGetRect | ERect = {top 0, left 0, bottom 880, right 620} (manifest), 戻り 1 |
| E3/E3b | effEditOpen | 戻り 1, HWND(0x5a5a) が surface に渡る, 初回描画 1 回, 表示リスト 22 op (bg 1 / body 6 / tick 6 / text 6 / slider 3) |
| E4 | 初期値取込 | getParameter 経由で Depth=0.25→frame 30, Time=0.5→frame 60。readout は `effGetParamDisplay` 由来 |
| E5 | 非転送 | op 13/14/15/19 は FakeOtt に 0 件到達 |
| E6 | ドラッグ | Depth を y 205→105 で 0.25→0.75 (200 px/全域)、guest param・host `getParameter` 往復とも f32 bit 一致、host が `audioMasterAutomate` を UI 変更回数と同数受信 |
| E7 | slider/clamp | Gain H: x=300 → (300−40)/510。上限クランプ 1.0 |
| E8 | effEditIdle | host の setParameter だけでは再描画せず、idle で getParameter を引き直して +1 描画 (Time=0.8→frame 96)、変化無し idle は再描画 0 |
| P1/P2 | 画素 | Depth 0→1 の差分画素は knob 80×80 内のみ (内 230 / 外 0)。tick 最終 frame の不透明画素 30/30 が出力 RGB と一致 (別算法) |
| C1 | Canvas2D | mock ctx で 22 op → drawImage 13 / fillText 6 / fillRect 3 |
| E9〜E11 | close/再open/未登録 | close で surface.close 1 回・以後 idle 描画 0、再 open 可、二重 open は 0、非 editor opcode は従来転送、未登録 plugin は HasEditor 立たず op 13/14 は guest へ |

所要: `h6_e2e.sh` 全体 0.35〜0.39 s (n=3), `h6_check.mjs` 本体 219〜256 ms。

**ネガティブコントロール**: N1 bg の 1 byte 反転 → sha256 pin 不一致 (検出)。N2/N3 manifest の param 名を 1 文字破損 → `missing=["Depthh"]` / effEditOpen=0・opens 0。
開発中の実測: 初版は E6d (automate 受信数) が 0 件で FAIL (HostInfo.am_calls オフセット誤り 244→240 を修正)、E11 が FAIL (未登録 plugin でも op 13/14 を横取りしていた実バグ。`edDesc` 判定を追加)。

## 2. 設計メモ

- **editor は host 側の web UI**: OTT 本来の GUI (JUCE/VSTGUI) は lift しない (G2 は対象外)。h2 の `ovr_editor_null` により guest の editor 系 opcode は 0 返しなので、G1 は bridge 層で完結する。
- **HWND**: `effEditOpen` の ptr は不透明値として `surface(hwnd)` ファクトリへ渡す (M7 仮想 window 識別子の結線点)。
- **UI → plugin**: VST2 の `setParameterAutomated` と同じ (guest `setParameter` + host へ `audioMasterAutomate`)。Wrapper 側の automate 受信 (`fw:0x7abca0` 汎用ハンドラ) との結線は H4。
- **座標**: manifest の knob/slider 座標は背景 PNG の文字ラベル位置からの目視推定 (実測ではない)。snapshot (`work/editor_snapshot.png`, gitignore) で配置の整合を目視確認した。
- **資産は非再配布**: 抽出物は `h6/work/` (gitignore)。commit したのは manifest の sha256/寸法 pin のみ (`docs/LEGAL.md` 方針)。

## 3. 範囲 / 範囲外

- 範囲: PNG 抽出、宣言的 UI モデル、effEdit* 結線、headless 画素検証、Canvas2D 呼出列の検証。
- **未束縛 11 param**: Bypass / Clean XOV / Thresh L,M,H / Byp Upwd L,M,H / Byp Dnwd L,M,H (名前表は `poc/plugin_ott_entry.c` の 19 名に h2 G4 の p0="Bypass" を前置した**推定**。実 guest の名前列で確定する)。H/M/L の slider は Gain 系に束縛した暫定割当 (OTT 本来の帯域 UI と一致する保証なし)。
- 範囲外: テキストのラスタライズ (soft_render は text 非描画; Canvas は TTF `T8` を FontFace で読む想定、未実装)、ホバー/ダブルクリック既定値/ホイール、実ブラウザ。

## 4. 未解決

| # | 未解決 | 影響 | 起票先 |
|---|---|---|---|
| 1 | **実 lift 済み OTT guest (h2 module) 上での結線検証が未実施**。検証は FakeOtt (20 param・editor 0 返し) + 実 host_vst2.wasm。h2 harness は `work-m6-ott work-liftlib toolchain-retdec fl-win64` 級の素材が必要で、本 run の素材 (plugins-ott / analysis-ott-binaries / toolchain-emsdk) では動かせない | param 名 20 件の実値で manifest が全解決することが未確認 (E4 の名前列は推定) | #100 にコメント (follow-up: `oc_artifacts: plugins-ott analysis-ott-binaries toolchain-emsdk toolchain-retdec work-m6-ott work-liftlib fl-win64` で h2 module に `HostBridgeG1` を適用し N 件 resolve を確認) |
| 2 | 実ブラウザ (Canvas/FontFace/PointerEvent) 未検証。mock ctx のみ | 描画/入力の実機差 | H8 (\`HOSTBRIDGE.md\` §5, 未起票なら PM 判断) に統合 |
| 3 | M7 仮想 window (HWND) と surface の結線は不透明値のまま | FL 側 Wrapper 結線時に確定 | H4 |
| 4 | 11 param の UI (Bypass/Thresh/Byp 系) | G1 の機能網羅 | #100 follow-up (実 guest の名前確定後) |
| 5 | `HOSTBRIDGE.md` §5 の H6 行/`DOC_MAP` 反映 | 索引 | 本 PR で DOC_MAP に 1 行追加 (STATUS は PM) |

## 5. 再現

```sh
bash tools/hostbridge/h6/h6_e2e.sh      # 前提: emsdk, python3, node>=22, OTT_vst2_win64.dll ($OTT_DLL か $PLUGINS_DIR/ott/binaries/)
node tools/hostbridge/h6/rsrc_extract.mjs <OTT_vst2_win64.dll> tools/hostbridge/h6/work/rsrc   # 抽出のみ
```

素材: `oc_artifacts: plugins-ott analysis-ott-binaries toolchain-emsdk`。
