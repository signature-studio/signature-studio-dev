# CAB-59 (KH-8) HeartCore ライセンス層 — 呼出点特定 (静的解析)

- 解析日: 2026-10-10 / 担当: `tools/targets/kilohearts/license/` (大物は `work/`, gitignore)
- 対象: `work/winpkg/HeartCore.core_64` (76,642,304 B, ImageBase 0x180000000, .pdata 111,666 関数)
- 確定方針 (ユーザ指示 bc07970): **ライセンス機構は無力化・アクティベーション無条件通過・状態は「アクティブ済み」として振る舞う**。本報告はその実装点候補の静的特定まで (stub 実装は下流チケット)。
- 再現: `lic_scan.py` (strings/sweep/query) + `lic_funcs.py` (関数詳細) + `ghidra_decomp.sh` (範囲限定逆コンパイル)。sweep 产物は `work/hc_{strings.json,xrefs.pkl}` (再利用可)。

## 0. 結論 (先出し)

| 項目 | 結果 |
|---|---|
| 判定の入口 | `getStatus` 系 4 関数 (`LicenseManagerHelper::*`) と分類 thunk 5 種。**UI/Model 側のみで消費され、DSP `process` 本体は通らない** (前報 §5 の再確認) |
| 鍵検証 | `KHSUnlock` export (0x180002780) → グローバル鍵バッファ → 変換 (salt `as0d789f6g` 併合) → **40hex ホワイトリスト 5 個と照合** (0x1813d0a40..b2f) |
| 状態保持 | (1) 鍵バッファ 0x182a2d5f0 (257B), (2) LicenseManager のグローバル map (root 0x182a2eea8, 鍵=文字列), (3) LicenseManager 実体 0x490B (状態 int +0x88/+0x8c, ライセンスソース 4 種 +0x140/+0x228/+0x310/+0x3a8), (4) EditorModel 側 +0xac8 `AudioWorksLicenseHelper` |
| 呼出箇所 | **EditorModel ctor 0x180051af0 の呼出元が 47 個 = 製品数 47 と一致** (各製品 1 ヶ所)。ほか UI 表示 0x180c194f0 / 状態 poll 0x180052830・0x180052a00 / ブラウザ 0x180ef7fc0 / サンプル Import メニュー 0x180d5dbe0→0x180d5e820 / Phase Plant 0x1805c6a50→0x180d52990 |
| 無力化の最短点 | 下記 §5 の 3 候補 (最小は分類 thunk `0x1800b4ac0` の常時 true 化、または `getStatus` の定数返し) |

## 1. 前回委任 (insufficient_credits 中断) の引継ぎ判断

残骸精査の結果、**引継ぎで継続** (クリーン再実行は不採用):

| 残留物 | 状態 | 判定 |
|---|---|---|
| `scripts/{lic_scan.py, lic_funcs.py, ghidra_decomp.sh}` (未追跡, 3 本) | 完成済・動作実績あり | **そのまま採用** (commit 済) |
| `work/hc_strings.json` (31,312 文字列) / `work/hc_xrefs.pkl` (rip 44,885 / iat 425) | 完全 (sweep 完走) | キャッシュとして再利用 |
| `work/decomp_{core,core2,ui}.txt` (38 関数) | 判読可 | 再利用 |
| `work/ghidra/decomp_core{,2}.log` の `Import failed` | 同時実行時の project name 競合。**出力 txt は成立済**で実害なし | 記録のみ |

追加で `decomp_c59.txt` (12 関数) を新規生成。`work/` は `.gitignore` 済で commit 対象外。

## 2. 判定関数一覧 (実測 VA)

| VA | サイズ | 役割 (Ghidra decompile + xref で確認) |
|---|--:|---|
| 0x180054bd0 | 285 | **`LicenseManagerHelper::getStatus`**: `getManager(name)` → null なら 0x16 を返し WARN → 鍵状態構築 → `FUN_1800b4b10([mgr+0x88], 鍵状態)` を返す。kind==3 かつ名前空のとき鍵文字列を `"Snapin Das Kleine Krokodil"` に差替 |
| 0x180054b90 | 64 | EditorModel 束縛 wrapper: `getStatus([this+0xac8]→string, this+0x298, [this+0x998])` |
| 0x180054ab0 | 16 | `this+0x298` への `getPending` 尾跳び wrapper |
| 0x1800548a0 | 125 | `hasTag`: `FUN_18010b6d0(mgr, tag)` (= mgr+0x470..0x478 の vector\<string\> 走査)。直接呼出 0 (間接のみ) |
| 0x1800549c0 / 0x180054ac0 | 158 / 122 | `getStatusAndDaysLeft` / `getPending`。getPending の直接呼出 0 |
| 0x180107430 | 397 | **`getManager(key)`**: グローバル map (root 0x182a2eea8) を string hash で検索 → あれば shared_ptr 取得、無ければ生成 (0x180106f20) |
| 0x180106f20 | 669 | LicenseManager 生成: `new 0x490` → ctor → **0x18010a1e0 (unlock適用)** → 0x18010a740 (通知) → map 挿入 |
| 0x180109d00 | 353 (pdata) | **`LicenseManager::LicenseManager(const Product&, bool)`** (RTTI lambda 文字列で署名確認): ソース 4 種を +0x140/+0x228/+0x310/+0x3a8 に構築 |
| 0x18010a1e0 | 289 (pdata) | **unlock 適用**: `[mgr+0x450]` 未処理かつ **`FUN_180021d50()==0`** (鍵≠マスター定数) のとき +0x450=1, pending(+0x458..460) 解放, ソース再計算 (0x18010a3c0, boost FileWatcher 含む) |
| 0x18010aa20 | 1044 (pdata) | **状態計算**: `FUN_180021d50()` ゲート → ソース +0x140/+0x228/+0x310/+0x3a8 を読み (0x18017e6c0 / 0x180111150 等) 状態値 (5/8/0x1c 等を観測) |
| 0x18010a740 / 0x18010bff0 | 664 (pdata) / 11体 | 変更通知 (旧/新 状態比較 → EventSlot 発火)。`FUN_180021d50()==0` のとき `[mgr+0x488] = (status==0x1c)` |
| 0x1800b4b10 | 157 | **状態マージ**: 29 エントリ (idx 0..0x1c) の分類テーブル `aiStack_78` で両者をクラス化 (0..4) し大きい方を返す。テーブル実値: idx 0-4→0, 5→4, 6→0, 7/8→4, 9→3, 10-23→0, 24→0, 25→2, 26→4, 27→1, 28→0 (機械語 disasm + decompile で確認 — 初版の「24/25→2」「28→4」は誤り、§8 参照) |
| 0x1800b4ac0 / ad0 / ae0 / af0 / b00 | 7-16 | **分類 thunk**: `0x60003a0`>>s (s∈{5,7,8,9,25,26}), `0x40001a0`>>s (s∈{5,7,8,26}), s==0x19, s==9, s==0xd |
| 0x180021d50 | 416 | **マスター鍵判定**: 鍵バッファ 0x182a2d5f0 → `FUN_180021f60` 変換 → 40hex なら `f6e538277fe8191ff1ecb5ce76154f8dc1731654` (0x1813d0a40) と比較 |
| 0x180021bd0 | 328 (pdata) | **鍵ホワイトリスト検証**: 変換結果を 5 定数 (§4) と照合し状態コードを返す |
| 0x180021f60 | 563 (pdata) | 鍵変換: 即値 `as0d789f6g` (`0x6639383764307361`+`0x6736`、10 文字 — 初版「as0cd7896g」は誤記) を接頭併合 (以降のハッシュは未同定・40hex 出力) |
| 0x1800219b0 | 449 | **unlock 鍵適用**: 状態==0x1a なら即 return / 長さ>99 で 0x18 / `FUN_180021bd0` 検証結果を状態に格納 / 有効なら鍵文字列を +8 に保持 |
| 0x180021490 | 695 | 鍵状態初期化: `{state=0x17, found}` 構造体 + 製品順序表 (`<ksqe><ksbc>…<kHs1>`, 0x1813d08a0, 33 id) に `<id>` が含まれるか検索 |
| 0x180045bd0 | 310 | **ksub 購読ソース記述子** (magic static): `00041569b824a6a61e8f6fbaaa5e14db91b2d08d` + `'Kilohearts Subscription'` + `'ksub'` |
| 0x18010b6a0 / b6b0 / b6c0 / 0x18006c040 / 0x180111150 | 4-8 | フィールド getter: `[mgr+0x8c]` / `[mgr+0x488]` / `[mgr+0x138]` / `[mgr+0x88]` / ソース D (+0x3a8) 状態 |

状態コード観測値: 0x16 (22, manager null フォールバック), 0x17 (23, 初期), 0x18 (24, 不正), 0x1a (26, unlocked), 5/8/9/0xd/0x19/0x1c (ソース・UI 分岐で使用)。**enum 名は未復元** (下流で要確認)。

## 3. 状態保持

1. **鍵バッファ**: 0x182a2d5f0 (257B, .data)。`KHSUnlock(rcx)` (export, 0x180002780) が `strncpy_s` 相当で書込。他の読取は鍵検証系のみ。
2. **LicenseManager map**: root 0x182a2eea8 (`std::map<std::string, shared_ptr<LicenseManager>>` と整合するノード構造)。参照関数は 0x180106ea0 / 0x180106ee0 / 0x180106f20 / 0x180107430 / 0x1801076e0 (64B, 直接呼出なし)。
3. **LicenseManager 実体 (0x490B)**: +0x88/+0x8c 状態 int, +0x138 bool, +0x140 / +0x228 / +0x310 / +0x3a8 ライセンスソース 4 種 (**+0x3a8 = `PaceLicenseHelper`** — ctor 0x180185290 が RTTI `PaceLicenseHelper` lambda vtable 0x181412b48 を格納。**+0x228 = ksub 記述子**), +0x450 適用済 flag, +0x458..0x460 pending vector, +0x470..0x478 tags `vector<string>`, +0x488 bool (status==0x1c と連動)。
4. **EditorModel 側** (0x180051af0 で初期化): +0xab8 shared_ptr (ctor 引数 2, `getManager` の map 鍵の由来), +0xac8 **shared_ptr\<`AudioWorksLicenseHelper`\>** (RTTI 0x1813d4828, 製品 id 文字列で構築), +0x298 名前文字列, +0x998 kind int, +0x270 先の sub-obj に +0x548 キャッシュ状態 / +0x5c8 dirty / +0xdb8 flag / +0x1088 編集可否 flag。
5. **鍵ホワイトリスト**: 0x1813d0a40 から 0x30 刻みで 5 個: `f6e53827…1654` / `686357bf…c6f1` / `17fdda9c…f502` / `0a50881b…a651` / `ce714390…b125`。製品別 `keyMessage` (index.json の SHA-1) と整合する別系統の 40hex 群が .rdata に ~50 個散在。

## 4. 呼出箇所 (xref 実測)

| 呼出点 | 数 / 経路 | 意味 |
|---|---|---|
| **0x180051af0 (EditorModel ctor)** | **直接呼出 47** (0x180267c50 … 0x180880550) | 製品 47 種の各 EditorModel ctor 1 ヶ所。Helper 生成 + getManager + 0x1800526f0 でコールバック `FUN_180052830` 登録 |
| 0x180052830 / 0x180052a00 | getStatus → `{status, 編集可否}` を EventSlot 発火 (+0x548/+0x550/0x5c8 更新) | **状態 poll → UI property 反映** (共通基盤) |
| 0x180c194f0 | FUN_180054b90 wrapper | **Editor バナー/アイコン**: status==9 → 解除 / ==0xd → "License has expired." / その他 → "Invalid license…" / 無効系 → mute icon + "You do not have a license for this plugin. It will still work as part of this preset, but can not be edited." (+ "No license." / "Editing disabled" / "icons/padlock.vec" / "icons/mute.vec") |
| 0x180ef7fc0 | getStatus (2,549B) | snap-in ブラウザ ("Essential Effects" / "Premium Effects" / "Effects Hosts" / "Groups")。無償系 id 列 `egskocskpsdktafkqepkswsktfsk` を保持 — 2 字組で逆順に読むと ksge/ksco/kdsp/kfat/kpeq/ksws/ksft (7 製品) と整合 (解釈は推定) |
| 0x180d5dbe0 → 0x180d5e820 | getStatus(kind=3) → 分類 thunk `0x60003a0` | サンプル Import メニュー ("Load as IR in Convolver" 等) の機能ゲート。分類 false なら機能無効 |
| 0x180d5f190 / 0x180d52990 | getStatus / getManager | 0x180d5xxx 領域 (0x180d52990 は Phase Plant 0x1805c6a50 等 3 個所から呼出) |
| KHSUnlock (export) | 直接呼出 0 (DLL 外から) | 鍵入力の唯一の外部入口 |
| hasTag / getPending | 直接呼出 0 | vtable / std::function 経由の間接呼出のみ (呼出元網羅は未実施) |

DSP 固有 closure (42 効果) にはライセンス/ネット系参照が無く、`gain::GainDsp::process` はライセンス層を通らず実行済 (前報 §5/§6) — **判定はすべて Editor/Model/UI 層**。

## 5. 無力化の実装点候補 (下流チケット KH-9 用・stub 実装は本チケットで行わない)

| 案 | 修正点 | 効果 / 副作用 |
|---|---|---|
| A. 分類 thunk 常時 true | `0x1800b4ac0` を `mov al,1; ret` 化 (等価な C stub) | 機能ゲート (Import メニュー等) は全通過。バナー文言は `0x180c194f0` の status 値に依存し残る可能性 |
| B. getStatus 定数返し | `0x180054bd0` / `0x180054b90` がライセンス済み状態 (9 系) を常時返す | UI バナー/poll/ブラウザ/Import が一括で「アクティブ済み」扱い。**推奨** |
| C. マスター鍵経路 | 起動時に `KHSUnlock` 相当で鍵バッファへ `f6e53827…` の原鍵を設定 (or `FUN_180021d50` 常時 true) | ソース再計算がスキップされ "unlocked" 振る舞い。原鍵の実値はリポジトリに置かない (定数 VA 参照で対応) |

補足: 外部通信 (activation.paceap.com / cloud.kilohearts.com) は対象外原則につき、案 B は通信系ソース (+0x3a8 PACE / +0x310) の呼出自体を短路できるため依存も減る。

## 6. 未解決 / 下流への引継ぎ

1. 状態 enum の値→意味対応 (5/8/9/13/25/26/0x1c の正式名) — UI 分岐・分類 bitmask からの推定止まり。
2. `FUN_180021f60` 変換のハッシュ本体 (SHA-1 推定) と salt `as0d789f6g` の位置づけ。
3. `+0x140` / `+0x310` ソース 2 種のクラス名 (RTTI 未同定) とライセンスファイル path (boost FileWatcher 0x18010a3c0 で監視)。
4. hasTag / getPending の間接呼出元 (std::function / vtable) の網羅。
5. `[EditorModel+0x270]→+0x1088` (編集可否 flag) の書込側 (vtable 経由と推定)。
6. 無ライセンス時の実音声挙動 (Windows 実機確認) — 前報からの未検証のまま。

## 7. 成果物

`scripts/{lic_scan.py, lic_funcs.py, ghidra_decomp.sh}`, `REPORT.md` (本文)。`work/` (gitignore): `hc_strings.json`, `hc_xrefs.pkl`, `decomp_{core,core2,ui}.txt`, `decomp_c59.txt` (本回追加: 0x180051af0 / 0x180106f20 / 0x1801076e0 / 0x18010bff0 / 0x180021f60 / 0x18001ba90 / 0x180d52990 / 0x180d5dbe0 / 0x180d5e820 / 0x180d5f190 / 0x180ef7fc0 / 0x1800b4b10), `ghidra/*.log`。

## 8. KH-9 追記 (stub 実装完了・詳細は `KH9_REPORT.md`)

- 本 REPORT §5 の無力化候補を実装: `lic_stub.py` (lift IR 後処理 pass) により **stub 14 関数 + 状態マージ保持** を実装。getStatus ≡ 9 (案B) + thunk 常時化 + isMasterKey ≡ 1 (案C 相当) + KHSUnlock no-op。
- 検証: stub モジュール実行 70/70 PASS / snapin 6 種 base・lic とも ctx-fuzz **200/200 bit-exact** (DSP の lift IR にライセンス参照 0 件 = §4 の IR レベル実証) / 既存 snapins e2e (run_all.sh) exit=0 で増減なし。
- §2 の訂正 1 件: 状態マージ 0x1800b4b10 のテーブルは **T[24]=0, T[25]=2, T[28]=0** (機械語 disasm + decompile の両方で確認。初版本文「24/25→2」「28→4」は誤り — §2 本文は修正済み)。
- 状態 enum の意味対応 (§6-1 引継) を呼出文脈から確定: **9 = ライセンス済み (バナー解除)** / {5,7,8,26} = class 4 (同くバナー解除) / 25 = No license (編集不可) / 13 = 期限切れ / 0x1c = PACE 検証マーカー (KH9_REPORT §3)。

## 9. KH-10 追記 (EditorModel 層部分 lift 完了・詳細は `KH10_REPORT.md`)

- §6-5 の「+0x1088 書込側」を解明: (1) **0x18002e850** — 47 製品のエディタ文書 ctor 0x18002dc30 が EM+0x1b0 に登録するコールバック (poll1 冒頭 `FUN_180022be0(EM+0x1b0)` から起火) で、**thunkB(status) (mask {5,7,8,26}) 成立時に 0 を書込**、(2) 0x1800f6540 — `[+0x1088] = !thunkA(status)`、(3) 0x18068f750/930/a00 — 汎用 property setter。**getStatus≡9 では全系統が 0 を書くか不発 → flag は 0 を保ち poll2 の「編集可」が成立**。
- EditorModel ctor 0x180051af0 + poll1/poll2 (0x180052830/0x180052a00) + EventSlot/property 機構 + 分類 thunk・状態マージ (実 IR) + writer 計 **25 関数を lift** (module E, wasm 142,168B)。
- 検証: **47/47 製品が「編集可能」として成立** (`em_check.mjs` ok=50/ng=0) + native oracle (実機機械語・アリーナ ms_abi・image パッチで stub seam 両系一致) との ctx-fuzz **200/200 (700 call) + 1000/1000 (10,000 call) bit-exact**。
- 回帰: lic_check 70/70 / license run_all.sh exit=0 / snapins e2e exit=0 (無劣化)。
- §5-2 の残課題は KH-11 (CAB-248) へ引継: subscribe 経路 (0x180024bd0/0x180025080) の解除 (間接 call 復元が前提) と listener/observer ありの通知、0x1800f6540 の lift。

## 10. KH-11 追記 (CAB-247 残スコープ・詳細は `KH11_REPORT.md`、検証起点 commit `0d589e6`)

- **subscribe 経路を実 IR 化して bit-exact 達成** (残スコープ 1): kh_lower [icall] pass を snapins 5d30dff から移植 (DEFECTS.md D15 / icall §4 D1 修復) + module E lift 25→44 関数。`em` 200/200 (700/700 call)・`empoll` 1000/1000 (10,000/10,000 call) bit-exact。subscribe no-op seam を撤去し EditorModel ctor → 0x1800526f0 の manager EventSlot 登録が wasm で動く。
- **functor offset 未初期化 qword コピーを 0 確定化**: clone (0x18005b430/0x18003f7d0) の `mov rcx,[rcx+0x18]` → `xor ecx,ecx` (native image パッチ) と kh_lower の同ブロック store 0 化 (wasm) の対称修正。抜くと invoke rcx ワイルド → SIGSEGV (負律対照 §5.2-1)。
- **module E -O1 採用** (残スコープ 5): -O0/-O1 × `--volatile-ret` の 4 組合せすべて回帰全項目 PASS。wasm 439,208 B → **364,770 B** (83.0%)。
- 回帰: run_all.sh **exit=0** (33 s)・lic_check **70/70**・em_check **ok=52 ng=0**・snapin 6 種 base/lic 200/200。
- 未解決 (起票先付き): emfire (manager slot 起火 0x18010b180) の post-state bit 不一致 (vector-compact の ctrl vtable delete thunk 0x180003360 = 尾 `jmp rax` 未 lift) → 親 CAB-13 に次タスク提案。0x1800f6540 lift・listener [sub+0x1170] 通知検証も未実施 → 親 CAB-13。
- 独立再計算: `python3 scripts/kh11_audit.py` (lift 44 関数 / icall raw 97 サイト (空ブロック 77) / slot map 4,934 スロット完全一致)。

## 11. #249 追記 (ブラウザ分類 lift・ctor 47 vs 46 同定、詳細は `KH249_REPORT.md`)

- 47 ctor = 製品 45 + `HostProxyEditorModel` + `SnapinGroupEditorModel`、product_index 46 = 製品 45 + `core` (KH9 §5-5 の推定を確定)。ブラウザ 0x180ef7fc0 は module F で emcc 通過・status 9 で全エントリ listed/unlocked を実 IR の thunk 実行で確認。

## 12. #710 named import 節 (HeapAlloc shim / 宣言補完) の検証

- 対象: `lift/gen_stubs_sigs.py` (`HEAP_C` / `IMP_SHIM`)・`lic_build.py` (`decl_named_imports`)。snapins 版 `HEAP_C` の同型問題は未修正 (追跡 #1116)。
- 変更点: `kh_heap_alloc` は領域を超える要求で **0 を返す** (旧: `n` を 0xF0000 に切り詰め、末尾超過で先頭へ巻き戻し生存ブロックを上書き)。`decl_named_imports` は引数付き・戻り非 i64・fastcc の呼出を `sys.exit` で停止し、`declare void @llvm.trap()` が無いときも停止する。`defined` は属性付き define (`define internal i64 @Foo(...) #0`) に対応。
- 再現 (emsdk・winpkg 不要、ホスト gcc のみ): `python3 scripts/kh710_check.py` → 終了 0 で全 PASS。

| 検査 | 期待 | 結果 |
|---|---|---|
| decl: 引数なし `call i64 @GetCurrentThreadId()` で `declare i64 @GetCurrentThreadId()` 補完 | 補完 | PASS |
| decl: 引数付き `call i64 @HeapFree(i64 1, i64 2)` | exit (停止) | PASS |
| decl: `call fastcc i64 @HeapFree(i64 1)` | exit (停止) | PASS |
| decl: 属性付き define `define internal i64 @Foo(...) #0` の呼出 | 補完なし・重複なし | PASS |
| decl: `declare void @llvm.trap()` 無し | exit (停止) | PASS |
| heap: 100B + 16B 確保が非 0・16B 整列 | 非 0 / 整列 | PASS |
| heap: 2MB 要求 | 0 | PASS |
| heap: 0xFFFFFFFFFFFFFFF0 要求 | 0 | PASS |
| heap: 0xF0000 要求 (領域内) | 非 0 | PASS |
| heap: 0xF0000 の 2 回目 (領域枯渇) | 0 | PASS |
| heap: 先に確保したブロックの内容 (0xAB 100B) が後続確保後も保持 | 保持 | PASS |

- 上記は HEAD 変更後の `lift/gen_stubs_sigs.py` の `HEAP_C` を、アドレスだけホストバッファへ差し替えて実行したもの (`kh710_check.py`)。
- 回帰確認 (emcc rc・sha256・`kh249_check.mjs` ok=17): **実施済み** (12.1 参照。旧 HEAD を同条件で再ビルドして一致)。
- `product_index.json` (46 plugins) は `work/winpkg/` の生成物 (gitignore)。差分に出ないのは仕様どおり。再生成には `plugins-kilohearts` 素材が要る (`scripts/kh249_product_index.py`)。
- **libc / CRT 名衝突 (レビュー指摘 3・#710)**: `gen_stubs_sigs.py` は body 中の未知の `@Name(` に `abort()` 付きの定義を生成するため、`memcpy`・`strlen`・`sqrt` 等が named import として出ると libc を上書きする。`LIBC_NAMES` (memcpy/memset/strlen/sqrt/malloc/printf 等 33 名) に当たる名前が `used_names` に出たら生成段で `sys.exit` する (`scripts/kh710_check.py` の `libc_clash:*` で検査: memcpy は停止 / GetCurrentThreadId は通過 = PASS)。
  - 実 lift 出力での `used_names` 列挙: **実施済み** (12.2 参照。4 module とも空で、`LIBC_NAMES` との衝突なし)。
- 実行 (HEAD `8e56adc8`): `python3 scripts/kh710_check.py` → `RESULT PASS` (rc=0・PASS 15 / FAIL 0)。

### 12.1 回帰確認 (実測・旧 HEAD `9c1f7c0b` を同条件で再ビルドして比較)

- 素材: `fl-win64` / `plugins-kilohearts` (installer zip → `work/winpkg/HeartCore.core_64`) / `toolchain-emsdk` (`/opt/emsdk`, node 24.19.0) / `toolchain-retdec` (`/opt/retdec`)。
- 旧 HEAD は `git worktree` (detached `9c1f7c0b`) で `winpkg` を複製し、`lic_build.py --module A|B|E|F` を実行。現 HEAD は同じ `lic_build.py` を実行。

| module | 旧 `9c1f7c0b` sha256 | 現 HEAD sha256 | wasm bytes | 判定 |
|---|---|---|---|---|
| A | `411007b8…b6fc` | `411007b8…b6fc` | 26705 | 一致 |
| B | `62182947…f04b` | `62182947…f04b` | 25249 | 一致 |
| E | `0cf066d1…6fed8` | `0cf066d1…6fed8` | 364770 | 一致 |
| F | `7ba79e65…8c7707` | `7ba79e65…8c7707` | 54394 | 一致 |

- 各 module の `lic_build.py` rc は 0。`undefined_imports` は全て `[]`。emcc は全 module で成功 (rc=0)。
- `kh249_check.mjs` (module F): 旧・現とも `kh249_check ok=17 ng=0`、rc=0。
- 全 module の `stubs.c` に `kh_heap_alloc` / `kh_cursor` は出力されず (`grep -c` = 0)、HeapAlloc shim は本 4 module では使われない。したがって `kh_heap_alloc` の失敗値変更は 4 module の wasm には影響しない (sha 一致の理由)。
- sha 表の数値は同じ `lic_build.py` を同条件で 2 HEAD から実行した結果 (旧 HEAD 側は `ws-1084-base` worktree)。

### 12.2 実 lift 出力の `used_names` と `LIBC_NAMES` の突合 (実測)

- 対象: `work/licA|B|E|F/final.ll` (RetDec stage-0 → lower → normalize → stub pass の出力) に対し、`gen_stubs_sigs.py` と同じ式で `used_names` を計算 (define/declare 名と `function_`・`kh_`・`llvm`・`global_var` を除外)。
- 結果: 4 module とも `used_names = []`。`LIBC_NAMES` (memcpy・strlen・sqrt 等) との交差は空。libc / CRT 名の衝突は実 lift 出力では発生しない。
- 注記: 現在の 4 module は named import (HeapAlloc 等) を呼ばない。`used_names` が非空になる入力での経路は `kh710_check.py` の `libc_clash:*` で検査する。

### 12.3 HeapAlloc カーソルの配置修正 (review 指摘 1)

- 指摘: `kh_heap_alloc` のカーソルが `0x04000100` (arena の `operator new` 確保域 = newheap の先頭) に置かれ、`TlsGetValue`/`FlsGetValue` の返却値 `0x04000200` も同域内だった。
- 修正: カーソルを `static u64 kh_cursor` に移す。TLS/FLS の返却値を `KH_TLS` (`0x05200000`、`KH_HEAP_END` 直後の未使用域) にする。
- 検査: `kh710_check.py` に `placement:*` を追加 (TLS 返却値が arena・cave・heap 域外 / カーソルが static / TLS shim が `KH_TLS` を使う) → 全 PASS。
- 影響: 上記 12.1 のとおり、4 module の wasm は変わらない (sha 一致)。
- **define 名の stub 化 (review 指摘 2)**: `used_names` は `define` 行の名前も拾い、同一モジュール内で定義された非 `function_` 関数 (`define internal i64 @LocalHelper(...)` を `function_1` が呼ぶ形) に `abort()` stub を生成していた。修正: `local` (`^define ... @Name(`) を `used_names` から除外。再現 (修正前): `gen_stubs_sigs.py` で `LocalHelper(void)` の stub 出力。修正後: 出力 0 件。検査 `define_not_stubbed` を `kh710_check.py` に追加 (PASS)。

### 12.4 本 run の実測 (HEAD `8e56adc8`・素材 4 種展開・旧 HEAD `9c1f7c0b` 比較)

- 素材: `plugins-kilohearts` は installer zip (取得 60 s) → `payload.dat` (取得 74 s) → `windows.zip` → `work/winpkg/HeartCore.core_64` のみ展開。`toolchain-emsdk` (`/opt/emsdk`)・`toolchain-retdec` (`/opt/retdec`) は既存。`KH_EM_CACHE=$RUNNER_TEMP/emcache`。
- 手順 (順序固定・1 つ終わるごとに本節へ追記):

| 順 | 測定 | 結果 | 時間 |
|---|---|---|---|
| 1 | 旧 HEAD `9c1f7c0b` の module A 再ビルド (比較基準) | sha `411007b8…b6fc`・26,705 B・undefined `[]` | 29.5 s |
| 2 | 現 HEAD `8e56adc8` の `used_names` 突合 (module A/B/E/F、現 HEAD の `LIBC_NAMES` 32 名) | 4 module とも `used_names = []`・衝突 0 | 数秒 |
| 3 | 現 HEAD `lic_build.py --module A` | sha `411007b8…b6fc`・26,705 B (旧と一致) | 11.3 s |
| 4 | 現 HEAD `--module B` | rc=0・sha `62182947…f04b`・25,249 B (旧と一致) | 12 s |
| 5 | 現 HEAD `--module E` | rc=0・sha `0cf066d1…6fed8`・364,770 B (旧と一致) | 13 s |
| 6 | 現 HEAD `--module F` | rc=0・sha `7ba79e65…8c7707`・54,394 B (旧と一致) | 11 s |
| 7 | 現 HEAD `kh249_check.mjs` | rc=0・`kh249_check ok=17 ng=0` | 数秒 |

- emcc rc: A/B/E/F 全て 0。`undefined_imports` は A で `[]`。
- 注: 旧 HEAD `9c1f7c0b` には `LIBC_NAMES` が無い (`b08b431a` で追加) ため、`used_names` 突合は現 HEAD の定義を使った。

### 12.5 ネガコン (宣言補完を無効化) の実測 — 不成立

- 操作: `lic_build.py` の `txt = decl_named_imports(txt)` (137 行) を一時的に無効化し、`--module F` を 1 回ビルド。作業ツリーは測定後に復元 (commit なし)。
- 結果: **rc=0**・`undefined_imports: []`。宣言補完を外しても module F は失敗しなかった。
- 解釈: module F は `used_names` が空 (§12.2) で、そもそも named import を呼ばない。よって本 4 module は宣言補完のネガコンに不適。#710 の本来の失敗 (閉包展開での `@GetCurrentThreadId` 宣言欠落) は、その名前を呼ぶ閉包を含む入力でしか再現しない。
- 未実施・起票先: 閉包展開で named import を呼ぶ入力でのネガコン (#656)。本 run では測定できていないため、受入条件のこの項目は未達のまま。

### 12.6 閉包入力でのネガコン・HeapAlloc 実行 (#1171 実測)

- 対象 HEAD `39ac1852` (`scripts/kh1171_negctrl.py` / `kh1171_heap_exec.sh` / `kh1171_heap_run.mjs`)。素材 `plugins-kilohearts` → Installer zip → payload.dat (`windows.zip/1ccb1df8c8f10745`) → `work/winpkg/HeartCore.core_64` (76,642,304 B)。`KH_EM_CACHE` は `$RUNNER_TEMP/emcache`。
- 入力: `0x180049c40` (288 B・IAT 経由で `GetCurrentThreadId` を呼ぶ・閉包 0)。HeapAlloc 経路: `0x180156e50` (`HeapAlloc` を IAT 経由で呼ぶ)。
- 実測 (`python3 scripts/kh1171_negctrl.py <tag> pos|neg <VA>`):

| 測定 | 結果 |
|---|---|
| POS: 宣言補完あり・`0x180049c40` | rc=0・`undefined_imports` 空・wasm 18,886 B・sha `4cac190e…f174` |
| NEG: 宣言補完なし・`0x180049c40` | **emcc 失敗** (`use of undefined value '@GetCurrentThreadId'`・rc≠0) |
| POS: 宣言補完あり・`0x180156e50` | rc=0・`undefined_imports` 空・`stubs 4` (HeapAlloc/GetProcessHeap shim 生成) |
| HeapAlloc wasm 実行 (`kh1171_heap_run.mjs`) | p1=0x5000010・p2=0x5000080 (16B 整列・HEAP 域内)・100 B 上書き後も保持・2MB 要求=0・0xFFFF..F0 要求=0・0xF0000 初回=非 0・2 回目=0 |
| `kh710_check.py` | RESULT PASS |

- 制約: HeapAlloc の実行は `test_heap(n)` ラッパーから `r8` に引数を入れて呼ぶ (export 経由の直接呼出しは不可)。module 全体 (`function_180156e50`) は未 lift callee `0x180156f40`/`0x180106440` を含むため wasm 上で丸ごと実行しない。

## 13. #4413 kclp native_ref scenario (ctx-fuzz native oracle)

- 対象: `harness/scen_kclp.h` (ACFRegisterPlugin_kclp の 32bit 検索関数 0x180f89cf0 を、経路フラグ .data 0x182989344 を指定して呼ぶ)。偶数 trial = ymm 経路 (flag 0x20)、奇数 trial = scalar 経路 (flag 0x2)。
- 測定 commit: `876bb09f7` (コードを変えた最後の commit)。以後 harness の差分は 0 (`git diff 876bb09f7 HEAD -- tools/targets/kilohearts/license/harness` = 空)。
- 正しいコマンド (引数 5 つ。4 つでは usage で rc=2): `native_ref <HeartCore.core_64> kclp 200 1 <out.bin>`。出力は `work/` 配下に置く。
- ビルド: `cc -O1 -Wall native_ref.c scenarios.c` rc=0 (本 run で再確認)。`native_ref - list` に `kclp` を含む (本 run で確認)。
- 前 run の記録 (測定 commit `876bb09f7`・素材 `plugins-kilohearts` 展開): rc=0・0.017 s・出力 66,146 B・不一致 0 件・ネガコン (比較の向きを反転) で 200 行の不一致・`HeartCore.core_64` sha256 一致 (`d55ce8b4c0ad7ebedf1a4a1f74443a91d255596be887a514e54269ec8751441e`、76,642,304 B)。
- **本 run で未再実行**: `$ARTIFACTS_DIR` (`fl-win64` のみ) に `HeartCore.core_64` が無く、正しいコマンドの再測定ができなかった。上の前 run 値は再確認されていない。再測定は `oc_artifacts: fl-win64 plugins-kilohearts` を付けた run で行う。
- 未確認: ymm 経路 (flag 0x20) に入ったことを示すトレース・分岐カウントは未記録。
- 関数 B (0x180fb6124) は未実装。`modules.F.lift` 追加は未実施 (#4413 の次 run)。
- 経路フラグの wasm 切替: `lic_build.py --module K` (lift 集合は A `0x180f89cf0` のみ・`0x180fb6124` を含む 2 関数) で、`.data` の `0x182989344` / `0x182989340` を setter `kh_set_flag_a/b` から書き換え可能にした (`globals.c` の `const` を外す)。`compare.mjs --path-flags` が trial ごとに `kh_set_flag_a` へ書く (偶数 0x20 / 奇数 0x2、scen_kclp.h と同規則)。
- 突合 (測定 commit: 本 PR の HEAD。素材 `plugins-kilohearts` 展開・`HeartCore.core_64` sha256 `d55ce8b4c0ad7ebe` 一致): `native_ref kclp 200 1` rc=0 → `compare.mjs --path-flags` **200/200 bit-exact (200 calls)**・ネガコン (`--neg-ctrl`) **0/200**・フラグ無し (`compare.mjs` 既定) 200/200。
- 解釈: フラグ切替後も突合が一致し、ネガコンで FAIL するため比較は機能している。ただし `find32` は両経路で同じ結果を返すため、経路の違い自体は突合で検出していない。ymm 経路に入った証拠 (分岐カウント) は未取得。
- wasm: `licK/mod.wasm` 29,276 B・`undefined_imports` 空・`sha256 445ad93b6258bdf3…`。
- 未実施: 関数 B (0x180fb6124) の scenario と突合、`modules.F.lift` 追加、`excluded_i256` 除去、`lic_build --module F`・`kh249_check.mjs` 回帰。
