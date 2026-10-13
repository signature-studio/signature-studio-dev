# REPORT (SHX-T8 / #175) — shimx 序数 import の同定・Crypt ハッシュ・CP932

> 正本: `tools/shimx/REPORT.md` §15 から分割移動した付録 (内容は無変更、§ 番号 15.x は維持)。親: `tools/shimx/REPORT.md`。
> 注記 (分割時): §15.4 の「MT 5 グループ・公開関数 678」は main マージ前の検証起点 `365f7fd` の値。
> main マージ後の head `3bafad0` では MT 6 グループ・公開関数 684 (SEH の `shimx_seh_*` 6 本が増加)。

## 15. SHX-T8 (#175): 序数 import の同定・Crypt ハッシュ・CP932

既知類型との関係 (`docs/DEFECTS.md`): 該当なし (lift/IR 変更なし。shimx 実装のみ)。検証起点 commit: `80c7471` (main)。

**結論**: OTT vst2/vst3 = 147/147・151/151、Serum2 = 238/238 (import カバレッジ, `data/coverage.json` の `covered`/`in_scope`)。
CP932 は MB→WC 全 DBCS 9,604 セルと WC→MB 往復が一致。Crypt は MD5/SHA-1/SHA-256 を実装し公開ベクトルと一致。

### 15.1 序数 → 名前 (根拠: Wine `shell32.spec` / `shlwapi.spec` = Windows の序数表。呼出箇所の引数での裏取りは §15.5 で完了)

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
| `bash tools/shimx/test.sh --quick` (クリーン worktree, 検証起点 HEAD `365f7fd`, n=3) | **3/3 exit 0**, 所要 23.6–24.1 s (load average 0.20–0.65 = 実行直前, 並列なし)。MT 5 グループ / ST PASS / fail-fast 8 / M4 互換 MT・ST PASS / 未実装 0 / 公開関数 678 (本 PR 前 674)。`--quick` は `verify_ott` を省く (フル実行は §15.6) (作業ツリー n=1: 24.3 s) |
| CP932 全 DBCS セル | **9,604 セル**: MB→WC 不一致 **0**、WC→MB→WC 往復不一致 **0** (`test_shord.inc`)。オラクル = Python 標準 codec `cp932` (表の出典と独立実装)。生成表 `src/cp932_tab.c` も同 codec と 11,340 セル全件突合し差 **0** |
| Crypt | RFC 1321 / FIPS 180-4 の公開ベクトル 7 件 + 百万 `a` ×3 アルゴ + 境界長 (55/56/63/64/65 B) ×3 アルゴ全一致。1 バイトずつ流した場合も同値。期待値は Python `hashlib` で再検算 (手書き値との差 0) |
| 序数 | `GetProcAddress` 序数 (shell32 74 / shlwapi 12・219)・lift トークン往復・IEnumFORMATETC / IStream / QISearch の実呼出を `test_link.c` / `test_cbtrans.c` / `test_shord.inc` で確認 |
| ネガティブコントロール (n=11, 全て意図どおり FAIL = exit 1) | SHA-256 定数 1 語 / MD5 回転量 1 つ / SHA-1 K 定数 / CP932 表 1 セル / best-fit 判定除去 / リード範囲 -1 / ord74 登録削除 / ord219→218 / QISearch の AddRef 除去 / Clone の位置引継ぎ除去 / HASHVAL 再確定 |
| import カバレッジ (`data/coverage.json`) | OTT vst2 147/147, vst3 151/151, Serum2 238/238, FreshAir 98/98, FL64.exe 111/111 |

範囲外: 実 PE (OTT/Serum2) を実際にリンク・実行しての import 解決は未実施 (`plugins-*` 素材なしで、coverage は `data/imports.json` の既存スナップショット (import_scan.py 出力) と `shimx` 定義の突合)。
**フル実行の実測 (本 PR 最終 HEAD, `work-m11` / `work-m6-ott` 展開済み)**: 下表 §15.6 参照。以前の「素材が無く SKIP・main 版のまま」の記述は誤りで、本 run では `verify_ott` は SKIP せず実行され、生成物は生成器の出力どおり更新されている。

exports.txt の再生成差分: 並べ替えに加えて **9 本が追加** (削除 0)。`shimx_drag_accepts` `shimx_hdrop_create` `shimx_seh_current_exception` `shimx_seh_depth` `shimx_seh_enter` `shimx_seh_leave` `shimx_seh_set_pad_resolver` `shimx_seh_set_typed_matcher` `shimx_set_notify_hook`。いずれも `src/shell.c` / `src/seh.c` / `src/handles.c` に既に定義があり、main の exports.txt が古かっただけ (生成結果は正しい)。

### 15.5 序数の裏取り (call site 引数) と残件

**裏取り (SHX-T8 再開 run, 2026-10-13)**: 素材 `plugins-ott` (`Install_Xfer_OTT_137.exe` → `$_13_/OTT_x64.dll`) / `plugins-serum2` (`Install_Xfer_Serum2_2.1.5.exe` → `$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3`) を 7z で展開し、IAT の序数スロットを `call *disp(%rip)` で呼ぶ箇所の引数設定を逆アセブルした。

| import | 呼出し箇所 (実 PE) | 引数形の観測 | 同定 (Wine spec と照合) |
|---|---|---|---|
| OTT shell32 #74 | `0x180138f63` (IAT `0x1801e2560`) | `cFmt=1`, `rgfmt`=FORMATETC 1 件 (`cf`=CF_HDROP 系, `tymed`=HGLOBAL), `ppenum`=`lea 0x20(%rsp)` | `SHCreateStdEnumFmtEtc(long ptr ptr)` 一致 |
| Serum2 shlwapi #12 | `0x18017644e` (IAT `0x180fe3070`) | `rcx`=`pbData`, `edx`=`cbData` (`r9d` 経由) を渡し直後に IStream vtable を組む | `SHCreateMemStream(ptr long)` 一致 |
| Serum2 shell32 #190 | `0x180267bef` (IAT `0x180fe2f20`) | `rcx`=`wstr` 相当 (`0x180267410` でパス文字列を埋めた後に呼ぶ) | `ILCreateFromPathW(wstr)` 一致 |
| Serum2 shell32 #155 | `0x180267c55` (IAT `0x180fe2f28`) | `rcx`=直前の PIDL (`test rsi` で非 NULL 時のみ呼ぶ) | `ILFree(ptr)` 一致 |
| Serum2 shlwapi #219 | `0x18094936d` / `0x1809499c1` → thunk `0x180a1b430` → IAT `0x180fe3068` | `QISearch(this, tab, riid, out)` の 4 引数を `rcx..r9` に配置。`tab`=`0x180f96370` が `QITAB` 2 エントリ (`piid` 有り, offset 0 / 8) | `QISearch(ptr ptr ptr ptr)` 一致 |
| Serum2 d2d1 #1 | `0x1801668da` (thunk `0x180a1b150`) | `(rcx=1, rdx=riid, r8=0, r9=out)` | 引数形は `D2D1CreateFactory(long ptr ptr ptr)` と一致。ただし同定は tools/gui 担当で保留 (`d2d1.spec` は名前のみで序数を明示しない) |

以上により、shell32 / shlwapi の 5 件は Wine spec と呼出し箇所の引数形が一致した。d2d1 #1 は引数形が一致するが、同定は tools/gui 担当で保留する (`ORD_KNOWN` には入れない)。`ORD_KNOWN` / `shord.c` の同定に変更は無い。裏取り用の逆アセ (`objdump -d`) は `work/` 配下 (commit しない)。

**残件**: d2d1 ord1 (tools/gui 担当, 分母外)。`inventory.md` / `BACKLOG.md` の「名前解決不能」表記は、この保留と一致している。

### 15.6 フル `test.sh` の実測 (fix run, 最終 HEAD)

| 項目 | 実測 |
|---|---|
| コマンド | `bash tools/shimx/test.sh` (`--quick` なし, 素材 `work-m11` / `work-m6-ott` 展開済み, `plugins-*` は未使用) |
| 検証 HEAD | `14e4eb35` (生成器修正 `270a32d7` + 生成物・REPORT 修正 `14e4eb35`) |
| 結果 | **exit 0**, real **52.9 s** (user 41.1 s / sys 11.9 s)。直前の HEAD `270a32d7` での 1 回目は exit 0, 55.8 s |
| 再生成後の差分 | `git status` 空 (再生成物は commit 済みの内容と一致) |
| MT / ST / M4 | MT PASS (7 グループ) / ST PASS / M4 テスト MT・ST PASS |
| 署名 | verify_sig m11 / m11_3 / ott: signature mismatch = 0。sig_test (a)〜(h) ALL PASS |
| R6 | 構造体展開スタブ + 重複 declare 正規化 OK |
| verify_ott | baseline 47 → shimx 解決 **24 種** (残 API 0, 新規 undefined 0)。t1 出力 SHA baseline = shimx = `b5a91b9b2ee8da1e` (一致, 512 行) |
| 完了 | 7/7 完了: shimx 687 公開関数 × MT/ST × M4 互換 × fail-fast 全 PASS |
| 生成物の差分 (main 比較) | `data/coverage.json`: `shimx_hooks` 59 → 68 (main 版の値が古かった)。`m11_closure` / `ott_api_resolved` (24) は main と同値 |
| 生成器修正の効果 | 再生成で `inventory.md` / `BACKLOG.md` の見出し注記・正本注記・SHX-T9 節 (`scripts/backlog_tail.md` から連結) は消えない。`exports.txt` も HEAD と一致 |

検証ログ: `work/` 配下 (commit しない)。
