# P0b-2 REPORT — TFruityHost.Dispatcher (0x13173a0) case 解析 (#986 / 親 #196)

部分達成。受入条件 1・2 (全 case の ID → 応答値表、未収載 ID の応答確定) は**未達**。
残りは子 issue に分割 (§5)。

## 1. 素材と実行条件

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf`, 8.0 秒, n=1)。
  `extracted/block00031_PE.bin` (22,227,016 bytes) 実在を確認。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PYTHONPATH=$RUNNER_TEMP/pylib python3 hs_disp_emu.py`
  (unicorn 2.1.4 / pefile 2024.8.26 を `uv pip install --target` で導入)。
- 全 256 ID 実行 (基準): exit 0 / 256 件すべて `stop=ended` / distinct (rax, path) = 109。
  wall は n=2 で 51.44 秒・50.94 秒 (min–max 50.94–51.44 秒)。2 回の ID 別結果は完全一致 (差分 0)。
  開始時 load average 0.91 (並列数 1)。
  本 commit での再測 (n=1、`hs_disp_emu.py` の集計追加後): wall 71.98 秒、開始 load 0.91、終了 load 1.00。
  実行時間は負荷 (load・CPU) に依存するため、同一コードでも 51 秒台と 72 秒台の両方を実測している。
- ネガティブコントロール run の wall (n=1): ret_tag 50.91 秒 / ret_one 51.02 秒 / nomap 6.59 秒。
  watch_broken は wall 未計測。

## 2. 既存ツールの限界 (実測)

- `hs_disp_tree.py` (一直線追跡) は Dispatcher の case 解析に**使えない**。
  - Dispatcher は jump table を使わず `cmp`/`jcc` の二分木 (`indirect jmp` 0 件 / 先頭 0x6000 bytes)。
  - 一直線で辿ると `0x13281af` (default 側の共通後処理) 以降の**データ領域**を命令として読み、
    `decode 終端` で全 ID が同じ結果になる (窓 0x8000 → 0x40000 に広げても同じ = 窓不足ではない)。
  - 本 run では窓幅の修正を試して元に戻した (無変更)。

## 3. 新ツール `hs_disp_emu.py` (unicorn 実行)

- block00031 を ImageBase に展開し、Win64 引数 (rcx=Host, rdx=Tag, r8=ID, r9=Index) で
  Dispatcher を ID ごとに実行。
- **制限**: Dispatcher 外への `call` は実行せず戻り値 0 で代替する。よって `rax` は
  case の応答値そのものではなく、**経路の分類**にのみ使う。実 host 応答値の確定には
  callee の意味論が要る (§5 子 issue)。

### 3.1 経路の実測 (256 ID)

distinct (rax, path) = 109 / IDs = 256。WATCH 番地の到達 (`hit`) は次のとおり。

| WATCH 番地 | 到達 ID (件数) | 解釈 |
|---|---|---|
| `0x131bb5c` | `0x56` (1) | `0x56` の case。`hostshim.c` / `hs_disp_tree.py` の主張 (global オブジェクトを返す) と一致 |
| `0x1320dd9` | `0x2e` (1) | 独立 case。`call 0x86c900` の結果を `[rbp+0x11a0]` へ store |
| `0x131b8dd` | `0x1d` (1) | 独立 case。`[rbp+0x1878]` の比較 (cmp eax,4) |
| `0x1320840` | `0x2b` (1) | 独立 case |
| `0x1322b53` | `0x67` (1) | 独立 case。`[rax+0x40]` の deref |
| `0x13281af` | 229 | 共通の後処理ブロック (`call 0x412d60` で始まる)。default 相当ではない |

- 末端 (leaf = 最後に実行した Dispatcher 内命令) の分布: `0x1328a4a` (`ret`) が 229 件。
  残り 27 件は別の番地で終わる (ID: 0x00 0x04 0x09 0x0a 0x12 0x1a 0x1e 0x23 0x2c 0x2f 0x3a 0x3c 0x44 0x49 0x4b 0x57 0x59 0x5b 0x5c 0x5d 0x5e 0x5f 0x60 0x62 0x67 0x69 0x6a)。
  例: 0x67 は `0x1322b69`、0x60 は `0x13228eb`。末端は 28 種類 (うち 0x1328a4a 以外 27 種) で、
  末端番地から case を一意に区別することはできない。経路の区別には `path_hash` を使う。
- 未収載 ID の到達分類 (hit / leaf / 外部 call) は `HS_DISP_OUT` の JSON で確認可能
  (main が出力する。関数名は存在しない)。個別の応答値は確定していない。

### 3.2 ネガティブコントロール (`hs_disp_negctl.py`、基準 run との ID 別差分)

| 壊した箇所 | path_hash 差 | path_len 差 | leaf 差 | rax 差 | WATCH hit 差 |
|---|---|---|---|---|---|
| Dispatcher 外 call の戻り値 0 → `0x54534154` (`ret_tag`) | 12 | 12 | 2 | 19 | 2 |
| 同 0 → 1 (`ret_one`) | 12 | 12 | 2 | 19 | 2 |
| WATCH `0x131bb5c` → `0x131bb5d` (`watch_broken`) | 0 | 0 | 0 | 0 | 1 (ID 0x56 の `0x131bb5c` が消える) |
| 未マップの自動 0 埋めを停止 (`nomap`、§3.3) | 59 | 59 | 59 | 28 | 34 |

- 戻り値を変えると経路が変わる (分類が callee 依存であることの実測)。
- WATCH 壊しは該当 hit のみ消え、経路は変わらない。WATCH は観測専用で判定を変えないことを示す。
- ネガティブコントロールは実行時の差分であり、判定の期待値そのものは不在。
  「外部 call の戻り値で経路が変わる」ため、経路分類は応答値の代替ではない。

### 3.3 unmapped (未マップ領域へのアクセス)

- 61 / 256 ID で未マップ領域へのアクセスが発生 (基準 run)。アクセス回数の合計 5,340 件、
  1 ID あたり最大 197 件 (ID 0x09)。
- 集計 (`hs_disp_emu.py` の `on_unmapped` で (ページ, access 種別) ごとに数え、`HS_DISP_OUT` の JSON `unmapped_pages`
  と標準出力の `unmapped:` 行に出力。キーは `<page>/<access>`)。基準 run の値:
  - (ページ, access) の組は 200、ページは 197。access 種別は fetch 195 組 / read 3 組 / write 2 組。
  - 件数が 27 の組は 195 (fetch・`0x1000`〜 の各ページ)、件数 44 は `0x0`/read の 1 組。
  - ページの下限は `0x0`、上限は `0x54534000`。`0x10000` 未満は 16 ページ、以上は 181 ページ。
  - 大半が fetch である理由は未確認 (関数外へ戻る経路の値か、ret 先の誤読かの切り分けは未実施)。
- hook は当該 1 ページを 0 埋めで自動マップして実行を継続する。0 は実値ではない。
  `nomap` (自動マップ停止) では 59 ID で経路が変わり、28 ID で rax が変わる (例外停止を含む: 停止内訳 ended 195 / Invalid memory read 53 / write 8)。
  よって経路判定は「0 埋めという仮定」の上に立つ。実値 (struct 構造) は未確定。
  (推定) 0 付近の読み出しは Dispatcher が参照する構造体フィールドで、実値は callee 側で決まると思われる。未確認。

## 4. 受入条件の状態

| # | 受入条件 | 状態 |
|---|---|---|
| 1 | 0x13173a0 の switch/case 構造を解析し ID → 応答値の対応表 | **部分**。WATCH 番地で case の到達は確定 (0x56/0x2e/0x1d/0x2b/0x67)。応答値の確定は未 |
| 2 | 未収載 ID (25, 54, 64, 88, 96, 101, 128 ほか) の応答を確定 | **未達**。応答値は callee 依存で未確定 |
| 3 | `hostshim.c` の応答表を実測に合わせ、Phase A 回帰 (dispatch=38 ff=0) を維持 | **部分** (Phase A 回帰 dispatch=38 ff=0 は実測 PASS。応答表の実測化は未実施。§9 参照) |
| 4 | 結果を REPORT に実測値で残す | **本節** |

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Dispatcher 外 callee (`0x412d60` 等の共通 call 先・`0x86c900` 等) の意味論、応答値の確定、`hostshim.c` の表の実測化 | 受入条件 1・2 | #1222 (PLG-P0b-3) |
| 未収載 ID (25, 54, 64, 88, 96, 101, 128 ほか) の応答確定 | 受入条件 2 | #1222 (PLG-P0b-3) |
| 未マップ領域の 0 埋め仮定 (§3.3) の実値確定 | 経路判定の信頼度 | #1222 (PLG-P0b-3) |
| Phase A 回帰の再実行と `hs_e2e.sh` の判定修正 | 受入条件 3 | #196 作業 4 (既存 issue) |

## 6. #1222 (PLG-P0b-3) の実測追記

本節は #1222 の run で追加した事実のみ。受入条件 1・2 の応答値は**未確定**、3 は**未実施**。

### 6.1 callee の機械語解釈 (`hs_callee_disasm.py`・block00031 の VA)

| VA | 機械語から読めた役割 | 戻り値 (rax) |
|---|---|---|
| `0x412d60` | `[rcx]` の参照を外し (`lock xadd` で減算)、0 になれば `0x409440` で解放。最後に `rax=rcx` (引数の値) を返す | 引数ポインタ (rcx) |
| `0x412e40` | `edx` 個の配列要素それぞれに `0x412d60` と同じ参照解放を行う | 未確認 (末尾の rax 設定は本 run で未読) |
| `0x416230` | `[rdx]` (型タグ byte) を `cmp`/`sub` の連鎖で分岐 (`0x0e`・`0x0a`・`0x0b` 等が判定に現れる) | 未確定 (分岐先ごとに異なる) |
| `0x86c900` | `[rbx+0x1d0]` (callback) があれば `[rbx+0x1d8]` を渡して呼び、結果が 0 なら `[rbx+0xa4]` があれば `0x617920` の結果で補う | callback 結果、無ければ `0x617920` (`[rbx+0x45c]` を読む。`0x6178e0` は未確認) |
| `0x409440` | `rcx != 0` なら `[rip+0xf9c844]` の関数を呼び、非 0 なら `0x409730` (解放) | 未確定 |

注意: `0x409440` の `call qword ptr [rip+...]` の先と、`0x416230` の分岐先ごとの戻り値は本 run では未確認。

### 6.2 既存エミュレータの限界 (変更なし)

- 測定 commit: 0eb3c961。`git diff 481eb2d7 HEAD -- tools/plugins/framework/hostshim` は追加 2 ファイル (`REPORT_DISPATCHER.md` +31・`hs_callee_disasm.py` +37 新規)。`git diff 0eb3c961 HEAD -- tools/plugins/framework/hostshim` は `hs_callee_disasm.py` +3 (範囲外 VA の WARN 出力のみ・逆アセンブル結果は不変) と本行の追記のみ。測定対象の `hs_disp_emu.py`・`hostshim.c` は 0 行。
- 今回の run で `hs_disp_emu.py` を全 256 ID で再実行: exit 0 / 256 件 `stop=ended` / distinct (rax, path) = 109 /
  unmapped 61 ID・5,340 件 (§3.3 と一致)。wall・load は未計測 (本 run では集計のみ)。
- 未収載 ID 25/54/64/88/96/101/128 の個別 (rax, leaf) は未取得。callee 戻り値 0 代替のため、
  §6.1 の解釈を使って応答値へ写す作業が残る。

### 6.3 未実施 (受入条件 3)

- Phase A (`hs_e2e.sh`) は `tools/plugins/work/fw/fw_flat4_canon3.ll` ほか framework stage-2 の生成物を要求する。
  素材 `work-fw-stage1` は stage-1 (`fw_icall.dll`・`fw_map.json`・`fw[0-7].restored.ll`) のみで、stage-2 は `fw_stage2.sh` での再生成が必要。
  本 run では時間内に完走できないため未実施。
- `hostshim.c` の応答表は変更していない。

## 7. #1222 2 回目 run の機械語確定 (block00031 VA、commit は本節の PR を参照)

### 7.1 追加で確定した callee の戻り値

| VA | 根拠 (機械語) | 戻り値 (rax) |
|---|---|---|
| `0x412e40` | 配列 `edx` 要素ごとに `0x412d60` 相当の参照解放を行うループのみ。末尾に `rax` 設定なし (`add rsp`/`pop`/`ret`) | 未定義 (呼出側は読まない) |
| `0x416230` | 関数先頭で `rcx` を `[rbp+0x38]` に保存し、全分岐の末尾 `0x416472` で `mov rax,[rbp+0x38]` して返す | **第 1 引数 (rcx) そのもの** |

- `0x416230` は型タグ (`[rdx]` の byte) で分岐する再帰関数 (`0x4162c4`→`0x412e90`、`0x4162d5`→`0x412ee0`、`0x4162e6`→`0x412e40`、`0x4162f7`→`0x415c00` 等)。返り値は分岐によらず引数であり、戻り値として case 応答に使われる経路は無い。
- Dispatcher 内の `call 0x416230`・`0x412e40`・`0x412d60` の多くは直後の命令が次の引数準備 (`lea rcx,…`) で、戻り値を読まない (後始末)。
- Dispatcher の応答値は `[rbp+0x11a0]` に格納され、関数末尾 `0x1328a38` で `mov rax,[rbp+0x11a0]` して返る。`0x1328a33` の `call 0x412e40` の直後にある。

### 7.2 0 代替の影響 (実測・`HS_DISP_RET_ARG=1` の A/B)

- `hs_disp_emu.py` に `HS_DISP_RET_ARG=1` を追加した (既定は従来どおり 0 代替)。このモードでは `0x412d60`・`0x416230` の戻り値を第 1 引数 (rcx) にする。
- 測定 (全 256 ID、同一 commit): 既定 wall 37.96 秒 / `HS_DISP_RET_ARG=1` wall 37.61 秒。開始 load 0.49 → 0.85 (並列数 1)。
- 結果: **rax 差 0 ID・path_hash 差 0 ID・WATCH hit 差 0 ID**。3 ID (0x56・0x2e・0x1d) の個別確認でも同一。
- 結論: この 2 callee の戻り値は、全 256 ID の経路と rax に影響しない。0 代替による経路判定の歪みは、少なくともこの 2 callee については無い。
- 注意: 機械語で `setne al`・`movzx rax,…` の直後に `0x412d60` を読む箇所が見えるが、それは当該 ID の経路上では実行されていない (実測 0 差)。経路外の case の応答は確認していない。
- 訂正: 本節の前版 (commit 未確定時点) にあった「0 代替は経路を変える可能性が高い」は誤り。機械語の読み違い (後続命令の rax 参照を経路上の値と誤認) による。

### 7.3 未達 (本 run 時点)

- 受入条件 1: `0x412e40` (戻り値なし)・`0x416230` (引数を返す)・`0x412d60` (引数を返す) は確定。応答値を決める `0x41a770`・`0x41d110`・`0x86c900` の case 別戻り値は未確定。0 代替の影響は 2 callee で 0 と実測。
- 受入条件 2: 未収載 ID の応答は未確定 (`0x41d110`・`0x41a770` の戻り値の影響は未測定)。
- 受入条件 3: 未実施 (§6.3 と同じ理由)。
- 次の作業: 残りの callee (`0x41d110`・`0x41a770`・`0x86c900`) で同じ A/B を取り、case 別応答値へ写す。起票先: #1222 (本 issue に残す)。

## 8. #1222 3 回目 run: 残り callee の機械語確定と A/B (測定 commit 252a4037)

### 8.1 機械語解釈 (block00031 VA・`hs_callee_disasm.py`)

| VA | 根拠 (機械語) | 戻り値 (rax) |
|---|---|---|
| `0x41a770` | `rcx` を `rbx` に保存し、`[rcx]` が非 0 なら (その値を `[rcx]` に 0 を書いてから) 解放 callback を呼ぶ。末尾で `mov rax, rbx` | **第 1 引数 (rcx) そのもの** |
| `0x41d110` | `[rip+…]` の flag で分岐。通常経路は `gs:[0x58]` (TLS) の配列から `[rax+rcx*8]` を読んで返す。別経路は `0x41cf60`・`0x41d000` を経由して `[rip+…]` の値を返す | **有効なポインタ (TLS 配列の要素)**。整数値ではない |
| `0x86c900` | `[rbx+0x1d0]` (callback) があれば `[rbx+0x1d8]` を渡して呼び、結果が 0 なら `[rbx+0xa4]` があれば `0x617920` の結果で補う (§6.1 と同じ) | callback 結果、無ければ `0x617920` の結果 |

### 8.2 A/B 実測 (全 256 ID・既定 0 代替との比較)

測定 commit `252a4037` (`hs_disp_emu.py` に `HS_DISP_RET_SPEC` を追加)。既定の基準は wall 51.07 秒・load 未計測 (並列数 1)。

| 指定 | wall | 基準との差 | 内容 |
|---|---|---|---|
| `0x41a770:rcx` | 51.02 秒 | **0 行** | rax・経路・callout すべて不変 |
| `0x41d110:host` | 51.52 秒 | 6 行 | ID 0x07・0x0e・0x1c・0x1d・0x3d・0x4e の rax が `0x2a8` → `0x400002a8`。経路 (path_hash) は不変 |
| `0x86c900:host` | 51.72 秒 | 1 行 | ID 0x2e の rax が `0x0` → `0x40000000`。経路 (path_hash) は不変 |
| 3 つ同時 (`0x41a770:rcx,0x41d110:host,0x86c900:host`) | 50.94 秒 | 7 行 | 上の 6 + 1 行の合算。個別測定の和と一致 |

注: `host` は emulator 側の HOST 領域 (`0x40000000`) を指す。実機の TLS 値は未確認のため、`0x2a8` → `0x400002a8` の変化は「戻り値が整数 0 ではなく有効ポインタである」ことを示すだけで、case 別の応答値の確定ではない。

### 8.3 未収載 ID (25・54・64・88・96・101・128) の応答

3 callee 同時指定の run でも、未収載 7 ID の rax は全て `0x0` のまま、path_hash は基準と同一 (0x60 のみ leaf `0x13228eb`、ほかは leaf `0x1328a4a`)。

| ID | rax (基準) | rax (3 指定) | path_hash (両者同一) |
|---|---|---|---|
| 0x19 (25) | 0x0 | 0x0 | a2b3f189 |
| 0x36 (54) | 0x0 | 0x0 | a6aec4e3 |
| 0x40 (64) | 0x0 | 0x0 | 9e2c8c77 |
| 0x58 (88) | 0x0 | 0x0 | ba82795c |
| 0x60 (96) | 0x0 | 0x0 | a2d7d299 |
| 0x65 (101) | 0x0 | 0x0 | 66827ede |
| 0x80 (128) | 0x0 | 0x0 | ac3fa863 |

結論: 未収載 ID の応答 (rax=0) は、検討した 3 callee の戻り値に依存しない。ただし rax=0 は emulator の既定値であり、実機の応答値の確定ではない。受入条件 2 は**未達**のまま。

### 8.4 受入条件 (本 run 時点)

- 受入 1: `0x41a770`・`0x412d60`・`0x412e40`・`0x416230` は機械語で確定。`0x41d110`・`0x86c900` は戻り値の型 (ポインタ / callback 結果) まで確定し、case 別の具体値は未確定。
- 受入 2: **未達**。未収載 7 ID は戻り値の仮定に依存せず rax=0 (emulator 既定)。実機の応答値は未確定。
- 受入 3: **部分**。Phase A 回帰は §9 で実測 PASS。応答表の実測化は未実施 (§9 参照)。
- 受入 4: 本節で記録。

### 8.5 次の作業

- case 別の具体的な応答値 (`0x41d110` の TLS 要素が何を指すか、`0x86c900` の callback 登録先) は、実機 (または stage-2 の lift) でしか確定できない。起票先: #1222 (本 issue に残す)。

## 9. #1222 4 回目 run: Phase A 回帰の実測 (受入 3)

測定 commit: `04a7ff1a` (main 起点・コード無変更)。素材: `fl-win64`・`work-fw-stage1` を展開 (`work-fw-stage1` は repo ルート相対で `tar -C .`)。

| 手順 | exit | wall (real) | load (開始 → 終了) | 結果 |
|---|---|---|---|---|
| `fw_stage2.sh` (stage-1 再利用・`FL_WIN64_DIR` 指定) | 0 | 6 分 35.98 秒 | 未計測 | smoke `dispatch=38 units_done=0 va=1 heap=1 ff=0` PASS・`fw_smoke_check PASS` |
| `hs_e2e.sh` | 1 | 2 分 29.85 秒 | 開始 load 3.00 | **Phase A PASS** (`[fw] Phase A: Halt0/RestoreContext dispatch=38 ff=0`)。Phase B は `memory access out of bounds` で FAIL (下記) |

- 受入 3 の判定: **部分**。Phase A 回帰 (dispatch=38 ff=0) は上表のとおり実測 PASS。
- Phase B の `memory access out of bounds` (`status=0xffffffff plug=0x0 rec=7`) は REPORT_1229 §1 の既知ベースライン (2b2faf52 で同症状) と同一。本 run はコード無変更のため、今回の変更による回帰ではない。起票先は既存の #1229 (`[PLG-P0b-4]`)。
- 受入 3 の未了: `hostshim.c` の応答表を実測に合わせる作業は未実施 (受入 2 の未収載 ID 応答が未確定のため。#1222 に残す)。
- 作業ツリー: `ws-1222` (branch `1222-plg-p0b-3-phaseA`)。生成物 (`tools/plugins/work/fw/`・`work/`) は gitignore 対象。

## 10. #2886 (PLG-P0b-25): 格納元の機械語確定

部分達成。詳細と VA は `REPORT_DISPATCHER_APPENDIX.md` (250 行上限のため分割)。測定 commit は `2d523491` (解析) と `2dca40dd` (応答表)。

- 受入 1 (格納元 19 ID): 出所を VA 付きで確定。TLS 要素ポインタ + `0x2a8` 6 ID / call 戻り値 6 ID / callee 出力引数 1 / グローバル・フィールド 5 / ローカル 1。値の実体は未確定。
- 受入 2 (仮想呼出し出口 27 ID): A (戻り値を格納) 3 / B (戻り値を捨てて `0x13281af` へ) 13 / C (後続未読) 11。B は応答が状態格納 0〜4 で決まる。
- 受入 3: `hostshim.c` に 0x07・0x1c・0x4e (非 NULL) を追加。Phase A `dispatch=38 ff=0` PASS。Phase B の OOB は変更前後で同一。
- 未解決: [PLG-P0b-27] (受入 2 の残り)・[PLG-P0b-28] (整数・bool 格納元の実値)。
