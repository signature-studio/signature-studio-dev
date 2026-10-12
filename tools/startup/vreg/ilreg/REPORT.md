# REPORT — CAB-212: 0x10c7cd0 登録パーサ / ILRegKey 書式の静的解読

日付: 2026-10-10 / 担当: ilreg / 書込範囲: `tools/startup/vreg/ilreg/` のみ
再現: `python3 tools/startup/vreg/ilreg/scripts/extract_constants.py` &&
`node tools/startup/vreg/ilreg/verify/test_golden.mjs` (要 node: `~/.nvm` or `[EMSDK]` 同梱 node `node/*/bin/node`)

## 0. 結論 (数値は全て実測。推定は (推定) 明記)

1. **`0x10c7cd0` (FLEngine 32,177 B) の判定の実体を機械語レベルで確定した**:
   ILRegKey 復号平文内の `|<機能キー>:<YYYYMMDD>:` レコード (有効期限) と
   `|id:<マシン識別文字列>` レコード (マシン束縛) を見て、ティア表 (`0x15b7f00`:
   A=31000 / B=31010 / C=31020, fallback 31005) ごとに grade 0/1/2 を計算し、
   `byte[0x14f84a8]` へ bit1/2 (Fire edition) のみ反映する。
   マシン識別文字列は **SHA-256(lowByte(AppData ++ ComputerNameNetBIOS ++ MachineGuid)) →
   大文字 hex 64 文字を 8 文字区切り + チェックサム 2 文字 = 74 文字** (書式は `FORMAT.md` §3)。
2. **vreg seed のプレースホルダ `WEBSTUDIO-ACTIVATED-PLACEHOLDER` は本検証を通らない**
   (全ティア grade 0 → `gradeChar=0x40` → 表示は「Update registration」/ボタン ID 3)。
   ただし例外・bit0 立ては起きず、存在検査 (`FUN_008e6150`) は CAB-94 済みの通り通る。
   seed 変更は**不要** (ユーザ方針「無力化・無条件通過」と矛盾しない)。詳細 `FORMAT.md` §8。
3. **本ビルドの新事実: bit0 (Trial bit) を立てる書込は全バイナリ中 1 箇所 (`0x10cf4e6`) しか無く、
   その条件 (`Pos("Please remember to register", ログ文字列)`) に使う文字列は関数内で常に空**
   → bit0 が立つ経路は静的に存在しない。`0x15e0698` が `0x14f84a8` への唯一のポインタであることも
   実測 (.data 全走査)。**CAB-106 は「bit0 は常に 0」を初期仮説に据えるべき**。
4. ティア判定には癖がある: ①grade 判定への入口が「平文 head 空 (= `:` 始まり)」条件
   (marker, `0x10cae5c`。head 非空時に通るはずの charsum 比較は死蔵コードで常時 grade 0 側)。
   ②日付 8 文字が不正 (パース結果 0) だと grade 2 (有効) 扱い (`0x10cb971`-`0x10cb98a`)。
5. ILRegKey 値の復号は 16 進エンベロープ + **VM バイトコード (687 B @ `0x14111e0`)**。
   VM の完全実装は次段 (入出力・引数・ストリーム構造までは確定、`work/vmprog.bin` 抽出済)。

## 1. 成果物 (`tools/startup/vreg/ilreg/`)

| パス | 内容 |
|---|---|
| `FORMAT.md` | 書式ドキュメント本体 (全主張に根拠アドレス。受入要件 1・2 は §2 と §8) |
| `verify/reader.mjs` | reader 模擬検証器: machineString / envelopeHexPack / splitFirstGroup / dateFrom8 / judge (0x10c7cd0 の制御フロー移植) |
| `verify/test_golden.mjs` | ゴールデンテスト **20/20 PASS**。vreg seed 値を入力に judge を検証 |
| `scripts/extract_constants.py` | バイナリから定数を決定的抽出 → `data/constants.json` (セパレータ, ティア表, mask, SHA-256 K 表 VA, VM プログラム VA) |
| `scripts/pedis.py` | capstone 逆アセンブラ (RIP 相対の文字列注釈付き)。解析の再現用 |
| `data/constants.json` | 実測定数 (`:` / `|` / `\|LL=OFF` / `\|LL=` / `TRSLA` / `id:` / ティア表 / mask=6 / SHA-256 K 表 / VM プログラム VA) |
| `work/` (gitignore) | Ghidra プロジェクト複製, decompile 結果, vmprog.bin |

## 2. ゴールデンテスト (実測: 20/20 PASS)

| 群 | 内容 |
|---|---|
| T1 (4) | machineString: 書式 74 文字正規形 / SHA-256 ストリーム / チェックサム (acc += c*2−3, 8bit) 手計算ベクタ / 決定性 |
| T2 (2) | vreg seed 読取 (`seed.json` license group) / プレースホルダの 16 進 pack (31 文字→15B, `'-'`→0xF6 ニブル規則) |
| T3 (2) | **プレースホルダ判定: 全ティア grade 0 / gradeChar 0x40 / flag=0 / bit0 不立** |
| T4 (7) | 合成平文: 有効 (gradeChar 'A', flag bit1/2 クリア, ボタン ID 1) / マシン不一致 ('+' → grade 0) / 期限切れ (grade 1) / 日付不正 (quirk grade 2) / id レコード無し / 第二ティア fallback (31005 → flag\|=2\|=4) / head 非空 (strictHead 両経路) |
| T5 (4) | FUN_008e6770 互換分割 / Pos 互換 / FUN_00442770 互換日付 (うるう年) |
| T6 (1) | constants.json のバイナリ抽出値スポット確認 |

## 3. vreg seed への統合手順 (実装は次段)

1. `verify/reader.mjs` を `tools/startup/vreg/js/` へ移植し `Vreg.expectedLicense()` を `judge()` に接続
   (入力: seed MachineGuid + VFS AppData パス + ComputerName。今日は engine 側 `HSD` 補正を踏まえ TDate で与える)。
2. `licenseMode:'external'` 時は `.reg` の ILRegKey を envelopeHexPack→VM→split で検査し
   `|id:<machineString>` の一致を表示に使う (判定強制はしない。無力化方針維持)。
3. seed 値自体は現状維持 (プレースホルダで十分)。`licenseFlagBit0` 制御は本ビルドでは効かない
   (bit0 書込死蔵のため) — Trial 表示にしたい場合は lift 後の再確認が必要。
4. 生成 (偽造) はしない。CAB-115 のユーザ `.reg` を reader で検証する用途に留める。

## 4. 未解決・ブロッカー

1. **VM バイトコードのオペコード表** — 復号の完全再現に必要。構造 (ストリーム×2 / 引数 9,0xe0,0x21,2,4 /
   プログラム 687B) は確定済み。`FUN_0055d810` (variant スタック VM) の解読が次段の主作業。
2. 平文 head の実データ構造 (`:` 始まりか) — marker ゲートの死蔵 charsum 比較が入るため、
   実ユーザ `.reg` (CAB-115) での確定が安全。reader は `strictHead` オプションで両対応済み。
3. `|LL=<n>` / `TRSLA` / 機能キー 31000 系の意味 — 数値実測のみ (推定: license level / 機能 ID)。
4. mac 側 (FLEngine_x64.dylib) は未解読。
5. 非 ASCII パスはハッシュ入力が下位バイト落ちする (日本語 AppData での挙動は lift 後確認)。

## 5. ユーザ依頼事項

1. (任意・CAB-115 と共通) 実ライセンスの `.reg` を `~/ダウンロード` に配置頂ければ、
   平文 head 構造と `|LL=`/`TRSLA` の意味を実データで確定できる (生成はしない)。
2. なし (seed 変更・追加素材は不要と判断)。

## 6. 次タスク提案 (下流チケット案)

- **CAB-213 (提案): ILRegKey VM 復号の実装** — `FUN_0055d810` 系オペコード表 → reader への統合。
  平文 head 構造の確定と CAB-115 検証器の完成が目的。
- **CAB-106 への引継**: bit0 常時 0 仮説の動的確認 (`0x11be5b8` 系読み側の観測)。
  `gradeChar` (obj `0x15e4790`+0xd0) とボタン ID (`0x15e0488`) を観測変数に追加推奨。
- vreg への reader 組込 (§3) は CAB-213 完了後が安全 (VM 無しでは外部 .reg の検証表示が不完備)。
