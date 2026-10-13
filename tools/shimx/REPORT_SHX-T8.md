# REPORT (SHX-T8 / #175) — shimx 序数 import の同定・Crypt ハッシュ・CP932

> 正本: `tools/shimx/REPORT.md` §15 から分割移動した付録 (内容は無変更、§ 番号 15.x は維持)。親: `tools/shimx/REPORT.md`。
> 注記 (分割時): §15.4 の「MT 5 グループ・公開関数 678」は main マージ前の検証起点 `365f7fd` の値。
> main マージ後の head `3bafad0` では MT 6 グループ・公開関数 684 (SEH の `shimx_seh_*` 6 本が増加)。

## 15. SHX-T8 (#175): 序数 import の同定・Crypt ハッシュ・CP932

既知類型との関係 (`docs/DEFECTS.md`): 該当なし (lift/IR 変更なし。shimx 実装のみ)。検証起点 commit: `80c7471` (main)。

**結論**: OTT vst2/vst3 = 147/147・151/151、Serum2 = 238/238 (import カバレッジ, `data/coverage.json` の `covered`/`in_scope`)。
CP932 は MB→WC 全 DBCS 9,604 セルと WC→MB 往復が一致。Crypt は MD5/SHA-1/SHA-256 を実装し公開ベクトルと一致。

### 15.1 序数 → 名前 (根拠: Wine `shell32.spec` / `shlwapi.spec` = Windows の序数表。呼出箇所の引数での裏取りは §15.5)

| import | 同定 | 実装 | 備考 |
|---|---|---|---|
| shell32 #74 (OTT) | `SHCreateStdEnumFmtEtc(UINT, const FORMATETC*, IEnumFORMATETC**)` | `src/shord.c` | 深いコピーの IEnumFORMATETC (Next/Skip/Reset/Clone) |
| shlwapi #12 (Serum2) | `SHCreateMemStream(const BYTE*, UINT)` | `src/shord.c` | データをコピーした IStream (ole.c の HGLOBAL ストリームを再利用) |
| shlwapi #219 (Serum2) | `QISearch(void*, const QITAB*, REFIID, void**)` | `src/shord.c` | QITAB = {piid, offset} 16B (Win64)。一致オブジェクトを AddRef |
| shell32 #155 / #190 (Serum2) | `ILFree` / `ILCreateFromPathW` | R3 で実装済み | 本チケットで集計側 (`ORD_KNOWN`) に反映しカバー扱い (`K` 状態) |

登録先: `module.c` `shx_ordtable` (shlwapi を追加) / `cbtrans.c` `g_lifttab` (13 → 16 本。dll 名前空間を shell32/kernel32/shlwapi の 3 値化。shlwapi #16 が shell32 #16 のトークンを返さないことをテスト)。

### 15.2 Crypt (`src/crypt.c`)

`CryptAcquireContextA` / `CryptReleaseContext` / `CryptCreateHash` / `CryptHashData` / `CryptGetHashParam` (HP_ALGID/HP_HASHSIZE/HP_HASHVAL) / `CryptDestroyHash`。
CALG_MD5 / CALG_SHA1 / CALG_SHA_256。鍵付き (`key != 0`)・他アルゴリズムは NTE_BAD_KEY / NTE_BAD_ALGID。ハンドルは 256 スロット + 世代 (解放済みの再利用を NTE_BAD_HASH で検出)。
サイズ問合せ (`pbData == NULL`) は確定しない。確定後の追記は NTE_BAD_HASH_STATE。旧スタブ (reg.c, 常時失敗) は削除。

### 15.3 CP932 (`src/cp932_tab.c` 自動生成 + `str.c`)

表の出典 = Microsoft `WindowsBestFit/bestfit932.txt` (Unicode Consortium 配布)。`scripts/gen_cp932.py` が生成 (生成物 192 KB を commit, 入力は `work/` に取得)。
MultiByteToWideChar / WideCharToMultiByte / GetCPInfo(Ex) / IsValidCodePage / IsDBCSLeadByteEx / CharNextExA が 932 (および `shimx_set_acp(932)` 後の CP_ACP) で動作。
無効列 (孤立リード・無効トレイル・未割当) は U+30FB (CPINFO の UnicodeDefaultChar) か `MB_ERR_INVALID_CHARS` で ERROR_NO_UNICODE_TRANSLATION、無効トレイルは 1 バイトとして再解釈。
`WC_NO_BEST_FIT_CHARS` は往復一致する文字のみ変換。

### 15.4 検証 (2026-10-13 実測, GitHub Actions runner, emcc 6.0.12 / node 22.23.3)

| 検証 | 結果 |
|---|---|
| `bash tools/shimx/test.sh --quick` (クリーン worktree, 検証起点 HEAD `365f7fd`, n=3) | **3/3 exit 0**, 所要 23.6–24.1 s (load average 0.20–0.65 = 実行直前, 並列なし)。MT 5 グループ / ST PASS / fail-fast 8 / M4 互換 MT・ST PASS / 未実装 0 / 公開関数 678 (本 PR 前 674)。`--quick` なしは `verify_ott` が素材なしで SKIP のため同等 (作業ツリー n=1: 24.3 s) |
| CP932 全 DBCS セル | **9,604 セル**: MB→WC 不一致 **0**、WC→MB→WC 往復不一致 **0** (`test_shord.inc`)。オラクル = Python 標準 codec `cp932` (表の出典と独立実装)。生成表 `src/cp932_tab.c` も同 codec と 11,340 セル全件突合し差 **0** |
| Crypt | RFC 1321 / FIPS 180-4 の公開ベクトル 7 件 + 百万 `a` ×3 アルゴ + 境界長 (55/56/63/64/65 B) ×3 アルゴ全一致。1 バイトずつ流した場合も同値。期待値は Python `hashlib` で再検算 (手書き値との差 0) |
| 序数 | `GetProcAddress` 序数 (shell32 74 / shlwapi 12・219)・lift トークン往復・IEnumFORMATETC / IStream / QISearch の実呼出を `test_link.c` / `test_cbtrans.c` / `test_shord.inc` で確認 |
| ネガティブコントロール (n=11, 全て意図どおり FAIL = exit 1) | SHA-256 定数 1 語 / MD5 回転量 1 つ / SHA-1 K 定数 / CP932 表 1 セル / best-fit 判定除去 / リード範囲 -1 / ord74 登録削除 / ord219→218 / QISearch の AddRef 除去 / Clone の位置引継ぎ除去 / HASHVAL 再確定 |
| import カバレッジ (`data/coverage.json`) | OTT vst2 147/147, vst3 151/151, Serum2 238/238, FreshAir 98/98, FL64.exe 111/111 |

範囲外: 実 PE (OTT/Serum2) を実際にリンク・実行しての import 解決は未実施 (`plugins-*` 素材なしで、coverage は `data/imports.json` の既存スナップショット (import_scan.py 出力) と `shimx` 定義の突合)。
`verify_ott` / M11 closure 突合は `work-m11` / `work-m6-ott` が無く SKIP (§13 と同じ)。このため `test.sh` が再生成した `BACKLOG.md` / `inventory.md` / `data/inventory.csv` は M11・OTT 列が空になり劣化するので **main 版のまま (未更新)** にした。`data/coverage.json` は生成器 (`gen_inventory.py`) の出力のうち `plugins` / `shimx_*` / `ordinal` のみ反映し、`m11_closure` / `ott_api_resolved` は main 版を保持。
結果として `inventory.md` / `BACKLOG.md` は「ord74 等が未解決」と古いままで `coverage.json` と食い違う → 15.5 の未解決に計上 (素材 `work-m11 work-m6-ott` 付きで `bash tools/shimx/test.sh` を再実行すれば生成器が全て更新する。生成器側は本 PR で修正済み)。

### 15.5 序数の裏取りの限界と未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 序数 → 名前は Wine の `.spec` (Windows の序数表と同一規約) で同定したが、**呼出箇所の引数での裏取り (OTT/Serum2 の call site 逆アセ) は未実施**。素材 `plugins-ott` / `plugins-serum2` が本 run に無い | 序数表が実 Windows 10/11 と食い違う場合、誤実装が silent に通る | #175 にコメント (再起動時 `oc_artifacts: fl-win64 plugins-ott plugins-serum2`)。新規子チケット案: `[SHX-T8b] 序数 import 5 件の call site 引数裏取り` |
| d2d1 ord1 は同定対象外 (d2d1 = tools/gui 担当帯。分母 238 にも含まれない)。Wine `d2d1.spec` は序数を明示せず名前のみ列挙するため、序数 1 の根拠が取れていない | Serum2 GUI 経路のみ | tools/gui 担当 (issue #175 にコメントで引継ぎ) |
| shlwapi #219 を `QISearch` とした点は Wine の `-import` 属性 (`QISearch(ptr ptr ptr ptr)`) に依拠 | 同上 | 上と同じ |
