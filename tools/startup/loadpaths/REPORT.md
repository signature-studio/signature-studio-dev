# REPORT — ST-T14 (#39): 言語ファイル (.moe 暗号化)/スキン/Artwork/Help のロード経路確認と VFS 配置

検証起点: 親 `main` = `bfccd23`、検証対象コミット = `14cb47e` (§5)。素材 = `fl-win64` (FL Studio 26.1.7.5653、`FLEngine_x64.dll`)。
既知類型 (`docs/DEFECTS.md`) との関係: **該当なし** (lift/IR pass を扱わない。FLEngine の静的解析のみ)。

## 0. 結論

1. **非 en の言語ファイル (.moe) は既定の起動では読まれない。** `CreateFruityInstance` (0x1375990) の直接 call 先 0x13754b0 → 言語初期化 0x9deaa0 が
   言語コードを `HKCU\Software\Image-Line\Shared\Language\Program Language` から読み、**値が無ければ既定 `en`**。`en.moe` は存在しないので (探索は走るが失敗し) 組込み英語のまま
   (読込に成功するファイルは無い)。`ja` 等を選ぶ (seed する) と、そのときだけ選択言語 1 ファイルを**全量**読む。→ .moe は起動必須ではない (静的根拠。実行トレースは未取得、§6)。
2. **.moe の形式を確定し、復号を再現した。** 暗号化 GNU gettext `.mo`。`u32 N=256 | RSA(e=3, 2048bit) 暗号文 256 byte | 本体`。RSA 復号で得る 16 byte 鍵で本体を
   8 byte ブロックの XOR ストリーム復号する。FL 同梱 7 言語すべてが復号でき、標準 `.mo` (magic `0x950412de`・UTF-8) として読める (§2)。
   **wasm 側に復号の実装は要らない**: リフト済みエンジンが自分で復号する。VFS は**元の暗号化バイトをそのまま**返せばよい。
3. **起動時に読むスキン/Artwork/Help を関数単位で特定した** (§3)。起動経路にあるもの = スプラッシュ `Title.png`・既定テーマ画像 2 枚・壁紙 `Default.txt`・フォント表・
   `Help/HelpPlugins.scr` + `HelpAliases.scr` (LoadSettings の 'Initialize the help file' 段)・`Data/System/Empty.flp`。ヘルプ本体 HTML・About/ライセンス文・
   テーマ/壁紙の選択肢・サブ画像は操作時のみ。
4. **VFS 配置は既存写像のまま成立する**: 対象 223 ファイルの Win パス全件が pathreg で `/fl/<相対>` (RO) に写る (不一致 0)。ユーザ側 `Languages\` `Skins\` `Themes\` は
   永続領域 `/c/home/**` が先に探される (§4)。既存の静的推定 tier (`tools/assets/bootset`) との差分は 6 点 (§4 表)。
5. **全受入条件の達成ではない**: 実 boot トレースでの動的確定、`lang-svg` の参照元、非 en 実読込の e2e は未達 (§6)。PR は `Refs #39`。

## 1. 成果物

| パス | 内容 |
|---|---|
| `mk_manifest.py` | `block_manifest.json` が無い環境用。NSIS(BI) のデータ領域を先頭から歩いて `blockNNNNN` ↔ `payload_off` を再構成 (extracted と先頭 80 + 乱数 120 block のバイト一致を検査)。既存 `tools/assets/win_paths/recover_paths.py` を無改変で動かす入力になる |
| `moe.py` | .moe の復号 + `.mo` 検査 (stdlib のみ)。法 n は**実行時に DLL から抽出** (repo に保存しない) |
| `verify_refs.py` | `loadpaths.json` の根拠 (関数先頭・文字列参照・call 辺) を DLL から機械照合 (stdlib のみ。逆アセンブラ不要) |
| `loadpaths.json` | 配置 group の宣言 (glob・phase・推奨 tier・読込単位・読み手関数 VA・`claims` / `calls`) |
| `check.py` + `mapcheck.mjs` | group を実ファイル一覧に当てて件数・サイズ・Win→VFS 写像 (pathreg JS ミラーを import) を実測 |
| `crosscheck.py` | 別算法 (RSA の乗算展開 / 64 bit ワード演算の XOR / 標準 `gettext`) による検算 + ネガコン |
| `e2e.sh` | 上記 1 コマンド検証 |

## 2. 言語ファイル (.moe)

### 2.1 ロード経路 (FLEngine_x64.dll の VA。`verify_refs.py` が関数先頭・参照文字列・call 辺を照合済み)

```
CreateFruityInstance 0x1375990 ── call ─→ 0x13754b0 ── call ─→ 言語初期化 0x9deaa0
  0x9deaa0: 0x9dece0(…,0)=Program Language(既定 空) が空なら 0x9df190 で OS UI 言語を取り、'zh' のときだけ 0x9df010 で保存
            0x9dece0(…,1)=Program Language(既定 'en') → 0x9de620(言語コード → 候補名) → 見つかれば 0x8dbf90 で適用
            見つからなければ 0x9de810 (フォールバック) → 0x8de4f0
  0x9de620: xx_YY → xx の縮約を繰り返し 0x9de400 で探索。最後に LC_MESSAGES\Default 系を試す
  0x9de400: "<name>.moe" を host の検索パス服務 (メッセージ id 0x40f = Languages 区分) に問い合わせ、無く、かつ内部フラグ [0x15e26e0] が真なら ".mo" も
  0x8daeb0 → 0x8e0110 → 0x8e1500: TMoFile 相当。拡張子 .moe → 0x8e13f0 (FileStream 全体を復号して MemoryStream) 、その他は MapViewOfFile
                                  復号後 magic 0x950412de/0xde120495 を検査。0x8daeb0 は Content-Type に charset=UTF-8 が無いと翻訳を無効化 (診断メッセージ)
検索パス登録 0x9db5b0: 区分 0x40f に `Languages\` (level 0 = ユーザ) 、`Languages\` (level 2) 、`System\Languages\` (level 1 = インストール先) を登録
```

- 検索順の意味 (level 0→1) は登録順・命名からの推定。`0x9de400` が呼ぶ `[self+0xa8]->vtbl+0x30` の実体は未追跡 (§6)。
- 言語の選択は**レジストリの `Program Language` のみ**。現行 seed `tools/startup/vreg/data/seed.json` では `Shared\Language` の `Program language` は catalog のみ (value `""`・`apply:false`) で起動時に書かれない → エンジン既定 `en`。OS 言語の自動採用は `zh` だけ
  (その場合は `Program language` を書き戻す)。shimx は UI 言語 API を `en-US` 固定で実装済み (`tools/shimx/REPORT.md` R3、`GetUserPreferredUILanguages` は inventory 上 locale.c で機能実装。返値の実測は未実施 → §6)。

### 2.2 形式と復号 (逆アセンブル 0x8e13f0 / 0x8d85d0 / 0x8d5670 / 0x8d8510 から確定)

| 段 | 内容 |
|---|---|
| ヘッダ | `u32le N` (= 256) の後ろに N byte。全 7 ファイルで 260 byte が同一 (distinct = 1) → **鍵は全言語共通** |
| 鍵導出 | `m = c³ mod n` (c = 暗号文 big-endian 整数、n = DLL 内の 256 byte 定数、2048 bit)。`m` の前ゼロを除いた ASCII 16 進 32 字 → HexToBin → 16 byte |
| 本体 | 8 byte ブロック i = 0.. について `out[i] = in[i] ^ K64[i & 1]`、直後に `K8[i & 15] ^= (i & 0xff)`。8 byte 未満の末尾は無変換 |
| 復号後 | 標準 GNU `.mo`。リトルエンディアン magic `0x950412de`・POEditor 生成・`Content-Type: charset=UTF-8` |

n は 0x8e1000 の関数が `mov byte/word/dword [rax], imm` の列で組み立てる (実行時構築)。`moe.py` は機械語パターンで関数を 1 件特定し、命令を読んで 256 byte を再構成する。
**n・鍵・復号結果は保存・出力しない** (FL 由来物。`docs/LEGAL.md` の方針)。

### 2.3 実測 (7 ファイル。`moe.py` 出力。entries = .mo の文字列数、非 ASCII = 非 ASCII を含む訳文数)

| 言語 | 暗号化 byte | 復号後 byte | entries | 非 ASCII 訳文 | Plural-Forms |
|---|---:|---:|---:|---:|---|
| de | 901087 | 900827 | 14568 | 3435 | nplurals=2; plural=(n != 1) |
| es | 924258 | 923998 | 14568 | 4084 | nplurals=2; plural=(n != 1) |
| fr | 766743 | 766483 | 12370 | 4703 | nplurals=2; plural=(n > 1) |
| ja | 941838 | 941578 | 14568 | 5752 | nplurals=1; plural=0 |
| ko | 918413 | 918153 | 14568 | 11784 | nplurals=1; plural=0 |
| vi | 981698 | 981438 | 14568 | 13234 | nplurals=1; plural=0 |
| zh (`Language: zh-Hans`) | 848087 | 847827 | 14568 | 14015 | nplurals=1; plural=0 |

- 全 7 件: 暗号化 − 復号後 = 260 byte (= 4 + 256)、不正 UTF-8 訳文 0、`charset=UTF-8` あり。合計 6282124 byte (`check.py`、`lang-moe` group)。
- 構造の独立裏付け: `fr` を除く 6 言語の**暗号文**の共通先頭は 116832–116840 byte。最小値は 260 + 116572 (= `.mo` 先頭 28 byte + 原文記述子表 8 × 14568) に一致する
  (同一平文 → 同一暗号文のストリーム暗号の性質。`fr` は entries が異なり 268 byte で分岐)。
- 言語名は ja/ko/zh… の 2 文字 (zh のみ `Language` ヘッダは `zh-Hans`)。ファイル名は `<code>.moe` (`en.moe` は無い。`en.svg` のみ)。

### 2.4 VFS への含意

- 読込は**ファイル全量** (`FileStream` で `Size - Position` を 1 回読む)。Range 部分取得の利点は無い。0.77–0.98 MB なので `tools/assets` の pack では 1 MiB chunk 未満の専用 chunk に載る。
- 既定 `en` では不要 (ただし `en.moe` の探索は走るので、`Languages\en.moe` / `System\Languages\en.moe` は ENOENT を即返すこと)。非 en を選ぶ操作 (seed または設定 UI) の時点で選択言語の 1 ファイルだけ取得すればよい → 推奨 tier は T2 (遅延)。既存推定は T1。
- `*.svg` (言語選択 UI の国旗と推定。8 ファイル 4025 byte) の参照元は未特定。小さいので T1 のままでよい。

## 3. スキン / Artwork / Help (group ごとの実測と根拠。`check.py` 出力 + `verify_refs.py` 照合済みの読み手関数)

phase: **boot** = 起動経路 (Init core paths〜最初のアイドル) に呼出点あり / **boot-conditional** = 起動経路だが設定が既定だと開かない / **on-demand** = 操作時のみ。
files / bytes は `$INSTDIR` 相対のユニークパス (`inventory_files` 27402 件中、15 group で 223 件・35043427 byte)。tier 列は本 ticket の推奨、推定列は `bootset.json` の現行 tier (件数)。

| group | phase | 推奨 | files | bytes | 現行推定 | 読み手 (VA) と根拠 |
|---|---|---|---:|---:|---|---|
| skin-splash | boot | T0 | 1 | 175455 | T0:1 | 0x136cba0 `Title.png` (レジストリ `General\SplashImage` 既定)、呼出元 0x13734d0 |
| skin-startsound | boot-conditional | T0p | 1 | 72076 | T0:1 | 0x11bfb10 / 0x1368840 `StartSnd.wv`。`ProcessFirstTimeStuff` 0x11ef180 の 'Play startup sound' (flags&8==0) |
| skin-ondemand | on-demand | T1 | 5 | 270952 | T0:5 | BigFruit (About 0x1369240) / ClipHanger (0x107f990) / PickerChan (0xec6760) / ScopeGradient (0xf633b0, 0xf69c90) / RenderSnd (0xc4eac0, 0x1188470) |
| theme-default | boot | T0 | 2 | 43826 | T0:2 | 0x11317b0 `(Default)` → thmDefault.png / tweak_default.png / `__current.flstheme` |
| theme-others | on-demand | T2 | 34 | 17723743 | T2:34 | 検索パス区分 0x413 `Themes` の列挙先 (登録 0x9db5b0 のみ確認) |
| wallpaper-default | boot | T0 | 1 | 97 | **T2:1** | 0x11c58d0 `Default.txt` (キー Background / Caption / Grid…)。呼出元 = 各フォーム生成 + 0x1196c00 (LoadSettings 経路) |
| wallpaper-images | on-demand | T2 | 28 | 1806488 | T2:28 | 0x11f7b40 壁紙選択 (`Browser.html`)、呼出元 0xf1be90 |
| fonts | boot | T0p | 56 | 5582269 | T0:2 T0p:50 T2:4 | 0x668d30 フォント表 (OpenSans-Regular/CondLight・ILGlyphsEx.ilfont。`segoeui`/`tahoma`/`consola`/`lucon` の名前も参照)、0x668b50 `.ilfont` |
| help-scr | boot | T0p | 2 | 10949 | **T1:2** | 0x10be350 (HelpPlugins.scr / HelpAliases.scr)。呼出元 0x1196c00 = ログ '  Initialize the help file'、その親 0x11a57c0 = **LoadSettings** |
| help-entry | on-demand | T1 | 2 | 33890 | T1:1 T2:1 | 0x10be5c0 `index_offline.html` + `/html/%s` (URL 組立。呼出元 0x10be820 / 0x10be840) |
| help-html | on-demand | T2 | 51 | 2880931 | T2:51 | 0x10be8c0 `/html/FD/web/documents/%s.html`、0x10bea60 `/html/plugins/%s.htm`、0xf1d660 `WhatsNew.htm` |
| texts-dialog | on-demand | T1 | 24 | 110241 | T0p:8 T1:16 | 0x10d5980 (BoxEdition/NotReggedTxt/DemoTxt)、0x1366ae0、0x1369240 (About)、0x11cb000 (`NewVersion.txt` = 更新確認) |
| empty-project | boot | T0 | 1 | 46361 | T0:1 | 0x11db420 `Data\System\Empty.flp` (無いと 'Could not find default empty project.')。呼出元 0xe1d090 / 0xed5c40 |
| lang-moe | boot-conditional | T2 | 7 | 6282124 | T1:7 | §2 |
| lang-svg | unresolved | T1 | 8 | 4025 | T1:8 | 参照元未特定 (.svg 汎用ローダは 0xdceea0) |

- **ヘルプは WebView ではなく URL 組立**: FL は HTML を解釈せず `index_offline.html` と `/html/…` の URL を作って外部ビューアへ渡す (#118 help-viewer の入力)。`Help/` 全体で 55 ファイル、起動で読むのは `.scr` 2 件のみ。
- 起動で触れる `Artwork/Fonts` は、`Cuprum.ttf` / `FrancoisOne.ttf` が `Shared/Artwork/Fonts/` と**同一内容** (同一 block)。現行推定で T2 になっている 4 件は `OFL.txt` 2 件 + この重複 `.ttf` 2 件 (内容重複排除で実害なし)。

## 4. VFS 配置

写像 (pathreg 既定表。`tools/shimx/pathreg/REPORT.md` §2.2): `C:\Program Files\Image-Line\FL Studio 2026\<rel>` → `/fl/<rel>` (RO)。`check.py` が 223 件全部を
`createMapper().map` に通し、**`/fl/<rel>` との不一致 0 件**を確認 (大小文字は保存)。

| FL の検索区分 (0x9db5b0 登録) | ユーザ側 (level 0 / 2) | インストール先 (level 1 → `/fl`, RO) |
|---|---|---|
| 0x40f Languages | `Languages\` (永続 `/c/home/**`) | `System\Languages\` |
| 0x409 Skins | `Skins` | `Artwork\Skins\` |
| 0x413 Themes | `Themes` | `Artwork\Themes\` |

- 既定構成では `Languages\` `Skins\` `Themes\` は空。初回の `FindFirstFile` / `GetFileAttributes` が**存在しない永続側ディレクトリ**に当たっても失敗を返せばよい (fail-soft かは §6 で動的確認が要る)。
- 配信 tier の推奨差分 (現行 = `tools/assets/bootset/bootset.json`。`classify_bootset.py` / `BOOTSET.md` は自動生成のため本 PR では編集しない):

| # | 対象 | 現行 | 推奨 | 根拠 |
|---:|---|---|---|---|
| 1 | `Help/HelpPlugins.scr` `HelpAliases.scr` (2 件 10949 byte) | T1 | **T0p** | LoadSettings で読む (§3) |
| 2 | `Artwork/Wallpapers/Default.txt` (1 件 97 byte) | T2 (規則なし) | **T0** | 起動中のフォーム生成で読む |
| 3 | `System/Languages/*.moe` (7 件 6282124 byte) | T1 | **T2** | 既定 `en` では開かない |
| 4 | `Artwork/Skins/Default/StartSnd.wv` (72076 byte) | T0 | T0p | flags&8 の条件付き |
| 5 | Skins/Default の BigFruit / ClipHanger / PickerChan / ScopeGradient / RenderSnd (5 件 270952 byte) | T0 | T1 | 操作時のみ |
| 6 | `System/Texts/*.txt` 直下 8 件 | T0p | T1 | ダイアログ経路のみ |

  T0 の合計は #4・#5 で 343028 byte 減り #2 で 97 byte 増える (差し引き 342931 byte 減)。**実トレースで答え合わせするまでは推定**として扱う (#105 `assettrace` の `diffTiers` が入力)。

## 5. 検証 (実測)

コミット済み `14cb47e` を `git worktree add --detach` で展開して `bash tools/startup/loadpaths/e2e.sh` (並列 1、node v22.23.3 / python3.14):

| 項目 | 結果 |
|---|---|
| e2e 3 回 | exit 0 ×3 / 所要 **12.45–12.72 秒** / load average (1 分) 開始 0.61・0.70・0.74 → 終了 0.70・0.74・0.80 |
| `check.py` | 15 group / 223 ファイル / `map_mismatch` 0 / first-match で後続 group に落ちた件数 1 (`wallpaper-default` の `Default.txt` を `wallpaper-images` の glob も拾う) |
| `mk_manifest.py` | 25165 block (extracted 25165 件と一致)、検査 200 block のバイト不一致 0。NSIS 参照されない block が 1 件 (idx 29) 存在し、`recover_paths.py` のパス復元は 25164 block 分 |
| `verify_refs.py` | pdata 関数 57816 / reader 33 / claims 36 関数・文字列参照 70 / call 辺 24 / fail 0 |
| ネガコン (verify_refs) | 文字列 1 + 呼出辺 1 を壊した spec → 2 件検出 (期待 2) |
| `moe.py` | 7 ファイル ok / 暗号化ヘッダ distinct 1 / charset=UTF-8 全件 / 不正 UTF-8 0 |
| `crosscheck.py` 別算法 | 64 bit ワード版 = バイト版 (7/7 一致)、標準 `gettext` で読んだ非複数形 msgid 全件 (de 14563・fr 12365 …) の訳文が自前パーサと一致 (不一致 0) |
| ネガコン (moe) | RSA ヘッダ 1 byte 反転 / n を 1 byte 反転 → 16 進文字列にならず失敗、本体先頭 1 byte 反転 → magic 破壊で失敗、後半切り詰め → 範囲外で失敗 (4/4 検出) |

再現: `source tools/shared/env.sh` (または `FL_WIN64_DIR` 指定) → `bash tools/startup/loadpaths/e2e.sh`。fl-win64 展開は `docs/WORKFLOW.md` §11。

**検証範囲**: DLL の静的構造 (関数境界・RIP 相対の文字列参照・直接 call) と、インストーラ由来のファイル一覧・サイズ。
**範囲外**: FL の実行 (boot は `CreateFruityInstance` に未到達 — unit 初期化 209 で停止: `tools/flelift/boot/REPORT.md` §0)。間接 call / vtable 経由の到達性、レジストリ値の実測、ファイル不在時の挙動。`phase` は静的な呼出点の位置づけで、「実際に開かれる」ことの実測ではない。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `phase` / tier の動的確定 (boot 中の open() トレース) | §3・§4 の推奨は静的根拠。boot が `CreateFruityInstance` に未到達 (unit 初期化 209 で停止) の間は答え合わせ不可 | #105 (T1・`assettrace` が入力、本 REPORT の group を diff の基準にする) / 依存 [FLE-2] #253 |
| `0x9de400` の `[self+0xa8]->vtbl+0x30` (検索パス服務) の実体と、ユーザ側ディレクトリ不在時の挙動 | `Languages\` 等の level 0 を VFS でどう見せるか (空ディレクトリ要否) | 新規子チケットを PM が起票 (親 #39。boot 到達後に実測) |
| 非 en 言語 (`Program Language`=`ja` を seed + `/fl/System/Languages/ja.moe`) の実読込 e2e と、`en` で .moe を一切開かないことの実測 | §0-1 の動的確認 | 同上 (非 en の seed 先は `tools/startup/vreg/data/seed.json`。生成元 `scripts/build_seed.py` の `OVERRIDES` で `Program language` を `apply:true`・value=`ja` にする) |
| `GetUserPreferredUILanguages` が en-US を返すことの実測 (非 `zh` を保証。`zh` 返却だと `Program language` が自動書込みされ 0x9deaa0 の分岐が変わる) | 言語の決定性 | shimx 側 (#13 系) / winstubs の子チケットを PM が起票 |
| `lang-svg` の参照元 (推定: 言語選択 UI) | 8 ファイル 4025 byte の phase が `unresolved` | 同上 (boot 到達後に UI 経路で確定) |
| Windows 標準フォント名 (`segoeui` `tahoma` `consola` `lucon`) の代替解決 (VFS に無い) | GUI の文字描画 | GUI 側 (#10 の子) へ PM が起票。`fonts` group の `Shared/Artwork/Fonts/*` が代替の候補 |
| テーマ選択 UI の列挙経路・`Default.txt` が参照する壁紙画像の必須性 | `theme-others` / `wallpaper-images` は検索パス登録と選択 UI 名のみ確認 | #105 (実トレース後) |
| `bootset.json` / `classify_bootset.py` への §4 差分 6 点の反映 | 配信 tier の精度 | `tools/assets` の責務。PM 判断で #22 系の子チケット (本 PR では編集しない) |
| 復号ツールの扱い (`moe.py`) | 本ツールは FL のローカライズ資源の難読化を解くコード。n・鍵・復号結果は保存しない設計だが、EULA の逆アセンブル/複製の制限との関係は未判断 | `docs/LEGAL.md` 側の論点として PM が判断 (LGL 系)。ランタイムには不要なので、問題があれば `moe.py` / `crosscheck.py` の削除で済む |

DEFECTS.md 追記案: なし (新しい silent miscompile 類型は見つけていない)。

## 7. 次タスク提案

1. boot が `CreateFruityInstance` を抜けた時点で `assettrace` を実行し、§3 の phase / §4 の差分 6 点を実測で答え合わせする (#105)。
2. 非 en seed の言語 e2e: `tools/startup/vreg/data/seed.json` (生成元 `build_seed.py` の `OVERRIDES` で `Program language` を `apply:true`・value=`ja` にした派生) + `/fl/System/Languages/<code>.moe` の全量読込を確認する子チケット。
3. `bootset` の規則に §4 の差分を反映する PR (`tools/assets`)。
