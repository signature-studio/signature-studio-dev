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
| N6 | 0x184ffcf87 / 0x184ffcfe8 / 0x184ffd03f / 0x184ffd092 / 0x184ffd0d6 / 0x184ffd131 | 'Please (open\|use) Native Access to (re-)activate.' 系 6 件 | **0 件** (3 方式とも) |
| N5 | 0x18415f411 | 'MXDemoPopup.qml' (QML 資源名。周辺は MX*.qml 列) | **0 件** |
| N5 | 0x184879407 / 0x1848792b9 / 0x18487941a | QML property 'demoExpired' / 'demoExpiredChanged' / 'subscriptionExpired' | **0 件** |
| N3 文言 | 0x185013ca8 (UTF-16) | 'Subscription expired.' | 関数 **0x18010e4e0** から RIP 参照 (1 件) |
| N2 文言 | 0x184ffc425 | 'Your serial number is incorrect. Please run ' | 関数 0x181142160 / 0x181143c00 から RIP 参照 (各 1 件) |

- **訂正**: §6・§11.2 の「N3 'Subscription expired.' 0x18010e4e0」は文字列アドレスではない。0x18010e4e0 は文言 0x185013ca8 を参照する**関数** (`.pdata` 登録済み)。文字列の正しい VA は 0x185013ca8。
- 同 §6 の N5/N6 表の文字列 VA は本節の実測と一致する (文字列の実在は `license/work/mx_strings.json` で確認)。

- 参照走査は `license/work/cg.pkl` の `rip` 表 (RVA キー) と、`.rdata`/`.data`/`.pdata`/`.xdata` 全体の 8B・4B 絶対値検索による。
- N6・N5 の文字列は `.rdata` の一般文字列プール内に並び、周辺は他の UI 文言・QML 資源名と混在する。**ネイティブ関数からの参照は見つからなかった**。QML ランタイム側 (Qt) が読む経路と推定 [推]。
- よって現行の IR pass (`mx_lic_stub.py`, 差し替え点は関数の分岐・store) では N5/N6 の差し替え点を指定できない。`acpt_verify_mx2.py` の N5/N6 項目は文字列の実在確認のみで、差し替え点ではない。

### 12.3 未達と起票先

| 未達 | 影響 | 起票先 |
|---|---|---|
| N5 demo UI 抑制 (QML 側の demoExpired / subscriptionExpired / MXDemoPopup 表示経路の特定と差し替え) | 受入条件 1 未達 | #1017 [MX-4] (OPEN) |
| N6 Native Access 誘導文言 6 種の抑制 (参照元の特定が先) | 受入条件 2 未達 | #1017 [MX-4] (OPEN) |
| `acpt_verify_mx2.py` の N5/N6 検査は文字列実在のみ | 「抑制済み」の機械検証が無い | #1017 [MX-4] (OPEN) |

### 12.4 #1017 の再確認 (前回 HEAD = `2f235a0a` の記録・本 run は実測なし)

- **この run の実測: なし**。`plugins-massivex` は `$ARTIFACTS_DIR` に無く (`fl-win64.tar.zst` のみ)、`Massive X.vst3` を用意できなかった。以下は前回 (HEAD `2f235a0a`) の記述で、再現手段はまだ PR 内に無い。
- 測定スクリプト (素材付きで再実行する手順):
  - `license/scripts/mx_n5n6_probe.py <Massive X.vst3>`: `Native Access` を含む文字列を全件列挙 (N6 の 6 文言は走査で求める)、既知の N5 名の出現と VA。
  - `license/scripts/mx_n5n6_refscan.py <Massive X.vst3>`: §12.2 の全 10 VA について 8B 絶対 / 4B RVA の出現数と 4B ヒットの raw オフセット。
- 前回記述の未検証項目 (再測定まで実測値として扱わない): 文字列 VA の一致 (§12.2 の 6 件 + 4 件との照合は、再測定後に全件で行う)、N5 名の moc / `MXDemoPopup.qml` 資源名としての並び、N6 文言の一般文字列プール内の位置、4B RVA ヒット (前回は 0x184ffd03f のみ) の周辺判定。
- 旧 refscan は VA 一覧に誤りがあった (`demoExpired` と `demoExpiredChanged` が同じ `0x1848792b9`、N6 の `0x184ffd092` / `0x184ffd0d6` / `0x184ffd131` が欠落)。そのため前回の「全 7 VA で 0 件」は 10 VA のうち 6 種類しか見ていない。
- **結論 (変更なし)**: 読み手は (a) moc / qrc 系の相対オフセット表、(b) 文字列 index 経由 (テーブル基準の 4B 相対差分)、のいずれかと推定 [推]。前回の RVA32 検索はテーブル基準の差分を見ないため、「参照 0 件」は (a)(b) を除外していない。
- 差し替え点は未特定のため、`mx_lic_stub.py` は変更しない。e2e は本 run では再実行しない (コード変更なし)。次の一手は #1017 で (b) のテーブル基準を総当たりで確かめる。
