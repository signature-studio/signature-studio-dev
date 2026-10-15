# PLG-P0b-38 (#3673) — Dispatcher 0x11a0 格納元 6 ID の書込み元と応答表の扱い

親 #3653。前身は `REPORT_DISPATCHER_APPENDIX_2886.md` §8 (静的読みで 6 ID とも未確定)。本付録は新規ファイルで、分割移動ではない。

## 0. 結論

| 受入 | 結果 | 状態 |
|---|---|---|
| 1 実行時の書込み元を確定 | 6 ID とも**値は未確定**。書込み元を 1 段先まで確定した (§2)。実行時の値は子 #3986 ([PLG-P0b-41]) | 部分 |
| 2 応答表を更新 | 値が確定しないため応答値は変えない。0 固定 5 ID と 0x56 の非 NULL 近似に理由を書いた (`hostshim.c`) | 理由の記載まで完了 |
| 3 Phase A 回帰 `dispatch=38 ff=0` | PASS (§4)。Phase B は既存 #2911 の失敗のまま | 完了 |
| 4 0x56 の『global オブジェクトポインタ』と画像値 0 の食い違い | 確定: 画像値は 0。唯一の書込み (0x9dec3f) の値は 0x40f9e0 の戻り値で、実行時の vcall 結果。『global オブジェクトポインタ』は画像からは確定しない。コメントを訂正 | 完了 |

## 1. 測定条件

- 測定 commit: `fe58ff465` (`hostshim.c` のコメント修正。コードを変えた最後の commit。基点は main `321f1620e`)。
- 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B) を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf` 2.9 秒)。`work-fw-stage1` を `tools/plugins/work/fw/` に展開 (12 ファイル)。emcc は `[EMSDK]` (既存。`docs/REFERENCES.md` §4)。
- Python (repo 外の `$RUNNER_TEMP/hsvenv`): `unicorn 2.1.4` / `pefile 2024.8.26` / `capstone 5.0.7`。
- 解析の再現 (n=1・実行はすべて `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` で、`hostshim/` の既存スクリプト):
  - `hs_glob_src.py 0x15ec298 0x15e0ff8 0x15e2118 0x15e4b68 0x15e30f8 0x16bcc00 0x15f61f4 0x1426f08 0x15f7190`
  - `hs_glob_src.py 0x9de2c0`
  - `hs_callee_disasm.py 60 0x9dec3f 0x11fc2b3 0x41d8f0`・`hs_callee_disasm.py 400 0x9dec3f`・`hs_callee_disasm.py 1200 0x11fc2b3`・`hs_callee_disasm.py 45 0x40f9e0`
- 検算 (別アルゴリズム): GNU objdump で同じ番地を読み直した (`objdump -d -M intel --start-address=… block00031_PE.bin`)。0x41d919、0x9dec31〜0x9dec3f、0x11fc2ac〜0x11fc2b3 の命令・オペランド・rip 解決先が capstone の結果と一致した。
- 負の確認: 本付録は解析値の記述で、判定系 (`hs_e2e.mjs`・`fw_smoke_check`) は変えていない。新設の検査は無く、ネガティブコントロールは未実施。

## 2. 受入 1: 6 ID の書込み元 (機械語 VA)

`hs_glob_src.py` の出力 (rip 相対の参照だけ・線形逆アセンブル。`image_qword` は PE の初期値):

| 参照位置 (sec) | 画像値 | rip 直接の書込み | 読出し件数 |
|---|---|---|---|
| G18 = 0x15ec298 (.bss) | 0x0 | 1 件: 0x41d919 | 67 |
| G45 = 0x15e0ff8 (.data) | P45 = 0x16bcc00 | 0 件 | 1077 |
| P45 = 0x16bcc00 (.bss) | 0x0 | 5 件: 0x11fc2b3 (`mov [P45], rax`)・0x11fd41e・0x11fda47・0x11fe5ec・0x123164f (0 化 4 件) | 315 |
| G54 = 0x15e2118 (.data) | T = 0x15f61f4 | 0 件 | 25 |
| T = 0x15f61f4 (.bss) | 0x0 | 0 件 | 0 |
| G56 = 0x15e4b68 (.data) | P56 = 0x1426f08 | 0 件 | 1 |
| P56 = 0x1426f08 (.data) | 0x0 | 1 件: 0x9dec3f | 1 |
| G64 = 0x15e30f8 (.data) | P64 = 0x15f7190 | 0 件 | 362 |
| P64 = 0x15f7190 (.bss) | 0x0 | 0 件 | 170 |
| 0x9de2c0 (.text・0x9dec31 の参照先) | 0x9de388 | 0 件 | 1 |

| ID | 格納元 (APPENDIX_2886 §2・§8.1) | 今回確定した書込み元 | 実行時にしか決まらない部分 | 判定 |
|---|---|---|---|---|
| 0x18 | `qword [G18]` (0x131a261) | 0x41d919 `mov [G18], rdi`。0x41d8f0 の `r9d==1` 分岐 (0x41d905) の内。rdi = r8 (0x41d8ff)。0x41d8f0 の呼出元は 0x1376870 の 1 件 (2886 §8.1) | 0x1376820 の第 1 引数 `[rbp+0x30]` の実行時の値 | 未確定 |
| 0x45 | `int32 [[P45]+0x3518]` (0x1321b78) | 0x11fc2b3 `mov [P45], rax`。rax = `[rbp+0x170]` = 0x11fba90 の第 1 引数 (rcx、0x11fbad9 で保存)。分岐は 0x11fbb4f (`cmp eax,0xb; je 0x11fc2ac`、eax = `[[rbp+0x140]+0x10]`) | P45 に入る this (受信オブジェクト) の実体と `[this+0x3518]` の値。0x11fc2ac は `[this+0x34a8] <= 0` の入口 (0x11fbaef) の後 | 未確定 (P45 = this は確定) |
| 0x54 | `int32 [T + 4*[rbp+0x1880]]` (0x13226dd) | G54 への書込みなし。T への rip 直接の読出し 0 件。T は .bss・画像値 0 | テーブル T の内容 (実行時に書かれる)。index `[rbp+0x1880]` (Dispatcher の第 5 引数。APPENDIX_3652 §2.1) | 未確定 |
| 0x56 | `qword [[G56]]` (0x131bb5c) | 0x9dec3f `mov [P56], rax`。rax = 0x9dec3a `call 0x40f9e0`。rcx = `[0x9de2c0]` (0x9dec31)、dl = 1 (0x9dec38) | 0x40f9e0 の戻り値 = dl≠0 のとき `0x410360(0x410320(X))` (0x40fa03・0x40fa17)。0x410320・0x410360 はいずれも vcall (APPENDIX_3652 §3.2)。受け手の型と戻り値は未確定。rcx の実行時の値 (下の注意) | 未確定 (画像値 0) |
| 0x64 | `cmp dword [[G64]+0x168], 0` (0x13229ef) | P64 への rip 直接の書込みなし。P64 は .bss・画像値 0 | P64 が指す実行時オブジェクト (レジスタ経由で書かれる) と `[obj+0x168]` | 未確定 |
| 0x65 | `movsxd [rbp+0x109c]` (0x1322b47) | ローカル (2886 §8.1 と同じ)。値は 0 (0x1322a55) か float のビット列 (0x1322b38) | obj = `[rbp+0x1168]` (0x1322b21) の値と分岐条件 | 未確定 |

注意 (0x56 の rcx): 0x9de2c0 は .text 内の番地で、画像値は 0x9de388 (コード番地)。`hs_glob_src.py 0x9de2c0` の読出しは 1 件 (0x9dec31) だけ。実行時にこの番地の内容が変わるかは未確認。画像の値をそのまま rcx に入れると 0x40f9e0 は code 番地を受け手として vcall することになり、実行時の値が画像と同じとは言えない。

### 2.1 0x56 の『global オブジェクトポインタ』 (受入 4)

- 画像値 `qword [0x1426f08]` = 0 (`hs_glob_src.py`)。
- P56 の唯一の書込みは 0x9dec3f で、書込み値は 0x40f9e0 の戻り値 (vcall の結果)。
- よって『global オブジェクトポインタ』は、画像の値からも書込み元からも確定しない。0 を返す可能性も残る。
- 書込み (0x9dec3f) が Dispatcher の ID 0x56 呼出しより前に実行されるかは**未測定**。Phase A の経路で書込みが起きるかも未測定。
- 応答表の非 NULL (`g_hs_obj`) は値の近似として残した。コメントを『未確定 (近似)』に改めた (`fe58ff465`)。

## 3. 受入 2: 応答表 (`hostshim.c`)

- 6 ID とも値は確定しなかったため、応答値は変えていない。
- 0x56: 非 NULL 応答はそのまま。FLE 側の値 (`[[G56]]`) が 0 になり得ることをコメントに書いた。
- 0 固定 (fail-soft) の ID に理由を書いた (`default:` 直前)。対象は 0x18・0x45・0x54・0x64・0x65 と、同じ理由で 0 固定の 0x01・0x13・0x26・0x41・0x46 (格納元の種別は 2886 §2)。0x01・0x13・0x26・0x41・0x46 の値の確定は本付録の範囲外 (APPENDIX_3652 の未確定)。
- 応答値の更新 (受入 2 の本体) は値の確定 (受入 1 の残り) に依存するため、子 #3986 ([PLG-P0b-41]) に移した。

## 4. 受入 3: Phase A 回帰 (測定 commit `fe58ff465`)

| 段 | 結果 | 所要 (n=1) |
|---|---|---|
| `fw_stage2.sh` (stage-1 再利用。step 17 で `hostshim.c` をリンク) | `[fw] SMOKE PASS (Halt0/RestoreContext 到達): dispatch=38 units_done=0 va=1 heap=1 ff=0`。`fw_smoke_check` は FAIL (`runerr got=1 expect=0`・`init_reach got=16 expect=288` の MISMATCH。既存 #2510)。終了コード 1 は `fw_smoke_check` の既存 FAIL による | 7 分 3 秒 (05:24:53〜05:31:56) |
| `hs_e2e.sh` Phase A (`fw_route.cjs`) | `[fw] Phase A (framework smoke): Halt0/RestoreContext dispatch=38 ff=0` (FAIL 行なし) → **PASS** | `hs_e2e.sh` 全体 2 分 39 秒 (05:32:05〜05:34:44) |
| `hs_e2e.sh` Phase B (`hs_route.cjs`) | `[hs] Phase B 例外: memory access out of bounds`・`status=0xffffffff plug=0x0 rec=7 pluglog=0 slotsCalled=0x0` → FAIL。`[hs] E2E FAIL: 1 項目`。APPENDIX_2886 §6 の測定と同じ値 (既存 #2911) | 同上 |

- load average は未採取。
- `hostshim.c` の変更はコメントだけ (`git diff 321f1620e fe58ff465 -- tools/plugins/framework/hostshim/hostshim.c`: 7 行追加・3 行削除。`+`・`-` の行はすべてコメント)。応答値の変更は無いため、Phase A の結果が変わる根拠は無い。実測で確認した。

## 4.1 #3986 (PLG-P0b-41): 実行時の値の計装 (測定 commit は PR 本文を正とする)

- 計装: `hs_val_probe.py` の観測点に §2 の書込み元 VA を追加 (0x41d919・0x11fc2b3・0x9dec3f・0x13226dd・0x1322a07・0x1322b47)。
  許可範囲は `HS_ALLOW_LO`/`HS_ALLOW_HI` で広げられるようにした (既定は従来の `[0x13173a0, 0x1330000)`)。
- 測定: `python3 hs_val_probe.py disp 0x18 0x45 0x54 0x56 0x64 0x65` (既定範囲・広げた範囲 `[0x9d0000, 0x1330000)` の両方。各 6.6 秒・n=1)。
- 結果: 6 ID とも `rax=0x0 stop=ended`。観測点に到達したのは 0x1318730 (開始点) と 0x13226dd (0x54)・0x1322a07 (0x64)・0x1322b47 (0x65) のみ。
  **0x41d919・0x11fc2b3・0x9dec3f は 6 ID とも未到達** (広げた範囲でも同じ。経路長は 855〜880 命令で変化なし)。
- 読み: Dispatcher を単独で実行しても、6 ID の格納元 (G18・P45・P56) の書込みには到達しない。書込みは Dispatcher の呼出し元側の経路 (0x41d8f0・0x11fba90・0x9de2c0 の呼出し) で行われる。
  0x13226dd・0x1322a07・0x1322b47 の値はいずれも 0 (`[rbp+0x1880]`・`[rbp+0x109c]` の初期値)。0x1322b47 の `[rbp+0x1168]` は 0x54534154 (TAG)。
- 結論: 6 ID の実行時の値は**未確定**のまま。応答表は変えない。次は呼出し元 (0x41d8f0 等) からの経路での計装 (子 `[PLG-P0b-47]`)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 6 ID の実行時の値 (§2 の『未確定』列) と、確定後の応答表の更新 | 受入 1・2 の残り。応答表の 0 固定 5 ID と 0x56 の近似 | #3986 ([PLG-P0b-41]) (子・本 PR の本文に番号) |
| 0x9dec3f が Phase A の経路で実行されるか (未測定) と、0x40f9e0 の vcall の受け手の型 | 0x56 の実値 | #3986 ([PLG-P0b-41]) |
| 0x9de2c0 の画像値 (コード番地) と実行時の rcx の値の一致 (未確認) | 0x56 の受け手 | #3986 ([PLG-P0b-41]) |
| Phase B の `memory access out of bounds` | Phase B の PASS | #2911 (既存) |
| `fw_smoke_check` の `runerr=1`・`init_reach=16` | smoke の判定 | #2510 (既存) |

## 6. 測定 commit と差分

- 測定 commit: `fe58ff465`。以降の commit は本付録 (`.md`) と `docs/DOC_MAP.md` だけを変える。
- 確認: `git diff fe58ff465 HEAD -- tools/plugins/framework/hostshim ':!*.md'` は空 (出力なし)。
