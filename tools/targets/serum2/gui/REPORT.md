# REPORT — [SR-7 #68] Serum 2 GUI 戦略: 残留 2 点の実バイナリ確認

- 日付: 2026-10-13 / 親: #15 [PLG-E] / 前段: `tools/targets/serum2/REPORT.md` §6.1 GUI 行・§9 T7、`license/authstub/REPORT.md` §4 N7
- 範囲: 本 dir (`tools/targets/serum2/gui/`) のみ新設。既存 REPORT.md は無変更 (250 行上限)。
- 既知類型との関係 (`docs/DEFECTS.md`): 該当なし (lift 前の静的確認。silent miscompile 類型は未触)。
- 検証起点: 本 PR の commit (クリーン HEAD の worktree `68-serum2-gui-strategy`)。入力 `Serum2_win64.vst3` sha256 `501e7bb3…5283` (19,236,864 B, REPORT §11 と一致)。

## 0. 結論 (先出し)

| 残留 | 判定 |
|---|---|
| (1) Splice 3 テンプレートの実体化分岐 | **未特定のまま**。確定したのは「uidesc 内の定義は 3 件・参照 0 件」「SpliceController の 0x180796320 は support 記事 URL を開くボタン処理」まで。実体化を行う関数は静的に見つけられなかった |
| (2) overlay_demo_version(_mini) | **表示経路の参照は bitmap 登録の 1 件のみ** (template の子・key からの参照は 0)。実体化の経路は無いと判断でき、authstub N7 の「実害なし」と整合 |

GUI 戦略 (a) 全 lift / (b) upstream VSTGUI 再構築の比較と判定は **本 run では行っていない** (§9 T7 の範囲)。

## 1. 再現手順と入力確認

```sh
# 素材: fl-win64 ではなく plugins-serum2 の Install_Xfer_Serum2_2.1.5.exe を使用
7z x -y -owork/exe_extract "$RUNNER_TEMP/plugins-serum2/Install_Xfer_Serum2_2.1.5.exe"
cp -f 'work/exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' work/Serum2_win64.vst3
python3 gui/extract_uidesc.py work/Serum2_win64.vst3 work/uidesc.json     # uidesc bytes 2093822 (REPORT §2 と一致)
python3 gui/decode_splice_url.py work/Serum2_win64.vst3                  # 0x180796320 の復号文字列
```

- 依存: `pefile` `capstone` `zstandard` (`python3 -m pip install --break-system-packages`)。
- 実測: sha256 `501e7bb3dd9cafe4…` (先頭 16 桁) が REPORT §11 の入力と一致。uidesc 抽出 **2,093,822 B** (REPORT §2 と一致)。
- 所要 (real, 逐次, load 未計測):
  - 今回 run (HEAD `0dcf5f4e` + 修正, 2026-10-13): `extract_uidesc.py` **2.97 s** / `decode_splice_url.py` **3.00 s** (別プロセス・各 1 run)。
  - 前回 run (HEAD `d692129c`, 修正前の値): 抽出 + 復号 + uidesc 解析 = 6.82 s。今回 run との差は環境差 (同一 run で再測定した値のみ採用)。

## 2. 残留 (1) Splice 3 テンプレートの実体化分岐

### 2-1. uidesc 内の定義と参照 (実測)

| 項目 | 結果 |
|---|---|
| `templates` 件数 | 123 |
| `SpliceRTO` / `SpliceExpired` / `SpliceMaxLimit` の定義 | 各 1 件。`class: CViewContainer`・`sub-controller: SpliceController`・`size: 1190, 740` |
| 他の template の子・属性からの参照 | **0 件** (own def を除く `"Splice*"` 文字列 count = 0) |
| 平文バイナリ内の出現 | **0 件** (ASCII・UTF-16LE とも。名前は zstd 圧縮 uidesc の中にだけ存在) |

→ 静的な名前参照では実体化元を辿れない。実行時の template 辞書引き (文字列キー) か、テーブル index 経由の可能性がある。

### 2-2. SpliceController のメソッド候補 (実測)

- `0x180796320` (size 358): 状態フィールド `[rsi+0x168/0x178/0x170/0x160]` の比較で 4 分岐し、`0x1801bc300` (ShellExecuteEx ラッパ, authstub §4) か `0x1800ccf60` / `0x1800cbb90` を呼ぶ。
- **復号結果 (`gui/decode_splice_url.py`)**: `https://support.splice.com/en/articles/10055412-serum-2-license-instructions` (76 文字・全文)。→ Splice 関連の「support 記事を開く」ボタン処理と判定 (high)。
- 復号の範囲: `0x180796320` の `movups xmmword ptr [rsp + 0x5d], xmm0` はバッファ offset 61 から 16 バイト (61〜76) を書く。バッファ長 76 の末尾 15 バイト (61〜75) を埋める。旧版は `off <= N - 16` (上限 60) でこの書き込みを捨てて文字化けしていた (旧出力 `...license-Ö×ØÙÚÛÜÝÞßàá`)。修正版は `0 <= off < N` で `min(16, N - off)` バイトを書く。
- `0x180796090` (size 587) は未解析。`0x180542a20` (size 3,105) は起動直後の初期化側と推定 (med)。いずれも実体化分岐の確定根拠ではない。

### 2-3. 未確定

実体化を行う関数 (state → template 名の選択) は**未特定**。`0x180796320` は「既に表示された Splice ビュー上のボタン処理」であって、ビューを選ぶ側ではない。

## 3. 残留 (2) overlay_demo_version(_mini)

| 項目 | 結果 |
|---|---|
| `templates` に `overlay_demo_version` を key とする定義 | **0 件** (`_mini` / `_fx_version` 系も同様) |
| 文字列の出現 | uidesc 内に `"path": "overlay_demo_version"` の bitmap 登録 1 件 (`overlay_demo_version_mini` ほか) |
| 参照元 (template 子) | 0 件 |

→ template として表示される経路は uidesc から見当たらない。bitmap 登録のみという authstub N7 の記述と一致する。

## 4. 残る作業 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (1) Splice テンプレートの実体化関数 (state → template 名) | authstub N7 の「非表示固定」が未検証。demo bit ≡ 0 で表示条件が偽になるかは実測不能 | #623 (SR-2c, 既存) |
| 残り 2 点の動的確認 (実 host で Splice 表示が出ないこと) | 静的確認のみ。実 VSTGUI 実行が必要 | #623 (SR-2c) / GUI lift 時 |
| GUI 戦略 (a) 全 lift / (b) upstream VSTGUI 再構築の比較 | 本 run 未実施。§9 T7 (2〜3 週調査) の本体 | 本 issue #68 の残作業 (Refs) |

## 5. GUI 戦略 (a) 全 lift / (b) upstream VSTGUI 再構築 の比較 (§9 T7)

### 5-1. 実測 (`gui/strategy_count.py` → `out/gui_strategy_count.txt`)

| 項目 | 実測 |
|---|---|
| 入力 | `work/uidesc.json` (2,093,822 B, §1 と同一)。templates 123 / bitmaps 344 |
| View クラス参照 | 817 件 / **103 種** (全 103 種がバイナリ RTTI に名前一致) |
| うち VSTGUI 標準名とみなした分 (`C` 接頭辞, ヒューリスティック) | 16 種 / **260 件** (`CViewContainer` 165 が大半) |
| うち Xfer 独自とみなした分 (その他, ヒューリスティック) | 87 種 / **557 件** (`HoverView` `XferAdvancedOptionMenu` `VectorKnob` `XferOnOffButton` ほか) |
| sub-controller | 159 件 / 61 種。RTTI 名一致 58 種。不一致 3 種 (`OscController2` `RoutingSlotController2` `RoutingSlotController6`) |
| VSTGUI `UIViewCreator` 系 RTTI | 39 件 (`VSTGUI::UIViewCreator::*Creator`) |
| GUI 関数 (closure, `out/closure_summary.json`, 静的・過大近似) | GUI root 836 / GUI closure 7,138 関数 (4.21 MB) / GUI のみ 3,217 関数 (1.92 MB) / DSP と共有 3,921 関数 (2.29 MB) |

注: 「C 接頭辞 = VSTGUI」「その他 = Xfer」は名前からの**推定**であり、個々の class の実体 (どの RTTI がどの .text に対応するか) は未確認。RTTI 照合は部分文字列ではなく単語境界の一致のみ。

### 5-2. 比較

| 観点 | (a) 全 lift | (b) upstream VSTGUI 再構築 + Xfer 固有ビューのみ lift/置換 |
|---|---|---|
| 対象量 | GUI closure 7,138 関数 / 4.21 MB (過大近似)。実数は動的トレース後 | VSTGUI 基盤 (推定 約 3,360 関数 / 692 KB, 本体 REPORT §3) は upstream ソースで置換。lift 対象は Xfer 固有 87 種 (557 参照) |
| 依存 | Win32 / D2D / DirectComposition を含む platform 層を lift するか、canvas へ差し替えるかが不明のまま | canvas platform を新規実装する前提。upstream VSTGUI の版は未確定 (SR-3 の cut 表に VSTGUI は未掲載) |
| 量の根拠 | 関数数・バイトは実測。ただし closure は間接呼出の取りこぼしを含み、真値は未確定 | 置換側の工数は未実測 (推定のみ) |
| 検証の取り方 | バイナリ同士の挙動比較が可能 | 参照 (実機) 表示との突合が必要。§4 の動的確認と同じ経路 |
| 既存資産 | host (§host/REPORT) で editor 生成まで到達。描画は未実施 | uidesc 展開 (§1) と PNG/TTF は既に取得可能 |

### 5-3. 判定 (推奨・確度付き)

- **推奨: (b)。** 根拠は実測の 2 点 (a) GUI closure 4.21 MB は DSP と 3,921 関数を共有し、lift 単独では DSP 側の切り分けも要る。(b) は uidesc の View 種が 103 と有限で、Xfer 固有は 87 種に限られる。
- **確度: 中。** (b) の工数・canvas platform の工数は**未実測**。VSTGUI 版の同定も未了のため、(b) を採るなら版確定を先にする。
- **残留 (1) Splice 実体化分岐** は (a)(b) どちらでも同じ未解決 (§2-3)。SpliceController は Xfer 固有ビューなので (b) では置換側で扱う。
- **PoC 境界 (次段)**: 最小 1 view (例 `CTextLabel` 系 + `XferOnOffButton`) を upstream VSTGUI で canvas 描画し、uidesc から 1 template を実体化する。ここまでを GUI 戦略の PoC とし、全 Xfer ビューの置換はこの後に起票する。

本 run では (a)(b) の工数見積もりを実測していないため、**判定は推奨止まり**。最終決定はユーザ判断。

## 6. 検証 (実測)

- `gui/strategy_count.py work/uidesc.json out/rtti_classes.txt` を 1 回実行 (0.09 s)。出力は `out/gui_strategy_count.txt` (691 B)。
- 入力の sha256 `501e7bb3dd9cafe4…` / 19,236,864 B は REPORT §11 と一致 (本 run で `plugins-serum2` の exe から再抽出)。
- uidesc 抽出 2,093,822 B (`extract_uidesc.py`, 3.55 s, 逐次)。

## 7. 検証 (前 run, 残留 2 点)

- 抽出 → 復号 → uidesc 解析を 1 コマンド系列で 1 回実行 (§1)。出力は §2-1 / §3 の数値と一致。
- ネガティブコントロール: テンプレート参照カウントは own def を差し引いて 0 (= 自己参照を数えていない)。定義件数 3 は `SpliceExpired`/`SpliceMaxLimit`/`SpliceRTO` の 3 名を列挙して確認。
- 範囲外: 実 VSTGUI 実行、wasm/canvas 上の表示、Machine ID、mac 版。

## 8. VSTGUI upstream 版の同定 (2026-10-13 run, §5-3 の未了分)

入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` から展開した `Serum2.vst3` (sha256 `501e7bb3dd9cafe4…`, 19,236,864 B)。gitignore 対象の `work/` に置いた。

| 観測 | 結果 | 判定 |
|---|---|---|
| VSTGUI ソースパス文字列 (`vstgui\lib\cframe.cpp` 等) | 存在。`uidescription/detail/uijsonpersistence.cpp` を含む | VSTGUI 由来の確認 (高) |
| `VSTGUI` / `vstgui` 文字列 | 計 2,358 件 (大半はパス・ログ用) | 版番号を含まない |
| `3.7.12` | `VST 3.7.12` (フォント表示付近の文字列, offset 16595120) | **VST3 SDK の版**。VSTGUI の版ではない |
| `3.19.3` / `9.1.5` / `2.0.20` / `2.0.24` | 版番号として単独出現 | VSTGUI と結び付く根拠は無い (未特定) |
| `kVstVersion*` / `VSTGUI_VERSION` 系 | 0 件 | 版定数は無い |

結論: **Xfer 版の VSTGUI の版は、バイナリの文字列からは同定できなかった。** 版確定には (1) upstream の各版 (4.x 系) の uidescription ソース (`uijsonpersistence.cpp` の有無と JSON 形式の差) と本バイナリの UIDescription JSON 読込関数を突き合わせる (2) 版ごとの `UIViewCreator` 名集合と §5-1 の 103 種 / RTTI 39 件を照合する、のいずれかが要る。どちらも本 run では未実施。

§5-3 の (a)/(b) 工数実測は本節の版同定を前提とするため、未実施のまま残す。

### 検証

- 本 run の再測定: **未実施**。`$RUNNER_TEMP/plugins-serum2/` が存在せず (`ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ)、上表の数値は前 run の実測値。本節の sha256 (`501e7bb3dd9cafe4…`) も前 run の記録で、本 run では照合していない。
- 前 run で使った grep の正確な式はログに残っていない。以下は再測定用に定義したもので、**表の数値との一致は未確認**。
- 抽出 (`tools/targets/serum2/` を cwd とする):
  ```sh
  7z x -y -owork/exe_extract "$RUNNER_TEMP/plugins-serum2/Install_Xfer_Serum2_2.1.5.exe"
  cp -f 'work/exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' work/Serum2_win64.vst3
  sha256sum work/Serum2_win64.vst3   # 完全な値を REPORT に追記する (前 run は先頭 16 桁のみ記録)
  stat -c %s work/Serum2_win64.vst3  # 19236864 の一致を確認
  ```
- 文字列走査 (grep 既定は大小区別あり。`VSTGUI` と `vstgui` は別々に数える):
  ```sh
  grep -aoE 'VSTGUI' work/Serum2_win64.vst3 | wc -l          # 大文字
  grep -aoE 'vstgui' work/Serum2_win64.vst3 | wc -l          # 小文字
  grep -aob 'VST 3\.7\.12' work/Serum2_win64.vst3            # offset (前 run の 16595120 と照合が必要)
  grep -aoE 'kVstVersion|VSTGUI_VERSION' work/Serum2_win64.vst3 | wc -l   # 版定数 (表の 0 件)
  ```
- 所要と load: **未計測** (PR 本文と揃える)。
