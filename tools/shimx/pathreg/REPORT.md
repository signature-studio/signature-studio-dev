# REPORT — CAB-168 (SHX-T3): パス写像・レジストリ永続化の shimx 側インタフェース接続

日付: 2026-10-10 / 親: CAB-11 (shimx, Done) / 関連: CAB-94 (vreg, Done)・CAB-104 (asset-vfs E, 稼働中)・CAB-98 (nfo)・CAB-213 (実キー確定)・CAB-101 (実FL結線)
書込範囲: `tools/shimx/pathreg/` のみ (shimx 既存ファイル・tools/startup・tools/assets・tools/hostbridge は無変更, `git status` で `?? tools/shimx/pathreg/` のみ)
検収: **`bash tools/shimx/pathreg/scripts/e2e.sh` → exit 0 (8.5 秒)**。`bash tools/shimx/test.sh --quick` も PASS を確認 (影響 0)

> **更新 2026-10-10 (CAB-214 follow-up, shimx REPORT §12)**: shimx の username 統一 (`C:\Users\webstudio`) と vreg reg.c の取込・退役に伴い、
> ①予備 profile `user2Profile` (`C:\Users\user` の alias mount 6 本) を**退役** (既定表は install + webstudio×6 + `C:` = **8 本**。C/JS 既定・
> `PathRegPaths` から `user2Profile` 削除。fixture は webstudio 表記に更新し、退役 alias が残余 `C:` 規則 `/c/Users/user/...` に落ちる陰性確認を C/JS/e2e に追加)、
> ②`module-a` は shimx 全 src (reg.c 含む) + vreg `probe.c` のリンクに変更 (vreg/src/reg.c は削除済み)。以下の本文中の「vreg reg.c 結線」は
> 「vreg_* フック export 構成」、「2 種の profile」は「webstudio のみ」と読み替える。e2e 6 groups PASS 維持。

## 0. 結論 (数値は全て実測)

1. **パス写像インタフェースを実装し、C (wasm) と JS の双方で同一結果になることを 15 fixture で検証した**。
   FL が期待する Windows パス (インストール dir / %APPDATA% / Documents\Image-Line / Plugin database / Temp) を
   仮想 FS (`/fl` = E asset bundle, `/c/home/...` = OPFS 永続, `/c/tmp` = MEMFS) へ写像する。正規化参照実装
   (大小無視・区切り文字・ドライブレター・`\\?\`・`.` `..` 畳み込み) 付き。C 側は `shimx_set_path_mapper`
   (既存フック, shimx 無変更) に登録する `shimx_path_mapper_fn` 互換関数で、未対応パスは <0 を返して
   shimx 既定写像 (`C:\x`→`/c/x`, POSIX 素通し) に委譲する。
2. **レジストリ永続化接続を 2 つのリンク構成で実装・検証した**: (a) vreg reg.c 結線 (本番推奨) — 通知フック
   `vreg_set_notify` → 遅延 flush、(b) shimx reg.c のまま — flush 点で C hash (export 全文 FNV-1a 64bit) を
   比較。**永続レコードは vreg `Vreg.flush()` と同一形式**で、e2e で**本物の vreg Vreg アダプタとの
   双方向相互運用** (bridge 書込→vreg 読取 / vreg 書込→bridge 読取, MachineGuid 一致) を確認した。
3. テスト: C 単体 (正規化 18 例・マウント 14 表・写像 8 例・実ファイル I/O・hash) を **ST/MT 両方 ALL PASS**、
   JS 単体 4/4、e2e 6 グループ (遅延 flush / onYield / onPageHide / flush 点契約 / 削除の永続 / C↔JS クロスチェック)。
   成果物 1,547 行 (C 460 / JS 462 / テスト 541 / スクリプト 84)。モジュール: module_a 204,830 B /
   module_b 188,820 B (SINGLE_FILE, wasm 埋込済み)。
4. **発見 (CAB-213 へ)**: shimx 内蔵の `SHGetFolderPathW`/環境変数は `C:\Users\user` 固定に対し、vreg seed の
   `Shared data` 値は `C:\Users\webstudio\Documents\Image-Line\` (推定)。両方を既定マウント表に登録して
   同一実体へ写像することで当面は吸収した (§3)。実キー確定時にどちらかに統一すること。
   **→ 解消 (CAB-213 + CAB-214 + follow-up)**: webstudio に統一済み、予備 `user` mount は退役。

## 1. 成果物 (`tools/shimx/pathreg/`)

| パス | 内容 |
|---|---|
| `include/pathreg.h` | 契約書 (135 行): マウント表 API / 正規化 / 写像 / 変更検出 + **ホストブリッジ (JS) フック署名・シリアライズ形式・flush タイミング・必要エクスポート一覧** |
| `src/pathmap.c` (267 行) | 正規化 `pathreg_normalize` / マウント表 `pathreg_{set_paths,add_mount,remove_mount,clear_mounts,get_mount}` / 写像 `pathreg_map` (`shimx_path_mapper_fn` 互換) + `pathreg_install()` / 逆写像 `pathreg_unmap` / 既定表の遅延ロード |
| `src/regpersist.c` (48 行) | `pathreg_reg_hash` (export 全文 → FNV-1a 64bit) / `pathreg_reg_changed` / `pathreg_reg_mark_saved` / `pathreg_reg_seed_text` |
| `js/pathmap.mjs` (110 行) | C の JS ミラー: `normalizeWinPath` / `createMapper` (既定表 + 追加マウント) / `defaultMounts` / `DEFAULT_PATHS`。glue が wasm 起動前に「どこに書けば C から見えるか」を計算する用 |
| `js/regbridge.mjs` (352 行) | `RegBridge`: seed 適用 (vreg `resolveSeed` 再利用) → `shimx_reg_import_text` 一括投入、変更検出 (通知 or hash)、flush (vreg 互換レコード)、`onYield`/`onPageHide`、検証用 read/write/delete API、`observeRegistration` (FUN_008e6150 同型判定) |
| `test/test_pathreg.c` (229 行) | C 単体 (shimx 結合含む)。`build.sh test` で ST/MT 両方実行 |
| `test/pathmap.test.mjs` (86 行) | JS 単体 (node:test 4 件) |
| `test/e2e.mjs` (181 行) | e2e: モック永続化層 (MemoryStore) で「再起動」を含む往復 + **本物の vreg Vreg との相互運用** + C↔JS 写像クロスチェック |
| `scripts/build.sh` | `test` / `module-a` (vreg_* フック export + probe.c 同梱) / `module-b` (フック非 export) / `all`。emcc フラグは shimx `flags.sh` を流用 |
| `scripts/e2e.sh` | 1 コマンド検収 (build → C 単体 ST/MT → JS 単体 → e2e) |

vreg 資産の利用は **import のみ** (読取専用遵守): `regfile.mjs` (model/serialize)・`seed.mjs` (`resolveSeed`)・
`store.mjs` (`MemoryStore/FileStore/IdbStore` がそのまま使える)・`vreg.mjs` (相互運用テスト)。

## 2. パス写像仕様

### 2.1 正規化 (`pathreg_normalize` / JS `normalizeWinPath`)

`/`→`\` 統一、`\\?\` / `\\.\` プレフィクス剥がし (`\\?\UNC\srv\share` → `\\srv\share` 保持)、
ドライブレター大文字化、連続区切り圧縮、`.` `..` 畳み込み (根を超える `..` は無視 = Win32 相当、
ドライブ表記 `X:` は根として保護)、末尾 `\` 除去 (`C:\` は保持)。大小文字は**保持**する
(比較のみ無視。E の manifest tree も大小無視 lookup のため実害なし)。

### 2.2 既定マウント表 (stub_plan §4 / vreg seed paths / nfo 配置規則と整合)

| Win パス接頭辞 | 実体 | flags |
|---|---|---|
| `C:\Program Files\Image-Line\FL Studio 2026` | `/fl` | RO (E asset bundle。tools/assets/vfs/emscripten.ts の mount 点) |
| `<profile>\Documents\Image-Line` (= Shared data) | `/c/home/Documents/Image-Line` | PERSIST。**Plugin database (`FL Studio\Presets\Plugin database\Installed\{Effects\|Generators}\{VST\|VST3\|AudioUnit\|CLAP}\`) はこの下に乗る (nfo REPORT §3)** |
| `<profile>\AppData\Roaming` | `/c/home/AppData/Roaming` | PERSIST (%APPDATA%) |
| `<profile>\AppData\Local\Temp\Image-Line` | `/c/tmp` | TMP (S18 の一時 dir。Local より長い接頭辞で勝つ) |
| `<profile>\AppData\Local` | `/c/home/AppData/Local` | PERSIST (%LOCALAPPDATA%) |
| `<profile>\AppData\Roaming\Image-Line` | `/c/home/AppData/Roaming/Image-Line` | PERSIST |
| `<profile>` | `/c/home` | PERSIST (`<profile>` = `C:\Users\webstudio` のみ。旧予備 `C:\Users\user` は退役) |
| `C:` | `/c` | PERSIST (shimx 既定と同じ形。表を自己完結させるため明示) |

照合は**大小無視・最長一致** (同長は後勝ち、セグメント境界必須)。未登録 (`D:\` 等や POSIX 形) は
`pathreg_map` が **<0** を返し shimx 既定写像に委譲 (M4 互換の POSIX 素通し・相対→Win cwd も維持)。
CAB-101 は `pathreg_set_paths()` / `pathreg_add_mount()` で実配置に合わせて上書きできる
(E の mount 点を変えるなら `vfsInstall` を 1 文字列変えるだけ)。

### 2.3 検証実績

- C 単体: 正規化 18 例 (UNC / `\\?\` / 相対 / 根超え pop 含む)、マウント表操作、写像 8 例
  (asset 読取 / Shared data 書込 / Temp 優先 / フォールバック)、**実ファイル I/O** — `/fl` 側 0444 ファイルを
  `CreateFileW(GENERIC_READ)` で読めて `GENERIC_WRITE` は `ERROR_ACCESS_DENIED` (E の EPERM 相当)、
  `/c/home/...` 側へ `CreateFileW(CREATE_ALWAYS)+WriteFile` で書けて posix 側から同一バイトを読取 — を ST/MT 両方 PASS。
- e2e クロスチェック: 15 fixture (`\\?\` 付き・UNC・相対・未登録含む) で **C `pathreg_map` と JS `createMapper` が
  全件一致** (非対応は両方 null) + 逆写像一致 + 追加マウント一致 + 既定表件数一致 (14)。

## 3. レジストリ永続化接続

### 3.1 構成と契約 (詳細は `include/pathreg.h` コメント)

```
wasm (shimx Reg* + pathreg) ⇄ RegBridge (js/regbridge.mjs) ⇄ store {load,save,delete} ⇄ IndexedDB
   Reg* 読み書き本体            seed 適用 / 変更検出 / flush       vreg store.mjs 互換     IdbStore:
                                                                                DB webstudio-vreg / profiles / key=profile
```

- **C ↔ JS ワイヤ形式**: `.reg` テキスト v5.00 (UTF-8)。C: `shimx_reg_export_text` (要 `_free`) / `shimx_reg_import_text`。
  JS: vreg `regfile.mjs` の `parseToModel` / `serializeReg` (全型対応、往復は vreg REPORT §3 の 57/57 実績を継承)。
- **永続レコード** (vreg `Vreg.flush()` と同一・相互運用可): `{ schema:1, seedVersion, machineGuid, savedAt, hkcu }`
  (`hkcu = { "<key>": { "<name>": { t:"REG_SZ"|..., v } } }`)。**HKCU のみ永続** (HKLM 等は seed から毎回再構成 = vreg と同一方針)。
- **flush タイミング (vreg REPORT §8-1 準拠)**: 変更 → 遅延 flush (既定 200ms) に加え、ポンプ yield 点で
  `onYield()`、`pagehide`/`visibilitychange` で `onPageHide()` を**明示的に**呼ぶ。e2e で「yield 無しの変更は
  次セッションに載らない (Atomics.wait 中は JS タイマが走らないため) こと」と「onYield/onPageHide で載ること」を両方検証。

### 3.2 2 つのリンク構成 (自動判別: `_vreg_export_root` の有無)

| | (a) vreg_* フック export (本番推奨; module-a) | (b) フック非 export (module-b) |
|---|---|---|
| リンク | shimx src 全部 (reg.c は CAB-214 で vreg 拡張取込済み) + `vreg/src/probe.c` を追加。`vreg_*` を EXPORTED に載せる | shimx src のまま (`vreg_*` 非 export) |
| 変更検出 | `vreg_set_notify` (addFunction 'vi') → dirty → 遅延 flush。`vreg_generation` で確認 | flush 点で `pathreg_reg_hash` (FNV-1a 64bit) を前回保存値と比較。通知口を増やしたい場合は CAB-101 が Reg* 呼出を wrap して `_pathreg_reg_mark_saved` 相当を叩ける (本実装は不要と判断) |
| 復元 | `vreg_clear_root(HKCU)` → 永続 model + `fillMissing(seed)` を import (削除含め永続値が正) | `shimx_reg_reset` は使わず (新規インスタンス = 内蔵既定のみ)、import 後に**内蔵既定 HKCU にあって永続 model に無い値/キーを Reg* で差分削除** (`_applyHkcuDeletions`) |
| seed 投入 | `shimx_reg_import_text` 一括 (=CAB-98 の `shimx_reg_set*` 個別投入も可。両方テスト済) | 同左 |
| 検証 | e2e A (遅延 flush・onYield・onPageHide・**vreg Vreg 双方向相互運用**) | e2e B (往復・**built-in 既定値削除の永続**・hash 検出・直後 flush no-op) |

e2e 実測: 復元後の `Software\Image-Line\FL Studio 26\General\Run counter` (REG_DWORD)・`LastProject` (REG_SZ)・
削除した `Control Panel\International\sDecimal` (内蔵既定) が**再起動後も正しく保持/欠落**、
`MachineGuid` はプロファイル内で安定。snapshot keys=50 種。

## 4. CAB-101 (実FL結線) での利用方法

```js
// 1) モジュール: tools/shimx/pathreg/scripts/build.sh module-a の構成で lift 済み FL とリンク
//    (shimx src 全部 (reg.c 含む) + vreg/src/probe.c + tools/shimx/pathreg/src/*.c を追加。
//     EXPORTED_FUNCTIONS は include/pathreg.h の一覧 + FL 本体が必要な分)
import createPathregModule from '<...>/module_a.mjs';
const mod = await createPathregModule();
const bridge = await RegBridge.create({ mod, store: new IdbStore(), seed, profile: 'default' });
//    ↑ boot 内で _shimx_init / _pathreg_install (mapper 登録) / seed 適用 / 復元 / flush(false→初回は強制) まで完了

// 2) FS 側 (E との結合手順):
//    - 読取: E の createEmscriptenFs(FS, vfs) を /fl に mount (既定表どおり)。OpfsCache 等は E の手順どおり
//    - 書込: /c/home/... (/c/tmp) を MEMFS+IDBFS または OPFS 由来の書込可 FS で mount。
//      写像先の計算は js/pathmap.mjs (C と全 fixture 一致) を使って起動前に mkdir/事前配置できる
//      (例: nfo の generateDb() 出力を /c/home/Documents/Image-Line/FL Studio/Presets/Plugin database/ へ)
// 3) ランタイム: メッセージポンプの yield 点で bridge.onYield()、pagehide/visibilitychange で
//    bridge.onPageHide()。 Worker 終了前にも close() (flush + 通知フック解除)
// 4) 設定: 実配置が確定したら pathreg_set_paths() で mount 表を上書き (C) + createMapper({paths}) (JS) を同一値に
```

E (asset-vfs) 側は無変更で良い (`/fl` mount 点と vpath = tree 相対の規約を本側が既定表に採用)。
書込可領域の mount 実装 (IDBFS/OPFS) は CAB-104/CAB-101 の担当範囲で、本チケットは
「どの Win パスがどの FS パスになるか」の契約とハーネスを提供する。

## 5. 制限

1. **HKCU のみ永続** (HKLM 等はセッション内のみ) — vreg と同一方針。vreg seed の HKLM 値は毎起動再適用される。
2. **shimx reg.c 構成の削除永続は HKCU のみ** (`_applyHkcuDeletions`)。HKLM の built-in 既定削除は復元時に復活する
   (vreg 結線でも HKLM は clear しないため同条件)。キー削除は葉のみ (RegDeleteKeyW の制約)。日本語等
   非 ASCII キー名の削除も動くが、mount 表の照合は ASCII 大小無視のみ (UTF-8 全体の casefold はしない。
   E の lookup が大小無視のため実害なしと判断)。
3. **pathreg_map の入力は UTF-8 前提** (shimx `shimx_path_to_posix` と同じ)。W 版 API は shimx 内部で UTF-8 化してから mapper へ渡る。
4. hash 変更検出 (構成 b) は export 全文の O(レジストリ全体) — flush 点のみ呼ぶ設計なので実用上無視できるが、
   高頻度ポーリングは想定していない。誤「無変更」確率は FNV-1a 64bit 衝突時のみ (事実上 0)。
5. レコードの `hkcu` は「その時点の全 HKCU」を含む (vreg と同一)。seed version 更新時は `fillMissing` で
   不足分のみ補完 (ユーザ変更・削除は保持)。レコード破損時のマイグレーションは未実装 (schema:1 固定)。
6. 実 FL バイナリを通した検証は未了 (本チケットはインタフェース接続。実 FL 結線は CAB-101)。

## 6. ユーザ依頼事項

なし。

## 7. 次タスク提案 (下流チケット案)

| # | チケット | 要点 |
|---|---|---|
| 1 | CAB-101 (実FL結線) | §4 の手順で lift 済み FL + E + RegBridge を 1 プロセスに結線。`SHIMX_TRACE` で Reg*/CreateFile の実呼出を観測し、既定マウント表と seed 値のずれ (username 問題含む) を確定する |
| 2 | ~~CAB-213 (パス実キー確定)~~ | 完了 (webstudio 統一; 予備 `user` mount は CAB-214 follow-up で退役) |
| 3 | E 側書込領域 | `/c/home`, `/c/tmp` の IDBFS/OPFS mount 実装と、`onPageHide` での IDBFS sync (`FS.syncfs`) 接続。flush 契約は本 REPORT §3.1 を流用可 |
| 4 | ~~vreg 取込の恒久化~~ | 完了 (CAB-214: shimx reg.c が正本、vreg/src/reg.c 削除)。構成 (b) は「通知口を export しない」代替経路として存続 (コード退役は任意) |

## 8. 規約遵守メモ

- コミット: `feat(shimx): path mapping + registry persistence interface (CAB-168)` / 追加は `tools/shimx/pathreg/` のみ
  (`build/`, `work/` は gitignore 済)。20MB 超 blob なし (最大 = module_a 204,830 B)。README / tools/docs / shimx 既存ファイルは無変更。
- 再現: `bash tools/shimx/pathreg/scripts/e2e.sh` (8.5 秒, exit 0)。環境: emcc 6.0.12 / node v24.19.0 (emsdk 同梱)。
