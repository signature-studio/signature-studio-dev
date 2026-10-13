# Massive X 1.7.1 REPORT 付録 (#830 MX2-3)

本体 `REPORT.md` §12 の全文 (250 行上限のため分割移動)。

## 12. MX2-3 (N5 / N6) 実測 — 2026-10-13 (#830)

- 結論: N6-1 の読み手関数 0x180f95e20 を確定 (§12.2a)。N6-2〜6 と N5 の読み手は未確定。現行 IR pass の差し替え点はまだ決められない。e2e は 3 レベルとも 11/11 PASS (`d7cf3c77` の記録)。
- 詳細・実測表・訂正: [REPORT_APPENDIX.md §12](REPORT_APPENDIX.md)。未達の起票先は同節 §12.3。


### 12.1 検証状況 (実測 HEAD = `d7cf3c77`)

- 素材: `plugins-massivex` / `toolchain-retdec` / `toolchain-emsdk` を `$HOME/artifacts` から展開 (`[RETDEC]`・`[EMSDK]` (docs/REFERENCES.md) として既存)。`mx_lic_stub.py` は本 run で未変更。
- 測定は `d7cf3c77` の worktree (`ws-830`) で実施。`work/` と `license/work/` は main 側の検証スナップショットを複製して使用 (lift キャッシュ込み)。

| 項目 (HEAD `d7cf3c77`) | 結果 | 所要 |
|---|---|---|
| license e2e `MX_OPT=-O0` | exit 0 / 11/11 PASS | 4 s |
| license e2e `MX_OPT=-O1` (既定) | exit 0 / 11/11 PASS | 5 s |
| license e2e `MX_OPT=-O2` | exit 0 / 11/11 PASS | 5 s |

- 所要はいずれも lift キャッシュ有りの値。キャッシュ無し (`7e8445b9` で実測) は `-O1` 78 s。

### 12.2 N5 / N6 の静的確認 (文字列・xref 実測)

| 対象 | VA | 文字列 | 直接参照 (RIP / 絶対ポインタ / RVA32) |
|---|---|---|---|
| N6 | 0x184ffcf87 | 'Please open Native Access to re-activate.' | abs64 0 / RVA32 0 / RIP は §12.2a 参照 |
| N6 | 0x184ffcfe8 | 'Please use Native Access to re-activate.' | abs64 0 / RVA32 0 / RIP は §12.2a 参照 |
| N6 | 0x184ffd03f | 'Please use Native Access to re-activate.' | abs64 0 / **RVA32 1** (raw 0x3c8af47・未分類。下記) / RIP は §12.2a 参照 |
| N6 | 0x184ffd092 | 'Please use Native Access to re-activate.' | abs64 0 / RVA32 0 / RIP は §12.2a 参照 |
| N6 | 0x184ffd0d6 | 'Please use Native Access to re-activate.' | abs64 0 / RVA32 0 / RIP は §12.2a 参照 |
| N6 | 0x184ffd131 | 'Please use Native Access to activate.' | abs64 0 / RVA32 0 / RIP は §12.2a 参照 |
| N6 候補 (表外) | 0x184ffdb55 | 'Native Access can't be found. You will be forwarded to the download page.' | abs64 0 / RVA32 0 / RIP 未測定 |
| N5 | 0x18415f411 | 'MXDemoPopup.qml' (UTF-16。QML 資源名の列に並ぶ) | abs64 0 / RVA32 0 / RIP 0 件 (§12.2a・範囲 `[0x18415f411,0x18415f42f)`) |
| N5 | 0x184879407 | QML property 'demoExpired' | abs64 0 / RVA32 0 / RIP 0 件 (§12.2a) |
| N5 | 0x1848792b9 | QML property 'demoExpiredChanged' (ASCII。'demoExpired' の探索でも同 VA にヒット) | abs64 0 / RVA32 0 / RIP 0 件 (§12.2a) |
| N5 | 0x18487941a | QML property 'subscriptionExpired' | abs64 0 / RVA32 0 / RIP 0 件 (§12.2a) |

| N3 文言 | 0x185013ca8 (UTF-16) | 'Subscription expired.' | 関数 **0x18010e4e0** から RIP 参照 (1 件) |
| N2 文言 | 0x184ffc425 | 'Your serial number is incorrect. Please run ' | 関数 0x181142160 / 0x181143c00 から RIP 参照 (各 1 件) |

- **訂正**: §6・§11.2 の「N3 'Subscription expired.' 0x18010e4e0」は文字列アドレスではない。0x18010e4e0 は文言 0x185013ca8 を参照する**関数** (`.pdata` 登録済み)。文字列の正しい VA は 0x185013ca8。
- §6 の N5/N6 表の文字列 VA との一致: **未確認**。今回 probe が `.rdata` で実在を確認したのは上表の VA (N6 6 件・N5 4 件) と表外の 0x184ffdb55 だけで、`license/work/mx_strings.json` との照合は行っていない。
- 旧版の「N6 直接参照 0 件」は、全関数の RIP 相対走査 (§12.2a) で再現しなかった。原因は未調査。「N5 MXDemoPopup の範囲 `[0x18415f411,0x18415f412)`」は UTF-16 を 1 バイトとして扱った誤りで、正しい範囲は `[0x18415f411,0x18415f42f)`。
- 0x184ffd03f の 4B RVA32 ヒット (raw 0x3c8af47) は `.rdata` 内で、同じ 5 バイト周期の 4B 値列に含まれる。参照元の関数・表の種類は未特定のため、「参照 1 件」とも「参照 0 件」とも断定しない (§12.4)。
- 旧 refscan の VA 一覧は誤りで、`0x184ffd092` / `0x184ffd0d6` / `0x184ffd131` と demoExpired 系 (`0x184879407`) は**旧 refscan では未検査**だった。上表の「0 件」は今回の新 refscan (`7a39dea0` 以降) での測定値のみを指す。


### 12.2a 読み手の追跡 (スクリプト `scripts/mx_xref_fn.py --all`・#1017)

- 素材: `plugins-massivex` (`Native Instruments Massive X v1.7.1.exe`) を本 run で `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py` で抽出。`work/extracted/VST3/Massive X.vst3` = 95,356,824 B / md5 `622993e7…` (PR 本文と一致)。
- 手順: `.pdata` の全関数 (`begin≠0` かつ `end>begin` の 187,061 件) を capstone で線形逆アセンブルし、RIP 相対メモリオペランドの参照先が範囲 `[lo,hi)` に入るものを列挙。ASCII 範囲は NUL 区切り、N5 `MXDemoPopup.qml` は UTF-16LE の既知長 (30 B)。
- 注: 本走査は **RIP 相対のみ**。絶対 8B・RVA32 の参照は走査していない。
- 実行時間: `--all` 2 min 25 s (`cbfcff96` の内容で実行)。

| 範囲 | `[lo,hi)` | 参照元 (関数 @ 命令 VA) |
|---|---|---|
| N6-1 | `[0x184ffcf6c,0x184ffcfb0)` | 0x180f95e20 @ 0x180f95f03 / 0x180f95f0d / 0x180f95f18 / 0x180f95f23 (movups 4 件) |
| N6-2 | `[0x184ffcfb1,0x184ffd010)` | 0x181142370 @ 0x1811424a9 |
| N6-3 | `[0x184ffd011,0x184ffd067)` | 0x181144570 @ 0x181144699 |
| N6-4 | `[0x184ffd068,0x184ffd0ba)` | 0x181142370 @ 0x181142426 / 0x181144570 @ 0x1811446c2, 0x18114472f, 0x181144796 / 0x1811453f0 @ 0x181145433 |
| N6-5 | `[0x184ffd0bb,0x184ffd0fe)` | 0x181144570 @ 0x18114498b |
| N6-6 | `[0x184ffd0ff,0x184ffd156)` | 0x181142640 @ 0x1811426b2 |
| N5 MXDemoPopup.qml | `[0x18415f411,0x18415f42f)` | 0 件 |
| N5 demoExpired | `[0x184879407,0x184879412)` | 0 件 |
| N5 demoExpiredChanged | `[0x1848792b9,0x1848792cb)` | 0 件 |
| N5 subscriptionExpired | `[0x18487941a,0x18487942d)` | 0 件 |

- **N6-1 の読み手 (確定)**: 関数 **0x180f95e20** (pdata `[0x180f95e20,0x180f960bf)`) は N6-1 `[0x184ffcf6c,0x184ffcfb0)` のみを読む (`movups` 4 件)。N6 の他 5 範囲は別関数 (上表) で、この関数は読まない。
  - 呼び出し元は未確定。E8 直接呼び出し 0 件は前版の記録 (本走査は呼び出し元を集計していない)。間接呼び出し経由と推定 [推]。
- **N6-2〜6 の読み手 (未確定の役割・呼び出し元)**: 関数 0x181142370 / 0x181144570 / 0x181142640 / 0x1811453f0 が読む。役割と呼び出し元は本節の対象外 (#1017 で扱う)。
- **N5 の読み手 (未特定)**: 4 範囲とも RIP 相対参照 0 件。前版の rel32 候補 (0x1834606c4 / 0x182d0841f) は RIP 相対の走査対象外で、未確定のまま。
- 検証 HEAD: `b83223e6` (main 取り込み後)。全走査は `mx_xref_fn.py` (`cbfcff96` で最終化) を `b83223e6` で実行した。`d838c825..b83223e6` の差分は main 取り込み (`ea88196e`) と massivex の調査スクリプト・REPORT のみで、e2e 対象コード (`license/e2e.sh`・`scripts/mx_lic_stub.py`・`tools/liftlib/liftlib/passes/base.py`) は `b5969e5a` から変更なし (`git diff --quiet b5969e5a b83223e6 -- <3 ファイル>` が 0)。main 取り込みで変わった `liftlib` の iargs・fp_bind・l1_restore は e2e.sh から呼ばれない。
- e2e 数値 (`-O0` 5 s / `-O1` 78 s・lift キャッシュ無し / `-O2` 6 s, 11/11 PASS) は作成者の記録 (`b5969e5a` 時点)。本 fix run では `toolchain-retdec` が無く lift を伴う e2e は再測定していない。

### 12.3 未達と起票先

| 未達 | 影響 | 起票先 |
|---|---|---|
| N5 demo UI 抑制 (QML 側の demoExpired / subscriptionExpired / MXDemoPopup 表示経路の特定と差し替え)。N5 の 4 範囲は RIP 相対の参照元 0 件 | 受入条件 1 未達 | #1017 [MX-4] (OPEN) |
| N6 Native Access 誘導文言 6 種の抑制 (N6-1 の読み手 0x180f95e20 の呼び出し元の特定。N6-2〜6 の読み手関数 0x181142370 / 0x181144570 / 0x181142640 / 0x1811453f0 の役割と呼び出し元の特定 → 差し替え点の決定) | 受入条件 2 未達 | #1017 [MX-4] (OPEN) |
| `acpt_verify_mx2.py` の N5/N6 検査は文字列実在のみ | 「抑制済み」の機械検証が無い | #1017 [MX-4] (OPEN) |
| e2e の再測定 (`toolchain-retdec` 素材が必要) | 本節の e2e 数値は作成者の記録のまま | #1280 (素材付き再測定・`[MX-7]`) |

### 12.4 #1017 の再確認 (main 側の素材付き実測。本 PR の HEAD `b83223e6` でも同一スクリプトで再実行済み)

- 注: 以下は main 側で `c2d47fda` 時に取った記録。本 PR の検証 HEAD `b83223e6` での再実行結果は PR 本文の「main 取り込み」節に記載。

- **素材**: `plugins-massivex` (`$ARTIFACTS_DIR/plugins-massivex.tar.zst`) を `$RUNNER_TEMP/mx` に展開 → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work key` で `work/extracted/VST3/Massive X.vst3` (95,356,824 B) を生成。md5 `622993e76565f49c094063a2b717d6ca` は REPORT.md §11.1 (2026-10-13 の記録) の値と一致。
  - 注: extract の 16B checksum は 125/125 不一致 (REPORT.md §1・§8 と同じ既知事象)。展開物の同一性は md5 の一致で確認した。
- **実行** (いずれも exit 0):
  - `python3 license/scripts/mx_n5n6_probe.py "work/extracted/VST3/Massive X.vst3"` (4.7 s)
  - `python3 license/scripts/mx_n5n6_refscan.py "work/extracted/VST3/Massive X.vst3"` (1.4 s)
- **probe の抜粋**: `Native Access` を含む ASCII 文字列は 8 件 (N6 の表 6 件 + 表外の `0x184ffc452` "Native Access to enter the correct serial number." と `0x184ffdb55` "Native Access can't be found. ...")。UTF-16LE は 1 件 (`0x18500c4d2`、プリセット パス内の製品名で誘導文言ではない)。いずれも `.rdata` 内 (raw 0x4ffaa52 = VA 0x184ffc452 〜 raw 0x4ffc155 = VA 0x184ffdb55)。
- **refscan の抜粋**:
  - `N6 0x184ffd03f: abs64=0 rva32=1` / `rva32 raw=0x3c8af47` (`.rdata` 内)。他の 9 VA は abs64 0 / rva32 0。
  - この 1 件は `0x04ffd03f` を含む 5 バイト周期の 4B 値列 (`0x04ffd04f` 等が連続) の一部。ポインタ表か別構造かは未特定のため、「参照」とは判定しない。
- **N5 名 (probe)**: `MXDemoPopup.qml` は UTF-16LE で 1 hit (`0x18415f411`、QML 資源名の列)。`demoExpired` ASCII 2 hit (`0x184879407` と、`demoExpiredChanged` の中 `0x1848792b9`)、`demoExpiredChanged` ASCII 1 hit、`subscriptionExpired` ASCII 1 hit。いずれも QML プロパティ名の並び (`MXFrameEvents::FramePage...` 等) に混在。
- **判定**: 上記の 1 件は未分類。N5/N6 の差し替え点は依然として未特定。`mx_lic_stub.py` は変更しない。
- **旧 refscan の誤り (前回 `2f235a0a`/`8d971da0` の記録)**: VA 一覧に `demoExpired` と `demoExpiredChanged` の重複、N6 3 件の欠落があった。そのため前回の「全 7 VA で 0 件」は 10 VA のうち 6 種類しか見ていない。今回の新 refscan は 10 VA 全件を測定した。
- **未検証として残るもの**: 前回記述の「テーブル基準 (文字列 index) 経由の参照」の有無、moc / qrc 系の相対オフセット表の確認 (RIP 参照は未測定)。これは #1017 で扱う。
- **結論 (変更なし)**: 読み手は (a) moc / qrc 系の相対オフセット表、(b) 文字列 index 経由 (テーブル基準の 4B 相対差分)、のいずれかと推定 [推]。前回の RVA32 検索はテーブル基準の差分を見ないため、「参照 0 件」は (a)(b) を除外していない。
- 差し替え点は未特定のため、`mx_lic_stub.py` は変更しない。e2e は本 run では再実行しない (コード変更なし)。次の一手は #1017 で (b) のテーブル基準を総当たりで確かめる。

### 12.5 N6 読み手 0x180f95e20 の呼び出し元探索 (2026-10-13 run・#830)
- 素材: `plugins-massivex` を `license/work/` に展開 → `parse_setup_headers.py` → `extract_massivex.py <exe> work key`。`Massive X.vst3` md5 `622993e76565f49c094063a2b717d6ca` (95,356,824 B) で REPORT §11.1 と一致。
- 読み手関数 `0x180f95e20` (pdata 範囲 `[0x180f95e20,0x180f960bf)`) への参照を次の 3 系統で走査:
  - E8 (call) / E9 (jmp) の rel32 一致: 0 件
  - 絶対 8B 一致: 0 件
  - RVA32 (LE 4B) 一致: 2 件 (raw `0x54a23f8` / `0x57e9d24`)。pefile で所属を確認すると `.pdata` (RVA `0x5fc0ff8`) と `.xdata` (RVA `0x630d324`) で、いずれも unwind/範囲表の内部。コード側の呼び出し元ではないと判定 [推]。
- 判定: N6 読み手の呼び出し元は直接参照では見つからない。間接呼び出し (関数ポインタ表・vtable 経由) か、テーブル基準の相対参照の可能性が残る。N5 の読み手は本節でも未特定。
- 結論: 差し替え点は依然として未特定。`mx_lic_stub.py` の N5/N6 ルールは追加しない (根拠なしに br_force/store を入れると silent miscompile になるため)。#1017 で間接参照の総当たりを行う。

### 12.6 N6 読み手の直接呼び出し元 (#1017 run・再実測)
- 素材: `plugins-massivex` を `tools/targets/massivex/license/work/` に展開 → `scripts/parse_setup_headers.py <exe> work` → `scripts/extract_massivex.py <exe> work key` (`work/` は tools 直下)。`Massive X.vst3` md5 `622993e76565f49c094063a2b717d6ca` (95,356,824 B) で §11.1 と一致。抽出時の 16B checksum 125/125 不一致は §1・§8 の既知事象。
- 測定 HEAD: `a893d1f2` (origin/main) + 本 commit の `license/scripts/mx_callers_probe.py` (lift コードは未変更)。
- `scripts/mx_xref_fn.py --all` (1 分 52 秒・exit 0): N6-1 4 件 / N6-2 1 件 / N6-3 1 件 / N6-4 5 件 / N6-5 1 件 / N6-6 1 件 (§12.2a と一致)。N5 の 4 範囲は 0 件 (一致)。
- `scripts/mx_callers_probe.py` (0.7 秒・exit 0): 読み手 5 関数 (0x180f95e20 / 0x181142370 / 0x181144570 / 0x181142640 / 0x1811453f0) への E8 call / E9 jmp は **いずれも 0 件**。
- 判定: 読み手の呼び出し元は直接 call/jmp・RIP 参照・絶対 8B では見つからない。間接呼び出し (vtable / 関数ポインタ表) か、文字列 index 経由のテーブル参照の可能性が残る。N5 の読み手は未特定。
- 次の一手 (子 issue で扱う): vtable / 関数ポインタ表の走査 (`.rdata` 内の 8B 値 = 読み手 VA) と、N5 の QML プロパティ名テーブルの走査。
