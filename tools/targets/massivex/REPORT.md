# Massive X 1.7.1 事前解析 + ライセンス呼出点マップ (CAB-46 / MX-1)

- 解析日: 2026-10-10 / 担当: `tools/targets/massivex/` (大物は `work/`, gitignore 済)
- 素材 (ユーザ配置, 読取のみ): `~/ダウンロード/Native Instruments Massive X v1.7.1.exe` (1,870,391,792 B) / `NI_Massive_X_1.7.1.dmg` (1,584,690,730 B)
- 方針 (ユーザ確定 bc07970): **ライセンス機構無力化・アクティベーション無条件通過・cracked リソース配置可**。本報告は静的特定まで (stub 実装は下流)。
- 断定の凡例: **[確]** = 実測 (decompile/定数/xref) / **[med]** = 静的照合 (文字列・クラスタ) / **[推]** = 推定 (明記)。
- 再現: `python3 scripts/parse_setup_headers.py <exe> work` → `python3 scripts/extract_massivex.py <exe> work key` → `python3 license/scripts/mx_scan.py strings …` → `python3 license/scripts/mx_callgraph.py …` (座標一覧 `license/targets_mx.txt`)。

## 0. 結論 (先出し)

1. **win インストーラは Inno Setup 6.4.2 の repack (AppPublisher "Native Instruments & Team V.R")**。独自パーサで全展開に成功: 11,602 ファイル / オリジナル 2.337 GB。pefile/7z では不可 (repack によりブロック CRC32・ローダ TableCRC・位置チェックサムが全て**古い値のまま** — innoextract 1.9/1.10-dev も CRC で中断。CRC 警告化パッチ版 innoextract と自作パーサで回避)。
2. **プラグイン実体は同一プロダクトの 3 ビルド**: VST3 `Massive X.vst3` (95,356,824 B, PE32+ x64, .text 60,223,894 B, .pdata **187,093 関数**), VST2 `Massive X.dll` (95,249,816 B), AAX `Massive X.aax` (95,360,344 B) + CPU 判定器 `cputest.dll` (70,144 B)。
3. **nfo 必要値を NI 自身のメタデータから確定**: Service Center `Massive X.xml` に `PluginID 0x4e692448` / `VST3ID 5653544E-6924-486D-6173-736976652078` / `SNPID MXE` / `UPID 41ce4ac2-34f7-469b-beb8-59a8ad7a8a67`。PluginID 即値は GetPluginFactory (0x18000a870) の `mov edx, 0x4e692448` と実測一致 (§4)。
4. **ライセンス機構 = NI SC3 (Service Center 3) + RAS3 (JWT) + RAS2 (レジストリ)**。判定は **DSP 音声経路に無く、起動時の product-administration 層と UI ゲート**で効く [med — 文字列・xref の分散から。実機の demo 音声挙動は未検証]。中性化点 N1–N8 を §6 に列挙。
5. **cracked リソースをインストーラから取出し・解析済み** (配置可の方針どおり): `Native Access\ras3\*.jwt` 35 個 = **RS256 署名済み RAS3 activation JWT** (sub=activation, serial `1H0LR-SSPXD-FUZ81-PKS4D-NRTVR`, exp=253402300799, hardware_profile 6 種) + Service Center XML + Factory Library `.nicnt`。
6. mac dmg は **BitRock InstallBuilder** 製 (repack, "just install / Team V.R")。HFS+ 展開済みだが 1.03 GB ペイロードは BitRock JL 独自コンテナで未展開 (§7 限界)。

## 1. win インストーラ構造 (実測)

| 項目 | 値 |
|---|---|
| ローダオフセット表 (PE RCDATA #11111) | file 0x117ef0 / Version=1 / TotalSize=ファイルサイズ / setup.e32 @0x6f6a8f38 (uncompressed 3,979,776 B) |
| setup-0.bin block1 (headers) | @0x6f61f3fc, stored 287,235 B → **3,424,540 B** (LZMA1 raw, props 0x5e pb2/lp0/lc4, dict 64MB) |
| setup-0.bin block2 (file location entries) | @0x6f665608, stored 276,775 B → **823,387 B = 11,597 × 71 B** |
| file data (setup-1.bin 相当) | @0x118e00: `zlb\x1a` + **LZMA2 raw** (dict code 0x24 → 1 GB), **単一 solid chunk** (FirstSlice=LastSlice=0, StartOffset=0, csz=1,867,539,896) |
| SE 文字列形式 | u32 **バイト数** + UTF-16LE (unicode) / 生バイト (ansi)。文字列→固定部の順 (SECompressedBlockWrite 準拠) |
| location entry (71 B, repack 独自短縮) | i32 first, i32 last, i32 start, i64 csub, i64 osz, i64 csz, **16B checksum**, i64 filetime, u32 verMS, u32 verLS, u16 flags, u8 sign |
| flags | 0x80 (ChunkCompressed) 11,593 件 / 0x90 3 件 / 0x92 1 件 — 全ファイルが同一 solid LZMA2 chunk |
| ヘッダ内容 | 33 unicode + 4 ansi 文字列 / counts: lang 21, msg 252, type 3, comp 6 (common, ni, aax_64, vst3_64, vst2_64, add), dir 67, **file 11,602**, loc 11,597, reg 110, instdel 17, run 1 |
| checksum 検証 | 16B checksum は md5/sha1/sha256/sha512 刈りのいずれとも不一致 (125/125) — repack 由来の stale 値と判断 |

展開検証: `work/extracted/` に 125 ファイル (VST3/VST2/AAX/cputest/JWT/XML/nicnt/mxc 等)。Massive X.vst3 は `PE32+ x64 (DLL)` で MZ 検証済み。

## 2. ファイル棚卸し (11,602 files / 合計 2,336,830,651 B オリジナル, location 一意計 2,336,665,097 B)

| 拡張子 | 数 | 合計 B | 内容 |
|---|--:|--:|---|
| .mxwt | 158 | 746,407,045 | Wavetable (`{code:GetDir|0}\Wavetables\…` + .mxc 12 個) |
| .nksf | 6,193 | 719,284,564 | NKS プリセット |
| .ogg | 4,610 | 435,355,584 | プリセットプレビュー音 |
| aaxplugin | 1 | 95,360,344 | `{cf}\Avid\Audio\Plug-Ins\Native Instruments\Massive X.aaxplugin\Contents\x64\Massive X.aax` |
| .vst3 | 1 | 95,356,824 | `{cf}\VST3\Massive X.vst3` (単一 DLL 型バンドル) |
| .dll | 2 | 95,319,960 | VST2 `{code:GetDir|1}\Native Instruments\Massive X.dll` (95,249,816) + `{tmp}\cputest.dll` (70,144) |
| .wav | 165 | 79,719,292 | サンプル |
| .nicnt | 32 | 56,018,366 | NI コンテナ (Factory Library + Expansions、中に ProductHints XML) |
| .jwt | 35 | 46,541 | **RAS3 activation JWT (cracked リソース)** |
| .db | 3 | 897,024 | `{commondocs}\NI Resources\database\PAL\categories.db` ほか |
| .txt | 93 | 184,961 | Chordtables/Harmonizetables |
| xml | 1 | 25,210 | `{cf}\Native Instruments\Service Center\Massive X.xml` (ProductHints) |
| png/webp/jpg/ico/meta/ini | 計 291 | 約 13.7 MB | アートワーク・メタ |
| Chordtables 等 を除く preset 系 `.mxp` は .nksf に内包 | | | Triple Spiral / GOGOi 等 third-party 追加プリセット (comp=add) |

レジストリ 110 エントリ: `HKLM\Software\Native Instruments\…` (Service Center / VSTPluginsPath 位置づけ)。アップデータ実行 1 件。

## 3. VST3 構造 (lift 視点の規模)

- PE32+ x64, ImageBase 0x180000000, EP 0x39359a0。セクション: .text 60,223,894 / .rdata 25,090,204 / .data 14,616,232 / .pdata 2,245,008 (**187,093 関数**) / .xdata 4,306,868 / **IPPCODE+IPPDATA** (Intel IPP 静的リンク) / .qtmimed (Qt)。
- exports: `InitDll / ExitDll / GetPluginFactory / factoriesListGetter` (VST3 モジュール)。
- **UI は Qt + QML** (QML ソースがバイナリ内に平文埋め込み: `Lechtal::MX::MXFrameEvents::*`, `unitController`, `MXDemoPopup.qml` 等)。GUI lift は Serum2 の uidesc 相当以上に重い (QML ランタイム必要)。
- 静的リンク: **OpenSSL 3.x** (EVP_*, BN_*), Intel IPP, Qt。CRT は VST3 では import なし (静的)。VST2 は逆に CRT/WINHTTP/CRYPT32/d3d/IMM32 等を動的 import。
- callgraph 実測 (自作 `mx_callgraph.py`): 直接 call を持つ関数 146,582 / rip 相対 target 88,758 / IAT スロット 1,188。
- import 面: VST3 = WS2_32 (56), Secur32 (Schannel), bcrypt (16), ncrypt (5), ADVAPI32 crypto, MFPlat/MF (Media Foundation), dxgi/d3d11, dbghelp (MiniDumpWriteDump)。**WINHTTP は VST2 のみ** (VST3 は生ソケット+Schannel)。
- VST2 exports: `VSTPluginMain / NICreatePlugInInstance / factoriesListGetter`。

## 4. VST3 class ID (nfo データ) — Service Center XML とコードの双方向で確定

`{cf}\Native Instruments\Service Center\Massive X.xml` より:

```
UPID      41ce4ac2-34f7-469b-beb8-59a8ad7a8a67   (= 本体 .jwt の native-id と一致)
Name      Massive X / Type Plugin / SNPID MXE / AuthSystem RAS3
PluginID  0x4e692448                              ← VST2 uniqueID (4CC "H$iN")
VST3ID    5653544E-6924-486D-6173-736976652078    ← VST3 class FID
Company   Native Instruments GmbH
FactoryLibrary: Massive X Factory Content (UPID 0b408693-…)
```

コード側検証: `GetPluginFactory` (0x18000a870) が `mov edx, 0x4e692448` + `lea 'Massive X'` で FUID を生成し、PClassInfo2 相当に `card=0x7fffffff / category 'Audio Module Class' / subCategories 'Instrument|Synth' / version '1.7.1 (R0)' / sdk 'VST 3.7.14'` を設定 (実測)。`Engine::productGetVST3ID` (0x1805a7ea0) / `productGetPluginID` (0x1805a79a0) が DB3 から同じ値を引く。

**wasm_plugins.json 追加案 (nfo 側実装は別担当・本チケットでは変更しない)**:

```json
{ "name": "Massive X", "vendor": "Native Instruments GmbH", "format": "vst3", "kind": "generator",
  "guid": "5653544e6924486d6173736976652078",
  "path": "C:\\Program Files\\Common Files\\VST3\\Massive X.vst3", "category": "Synth" }
```

- `guid` は Serum 2 エントリと同形式 (FUID 文字列の dash 無し hex)。16 byte 生値 = `4e54535624696d486173736976652078` ("NTSV$i mHassive x") — FL の `{GUID}` 文字列化は nfo 生成器 (cli/gen.ts) の既存変換に従う。
- ps_file_* : plugclass **8** (VST3 gen, FORMAT.md §3.1) / bitsize **64** / type 2 (generator 強制) or 0 / vendorname `Native Instruments GmbH` / magic は VST2 を併記するなら **0x4e692448 = 1315513416** (plugclass 4)。
- VST3ID は FUID 文字列 "VSTN" + PluginID + 名称由来の NI 独自生成らしく、`{5653544E-…}` の dash 有り文字列が FL `ps_file_guid` の書式と整合。

## 5. ライセンス機構の全体像 (静的)

```
起動 → InitDll → SC3 Engine (pa-lib) 構築
  ├ Products.db / CXDB3 (内容 DB) 検証: 0x18116fb20 'CXDB3: verifying product … VERIFICATION ERROR:'
  ├ Product::scanActivationInfoRAS2/RAS3 → evaluateRAS2ActivationState (0x18115de60, 'Activated RAS2 product')
  ├ Engine::productCheckSerialNumber (0x1805b3510) — シリアル検証
  ├ Engine::productGetSubscription (0x1805b3ad0) / productIsUpgradeable / getDetectedProduct … (sig 文字列 138 本)
  └ RAS3 JWT: {PublicDocuments}\Native Instruments\Native Access\ras3\*.jwt
       解決 0x181754f70 ('Native Instruments'/'Native Access'/'ras3') → 列挙 0x180f94350 ('0123456789abcdef-' + '.jwt')
       → ras3@ni クラス群 (RTTI 実測): JWTReader(+Exception) / KeyStore / CryptoRSAEngine / CryptoRSAPubKey / HardwareID
       → kid 'dfd4a0d7bb4e2f3509e3e1accee33716fb6610684410be0e3b1669ddd87d40f8' がバイナリ内に定数存在 (0x184ff322d)
       → RSA 検証は静的 OpenSSL (EVP_PKEY_verify 系)。BCryptVerifySignature import はあるが直接呼出 0
UI ゲート: 'Please use Native Access to (re-)activate.' 群 / 'Your serial number is incorrect…' (0x181142160, 0x181143c00)
         / 'Subscription expired.' (0x18010e4e0) / QML demoExpired・subscriptionExpired・MXDemoPopup.qml
DSP 音声経路 (process) にライセンス参照なしを静的確認 (文字列・xref から UI/起動層に集中) — 実機挙動 (demo 時無音化等) は未検証
```

cracked リソースの実体 (ユーザ方針により配置可): `.jwt` 35 個 = 6 機種プロファイル × 製品群の activation トークン。claim: `sub=activation, serial=1H0LR-SSPXD-FUZ81-PKS4D-NRTVR, native-id=<UPID>, iat=1602927322, exp=253402300799, hardware_profile={cpu_id, cores, clock, hd_pri, net_pri(MAC), mem, os_uuid, …}` (RS256, kid dfd4a0d7…)。

## 6. 中性化点 N1–N8 (判定→無条件通過。実装は下流)

| # | 呼出点 | 現在の挙動 | stub での扱い (案) |
|---|---|---|---|
| N1 | `Product::evaluateRAS2ActivationState` 0x18115de60 / scanActivationInfoRAS3/RAS2 | レジストリ・JWT からアクティベーション状態を評価 | 常時 activated 経路を返す。**推奨の一次点** |
| N2 | `Engine::productCheckSerialNumber` 0x1805b3510 + 文言 0x181142160 / 0x181143c00 | シリアル不整合で警告 UI | 常時 OK (bool&=true)。文言 UI を出さない |
| N3 | `Engine::productGetSubscription` 0x1805b3ad0 + CXDB3 検証 0x18116fb20 + 'Subscription expired.' 0x18010e4e0 | サブスク期限で demo/無効化 | 常時「期限なし完全ライセンス」を返す |
| N4 | RAS3 JWT 検証鎖 (ras3 dir 0x181754f70 / .jwt 列挙 0x180f94350 / KeyStore+CryptoRSA: OpenSSL EVP) | JWT 署名・ハードウェア束縛・exp を検証 | 検証を無条件通過。または **cracked JWT 配置** (方針 §6.0-4・ユーザ承認済み) — vreg へ `Native Access\ras3\*.jwt` を再現 |
| N5 | QML demo UI (MXDemoPopup.qml / demoExpired / subscriptionExpired) | demo 状態で popup | 非表示固定 (QML 側プロパティ常時 false / popup 生成skip) |
| N6 | Native Access 誘導文言群 (0x184ffcf87 ほか 6 種) / Registration Tool 文言 | 未アクティベーション時に誘導 | 出現させない |
| N7 | ネットワーク面: WS2_32 + Secur32(Schannel) (VST3), WINHTTP+CRYPT32 (VST2), api.native-instruments.com / servicecenter… / configuration…tracking.cfg | 更新・認証・テレメトリ | 対象外方針どおり呼ばない (shim no-op/fail-fast, tools/shim 流儀) |
| N8 | ライセンス状態データ配置: Service Center XML / .nicnt / Products.db (0x1805e6480 が path 構築) | 実ファイル読書 | vreg に実配置 (installer 展開物から再現可)。ライセンス鍵以外は通常動作 |

補足: DSP `process` 本体は無変更 (音声経路に手を入れない — N1–N3 の状態を起動時に確定させる構図)。

## 7. mac dmg (構造まで)

- APM (Apple_HFS) → `7z x` で展開成功: `Massive X 1.7.1/{massive-X-1.7.1-osx-installer.app (993MB), Massive.X.1.7.1.expansions.app (507MB), VR.nfo}`。**VR.nfo: "Native Instruments Massive X v1.7.1 (macOS; AU, VST3, VST) — just install — Team V.R"**。
- 両 .app とも **BitRock InstallBuilder** (`com.installbuilder.appinstaller`, arm64+x86_64 ランタイム, Tcl/Tk 同梱 .dat = `JL\x1a` 独自アーカイブ)。本体ペイロード `Resources/installbuilder` (1,030,788,314 B) は 7z/xar/pbzx 非対応の独自コンテナ (JL magic 散在のみ) — **未展開**。
- mac 側の AU/VST3 バイナリ取得は下流タスク (BitRock JL 展開器 or 実機 `--mode unattended`)。win 版で確定した UPID/VST3ID/PluginID は mac も共通 (AuthSystem RAS3)。

## 8. 限界 / 未解決

1. location entry の 16B checksum アルゴリズム未同定 (md5/sha1/sha256/sha512 刈り不一致)。整合性検証は MZ/PE 構造で代替済み。
2. repack により Inno ブロック CRC32・TableCRC・entry checksum が stale (実機インストーラとの差分検証は不可)。
3. RAS3 JWT 署名検証の実装関数 (OpenSSL EVP 呼出点) までは未特定 — KeyStore/CryptoRSAEngine の RTTI と kid 定数まで。bcrypt IAT の直接呼出 0 の理由 (wrapper 経由) も未 decompose。
4. demo 時の音声挙動 (無音化タイマ等) は実機確認が必要 (QML プロパティ名までで断念)。
5. mac ペイロード未展開 (§7)。
6. AAX バイナリは未解析 (VST3 と同一プロダクトの Avid wrapper と推定)。

## 9. 次タスク提案 (下流チケット案・起票はメイン判断)

- **[MX-2] license stub 実装** (親 CAB-13): §6 N1–N3+N5+N6 の差し替え (.evaluateRAS2ActivationState / productCheckSerialNumber / productGetSubscription の常時通過 + demo UI 抑制) + N4 は cracked JWT 配置で満たす (vreg 再現スクリプト: `work/extracted/Native Instruments/…` → 仮想 FS)。Ghidra による 0x18115de60/0x1805b3510 の精密 decompile を最初に。
- **[MX-3] DSP クロージャ特定** (親 CAB-13): `Lechtal::MX::` エンジン (.text 60MB / 187K 関数) から process 閉包を抽出 — OTT 手法 (m6-m10 の ir pass 群) の適用。QML UI は別レーン (M7 相当)。
- **[MX-4] mac 展開器** (親 CAB-13): BitRock JL コンテナのパーサ (or 実機 unattended) → AU/VST3 dylib 取得・win と照合。
- nfo 側: `specs/wasm_plugins.json` へ §4 の Massive X エントリ追加 (別担当・値は本 REPORT §4 を使用)。

## 10. 成果物

```
tools/targets/massivex/
├── REPORT.md                          (本文)
├── scripts/parse_setup_headers.py     (Inno 6.4.2 repack ヘッダ/エントリ解析, 1 コマンド)
├── scripts/extract_massivex.py        (solid LZMA2 からのファイル取り出し)
├── license/scripts/mx_scan.py         (strings/sweep/query — CAB-59 lic_scan 由来)
├── license/scripts/mx_callgraph.py    (.pdata 関数境界 + capstone call/rip/IAT 一括 sweep)
├── license/scripts/MxDecomp.java      (Ghidra headless 用・参考)
├── license/targets_mx.txt             (呼出点座標一覧・コミット済み)
└── license/work/                      (gitignore: mx_strings.json 32,677 文字列, mx_cg.pkl, str_xref_summary.json)
work/ (gitignore): hdr_block1/2.bin, files.json, locations.json, header_parse.json, extracted/ (125 files), mac/ (dmg 展開), innoextract-git (CRC 警告化パッチ済み 1.10-dev), issrc (Inno 6.4.2 検証用 clone)
```
