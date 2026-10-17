# tools/python REPORT: PY-140 ui 操作 27 関数の作用先 — `0xfdd2c0` の op 別 leaf (#3035, 親 #2981)

> 正本: `REPORT_PY120.md` (27 関数の PE 呼出し契約と保留の表)、`REPORT_PY87.md` (PE 確定の書式・ネガティブコントロール)。本付録は PY-140 の実測のみ。
> 解析補助: `analysis/flapi/pe_ui_dispatch_probe.py` (op・arg・mode を具体値で与えて、決まる分岐だけを辿る)。

## 結論

- `0xfdd2c0` (UI 側ディスパッチャ) の op 別 leaf を VA 付きで特定した。27 関数のうち **15 関数は、送出する仮想キー (VK)・修飾・回数が PE から確定**した。どの leaf も `0x8186a0` (キー入力列を作って `user32!SendInput` に渡す関数) を呼ぶ。
- 15 関数の**送出の成否** (leaf に入るか) は、leaf の手前のゲート (`0x60c220`・`0x728f50`・`0xfdeaf0`) と mode の源 (`0xfdd270`) の戻り値で決まり、その値は未確定。よって作用の意味 (FL 側でそのキーが何をするか) は未確定。
- 12 関数は送出 leaf に到達しない、または別経路で未追跡。`ui.scrollWindow` は `0xd843d0` 経路 (REPORT_PY120 の保留) のまま。
- 15 関数の mock・C の実装は子 #3759 (PY-246) で入れた (`a0fc92492`)。本 PR の commit は REPORT だけを変える (コード差分 0)。作用の意味が未確定の点は PY-87・PY-120 と同じ方針で、送出の成否は子 #3758、残り 12 関数は子 #3761 に分けた。

## 手段

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `tar --zstd -xf ... --wildcards '*block00031_PE.bin' '*block24429_DATA.bin' '*block24430_DATA.bin' '*block25159_DATA.bin' '*block24618_DATA.bin'` で展開 (2.8 秒)。`$ARTIFACTS_DIR` の実在は展開前に `ls` で確認した。`toolchain-emsdk` は本 PR では使わない (mock/C を変えないため)。
- 逆アセンブル: `pe_disasm.py fdd2c0 1500` と capstone で `0xfdd2c0`〜`0xfde8ad` (`.pdata` の終端、0x15ed バイト、1269 命令)。
- 到達解析: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_ui_dispatch_probe.py <op...> --arg <N|-> --mode <N|->`。op (`ecx`)・arg (`edx`)・mode (`r8b`) を具体値で与え、op 由来の `eax` と比較フラグだけを具体値で追う。フラグ (ZF/SF/CF/OF) は演算幅 (8/16/32bit) から求める。決まらない分岐 (メモリ・呼出しの戻り値) は両方を辿る。`.data` の定数は読み、`[rip+X]` の 16bit 定数 (修飾子) も PE の静的値で読む。`rcx` の間接テーブル引き (矢印キーの VK) は probe では追わず、テーブル値は手で読んだ (下)。
- 追加で読んだ値: `0x8186a0` の本体 (`dx` のビットと user32 の thunk)、矢印キーの VK 表、修飾子ワード。

## 0xfdd2c0 の骨格 (PE 根拠)

引数: `ecx`=op (`[rbp+0x40]`)、`edx`=arg (`[rbp+0x44]`)、`r8b`=mode (`[rbp+0x1a0]`)、`r9d`=0xf (`[rbp+0x48]`)。戻り値は `[rbp+0x4c]` (status、`0xfde89e`)。

| VA | 条件・動作 | 結果 |
|---|---|---|
| `0xfdd3e9`〜`0xfdd3f3` | `test al, 2` (mode bit 1) が 0 | status -1 で終了 |
| `0xfdd4ef`〜`0xfdd55b` | mode bit 0x20 と `[rbp+0x1b0]` の条件 → `call 0xfdeaf0(op, arg)` (`0xfdd54e`) | status 5 |
| `0xfdd560`〜`0xfdd586` | mode bit 4 → `call 0x728f50(op, arg)` (`0xfdd575`) の戻り値 > 0 | status 4 |
| `0xfdd5bb`〜`0xfdd5e1` | `bl` (`0xfdd4fe`〜の判定) と `[rbp+0x48]` の bit 1/2 で `0x60c220` の呼出しへ進む | — |
| `0xfdd5f9`〜`0xfdd608` | `call 0x60c220(obj, edx=0x57f, r8=op, r9=arg)` の戻り値 > 0 → status 1 (送出なし) | status 1 |
| `0xfdd77a`〜`0xfdd782` | `test [rbp+0x48], 8` が 0 なら終了 (r9=0xf は bit 8 を持つ) | — |
| `0xfdd788`〜 | op による比較の木 (0x3b, 0x1e, 0x0d, 0x0a, 0x02, 0x6a, 0x65 …) で leaf の入口を決める | leaf |
| `0xfde854` | 送出 leaf の共通の終わり: `mov eax, 8` → `mov [rbp+0x4c], eax` → `0xfdee80` → 戻り | status 8 |

- 送出 leaf の共通形: `mov ecx, <VK>`・`movzx rdx, word ptr [rip+X]` (修飾子)・`mov r8d, 1` (または `arg`)・`call 0x8186a0`。`arg ≤ 0` のとき leaf の手前で `jle 0xfde854` (送出なし)。矢印キー (`0xfde0f0`) だけは `arg` をそのまま `r8d` に入れ、`0x8186a0` が `r8d ≤ 0` で何もしない (`0x8186b6`〜`0x8186b9`)。

## 送出 leaf の意味 `0x8186a0` (PE 根拠)

- 引数: `rcx`=VK (`mov word ptr [rbp+rdx*8+0x28], cx` の形で INPUT 配列に入る)、`rdx`=修飾ビット (`test ax,1`/`2`/`4`)、`r8d`=回数 (`test r8d,r8d; jle 0x818767`)。
- 修飾ビット: bit 0 (1) → `wVk=0x10` (VK_SHIFT)、bit 1 (2) → `wVk=0x12` (VK_MENU = Alt)、bit 2 (4) → `wVk=0x11` (VK_CONTROL) を押下記録として組む (`0x8186c7`〜`0x818803`)。
- 呼出し先 (IAT 経由の薄い thunk): `0x425370` → `user32!SendInput` (`jmp qword ptr [rip+0x154baf2]` の IAT 名)、`0x424d50` → `user32!GetKeyState` (修飾キーの状態。`0x8188a2`〜`0x8188c8` で `ecx=0x10/0x11/0x12`)、`0x424b60` → `user32!GetActiveWindow`。
- よって 15 関数の作用先 (PE 確定) は **OS の仮想キー入力 (SendInput) へ渡すキー列**。FL 側がそのキーをどう処理するかは、この PE だけからは決まらない (子 #3759 で扱う)。

## 27 関数の作用先 (op 別)

凡例: 入口 = `0xfdd788` 以降の比較木が leaf の先頭へ飛ぶ VA。送出 call = `0x8186a0` を呼ぶ VA。VK・修飾・回数は PE の値 (修飾子ワードは `.text` 内の定数、矢印の VK は `.data` の表)。

| 関数 | op | 入口 | 送出 call | VK | 修飾 | 回数 | 判定 |
|---|---|---|---|---|---|---|---|
| ui.jog | 0x00 | なし (`0xfdd5f9` の 0x60c220 と `0xfdd678`・`0xfdda37 call 0x1180dd0` の別経路のみ) | なし | — | — | — | 保留 (未追跡) |
| ui.jog2 | 0x01 | なし (`0xfdd5f9` の 0x60c220 のみ) | なし | — | — | — | 保留 (未追跡) |
| ui.strip | 0x02 | なし (`0xfdd5f9` の 0x60c220 のみ) | なし | — | — | — | 保留 (未追跡) |
| ui.stripJog | 0x03 | なし (`0xfdd678`・`0xfdda37 call 0x1180dd0` の別経路) | なし | — | — | — | 保留 (未追跡) |
| ui.stripHold | 0x04 | なし (`0xfdd5f9` の 0x60c220 のみ) | なし | — | — | — | 保留 (未追跡) |
| ui.previous | 0x05 | 別経路 (`0xfde3e7 call 0x1180ef0`・`0xfde483`・`0xfde4be`) | なし | — | — | — | 保留 (未追跡) |
| ui.next | 0x06 | 別経路 (同上) | なし | — | — | — | 保留 (未追跡) |
| ui.moveJog | 0x08 | なし (`0xfdd5f9` の 0x60c220 のみ) | なし | — | — | — | 保留 (未追跡) |
| ui.up | 0x28 | `0xfde0f0` | `0xfde110` | 0x26 (VK_UP) | 0 | arg | **PE 確定 (送出キー)** |
| ui.down | 0x29 | `0xfde0f0` | `0xfde110` | 0x28 (VK_DOWN) | 0 | arg | **PE 確定 (送出キー)** |
| ui.left | 0x2a | `0xfde0f0` | `0xfde110` | 0x25 (VK_LEFT) | 0 | arg | **PE 確定 (送出キー)** |
| ui.right | 0x2b | `0xfde0f0` | `0xfde110` | 0x27 (VK_RIGHT) | 0 | arg | **PE 確定 (送出キー)** |
| ui.horZoom | 0x2c | なし (`0xfdd891`〜`0xfdd8a1` で status 8) | なし | — | — | — | 保留 (送出 leaf 非到達) |
| ui.verZoom | 0x2d | なし (同上) | なし | — | — | — | 保留 (送出 leaf 非到達) |
| ui.snapOnOff | 0x30 | 非到達 (`0xfddb7d call 0x12134f0`) | なし | — | — | — | 保留 (未追跡) |
| ui.cut | 0x32 | `0xfde11a` (arg>0) | `0xfde138` | 0x58 ('X') | 4 (Ctrl) | 1 | **PE 確定 (送出キー)** |
| ui.copy | 0x33 | `0xfde142` (arg>0) | `0xfde160` | 0x43 ('C') | 4 (Ctrl) | 1 | **PE 確定 (送出キー)** |
| ui.paste | 0x34 | `0xfde16a` (arg>0) | `0xfde188` | 0x56 ('V') | 4 (Ctrl) | 1 | **PE 確定 (送出キー)** |
| ui.insert | 0x35 | `0xfde192` (arg>0) | `0xfde1b0` | 0x2d (VK_INSERT) | 0 | 1 | **PE 確定 (送出キー)** |
| ui.delete | 0x36 | `0xfde1ba` (arg>0) | `0xfde1d8` | 0x2e (VK_DELETE) | 0 | 1 | **PE 確定 (送出キー)** |
| ui.enter | 0x50 | `0xfde1e2` (arg>0) | `0xfde200` | 0x0d (VK_RETURN) | 0 | 1 | **PE 確定 (送出キー)** |
| ui.escape | 0x51 | `0xfde20a` (arg>0) | `0xfde228` | 0x1b (VK_ESCAPE) | 0 | 1 | **PE 確定 (送出キー)** |
| ui.yes | 0x52 | `0xfde232` (arg>0) | `0xfde250` | 0x59 ('Y') | 0 | 1 | **PE 確定 (送出キー)** |
| ui.no | 0x53 | `0xfde25a` (arg>0) | `0xfde278` | 0x4e ('N') | 0 | 1 | **PE 確定 (送出キー)** |
| ui.nextWindow | 0x3a | `0xfde087` (arg>0) | `0xfde0a5` | 0x09 (VK_TAB) | 0 | 1 | **PE 確定 (送出キー)** |
| ui.selectWindow | 0x3b | `0xfde0af` | arg>0: `0xfde0c9` / arg≤0: `0xfde0e6` | 0x09 (VK_TAB) | arg>0: 0 / arg≤0: 1 (Shift) | 1 | **PE 確定 (送出キー)。符号は未確定** |
| ui.scrollWindow | — | 対象外 (`0xd843d0` 経路) | — | — | — | — | 保留 (REPORT_PY120) |

- 矢印 4 関数の VK は `0xfde0f0` の `mov ecx, dword ptr [rax + rcx*4 - 0xa0]` の表で引く。表の基点 `ptr` は `[0x15e1418]` (`.data`) の静的値 `0x13f1c88`。`op=0x28`〜`0x2b` の 4 要素は `0x26, 0x28, 0x25, 0x27` (`.data` の静的値)。`op=0x2c`・`0x2d` の要素 (`0x13f1c98`・`0x13f1c9c`) は VK ではなく、`0xfdd891` で leaf に入らない。
- `ui.selectWindow` の shift の符号: PE は `arg>0` で修飾 0 (Tab)、`arg≤0` で Shift+Tab。`REPORT_PY120` の stub は `shift: bool`。`shift=1` が Shift を意味するなら符号が逆になる。判断は子 #3759。
- 修飾子ワードの静的値 (`.text` 内の定数): `0xfdea12` = 0、`0xfdea14` = 1 (Shift)、`0xfdea16` = 4 (Ctrl)。表の修飾列はこの読み先の値。

## 保留 (PE で確定できなかった点)

- **ゲート**: 送出 leaf の入口に至る前に `0x60c220(obj, 0x57f, op, arg)` の戻り値 (> 0 で status 1) と `0x728f50` (mode bit 4) と `0xfdeaf0` (mode bit 0x20) がある。戻り値の値は未確定。`0x60c220` は `obj` の `[obj+0x80]` を直接呼ぶ汎用の問合せ (`0x60c22c`〜`0x60c24f`)。
- **mode の源**: `0xfdd270` は `0x1542bec` (`.data` の定数表) を `vtbl+0x80` (`call [rax+0x80]`・`rax=[G+8]` の vtbl) の戻り値で引き、`call 0x81c0a0` の戻り値が 0 のとき `or bl, byte ptr [rip+0xa]` (`0xfdd2a8`、対象 VA `0xfdd2b9`) を行う。表の添字の値域と `0x81c0a0` は未確定。
- **runtime の状態**: `rsi` (`0xfdd402` の `[rax+0xcc]` と比較する値) やゲート関数の対象 `obj` は runtime の状態。送出の成否はこの状態に依存する。

## PY-406 受入 1: `0x60c220` の戻り値条件

- **確定した構造** (`pe_disasm.py 60c220`): `0x60c220` は `msg.Result` (`[rbp+0x38]`、初期値 0) を戻す。`[rbp+0x20]`=edx (0x57f)・`[rbp+0x28]`=r8・`[rbp+0x30]`=r9 を立てたあと、`obj` (`rbx`=rcx) が非 0 なら `call qword ptr [rbx+0x80]` を `rcx=[rbx+0x88]`・`rdx=&msg` で呼ぶ (`0x60c244`〜`0x60c24f`)。よって戻り値は呼ばれた先が `msg.Result` に書く値そのもの。
- **未確定**: 呼ばれる先 (`[obj+0x80]`) の値。`[obj+0x80]` を直接読む (VMT 経由ではない: `0x410090` の `call [rbx-0x38]` は VMT 経路)。この関数ポインタは obj のインスタンス状態で、PE 内の静的な書込み元が確定できない。
- **探索範囲と結果**: `analysis/flapi/pe_obj80_writers.py` が block00031_PE の実行可能 section を線形走査 (5,022,467 命令を復号)。`mov qword ptr [<非フレーム reg>+0x80], <src>` は 77 件。うち src が `lea reg,[rip+disp]` で `0x410090` を指すものは 0 件。`call 0x410090` の直接参照も 0 件。すなわち「`0x410090` が `obj+0x80` に入る」経路は静的な即値・rip 相対では見つからない。線形走査のため、間接 (レジスタ経由の複数段) の書込みは除外しきれない。
- **結論**: 戻り値 ≤ 0 の条件は、`obj+0x80` の実行時の値 (呼び先) と、その呼び先が `msg.Result` に書く値で決まる。静的には確定できない。理由は上記の書込み元が PE から一意に決まらないことである。確定には実行時の trace (`obj`・`[obj+0x80]`・呼び先が書く `msg.Result`) が要る。

## 検証

- 本 REPORT の 27 関数の数値 (送出 leaf・VK・修飾) は PY-246 の実装 commit `a0fc92492` で測定した。`a0fc92492`..`9b57a83cd` の差分は REPORT のみ。
- 新節 (PY-406 受入 1) の数値 (`decoded=5022467 writes_to_nonframe+0x80=77`) は `pe_obj80_writers.py` を含む commit `70c323053` で測定した。この PR の commit が `tools/python` のコードに加えたのは `analysis/flapi/pe_obj80_writers.py` の追加 (63 行) のみ。`pe_ui_dispatch_probe.py` と `pe_disasm.py` は `a0fc92492` 以降変更なし。
- `a0fc92492`..`70c323053` の `tools/python` の非 md 差分 (157 ファイル) は main 側 (`9b57a83cd`..`1e95ba237`) の取り込みで、この PR の変更ではない。
- 解析 probe (`analysis/flapi/pe_ui_dispatch_probe.py`) の測定 commit は `ca104e569`。旧版の `cond()` は符号付き分岐 (`jle`・`jg`) を判定できず到達しない経路を出していたため、ca104e569 でフラグを演算幅から求めるように直した。以下の probe 出力は ca104e569 以降のコードによる。
- 測定 commit `a0fc92492` (HEAD `9b57a83cd` と tools/python のコード同一) で実行したコマンドと結果:

| コマンド | 結果 | wall |
|---|---|---|
| `python3 -m py_compile analysis/flapi/pe_ui_dispatch_probe.py` | rc 0 | — |
| `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_ui_dispatch_probe.py <26 op> --arg 1 --mode 2` | rc 0。送出 call (`0x8186a0` を呼ぶ VA) は 12 VA。矢印 4 op → `0xfde110`、nextWindow → `0xfde0a5`、selectWindow → `0xfde0c9` (rdx=0x0) の 1 VA、cut・copy・paste・insert・delete・enter・escape・yes・no → 各 1 VA。`0xfde0e6` (selectWindow の Shift 経路) は出ない | 0.19 秒 |
| 同 `--arg 0 --mode 2` | rc 0。送出 call は 2 VA。`0xfde110` (矢印 4 op。`r8d ≤ 0` のため `0x8186a0` は何もしない) と `0xfde0e6` (selectWindow・rdx=0x1)。arg>0 で送出する 10 op (nextWindow と cut〜no) と `0xfde0c9` は出ない | 0.18 秒 |
| `bash tools/python/provider/build.sh` (emsdk 6.0.12・`$RUNNER_TEMP` に上流から導入) | rc 0。`dist/flprov.{js,wasm}` 生成 | 2.07 秒 |
| `node tests/ui_keys_diff.mjs` | rc 0。`{"calls":26,"diffs":0,"PASS":true}` | 0.049 秒 |
| ネガティブコントロール: `host/fl_mock.mjs` の `ui.selectWindow` の符号を反転して `node tests/ui_keys_diff.mjs` | rc 1。`ui 送出キー差分 4 件` (selectWindow の arg 1・0 などで mock と C が食い違う)。検証後に mock を元へ戻し、`git diff` は 0 行 | — |
| `node tests/ui_diff.mjs` | rc 0。`{"calls":17,"diffs":0,"outOfRangeKnownDiffs":3,"PASS":true}` (範囲外 index 3 件は既知の差分として分けて報告) | — |
| `node tests/provider_check.mjs` (HEAD `d81fa4a45` で再測定) | §1 (表の整合・件数) のみ。`provider_check.mjs` を `// 2. エラー code` の行の前で切った一時ファイルで実行し rc 0。`{"functions":435,"implemented":234,"unimplemented":201,"mcp_static":60,"PASS":true}`。a0fc92492 の同じ切り出しは `implemented:220`・`unimplemented:215` で、差 14 は `provider_expect` に追加された 7 ファイル (14 関数。すべて `fl_engine.c` で実装済み)。§2 (エラー code) と §3 (flpy 経路) は HEAD で未実行: §3 は `dist/flpy.js` が要り、`build_flpy.sh` は CPython wasm (`work/build-wasm/.../python312.zip`) が無いため HEAD で rc 1 (`cp: cannot stat`) で止まる。受入 4・5 の未達は未解決表 (#4579) のとおり | — |

- 修飾子 (`rdx`) の値: 上の出力では cut/copy/paste = 0x4、selectWindow の arg≤0 = 0x1、他 = 0x0。PE の静的値と一致。
- 差分の証跡 (`docs/WORKFLOW.md` §6): 27 関数の表の測定 commit `a0fc92492` から HEAD `f8ba50187` までに、上の表のテストが読むコードは変わっている。`git diff --stat a0fc92492 f8ba50187 -- tools/python/host tools/python/provider tools/python/tests` は 20 ファイル (`host/fl_mock.mjs`・`provider/fl_engine.c`・`provider/gen/fl_table.c`・`tests/*.mjs`・`tests/provider_expect/*.json`、main 側 `9b57a83cd`..`1e95ba237` の取り込み)。このため表のうち `ui_keys_diff`・`ui_diff` の 2 行は HEAD `f8ba50187` で再実行し、下の「HEAD 再測定」の値が表の値と同じであることを確認した。`pe_ui_dispatch_probe.py`・`pe_disasm.py` は a0fc92492..f8ba50187 で 0 byte。`provider_check` の §1 の件数は HEAD `d81fa4a45` で再測定して上の表に書いた。`a0fc92492`..`d81fa4a45` で件数に効く入力は `provider_expect/*.json` の 7 ファイル (14 関数の追加) のみ。`provider/gen/fl_table.c` の 1 行の変更 (`launchMapPages.setMapItemTarget` の戻り型 `'i'`→`'n'`) は関数の有無を変えず、件数 (435) は変わらない。`build_flpy.sh` の変更 (EMSDK_ENV の受け口) は件数に関与しない。`host/fl_mock.mjs` は §1 の切り出しで読まれない (§6 の mock 照合でだけ使われる)。`gen/fl_table.c` は HEAD のビルドで「435 関数」と出ており、§1 の件数 `functions:435` と一致する。新節の測定 commit は `70c323053` (上の「検証」)。
- HEAD 再測定 (`f8ba50187`・emsdk 6.0.12 を `$RUNNER_TEMP` に導入): `bash tools/python/provider/build.sh` rc 0。`node tests/ui_keys_diff.mjs` rc 0 `{"calls":26,"diffs":0,"PASS":true}`。`node tests/ui_diff.mjs` rc 0 `{"calls":17,"diffs":0,"outOfRangeKnownDiffs":3,"PASS":true}`。ネガティブコントロール (`host/fl_mock.mjs` 489 行の `ui.selectWindow` の符号を反転) で `ui_keys_diff` は `AssertionError: ui 送出キー差分 4 件` rc 1、元に戻して `git diff` は 0 行。表の数値 (件数・VK・修飾・回数) は a0fc92492 の値と一致。
- `FL_ENGINE=wasm node tests/all_tools.mjs` は本 PR では実行していない (受入 5 は子 #4579 で扱う)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ゲート `0x60c220`・`0x728f50`・`0xfdeaf0` の戻り値と mode の源 (`0xfdd270` の表・`0x81c0a0`・`[0xfdd2b9]`) | 15 関数の送出の成否 | #3758 (PY-245) |
| 送出キーの実装は PY-246 で済 (15 関数・`tests/ui_keys_diff.mjs` 差分 0)。未達: `FL_ENGINE=wasm node tests/all_tools.mjs` 48/48 と `provider_check.mjs` の flpy 経路 (素材展開先の `fetch_inputs.sh` が runner の素材配置と合わず未実行。子 #4579) | 受入 4・5 | #3759 (PY-246・残り) |
| `selectWindow` の shift の符号 (PE は arg>0 で修飾 0、stub は `shift: bool`)。PY-246 は PE の符号 (arg>0 で Tab) を採り、mock/C ともに同じ符号で記録する | 引数契約 (stub 側の `shift` 名と不一致のまま) | #3759 (PY-246) |
| jog 系 5・previous/next・moveJog・horZoom/verZoom・snapOnOff の作用先、`ui.scrollWindow` の `0xd843d0` | 12 関数の作用 | #3761 (PY-247) |
| 戻り値の値と型 (`0x415610` の out+8 既定値・`0x15e4280`・`0xc38bc0`) | 27 関数の戻り値 | #3034 (PY-141) |
