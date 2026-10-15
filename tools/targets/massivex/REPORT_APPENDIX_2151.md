# Massive X 1.7.1 REPORT 付録 (#2151 MX-31・§12.12〜§12.15)

本体 `REPORT_APPENDIX.md` の §12.12〜§12.14 の全文 (250 行上限のため分割移動・内容は無変更)。§12.15 は #1976 残件 (MX-32 #2195) の実測で、§12.14 の `.pdata` 未確定と §12.13 の「pdata 範囲外」を確定・訂正する。

### 12.12 DLL (`Native Instruments/Massive X.dll`) の読み手・呼び出し元の走査 (#1976・測定 commit `28e39ee1`)

- 素材: `plugins-massivex` → `$RUNNER_TEMP/mx` → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work/key key`。`work/key/extracted/Native Instruments/Massive X.dll` = 95,249,816 B。checksum 不一致 125/125 は既知事象。
- 走査器 (新規・`license/scripts/`): `mx_dll_readers.py` (文字列 blob の読み手・線形逆アセンブル)、`mx_dll_callers.py` (関数単位の直接 call/jmp・即値)、`mx_dll_table_refs.py` (既存 `mx_table_refs.py` を DLL の VA で実行。既存スクリプトは無変更)。
- 検出器の健全性: 同じ `mx_dll_readers.py` を `.vst3` に実行すると、既知の N6-1 読み手 `0x180f95e20` (movups 4 件) を再現した (§12.2a と一致)。`mx_indirect_refs.py --selftest` / `mx_table_refs.py --selftest` は PASS (rc 0)。
- NUL 区切り blob (DLL): N6 文字列 `[0x184fe83b7,0x184fe8fa0)` 付近の 11 blob。N5 は `demoExpired`/`demoExpiredChanged` が `[0x184862d19,…)`、`subscriptionExpired` が `[0x184862e7a,…)`。`MXDemoPopup.qml` は UTF-16LE のみ (VA `0x18414cd91`)。

| 項目 | 結果 |
|---|---|
| 線形逆アセンブル | 15,200,102 insn・bad-resync 34,698・`.text` 60,154,368 B 全域 |
| 文字列 blob を参照する `.text` 命令 | 16 件 (RIP 相対 lea 10・movups 4・他 2) |
| 読み手関数 (文字列を読む関数) | 8 件: `0x180167a70` / `0x180f84920` / `0x181130b20` / `0x181130d30` / `0x181131000` / `0x1811325c0` / `0x181132f30` / `0x181133db0` |
| 読み手 8 件への直接 call/jmp・即値 | 0 件 (関数単位の再逆アセンブル: 関数 186,730・部分 decode 4,391) |
| 読み手 8 件への絶対 8B / RVA 4B / 自己相対 4B | `.pdata`・`.xdata` の関数範囲表 (各 1 件・呼び出し元ではない) と、`0x181133db0` への自己相対 1 件 (`.rdata` `0x18470e211`) のみ。後者は 4B 値が表の一部か偶然か未判定 |
| 文字列 blob への絶対 8B / RVA 4B | 0 件 |
| 文字列 blob への自己相対 4B | `0x184fe7870` (`.text` `0x181733070`)・`0x184fe83b7` (`.rdata` `0x184f98a2d`)・`0x184fe83fc` (`.rdata` `0x184f94349`) の 3 件 |
| テーブル基準 (E・`mx_dll_table_refs.py`) | base 候補 177,324 件 → hit 4 件。全件が同一 base `0x183b27dda` の差分 `-0x29f402a` (→ `0x181133db0`) で、idx 236・244・249 の 3 件と base 参照元 `0x1831c9e45` (どの関数にも属さない)。`0x184021d48` の 1 件 (参照元 `0x1838565d3`・関数外) を含む |
| N5 UTF-16 `MXDemoPopup.qml` (VA `0x18414cd91`) | RIP 相対・即値 0 件 |

- 判定: **N6 読み手 8 関数は確定** (文字列 blob 参照の実命令で確認)。**呼び出し元は未確定**: 直接・即値・絶対・RVA の 4 系統で 0 件。テーブル基準の 4 件は同一差分の 1 組で、base 参照元が関数外のため候補止まり。N5 の読み手は ASCII・UTF-16 とも未特定。
- `mx_lic_stub.py` の RULES は変更しない (呼び出し元が未確定のため、差し替え点を決めると silent miscompile になる)。
- 残件 (起票先は PR 本文の未解決表): (1) テーブル基準候補 `0x183b27dda` 系の base 参照元の逆引き (関数外のため、呼び出し経路の確定が必要)、(2) N5 読み手の特定 (ASCII / UTF-16 とも `.text` 直接参照 0 件のため、文字列 index 経由・関数ポインタ埋め込みを疑う)、(3) `acpt_verify_mx2.py` の DLL 対応。

### 12.13 DLL の N5 読み手・テーブル基準候補の確認 (#2108 [MX-30]・測定 commit `637b70de`・2026-10-14)

- 素材: `plugins-massivex` → `$RUNNER_TEMP/mx` → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work/key key`。`work/key/extracted/Native Instruments/Massive X.dll` = 95,249,816 B (§12.12 と一致)。md5 `9b3f9107a7b2d7ccd9146622bb39eefb`。checksum 不一致 125/125 は既知事象。
- 実行 (`tools/targets/massivex` 直下・いずれも rc 0):
  - `python3 license/scripts/mx_dll_readers.py` (2 min 34 s・load 1.53 開始)。§12.12 の読み手 8 関数と blob 一覧を再現。
  - `python3 license/scripts/mx_dll_table_refs.py` (2 min 18 s)。§12.12 の hit 4 件を再現。
  - 調査用の追加確認 (`work/` のみ・commit しない): 参照元の逆引き・セクション表・call 先の内容。
- 結果:

| 項目 | 結果 |
|---|---|
| N5 blob (`demoExpired`×2 `0x184862d19`/`0x184862e67`・`subscriptionExpired` `0x184862e7a`) の読み手 | 関数 0 件 (blob 参照の命令は N6 のみ。直接 call/jmp・即値も 0 件) |
| N5 UTF-16 `MXDemoPopup.qml` (`0x18414cd91`) の読み手 | RIP 相対・即値 0 件 |
| テーブル基準候補 base `0x183b27dda` の参照元 `0x1831c9e45` | pdata 範囲外 (関数外)。`call 0x183b27dda` の命令。**その call 先 `0x183b27dda` は `.rdata` (chars `0x40000040`・実行不可)** |
| テーブル基準候補 base `0x184021d48` の参照元 `0x1838565d3` | pdata 範囲外 (関数外)。`call 0x184021d48` の命令。**call 先 `0x184021d48` も `.rdata`** |
| base `0x183b27dda` の表 (idx 236/244/249) | いずれも `0x181133db0` (N6-8 読み手) を指す。他 idx の target は散らばり、表として一貫しない |
| base `0x184021d48` の表 (idx 239) | `0x184fe84b3` (N6 文字列) を指す。idx 236/244/249 の target は散らばる |

- 判定:
  - **受入条件 1 (N5 読み手の特定): 未達**。N5 の 4 文字列は直接参照・即値の走査で 0 件。文字列 index 経由・関数ポインタ埋め込み (§12.10 の残件) は未走査。
  - **受入条件 2 (候補の判定): 判定保留**。参照元 2 箇所は pdata 範囲外で、前後の命令は `.text` 内で連続している。`call` 先の候補アドレスは `.rdata` にあり、実行可能な call 先としては不自然なので、偶然一致の可能性が高い。ただし参照元の領域が非コード (データ) の誤デコードである可能性も残り、関数としての特定はできていない。idx 236/244/249 の `0x181133db0` 一致は 3 件とも同一差分 `-0x29f402a` の繰り返しで、表全体の一貫性は確認できない。**N6 読み手の呼び出し元は依然として未確定**。
  - 差し替え点は未確定のため `license/scripts/mx_lic_stub.py` の RULES は変更しない。
  - e2e は本 run でコードを変えていないため未実行 (§12.6・§12.10 が正本)。

### 12.14 MX-31 (#2151) の再走査と §12.13 の訂正 (2026-10-14・測定 commit `b623937f`)

- 素材: `plugins-massivex` → `$RUNNER_TEMP/mx` → `parse_setup_headers.py` → `extract_massivex.py key`。DLL md5 `9b3f9107a7b2d7ccd9146622bb39eefb`・95,249,816 B (§12.13 と一致)。
- 再実行 (`tools/targets/massivex` 直下・rc 0): `mx_dll_readers.py` 3 min 35 s (読み手 8 関数を再現)・`mx_dll_table_refs.py` 3 min 21 s (hit 4 件を再現)・`mx_dll_callers.py` 2 min 36 s (`functions 186730 partial-decode 4391`・読み手 8 件すべて direct call/jmp・即値 0 hits)。
- **§12.13 の「pdata 範囲外」への訂正は未確定 (断定しない)**: DLL の `.pdata` セクションは 2 つあり (作成者の記録: `.pdata` 0x185f3a000 と 0x18615f000)、どちらが x64 本体かは本節では判定できていない。
  - 根拠の現状: `mx_dll_callers.py` は `secs.setdefault` (セクション名の先勝ち) で最初の `.pdata` を使うだけで、x64 本体かを判定していない。`mx_rtti.py` (Massive X.vst3 用) は「大きい方 = x64 本体」として `Misc_VirtualSize` 降順で採用しているが、これは VST3 の判断であり DLL に適用できる根拠ではない。「既存スクリプトと一致する」は正しさの根拠にならない。
  - 2 つの `.pdata` の `VirtualAddress` / `Misc_VirtualSize` / 関数数は、本 run で再計測していない (素材 `plugins-massivex` 不在)。
  - 仮に先勝ちの `.pdata` を使った場合、参照元 2 件 `0x1831c9e45`・`0x1838565d3` は `0x1831c9bae`〜`0x1831c9f6a`・`0x1838544f0`〜`0x183859834` の範囲内に入る (作成者の記録)。大きい方を使った場合の所属は未確認。
  - 両 call 先 `0x183b27dda`・`0x184021d48` は `.rdata` (実行不可) と記録されている (作成者の記録)。
  - 次の検証 (未実施・起票先 #2195 の受入条件): 2 つの `.pdata` の VA・サイズ・関数数を DLL から実測して並べ、どちらが x64 本体かを (例: `.text` 内の関数境界と整合する方・`IMAGE_RUNTIME_FUNCTION_ENTRY` の妥当性) 根拠付きで示す。そのうえで `0x1831c9e45`・`0x1838565d3` の所属を両 `.pdata` で比べる。
- **実測の主体**: 上の §12.14 の再走査 (readers・table_refs・callers の件数・時間) は測定 commit `b623937f` の run (PR #2151 の作成者 run) の実測。本ファイルの review 対応 run (`d3e01fc9` 以降) では `plugins-massivex` が取得されておらず、DLL を再生成していない。
- **N6 読み手 8 関数の呼び出し元 (受入条件 3)**: 直接 call/jmp・即値は 8 件すべて 0。絶対 8B・RVA 4B・自己相対 4B のうち、読み手への該当は `.pdata`/`.xdata` の関数範囲表 (呼び出し元ではない) と `.rdata 0x18470e211` (自己相対 1 件) のみ。`0x18470e211` は非整列で、前後 24 entry の値は無作為 (表ではない)。N6 読み手の呼び出し元は確定しない。
- **N5 の読み手 (受入条件 2)**: N5 の 4 文字列 (`demoExpired` `0x184862d19`・`demoExpiredChanged` `0x184862e67`・`subscriptionExpired` `0x184862e7a`・UTF-16 `MXDemoPopup.qml` `0x18414cd91`) への絶対 8B・RVA 4B は DLL 全域で 0 件。`.rdata` の自己相対 4B で N5 窓 (`0x184862000`〜`0x184863000`) に入るものは 133 件 (129 種の target) あるが、target は整列していない小さなオフセットで、N5 blob の開始アドレスと一致しない。偶然一致として扱い、N5 読み手は未特定。
- **判定**:
  - 受入条件 1 (N5 読み手の特定): 未達。
  - 受入条件 2 (テーブル基準候補の判定): 判定保留。候補は偶然一致の可能性が高いが、`.pdata` の選択が未確定のため参照元の所属は確定しない。`0x1838544f0` は部分 decode が残る。
  - 受入条件 3 (N6 読み手 8 関数の呼び出し元の確定): 未達。直接・即値・絶対・RVA・自己相対で 0 件。残るのは文字列 index 経由・関数ポインタ経由の間接参照。
- 差し替え点は未確定のため `license/scripts/mx_lic_stub.py` の RULES は変更しない。
- e2e は本 run でコードを変えていないため未実行。

### 12.15 #1976 残件の実測: x64 本体の `.pdata` 確定と命令境界に依らない参照走査 (MX-32 #2195・測定 commit `1c89aa4b`・2026-10-14)

- 素材: `plugins-massivex` → `$RUNNER_TEMP/mx` → `scripts/parse_setup_headers.py <exe> work/key` → `scripts/extract_massivex.py <exe> work/key key`。`work/key/extracted/Native Instruments/Massive X.dll` = 95,249,816 B、md5 `9b3f9107a7b2d7ccd9146622bb39eefb` (§12.12〜§12.14 と一致)。extract の checksum 不一致 125/125 は既知事象。
- 実行 (`tools/targets/massivex` 直下・rc 0): `python3 license/scripts/mx_dll_relscan.py` (測定 commit `1c89aa4b`・12.9 s・load 0.35 → 0.45)。`mx_indirect_refs.py --selftest` PASS (rc 0)、`mx_table_refs.py --selftest` PASS (rc 0)。
- 走査器 `license/scripts/mx_dll_relscan.py`: `.text` 60,154,310 B の全バイト位置で disp32 を次命令位置 (変位 4・5・6・8) として評価し、先頭が disp32 より前 (`q < p`)・末尾が disp32 の直後に一致する 1 命令が復号できるものだけを命令レベルの参照とする。絶対 8B・RVA 4B・自己相対 4B (フィールドの VA + 4B 値 == 対象 VA) は全ファイルの全バイト位置で走査する。陽性対照 2 件 (下記 (d)) で検出を確認。
- 本 fix で直した点: `ins.address <= p` を `<` に (偽ヒット `0x184fe852c` が消えた)。変位 6 (66 接頭辞 + imm16) を追加。`owner()` は end の前方最大値が va を超える間は手前へ遡る (表示のみ)。N6 文字列 6 件 (#1976 指定) を追加し、既存 8 件はラベルを「blob 先頭」に直した。自己相対 4B の走査を追加した。

**(a) x64 本体の `.pdata` 判定**

| 項目 | `.pdata` #0 (VA `0x185f3a000`) | `.pdata` #1 (VA `0x18615f000`) |
|---|---|---|
| VirtualSize / Raw ptr | `0x2231a0` / `0x541b400` (ファイル内) | `0x26ce8` / `0x7c5e800` (ファイル末尾 `0x5ad6598` より後) |
| 非ゼロのエントリ | 186,744 | 0 |
| 有効 (begin < end) | 186,731 | 0 |
| begin ∈ .text / end ∈ .text (有効の内) | 186,653 / 186,631 | — |
| 不正 end (.text 外) | 100 | — |
| unwind ∈ .xdata (非ゼロの全件中) | 186,626 | — |
| 隣接重なり (begin 順) | 29 組 (うち不正 end を含む 22 組) | — |
| unique (begin, end) / その隣接重なり | 186,730 / 28 | — |

- 定義: 「有効」は begin < end のエントリ。「∈ .text」は `.text` の `[VA, VA + VirtualSize)` への包含 (end が VirtualSize の末尾ちょうどのものは 0 件。`≤` で判定しても 186,631)。「隣接重なり」は有効エントリを begin 順 (同じ begin は end 順) に並べ、隣の begin < 手前の end となる組を数える。重複エントリ (同一の (begin, end)) も数える。「unique」は重複を除いた個数で、その隣接重なりは 28。
- 判定: x64 本体の関数表は `.pdata` #0。`.pdata` #1 はファイル内にエントリのバイトを持たず、関数表として成立しない。`mx_dll_callers.py` が先勝ちで使ったのも #0 で、§12.12 の結果は変わらない。
- 注記: #0 の不正な end 100 件は `.text` 外へ出る。`owner()` の表示はこの長い範囲に入る位置の所属も示すが、判定は (b) と (e) で `.text` 内の関数境界だけを使う。

**(b) テーブル基準候補の参照元 (§12.13 の「pdata 範囲外」を訂正)**

| 参照元 | 所属関数 (#0) | 命令 | call 先 (section) |
|---|---|---|---|
| `0x1831c9e45` | `0x1831c9bae`–`0x1831c9f6a` | `e8 90 df 95 00` `call 0x183b27dda` | `.rdata` (実行不可) |
| `0x1838565d3` | `0x1838544f0`–`0x183859834` (21,316 B) | `e8 70 b7 7c 00` `call 0x184021d48` | `.rdata` (実行不可) |

- 基準 `0x183b27dda`・`0x184021d48` を RIP 相対 (disp32 の全変位 4・5・6・8) で参照する命令は、いずれも `call` 1 件だけ (`control call` の生ヒットは変位 4 で 1 件、変位 5・6・8 では 0 件)。
- 判定: 両参照元は関数内にある (§12.13 の「pdata 範囲外」は誤り)。ただし指す命令は `call rel32` で、表基準 (RIP 相対の表参照) ではない。call の変位を RIP 相対データ参照として読んだ偶然一致であり、call 先が実行不可の `.rdata` のため実行経路にも乗らない。
- 表基準候補 4 件 (§12.12): 基準 `0x183b27dda` の 3 件 (N6-8 を指す表エントリ idx 236・244・249) と参照元 call 1 件 `0x1831c9e45` は、偶然一致と判定 ((b))。基準 `0x184021d48` の 1 件 (idx 239 → N6 文字列 `0x184fe84b3`) は、参照元 call `0x1838565d3` が `.rdata` を呼ぶことから偶然一致の可能性が高い。ただし表の一貫性は未確認のため判定を保留する (§12.13 を継続・未解決表へ)。

**(c) `0x1838544f0` の部分 decode の原因**

- 線形 decode は `0x1838545ba` の `85 00` (test) の直後の `00` (`0x1838545bc`) で、`00 49 b8` (`add byte ptr [rcx-0x48], cl`・3 B) と復号され、`0x1838545bd` の movabs (`49 b8 ...`・`movabs r8, 0x7ffffffffffffff`) と重なる。`0x1838545bd` から decode すると有効命令が続く。
- 原因: 命令境界そのものは未確定 (`0x1838545bc` がデータ・パディングか、直前の命令長の誤認かは未確認)。
- 影響: (d) の命令境界に依らない走査で `.text` 全体を再走査済み。この関数内にも N6 読み手への参照は無い。

**(d) 命令境界に依らない参照走査 (`mx_dll_relscan.py`・測定 commit `1c89aa4b`)**

| 対象 | 命令レベルの参照 (変位 4・5・6・8) | 絶対 8B / RVA 4B (全ファイル) | 自己相対 4B (全ファイル) |
|---|---|---|---|
| N6 読み手 8 件 (`0x180167a70` … `0x181133db0`) | 0 件 (復号できない生ヒットは 3 件: N6-4・N6-5・N6-7 の各 1 件) | 各 1–2 件。すべて `.pdata`・`.xdata` の範囲表 (呼び出し元ではない) | 1 件 (N6-8 ← `.rdata` `0x18470e211`・(e)) |
| N6 文字列 blob 先頭 8 件 (§12.12) | 読み手の内部からの読み取りのみ (下記) | 0 件 | 3 件 (`0x184fe83b7` ← `.rdata` `0x184f98a2d`・`0x184fe83fc` ← `.rdata` `0x184f94349`・`0x184fe7870` ← `.text` `0x181733070`・(e)) |
| N6 文字列 6 件 (#1976 指定) | 0 件 (生ヒット 3 件はいずれも命令として復号できない) | 0 件 | 2 件 (`0x184fe83de` ← `.rdata` `0x183a9828a`・`0x184fe84e8` ← `.rdata` `0x184f98b5d`・(e)) |
| N5 文字列 4 件 (UTF-16 `0x18414cd91` を含む) | 0 件 | 0 件 | 0 件 |
| 陽性対照 `0x183b27dda`・`0x184021d48` | 各 1 件 (`0x1831c9e46`・`0x1838565d4` の `call`) | 0 件 | 0 件 |

アドレスは disp32 の位置 (命令先頭はその 1〜3 バイト手前)。N6 文字列 blob 先頭の参照元 (すべて読み手の内部):
- `0x184fe8fa0` ← `0x180167ab0` (N6-1)
- `0x184fe83b7` ← `0x180f84a06` (N6-2)
- `0x184fe83fc` ← `0x181130e6c` (N6-4)
- `0x184fe845c` ← `0x18113305c` (N6-7)
- `0x184fe84b3` ← `0x181130de9` (N6-4)・`0x181133085`・`0x1811330f2`・`0x181133159` (N6-7)・`0x181133df6` (N6-8)
- `0x184fe8506` ← `0x18113334e` (N6-7)
- `0x184fe854a` ← `0x181131075` (N6-5)
- `0x184fe7870` ← `0x181130b6f` (N6-3)・`0x18113271c` (N6-6)

- 追加: DLL の export は 3 件 (`NICreatePlugInInstance` `0x18000b650`・`VSTPluginMain` `0x18000b7a0`・`factoriesListGetter` `0x181177040`)。読み手 8 件と N5 読み手は export ではない。

**(e) 自己相対 4B の判定**

- 基準: (i) フィールドの VA が 4 の倍数でない (非整列)、(ii) 前後 24 entry (4B 刻み・計 48) のうち、関数先頭 (`.pdata` の begin) を指すものが 0 件 (表なら関数先頭が並ぶ)、(iii) `.text` を指す数 (無作為なら期待値は 48 × 60,154,310 / 2^32 = 0.67)。

| 自己相対 hit (フィールド → 対象) | 所属関数 | VA % 4 | 前後 24 の `.text` 指し / 関数先頭指し | 判定 |
|---|---|---|---|---|
| `.rdata` `0x18470e211` → N6-8 `0x181133db0` | — | 1 | 1 / 0 | 偶然一致 |
| `.rdata` `0x184f98a2d` → blob `0x184fe83b7` | — | 1 | 0 / 0 | 偶然一致 |
| `.rdata` `0x184f94349` → blob `0x184fe83fc` | — | 1 | 0 / 0 | 偶然一致 |
| `.rdata` `0x183a9828a` → 文字列 `0x184fe83de` | — | 2 | 0 / 0 | 偶然一致 |
| `.rdata` `0x184f98b5d` → 文字列 `0x184fe84e8` | — | 1 | 0 / 0 | 偶然一致 |
| `.text` `0x181733070` → blob `0x184fe7870` | `0x181732bd0` | 0 | 5 / 0 | 表ではない (読み出し側は未確定) |

- 判定: `.rdata` の 5 件は非整列で、前後に関数先頭を指す entry が無いため、表としては成立しない。N6-8 の 1 件は読み手 8 件への呼び出し元ではなく偶然一致と判定する (受入条件 2 の判定に含める)。
- `.text` `0x181733070` は VA が 4 の倍数で、近傍 5 件が `.text` を指す (期待値 0.67 より多い)。ただし関数先頭は 0 件で、値は散らばっている。所属 `0x181732bd0` は N6 読み手 8 件ではない。表ではないと判定するが、この値を読む経路は未確認のため #2195 の未解決とする。

**判定**
- 受入 1 (N5 読み手の特定): **未達**。N5 の 4 文字列は、命令レベル (変位 4・5・6・8)・絶対 8B・RVA 4B・自己相対 4B のいずれでも参照 0 件。
- 受入 2 (N6 読み手 8 件の呼び出し元の確定): **未達**。本走査が見たのは次の形式だけ: 直接 call/jmp/jcc・RIP 相対 (変位 4・5・6・8)・絶対 8B・RVA 4B・自己相対 4B と、表基準候補 (b)。読み手 8 件への参照は、命令・絶対・RVA では 0 件、自己相対は (e) の 1 件のみで偶然一致、表基準は (b) で偶然一致。文字列 index・関数ポインタを計算で作る経路・暗号化された表は見ていない。静的な参照形式では呼び出し元が見つからない。
- 差し替え点 (`mx_lic_stub.py` の RULES): 未確定のまま (呼び出し元が無いため、呼び出し側に差し替え点を置けない)。
- 残件の起票先: #2195 [MX-32] (PR 本文の未解決表の 4 行)。残る作業は静的走査の外 (動的な確認手段) である。
- e2e (wasm) は本 run で対象コードを変えていないため未実行 (§12.6・§12.10 が正本)。

### 12.16 MX-32 (#2195) の間接参照走査: N5 読み手・N6 呼び出し元は未確定 (測定 commit `2fbba3c4`・2026-10-15)

- 素材: `plugins-massivex` → `$RUNNER_TEMP/mx` → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> work/key key`。DLL = 95,249,816 B、md5 `9b3f9107a7b2d7ccd9146622bb39eefb` (§12.12〜§12.15 と一致)。
- 走査器 `license/scripts/mx_dll_indirect.py` (新規・`--selftest` PASS rc 0)。測定 commit `2fbba3c4` (ラベル入替と未使用変数の削除。コード変更の最後)。実行 `python3 license/scripts/mx_dll_indirect.py` (rc 0・実測 9 min 13 s (00:25:15→00:34:28 UTC)・load 1.00 (終了時の 1 分平均))。出力は `work/mx_dll_indirect_2fbba3c4.out` のみ (非コミット)。測定後のコード差分 `git diff 2fbba3c4 HEAD -- tools/targets/massivex/license/scripts/mx_dll_indirect.py` は 0 行。同じ `license/scripts` 内で main 取り込みにより変わった `mx_table_refs.py`・`mx_dll_table_refs.py` は走査器から import されない (走査器の import は標準・capstone・numpy・pefile のみ) ため、再測定は行わない。
- 検出条件: `.text` の全バイト位置で disp32 を変位 4・5・6・8 の RIP 相対として評価し、復号できる命令が RIP 相対 mem を持つもの、または `.text` 内を指す rel32 の call/jmp/jcc だけを採用 (`.rdata` への call は復号の誤りとして除外)。

| 項目 | 結果 |
|---|---|
| S1 RIP 相対 (領域内の任意 offset) | N5 blob `[0x184862000,0x184863000)` 25 件・N5 UTF-16 `[0x18414c000,0x18414e000)` 5 件・N6 blob `[0x184fe7000,0x184fe9000)` 237 件・N6 blob2 `[0x184ffc000,0x184ffe000)` 246 件 |
| S1 うち N5 文字列 span `[0x184862d19,0x184862f10)` / `MXDemoPopup.qml` UTF-16 `[0x18414cd91,0x18414cdb5)` への参照 | 0 件 / 0 件 |
| 領域内の絶対 8B・RVA 4B (全セクション) | N5 blob: abs8 2 件 (`.rdata` `0x184863628`・`0x184863630` が `0x184862ab0`・`0x184862fa0` を指す。N5 の開始位置ではない)・rva4 5 件。UTF-16 領域: abs8 0・rva4 126 件 (整列・表の裏付けは未判定) |
| S2 表 (RIP mem の実効先 B 106,737 件、B から 2048 entry の 4B 符号付き・2B 符号付き/符号なし) | N5 `0x184862d19` 2 件・`0x184862e67` 3 件・`0x184862e7a` 3 件・UTF-16 0 件。N6 読み手 8 件は各 0 件。N6 文字列 8 件は 36〜332 件 |
| S2 対照 (同じ領域内の非文字列 VA 各 8 件) | N5 近傍 3〜31 件・N6 近傍 48〜362 件。対象の件数は対照と同じ水準のため、偶然一致と判定 |
| S3 読み出し経路 | `0x181733070`: RIP 0・abs8 0・rva4 0 (読み出し元なし)。`0x184021d48`: RIP 0 (唯一の参照は `0x1838565d3` (`e8 70 b7 7c 00`) の `call 0x184021d48`。走査器は `.text` 外への call を除外するため出力に現れない。この 1 件は走査器の外のインライン確認 (capstone で `0x1838565d3` から復号)。`.rdata` への call のため偶然一致) |

- **ラベルの訂正**: `0x184862d19` は `demoExpiredChanged`、`0x184862e67` は `demoExpired` (文字列ダンプで確認)。§12.12〜§12.15 と `mx_dll_relscan.py` の N5 ラベルは入れ替わっている。アドレスは正しい。`mx_dll_table_refs.py` のラベルは正しい。走査器 `mx_dll_indirect.py` の N5 ラベルは commit `2fbba3c4` で入れ替えた (旧版の S2 出力は逆に出ていた。新版: `target N5 demoExpiredChanged 0x184862d19: 2 件`・`target N5 demoExpired 0x184862e67: 3 件`)。
- **N5 文字列の正体 (仮説・未検証)**: `0x184862c78` の `Lechtal::MX::Gui::MXFrameController` に続く NUL 区切りの名前列 (`demoPopupVisibleChanged`・`demoExpiredChanged`・`demoExpired`・`subscriptionExpired` …) は Qt の moc 文字列表の形。N5 の 4 文字列は Qt メタオブジェクトの名前で、読み手は個別の関数ではなく Qt の meta-object 機構 (インデックス・オフセット経由) の可能性が高い。UTF-16 `MXDemoPopup.qml` も Qt リソース名の列の一部。どちらも VA を直接指す参照は作られないため、本走査では捉えられない。

- **`0x1838544f0` の部分 decode の原因 (確定)**: `0x1838545ba` の `85 00` (test dword ptr [rax], eax・2 B) は閉じている。`0x1838545bc` の単独の `00` は直前の命令の続きではない。線形復号はこれを `add byte ptr [rcx-0x48], cl` (`00 49 b8`・3 B) として取り、`0x1838545bd` の `movabs r8, 0x07ffffffffffffff` (`49 b8` + 8 B) の REX (`49`) を食う。以後 `ff` が続き、`0x1838545bf` から invalid になる (スクリプト外のインライン確認: 関数先頭からの線形で invalid 115 件)。`0x1838545bd` から復号すると `0x1838545c7` (`cmp byte ptr [rcx+0x19], r13b`) で整合する。`0x1838545bc` の 1 バイトを置いた理由 (データ・パディング・難読化) は未確定。
- `.pdata` の x64 本体判定は §12.15 (a) で確定済み (本節では再測定していない)。

判定:
- 受入 1 (N5 読み手の特定): **未達**。直接・RIP 相対・絶対・RVA・自己相対・表 (S2) のいずれでも、N5 span・UTF-16 `MXDemoPopup.qml` への参照は 0 件。読み手は Qt の meta-object 機構の可能性がある (仮説)。
- 受入 2 (N6 読み手 8 件の呼び出し元、`0x181733070` の読み出し経路、表 idx 239 の判定): **未確定**。直接 call/jmp (rel32)・RIP 相対・絶対・RVA・自己相対は §12.15 (b)(d)(e) の結果 (本走査は N6 読み手を直接の参照先として走査していない: S1 は領域単位、S2 は表のみ)。本走査の表 (S2) で N6 読み手 hit は 0 件。残るのは実行時にだけ決まる経路。`0x181733070` の読み出し元は 0 件、表基準 `0x184021d48` の RIP 参照は 0 件のため、idx 239 の判定は偶然一致とする (根拠は読み出し経路が無いこと)。
- 受入 3 (`0x1838544f0` の部分 decode の原因): **確定** (上記)。
- 受入 4 (2 つの `.pdata` の実測と x64 本体の決定): **確定**。§12.15 (a) の結果 (測定 commit `1c89aa4b`・main 取り込み済み)。本節では再測定していない。
- 差し替え点 (`mx_lic_stub.py` の RULES): 未確定のまま変更しない (呼び出し元が無いため、呼び出し側に差し替え点を置けない)。
- e2e (wasm) は本 run でコードを変えていないため未実行。
- 未解決 (起票先 #1977・差し替え点決定の入力。#2195 は本 PR で閉じる): (1) N5 読み手: Qt moc 文字列表 (`MXFrameController`) の構造と、その表を指す `staticMetaObject`・`qt_static_metacall` の逆引き。手がかり: `.rdata` `0x184863628`・`0x184863630` の abs8 が N5 blob 内 `0x184862ab0`・`0x184862fa0` を指す (S1)。(2) N6 呼び出し元と `0x181733070` の読み出し経路・表 idx 239: 実行時の呼び出し記録 (動的な確認手段) の選定。(3) `0x1838545bc` の 1 バイトの由来: 参照走査には影響しないため起票しない (本節に記録のみ)。
