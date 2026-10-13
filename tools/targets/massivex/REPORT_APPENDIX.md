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
| N6 | 0x184ffcf87 / 0x184ffcfe8 / 0x184ffd03f / 0x184ffd092 / 0x184ffd0d6 / 0x184ffd131 | 'Please (open\|use) Native Access to (re-)activate.' 系 6 件 | 全 pdata 関数の RIP 相対走査で **14 件** (§12.2a)。旧記載の「0 件」は再現しない (原因未調査) |
| N5 | 0x18415f411 | 'MXDemoPopup.qml' (UTF-16LE。QML 資源名。周辺は MX*.qml 列) | RIP 相対 **0 件** (正しい範囲 `[0x18415f411,0x18415f42f)` で §12.2a) |
| N5 | 0x184879407 / 0x1848792b9 / 0x18487941a | QML property 'demoExpired' / 'demoExpiredChanged' / 'subscriptionExpired' | RIP 相対 **0 件** (§12.2a) |
| N3 文言 | 0x185013ca8 (UTF-16) | 'Subscription expired.' | 関数 **0x18010e4e0** から RIP 参照 (1 件) |
| N2 文言 | 0x184ffc425 | 'Your serial number is incorrect. Please run ' | 関数 0x181142160 / 0x181143c00 から RIP 参照 (各 1 件) |

- **訂正**: §6・§11.2 の「N3 'Subscription expired.' 0x18010e4e0」は文字列アドレスではない。0x18010e4e0 は文言 0x185013ca8 を参照する**関数** (`.pdata` 登録済み)。文字列の正しい VA は 0x185013ca8。
- 同 §6 の N5/N6 表の文字列 VA は本節の実測と一致する (文字列の実在は `license/work/mx_strings.json` で確認)。
- 旧版の「N6 直接参照 0 件」は、全関数の RIP 相対走査 (§12.2a) で再現しなかった。原因は未調査。「N5 MXDemoPopup の範囲 `[0x18415f411,0x18415f412)`」は UTF-16 を 1 バイトとして扱った誤りで、正しい範囲は `[0x18415f411,0x18415f42f)`。

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
- 検証 HEAD: `d838c825`。全走査の実測は `d838c825` と同一の `mx_xref_fn.py` (`cbfcff96` で最終化) で行った。`a89d4ea3..d838c825` の差分は本 PR の 3 ファイル (`REPORT.md` §12・`REPORT_APPENDIX.md` §12・`mx_xref_fn.py`) のみで、e2e 対象コード (`mx_lic_stub.py` 等) は変更なし。
- e2e 数値 (`-O0` 5 s / `-O1` 78 s・lift キャッシュ無し / `-O2` 6 s, 11/11 PASS) は作成者の記録 (`b5969e5a` 時点)。本 fix run では `toolchain-retdec` が無く lift を伴う e2e は再測定していない。

### 12.3 未達と起票先

| 未達 | 影響 | 起票先 |
|---|---|---|
| N5 demo UI 抑制 (QML 側の demoExpired / subscriptionExpired / MXDemoPopup 表示経路の特定と差し替え)。N5 の 4 範囲は RIP 相対の参照元 0 件 | 受入条件 1 未達 | #1017 [MX-4] (OPEN) |
| N6 Native Access 誘導文言 6 種の抑制 (N6-1 の読み手 0x180f95e20 の呼び出し元の特定。N6-2〜6 の読み手関数 0x181142370 / 0x181144570 / 0x181142640 / 0x1811453f0 の役割と呼び出し元の特定 → 差し替え点の決定) | 受入条件 2 未達 | #1017 [MX-4] (OPEN) |
| `acpt_verify_mx2.py` の N5/N6 検査は文字列実在のみ | 「抑制済み」の機械検証が無い | #1017 [MX-4] (OPEN) |
| e2e の再測定 (`toolchain-retdec` 素材が必要) | 本節の e2e 数値は作成者の記録のまま | #1183 (素材付き再測定) |
