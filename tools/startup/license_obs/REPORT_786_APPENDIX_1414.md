# 付録 — #1414 (#786 受入 2): 0x10d3a30 が gradeChar を書く条件 (戻り値スタブ)

日付: 2026-10-15 / 起点: `origin/main` (93307cc6a) / 素材: `fl-win64` (`block00031_PE.bin`) /
再現: `python probe_1414_writecond.py` (約 40 秒・rc 0・結果 `results/probe_1414_writecond.json`)。
REPORT_786 §12.2 (F2・F3 が 0x10c7850 の中で停止) の続き。0x10c7850 の戻り値だけを固定し、その中身は実行しない。

## 1. 結論

- 0x10d3a30 が gradeChar を `?` (0x3f) に書くのは、次の 2 条件がともに成り立つとき (機械語で確認。7 ケースで予測と一致)。
  1. 入口で `[g1] != 0x7fffffff` または `[g2] != 0`。両方とも既定値 (sentinel・0) なら、0x10c7850 を呼ばずに `xor eax,eax` で戻る。
  2. 0x10c7850 の戻り値 `eax` (符号付き) が **0 以下**。`mov [g3],eax` で格納した後、`cmp [g4],0` の判定で書く。
- g3・g4 は g1 と同じ dword (0x14f852c) を指す (§2)。よって 0x10d3a30 の中では、0x10c7850 の戻り値がそのまま次回の g1 になる (§3 の W3・W5・W7 で `g1_after` が戻り値と一致)。
- 実機経路の 6 入力では 0x10d3a30 が未到達 (REPORT_786 §8.1) のため、6 入力で '?' が書かれないことは条件 2 の検証にならず、条件 2 では説明できない。6 入力で観測した 0x10c7850 の戻り値 0x7fffffff は呼出し元 0x10c9bf2 での値で、0x10d3a30 からの戻り値ではない。
- 未確定 (起票先は §8): (a) 0x10c7850 が 0 以下を返す入力、(b) 実機の経路で 0x10d3a30 の入口 (条件 1) に届く条件、(c) 0x11cb000 の起動元。

## 2. 静的: 0x10d3a30 (91 B) の rip 相対参照

| 命令 | スロット | 指す先 (イメージ上の値) | 役割 |
|---|---|---|---|
| 0x10d3a34 `mov rax,[rip+0x50da6d]` | 0x15e14a8 | 0x14f852c | g1 (`cmp dword [rax],0x7fffffff`) |
| 0x10d3a43 `mov rax,[rip+0x510336]` | 0x15e3d80 | 0x16b6e58 | g2 (`cmp byte [rax],0`) |
| 0x10d3a58 `mov rcx,[rip+0x50da49]` | 0x15e14a8 | 0x14f852c | g3 (`mov [rcx],eax` の格納先) |
| 0x10d3a61 `mov rax,[rip+0x50da40]` | 0x15e14a8 | 0x14f852c | g4 (`cmp dword [rax],0`) |
| 0x10d3a72 `mov rcx,[rip+0x510d17]` | 0x15e4790 | 0x141d6b8 | g5 (`*(0x141d6b8)` が gradeChar の親オブジェクト。格納先は `*(*(0x141d6b8)+0xd0)`) |

- g1・g3・g4 は同一 dword。g2 は別の byte。
- 関数の骨格: `sub rsp,0x28` → g1 判定 → g2 判定 → 早期 `xor eax,eax; jmp 0x10d3a86` → `call 0x10c7850; mov [g3],eax` → `cmp [g4],0; setle al; test al,al; je 0x10d3a86` → `mov rcx,[g5]; mov rcx,[rcx]; mov rcx,[rcx+0xd0]; mov byte [rcx],0x3f` (0x10d3a72〜0x10d3a83 の 4 命令。格納先 = `*(*(0x141d6b8)+0xd0)`) → `add rsp,0x28; ret`。
- `setle` の後に `test al,al` が続くので、`je` は「値 > 0」のとき飛ぶ。書込みは値 ≤ 0 (符号付き) のときだけ。

## 3. 動的: 0x10c7850 の戻り値を固定 (W1〜W7)

0x10c7850 の入口に code hook を張り、eax を固定値にして呼出し元へ戻す (本体は実行しない)。g1・g2 は入口で直接書き込む。gradeChar の初期値は 0x40。

| ケース | g1 入力 | g2 入力 | 戻り値 (固定) | 0x10c7850 呼出し | gradeChar (後) | 書込み | 予測 | 一致 |
|---|---|---|---|---|---|---|---|---|
| W1 | 0x7fffffff | 0 | (呼ばれない) | 0 | 0x40 | 無 | 無 | ✓ |
| W2 | 0x7fffffff | 1 | 0x7fffffff | 1 | 0x40 | 無 | 無 | ✓ |
| W3 | 0x7fffffff | 1 | 0 | 1 | 0x3f | 有 | 有 | ✓ |
| W4 | 0 | 0 | 0x7fffffff | 1 | 0x40 | 無 | 無 | ✓ |
| W5 | 0 | 0 | -1 | 1 | 0x3f | 有 | 有 | ✓ |
| W6 | 0 | 1 | 1 | 1 | 0x40 | 無 | 無 | ✓ |
| W7 | 0 | 1 | INT_MIN (0x80000000) | 1 | 0x3f | 有 | 有 | ✓ |

予測 = 「呼ばれる (条件 1) かつ 戻り値 ≤ 0」。W3・W5・W7 の後の g1 は、それぞれ戻り値 (0・-1・INT_MIN) と一致する。

## 4. 検証 (測定 commit: `0e6168b67` = コードを変えた最後の commit)

| 項目 | 実測 |
|---|---|
| `probe_1414_writecond.py` 単体 (0e6168b67) | 39.6 秒・rc 0・`all_match True` (W1〜W7 全一致) |
| `bash license_obs.sh` (0e6168b67・素材 fl-win64・load average 1 分値 0.42 → 1.02) | 2 分 45.9 秒・rc 0・`ALL OK`・`RESULT ALL PASS`・PASS 行 40 件・FAIL 0 |
| 同条件の先行実行 (93307cc6a・新 probe は未コミットで license_obs.sh は呼ばない・load average 0.66 → 0.98) | 2 分 46.6 秒・rc 0・`ALL OK`・`RESULT ALL PASS`・PASS 行 40 件・FAIL 0 |
| `probe_1414_writecond.py` (HEAD `285058310`・main 取り込み後) | 41 秒・rc 0・`all_match True` (W1〜W7 全一致) |
| `bash license_obs.sh` (HEAD `285058310`・素材 fl-win64 全展開・load average 1 分値: probe 直後 0.52 → 終了直後 0.97) | 2 分 50 秒・rc 0・`ALL OK`・`RESULT ALL PASS`・PASS 行 40 件・FAIL 0 |

- 差分: `git diff 0e6168b67 HEAD -- tools/startup/license_obs` の md 以外 (`*.py`・`*.sh`・`*.json`) は 0 行。`tools/startup/vreg/ilreg`・`tools/shared/paths.py` (license_obs が読む経路) も 0 行。測定の後にコードは変えていない (後続の変更は REPORT (.md) と DOC_MAP のみ)。

## 5. 受入 1 の探索: 表の基底の参照と間接 call (本 PR で追記)

再現: `python probe_1414_tables.py --dyn --write` (7c246e7eb で 50.3 秒・rc 0・結果 `results/probe_1414_tables.json`)。
表 T1 は `0x11740f5`〜 (42 件・終端 `0x1174245`)、T2 は `0x1378820`〜 (826 件・終端 `0x137a1f0`)。

| 項目 | 実測 |
|---|---|
| 表の基底 (`0x11740f5`・`0x1378820`) を指す rip 相対・即値・データ中の 8 バイト値 (全 8 オフセット) | **0 件** |
| 表の範囲 ±0x100 内を rip 相対で指す命令 | 2 件 (0x1083750・0x1251063 が `0x1174310` を読む。表の終端の外 0xcb バイトの別オブジェクト) |
| 表の範囲 ±0x100 内の値を持つデータ中の 8 バイト | 9 件 (基底ではない。終端 `0x1174245` を指す値 1 件を含む: file offset `0xd67218`。走査の begin/end 対の一部かは未確認) |
| 0x10c7cd0 内の間接 call (`call qword [reg+disp]`) の静的全件 | **298 件** (base `rax` 165・`rbx` 130・`rsi` 2・`rbp` 1・index は全件無し) |
| 6 入力で実行された間接 call サイト (入力別) | A1 33 / A2 33 / B1 37 / B2 37 / D2 33 / D1 37 |
| 6 入力の実行サイトの和集合 (`dyn_union`) | **41 件**。静的 298 件のうち未実行は **257 件** |
| 実行サイトで object 先頭値 (`[reg]`) が表の範囲に入った件数 | **0 件** (6 入力とも) |

- 静的にも動的にも、表の基底を引く参照は見つからなかった。298 件の間接 call は vtable 風の形で、表を直接引く形ではない。
- 0x11cb000 自身も g1 を読む (`cmp dword [g1], 0x7fffffff` at 0x11cce0c・`je 0x11cd141`)。表の関数は残日数の sentinel を見る関数の一つ。
- 前版 (3b22d1d3b) の「未実行 261 件 (298 − 実行 37)」は誤り。37 は入力 1 件あたりの最大値で、和集合ではない。`probe_1414_tables.py --dyn` が和集合 (`dyn_union`) を出すようにした。
- 前版の `text_refs_near` にあった `kind: rva` 10 件は、rip 相対の disp と直接 call の VA を RVA と読んだ誤検出だった。probe で除き、残りは rip 2 件 (表の基底を指す参照 0 件は変わらない)。
- 未試行 (起票 #3727): 未実行の 257 件 (298 − 和集合 41) の入力条件、表の終端 `0x1174245` を指す値の役割、0x10c7cd0 の上流 (0xc4dba0・0xd18130・0xed7c00)。

## 6. 受入 3 の探索: g1 のスロットの参照 42 箇所 (本 PR で追記)

g1 のスロット `0x15e14a8` を rip 相対で読む命令は 42 件。その直後に `[g1]` を使う命令を分類した (`probe_1414_tables.py` の `g1_refs`)。
g1 の dword (`0x14f852c`) を rip 相対で直接指す命令は 0 件 (既知)。

| 分類 | 件数 | 内訳 |
|---|---|---|
| 書込み (`mov dword [reg], eax`) | **2** | 0x10c9bf9 (0x10c7cd0 内。直前の `call 0x10c7850` (0x10c9bed) の戻り値 eax を格納)・0x10d3a5f (0x10d3a30 の g3 格納) |
| 比較 (`cmp dword [g1], c`) | 36 | 定数: 0x7fffffff 9・7 11・0 12・0x1e (30) 2・1 1・0x3c (60) 1。15 関数 |
| 読込み後に構造体へ複写 | 4 | 0xefb3be・0x10d15d3・0x11f1785・0x124f147 (`mov [rbp+X], eax`) |

- g1 への書込みは 0x10c7cd0 の 0x10c9bf9 (0x10c7850 の戻り値) だけで、6 入力では 0x7fffffff が格納される (REPORT_786 §8.2 と一致)。
- 閾値 7・30・60 と sentinel 0x7fffffff の並びから、g1 は「残日数」(期限までの日数。0x7fffffff は期限なし・未設定) と推定する。推定のまま。
- 0x10d3a30 の書込み条件 (§1: 戻り値 ≤ 0 で `?`) は、「残日数 ≤ 0 (期限切れ) で gradeChar を `?` にする」と読むと整合する。確定は子 #3725 (原文の受入 3)。

## 7. 検証 (測定 commit: `7c246e7eb` = コードを変えた最後の commit)

| 項目 | 実測 |
|---|---|
| `probe_1414_tables.py --dyn --write` (7c246e7eb) | 50.3 秒・rc 0・間接 call 298・g1 参照 書込み 2 / 比較 36 / 複写 4・動的 vtable 一致 0 (6 入力)・和集合 41 (未実行 257)・`text_refs_near` 2 件 (rip のみ) |
| `bash license_obs.sh` (7c246e7eb・素材 fl-win64 の `extracted/block00031_PE.bin` を展開して使用・load average 1 分値 0.63 → 0.96) | 2 分 16.5 秒・rc 0・`ALL OK`・`RESULT ALL PASS`・PASS 40・FAIL 0 |

- 測定 commit から HEAD までのコード差分 (`git diff 7c246e7eb HEAD -- tools/startup/license_obs ':!*.md'`) は 0 行 (出力は空)。
- 前版 (3b22d1d3b) の測定は、probe の出力 (`dyn_union` の追加・`text_refs_near` の 12 → 2 件) が変わったため、本節で置き換えた。

## 8. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x11cb000・0x10d50d0 の起動元 (表 T1/T2 の基底の由来・未実行の間接 call 257 件の入力条件) | 原文の受入 1 (#3727 に原文のまま載せた) | #3727 [ST-2] |
| 0x10d3a30 の実機経路 (入口で g1 ≠ sentinel または g2 ≠ 0 に届く条件。0x11fc770 の上流) | 新規 (旧受入 2 は PR #3484 で達成済み。残りではない) | #3727 [ST-2] |
| 0x10c7850 の戻り値の計算式 (0 以下を返す入力) | 新規 (0x10d3a30 の書込み条件の上流) | #3725 [ST-1] |
| g1 の意味 (sentinel・閾値 7/30/60 の読み方) | 原文の受入 3 (推定のみ) | #3725 [ST-1] |

- 子 issue の本文には、#1414 の原文の受入 (userContentEdits の 2026-10-13T21:57:43Z の版) を原文のまま載せた。原文にない項目は「新規」と明記した。
- 依頼者の .reg 素材 (#785) は本件の入力には使わない。

## 9. #3727 受入 2: 0x10d3a30 の上流 (呼出し元の遡及・本 PR で追記)

再現: `python probe_1414_callers.py --dyn --write` (結果 `results/probe_1414_callers.json`)。静的は rel32 の `call` のみ。

| 段 | 呼出し元 (直接・rel32) | 件数 | 6 入力で到達 |
|---|---|---|---|
| 0x10d3a30 | 0x10cf498 (0x10c7cd0 内・g6 gate)・0x11fd457・0x11fe627 (0x11fc770 内) | 3 | 0 (0x10c7cd0 の entry のみ 6 入力で到達) |
| 0x11fc770 | 0xc4e49e (0xc4dba0 内)・0xd1a996 (0xd18130 内)・0xed7c32 (0xed7c00 内) | 3 | 0 |
| 0xc4dba0 | 0xc4f32e (0xc4ecf0 内) | 1 | 0 |
| 0xd18130 | 0xd1d656 (0xd1d3d0 内)・0xd1f026 (0xd1efd0 内) | 2 | 0 |
| 0xed7c00 | 0 (rel32 の call/jmp 参照は無し。0xed7c00 は 0xed83c5 で 0xd1efd0 を call する側。0xd1efd0 は 0xd18130 の呼出し元) | 0 (直接) | 0 |

- 深さは呼出し辺の数で数える。0x10d3a30 ← 0x11fc770 (1) ← 0xc4dba0・0xd18130 (2) ← 0xc4ecf0・0xd1d3d0・0xd1efd0 (3)。深さ 3 までを列挙し、深さ 3 の関数の呼出し元は遡っていない (0xd1efd0 の呼出し元は 0xed83c5 (0xed7c00 内) だが、表の深さ外)。
- 上の表は `probe_1414_callers.py --dyn --write` の出力 (`results/probe_1414_callers.json`) から作った。

- 6 入力 (`probe_1414.CASES`) の unicorn code hook: 0x10d3a30・0x11fc770・0xc4dba0・0xd18130・0xed7c00 は 6 入力とも未到達 (hit 0)。到達したのは 0x10c7cd0 の entry (6 入力とも 1 回) のみ。
- 0x10d3a30 の入口 (条件 1) の実機経路は未特定。0xed7c00 は直接呼出し 0 件のため、関数ポインタ経由と推定 (未確認)。
- 静的 `probe_1414_tables.py` の再現 (本 PR で再測定): 間接 call 298・動的 `dyn_union` 41・未実行 257・vtable hit 0 (6 入力)。前回の値と一致。
- 受入 1 (0x11cb000 / 0x10d50d0 の起動元) は未達。表 T1/T2 の基底を指す参照は静的に 0 件 (§5 と同じ)。6 入力では 0x10c7cd0 の間接 call が表を引かない。
- 未実行 257 件の入力条件は、本探索では特定していない (6 入力の seed からは未到達)。

## 10. 未解決 (#3727 残り)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x11cb000・0x10d50d0 の起動元 (表 T1/T2 の由来・未実行の間接 call 257 件の入力条件) | 受入 1 未達 | #3727 (部分達成のため Refs) |
| 0xed7c00 の起動元 (直接呼出し 0 件・関数ポインタ経由と推定) | 0x10d3a30 の上流の終端が未確定 | #3727 |
| 0x10d3a30 の入口に実機経路で届く入力 (6 入力では 0x11fc770 系が未到達) | 受入 2 の入力条件が未確定 | #3727 |
