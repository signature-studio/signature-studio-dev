# Massive X 1.7.1 REPORT 付録 (#3154 MX-34 分割移動・§12.2・§12.2a・§12.10)

本体 `REPORT_APPENDIX.md` の 250 行上限のため、§12.2・§12.2a・§12.10 を分割移動した (内容は無変更)。

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

### 12.10 MX-17 (#1857) 着手時の確認と e2e 基準値 (2026-10-14・測定 commit `8ea5d402`)

- 結論: 受入条件 1〜3 は未達 (呼び出し元・差し替え点は未確定)。本 run は受入条件 4 の基準値取得のみ行った。未走査経路の走査は本 run では実施していない。RULES は変更しない。
- 素材: `plugins-massivex` → `$RUNNER_TEMP/mx`、`parse_setup_headers.py` → `extract_massivex.py <exe> work/key key` で `Massive X.vst3` (95,356,824 B、md5 `622993e7…` 一致。extract の checksum 不一致 125/125 は既知事象)。`toolchain-retdec` → `$RUNNER_TEMP/rd/retdec`、`toolchain-emsdk` → `$RUNNER_TEMP/em/emsdk`。
- selftest: `mx_table_refs.py --selftest` rc 0、`mx_indirect_refs.py --selftest` rc 0。

| MX_OPT | 所要 (wall) | load (開始) | harness | 結果 | 備考 |
|---|--:|--:|--:|---|---|
| `-O0` | 56.8 s | 0.86 | 11/11 | PASS (exit 0) | `license/work` 冷間 (lift 再生成) |
| `-O1` | 10 s | 1.07 | 11/11 | PASS (exit 0) | lift キャッシュ流用 (温間) |
| `-O2` | 4 s | 1.30 | 11/11 | PASS (exit 0) | lift キャッシュ流用 (温間) |

- 逐次実行 (`-O0` → `-O1` → `-O2`)。`-O0` の 56.8 s は作業 VM の 4 vCPU・load 0.86 時点の実測。
- 残件 (受入条件 1〜3): 未走査の「文字列 index 経由の間接参照」と「関数ポインタを埋め込む構造体の `.data` 走査」。`acpt_verify_mx2.py` の N5/N6 機械検証 (受入条件 3) は未着手。残件は子 issue #1900 [MX-24] に分離して追跡する (#1857 は受入 4 のみに範囲を縮めて `Closes #1857`)。
