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

## 5. 検証 (実測)

- 抽出 → 復号 → uidesc 解析を 1 コマンド系列で 1 回実行 (§1)。出力は §2-1 / §3 の数値と一致。
- ネガティブコントロール: テンプレート参照カウントは own def を差し引いて 0 (= 自己参照を数えていない)。定義件数 3 は `SpliceExpired`/`SpliceMaxLimit`/`SpliceRTO` の 3 名を列挙して確認。
- 範囲外: 実 VSTGUI 実行、wasm/canvas 上の表示、Machine ID、mac 版。
