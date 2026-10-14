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

### 12.2・12.2a (N5/N6 静的確認・読み手の追跡) — 分割移動

本文は [REPORT_APPENDIX_3154.md](REPORT_APPENDIX_3154.md) §12.2・§12.2a (内容は無変更・250 行上限のため #3154 で移動)。

### 12.3 未達と起票先

| 未達 | 影響 | 起票先 |
|---|---|---|
| N5 demo UI 抑制 (QML 側の demoExpired / subscriptionExpired / MXDemoPopup 表示経路の特定と差し替え)。N5 の 4 範囲は RIP 相対の参照元 0 件 | 受入条件 1 未達 | #1017 [MX-4] (OPEN) |
| N6 Native Access 誘導文言 6 種の抑制 (N6-1 の読み手 0x180f95e20 の呼び出し元の特定。N6-2〜6 の読み手関数 0x181142370 / 0x181144570 / 0x181142640 / 0x1811453f0 の役割と呼び出し元の特定 → 差し替え点の決定) | 受入条件 2 未達 | #1017 [MX-4] (OPEN) |
| `acpt_verify_mx2.py` の N5/N6 検査は文字列実在のみ | 「抑制済み」の機械検証が無い | #1017 [MX-4] (OPEN) |
| e2e の再測定 (`toolchain-retdec` 素材が必要) | 素材付きの再測定は §12.6 で実施済み (`-O0`/`-O1`/`-O2` とも 11/11 PASS) | #1280 (`[MX-7]`・受入条件 達成) |

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

### 12.6 license e2e の素材付き再測定 (`[MX-7]`・#1280・2026-10-13)

- 測定 commit = `604e900f` (origin/main。測定時点で `tools/targets/massivex/` のコードは無変更)。
- 素材: `plugins-massivex` と `toolchain-retdec` / `toolchain-emsdk` を `$ARTIFACTS_DIR` から `tar --zstd -xf` で展開。`Massive X.vst3` は `parse_setup_headers.py` → `extract_massivex.py <exe> work key` で生成し、md5 `622993e76565f49c094063a2b717d6ca` (95,356,824 B) が §11.1 と一致。RetDec は `$RUNNER_TEMP/rd/retdec`、emsdk は `$RUNNER_TEMP/em/emsdk` を `RETDEC` / `EMSDK` で指定。
- 実行: `license/work` を削除してから `MX_OPT=<level> bash e2e.sh` (lift キャッシュ無し = 冷間)。各レベルとも exit 0。

| MX_OPT | 所要 (wall) | load (開始→終了) | harness | 結果 |
|---|--:|---|--:|---|
| `-O0` | 55.7 s | 0.90 → 1.13 | 11/11 | PASS (exit 0) |
| `-O1` (既定) | 52.4 s | 0.88 → 1.19 | 11/11 | PASS (exit 0) |
| `-O2` | 47.6 s | 1.01 → 1.00 | 11/11 | PASS (exit 0) |

- 全レベルで T1〜T11 が PASS。`-O1`/`-O2` の T7〜T11 が TRAP しなかったことは確認したが、MX2-1 zero-init pass の寄与は未測定 (`MX_ZEROINIT=0` の対照実験は本節では実施していない)。
- コード差分: 測定 commit `604e900f` から HEAD までの `tools/targets/massivex/` のうち `.md` 以外は 0 行 (`git diff 604e900f HEAD -- tools/targets/massivex ':!*.md'` が空)。
- 生ログ: `$RUNNER_TEMP/e2e_O{0,1,2}.log` (`work/` 外・commit しない)。

### 12.7 N6 読み手の直接呼び出し元 (#1017・実 PE 実測 2026-10-13)

- 測定 commit = `1260d27e` (最後にコードを変えた commit。linear の欠落区間の出力を追加)。実 PE・selftest とも同一 commit で実行。
- 素材: `plugins-massivex` (`$ARTIFACTS_DIR`) を `$RUNNER_TEMP/mx` に展開 → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work key` (`tools/targets/massivex` 直下、展開先 `work/`)。`work/extracted/VST3/Massive X.vst3` = 95,356,824 B、md5 `622993e76565f49c094063a2b717d6ca` (§11.1 と一致)。
- 走査スクリプトの読む先: `work/extracted/VST3/Massive X.vst3` (`tools/targets/massivex` 起点)。

| 手順 | コマンド (`tools/targets/massivex` 直下) | 所要 (wall) | 結果 |
|---|---|--:|---|
| 陽性対照 (probe) | `python3 license/scripts/mx_callers_probe.py --selftest` | 1.1 s (probe 実走査と合計) | 期待 1/2/0/0/0 → 検出 1/2/0/0/0 PASS (rc 0) |
| 直接走査 (probe) | `python3 license/scripts/mx_callers_probe.py` | 同上 | 5 読み手への E8/E9 = **0 件** (rc 0) |
| 陽性対照 (linear) | `python3 license/scripts/mx_callers_linear.py --selftest` | 0.1 s | 期待 1/2/1/0/0 → 検出 1/2/1/0/0 PASS・不正バイト 3 B を挟んでも後続 call を検出 (rc 0) |
| 線形検算 (linear) | `python3 license/scripts/mx_callers_linear.py` | 36.5 s | `.text` 60,224,000 B 中 **デコード 60,189,833 B (99.94%)**・未デコード 34,167 B (17,579 区間)。5 読み手への call/jmp = **0 件** (rc 0) |

- 欠落区間: 未デコードは 1 B ずつ再同期した区間。全区間の VA 開始・バイト数を `work/mx_linear_gaps.txt` に出力 (`work/` は gitignore・commit しない)。区間バイト数の合計 34,167 B は上の未デコード量と一致。カバー率は 100% ではないが、この欠落区間の中身 (データか未対応命令か) は未分類。読み手への直接 call/jmp の 0 件は、バイト走査 (probe) が欠落区間を含む全 `.text` を走査して同じく 0 件である点で裏付ける。
- 負荷: 測定時 `uptime` load average 0.31 (開始) → 0.65 (linear 完走時・HEAD 88fcedc1 再測定)。4 vCPU。並列 1 プロセス。
- 件数の一致: 読み手 5 関数は probe / linear とも 0 件で一致。0 件の根拠となる陽性対照は selftest (合成 .text) で示した。実 PE 上の陽性対照 (読み手以外の頻出関数の件数比較) は本 HEAD では再測定していない。
- 判定 (実 PE・現 HEAD): **直接 call/jmp (E8/E9) で N6 読み手 5 関数を呼ぶ箇所は .text 内に 0 件** (バイト走査・線形逆アセンブルの 2 方式で一致)。間接呼び出し (vtable / 関数ポインタ表) と、テーブル基準の参照は本節では判定していない。N5 の読み手は未特定。
- 残件: 間接呼び出し元の特定 (vtable / 関数ポインタ表の `.rdata` 走査) → #1439 [MX-9]。N5 の読み手の特定 → #1439 [MX-9]。
- e2e (`license/e2e.sh`) は本節では未実行。e2e の実測は §12.6 (#1280) が正本。
- コード差分: 測定 commit `1260d27e` から HEAD までの `tools/targets/massivex/license` と非 md の差分は 0 行 (`git diff 1260d27e HEAD -- tools/targets/massivex ':!*.md'` が空)。

### 12.8 間接参照の 4 系統総当たり (#1439 [MX-9]・2026-10-14)

- 素材: `plugins-massivex` を `$RUNNER_TEMP/mx` に展開 → `scripts/parse_setup_headers.py <exe> work/key` → `scripts/extract_massivex.py <exe> work/key key`。`work/key/extracted/VST3/Massive X.vst3` = 95,356,824 B、md5 `622993e76565f49c094063a2b717d6ca` (§11.1 と一致)。extract の checksum 不一致 125/125 は §1・§8・§12.4 と同じ既知事象。
- 新規スクリプト `license/scripts/mx_indirect_refs.py` (`--selftest` 付き)。読み手 5 関数 (§12.7) と N5/N6 文字列 10 VA (§12.2) を次の 4 系統で走査:
  - A: 8B 絶対 VA (全セクションの raw バイト列)
  - B: 4B RVA (image base 相対、全セクション)
  - C: 命令の RIP 相対 mem 実効先・即値 (`.text` 線形逆アセンブル、capstone)
  - D: 自己相対 4B (位置 p の値 d について p+d が対象 VA)
- 陽性対照: `--selftest` で 4 系統とも既知 1 件を検出 (`abs8=1 rva4=1 self4=1 rip/imm=1`) → PASS。
- **修正版の全域再走査 (commit `605b43b2`・B/D を開始 offset 0〜3 で走査)**: 下表が現行の結果。旧版 (4B 整列のみ) では offset 1 / 33 の既知参照が `rva4=0 self4=0` (期待 1) になることを確認済みで、旧版の「0 件」は無効。修正版の `--selftest` は非整列 (offset 1 / 33) の陽性対照を含み PASS (`unaligned rva4=0x180100001 self4=0x180100021`)。
- 再現手順 (`tools/targets/massivex` 直下): `python3 license/scripts/mx_indirect_refs.py --selftest` (rc 0) → `python3 license/scripts/mx_indirect_refs.py "work/key/extracted/VST3/Massive X.vst3"` (rc 0・約 1 分 43 秒)。PE は `work/key/` に §12.8 冒頭の手順で生成 (md5 `622993e7…` 一致)。
- C (rip/imm) の 0 件は `.text` 線形逆アセンブルで、§12.7 の未デコード区間 34,167 B (約 0.06%) の命令は見ていない。C の 0 件はこの区間を含まない。

| 対象 | A abs8 | B rva4 | C rip/imm | D self4 |
|---|--:|--:|--:|--:|
| 読み手 0x180f95e20 (N6-1) | 0 | 2 (.pdata・.xdata 各 1) | 0 | 0 |
| 読み手 0x181142370 (N6-2) | 0 | 2 (.pdata・.xdata 各 1) | 0 | 0 |
| 読み手 0x181144570 (N6-3) | 0 | 2 (.pdata・.xdata 各 1) | 0 | 0 |
| 読み手 0x181142640 (N6-4) | 0 | 2 (.pdata・.xdata 各 1) | 0 | 0 |
| 読み手 0x1811453f0 (N6-5) | 0 | 2 (.pdata・.xdata 各 1) | 0 | 0 |
| N6 文字列 6 件 (0x184ffcf87〜0x184ffd131) | 0 | 1 (0x184ffd03f ← `.rdata` 0x183c8c947・非整列 mod 4 = 3) | 0 | 1 (0x184ffd0d6 ← `.rdata` 0x184bfd0d6・非整列 mod 4 = 2) |
| N5 文字列 4 件 (MXDemoPopup.qml / demoExpired / demoExpiredChanged / subscriptionExpired) | 0 | 0 | 0 | 0 |

- 読み手 5 件の rva4 (各 2 件) は `.pdata` (`0x185fc0ff8` 等) と `.xdata` (`0x18630d324` 等) 内の関数範囲表の登録で、呼び出し元ではない (§12.5 と同じ判定)。
- 非整列の 2 件 (N6 文字列への参照) の分類: **表・構造体とは判定できず、誤検出の疑い**。
  - `.rdata` 0x183c8c947 (B): 周囲は `fd 4f d0 ff 04` の周期的なバイト列で、前後の整列 4B 値も image 内 RVA として意味を持たない。4B 窓の値 `0x04ffd03f` が偶然 `0x184ffd03f` と一致した可能性が高い。
  - `.rdata` 0x184bfd0d6 (D): 周囲は `00 00 04 00 00 00 3b 00 00 00 7e 02 …` の 16bit 値の列で、4B 窓が値の境界をまたいでいる。`0x00400000` が自己相対 disp として偶然 `0x184ffd0d6` を指した可能性が高い。
  - 参照元の表を特定するには、両位置を含む `.rdata` の構造 (stride・型) を未同定のまま残す。この 2 件は差し替え点の根拠にしない。
- 実行: `mx_indirect_refs.py` rc 0、実測 1 min 43 s (`load` 1.11 → 開始時・4 vCPU・並列 1)。
- 判定: 読み手 5 関数への参照は A/B(非 .pdata/.xdata)/C/D のいずれでも 0 件。N5 文字列も 0 件。N6 文字列への参照は非整列の 2 件のみで、いずれも誤検出の疑い (上記)。前版の「vtable / 関数ポインタ表経由」の仮説は絶対ポインタ形式で否定された。残る候補は (E) テーブル基準 (表先頭 base) からの相対差分 (`t - base` が 4B 符号付き) と文字列 index 経由の間接参照で、本節では未走査。
- 差し替え点は未確定のため `license/scripts/mx_lic_stub.py` の RULES は**変更しない** (根拠なしの br_force / store は silent miscompile になる)。
- 残件: (E) の走査、呼び出し元の確定、差し替え点の決定、`acpt_verify_mx2.py` の拡張 (N5/N6 の抑制を機械検証)。→ 子 issue [MX-11] に起票 (番号は PR 本文・issue コメント参照)。

#### e2e 再測定 (同一素材・冷間 = `license/work` 削除後)

| MX_OPT | 所要 (wall) | load (開始) | harness | 結果 |
|---|--:|--:|--:|---|
| `-O0` | 81.9 s | 1.50 | 11/11 | PASS (exit 0) |
| `-O1` (既定) | 87.2 s | 0.83 | 11/11 | PASS (exit 0) |
| `-O2` | 73.9 s | 0.90 | 11/11 | PASS (exit 0) |

- 素材: `toolchain-retdec` (`$RUNNER_TEMP/rd/retdec`) と `toolchain-emsdk` (`$RUNNER_TEMP/em/emsdk`) を `RETDEC` / `EMSDK` で指定。`license/e2e.sh` 本体は未変更 (`mx_lic_stub.py` も未変更)。

### 12.9 テーブル基準 (E) の総当たり (#1613 [MX-11]・2026-10-14。対照と一貫性は #3154 [MX-34] で再現化)

- スクリプト `license/scripts/mx_table_refs.py` (`--selftest`・`--control` 付き)。`.text` の RIP 相対 mem 実効先・即値のうち `.rdata`/`.data` に入る VA を表の base 候補 (177,327 件) とし、各 base から先頭 512 個の 4B 符号付き値 d を読んで `base + d` が対象 15 VA (読み手 5 関数 + N5/N6 文字列 10 VA) に一致するかを判定する。
- **一貫性 (#3154)**: hit の前後 WINDOW=4 個 (範囲内) の entry のうち、d≠0 で対象と同じセクションを指す割合が 1/2 以上なら OK。d=0 は base 自身を指すため除外し、hit 自体が d=0 なら NG。
- **対照 (#3154)**: `.rdata` 内のランダム VA 40 件 (seed 3154) を同じ走査・同じ一貫性判定に通す。再現: `python3 license/scripts/mx_table_refs.py --control` (既定の素材パスは `tools/targets/massivex` から実行)。
- 自己検査: `--selftest` PASS (rc 0)。4 ケース = 一貫 OK 1 件 (既知の表 entry) と一貫 NG 3 件 (周辺が別セクション・周辺が 0 埋め・hit が d=0 の自己参照)。判定 (一貫性) を常に真にする / hit の d=0 ガードを外す / 周辺の 0 除外を外す、の 3 種の mutant で FAIL を確認。
- 測定 commit `8b2eb41e` (素材 `plugins-massivex` → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work/key key` で `work/key/extracted/VST3/Massive X.vst3` (95,356,824 B、md5 `622993e7…` 一致))。
- 修正 commit `bf1ad2de` (#3173 round 1): `scan_tables` の `targets`・`sections` を省略可能にし、`mx_dll_table_refs.py` の呼出しを更新。`git diff --stat 8b2eb41e bf1ad2de -- tools/targets/massivex/license/scripts` は 2 files, 17 insertions(+), 3 deletions(-)。コードが変わったため、下表の数値は `8b2eb41e` 時点の値で `bf1ad2de` での再測定は未了 (本 run に素材 `plugins-massivex` が無い)。
- `bf1ad2de` の検証: `--selftest` PASS (rc 0)、既定経路の検査を外す mutant (`targets = {}`) で FAIL。`mx_dll_table_refs.py` は合成 PE (表 1 件・N6-1 を指す) で `main` と同じ hit 1 件 (rc 0)、修正前 `190c2e20` は `TypeError` で再現。実素材の DLL で hit 4 件を再現する検証は未実施。

| 測定 (`8b2eb41e`・同一 VM 4 vCPU) | 所要 (wall) | 結果 |
|---|--:|---|
| `--selftest` | 0.11 s | PASS (rc 0) |
| (E) 走査 (既定) | 2 min 32 s | raw 3 件・一貫性 OK 0 件 (rc 0) |
| 対照 `--control` | 2 min 35 s | raw 70 件・一貫性 OK 5 件 (rc 0) |

測定直後の load 1 分平均は 0.55 (開始時の load は未記録)。

| 対象 | (E) raw hit | (E) 一貫性 OK |
|---|--:|--:|
| 読み手 5 関数 (N6-1〜5) | 0 | 0 |
| N6 文字列 0x184ffcf87 / 0x184ffd03f / 0x184ffd092 / 0x184ffd0d6 / 0x184ffd131 | 0 | 0 |
| N6 文字列 0x184ffcfe8 | 1 | 0 |
| N5 MXDemoPopup.qml / demoExpired / subscriptionExpired | 0 | 0 |
| N5 demoExpiredChanged | 2 (同一 base 0x1847f8cb8 の idx 30 / 200) | 0 |
| **合計 (15 対象)** | **3 (1 対象あたり平均 0.200)** | **0 (平均 0.000)** |

| 対照 (`.rdata` 0x183971000..0x18515e89c のランダム VA 40 件) | raw hit | 一貫性 OK |
|---|--:|--:|
| **合計 (40 対象)** | **70 (1 対象あたり平均 1.750)** | **5 (平均 0.125)** |
| うち control 18 (0x184183474。表の base 自身の 0 埋め領域で d=0 が全件 hit) | 64 | 0 |
| control 18 を除く (39 対象) | 6 (平均 0.154) | 5 (平均 0.128) |

`--control` の出力 (hit が 1 件以上の対象のみ抜粋 (5 対象: 01・12・18・21・26)。0 件の 35 対象は省略。全行は同コマンドで再現):

```
対照: .rdata 0x183971000..0x18515e89c 内のランダム VA 40 件 (seed 3154)
base 候補 (.text 参照・.rdata/.data 内): 177327 件, entries/base = 512
section .rdata   base 内候補 154842 件 -> hit 70 件
section .data    base 内候補 9152 件 -> hit 0 件

control 01 0x183cbee7a: 1 件 (一貫性 OK 1 件)
  base 0x184cbed78 idx 110 entry@0x184cbef30 base 参照元 0x182b2c860 一貫性 OK

control 12 0x184eefc29: 2 件 (一貫性 OK 2 件)
  base 0x1849ffbe0 idx 244 entry@0x1849fffb0 base 参照元 0x183264417 一貫性 OK
  base 0x184e4fc20 idx 461 entry@0x184e50354 base 参照元 0x1833b5141 一貫性 OK

control 18 0x184183474: 64 件 (一貫性 OK 0 件)
  base 0x184183474 idx 36 entry@0x184183504 base 参照元 0x180171310 一貫性 NG
  base 0x184183474 idx 45 entry@0x184183528 base 参照元 0x180171310 一貫性 NG
  base 0x184183474 idx 58 entry@0x18418355c base 参照元 0x180171310 一貫性 NG
  base 0x184183474 idx 60 entry@0x184183564 base 参照元 0x180171310 一貫性 NG
  base 0x184183474 idx 61 entry@0x184183568 base 参照元 0x180171310 一貫性 NG
  base 0x184183474 idx 62 entry@0x18418356c base 参照元 0x180171310 一貫性 NG
  base 0x184183474 idx 69 entry@0x184183588 base 参照元 0x180171310 一貫性 NG
  base 0x184183474 idx 70 entry@0x18418358c base 参照元 0x180171310 一貫性 NG

control 21 0x184f1146c: 2 件 (一貫性 OK 2 件)
  base 0x184f111f0 idx 364 entry@0x184f117a0 base 参照元 0x183707e12 一貫性 OK
  base 0x184f111f8 idx 306 entry@0x184f116c0 base 参照元 0x18370b6c2 一貫性 OK

control 26 0x184063916: 1 件 (一貫性 OK 0 件)
  base 0x184063910 idx 22 entry@0x184063968 base 参照元 0x1838a64eb 一貫性 NG

合計: 対象 40 件・hit 70 件 (1 対象あたり平均 1.750)・一貫性 OK 5 件 (1 対象あたり平均 0.125)
```

(E) の hit 行 (既定実行・`8b2eb41e`): `N6 0x184ffcfe8`: `base 0x184e2c7e8 idx 276 entry@0x184e2cc38 base 参照元 0x18193ff4a 一貫性 NG`。`N5 demoExpiredChanged`: `base 0x1847f8cb8 idx 30 / idx 200`・参照元 `0x181a0ae57`・いずれも一貫性 NG。

- **判定: 実参照と判定する根拠は無い (従来の判定を維持)**。(E) の raw hit 3 件は全て一貫性 NG で、対照の一貫性 OK の平均 0.125 (1 対象あたり) を下回る。旧版の数値 (対照 40 件・1 対象あたり平均 0.05 件) は ad hoc 計測で再現できないため、本節の `--control` の値で置き換える。
- **旧版との差 (経緯)**: 測定 commit `e0c47d2f` (d=0 の周辺を除外しない版) では対照の一貫性 OK が 58 件 (平均 1.450) になった。`control 18` の 0 埋め領域 (d=0 が base 自身を指す) を OK と誤判定していたため、d≠0 の周辺だけを数える版に直して `8b2eb41e` で再測定した。
- **限界**: 一貫性判定は対照でも 5 件を OK と判定する。OK 判定だけでは表の実在を示せず、本節の判定は「(E) の raw hit が一貫性を満たさない」ことにだけ依拠する。
- 結論: テーブル基準でも読み手 5 関数と N5 文字列の参照元は**確定しない**。N6 読み手の呼び出し元と N5 の読み手は、直接参照 (§12.7)・絶対/RVA/RIP/自己相対 (§12.8)・テーブル基準 (本節) の 4 系統 + (E) で 0 件。残るのは文字列 index 経由など未走査の間接参照。
- 差し替え点は未確定のため `license/scripts/mx_lic_stub.py` の RULES は**変更しない** (根拠なしの br_force / store は silent miscompile になる)。受入条件 2 は未達。`acpt_verify_mx2.py` の拡張 (受入条件 4) も未着手。

#### e2e (受入条件 3・測定 commit `a2cbc607`)

| MX_OPT | 所要 (wall) | load (開始) | harness | 結果 | 備考 |
|---|--:|--:|--:|---|---|
| `-O0` | 61.8 s | 0.10 | 11/11 | PASS (exit 0) | `license/work` 削除後 (冷間・lift 再生成) |
| `-O1` | 4.8 s | 0.23 | 11/11 | PASS (exit 0) | lift キャッシュ流用 (温間) |
| `-O2` | 4.7 s | 0.16 | 11/11 | PASS (exit 0) | lift キャッシュ流用 (温間) |

- 素材: `plugins-massivex` → `$RUNNER_TEMP/mx`、`toolchain-retdec` → `$RUNNER_TEMP/rd/retdec`、`toolchain-emsdk` → `$RUNNER_TEMP/em/emsdk`。`parse_setup_headers.py` / `extract_massivex.py` で `work/key/extracted/VST3/Massive X.vst3` (95,356,824 B、md5 `622993e7…` 一致)。`work/extracted` は同ディレクトリへの symlink。
- 注意: 検証途中、`-O1` と `-O2` を並列実行して `license/work/mx_fixed.vst3` を競合させ、`-O2` が PE 修復 assert で rc=1 になった。並列実行の誤りで、スクリプトの不具合ではない。上表は逐次実行・同一 commit での再測定値。

### 12.10 MX-17 (#1857) — 分割移動

本文は [REPORT_APPENDIX_3154.md](REPORT_APPENDIX_3154.md) §12.10 (内容は無変更・#3154 で移動)。

### 12.11 MX-24 (#1900) 残件の確認 (2026-10-14・基点 `46faf265`)

- 素材: `plugins-massivex` → `$RUNNER_TEMP/mx`。`parse_setup_headers.py` → `extract_massivex.py <exe> work/key key` で `work/key/extracted/VST3/Massive X.vst3` (95,356,824 B、md5 `622993e7…` 一致)。extract の checksum 不一致 125/125 は既知事象。
- selftest: `mx_table_refs.py --selftest` PASS、`mx_indirect_refs.py --selftest` PASS (いずれも rc 0)。
- **新規事実 (DLL の存在)**: 同じ素材の `work/key/extracted/Native Instruments/Massive X.dll` (95,249,816 B) にも N5/N6 文字列がある (`Native Access to re-activate.` 6 件・`demoExpired` 2 件・`subscriptionExpired` 1 件)。ImageBase は `.vst3` と同じ `0x180000000` だが、`.text` の md5 が `.vst3` と異なる別バイナリで、文字列の RVA も一致しない (`.vst3` 0x4ffcf93 / DLL 0x4fe83de)。§12.2〜12.9 の走査は `.vst3` だけが対象で、DLL は未走査だった。
- DLL の文字列 VA: `Native Access to re-activate.` 0x184fe83de / 0x184fe843e / 0x184fe8495 / 0x184fe84e8 / 0x184fe852c、`Native Access to activate.` 0x184fe8587。`MXDemoPopup.qml` は DLL に ASCII 0 件・UTF-16 1 件。
- DLL 参考走査 (`mx_indirect_refs.scan_data` を DLL の全セクションに適用): `.vst3` の読み手 VA (0x180f95e20 等) を対象にした。DLL の関数は別の VA にあるため、これは参照の判定ではなく参考値。結果は `.pdata`・`.xdata` の rva4 各 1 件のみ (関数範囲表の登録で呼び出し元ではない)。DLL の読み手関数は未特定。
- 判定: 受入条件 1 (呼び出し元確定) は未達。受入条件 2 (差し替え点) は未達。`mx_lic_stub.py` の RULES は変更しない (根拠なしの br_force / store は silent miscompile になる)。受入条件 3 (差し替え後の機械検証) は差し替え点が無いため未着手。
- 残件の起票先: DLL 側の読み手と呼び出し元の確定 → 子 issue (本 PR 本文の未解決表を参照)。文字列 index 経由の走査と差し替え点の決定、`acpt_verify_mx2.py` 拡張 → 子 issue。
- 12.12〜12.15 (#1976・#2108・#2151・#2195 残件) の全文は [REPORT_APPENDIX_2151.md](REPORT_APPENDIX_2151.md) (分割移動)。§12.13 の「pdata 範囲外」は §12.15 (b) で訂正 (関数内)。
