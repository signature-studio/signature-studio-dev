# Massive X 1.7.1 REPORT 付録 (#830 MX2-3)

本体 `REPORT.md` §12 の全文 (250 行上限のため分割移動)。

## 12. MX2-3 (N5 / N6) 実測 — 2026-10-13 (#830)

- 結論: N5/N6 は現行 IR pass の差し替え点を指定できない (文字列に参照元が無い)。e2e は 3 レベルとも 11/11 PASS (`d7cf3c77`)。
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
| N6 | 0x184ffcf87 | 'Please open Native Access to re-activate.' | abs64 0 / RVA32 0 / RIP 未測定 |
| N6 | 0x184ffcfe8 | 'Please use Native Access to re-activate.' | abs64 0 / RVA32 0 / RIP 未測定 |
| N6 | 0x184ffd03f | 'Please use Native Access to re-activate.' | abs64 0 / **RVA32 1** (raw 0x3c8af47・未分類。下記) / RIP 未測定 |
| N6 | 0x184ffd092 | 'Please use Native Access to re-activate.' | abs64 0 / RVA32 0 / RIP 未測定 |
| N6 | 0x184ffd0d6 | 'Please use Native Access to re-activate.' | abs64 0 / RVA32 0 / RIP 未測定 |
| N6 | 0x184ffd131 | 'Please use Native Access to activate.' | abs64 0 / RVA32 0 / RIP 未測定 |
| N6 候補 (表外) | 0x184ffdb55 | 'Native Access can't be found. You will be forwarded to the download page.' | abs64 0 / RVA32 0 / RIP 未測定 |
| N5 | 0x18415f411 | 'MXDemoPopup.qml' (UTF-16。QML 資源名の列に並ぶ) | abs64 0 / RVA32 0 / RIP 未測定 |
| N5 | 0x184879407 | QML property 'demoExpired' | abs64 0 / RVA32 0 / RIP 未測定 |
| N5 | 0x1848792b9 | QML property 'demoExpiredChanged' (ASCII。'demoExpired' の探索でも同 VA にヒット) | abs64 0 / RVA32 0 / RIP 未測定 |
| N5 | 0x18487941a | QML property 'subscriptionExpired' | abs64 0 / RVA32 0 / RIP 未測定 |
| N3 文言 | 0x185013ca8 (UTF-16) | 'Subscription expired.' | 関数 **0x18010e4e0** から RIP 参照 (1 件) |
| N2 文言 | 0x184ffc425 | 'Your serial number is incorrect. Please run ' | 関数 0x181142160 / 0x181143c00 から RIP 参照 (各 1 件) |

- **訂正**: §6・§11.2 の「N3 'Subscription expired.' 0x18010e4e0」は文字列アドレスではない。0x18010e4e0 は文言 0x185013ca8 を参照する**関数** (`.pdata` 登録済み)。文字列の正しい VA は 0x185013ca8。
- §6 の N5/N6 表の文字列 VA との一致: **未確認**。今回 probe が `.rdata` で実在を確認したのは上表の VA (N6 6 件・N5 4 件) と表外の 0x184ffdb55 だけで、`license/work/mx_strings.json` との照合は行っていない。
- 0x184ffd03f の 4B RVA32 ヒット (raw 0x3c8af47) は `.rdata` 内で、同じ 5 バイト周期の 4B 値列に含まれる。参照元の関数・表の種類は未特定のため、「参照 1 件」とも「参照 0 件」とも断定しない (§12.4)。
- 旧 refscan の VA 一覧は誤りで、`0x184ffd092` / `0x184ffd0d6` / `0x184ffd131` と demoExpired 系 (`0x184879407`) は**旧 refscan では未検査**だった。上表の「0 件」は今回の新 refscan (`7a39dea0` 以降) での測定値のみを指す。

- 参照走査は `license/work/cg.pkl` の `rip` 表 (RVA キー) と、`.rdata`/`.data`/`.pdata`/`.xdata` 全体の 8B・4B 絶対値検索による。
- N6・N5 の文字列は `.rdata` の一般文字列プール内に並び、周辺は他の UI 文言・QML 資源名と混在する。**ネイティブ関数からの参照は見つからなかった**。QML ランタイム側 (Qt) が読む経路と推定 [推]。
- よって現行の IR pass (`mx_lic_stub.py`, 差し替え点は関数の分岐・store) では N5/N6 の差し替え点を指定できない。`acpt_verify_mx2.py` の N5/N6 項目は文字列の実在確認のみで、差し替え点ではない。

### 12.3 未達と起票先

| 未達 | 影響 | 起票先 |
|---|---|---|
| N5 demo UI 抑制 (QML 側の demoExpired / subscriptionExpired / MXDemoPopup 表示経路の特定と差し替え) | 受入条件 1 未達 | #1017 [MX-4] (OPEN) |
| N6 Native Access 誘導文言 6 種の抑制 (参照元の特定が先) | 受入条件 2 未達 | #1017 [MX-4] (OPEN) |
| `acpt_verify_mx2.py` の N5/N6 検査は文字列実在のみ | 「抑制済み」の機械検証が無い | #1017 [MX-4] (OPEN) |

### 12.4 #1017 の再確認 (HEAD = `7a39dea0` の素材付き実測)

- **素材**: `plugins-massivex` (`$ARTIFACTS_DIR/plugins-massivex.tar.zst`) を `$RUNNER_TEMP/mx` に展開 → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work key` で `work/extracted/VST3/Massive X.vst3` (95,356,824 B) を生成。md5 `622993e76565f49c094063a2b717d6ca` は REPORT.md §11.1 (2026-10-13 の記録) の値と一致。
  - 注: extract の 16B checksum は 125/125 不一致 (REPORT.md §1・§8 と同じ既知事象)。展開物の同一性は md5 の一致で確認した。
- **実行** (いずれも exit 0):
  - `python3 license/scripts/mx_n5n6_probe.py "work/extracted/VST3/Massive X.vst3"` (4.7 s)
  - `python3 license/scripts/mx_n5n6_refscan.py "work/extracted/VST3/Massive X.vst3"` (1.4 s)
- **probe の抜粋**: `Native Access` を含む ASCII 文字列は 8 件 (N6 の表 6 件 + 表外の `0x184ffc452` "Native Access to enter the correct serial number." と `0x184ffdb55` "Native Access can't be found. ...")。UTF-16LE は 1 件 (`0x18500c4d2`、プリセット パス内の製品名で誘導文言ではない)。`.rdata` 範囲 (raw 0x4ffaa52〜0x4ffdb55 付近)。
- **refscan の抜粋**:
  - `N6 0x184ffd03f: abs64=0 rva32=1` / `rva32 raw=0x3c8af47` (`.rdata` 内)。他の 9 VA は abs64 0 / rva32 0。
  - この 1 件は `0x04ffd03f` を含む 5 バイト周期の 4B 値列 (`0x04ffd04f` 等が連続) の一部。ポインタ表か別構造かは未特定のため、「参照」とは判定しない。
- **N5 名 (probe)**: `MXDemoPopup.qml` は UTF-16LE で 1 hit (`0x18415f411`、QML 資源名の列)。`demoExpired` ASCII 2 hit (`0x184879407` と、`demoExpiredChanged` の中 `0x1848792b9`)、`demoExpiredChanged` ASCII 1 hit、`subscriptionExpired` ASCII 1 hit。いずれも QML プロパティ名の並び (`MXFrameEvents::FramePage...` 等) に混在。
- **判定**: 上記の 1 件は未分類。N5/N6 の差し替え点は依然として未特定。`mx_lic_stub.py` は変更しない。
- **旧 refscan の誤り (前回 `2f235a0a`/`8d971da0` の記録)**: VA 一覧に `demoExpired` と `demoExpiredChanged` の重複、N6 3 件の欠落があった。そのため前回の「全 7 VA で 0 件」は 10 VA のうち 6 種類しか見ていない。今回の新 refscan は 10 VA 全件を測定した。
- **未検証として残るもの**: 前回記述の「テーブル基準 (文字列 index) 経由の参照」の有無、moc / qrc 系の相対オフセット表の確認 (RIP 参照は未測定)。これは #1017 で扱う。
- **結論 (変更なし)**: 読み手は (a) moc / qrc 系の相対オフセット表、(b) 文字列 index 経由 (テーブル基準の 4B 相対差分)、のいずれかと推定 [推]。前回の RVA32 検索はテーブル基準の差分を見ないため、「参照 0 件」は (a)(b) を除外していない。
- 差し替え点は未特定のため、`mx_lic_stub.py` は変更しない。e2e は本 run では再実行しない (コード変更なし)。次の一手は #1017 で (b) のテーブル基準を総当たりで確かめる。
