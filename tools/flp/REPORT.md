# tools/flp/REPORT.md — FLP/FST パーサ・ライタ・往復コーパス・比較オラクル設計

最終更新 2026-10-10 / 担当 L (flp-corpus) / 再現: `bash tools/flp/flp_e2e.sh` (exit 0 = 全 PASS)

## 0. 結論

- **TypeScript パーサ/ライタ (Node 26 / ブラウザ可, 依存ゼロ) を実装し、FL 同梱の FLhd 系 9,740 ファイル (262.4 MB, 552,878 イベント) で往復 byte-exact 100% (9,740/9,740)**。typed 往復 (全イベントを型付き復号→再符号化) も 100%。
- 対象内訳: `.flp` 164 (Demo 45 / Template 35 / **Render tests 82** / system 2)、`.fst` 8,967、`.fsc` 609。mac 側の一意内容は 8,976 件で、**win インストーラ (9,128 ブロック) は mac を完全に包含**し win のみは 152 件 (FL Slayer/Wasp/Wasp XT の preset 151 + Harmor デモ 1)。win 側 9,128 も 100% 往復。
- **発見 (FLEngine 逆アセンブルで確定)**: FL 25.2 以降は **拡張イベント ID** — 先頭バイト `0xAC` + u32 LE の 32bit ID を使い、payload 形式は `id & 0xF0000000` (0=BYTE / 0x4=WORD / 0x8=DWORD / 0xC=可変長) で決まる。公開パーサ (PyFLP 2.2.1) はこれを BYTE イベント列として誤読しフレームがずれる (NewStuff.flp で +37 イベント; §3)。
- 未知イベント: コーパスの 151 ID のうち **PyFLP 非収録 48 / 意味未確定 (低信頼) 47 / FL21 以降に出現 28 / FL 25.2 以降に出現 7** (+ 拡張 ID 機構そのもの)。FLEngine 26.1.7 が書くが未出現の ID 11 個。
- 使用 plugin 集計: 137 種 (`corpus/plugins.json`)。Render tests が **80 plugin を 1 本ずつ**カバー。比較オラクル設計は `ORACLE.md`。

## 1. 成果物

| パス | 内容 |
|---|---|
| `src/flp.ts` | 無損失コンテナ層 (FLhd/FLdt, BYTE/WORD/DWORD/TEXT/DATA, 可変長, 0xAC 拡張 ID, 非正規 varint, slack/trailer 保持)。`parseFlp`/`writeFlp` |
| `src/events.ts` `id_sets.ts` | イベント辞書 (151 ID に名前/型/scope/信頼度/出典), PyFLP 既知 ID 集合 (ID のみ), FLEngine 書込 ID 集合 |
| `src/decode.ts` | 型付き復号/符号化 (text の版依存エンコード, 構造体レイアウト 18 種, レコード列: notes/playlist/mixer params) |
| `src/summary.ts` | scope 追跡 → tempo/拍子/小節数/チャンネル/パターン/ノート/インサート/plugin 使用 (VST ラッパ chunk 解析つき) |
| `src/wav.ts` `flpdiff.ts` | オラクル部品: WAV 読込・ULP/RMS/ピーク指標・許容クラス判定, FLP イベント差分 (揮発 ID マスク) |
| `cli/dump.ts` | イベントダンプ (人間可読 / `--json` / `--summary` / `--ids` / `--offsets`) |
| `cli/roundtrip.ts` `corpus.ts` `winmac.ts` `wavcmp.ts` `flpdiff.ts` | 往復検証 / manifest・census・plugin 集計 / win-mac 比較 / WAV 比較 / FLP 差分 |
| `corpus/` | `manifest.json` (164 projects), `fst_manifest.json` (9,576 presets), `plugins.json`, `event_census.json`, `unknown_events.json`, `engine_event_ids.json`, `roundtrip.json`, `winmac.json`, `pyflp_crosscheck.json` |
| `scripts/` | `engine_event_ids.py` (DLL から書込 ID 回収), `gen_id_sets.py`, `crosscheck_pyflp.py` |
| `test/` | node:test 21 件 (合成 FLP/WAV, 拡張 ID, 非正規 varint, コーパス往復) / `tsc --noEmit` クリーン |

使い方: `node cli/dump.ts "<…>/Demo projects/NewStuff.flp" --ids 156,233` / `--summary`。環境変数 `FL_ROOT` で素材ルート変更。FL 本体データはリポジトリに複製せず、manifest は派生メタデータ (サイズ/sha256/イベント数/plugin 名等) のみ。

## 2. FLP フォーマット (実データ + エンジン突合で確認済みの事実)

- ヘッダ `FLhd`(len=6: format u16 / nChannels u16 / ppq u16) + `FLdt`(len)。**format**: 0=project, 0x10=score(.fsc), 0x20=channel-state, 0x30=plugin-state, 0x40=insert-state (全コーパスで slack/trailer/hdr 拡張 0 件、非正規 varint 0 件)。ppq は 24/48/72/96/120/192/384/768 (96 が 8,833 件)。
- イベント: ID<64 → 1B, <128 → 2B, <192 → 4B, ≥192 → 7bit varint 長 + payload (TEXT=192–207, DATA=208–255 は枠組み同一)。
- **text のエンコード**: FL < 11.5 は ASCII (ANSI)、**≥ 11.5 は UTF-16LE + NUL 終端** (実測: 11.0 までは ASCII 100%、11.5 以降 UTF-16 100%)。例外: 199 (FlVersion)・198 (RTF) は常に ASCII、231/239/241 は常に UTF-16。
- **Playlist items (233) のレコード長は版依存**: ≤ FL 20.8 = **32B** / build 3031 (20.99, FL21 beta) 〜 FL 24.1 = **60B** / FL 24.2.99.4720 以降 = **80B**。全 playlist イベントで `u16@4==0x5000` の格子間隔から実測 (`playlistStride()`; stride 自体は実測だが、60B→80B の境界 build 4700 は**推定** — 4213–4719 は標本無し)。PyFLP は 32B 固定。
- **mixer 構造** (event 順): `236 InsertFlags` が 1 insert を開き、`98 SlotIndex` が effect slot (0–9) を開く。plugin は `201 内部名 → 212 wrapper(52B) → 203 表示名 → 155/128/41 → 213 状態` の並び。channel は `64 NewChannel` で開く。
- 型付きレイアウトを与えた構造: notes(224)=24B, playlist(233), mixer params(225)=12B, track(238)=47–70B, timestamp(237)=2×f64, wrapper(212), insert flags(236), levels(219) 他。
- **FST/FSC の構造** (イベント ID 列を畳んだ最頻形): plugin-state = `199 [159 28 37] 201 212 [203 155 128 41] 213` (8,306 件。159/37/41 付きの新形式 2,206, `199 28 201 212 213` 2,163, `199 201 212 213` 1,157 …)、channel-state = `199 [28] 64 21 [201 212 213] 0 209 138 139 … 218* 143 20 135 192 [155] 128` (643)、insert-state = `199 (201 212 213)×n 149 204 225` (18)、score(.fsc) = `199 [28] 65 224` (609)。
- **FLEngine_x64.dll (win, FL 26.1.7) からの突合**: FLP 保存関数 `0xf40840` と書込ヘルパ (`0xa9ec60` ヘッダ / `0xa9eb60` UTF-16 text / `0xa9ea80` data / `0xa9ece0` XOR 難読化) の全呼出点から **書込 ID 149 個**を回収 (`corpus/engine_event_ids.json`)。**FL ≥ 25.2 保存の 163 ファイルが使う 129 ID のうち 126 を説明** (残り 0/226/227 は別経路)。読込側 (`0xa9e7a0`) は `0xAC` 受信時に u32 を読み、`<0x40/<0x80/<0xC0/<0x100` を従来クラス、それ以上は上位ニブルでクラス判定することを確認。

## 3. 往復検証 (実測)

| グループ | ファイル | イベント | L0 container | L1 typed |
|---|---:|---:|---:|---:|
| demo | 45 | 267,683 | 45/45 | 45/45 |
| template | 35 | 86,431 | 35/35 | 35/35 |
| render-test | 82 | 104,362 | 82/82 | 82/82 |
| system-flp | 2 | 2,048 | 2/2 | 2/2 |
| fst | 8,967 | 90,272 | 8,967/8,967 | 8,967/8,967 |
| fsc | 609 | 2,082 | 609/609 | 609/609 |
| **計** | **9,740** | **552,878** | **100.0%** | **100.0%** |

所要 21 s (L0+L1, 262 MB)。win 側 9,128 ブロックも L0 100%。L1 は text の孤立サロゲート/末尾バイトも `tail` で保持、構造体は「名前付きフィールド + 残余バイト」で無損失。

**PyFLP 2.2.1 との突合** (Python 3.10 venv, 参照のみ): `.flp` 164 件中 133 件を PyFLP が解析可 (31 件失敗 = `NoModelsFound` 29 + utf-16 デコード/IndexError 各 1; PyFLP 側制約)。解析可 133 件で **チャンネル数 133/133 一致、イベント数 127/133・テンポ 127/133 一致**。不一致 6 件は全て FL 25.2.x 保存ファイル (0xAC 拡張 ID で PyFLP のフレームがずれる, 例 NewStuff.flp: PyFLP 4,440 vs 本実装 4,403 イベント → 本実装の解釈の独立な裏付け)。Python 3.12/3.14 では PyFLP 自体が起動不能。

## 4. FL 26.x で追加された未知イベント (`corpus/unknown_events.json`)

定義: 「PyFLP 2.2.1 (FL≤21 相当) 非収録」かつ「コーパス内の初出版」で分類。

- **FL ≥ 25.2 初出 (7)**: `0xC0000101` (拡張 text "FL Studio x.y.z.build", 127 ファイル), `0x100` (拡張 BYTE, FL 26.1.0.5528 の 1 ファイルのみ), `52`(pattern 末尾 flag, 87), `171`(87), `252`(UTF-16 text, 空), `253`(UTF-16 text `"0,0,0,…"` 48B), `251`(43B, 2 ファイル)。
- **FL 21〜24 初出 (21)**: 41(6,314: plugin 付随 flag), 42, 43(27,000: track 毎), 44, 45/46/101/168(time marker 4 点), 47/167/242(28B)/243(8B)(mixer prelude), 48, 49, 50/104(24.2.99.4720), 51/170(24.2.99.4831), 103, 169(347 ファイル, 値 7), 240(UTF-16 text: "Instruments"/"Drums"/"Bass"/"Sidechain"/"SFX" — insert グループ名か, 1 ファイル)。
- **FL≤20 に既出だが PyFLP 非収録 (20)**: 19, 25, 27(6,198), 31, 35–40, 91, 92, 157/158(pattern, 0xFFFFFFFF=未設定), 165/166(insert), 210, 216, 220, 230(UTF-16 text, 式様)。
- **エンジンのみ (コーパス未出現, 11)**: 0x0F, 0xF5–0xF9, 0xFA, 0xFE, 0xFF, 0xC0000100 (拡張 text, URL の直後), 0xC0000102。
- 辞書上 **低信頼 (名前は位置由来のみ) のイベントは 47 ID = 全イベントの 12.5% (69,138/552,878)**。残りは PyFLP/エンジン書込順と構造から高/中信頼で命名。意味の最終確定にはエンジンの読込 switch 逆アセンブル (チケット L-6) が必要。

## 5. 使用 plugin 集計 (`corpus/plugins.json`, 上位)

順位は「使用する distinct .flp 数」(Render tests 82 本が各 plugin に 1 を加算する偏りあり — `groups` で分離可)。`inst` = channel+mixer slot の総数、`preset` = .fst/.fsc の root plugin 数。

| # | plugin | proj | inst | preset |
|--:|---|--:|--:|--:|
| 1 | 3x Osc | 75 | 152 | 351 |
| 2 | Fruity Parametric EQ 2 | 58 | 707 | 18 |
| 3 | Fruity Limiter | 53 | 288 | 17 |
| 4 | Maximus | 45 | 101 | 53 |
| 5 | Fruity Reeverb 2 | 42 | 266 | 10 |
| 6 | Fruity Delay 3 | 31 | 64 | 14 |
| 7 | Fruity WaveShaper | 29 | 62 | 40 |
| 8 | Fruity Stereo Shaper | 28 | 55 | 29 |
| 9 | Fruity Peak Controller | 27 | 22 | 7 |
| 10 | Sytrus | 25 | 267 | 1,022 |
| 11 | Harmless | 25 | 160 | 434 |
| 12 | Fruity Soft Clipper | 23 | 18 | 8 |
| 13 | Fruity PanOMatic | 22 | 175 | 5 |
| 14 | Fruity Love Philter | 21 | 36 | 51 |
| 15 | Harmor | 20 | 99 | 329 |
| 16 | Slicex | 20 | 42 | 8 |
| 17 | Fruity Flangus | 20 | 35 | 16 |
| 18 | FPC | 20 | 25 | 86 |
| 19 | Fruity Fast Dist | 18 | 38 | 12 |
| 20 | Pitcher | 18 | 20 | 4 |

- 137 種中、projects で使われず preset のみに現れるのは 32 種 (Kepler Exo 192, VFX Script 99, VFX Key Mapper 42, Transmitter 39, FL Studio Mobile Rack FX 36, Multiband Delay 22 …)。
- **第三者 VST は本コーパスに存在しない** (wrapper 経由は Fruity Mute 2 / Phase Inverter の 2 件のみ)。VST2/VST3 の chunk 解析 (`parseWrapperData`) は合成データでのみ検証。Serum 2 / OTT 等を含む FLP は素材待ち (§7)。
- tools/plugins への示唆: 実効影響は **ミキサ insert の EQ/Limiter/Reverb/Delay/Maximus/WaveShaper/PanOMatic** (instance 数) と **ジェネレータ 3x Osc / Sytrus / Harmless / Harmor**。Render tests が各々単体検証の足場になる。

## 6. コーパス manifest (`corpus/manifest.json`) の概況

- Demo 45 本: 48.4 MB, tempo 75–178 BPM, 曲長 2–314 小節 (render 長 3.7–589 s, 計 7,360 s), ノート 50,682。最大 `Never Out.flp` 7.1 MB / 7,120 イベント。Template 35 本: 30.8 MB, 1–8 小節。
- FL 版: 10.9〜26.1 (11.1: 54 本 = Render tests が多数, 24.2: 21 本, 25.2: 10 本, **26.1: 1 本** `Templates/Minimal/Basic with limiter`)。
- sample 参照 1,243 件のうち `%FLStudioFactoryData%` 参照 1,105、実在解決 1,100 (**99.5%**, 欠落 5 件は `Misc/Used by demo projects/…`)。Render test に必要な素材は同梱で足りる。

## 7. 未解決 / ブロッカー / ユーザ依頼

- 未解決: ① 低信頼 47 ID の意味 (読込 switch 未解析), ② native plugin state (event 213) は blob のまま (plugin 毎デコーダ未実装), ③ 版境界 build 4213–4719 の playlist stride は標本無し, ④ ORACLE の STFT 判定 (D クラス) 未実装 / C・D 閾値は暫定。
- ブロッカー: なし (ネイティブ FL 不在は設計で回避)。
- **ユーザ依頼**: (1) 可能ならネイティブ FL 26.1.7 で **Render tests 82 本 + Demo 3 本を 48kHz/32bit float/dither off で WAV 書出し** (ORACLE.md §7) — T5 の golden。(2) Serum 2 / OTT / Fresh Air / Kilohearts を実際に使った `.flp` (第三者 VST の 213 解析と tools/plugins の実使用検証用)。
- 法務は事実整理のみ: Demo/Template/preset は Image-Line 同梱素材。リポジトリには複製せず派生メタデータのみコミット。PyFLP は GPL-3.0 で **参照のみ** (コード非流用; `id_sets.ts` は ID 番号のみ, 名前とレイアウトは本実装で独立に記述)。

## 8. 下流チケット案

| ID | 内容 | 受入 |
|---|---|---|
| L-1 | wasm FLEngine の FLP load→save ハーネス (T1) | 26.1 保存ファイルで `flpdiff` identical, 書込 ID ⊆ `ENGINE_WRITTEN_IDS` |
| L-2 | headless offline render 入口 + 決定論ランナー (T2): Render tests 82 本 × 3 回 SHA 一致 | ORACLE §2 |
| L-3 | 上位 plugin の state (213) デコーダ + 単体 DSP 3 者比較 (T3): Fruity Parametric EQ 2 / Limiter / Reeverb 2 / Maximus / Delay 3 から | クラス A/B 判定表 |
| L-4 | ネイティブ golden 取込 (T5) と C/D 閾値再校正 | §7 依頼 (1) |
| L-5 | STFT/LUFS 判定 (`src/wav.ts` D クラス) と最初の差分位置レポート | ORACLE §4.4 |
| L-6 | エンジン読込 switch (`0xa9e7a0` 以降の FlpLoad) 逆アセンブルで低信頼 47 ID を確定 | `unknown_events.json` の undocumented → 0 |
| L-7 | VST2/VST3/CLAP ラッパ (213) の実データ検証 | §7 依頼 (2) |
| L-8 | `flp_e2e.sh` を `agent-browser` E2E に接続 (ブラウザで parse/dump) | M12 |
