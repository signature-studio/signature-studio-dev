# P0b-2 REPORT — TFruityHost.Dispatcher (0x13173a0) case 解析 (#986 / 親 #196)

部分達成。受入条件 1・2 (全 case の ID → 応答値表、未収載 ID の応答確定) は**未達**。
残りは子 issue に分割 (§5)。

## 1. 素材と実行条件

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf`, 5.4 秒)。
  `extracted/block00031_PE.bin` 実在を確認。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PYTHONPATH=$RUNNER_TEMP/pylib python3 hs_disp_emu.py`
  (unicorn 2.1.4 を `uv pip install --target` で導入。`$RUNNER_TEMP/pylib`)。
- 全 256 ID 実行: exit 0 / 1 分 12 秒 (72.4 秒, 実測) / 256 件すべて `stop=ended`。

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

- 全 ID の末端 (leaf) は `0x1328a4a` (`ret`) の 1 点に集まる。end 点では case を区別できない。
- 未収載 ID の到達分類 (hit / leaf / 外部 call) は `hs_disp_all` の JSON 出力で確認可能
  (`HS_DISP_OUT`)。個別の応答値は確定していない。

## 4. 受入条件の状態

| # | 受入条件 | 状態 |
|---|---|---|
| 1 | 0x13173a0 の switch/case 構造を解析し ID → 応答値の対応表 | **部分**。WATCH 番地で case の到達は確定 (0x56/0x2e/0x1d/0x2b/0x67)。応答値の確定は未 |
| 2 | 未収載 ID (25, 54, 64, 88, 96, 101, 128 ほか) の応答を確定 | **未達**。応答値は callee 依存で未確定 |
| 3 | `hostshim.c` の応答表を実測に合わせ、Phase A 回帰 (dispatch=38 ff=0) を維持 | **未実施** (shim は変更していない。Phase A の再実行は未) |
| 4 | 結果を REPORT に実測値で残す | **本節** |

## 5. 未解決 (起票先)

- Dispatcher 外 callee (`0x412d60` 等の共通 call 先・`0x86c900` 等) の意味論を解き、
  応答値を確定して `hostshim.c` の表を実測化 → 子 issue (親 #986 / #196)。
- 未収載 ID の応答確定 (受入条件 2) → 同上。
- Phase A 回帰の再実行と `hs_e2e.sh` の判定修正 (#196 作業 4) → 既存の #196 側。
