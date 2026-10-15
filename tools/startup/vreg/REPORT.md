# REPORT — CAB-94 vreg: 仮想レジストリ shim + 登録済み seed

日付: 2026-10-10 / 担当: vreg / 書込範囲: `tools/startup/vreg/` のみ (tools/startup 直下の共通スクリプトは**無変更**) / 再現: `bash tools/startup/vreg/vreg.sh` (約 11 秒, `--no-chrome` `--no-shimx` 可)

> **更新 2026-10-10 (CAB-214 follow-up, shimx REPORT §12 = 薄ラッパ化)**: Reg* 本体は **shimx `src/reg.c` が正本**になり、`vreg/src/reg.c` は**削除**した
> (`build.sh` は shimx `src/*.c` 全部 + `src/probe.c` をリンク、SRCS 除外工作なし)。JS (`js/*.mjs`) は無変更で `vreg.sh` が通る。`build.sh symcheck` は
> 「vreg が要求する公開面 (shimx.h 宣言の `Reg*` 全て + module の EXPORTED `vreg_*`/`shimx_reg_*`) を shimx reg.c が定義している」検査に差し替え。
> 以下本文中の「vreg の reg.c / shimx 派生」は取込前 (CAB-94 時点) の記述 (履歴)。

## 0. 結論 (数値は全て実測。推定は「推定」と明記)

1. **Reg\* API は shimx `reg.c` の派生 (`vreg/src/reg.c`: 686→828 行, shimx との差分 206 行) に集約**。FLEngine が import する 12 本 (W 11 + `RegOpenKeyExA`; +delay `RegDeleteKeyExW`)、FL64.exe の 3 本、m11 init closure IR が参照する 10 本の `Reg*` は**全て定義済み**。
   shimx `reg.c` の公開 39 シンボルを全て包含 (`build.sh symcheck`: 追加 11)。shimx 既存テスト (core/sys/ole_shell MT+ST, M4 互換 ST) は vreg の reg.c で **ALL PASS**。
2. **seed**: `data/seed.json` に 236 エントリ (CAB-213 反映後; 初版 241) = REGISTRY.csv の win 値名 **229 種 (大小無視; 大小区別では 231) を 100% 被覆**。うち **81 値を起動時に書込** (apply; 初版 77)、155 は catalog のみ (§3, §11)。全エントリに `confidence`(確定/推定)+`key_conf`/`value_conf`/`basis`。
3. **ライセンス (ユーザ方針「全てのライセンス機構は無力化。アクティベーションは無条件通過」の下で実施)**: 既定は registered。`HKCU/HKLM\…\Registrations\FL Studio 26.1\ILRegKey` 等 11 エントリ (apply 8) を **pinned** で書き、`observeRegistration()` (= engine `FUN_008e6150` と同じ「`FL Studio *` サブキーの ILRegKey 非空」検査) は true。
   **FLEngine 内の本検証 (`0x10c7cd0` → byte[0x14f84a8] bit0) を通るかは未確認** (値はプレースホルダ。§6)。bit0 対応の registry 状態は `licenseFlagBit0` (0=登録済み値を書く / 1=Trial: 書かず削除) で切替可、`external` で cracked 由来 `.reg` を最優先適用。
4. **永続化**: HKCU のみを `IndexedDB` (`IdbStore`: DB `webstudio-vreg` / store `profiles` / key=profile) に JSON (`{hive:{key:{value:{t,v}}}}`) で保存し起動時復元。**headless Chrome 154 の実 IndexedDB でページ再読込を 2 回またいで検証 PASS** (`test/e2e_chrome.mjs`)。HKLM はセッション内のみ。MachineGuid はプロファイル毎に UUIDv4 を 1 回生成し永続。
5. テスト: C 単体 6 グループ / shimx 結合 3 ビルド / node 22 件 (unit 5 / 結合 14 / IDB 2 / CLI 1) / Chrome e2e 1 = **全 PASS**。

## 1. 成果物 (`tools/startup/vreg/`)

| パス | 内容 |
|---|---|
| ~~`src/reg.c`~~ | **削除 (CAB-214 follow-up)**。拡張 (変更世代+通知、Enum の MORE_DATA 必要長、import 強化、ルート単位 export/clear、追加 6 API) は `tools/shimx/src/reg.c` が正本 |
| `src/vreg.h`, `src/probe.c` | probe 宣言 (運用フック・追加 6 API の宣言は shimx.h へ移管) / FL(Delphi TRegistry) と同じ呼出パターンの UTF-8 検証ヘルパ (テスト専用) |
| `js/regfile.mjs` | `.reg` parse/serialize (UTF-16LE BOM / UTF-8 / BOM 無し UTF-16LE 復号、CRLF、継続行、全型、削除構文)、ツリーモデル |
| `js/seed.mjs`, `js/vreg.mjs`, `js/store.mjs`, `js/cli.mjs` | seed 展開 / `Vreg` アダプタ (注入式 wasm factory + store) / `MemoryStore` `FileStore` `IdbStore` / import·export·show CLI |
| `data/seed.json`, `keys.json`, `coverage.json` | seed (236) / REGISTRY.csv キー→具象キー (57) / 実測 coverage (テストが更新) |
| `scripts/build_seed.py` | REGISTRY.csv + 手書き仕様 + key 上書き表 OVERRIDES (CAB-213 移設, §11) → seed.json/keys.json (決定的) |
| `build.sh`, `vreg.sh`, `test/` | ビルド (`test` `shimx` `module` `symcheck`) / 1 コマンド e2e / テスト一式 |

## 2. 実装範囲

**C 側 (Reg\* 本体, 全て `shimx.h` と同一シグネチャ)**: W 版 (OpenKeyEx/CreateKeyEx/CloseKey/QueryValueEx/SetValueEx/DeleteValue/DeleteKey/EnumKeyEx/EnumValue/QueryInfoKey/FlushKey) + `RegOpenKeyW` `RegCreateKeyW` `RegGetValueW` `RegDeleteKeyExW`、A 版 8 本 (`RegOpenKeyExA` `RegCreateKeyExA` `RegDeleteKeyA` `RegDeleteValueA` `RegSetValueExA` `RegQueryValueExA` `RegEnumKeyExA` `RegEnumValueA`)、
追加 6: `RegGetValueA` `RegEnumKeyW` `RegDeleteTreeW` `RegSetKeyValueW` `RegDeleteKeyValueW` `RegQueryInfoKeyA`。意味論: 5 ルート木、サブキー名前順 (大小無視)・値は作成順、削除済みキーは `ERROR_KEY_DELETED`、全体 1 mutex。
shimx 差分: ①`vreg_generation()` / `vreg_set_notify(cb)` (set/delete/create で世代+1、**ロック解放後に呼出スレッドで同期通知**) ②`RegEnum*` の `ERROR_MORE_DATA` で必要長を返す ③import: UTF-8 BOM、`[-HKEY_…]` (サブツリー削除)、`"v"=-`、`@=-` ④`vreg_export_root(i)` / `vreg_clear_root(i)` / `vreg_clear_all()`。

**JS 側 (`Vreg.create({createModule, store, seed, …})`)**: ブート順 = ①wasm 起動 (shimx 内蔵 OS 既定) ②store から profile 読出 ③seed 展開 (`${MACHINE_GUID}` 置換) ④復元時は HKCU を永続値で置換 (seed 版が変われば**不足分のみ補完**: ユーザ変更・削除は保持)
⑤pinned (license/MachineGuid) を永続値より優先 ⑥`external` .reg を最後に適用 ⑦C へ一括 import ⑧通知フック設置 (以降の変更で dirty → 遅延 flush)。新規プロファイルは即保存。
API: `flush()` `close()` `importReg(bytes|text)` `exportReg({hives, utf16le})` `snapshot()` `observeRegistration()` `expectedLicense()` `stats()` と検証用 `readStr/readInt/readBool/writeStr/writeInt/enumNames/keyExists/valueExists`。
オプション: `licenseFlagBit0` `licenseMode` `externalReg` `machineGuid` `applyCatalog` `skipGroups` `flushDelayMs` `profile`。

## 3. coverage (実測: `data/coverage.json`)

| 項目 | 実測 |
|---|---|
| REGISTRY.csv (win/both) の具体的値名 | 229 (大小無視) / 231 (大小区別)。除外=`(dynamic)` `#0` `(default)…` 等の非名称 22 表記。startup REPORT の「約 222」とは数え方の差と推定 (再集計根拠は未特定)。検収再試算: platform=both のみ 218 / installer+os-or-misc 除去 219 / access≠installer-W 227 等 12 通りを試算したが 222 に一致する集計法は見付からず (既定値あり 78・access含R 208 も不一致) |
| seed が初期値を持つ値名 | **229 / 229 (100%)**, seed 欠落 0 |
| seed エントリ (hive,key,name 単位) | 236 (HKCU 215 / HKLM 21)。apply **81** (settings 40 / os 13 / shared 12 / license 8 / paths 5 / gate 3) |
| catalog のみ (書かない) 155 | うちキー不明 **3 エントリ / 3 名** (初版 low-key 112 → CAB-213 で 3; `Count` `Random seed` `clsid`)。理由: 実行時生成キーで静的に確定できず、書くと誤キーを作るため。エンジン内蔵既定で動く |
| Reg API 経由で読めた apply 値 | 81 / 81 (値一致まで検査) |
| 初期値がコード既定値 (ReadInt/ReadBool 第 3 引数) 由来 | 58 エントリ (`value_conf`=確定 かつ CSV 由来で数える; 同定義の初版は 57)。残りは決定値 (Paths, OS, gate, license) または既定値不明 (`''`) |
| キー: CSV (hive,key) 47 行 → 具象キー | **57 本** (`X / Y` や `%.8x` `<ProductGUID>` を展開)。class: literal 38 / inferred 5 / installer 14 |
| 起動後に存在するキー | 17 / 57 (literal 14, inferred 2, installer 1)。残りはエンジンが `RegCreateKeyExW` で作る/インストーラ専用/不在が正常 (`Wow6432Node`, `software\asio` 等) |
| 全 57 具象キーの往復 (set→export UTF-16LE→[-key]削除→import→get) | **57 / 57 一致**、レジストリ全体のスナップショットも完全一致 |

CSV の key 数は startup REPORT の 46 (31/5/10) に対し本集計は 47 (33/5/9): 同一キーの hive/確度の集約法の差 (本集計は (hive,key) 一意化)。

## 4. confidence 表

`確定` = キー・値名がバイナリのリテラル**かつ**値がコード既定値/実在 OS 値。`推定` = どれかが推定・選択値。軸は別に保持 (`key_conf` × `value_conf`)。

| key_conf | value_conf | apply | 件数 | 代表 |
|---|---|---|---|---|
| 確定 | 確定 | ✔ | 25 | OS 8 値 (Win10 22H2), FontSubstitutes, Shared\General の既定値群, CAB-213 apply 昇格 4 (Sample rate 等) |
| 確定 | 推定 | ✔ | 15 | Paths (値=VFS 配置先), MachineGuid, ILRegKey 等 license 8, ProxyEnable |
| 推定 | 確定 | ✔ | 38 | `FL Studio 26\General` のコード既定値 (キーが inferred-base), Keyboard Layouts |
| 推定 | 推定 | ✔ | 3 | gate 3 値 (Browser FL CLOUD displayed / Disable FL CLOUD search / CrashLoadingStartupProject: 決定値) |
| 確定 | 確定 | – | 1 | `Windows\PRForm` Grid Contrast (CAB-213 で key 確定; 既定値あり、apply 対象外) |
| 確定 | 推定 | – | 72 | Token\*, Paths\FL Studio, VSTPluginsPath, 値不明の literal 名, CAB-213 で key 確定した値不明 catalog (Render 34 等) |
| 推定 | 確定 | – | 5 | 既定値あり・展開キー/動的尾部キー |
| 推定 | 推定 | – | 74 | 動的尾部キー (placeholder 付き, CAB-213) かつ既定値不明 |
| (key=null) | 推定 | – | 3 | 確定不能 (§3 の 3 件) |

合計: 236 (apply 81 + catalog 155)、confidence=確定 26 / 推定 210 (初版 21 / 220)。key 確定 113 / key 推定 120 / key=null 3。値名はバイナリ上の文字列リテラル由来が大半 (値名自体が推定なのは CSV の `value-name=inferred` 6 行のみ)。不確実なのは主に「どのキー(section)に属すか」と「初期値」。

## 5. テスト (`bash vreg.sh` = 全 PASS, 11 秒)

| 層 | 内容 |
|---|---|
| C 単体 (`test/test_vreg.c`) | FL 流 ReadInt/Bool (REG_SZ 文字列→数値, 空/非数→既定, OS だけ DWORD, 大小無視, 日本語名) / Enum MORE_DATA / 世代・通知 (読出しは不変, 失敗は通知しない) / import (BOM, `-`, hex(7)/hex(b), 既定値) / export_root→clear→import 復元 / 追加 6 API / Registrations 列挙 |
| shimx 結合 (`build.sh shimx`) | shimx の test_core/sys/ole_shell を vreg reg.c で MT+ST、M4 互換 ST — ALL PASS |
| node unit (`regfile`) | 全型 parse/serialize 恒等, UTF-16LE/UTF-8/BOM 無し, 継続行, 削除構文, モデル大小無視, fillMissing |
| node 結合 | **受入**: Shared\Paths / MachineGuid / CurrentVersion の期待値 ✔、**全具象キー往復** ✔、**リロードで HKCU 永続** ✔ + 削除の永続 / HKLM 非永続 / 自動 flush / MachineGuid プロファイル別・安定 / license 切替往復 / external / seed 版更新 / skipGroups / FileStore / coverage |
| IDB | `IdbStore` × FakeIDB (node), × **実 Chrome IndexedDB** (`e2e_chrome.mjs`: 新規→reload→復元→reload→Trial 切替) |
| CLI | UTF-16LE `.reg` を別プロセスで import→export |

## 6. ライセンス: 方針・実施・限界

- 方針根拠: ユーザ確定「全てのライセンス機構は無力化。アクティベーションは無条件通過。必要なら cracked リソースを配置可能」。**CAB-94 チケット本文の「Registrations\* は seed しない」および startup `stub_plan.md §6`/`vreg_seed.json` の「Trial で起動」は本方針で上書き** (それらは読取専用のため未修正 → 要更新)。
- 実施した合成: `ILRegKey`=`WEBSTUDIO-ACTIVATED-PLACEHOLDER` (`FL Studio 26.1` と `FL Data`, HKCU+HKLM), `FL Studio user name/webpass/FLS Info/license plate` (HKCU\Registrations)。**書式は未解読のプレースホルダで、鍵生成アルゴリズムは実装していない**。
- 確認できていること: 登録検査 `FUN_008e6150` (Registrations 配下を `RegEnumKeyExW` で列挙→`FL Studio ` 前方一致→`ILRegKey` 非空) は静的読解どおり満たす (`observeRegistration()` true / Trial で false を自動テスト)。
- **未確認**: `0x10c7cd0` (32 KB 登録パーサ) が MachineGuid/ComputerName 等と突合してプレースホルダを拒否するか。拒否されると bit0 は未登録のまま (`expectedLicense()` の期待 bit0=0 は seed 側の意図で、実 byte の観測は CAB-106)。bit0 の語義 (0=登録) も**推定**のまま。
  追加観察候補: `General\TrialEdition` (既定 `2`, `0x11bddf0` ReadInt / `0x11444e0` WriteInt) はエディション/Trial に関連する可能性があり seed は既定値のまま。
- 拒否された場合の次手: ユーザが `.reg` を `vreg/resources/cracked/` (git 管理外) に置き `externalReg` で投入 / または `0x10c7cd0` の検証解読 (別チケット)。`Token`(FL Cloud 認証) は外部通信対象外 (`docs/DECISIONS.md` D3) に従い seed しない。

## 7. 境界メモ (実装していないもの / 他担当への連絡)

- **CAB-96 win-stubs**: `Reg*` を定義しないこと。vreg の reg.c は shimx の reg.c と**同名シンボルなので同時リンク不可** → 下流ビルドは `shimx/src/*.c` から `reg.c` を除き `vreg/src/reg.c` を入れる (`build.sh` の `SRCS` 参照)。**[CAB-214 follow-up で解消: 同名衝突自体が無くなり、shimx `src/*.c` をそのままリンクすればよい]**`Crypt*` スタブ/`OpenProcessToken`/`GetTokenInformation` は reg.c 同居のまま継承 (shimx 同一挙動)。
- 恒久化するなら shimx 側 (CAB-11 担当) へ本差分の取込を提案 (そうすれば二重管理が消える)。shimx は読取専用のため本チケットでは行わない。
- 未実装 (曖昧/未使用で見送り): `RegNotifyChangeKeyValue` `RegConnectRegistry` `RegLoadKey/SaveKey/CopyTree/ReplaceKey` `RegQueryMultipleValues` `RegGetKeySecurity/SetKeySecurity` `RegOverridePredefKey` `RegOpenCurrentUser` `RegCreateKeyTransacted` `RegSetValueW/RegQueryValueW`(旧式) と GetProcAddress 組込み表 (`proctable.c`) への追加 6 API の登録 (静的 import のみ想定。必要になれば proctable 生成の対象に追加)。
- WOW64 リダイレクトなし (`0x100/0x200` mask は無視; 1 本の木)。HKU/HKCC/HKCR は空 (HKCR は FL が `Software\Classes` を直接見るため不要の見込み)。`KEY_NOTIFY` 等は無視。
- mac の `reg.xml` 形式は未対応 (stub_plan §6 の「後日」)。

## 8. 制限

1. **永続化の flush は通知→`setTimeout`**。FL を専用 Worker で回しメッセージポンプが `Atomics.wait` でブロックする間は JS のタイマが走らない → ブロック中は保存されない。ポンプの yield 点/`pagehide`/`visibilitychange` で `flush()` を呼ぶこと (T6 message-pump と要調整。Worker 内ブロック中の IDB コミット可否は未検証)。
2. 複数タブ同時起動は後勝ち (Web Locks 未使用; FL 側 G06 単一インスタンスと併せて別途)。
3. `readInt` プローブは C `long`(wasm32 は 32bit) で `strtol`: `ScaleHL=4294967294` は飽和する。FL 実装の整数変換 (符号/幅) は未確認で、プローブは「REG_SZ 文字列→数値」という startup REPORT の知見の再現に留まる。
4. seed の `settings`/`shared` 既定値 (57 エントリ) を**書く**ため「値が存在するか」で分岐するコードがあると初回経路が変わる可能性 (例 `Run counter` 存在)。懸念時は `skipGroups:['settings','shared']` (テスト済) で書かずに運用可能。
5. `FL Studio 26\General` 系のキーは inferred-base (wrapper の基底パスからの推定)。実キーは lift 後の open ログで確定する (startup REPORT §4-4)。
6. shimx の m11 IR 署名一致検査 (`verify_sig.sh`) は vreg 版では未実施 (シグネチャは C レベルで同一、`symcheck` 済)。

## 9. ユーザ依頼事項

1. (任意) プレースホルダが `0x10c7cd0` に拒否されたと CAB-106 で分かった場合の cracked 資源 (`.reg`) の配置: `tools/startup/vreg/resources/cracked/*.reg` (`.gitignore` 済)。現時点で必須ではない。
2. CAB-94 本文と `stub_plan.md §6` / `vreg_seed.json` の「Registrations は seed しない」記述を、本方針に合わせて更新して良いか (読取専用のため未修正)。

## 10. 次タスク提案

- **CAB-106 license-observation**: lift 後に `vreg` の open/read ログ + byte[0x14f84a8] を観測 (`Vreg` の `licenseFlagBit0` 0/1 で A/B、`General\TrialEdition` も記録)。`generation()` と通知フックで Reg 呼出トレースを取る拡張が容易。
- vreg → hostbridge 結線: `Vreg.create` を startup-glue (T1) のブートに組込み、`flush()` を message-pump (T6) の yield 点に接続 (制限 1)。
- `0x10c7cd0` 登録パーサの解読 (入力=ILRegKey 書式, MachineGuid 依存の有無)。
- ~~shimx 本体への reg.c 取込 (CAB-11) と vreg の薄い層化。~~ → 完了 (取込 CAB-214 / 薄ラッパ化 CAB-214 follow-up)。
- ~~low-key 112 エントリの実キー確定~~ は CAB-213 + §11 で完了 (112→3、上書き表は `scripts/build_seed.py` の OVERRIDES が正本)。残: lift 後 open ログによる推定 47 (placeholder 付き) の具体化 → OVERRIDES へ追記。

## 11. CAB-213 反映: key 上書き表 OVERRIDES の正本化 (CAB-213 follow-up)

**結論**: CAB-213 (74ea63b) の `tools/startup/keyfix/apply_keys.py` にあった OVERRIDES 表 (定義 115 / 一致 112) を **`scripts/build_seed.py` へ verbatim 移設**。`build_seed.py` 単独で CAB-213 の成果 (236 / apply 81 / 被覆 229/229 / key 確定 113 / key=null 3) が再現され、`vreg.sh` の seed 再生成で成果が消える二重管理は解消した。

- **正本**: 以後 key 上書きは `build_seed.py` の `OVERRIDES` のみを編集する。keyfix 側の同表は履歴 (根拠は keyfix/REPORT.md §1) で正本ではない (keyfix は読取専用のため無改変)。`keyfix_e2e.sh` は build_seed → apply_keys の順を保つが、apply_keys は残 3 件 (key=null) を再照合するだけの no-op になり、seed.json はバイト不変 (実測)。
- **実装**: `apply_overrides(out_entries)` を整列後・`seed` 組立前に適用 (整列は上書き前 key で行うため並びが CAB-213 成果物とバイト同一)。同一座標 (hive,key,name) の重複カタログ 5 件削除 (coverage テストが catalog 値の非書込を要求) と apply 昇格 4 (MIDIForm の 3 値 + Sample rate) も同ロジックで移設。実行ログ末尾に `overrides: low_key=112 defined=115 matched=112 apply_promoted=4 removed_duplicates=5 null_key_after=3` を出力。未一致の定義 3 (`FUN_00ba5650` Visible/Left/Top) は該当 low-key が無い予備定義で、verbatim 移設のため残置。
- **再生成 diff (実測)**:

| 比較 | 結果 |
|---|---|
| 新 `build_seed.py` 再生成 seed.json vs CAB-213 コミット (74ea63b) | **バイト同一** (`cmp`; keys.json・coverage.json も同一) |
| 旧 pipeline (旧 build_seed → apply_keys) vs 新 build_seed 単独 | **バイト同一** |
| 旧 `build_seed.py` 単独 (移設前の挙動) | 241 entries / apply 77 / key=null 112 / key 確定 56 = CAB-213 成果が消える (二重管理問題の再現) |
| 新 `build_seed.py` 単独 | 236 / apply 81 / 被覆 229/229 / key 確定 113 / key=null 3 / 座標重複 0 |

- **注意**: 上書き時 `basis` は表の根拠文に置換されるため、CSV 由来の「コード既定値 ReadInt/ReadBool=…」文言は 112 件で失われる (値は不変)。§3 の既定値由来件数を `value_conf` ベースに改めたのはこのため。
- **回帰 (実測)**: `bash tools/startup/vreg/vreg.sh` exit 0 (C 単体 / shimx 結合 ST+MT+M4 / symcheck / wasm / node 22/22 / Chrome 実 IndexedDB)、`bash tools/startup/keyfix/keyfix_e2e.sh` exit 0 (上記 + pathreg 6 groups + `verify_consistency.py` 6 項目 ALL PASS)。
- **残 (keyfix 担当範囲)**: `apply_keys.py` への廃止注記と `keyfix_e2e.sh` step 1 からの `apply_keys.py` 除去は keyfix 側の編集が必要 (本チケットでは未実施)。

## 12. #116 (ST-T9) ユーザ .reg 取込の入口 (vreg 側・2026-10-14)

**結論**: ユーザが自分で書き出した .reg を仮想レジストリへ取り込む入口 (`ui/import.html`) と、MachineGuid のユーザ指定を追加した。実 Chrome の IndexedDB で、取込と MachineGuid が再読込をまたいで残ることを確認した。製品 `src/` の startup への結線は本節の範囲外 (子 issue)。FLEngine は起動していない。

**本 PR が定めた受入範囲 (#116 本文に受入条件の記載なし)**

| 条件 | 結果 |
|---|---|
| 取込: 選んだ .reg を受理し、取込後 `observeRegistration()` が登録済み・mode=external になる | PASS (値 3 件) |
| 不正: 1 行目ヘッダ不一致・値なしは拒否し、取込済みの状態を変えない | PASS |
| 生成しない: 受理したバイト列をそのまま保存し、鍵の生成・改変はしない | 設計 (`js/license_import.mjs`) |
| 永続: 再読込後も取込内容と MachineGuid が残り、既定 placeholder に戻らない | PASS |
| MachineGuid: ユーザが 8-4-4-4-12 の 16 進で指定 (保存は小文字) | PASS |

**設計**
- `js/license_import.mjs`: 取込バイト列を `<profile>#user-reg` キーで store に保存し、以後の boot で `externalReg` として最後に適用する。external モードでは seed の license 値を除き、ユーザ値だけが残る。
- 取込と MachineGuid 変更は「保存 → 仮想レジストリを開き直す」で行う。取込直後の状態と再読込後の状態が一致する。
- 開き直した後に `flush(true)` で決定値を記録する。vreg は新規プロファイル以外で記録しないため、これが無いと MachineGuid が再読込で戻る (e2e で検出して修正)。

**実測 (測定 commit `361e35d6`・コードを変えた最後の commit)**

| 項目 | 結果 |
|---|---|
| 実行 | `RUNTIME_TMP=<一時ディレクトリ> bash tools/startup/vreg/vreg.sh` |
| 所要 / exit / load (実行前 1 分平均) | 12.03 s / 0 / 0.31 |
| C 単体 (`test_vreg.c`) | ALL PASS |
| shimx 既存テスト (st / mt / M4) | ALL PASS × 3 |
| symcheck | vreg 要求 38 シンボルを shimx reg.c が全て定義 (reg.c 公開 45) |
| node テスト | 24 / 24 PASS (既存 22 + `checkUserReg` 2) |
| Chrome e2e `e2e_chrome.mjs` (既存) | PASS |
| Chrome e2e `e2e_import_ui.mjs` (新規) | PASS: 初回 placeholder → 取込 (external) → 不正拒否 → MachineGuid 設定 → reload で取込と GUID 維持 |

測定後のコード差分: `git diff 361e35d6 HEAD -- tools/startup/vreg ':!tools/startup/vreg/REPORT.md'` の出力は 0 行 (本節の追記は REPORT のみ)。

**未解決**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 製品 `src/` の startup への vreg 結線 (wasm の製品バンドル組込みと、製品 UI の入口への配置) | 製品ユーザは取込を使えない | 子 issue (#116 の issue コメント参照) |
| 取込の取消し UI。取込済みの値のうち seed 外のキーは HKCU に残る | 取消しは profile 削除でしかできない | 子 issue (同上) |
| 取込が 0x10c7cd0 の本検証を通るか (gradeChar > 0x40) | ライセンス判定への効果は未確認 | #785 (ST-T16 子-1) |

## 13. #2793 (ST-T21) 製品ページへの .reg 取込入口・取消し (2026-10-15)

**結論**: 製品ページ (`index.html`) に `?license=import` で開く取込入口を置いた。取込・不正拒否・MachineGuid 設定・再読込保持に加え、取消し (既定の登録済み placeholder へ戻す) を製品 bundle 上の headless Chrome で確認した。既定ページには入口も vreg も載らない。**FLEngine の起動経路は vreg を読まない** (取込値は IndexedDB に保存されるだけで、FL 本体の登録判定には届いていない。残りは `[ST-T22]` へ起票)。

**設計**
- `src/runtime/license_import_panel.ts`: 製品側の入口 (DOM は `ui/import.html` と同じ操作・ID は `license-*`)。`src/index.ts` が `?license=import` のときだけ `import()` する。vreg wasm (200KB) と seed は `license_import_panel` chunk (252 KB) にだけ入り、既定の `index` chunk (60 KB) には vreg の痕跡が 0 件 (`grep` 実測)。
- `js/license_import.mjs` `revertUserReg()`: 取込バイト列 (`<profile>#user-reg`) を消し、プロファイル記録を消して開き直す。取込が無ければ何もせず `false`。MachineGuid は保持する。
- **プロファイル記録ごと作り直す理由**: vreg は HKCU 全体を保存する。`#user-reg` だけを消すと、取込由来の seed 外の値 (`Software\Image-Line\E2E-Import\Marker` 等) が HKCU の永続値に残る。ネガティブコントロール (記録の削除を外す) で、この残存を e2e が検出することを確認済み (下表)。
- `src/runtime/vreg_modules.d.ts`: vreg の JS / wasm の型宣言 (実装の正本は `tools/startup/vreg/js/*.mjs`)。

**実測 (測定 commit `d04ba8206`・コードを変えた最後の commit)**

| 項目 | 結果 |
|---|---|
| 実行 | `RUNTIME_TMP=<一時ディレクトリ> bash tools/startup/vreg/vreg.sh` |
| 所要 / exit / load (実行直前の uptime: 1 分 0.03・5 分 0.25・15 分 0.20) | 17 s / 0 / 0.03 |
| C 単体 / shimx 既存 (st・mt・M4) / symcheck | ALL PASS / ALL PASS ×3 / vreg 要求 38 シンボルを shimx reg.c が全て定義 (公開 45) |
| node テスト | **25 / 25 PASS** (既存 24 + `revertUserReg` 1) |
| Chrome `e2e_chrome.mjs` (既存) | PASS |
| Chrome `e2e_import_ui.mjs` (既存・ui/import.html) | PASS |
| Chrome `e2e_product_import.mjs` (新規・製品 bundle) | **PASS** (Chrome 155。既定ページに入口なし → 製品ページで 初回 placeholder → 取込(external) → 不正拒否 → MachineGuid 設定 → reload 保持 → 取消し → reload で既定のまま。所要 3.1 s) |
| ネガティブコントロール (記録の削除を外す) | `e2e_product_import.mjs` が FAIL: `AssertionError … actual: true, expected: false` (取消し後の Marker 残存を検出)。元に戻して PASS を再確認 |
| 製品 bundle (`vite build`) | `license_import_panel` 252.03 kB (gzip 56.62) / `index` 60.25 kB (gzip 24.12)。`index` の vreg 痕跡 0 |

測定後のコード差分: `git diff d04ba8206 HEAD -- src tools/startup/vreg ':!tools/startup/vreg/REPORT.md'` の出力は 0 行 (本節の追記は REPORT のみ)。

**範囲と限界**
- 取込入口は query (`?license=import`) のみ。メニューからは開けない。
- 取込値は profile `default` の IndexedDB に保存されるが、**FLEngine の起動経路 (`src/runtime` の worker) は vreg を呼ばない**。`tools/startup/glue/host/glue_host.ts` の RegBridge は node 実行専用で、製品 bundle には入っていない。→ `[ST-T22]` (起票先)。
- 取込が FLEngine の登録判定 (0x10c7cd0 → byte[0x14f84a8]) を通るかは未確認 (#785)。
- 製品の起動 (FLEngine boot) は**動かしていない** (fl-win64 は未展開・未実行)。KPI (dispatch 数・通過 unit 数・最初のウィンドウ) は測っていない。既定ページの起動経路は変更していない。
- 既存の runtime e2e (`pnpm runtime:e2e`) は `tools/runtime/work/wasm` (stage 済み wasm) が無いため**未実行**。
- ui/import.html (standalone) に取消しは無い (製品側のみ)。
- vite build は `FL_WIN64_DIR` 未指定で THIRD_PARTY_NOTICES 不完全 (15 件) の既存警告を出す。本変更の依存ではない。
