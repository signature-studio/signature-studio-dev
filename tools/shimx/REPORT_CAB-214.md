# REPORT (CAB-214) — shimx vreg reg.c 本体取込 + username 統一 + 後始末 3 件

> 正本: `tools/shimx/REPORT.md` §11・§12 から分割移動した付録 (内容は無変更、§ 番号 11.x / 12.x は維持)。親: `tools/shimx/REPORT.md`。
> 分割理由: `docs/DOC_MAP.md` §1 の 250 行上限 (#584)。

## 11. vreg reg.c 本体取込 + username 統一 (CAB-214, SHX-T10)

**結論**: `tools/startup/vreg/src/reg.c` (828 行, CAB-94/a5b44fe) の拡張全てを `src/reg.c` に取込した
(686→829 行, 公開シンボル **39→50**, 欠落 0 — 旧 39 シンボルは全て継承)。以後の改良は shimx 側が正本。
vreg 側との二重管理は解消 (vreg `build.sh symcheck`: shimx 50 シンボルを vreg reg.c が全包含 / **追加 0** =
両者はシンボル集合として同一)。username も CAB-213 の正規表記 `C:\Users\webstudio` に統一した。

### 11.1 取込差分 (vreg REPORT §2 の 4 項目 + 追加 6 API → 全て実装)

| # | 取込内容 | 実装 | shimx での改善点 |
|---|---|---|---|
| 1 | 変更世代 `vreg_generation()` + 通知 `vreg_set_notify(cb)` (set/delete/create で世代+1, **ロック解放後に呼出スレッドで同期通知**) | `reg_unlock()` / `touched()` (全 22 unlock site を経由) | 永続化トリガ (vreg JS の dirty→遅延 flush) が shimx 単体で利用可 |
| 2 | `RegEnum*` の `ERROR_MORE_DATA` で必要長を返す | `put_name()`: `*cch = n` を設定して返す | Delphi TRegistry 流の 2 段呼出 (長さ問合せ→再取得) が通る |
| 3 | import 拡張: UTF-8 BOM / `[-HKEY_..]` (サブツリー削除) / `"v"=-` / `@=-` | `shimx_reg_import_text()` | `.reg` 往復が vreg seed (236 エントリ) と同一経路に |
| 4 | `vreg_export_root(i)` / `vreg_clear_root(i)` / `vreg_clear_all()` | `export_key`/`clear_root_locked` を共用 (`shimx_reg_reset` も `clear_root_locked` に統合) | ルート単位 export/clear が shimx 公開面に |
| 5 | 追加 6 API: `RegGetValueA` `RegEnumKeyW` `RegDeleteTreeW` `RegSetKeyValueW` `RegDeleteKeyValueW` `RegQueryInfoKeyA` | `src/reg.c` + `shimx.h` 宣言 | **`proctable.c` にも自動登録** (advapi32, 532→538 エントリ) — vreg では未登録だった (vreg REPORT §7「必要になれば proctable 生成の対象に追加」を本取込で解消) |
| 6 | ヘルパ整理: `free_vals` / `mark_deleted` / `unlink_key` / `type_flags_ok` | vreg 版を verbatim 取用 | 重複コード削減 (`shimx_reg_reset` と `vreg_clear_*` の共通化) |

**exports.txt 差分 (+11)**: `RegDeleteKeyValueW` `RegDeleteTreeW` `RegEnumKeyW` `RegGetValueA` `RegQueryInfoKeyA` `RegSetKeyValueW` `vreg_clear_all` `vreg_clear_root` `vreg_export_root` `vreg_generation` `vreg_set_notify`。
運用フックは `shimx_*` 53 + `vreg_*` 5 = **58 本** (`gen_inventory.py` と `gen_proctable.py` に `vreg_` 接頭辞分類を追加 — proctable の GetProcAddress 組込み表には載せない。名前は vreg JS 側 `EXPORTED_FUNCTIONS` (`_vreg_generation` 等) との互換のため **`vreg_` 接頭辞を維持**)。

### 11.2 username 統一 (`C:\Users\user` → `C:\Users\webstudio`)

CAB-213 §3 の正規表記へ shimx 内蔵値を統一 (pathreg の alias mount 吸収は不要になる方向。**実効挙動は表記変更のみ**)。

| ファイル | 箇所 | 変更 |
|---|---|---|
| `src/env.c` | env 既定表: `USERPROFILE` `HOMEPATH` `APPDATA` `LOCALAPPDATA` `TEMP` `TMP` (6 パス) + `USERNAME` | `...\Users\user...` → `...\Users\webstudio...` / `USERNAME=user` → `webstudio` |
| `src/file.c` | `GetTempPathW/A` の既定 Temp (2 箇所) | 同上 |
| `src/shell.c` | `csidl_path()` 13 箇所 + KnownFolder GUID 表 6 箇所 (SHGetFolderPathW/SHGetKnownFolderPath/SHGetSpecialFolderPathW が返すパス) | 同上 (`C:\Users\Public` 系は不変) |
| `test/test_sys.c` | `PathUnExpandEnvStringsW` 入力 / `GetTempPathW` 期待値 (2 箇所) | 期待値を新正規表記に更新 |
| `test/test_ole_shell.c` | `SHGetFolderPathW`/`SHGetKnownFolderPath`/`SHGetSpecialFolderLocation` 期待値 (3 箇所) | 同上 |

**触っていないもの**: `tools/shimx/pathreg/` 全体 (V18 検収が読み中のため読取のみ) / `src/reg.c` の seed 内 `RegisteredOwner="user"` (Windows の登録所有者名でユーザ profile 路線でない。vreg seed 236 エントリにも含まれず影響 0)。

### 11.3 vreg 側の薄ラッパ化 / 退役方針 (別作業用 — 本チケットでは vreg 無改変) — **→ 実施済み (§12.1)**

vreg (`tools/startup/vreg/`) は **1 行も変更していない** (vreg.sh 再実行で data/seed.json 等バイト不変を実測済)。
現状の vreg `build.sh` は shimx `src/*.c` から `reg.c` を除外して自前 `src/reg.c` をリンクしているが、
取込後は**両者のシンボル集合が完全一致**したため、下記の退役が可能 (vreg 担当 or CAB-11 後続で実施):

1. `vreg/build.sh` の `SRCS` 除外工作 (12 行目の `[ reg.c ] || ...`) を削除 — shimx `reg.c` をそのまま使う
2. `VSRC` から `src/reg.c` を外す (`probe.c` はテスト/e2e 専用ヘルパとして継続)
3. `vreg/src/reg.c` を削除 (参照実装が shimx に一本化)。JS 側 (`js/vreg.mjs` 等) は `_vreg_generation` 等
   の名前が shimx 側でも不変のため **無変更で動作する**
4. 退役後も `build.sh symcheck` は「自前 vs shimx」の退化検査として残せる (追加 0 を維持)

### 11.4 pathreg 予備 profile (`user2Profile`) の退役手順 (別タスク用) — **→ 実施済み (§12.2)**

username 統一により shimx は `C:\Users\user` を**発行しなくなった**ため、pathreg 既定表の
`user2Profile = "C:\Users\user"` (pathmap.c 164 行, 予備 mount 4 本) は冗長。退役は pathreg 担当作業:

1. `src/pathmap.c` の `pathreg_paths_init` から `user2Profile` 設定と 197-198 行の条件追加 mount を削除
2. `test/e2e.mjs` の B グループ等、`C:\Users\user` 表記を使っている fixture があれば `webstudio` 表記へ
3. **`pathreg_unmap` の同長 tie-break (先勝ち)** は webstudio のみの mount になっても結果不変 (既に正規が先頭)
4. 削除後の検収: `bash tools/shimx/pathreg/scripts/e2e.sh` (6 groups) + `verify_consistency.py` の
   username 整合チェック (「+予備 user」の文言も更新)

### 11.5 検証実績 (全て 2026-10-10 実測)

| 検証 | 結果 |
|---|---|
| `bash tools/shimx/test.sh` | **exit 0**: MT PASS / ST PASS / fail-fast 8 モード / M4 互換 MT・ST (53/53) / 署名突合 3 IR (m11, m11_3, ott) mismatch **0** / OTT t1 SHA **b5a91b9b2ee8da1e 不変** (512 行) / 未実装 0 (担当範囲 100.0%) |
| シンボル突合 (llvm-nm) | 旧 shimx reg.c 39 → 新 50 (**+11**, 欠落 0)。`vreg build.sh symcheck` = shimx 50 シンボルを vreg reg.c が全包含 (**追加 0** = 同一集合) |
| `bash tools/startup/vreg/vreg.sh` | **ALL OK** (6/6 step: seed 再生成バイト不変 / C 単体 / shimx 結合 MT+ST+M4 / symcheck / wasm / node 22/22 / Chrome 実 IndexedDB PASS)。vreg dir の git 差分 **0** |
| `bash tools/startup/keyfix/keyfix_e2e.sh` | **ALL PASS** (entries=236 / apply=81 / key確定=113 / key=null=3 不変, `verify_consistency.py` 6 項目 PASS — username 整合含む) |
| `bash tools/shimx/pathreg/scripts/e2e.sh` | **ALL PASS** (C 単体 ST/MT + JS 4/4 + e2e 6 groups。module-b = **shimx reg.c のまま**の構成で新 reg.c を実行して無劣化) |
| winstubs/gui リンク共存 | `coexist_gui.sh`: 重複シンボル = **既知記録 1 件のみ** (`WTSRegisterSessionNotification`, shimx weak × gui 強定義の既存分)。winstubs 由来の重複 **0**。`verify_sig_ir.sh`: mismatch 0 + 陰性対照 1 検出。winstubs wrap 層経由の shimx 単体テスト ST/MT **ALL PASS** |

### 11.6 winstubs への影響 (後続タスク) — **→ 実施済み (§12.3)**

username 統一により、winstubs (CAB-96) が wrap していた **5 API が shimx 単体で期待値一致**になった
(`winstubs.sh` step 4 の「差分実装は不要」検査が FAIL 5 件: `SHGetFolderPathW` `SHGetSpecialFolderPathW`
`SHGetKnownFolderPath` `GetTempPathW` `ExpandEnvironmentStringsW` — shimx 単体ですでに全行 MATCH)。
これは wrap 層の退役機会であり、winstubs 担当が `wrap_list.txt` / api_matrix の impl 分類を更新すれば解消する
(winstubs は本チケットでは無改変。`data/diff_table.tsv` は検収スクリプトが毎回再生成する実測表ゆえ触らず)。

### 11.7 CAB-101 (実 FL 結線) への影響

1. **正の影響**: engine が env/SHGetFolderPath で受ける username 表記が seed (vreg 236 エントリ) と
   完全一致 (`webstudio`) になった → CAB-213 で吸収していた「user 表記と webstudio 表記の併存」が解消され、
   `SHIMX_TRACE` のパス観測が seed 期待値と直接突合できる。pathreg の alias mount 経由の解釈が不要に。
2. **レジストリ**: `Reg*` は shimx 正本 1 本に。CAB-101 の open ログ観測では vreg と shimx の差違を気にする
   必要がなくなり、`vreg_generation()`/`vreg_set_notify()` で Reg 呼出トレース拡張が shimx 直結で可能
   (vreg REPORT §10 の提案がそのまま shimx で実施可)。
3. **追加 6 API が GetProcAddress 組込み表に載った** (advapi32 532→538) — lift 側が動的解決しても解決する。

## 12. CAB-214 follow-up: 後始末 3 件 (§11.3 / §11.4 / §11.6) — 全て実施

**結論**: 3 件とも REPORT §11 の手順どおり実施し、回帰は全て exit 0 (§12.4)。shimx 本体 (`src/*.c`) は**コメント 1 箇所以外無変更** (挙動不変)。
退役の本質は「同名シンボル同時リンク不可」の正式解消 (vreg) と「username 差の吸収層」の撤去 (pathreg alias mount / winstubs wrap) で、いずれも §11.2 の統一で不要になったもの。

### 12.1 vreg 薄ラッパ化 (§11.3 の 4 手順)

| 手順 | 実施 |
|---|---|
| 1. `SRCS` 除外工作の削除 | `vreg/build.sh`: `SRCS=("$SHIMX"/src/*.c)` (reg.c 含む) |
| 2. `VSRC` から reg.c を外す | `VSRC=("$HERE/src/probe.c")` (probe.c はテスト/e2e 専用ヘルパとして継続) |
| 3. `vreg/src/reg.c` 削除 | `git rm` (828 行)。JS (`js/*.mjs`) は**無変更**で動作 (`vreg_generation` 等の名前不変)。`src/vreg.h` は probe 宣言のみに縮小 (運用フック/追加 6 API の宣言は shimx.h に既存) |
| 4. `symcheck` の継続 | 手順どおり「自前 vs shimx」比較は自前が無くなるため成立しない → **判断**: 「vreg が要求する公開面 (shimx.h 宣言の `Reg[A-Z]*` 全て + module の EXPORTED `vreg_*`/`shimx_reg_*`) を shimx reg.c が定義している」検査に差し替え (実測: 要求 38 シンボル / reg.c 公開 50 / 不足 0) |

**手順書に無かった波及 (判断)**: `pathreg/scripts/build.sh module-a` が `vreg/src/reg.c` をリンクしていたため同時に修正 — shimx 全 src + `vreg/src/probe.c` + pathreg に変更
(module-a = `vreg_*` フック export + probe 同梱の本番構成 / module-b = フック非 export の代替構成、として両方存続。regbridge の自動判別 (`_vreg_export_root` の有無) は不変)。

### 12.2 pathreg 予備 profile `user2Profile` 退役 (§11.4 の 4 手順)

| 手順 | 実施 |
|---|---|
| 1. `pathmap.c` | `pathreg_paths_init` の `user2Profile` 設定 + `pathreg_set_paths` の条件追加 mount を削除。構造体 `PathRegPaths.user2Profile` (pathreg.h) と JS ミラー (`js/pathmap.mjs` DEFAULT_PATHS + 2 profile ループ) も削除。既定表 **14→8 本** (install 1 + webstudio×6 + `C:` 1) |
| 2. fixture の webstudio 化 | `test_pathreg.c` / `pathmap.test.mjs` / `e2e.mjs` の `C:\Users\user` → `webstudio`。**追加 (判断)**: 表件数 8 の厳密化 (旧 `>= 9`)、退役 alias `C:\Users\user\...` が残余 `C:` 規則 (`/c/Users/user/...`) に落ちる陰性確認を C / JS / e2e クロスチェック (fixture 15→16) に追加 |
| 3. `pathreg_unmap` tie-break | コード無変更 (webstudio のみになり結果不変。e2e C グループの逆写像一致で確認) |
| 4. 検収 + `verify_consistency.py` | `keyfix/verify_consistency.py`: 「+予備 user」文言と `user2Profile = "...user"` 必須判定を撤去し、「webstudio のみ + `user2Profile` 不在 (C / JS 各 1 項目)」に更新 (6→7 項目)。keyfix は shimx 取込完了を待って予備退役する計画 (keyfix REPORT §4-4) だったため整合 |

### 12.3 winstubs wrap 5 API 退役 (§11.6)

| API | 実施 |
|---|---|
| `SHGetFolderPathW` `SHGetSpecialFolderPathW` `SHGetKnownFolderPath` `GetTempPathW` | `wrap_list.txt` から削除 (16→12 本)。`ws_sys.c` の `fix_user`/`is_default_user_prefix`/`__wrap_*` 4 本と `ws_internal.h` の `__real_*` 4 宣言を削除。`api_matrix.tsv` impl `wrap`→`shimx`。CREATE フラグ (`CSIDL_FLAG_CREATE`/`KF_FLAG_CREATE`/Temp 作成) は shimx 側 (`shell.c` `mk_win_dir` / `file.c` `mkdirs`) が webstudio を作るため wrap 不要 (boot e2e G07 `created=1 writable=1` 維持) |
| `ExpandEnvironmentStringsW` | wrap でなく `shimx+seed` 分類だった (§11.6 の 5 件目)。impl→`shimx` (既定環境表が webstudio で一致)。`winstubs_init` の env 上書きは `GetEnvironmentVariableW` (`LANG=en`) のため残置 |

**判断**: `WsConfig.user` は存続 (ABI 維持)。ただし既定以外にすると env (`USERNAME`/`USERPROFILE` 等) のみ追従し、`SHGetFolderPathW`/`GetTempPathW` は shimx 固定の webstudio になる (従来は wrap の `fix_user` が追従)。
使用箇所は現状ゼロ (テスト・下流とも既定値のみ) のため許容し、`ws_core.c` にコメントで明記。
再計測 (`winstubs.sh` step 4): impl 内訳 `shimx` 23→**28** / `shimx+seed` 2→**1** / `wrap` 14→**10**、baseline 差分 MATCH 60→**72** / DIFF 40→**28** / MISSING 31 (不変)。「差分実装は不要」検査 FAIL 5→**0**、checks=1133 ALL PASS。

### 12.4 回帰 (全て 2026-10-10 実測、exit 0)

| 検証 | 結果 |
|---|---|
| `bash tools/shimx/test.sh` | **exit 0**: MT/ST PASS / fail-fast 8 / M4 53/53 / 署名突合 3 IR mismatch **0** / OTT t1 SHA **b5a91b9b2ee8da1e 不変** / 未実装 0 (担当 100.0%) |
| `bash tools/startup/vreg/vreg.sh` | **ALL OK** (6/6 step: seed 再生成バイト不変 / C 単体 / shimx 結合 ST+MT+M4 / symcheck / wasm / node 22/22 / Chrome 実 IndexedDB) |
| `bash tools/startup/keyfix/keyfix_e2e.sh` | **ALL OK** (entries=236 / apply=81 / key確定=113 / key=null=3 不変、`verify_consistency.py` **7 項目** ALL PASS) |
| `bash tools/shimx/pathreg/scripts/e2e.sh` | **ALL PASS** (C 単体 ST/MT + JS 4/4 + e2e 6 groups, fixture 16) |
| `bash tools/startup/winstubs/winstubs.sh` | **exit 0** (8/8 step: 131/131 行一致 ST/MT / リンク 67/67 / boot 21/21 / IR 署名 mismatch 0 + 陰性対照 1 / shimx 回帰 ST/MT PASS / **gui 共存**: 重複は既知記録 `WTSRegisterSessionNotification` 1 件のみ・winstubs 由来 0・GetProcAddress 不整合 0・gui 強定義 6/8) |
| `bash tools/startup/pump/pump.sh` (波及確認; winstubs src を別 work で再ビルド) | **exit 0** (全 PASS) |


