# REPORT — CAB-213: vreg low-key 112 エントリの実キー確定 + username 二重表記の統一

日付: 2026-10-10 / 親: CAB-94 (vreg) 検収起票 / 下流: CAB-101 (実FL結線, 本チケットを blockedBy) / 関連: CAB-168 (pathreg)
書込範囲: `tools/startup/keyfix/` (新規) + `tools/startup/vreg/data/{seed.json,coverage.json}` + `tools/shimx/pathreg/src/pathmap.c` (2 点) のみ
再現: **`bash tools/startup/keyfix/keyfix_e2e.sh`** (seed 再生成 → key 適用 → vreg e2e → pathreg e2e → 整合チェック, 約 2 分, exit 0)

## 0. 結論 (数値は全て実測)

1. **キー不明 112 エントリ → 不明 3 に** (目標 ≤20 達成)。内訳: **完全確定 62** (= seed 内 57 + 既存 core エントリと
   同一座標のため重複削除した 5) / **機構確定・尾部動的 47** (静的 prefix+placeholder key を付与, key_conf=推定) /
   **確定不能 3** (FUN_007a4e30 `Count`, FUN_00dd2da0 `Random seed`, FUN_00c526f0 `clsid` — 実行時生成キー)。
2. **FLEngine のレジストリ機構を静的に確定** (capstone 5.0.9 + .pdata 関数索引 + m11 lift IR 突合 + Ghidra 12.1.4 decompile):
   (a) 0x5ae000–0x5b4000 は FL 独自 TRegistry 実装で、OpenKey(0x5af5e0)=RegOpenKeyExW+RegCreateKeyExW、
   OpenKeyRO(0x5af7c0)、CreateKey(0x5af470)、OpenKeyHandle(0x5b0cd0)、GetKeyHandle(0x5b16a0→0x5b1750→OpenKey)、
   WriteData(0x5b0b30)=RegSetValueExW、ReadData(0x5b0bd0)=RegQueryValueExW、ReadStr(0x5b1820) は rdx=返値・key=r8・value=r9。
   (b) **key 引数が nil/空 → CurrentKey そのもの** (IsRelative 0x5aeec0 実測: 空 or 先頭≠`\` → 相対)。
   (c) **CurrentKey は OpenKey/OpenKeyRO/GetKeyHandle で永続変更**され、Read/WriteXxx の key 付き版は save→open→write→restore。
   (d) 起動時 0x1104fe0 が `Software\Image-Line\FL Studio 26` を OpenKey (共有管理オブジェクト [0x6510F0])。
   0x11c71b0/0x11cde20 は同一関数内で GetKeyHandle(FL26)→相対 `General` ops の組で**基底=FL26 を実証**。
   (e) boot 0x11be0a0 (BeforeRunning) が `[0x15C2620]="Plugin version specific\"`、`[0x15C2608]=+"Windows"`、
   `[0x15C2618]=+"Devices"`、`[0x15C2610]=+"Windows\<WxHxBPP>"` (GetSystemMetrics) を計算 —
   `Plugin version specific\...` 系キーの生成点。`[obj+0x10]`=TComponent.Name、`[obj+0xc0c]`=窓の section 名 (実行時)。
3. **IR 突合**: m11 boot closure (boot_final3.ll, 7,429 関数) に含まれる対象ソースは FUN_00ba5650 のみで、
   lift IR の呼出集合 (@function_5b1920×2 / @function_5b1b00×9 / @function_5b1c50×1) が capstone 解析と完全一致。
   残 28 関数は closure 外のため capstone+Ghidra decompile (tools/m2 の Ghidra プロジェクトを読取専用複製して使用) で確定。
4. **username 統一**: 正規 = **`C:\Users\webstudio`**。根拠: vreg seed (env/known_folders/Shared data) と
   vreg/pathreg の e2e が契約値として固定 (vreg test/integration.test.mjs:19, pathreg test/e2e.mjs:40/95 — 双方読取専用)。
   shimx 内蔵 `C:\Users\user` (env.c/shell.c) は読取専用のため不変 → pathreg 既定マウント表が両表記を同一実体
   (`/c/home/...`) へ写像して吸収 (CAB-168 §3 設計を維持)。**実効挙動は変更なし** (unmap は従来どおり正規表記を返す)。
5. **検証 ALL PASS**: vreg e2e (C 単体 / shimx 結合 ST+MT / symcheck / wasm module / node 22/22 / headless Chrome 実
   IndexedDB) + pathreg e2e (C 単体 ST+MT / JS 4 / e2e 6 グループ — **vreg Vreg との双方向ミラー含む**) +
   整合チェック 6 項目 (`verify_consistency.py`: key 一意 / 不明≤20 / username 統一 / Shared data↔マウント同一実体 /
   apply 健全性)。seed 241→**236 エントリ** (重複 5 削除)、**apply 77→81**、値名被覆 229/229 (100%) 維持。

## 1. 確定キー表 (112 の行き先)

| 実キー | 件数 | 根拠 (ソース関数 / 根拠 site) | confidence |
|---|--:|---|---|
| `...\FL Studio 26\General\Render` | 34 | RenderOptions.save 0xeeac20 / load 0xeec630 が UStrAsg+UStrCat3 で `General\`+`Render`(`Render (master)` は保存側分岐) を構成。load 側は `Render` 固定 | 確定 |
| `...\FL Studio 26\General\MIDIForm` | 11 | FUN_01175480 が絶対 literal `FL26\General`+`\MIDIForm` で WriteBool(1)。LoadSettings 0x11a6d71 / SaveSettings 0x11afb79 は `General\`+[0x15e13b8(MIDIForm)+0x10] (=TComponent.Name `MIDIForm`) | 確定 |
| `...\FL Studio 26\Plugin version specific\General` | 4 | SaveSettings 0x11afa0b/0x11b0386: [0x15C2620]+`General` (Enable MIDI sync/input/output, Template) | 確定 |
| `...\Plugin version specific\Devices\Audio output` | 3 | SaveSettings 0x11b0cda: [0x15C2618]+`\Audio output` (Sample rate=44100 は **apply 昇格**, Buffer length (DS), Device name) | 確定 |
| `...\Plugin version specific\Windows\PLForm` | 2 | FUN_0112e240 0x112e42b: [[0x15e1f00]]+`\PLForm` ([[0x15e1f00]]=Cell 0x15C2608) | 確定 |
| `...\Plugin version specific\Windows\PRForm` | 1 | FUN_011245e0 0x1124d02 (`\prform` 読み — 大小無視で同一キー) | 確定 |
| `...\Plugin version specific\Windows\EventEditForm` | 1 | FUN_01306d60 0x1306d7c (`\EventEditForm` literal) | 確定 |
| `Software\Image-Line\Shared\General` | 1 | FUN_0119f7e0 0x119f8ab: GetKeyHandle(Shared\General) 直後の key=nil ops | 確定 |
| `Software\Image-Line\Shared\Paths` | 1 | Paths.sharedData 0x652e60 — core paths group と同一キー | 確定 |
| `Software\Image-Line\Registrations\FL Studio 26.1` | 2 | Reg.readKey 0x8e6150 literal + version サブキー literal。pinned license と同一キー | 確定 |
| `System\...\Keyboard Layouts\00000409` (HKLM) | 2 | FUN_00843390 / FUN_00865c90 wrapper literal section。ID は US (00000409) 採用。core os と同一キー | 確定 |
| `...\Plugin version specific\Windows\<WxHxBPP>\<FormName>` | 13 | FUN_00ba5650 (caller 基底=[0x15e2ce8]=Cell 0x15C2610) / FUN_011a5250 / FUN_00e42380。解像度・窓名は実行時 | 推定 |
| `...\Plugin version specific\Windows\<FormName>` | 9 | FUN_01136050 0x11360cb: [[0x15e1f00]]+`\`+[param+0x10] | 推定 |
| `...\Plugin version specific\Devices\MIDI input\<device>` | 7 | FUN_0117e9b0: [0x15C2618]+`\MIDI input`+`\`+<列挙デバイス名> | 推定 |
| `...\Plugin version specific\Devices\MIDI output\<device>` | 2 | 同左 (Sync, SendAllNotesOff) | 推定 |
| `...\Plugin version specific\Windows\<SectionName>` | 5 | FUN_00eb9ef0/eba140/eba6d0/ebab30/e4a1d0: [0x15C2608]+`\`+[obj+0xc0c 名] | 推定 |
| `...\Plugin version specific\Windows\<WxHxBPP>\Toolbars` | 4 | LoadBrowserToolbars 0x11ad60e → FUN_011a3610/011a3440 (GetSystemMetrics 連結) | 推定 |
| `Software\Image-Line\Shared\FL Studio tools\<id>` | 3 | SaveSettings 0x11b0de1 (tools メニュー 0..49 列挙) | 推定 |
| `Software\Image-Line\Shared\Browser\<path>` | 2 | FUN_00a4a910: `Shared\Browser\`+[param+0x58] (パス別) | 推定 |
| `Software\Image-Line\Shared\Plugins\<name>` | 1 | FUN_012b5a10 | 推定 |
| `...\FL Studio 26\General\<Name>` | 1 | FUN_00cef380 0xcef416: `General\`+[param+0x10] (plugin/窓名) | 推定 |
| (key=null — 確定不能) | 3 | FUN_007a4e30 (caller 渡しキー) / FUN_00dd2da0 (実行時生成) / FUN_00c526f0 (`software\asio\<driver>` 列挙) | 推定 |

「...\FL Studio 26」= `Software\Image-Line\FL Studio 26`。**基底=FL26 の根拠は §0-2(d)**。
全 62 確定 + 47 推定 + 3 null = 112。エントリ単位の basis (機械検証可能な根拠列) は seed.json 各 entry の `basis` に記録済み。

## 2. seed 変更内容 (`tools/startup/vreg/data/seed.json`)

1. `scripts/build_seed.py` は読取専用の範囲のため、key 上書きは **`tools/startup/keyfix/apply_keys.py`**
   (後処理; 上書き表=OVERRIDES 115 定義) で実施。vreg.sh が build_seed.py を毎回再生成するため、
   適用順は **build_seed.py → apply_keys.py** (keyfix_e2e.sh が順序を保証)。
2. key 確定により **apply 昇格 4** (起動時 Read が既定値で読む値を seed し実機同等に):
   `General\MIDIForm` の SmootherUpdateBox=`1` / MTC offset=`0` / OfflineHelpBox=`0`、
   `...\Devices\Audio output` の Sample rate=`44100`。**apply 77→81**、被覆 229/229 維持 (coverage.json 更新)。
3. 既存 apply エントリと同一座標 (hive,key,name) になった低-key カタログ 5 件 (ILRegKey×2, Shared data, Layout Text/File)
   は**削除** (coverage テストが「catalog 値は書かれない」ことを要求するため二重登録不可。情報は §1 の表に保持)。
4. placeholder 表記 (`<device>` `<FormName>` 等) は keys.json の既存慣行 (`%.8x` `<ProductGUID>`) に準拠。apply=false のため
   誤キー生成は起きない (CAB-94 の「書かない方針」維持)。

## 3. username 統一方針

- **正規 = `C:\Users\webstudio`**。固定値を採用 (変数化 `%USERPROFILE%` は技術的には可能 — エンジンは
  ExpandEnvironmentStringsW 後に使用 — だが vreg/pathreg の e2e が固定値を契約とするため、変数化は seed 消費側の
  実装変更 (別チケット) が必要)。
- pathreg 側は `src/pathmap.c` の **2 点のみ**変更: (1) `pathreg_paths_init` で正規 username を primary
  (`userProfile="C:\Users\webstudio"`)、shimx 内蔵ミラー (`C:\Users\user`) を secondary (`user2Profile`) に明示、
  (2) `pathreg_unmap` の同長 tie-break を後勝ち→**先勝ち** (正規 profile を返す; 既定表の先頭=正規)。
  **マウント集合は 14 個のまま不変**のため、map/unmap の観測結果は変更前と同一 (unmap は従来どおり webstudio 表記)。
- shimx 内蔵 (env.c/shell.c の `C:\Users\user`) は読取専用につき未変更 → **engine が env/SHGetFolderPath で受ける
  user 表記と seed の webstudio 表記が併存**する状態は pathreg の alias mount で吸収 (CAB-168 設計どおり)。

## 4. CAB-101 (実FL結線) への引き継ぎ事項

1. **起動時 open ログの期待値表**: 本 REPORT §1 の表がそのまま期待キー集合。`SHIMX_TRACE` の Reg* ログで
   `HKCU\Software\Image-Line\FL Studio 26\*` / `Plugin version specific\*` / `Shared\*` / `Registrations\*` /
   `Keyboard Layouts` 以外が出たら本表の未確定部 (推定 47 / null 3) の確定機会。
2. **`<WxHxBPP>` と `<device>` `<FormName>` の具体化**: 実機ログから観測値を seed の key 上書き表
   (apply_keys.py OVERRIDES) に追加すれば `scripts/build_seed.py` 由来 seed への反映は後処理 1 コマンド。
3. **`Plugin version specific\Windows\<WxHxBPP>` の解像度**: GetSystemMetrics(SM_CXSCREEN/CYSCREEN/bit) 由来。
   ブラウザ版では画面サイズが可変 → vreg 側で起動時の実画面サイズキーを書くか、observed 値のみ seed する方針決定要。
4. **shimx 内蔵 username の将来統一**: shimx 取込 (CAB-11 恒久化) 時に env.c/shell.c を `C:\Users\webstudio` へ
   統一し、pathreg の user2Profile (user) を退役させるのが本丸 (shimx 読取専用につき本チケットでは未実施)。
5. **license 関連**: `Registrations\FL Studio 26.1\ILRegKey` は pinned seed が書くため、FUN_01183130 系の読みが
   通るはず。通らない場合 CAB-106 (license-observation) の観測対象。

## 5. 残存不明キー 3 件の次手段

| entry | 現状 | 次手段 |
|---|---|---|
| FUN_007a4e30 `Count` | caller 渡しキー (SetRoot(引数)+OpenKey(引数)) | caller 解析 (browser URL/履歴系と推定) — lift 後 open ログで確定が最短 |
| FUN_00dd2da0 `Random seed` | FUN_00dd2190/ba6150 経由の実行時生成キー | Ghidra caller chain 追跡 or lift 後ログ (generator 設定文脈) |
| FUN_00c526f0 `clsid` | `HKLM\software\asio\<driver>` 列挙 (driver 名は実機依存) | 確定不能扱いで確定 (engine が列挙して書くため seed 不要の見込み)。vreg の ASIO COM (CAB-97) 側と突合 |

## 6. テスト (`bash tools/startup/keyfix/keyfix_e2e.sh` = ALL PASS)

| 層 | 内容 | 実測 |
|---|---|---|
| seed 生成+適用 | build_seed.py → apply_keys.py | 241→236 entries / apply 81 / null 3 / 重複 0 |
| vreg C 単体 | `build.sh test` (FL 流 Read/Enum/import/export/追加 6 API) | ALL PASS |
| shimx 結合 | `build.sh shimx` (core/sys/ole MT+ST, M4 互換) × vreg reg.c | ALL PASS |
| symcheck / module | shimx 39 シンボル包含 / wasm ビルド | PASS |
| node テスト | unit/結合/IDB/CLI (coverage 更新含む) | **22/22 PASS** |
| Chrome e2e | 実 IndexedDB ×2 reload | PASS (Chrome/154.0.8037.97) |
| pathreg e2e | C 単体 ST+MT / JS 4 / e2e 6 groups (**vreg 双方向ミラー A4 含む**) | ALL PASS |
| 整合チェック | verify_consistency.py 6 項目 | **ALL PASS** |

## 7. 成果物 (`tools/startup/keyfix/`, 解析スクリプト一式)

| パス | 内容 |
|---|---|
| `feparse.py` / `fnindex.py` | FLEngine PE パーサ (pefile+capstone) / .pdata 関数索引 (57,816 関数) |
| `regcalls.py` / `regapi.py` | Reg* IAT 参照 site 抽出 (108 関数 199 site) / TRegistry メソッド意味分類 |
| `keyflow.py` / `keyflow2.py` | TRegistry 呼出列の key/value 解決 (v2: CurrentKey コンテキスト追跡) |
| `dynkeys.py` / `inscache.py` / `xref.py` | 動的キー構造抽出 / 全 .text 命令キャッシュ (5,183,665 命令) / caller 引数文字列 |
| `resolve_keys.py` / `apply_keys.py` | 112 エントリの一括解決 / seed への key 上書き表適用 |
| `verify_consistency.py` / `keyfix_e2e.sh` | 整合チェック 6 項目 / 1 コマンド検収 |
| `work/` (gitignore) | 解析中間物 (allins.pkl, ops_dump.txt, resolved_keys.json, Ghidra decompile, seed backup) |

## 8. 制限・正直な注記

1. **「推定 47」の key は placeholder を含む** (`<FormName>` 等)。これは keys.json 既存慣行に沿うカタログ表記で、
   apply=false のため書込は発生しない。「キー不明」の定義を「key=null」で数えた場合 3、
   「placeholder 含む推定も不明」扱いの場合 50 — 本 REPORT は前者で統一 (後者でも §1 表で全量を説明可能)。
2. 確定の根拠は静的解析 (capstone/Ghidra/lift IR) であり、**実 lift 後の動的観測では未確認** (CAB-101 の範囲)。
   特に「基底=FL26 が全起動経路で保たれる」ことは 0x11c71b0 系の同一関数実証 + boot 計算の静的読解まで。
3. RenderOptions.save の `Render (master)` 分岐 ([obj+0xde8]) は load 側が読まないため seed は `General\Render` のみ。
   master 版が将来読まれる場合は追加エントリ。
4. seed.json は build_seed.py 再生成で上書きされる (vreg.sh step1)。恒久化には apply_keys.py の OVERRIDES を
   build_seed.py へ取込む必要 (tools/startup/vreg/scripts は本チケットの書込範囲外のため未実施 → 次タスク案)。
   **→ 完了 (follow-up c72f220)**: OVERRIDES 正本は `tools/startup/vreg/scripts/build_seed.py` へ verbatim 移設済み
   (115 定義 / 差分 0 を検収で再照合。本ファイルの表は履歴。詳細は vreg REPORT §11)。
5. m11 IR 突合は closure 内 1 関数のみ (closure 外 28 関数は capstone+Ghidra decompile で代替)。

## 9. ユーザ依頼事項

なし ( ブロッカー無し )。

## 10. 次タスク提案 (下流チケット案)

| # | チケット | 要点 |
|---|---|---|
| 1 | CAB-101 | §4 の期待キー表を SHIMX_TRACE 観測と突合。推定 47 の具体化データが取れる |
| 2 | ~~build_seed.py 取込~~ **完了** | follow-up c72f220 で移設済み (正本=build_seed.py OVERRIDES / apply_keys.py は no-op 後処理として残置) |
| 3 | shimx username 統一 | shimx 取込時に env.c/shell.c を webstudio へ (pathreg secondary 退役) |
| 4 | vreg REPORT/§3・§4 更新 | 本成果 (236/81/3) への数値更新 — tools/startup/vreg/REPORT.md は本チケット範囲外のため main 側で |
