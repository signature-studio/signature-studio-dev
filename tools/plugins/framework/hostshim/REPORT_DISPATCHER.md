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
| 3 | `hostshim.c` の応答表を実測に合わせ、Phase A 回帰 (dispatch=38 ff=0) を維持 | **未実施** (shim は変更していない。Phase A の再実行は未) |
| 4 | 結果を REPORT に実測値で残す | **本節** |

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Dispatcher 外 callee (`0x412d60` 等の共通 call 先・`0x86c900` 等) の意味論、応答値の確定、`hostshim.c` の表の実測化 | 受入条件 1・2 | #1222 (PLG-P0b-3) |
| 未収載 ID (25, 54, 64, 88, 96, 101, 128 ほか) の応答確定 | 受入条件 2 | #1222 (PLG-P0b-3) |
| 未マップ領域の 0 埋め仮定 (§3.3) の実値確定 | 経路判定の信頼度 | #1222 (PLG-P0b-3) |
| Phase A 回帰の再実行と `hs_e2e.sh` の判定修正 | 受入条件 3 | #196 作業 4 (既存 issue) |
