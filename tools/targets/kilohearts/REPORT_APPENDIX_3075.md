# REPORT 付録 (#1216 差し戻し round 4): merge 後 head での Stereo / Delay 再測定

`REPORT_APPENDIX.md` の 250 行上限のため分割した (内容は削除していない)。正本は本付録の §10-7p-3。

#### 10-7p-3. merge 後 head (`2a17665f`) での再測定 (round 4 B1)
- 測定 commit (コードを変えた最後の commit): `2a17665f` (origin/main `1b37410c` の取り込み merge)。`git diff 2a17665f HEAD -- tools/targets/kilohearts/ghidra_route` の出力: 0 行 (本 commit 時点)。
- 比較対象 (merge 前): `bcae3755` の converter を `git archive` で repo 外に展開。`snapins/lift`・`snapins/scripts` も同時に展開し、`PYTHONPATH` で `gen_simd` を読ませた (展開しないと `import gen_simd` で停止)。
- 環境: 素材 `plugins-kilohearts` (`HeartCore.core_64` 76,642,304 B)・`toolchain-emsdk`。[GHIDRA] 12.1.4 は repo 外で取得 (`ghidra_12.1.4_PUBLIC_20260921.zip`・sha256 `ddac49f9…d2db` 一致)。JDK 21。n=1。
- decompile: 151 関数 (stereo 8 ∪ delay 141 ∪ gain・haas・gate の 10 の和集合・番地昇順) → **151/151 OK** (`summary.tsv`・headless wall 35.2 s)。

| 入力 | merge 前 (`bcae3755`) C 行 | merge 後 (`2a17665f`) C 行 | C の cmp | emcc 件数 (前 → 後) |
|---|---|---|---|---|
| gain | 122 | 122 | **一致** | 未測定 (C 同一) |
| haas | 301 | 301 | **一致** | 未測定 (C 同一) |
| gate | 429 | 429 | **一致** | 未測定 (C 同一) |
| stereo | 891 | 914 | **差分 61 行** (rsqrtps 近似表 helper・`in_XMM3` の V128 化・`gd_` 参照) | 39 → **12** |
| delay | 7,247 | 7,248 | **差分 17 行** (rcpps helper の形・`maxps` の `gd_` 参照・V128 ポインタ化) | 602 → **577** |

- emcc: `emcc -c -ferror-limit=0 -I ghidra_route <name>.c`。`grep -c 'error:'` は各 log と census の合計が一致 (ドライバ行 0)。
- census (`emcc_census.py`・排他的。順に: 未関数化 callee・レーン型・引数数不一致・SIMD/AVX/swi・Win API・code 間接呼出・未定義 identifier・型不一致・その他):
  - Stereo 前 39 = 2・16・10・9・0・0・0・2・0 (REPORT §10-7p-2 と一致)。後 12 = 2・6・0・2・0・0・0・2・0。
  - Delay 前 602 = 5・201・108・61・0・21・17・187・2。後 577 = 5・191・108・46・0・21・17・187・2。
  - Delay 前の 602 は REPORT §10-7p-2 の 601 と 1 件違う。本 run は番地昇順で decompile しており、`REPORT_APPENDIX.md` の昇順 150 関数 = 602 と同じ傾向 (decompile の投入順で件数が変わる)。
- #3110 (`50661465`) の記録 Stereo 39 → 10 との関係: 本 run の merge 後は 12 で、2 件の差が残る。原因は未検証 (投入順・測定環境の差を疑うが確認していない)。

**1000 trial の扱い (round 4 B1 の 5)**
- Gain / Haas / Gate: C が merge 前と byte 一致 (cmp)。§10-7q ⑤ の 1000 trial をそのまま引き継ぐ。
- Stereo / Delay: C は変わったが emcc 未通過 (wasm 不成立) のため、1000 trial は実行不能。未実施のまま #3073 [KH-41] へ。

**子 issue の数値 (merge 後の census に合わせる)**
- #3094 [KH-42] = レーン型 191 (旧 138 / 200 の表記を訂正)。
- #3095 [KH-43] = SIMD・AVX・swi 46 (旧 61)。
- #3096 [KH-44] = 残り 340 (引数 108・型 187・code 21・未定義 17・未関数化 5・その他 2。不変)。
- #3108 [KH-45] = Stereo の残件 12 (merge 後)。#3108 の題名の 10 件は #3110 の記録。
