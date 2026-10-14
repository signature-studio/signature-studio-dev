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

### 12.15 #1976 残件の実測: x64 本体の `.pdata` 確定と命令境界に依らない参照走査 (MX-32 #2195・測定 commit `1b079671`・2026-10-14)

- 素材: `plugins-massivex` → `$RUNNER_TEMP/mx` → `scripts/parse_setup_headers.py <exe> work/key` → `scripts/extract_massivex.py <exe> work/key key`。`work/key/extracted/Native Instruments/Massive X.dll` = 95,249,816 B、md5 `9b3f9107a7b2d7ccd9146622bb39eefb` (§12.12〜§12.14 と一致)。extract の checksum 不一致 125/125 は既知事象。
- 実行 (`tools/targets/massivex` 直下・rc 0): `python3 license/scripts/mx_dll_relscan.py` (7.4 s・load 0.35)。`mx_indirect_refs.py --selftest` PASS、`mx_table_refs.py --selftest` PASS。
- 新規走査器 `license/scripts/mx_dll_relscan.py`: `.text` 60,154,310 B の全バイト位置で disp32/rel32 を次命令位置 (変位 4・5・8) として評価し、その位置を末尾に持つ 1 命令が復号できるものだけを命令レベルの参照とする。全ファイルの絶対 8B・RVA 4B も全バイト位置で走査する。線形・関数単位の逆アセンブル (§12.12 の `mx_dll_callers.py`) が desync する箇所の取りこぼしを補う。陽性対照 2 件 (下記) で検出を確認。

**(a) x64 本体の `.pdata` 判定**

| 項目 | `.pdata` #0 (VA `0x185f3a000`) | `.pdata` #1 (VA `0x18615f000`) |
|---|---|---|
| VirtualSize / Raw ptr | `0x2231a0` / `0x541b400` (ファイル内) | `0x26ce8` / `0x7c5e800` (ファイル末尾 `0x5ad6598` より後) |
| 非ゼロのエントリ (有効 = begin < end) | 186,744 (有効 186,731) | 0 (ファイル内にバイトが無い) |
| begin が `.text` 内 / end が `.text` 内 | 186,653 / 186,630 | — |
| unwind の RVA が `.xdata` 内 | 186,626 (全 186,744 件中) | — |

判定: x64 本体の関数表は `.pdata` #0。`.pdata` #1 はファイル内にエントリのバイトを持たず、関数表として成立しない。`mx_dll_callers.py` が先勝ちで使ったのも #0 で、§12.12 の結果は変わらない。
- 注記: #0 には `.text` 外へ出る不正な end が 100 件あり (例 `0x1800e1db0`–`0x1c29b16e9`)、重なり 29 組のうち 22 組がそれを含む。(b) の所属判定は両方とも `.text` 内の関数境界だけを使う。

**(b) テーブル基準候補の参照元 (§12.13 の「pdata 範囲外」を訂正)**

| 参照元 | 所属関数 (#0) | 命令 | call 先 (section) |
|---|---|---|---|
| `0x1831c9e45` | `0x1831c9bae`–`0x1831c9f6a` | `e8 90 df 95 00` `call 0x183b27dda` | `.rdata` (実行不可) |
| `0x1838565d3` | `0x1838544f0`–`0x183859834` (21,316 B) | `e8 70 b7 7c 00` `call 0x184021d48` | `.rdata` (実行不可) |

判定: 両参照元は関数内にある (§12.13 の「pdata 範囲外」は誤り)。ただし指す命令は `call rel32` で、表基準 (RIP 相対の表参照) ではない。call の変位を RIP 相対データ参照として読んだ偶然一致であり、call 先が実行不可の `.rdata` のため実行経路にも乗らない。テーブル基準候補 4 件は偶然一致と判定する (§12.13 の判定を確定)。

**(c) `0x1838544f0` の部分 decode の原因**

- 線形 decode は `0x1838545ba` の `85 00` (test) の直後の 1 バイト `00` (`0x1838545bc`) で desync し、`0x1838545bd` の `movabs r8, 0x7ffffffffffffff` (`49 b8 ...`) と重なる。`0x1838545bd` から decode すると有効命令が続く。
- 原因: `0x1838545bc` の 1 バイトが命令になっていない (データ・パディング、または直前の命令長の誤認)。命令境界そのものは確定していない。
- 影響: (d) の命令境界に依らない走査で `.text` 全体を再走査済み。この関数内にも N6 読み手への参照は無い。

**(d) 命令境界に依らない参照走査 (`mx_dll_relscan.py`・測定 commit `1b079671`)**

| 対象 | 命令レベルの参照 (call/jmp/jcc/RIP 相対 lea・movups) | 絶対 8B / RVA 4B (全ファイル) |
|---|---|---|
| N6 読み手 8 件 (`0x180167a70` … `0x181133db0`) | 0 件 (変位 4・5・8 とも) | 各 1–2 件。すべて `.pdata`・`.xdata` の範囲表 (呼び出し元ではない) |
| N6 文字列 8 件 | 読み手の内部からの読み取りのみ (下記) | 0 件 |
| N5 文字列 4 件 (UTF-16 `0x18414cd91` を含む) | 0 件 | 0 件 |
| 陽性対照 `0x183b27dda`・`0x184021d48` | 各 1 件 (`0x1831c9e46`・`0x1838565d4` の `call`) | 0 件 |

アドレスは disp32 の位置 (命令先頭はその 1〜3 バイト手前)。N6 文字列の参照元 (すべて読み手の内部):
- `0x184fe8fa0` ← `0x180167ab0` (N6-1)
- `0x184fe83b7` ← `0x180f84a06` (N6-2)
- `0x184fe83fc` ← `0x181130e6c` (N6-4)
- `0x184fe845c` ← `0x18113305c` (N6-7)
- `0x184fe84b3` ← `0x181130de9` (N6-4)・`0x181133085`・`0x1811330f2`・`0x181133159` (N6-7)・`0x181133df6` (N6-8)
- `0x184fe8506` ← `0x18113334e` (N6-7)
- `0x184fe854a` ← `0x181131075` (N6-5)
- `0x184fe7870` ← `0x181130b6f` (N6-3)・`0x18113271c` (N6-6)

- 追加: DLL の export は 3 件 (`NICreatePlugInInstance` `0x18000b650`・`VSTPluginMain` `0x18000b7a0`・`factoriesListGetter` `0x181177040`)。読み手 8 件と N5 読み手は export ではない。
- 対象外: 自己相対 4B のデータ参照 (§12.12・§12.14 の `.rdata 0x18470e211` 1 件など) は本走査に含めていない。

**判定**
- 受入 1 (N5 読み手の特定): **未達**。N5 の 4 文字列は、命令レベル (変位 4・5・8) と絶対 8B・RVA 4B のいずれでも参照 0 件。
- 受入 2 (N6 読み手 8 件の呼び出し元の確定): **未達**。直接 call/jmp/jcc・RIP 相対・絶対 8B・RVA 4B・表基準の各形式で、読み手への呼び出し元は 0 件。静的な参照形式では呼び出し元が見つからない。実行時にだけ決まる経路 (計算されたポインタ・暗号化された表など) の可能性はあるが、未確認。
- 差し替え点 (`mx_lic_stub.py` の RULES): 未確定のまま。呼び出し元が無いため、呼び出し側に差し替え点を置けない。
- 残件の起票先: N5 読み手と N6 読み手の呼び出し元 → #2195 [MX-32] (本 run の結果を反映)。残る作業は静的走査の外 (動的な確認手段) である。
- e2e (wasm) は本 run で対象コードを変えていないため未実行 (§12.6・§12.10 が正本)。
