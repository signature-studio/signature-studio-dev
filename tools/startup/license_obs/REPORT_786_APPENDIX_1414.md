# 付録 — #1414 (#786 受入 2): 0x10d3a30 が gradeChar を書く条件 (戻り値スタブ)

日付: 2026-10-15 / 起点: `origin/main` (93307cc6a) / 素材: `fl-win64` (`block00031_PE.bin`) /
再現: `python probe_1414_writecond.py` (約 40 秒・rc 0・結果 `results/probe_1414_writecond.json`)。
REPORT_786 §12.2 (F2・F3 が 0x10c7850 の中で停止) の続き。0x10c7850 の戻り値だけを固定し、その中身は実行しない。

## 1. 結論

- 0x10d3a30 が gradeChar を `?` (0x3f) に書くのは、次の 2 条件がともに成り立つとき (機械語で確認。7 ケースで予測と一致)。
  1. 入口で `[g1] != 0x7fffffff` または `[g2] != 0`。両方とも既定値 (sentinel・0) なら、0x10c7850 を呼ばずに `xor eax,eax` で戻る。
  2. 0x10c7850 の戻り値 `eax` (符号付き) が **0 以下**。`mov [g3],eax` で格納した後、`cmp [g4],0` の判定で書く。
- g3・g4 は g1 と同じ dword (0x14f852c) を指す (§2)。よって 0x10d3a30 の中では、0x10c7850 の戻り値がそのまま次回の g1 になる (§3 の W3・W5・W7 で `g1_after` が戻り値と一致)。
- 実機経路の 6 入力 (REPORT_786 §8.1) では 0x10c7850 の戻り値が 0x7fffffff で、条件 2 を満たさない。6 入力で '?' が書かれないのは、この条件から説明がつく。
- 未確定 (起票先は §5): (a) 0x10c7850 が 0 以下を返す入力、(b) 実機の経路で 0x10d3a30 の入口 (条件 1) に届く条件、(c) 0x11cb000 の起動元。

## 2. 静的: 0x10d3a30 (91 B) の rip 相対参照

| 命令 | スロット | 指す先 (イメージ上の値) | 役割 |
|---|---|---|---|
| 0x10d3a34 `mov rax,[rip+0x50da6d]` | 0x15e14a8 | 0x14f852c | g1 (`cmp dword [rax],0x7fffffff`) |
| 0x10d3a43 `mov rax,[rip+0x510336]` | 0x15e3d80 | 0x16b6e58 | g2 (`cmp byte [rax],0`) |
| 0x10d3a58 `mov rcx,[rip+0x50da49]` | 0x15e14a8 | 0x14f852c | g3 (`mov [rcx],eax` の格納先) |
| 0x10d3a61 `mov rax,[rip+0x50da40]` | 0x15e14a8 | 0x14f852c | g4 (`cmp dword [rax],0`) |
| 0x10d3a72 `mov rcx,[rip+0x510d17]` | 0x15e4790 | 0x141d6b8 | g5 (gradeChar の親オブジェクト。`[g5]+0xd0` が格納先) |

- g1・g3・g4 は同一 dword。g2 は別の byte。
- 関数の骨格: `sub rsp,0x28` → g1 判定 → g2 判定 → 早期 `xor eax,eax; jmp 0x10d3a86` → `call 0x10c7850; mov [g3],eax` → `cmp [g4],0; setle al; test al,al; je 0x10d3a86` → `mov rcx,[g5]; mov rcx,[rcx+0xd0]; mov byte [rcx],0x3f` → `add rsp,0x28; ret`。
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

- 差分: `git diff 0e6168b67 HEAD -- tools/startup/license_obs/*.py` の出力は 0 行。測定の後にコードは変えていない (後続の変更は REPORT (.md) と DOC_MAP のみ)。

## 5. 未解決 (起票先)

- (a) 0x10c7850 の戻り値の決定条件 (0 以下を返す入力): #1414 受入 3 (g1 の意味)。open の #1414 が担当。g1 はこの関数の戻り値の格納先と確定したので、残りは戻り値の意味。
- (b) 実機経路で 0x10d3a30 の入口 (条件 1) に届く条件: 呼出し元 0x10cf498 (g6 gate)・0x11fd457・0x11fe627 の上流 (REPORT_786 §1)。#1414 受入 2 の残り。
- (c) 0x11cb000・0x10d50d0 の起動元 (関数ポインタ表の間接呼出し): #1414 受入 1。
