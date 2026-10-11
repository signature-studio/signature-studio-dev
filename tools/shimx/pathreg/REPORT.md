# REPORT — CAB-168 (SHX-T3): パス写像・レジストリ永続化の shimx 側インタフェース接続

preflight: RULES_SHA=ff4999169333
日付: 2026-10-10 (CAB-168 実装) / **2026-10-11 (CAB-271 既定ロード上書きバグの根本修正)** / 親: CAB-11 (shimx, Done) / 関連: CAB-94・CAB-104・CAB-98・CAB-213・CAB-101
書込範囲: `tools/shimx/pathreg/` のみ (shimx 既存ファイル・tools/startup・tools/assets・tools/hostbridge は無変更, `git status` で `?? tools/shimx/pathreg/` のみ)
検収: **`bash tools/shimx/pathreg/scripts/e2e.sh` → exit 0 (12.9〜15.4 秒・実測 n=7・§8-3)**。`bash tools/shimx/test.sh --quick` も PASS (影響 0)

> **更新 2026-10-10 (CAB-214 follow-up, shimx REPORT §12)**: shimx の username 統一 (`C:\Users\webstudio`) と vreg reg.c の
> 取込・退役に伴い、①予備 profile `user2Profile` (alias mount 6 本) を**退役** (既定表は install + webstudio×6 + `C:` = **8 本**。
> 退役 alias が残余 `C:` 規則 `/c/Users/user/...` に落ちる陰性確認を追加)、②`module-a` は shimx 全 src + vreg `probe.c` のリンクに変更。
> 以下「vreg reg.c 結線」は「vreg_* フック export 構成」、「2 種の profile」は「webstudio のみ」と読み替える。e2e 6 groups PASS 維持。

> **更新 2026-10-11 (CAB-271)**: `pathreg_set_paths()` 直後の初回 `pathreg_map()` が既定マウント表で**上書き**するバグを根本修正
> (§8-3)。既定表は `pathreg_set_paths()` を一度も呼ばない経路でのみ遅延ロードされる。既定経路 (`test_defaults.c`) と明示設定経路
> (`test_pathreg.c` §1.5) を分離し `build.sh nc` でネガコン (規則 41)。fixture 16 件・既定表 8 本・e2e 6 groups・glue e2e は
> 不変。行数 1,508→**1,709**・module →**204,729/190,698 B**・JS 単体 4→**5** 件。詳細は **`REPORT_CAB-271.md`**。

## 0. 結論 (数値は全て実測)

1. **パス写像インタフェースを実装し、C (wasm) と JS の双方で同一結果になることを 16 fixture で検証した**。FL が期待する Windows
   パス (インストール dir / %APPDATA% / Documents\Image-Line / Plugin database / Temp) を仮想 FS (`/fl` = E asset bundle,
   `/c/home/...` = OPFS 永続, `/c/tmp` = MEMFS) へ写像する。正規化参照実装 (大小無視・区切り・ドライブレター・`\\?\`・`.` `..`
   畳み込み) 付き。C 側は `shimx_set_path_mapper` (既存フック, shimx 無変更) に登録する `shimx_path_mapper_fn` 互換関数で、
   未対応は <0 を返して shimx 既定写像に委譲。
2. **レジストリ永続化接続を 2 つのリンク構成で実装・検証した**: (a) 通知フック `vreg_set_notify` → 遅延 flush (本番推奨)、
   (b) flush 点で C hash (export 全文 FNV-1a 64bit) を比較。**永続レコードは vreg `Vreg.flush()` と同一形式**で、
   e2e で**本物の vreg Vreg アダプタとの双方向相互運用** (MachineGuid 一致) を確認した。
3. テスト: C 単体 (正規化 18 例・マウント表 8 本・写像 8 例・実ファイル I/O・hash) を **ST/MT 両方 ALL PASS**、JS 単体 **5**/5、
   e2e 6 グループ (遅延 flush / onYield / onPageHide / flush 点契約 / 削除の永続 / C↔JS クロスチェック)。成果物 **1,709 行**
   (§8-1・README・REPORT・accept_recount を除く 12 ファイル。C 474 / JS 461 / テスト 654 / スクリプト 120)、module_a **204,729 B** / module_b **190,698 B**。
4. **発見 (CAB-213 へ) → 解消**: shimx 内蔵 `SHGetFolderPathW`/環境変数 (`C:\Users\user`) と vreg seed の `Shared data`
   (`C:\Users\webstudio\...`) の不一致は、webstudio に統一済みで予備 `user` mount も退役。

## 1. 成果物 (`tools/shimx/pathreg/`)

| パス | 内容 |
|---|---|
| `include/pathreg.h` | 契約書: マウント表 API / 正規化 / 写像 / 変更検出 + **ホストブリッジ (JS) フック署名・シリアライズ形式・flush タイミング・必要エクスポート一覧**。set_paths 後の既定ロード抑制を明記 (CAB-271) |
| `src/pathmap.c` | 正規化 `pathreg_normalize` / マウント表 `pathreg_{set_paths,add_mount,remove_mount,clear_mounts,get_mount}` / 写像 `pathreg_map` (`shimx_path_mapper_fn` 互換) + `pathreg_install()` / 逆写像 `pathreg_unmap` / 既定表の遅延ロード (`pr_ensure_defaults`) |
| `src/regpersist.c` | `pathreg_reg_hash` (export 全文 → FNV-1a 64bit) / `pathreg_reg_changed` / `pathreg_reg_mark_saved` / `pathreg_reg_seed_text` |
| `js/` | `pathmap.mjs` = C の JS ミラー (`normalizeWinPath` / `createMapper` / `defaultMounts` / `DEFAULT_PATHS`。glue が起動前に「どこに書けば C 側から見えるか」を計算する用)。`regbridge.mjs` = `RegBridge` (seed 適用 → `shimx_reg_import_text` 一括投入、変更検出 (通知 or hash)、flush (vreg 互換レコード)、`onYield`/`onPageHide`、検証用 read/write/delete API、`observeRegistration`) |
| `test/` | `test_pathreg.c` (C 単体・shimx 結合含み・§1.5 で既定/明示を検証)・`test_defaults.c` (既定経路専用・CAB-271)・`pathmap.test.mjs` (JS 単体 5 件)・`test_common.h` (集計除外)・`e2e.mjs` (モック永続化層で「再起動」往復 + **本物の vreg Vreg との相互運用** + C↔JS 写像クロスチェック) |
| `scripts/` | `build.sh` (`test` ST/MT × `test_pathreg`+`test_defaults` / `module-a` (vreg_* フック export + probe.c 同梱) / `module-b` (フック非 export) / `nc` (ネガコン) / `all`)・`e2e.sh` (1 コマンド検収)・`accept_recount.mjs` (集計除外) |

## 2. パス写像仕様

### 2.1 正規化 (`pathreg_normalize` / JS `normalizeWinPath`)

/`→`\` 統一、`\\?\` / `\\.\` 剥がし (`\\?UNC\srv\share` → `\\srv\share` 保持)、ドライブレター大文字化、連続区切り圧縮、`.` `..` 畳み込み
(根を超える `..` は無視 = Win32 相当、`X:` は根として保護)、末尾 `\` 除去 (`C:\` は保持)。大小文字は**保持**する (比較のみ無視)。

### 2.2 既定マウント表 (stub_plan §4 / vreg seed paths / nfo 配置規則と整合)

| Win パス接頭辞 | 実体 | flags |
|---|---|---|
| `C:\Program Files\Image-Line\FL Studio 2026` | `/fl` | RO (E asset bundle。tools/assets/vfs/emscripten.ts の mount 点) |
| `<profile>\Documents\Image-Line` (= Shared data) | `/c/home/Documents/Image-Line` | PERSIST。**Plugin database (`...\Installed\{Effects\|Generators}\{VST\|VST3\|AudioUnit\|CLAP}\`) はこの下 (nfo REPORT §3)** |
| `<profile>\AppData\Roaming` | `/c/home/AppData/Roaming` | PERSIST (%APPDATA%) |
| `<profile>\AppData\Local\Temp\Image-Line` | `/c/tmp` | TMP (S18 の一時 dir。Local より長い接頭辞で勝つ) |
| `<profile>\AppData\Local` | `/c/home/AppData/Local` | PERSIST (%LOCALAPPDATA%) |
| `<profile>\AppData\Roaming\Image-Line` | `/c/home/AppData/Roaming/Image-Line` | PERSIST |
| `<profile>` | `/c/home` | PERSIST (`<profile>` = `C:\Users\webstudio` のみ。旧予備 `user` は退役) |
| `C:` | `/c` | PERSIST (shimx 既定と同じ形。表を自己完結させるため明示) |

照合は**大小無視・最長一致** (同長は後勝ち、セグメント境界必須)。未登録 (`D:\` 等や POSIX 形) は `pathreg_map` が **<0** を返し
shimx 既定写像に委譲 (M4 互換の POSIX 素通し・相対→Win cwd も維持)。CAB-101 は `pathreg_set_paths()` / `pathreg_add_mount()` で
実配置に合わせて上書きできる (E の mount 点を変えるなら `vfsInstall` を 1 文字列変えるだけ)。

### 2.3 検証実績

- C 単体: 正規化 18 例 (UNC / `\\?\` / 相対 / 根超え pop 含む)、マウント表操作 (既定表 **8 本**)、写像 8 例 (asset 読取 /
  Shared data 書込 / Temp 優先 / フォールバック)、**実ファイル I/O** — `/fl` 側 0444 ファイルを `CreateFileW(GENERIC_READ)` で
  読めて `GENERIC_WRITE` は `ERROR_ACCESS_DENIED` (E の EPERM 相当)、`/c/home/...` 側へ書けて posix 側から同一バイトを読取 —
  を ST/MT 両方 PASS。CAB-271 追加分: `test_pathreg.c` §1.5 (**CHECK 23 件**)・`test_defaults.c` (**CHECK 22 件・map 9 例**)。
- e2e クロスチェック: 16 fixture (`\\?\` 付き・UNC・相対・未登録・退役 alias 含む) で **C `pathreg_map` と JS `createMapper`
  が全件一致** (非対応は両方 null) + 逆写像一致 + 追加マウント一致 + 表件数一致 = **8**。
- **既定経路と明示設定経路の対比 (CAB-271)**: set_paths 未使用 → `C:\Users\webstudio\...` が `/c/home/...`。
  `set_paths({userProfile:"C:\Users\alpha", vfsHome:"/home/alpha", vfsInstall:"/fl-alpha"})` 後は alpha 表が保持され `C:\Users\alpha\Desktop\x.txt` → `/home/alpha/Desktop/x.txt`、webstudio は残余 `C:` 規則に落ちる。

## 3. レジストリ永続化接続

### 3.1 構成と契約 (詳細は `include/pathreg.h` コメント)

- **構成**: `wasm (shimx Reg* + pathreg) ⇄ RegBridge (js/regbridge.mjs) ⇄ store {load,save,delete} ⇄ IndexedDB` (IdbStore: DB
  `webstudio-vreg` / store `profiles` / key = profile)。vreg 資産は **import のみ**: `regfile.mjs`・`seed.mjs`・`store.mjs`・`vreg.mjs`。
- **C ↔ JS ワイヤ形式**: `.reg` テキスト v5.00 (UTF-8)。C: `shimx_reg_export_text` (要 `_free`) / `shimx_reg_import_text`。JS: vreg
  `regfile.mjs` の `parseToModel` / `serializeReg` (全型対応、往復は vreg REPORT §3 の 57/57 実績を継承)。
- **永続レコード** (vreg `Vreg.flush()` と同一・相互運用可): `{ schema:1, seedVersion, machineGuid, savedAt, hkcu }`。**HKCU のみ永続**
  (HKLM 等は seed から毎回再構成 = vreg と同一方針)。
- **flush タイミング (vreg REPORT §8-1 準拠)**: 変更 → 遅延 flush (既定 200ms) に加え、ポンプ yield 点で `onYield()`、
  `pagehide`/`visibilitychange` で `onPageHide()` を**明示的に**呼ぶ。e2e で「yield 無しの変更は次セッションに載らない
  (Atomics.wait 中は JS タイマが走らないため)」と「onYield/onPageHide で載る」を両方検証。

### 3.2 2 つのリンク構成 (自動判別: `_vreg_export_root` の有無)

| | (a) vreg_* フック export (本番推奨; module-a) | (b) フック非 export (module-b) |
|---|---|---|
| リンク | shimx src 全部 (reg.c は CAB-214 で vreg 拡張取込済み) + `vreg/src/probe.c`、`vreg_*` を EXPORTED に | shimx src のまま (`vreg_*` 非 export) |
| 変更検出・復元 | `vreg_set_notify` (addFunction 'vi') → dirty → 遅延 flush (`vreg_generation` で確認)、`vreg_clear_root(HKCU)` → 永続 model + `fillMissing(seed)` を import | flush 点で `pathreg_reg_hash` を前回保存値と比較、`shimx_reg_reset` は使わず import 後に内蔵既定で永続 model に無い値/キーを差分削除 (`_applyHkcuDeletions`) |
| seed 投入・検証 | `shimx_reg_import_text` 一括。e2e A (遅延 flush・onYield・onPageHide・**vreg Vreg 双方向相互運用**) | 同左。e2e B (往復・**built-in 既定値削除の永続**・hash 検出・直後 flush no-op) |

e2e 実測: 復元後の `Run counter`・`LastProject`・削除した `sDecimal` (内蔵既定) が**再起動後も正しく保持/欠落**、
`MachineGuid` はプロファイル内で安定。キー数 (§8-1): 永続レコード `hkcu` キー **12** / `bridge.stats()` **53・values 99** (全ハイブ) / `bridge.counts()` **25・values 99** (model)。

## 4. CAB-101 (実FL結線) での利用方法

1. **モジュール**: `scripts/build.sh module-a` の構成 (shimx src 全部 + vreg/src/probe.c + pathreg/src/*.c) で lift 済み FL とリンク。
   EXPORTED_FUNCTIONS は `include/pathreg.h` の一覧 + FL 本体が必要が分。`RegBridge.create({mod, store: new IdbStore(), seed, profile})`
   で boot 内に `_shimx_init` / `_pathreg_install` / seed 適用 / 復元 / flush (初回は強制) まで完了。
2. **FS 側**: 読取は E の `createEmscriptenFs(FS, vfs)` を `/fl` に mount。書込は `/c/home`(`/c/tmp`) を MEMFS+IDBFS または OPFS 由来の書込可
   FS で mount。写像先は `js/pathmap.mjs` で起動前に計算できる (nfo `generateDb()` 出力を Shared data 配下へ)。
3. **ランタイム**: pump の yield 点で `bridge.onYield()`、`pagehide`/`visibilitychange` で `bridge.onPageHide()`。Worker 終了前にも `close()`。
4. **設定 (CAB-271 で注意)**: `pathreg_set_paths()` (C) + `createMapper({paths})` (JS) を同一値で上書きする。set_paths 後は既定表の
   遅延ロードは起こらないため「set_paths → map」順で正しく動く (旧実装では逆だった)。

E (asset-vfs) 側は無変更で良い (`/fl` mount 点と vpath = tree 相対の規約を本側が既定表に採用)。書込可領域の
mount 実装 (IDBFS/OPFS) は CAB-104/CAB-101 の担当で、本チケットは「どの Win パスがどの FS パスになるか」の契約とハーネスを提供する。

## 5. 制限

1. **HKCU のみ永続** (HKLM 等はセッション内のみ) — vreg と同一方針。vreg seed の HKLM 値は毎起動再適用される。
2. **shimx reg.c 構成の削除永続は HKCU のみ** (`_applyHkcuDeletions`)。HKLM の built-in 既定削除は復元時に復活する (vreg 結線でも
   HKLM は clear しないため同条件)。キー削除は葉のみ。日本語等非 ASCII キー名の削除も動くが、mount 表の照合は ASCII 大小無視のみ。
3. **pathreg_map の入力は UTF-8 前提** (shimx `shimx_path_to_posix` と同じ)。W 版 API は shimx 内部で UTF-8 化してから mapper へ渡す。
4. hash 変更検出 (構成 b) は export 全文の O(レジストリ全体) — flush 点のみ呼ぶ設計なので実用上無視できる (誤「無変更」は FNV-1a 64bit 衝突時のみ)。
5. レコードの `hkcu` は「その時点の全 HKCU」を含む (vreg と同一)。seed version 更新時は `fillMissing` で不足分のみ補完。破損時マイグレーションは未実装 (schema:1 固定)。
6. **既定表の遅延ロードは 1 度だけ** (CAB-271)。`pathreg_clear_mounts()` 後も既定表は復活しない。必要なら `pathreg_paths_init()` + `pathreg_set_paths()`。
7. 実 FL バイナリを通した検証は未了 (本 ticket はインタフェース接続。実 FL 結線は CAB-101)。

## 6. ユーザ依頼事項

なし。

## 7. 次タスク提案 (下流チケット案)

| # | チケット | 要点 |
|---|---|---|
| 1 | CAB-101 (実FL結線) | §4 の手順で lift 済み FL + E + RegBridge を 1 プロセスに結線。`SHIMX_TRACE` で Reg*/CreateFile の実呼出を観測し、既定マウント表と seed 値のずれを確定する |
| 3 | E 側書込領域 | `/c/home`, `/c/tmp` の IDBFS/OPFS mount 実装と、`onPageHide` での IDBFS sync (`FS.syncfs`) 接続。flush 契約は §3.1 を流用可 |
| 4・5 | ~~vreg 取込の恒久化~~ / ~~CAB-213 (パス実キー確定)~~ | 完了 (CAB-214: shimx reg.c が正本。構成 (b) は代替経路として存続 / webstudio 統一・予備 `user` mount 退役) |

## 8. 数え方の定義・検収記録 (規則 36・37・41)

### 8-1. 数え方 (定義 / 実測)

| 数値 | 定義 | 実測 |
|---|---|---|
| fixture N | `test/e2e.mjs` の `fixtures[]` 要素数 | **16** |
| 正規化 N 例 | `test_pathreg.c` `test_normalize()` の `cases[]` 要素数 | **18** |
| 写像 N 例 | `test_map()` の `cases[]` 要素数 (fallback 1 含む) / `test_defaults.c` `main()` (fallback 3 含む) | **8** / **9** |
| 既定マウント表 N 本 / CHECK N 件 | C `pathreg_mount_count()` = JS `defaultMounts().length` / ファイル本文の `CHECK(` 出現数 (同一行 2 個は 2)。CAB-271 の §1.5 は **23** | **8** / `test_pathreg.c` **90**・`test_defaults.c` **22** |
| 行数 | `wc -l` / README・REPORT・`accept_recount.mjs` を除く **12 ファイル**。C=`include/`+`src/`, JS=`js/`, テスト=`test/`(`test_common.h` 除く), スクリプト=`scripts/{build,e2e}.sh` | C **474** / JS **461** / テスト **654** / スクリプト **120** / 計 **1,709** |
| module サイズ | `ls -l build/module_{a,b}.mjs` (SINGLE_FILE, wasm 埋込) | a **204,729 B** / b **190,698 B** |
| e2e キー数 / group N | A4=`Object.keys(rec.hkcu).length`(永続レコード) / B=`bridge.stats()`(全ハイブ) / `bridge.counts()`(model) / `test/e2e.mjs` の `ok()` 呼出し箇所 | **12** / **53 (values 99)** / **25 (values 99)** / **6** (A1・A2・A3・A4・B・C) |
| seed エントリ / ablate N 件 | `vreg resolveSeed(registered)` の model 値数 + `catalogSkipped` / `scripts/build.sh nc` が build・実行する ablation 数 | **236** (起動時書込 **81** / catalog のみ **155**) / **2** (nc1: 修正のみ取消 / nc2: 既定ロード無効化) |

独立再計算 (別アルゴリズム・規則 37): `bash tools/shimx/pathreg/scripts/build.sh all` 後に `node tools/shimx/pathreg/scripts/accept_recount.mjs`
→ exit 0。3 経路で数え直す: ①ソースのテキスト解析 (関数名で囲んだ `cases[]`・`CHECK(`) ②`defaultMounts()` と build 済み module の生 export ③**C 単体 binary の再実行**。全項目 MATCH → `accept_recount: MATCH (mounts 8 / fixtures 16 / CAB-271 PASS / LOC 1709)`。
ネガティブコントロール (規則 41): ① 従来部 — C 側のみ追加マウント (`E:\Ablated`) → `C=/libs/ablated/x/y.dll` / `JS=null` で**不一致を検出**
(対照は 5/5 一致 → 空振りでない) ② CAB-271 追加 — §8-3 の 2 ablate が FAIL することを実測。

### 8-2. 検収記録 (2026-10-11・CAB-168 検収 agent)

- 検証起点 commit **0669f26** (+ follow-up **baca426** 後の HEAD)。`bash tools/shimx/pathreg/scripts/e2e.sh` → **exit 0 / 8 秒**
  (`E2E PASS: 6 groups`)。load average 開始 4.90/3.96/3.72 → 終了 4.92/3.99/3.74。
- 誤記修正 (本 commit): 15→**16** fixture / 表件数 14→**8** / 行数・module サイズ。原因は `user2Profile` 退役に REPORT の数値が
  追随していなかったため。コミットは `feat(shimx): path mapping + registry persistence interface (CAB-168)`。

### 8-3. CAB-271: 既定ロード上書きバグの根本修正 (2026-10-11・実装 agent)

**原因 (実測)**: `pathreg_map()` / `pathreg_add_mount()` / `pathreg_remove_mount()` / `pathreg_mount_count()` の頭の
`pr_ensure_defaults()` は `g_defaults_loaded` だけを見ており、`pathreg_set_paths()` がこのフラグを**立てていなかった**。
`g_defaults_loaded == 0` のとき既定 `pathreg_paths_init()` + `pathreg_set_paths()` を実行して既定 (`C:\Users\webstudio`) 表を
作り直すため、set_paths の**後**で初回照合が走ると呼出側の表が消える (CAB-101 §5.1 と同一の観測)。
**修正** (`src/pathmap.c` +17 行 / `include/pathreg.h` +5 行): `g_defaults_blocked` (新設 static) を `pathreg_set_paths()` が 1 にし、
`pr_ensure_defaults()` は `if (g_defaults_loaded || g_defaults_blocked) return;` とする。既定表は `pathreg_set_paths()` を**一度も
呼ばない**経路でのみ遅延ロードされる (変更全文は **`REPORT_CAB-271.md` §2**)。

**検証 (実測・詳細は `REPORT_CAB-271.md` §4〜§6)**: ① `set_paths` → `map` で上書きされない (C 単体 ST/MT **PASS** —
`test_pathreg.c` §1.5 CHECK 23 件。alpha 表 6 本 / webstudio 残存 0 / `map`・`unmap`・`shimx_path_to_posix` が alpha 参照)
② 既定経路は従来どおり既定表がロードされる (**PASS** — `test_defaults.c` CHECK 22 件・map 9 例・ST/MT
`PATHREG DEFAULTS ALL PASS`) ③ pathreg e2e **6 groups PASS** (`E2E PASS: 6 groups`・n=7 全 exit 0) ④ glue e2e (CAB-101)
無劣化 (**PASS** — exit 0。C 単体 66/66・TS 単体 49・SIGKILL 跨ぎ mismatches 0・trace `C:\Users\user` 0・stage 10)
⑤ 既存 fixture **16 件不変** (`fixtures[]` 本 ticket で 0 行変更・C↔JS 全 16 件一致) ⑥ 既定表・module 構成の非変更 (**PASS**)。

**所要 (規則 38・実測)**: `scripts/e2e.sh` = **12.9〜15.4 秒** (n=7: 13.89 / 15.40 / 14.30 / 13.10 / 13.13 / 13.26 / 12.95・全 exit 0)。
旧 8 秒から増えたのは `test_defaults` 2 build・ネガコン 2 build の追加分。`glue/glue.sh` = **4.0〜5.7 秒** (n=2)。load average (1/5/15 分)
は開始 4.12/3.39/3.20 → 各 run 後 4.02〜4.46 / 3.39〜3.54 / 3.20〜3.27 (`/proc/loadavg`・並列数 1)。

**ネガティブコントロール (規則 41・`build.sh nc` → exit 0)**: 修正を 1 つずつ外した ablate 2 件を build し **FAIL を実測** —
nc1 (`g_defaults_blocked = 1` を外す = 修正のみ取消) → **FAIL** `test_pathreg.c:70: nAlpha == 6` /
nc2 (`pr_ensure_defaults()` の既定ロードを無効化) → **FAIL** `test_defaults.c:14: pathreg_mount_count() == 8`。
→ ①は nc1 で、②は nc2 で空振りでないことを確認した。

**未解決・起票先 (規則 42)**: glue (`tools/startup/glue/src/glue.c` L178) の回避 `pathreg_mount_count()` 先呼びが冗長になった (削除は glue
側変更が必要で本 ticket の書込範囲外) → (c) 親 **CAB-168**・**CAB-101** にコメント済。`pathreg_clear_mounts()` 後の既定表再ロードは
起こらない (1 度だけロードする設計) → (c) 親 **CAB-168** にコメント、契約を明記済。

**コミット・Linear**: `fix(shimx): pathreg explicit paths not overridden by defaults` (変更は `tools/shimx/pathreg/` のみ・20 MiB 超 blob
0 個・最大 `module_a.mjs` 204,729 B)。CAB-271 を起票 (parent=**CAB-168** / project=**signature-studio** / assignee=me / milestone=**ブラウザ初回起動** 654c816c-07d2-401b-bd9b-8a52cf056b0a)。Backlog → In Progress → **In Review**。CAB-168・CAB-101 にコメント。
