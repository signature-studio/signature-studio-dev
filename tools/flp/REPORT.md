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
| L-8 | `flp_e2e.sh` を `agent-browser` E2E に接続 (ブラウザで parse/dump) | M12 — **実装済 (#112, §9)** |

## 9. ブラウザ E2E (L-8 / #112)

既知類型との関係 (`docs/DEFECTS.md`): 該当なし (lift 無関係)。

- **ハーネス** `web/` (`index.html` + `main.ts`): `src/` の `parseFlp`/`writeFlp`/`dumpText`/`summarize` をブラウザで実行。入力は `<input type=file>` と drag&drop のみ (FL 同梱ファイルは配布物に含めない)。結果を `window.__flp` に公開。`?sabotage` は書込結果を 1 byte 壊すネガティブコントロール用。
- **スイート** `tools/e2e/suite/flp.mjs` (`bash tools/e2e/run.sh --suite flp [--driver both]`)。vite build → 静的配信 → agent-browser (puppeteer-core も可) で file input (`upload`) と drop (合成 `DragEvent`) の両経路を検証。ブラウザ結果を (a) Node 側で別プロセス実行した `src/` の結果、(b) `corpus/manifest.json` (events/version/tempo/channels) の 2 つと突合。
- **フィクスチャ** `suite/flp-fixtures.mjs`: `E2E_FLP_WIN_DIR` (= `fl-win64.tar.zst` の `extracted/`; `block*_DATA.bin` のうち先頭 `FLhd`。`.flp` は manifest の sha256 で特定、`.fst/.fsc` は size + イベント数) か `FL_ROOT` (mac)。代表 6 件: Empty.flp / NewStuff.flp (0xAC 拡張 ID) / Basic with limiter.flp (26.1) / Never Out.flp (7.1 MB) / Accordeon 2.fst / 4 steps.fsc。無ければ SKIP、`E2E_REQUIRE_FLP=1` で FAIL。
- **検査 7 件**: page-load (node グローバル無し) / file-input (6 件の byte-exact 往復 + 突合) / dump-view (画面の dump が Node の `dumpText` と一致) / drop (5 件) / bad-input (`not an FLhd file` を error 表示しページは継続) / console-clean / negative-control (1 byte 破壊を検出)。
- `flp_e2e.sh` は web/ の `node:` import 禁止検査を追加し、`E2E_FLP_WIN_DIR` か `FL_ROOT` があれば末尾で本スイートを `E2E_REQUIRE_FLP=1` で実行 (`BROWSER_E2E=0` で無効化)。

**実測** (検証起点 commit `1769513` (n=3 は rebase 前の同一内容 `d9689f8` で取得し、rebase 後 HEAD `9874680` で 1 回再実行して PASS 14 / FAIL 0, 9.3 s, load 0.98 を確認), クリーン HEAD, Chrome 154.0.8037.97 headless, Node v22.23.3, 素材 = `fl-win64.tar.zst` の `extracted/` 9,128 FLhd ブロック, CI runner):

| 項目 | 結果 |
|---|---|
| `bash tools/e2e/run.sh --suite flp --driver both` (n=3) | 3/3 とも **PASS 14 / FAIL 0** (7 検査 × 2 driver)。所要 11.6 / 9.4 / 9.7 s (load average 1 分値 1.04 / 2.00 / 2.06, 並列 1) |
| ブラウザ往復 (file input 経路, 6 件) | 6/6 byte-exact (入力 sha256 == 書出 sha256 == Node 別プロセス結果)。イベント数は Node・manifest と一致: 1,413 / 4,403 / 1,614 / 7,120 / 40 / 3 |
| 最大ファイル (Never Out.flp, 7,142,631 B, 7,120 ev) の parse+write+summarize+dump+sha256 | agent-browser 804–1,528 ms (n=6 の min–max は両 driver 込み) |
| 既存 app スイート (`run.sh --targets preview,edge-sim`) への影響 | PASS 15 / FAIL 0 / SKIP 3 (`tools/runtime/REPORT.md` の基準値と同一) |
| win 抽出物の FLhd ブロック | 9,128 個。manifest の `.flp` 164 件の sha256 は **164/164** が win ブロックに存在 (`.fst/.fsc` は manifest に sha256 が無いため size + イベント数一致で特定) |

- **ネガティブコントロール**: `?sabotage` (書込結果の末尾 1 byte を反転) のページに Empty.flp を渡すと、検出器 `compare()` が **3 項目**で不一致 (`roundtrip` / `outSha(=inSha)` / `outSha(node)`) を報告 = 検査が FAIL 側に倒れることを確認 (`flp-negative-control` が PASS)。
- **素材なし**: `E2E_FLP_WIN_DIR` / `FL_ROOT` が無いと `run.sh --suite flp` は SKIP (rc 0)、`E2E_REQUIRE_FLP=1` では FAIL (rc 1) を実測。
- `tsc -p tools/flp/tsconfig.json` (web/ を include) rc 0、`src/` `web/` に `from 'node:` 0 件。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `flp_e2e.sh` 全体 (往復 9,740 件 / census 等) は mac 抽出ツリー (`FL_ROOT`) が前提で、CI の win 素材だけでは前半を実行できない。今回はブラウザ段のみ単体実行 | CI から `flp_e2e.sh` を 1 本で回せない | #112 にコメント (win ブロック入力対応は別チケット案) |
| 代表 6 件のみブラウザで検証。全 9,740 件のブラウザ往復は未実施 | ブラウザ固有の差異 (巨大 FLP のメモリ等) は代表件数の範囲でのみ保証 | 必要なら新規子チケット (親 #16) |
| Firefox / Safari は未検証 | Chrome 以外の挙動不明 | `docs/STATUS.md` の MS12 / GUI-8 (Firefox 依存) に従う |

範囲外: Firefox/Safari、FL 本体のロード、実 URL (`--url`) への FLP スイート適用。
