# PLG-P0b-54 (#4849) — 応答スロット格納 27 行の格納値の供給元

親 #4075。入力は `REPORT_DISPATCHER_APPENDIX_4075.md` §4 の 27 行。解析は `hs_store_src27.py` (新規)。

## 1. 結論

- 受入 1 (供給元の確定): **未達**。27 行の格納値について、直前に rax を書いた命令 (VA) は 27/27 列挙できた。ただし「その値が何の値か」(callee の戻り値の意味・フィールドの書込み元) を確定できたのは 0/27。
- 受入 2 (供給元の値を与えた emulator 実測): **未実施**。供給元が確定していないため、与える値を決められない。
- 受入 3 (回帰): 基準 run で `distinct (rax, path) = 109`・unmapped 61 ID が main と一致。

## 2. 測定条件・測定 commit

- 測定 commit: `8cc5288fd` (`hs_store_src27.py` を追加した最後の commit)。基準 run は `31208b4c8` (main) のコードで実施。`8cc5288fd` との差分は新規ファイル 1 本で、`hs_disp_emu.py`・`hostshim.c` は変わらない (§6 の diff)。
- 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B) を `$RUNNER_TEMP` に `tar --zstd -xf` で当該 1 件だけ展開。
- Python venv: `unicorn 2.1.4`・`pefile`・`capstone 5.0.7`。
- 基準 run (`hs_disp_emu.py` 既定・`HS_DISP_PATH=1`・全 256 ID): real 51.4 秒、rc=0、load 0.56 (run 終了時の uptime)。
- `hs_store_src27.py`: 0.4 秒前後。

## 3. 格納値の種別 (27 行)

| 種別 | 件数 | 格納 VA |
|---|---|---|
| 即値 0 | 4 | 0x1319f1f・0x1320fda・0x13210e8・0x13220be |
| 即値 1 | 2 | 0x1321bb0 (`mov`)・0x13220ef (`or ... 1`) |
| 即値 2 | 2 | 0x132210a (`or ... 2`)・0x1326b9a |
| 即値 3 | 1 | 0x132567c |
| 即値 4 | 1 | 0x132415e |
| 即値 0x10 | 1 | 0x132268e |
| rax | 16 | 0x1319f13・0x1320fc4・0x1320ff9・0x13218c1・0x1321966・0x13219b0・0x1321b6c・0x1321f0e・0x1321f34・0x1321f6c・0x1321fc2・0x132206e・0x13220b2・0x13221be・0x132257d・0x1321225 |

検算: 即値 11 + rax 16 = 27。

rax 格納の直前書込み (VA 付き、`hs_store_src27.py` の出力):

| 格納 | 直前の rax 書込み | 種類 |
|---|---|---|
| 0x13218c1 | `0x13218bd movsx rax, al` (直前 `call 0x1313220`) | call 戻り値 |
| 0x13219b0 | `0x13219ac movsx rax, al` (直前 `call 0x1313220`) | call 戻り値 |
| 0x1321966 | `0x1321962 movsx rax, al` (直前 `call 0xf5b190`) | call 戻り値 |
| 0x1321b6c | `0x1321b68 lea rax, [rax+rcx]` (直前 `call 0x41d110`) | call 戻り値 + 定数 |
| 0x1321f0e | `0x1321f07 movsxd rax, [rbp+0x10b8]` | フィールド読み |
| 0x1321f34 | `0x1321f2f movsxd rax, [rax+rcx*8+4]` | グローバル配列の読み |
| 0x1321f6c | `0x1321f67 movsx rax, byte [rax+0x19]` | 構造体読み |
| 0x1321fc2 | `0x1321fbe movsx rax, al` (直前 `cmp`) | 比較結果 |
| 0x132206e | `0x1322067 movsxd rax, [rbp+0x109c]` | float 変換 (call `0x40ae70` 経由) |
| 0x13220b2 | `0x13220ab movsxd rax, [rbp+0x109c]` | float 変換 |
| 0x13221be | `0x13221b7 movsxd rax, [rbp+0x109c]` | float 変換 (call `0x40ae70` 経由) |
| 0x132257d | `0x132257a movsxd rax, eax` (直前 `call 0xfdd2c0`) | call 戻り値 |
| 0x1319f13 | `0x1319f0f mov rax, [rax+0xc]` (直前 `[0x10a8]` ← `call [rax+0x18]`) | 仮想呼出の戻り値の読み |
| 0x1320fc4 | `0x1320fbd mov rax, [rbp+0xbb8]` | フィールド読み (連鎖) |
| 0x1320ff9 | `0x1320ff6 movsxd rax, eax` (直前 `mov eax, [global]`) | グローバル読み |
| 0x1321225 | `0x1321221 movsx rax, al` (直前 `cmp`) | 比較結果 |

## 4. 基準 run での実行 (実測・全 256 ID)

- `hs_store_cov.py` の出力: 静的 69 格納のうち基準で実行されたのは 30、未実行 39。
- 27 行のうち未実行は 24 件 (0x1319f13・0x1319f1f・0x1320fc4・0x1320ff9・0x13218c1・0x1321966・0x13219b0・0x1321b6c・0x1321bb0・0x1321f0e・0x1321f34・0x1321f6c・0x1321fc2・0x132206e・0x13220b2・0x13220be・0x13220ef・0x132210a・0x13221be・0x132257d・0x132268e・0x132415e・0x132567c・0x1326b9a)。残り 3 件 (0x1320fda・0x13210e8・0x1321225) は 1 ID だけ実行。`REPORT_DISPATCHER_APPENDIX_4075.md` §3 と一致。
- 基準 run の `distinct (rax, path) = 109`・unmapped 61 ID・`no-case-store IDs = 202` は main と一致。

## 5. 未確定と残作業

| 未確定 | 理由 | 次の作業 |
|---|---|---|
| 16 件の rax 格納の値の意味 (call 戻り値・フィールド・グローバルの書込み元) | 直前の書込みは VA で列挙できたが、その先 (`call` 先の戻り値の由来・構造体フィールドの書込み元) は関数外か窓の外にある | `call` 先 (0x1313220・0xf5b190・0x41d110・0x40ae70・0xfdd2c0) の戻り値を関数ごとに追う |
| 27 行の到達性 (受入 2) | 供給元が未確定のため、与える値が決まらない | 供給元の確定後に `HS_DISP_RET_SPEC` で callee 戻り値を与えて `hs_store_cov.py` で実測 |

### 5.1 #5422 (PLG-P0b-59): 11 行の供給元と実測

入力は §3 の rax 格納 16 件のうち、call 戻り値以外の 11 行。解析は `hs_store_src11.py` (新規)。測定 commit: `8436217c4` (`hs_store_src11.py` を追加した最後の commit)。

- 確定 4 行 (供給元の命令まで VA で確定): 0x132206e・0x13220b2・0x13221be は `[rbp+0x109c]` ← `0x1322061`/`0x13221b1` の書込み ← `movss [rbp+0xb30]/[rbp+0xb28]` ← `call 0x40ae70` (戻り値 xmm0 を倍率・定数で変換)。0x1321f0e は `[rbp+0x10b8]` ← `0x1321e2c` ← `mov eax,[obj+0x130]` (`obj = [rbp+0x1868]`)。
- 未確定 7 行 (理由つき): 0x1321f34・0x1321f6c は index `[rbp+0x10b8]` まで確定、グローバル基底 `[rip+0x2be77f]`/`[rip+0x2be759]` の書込み元は未追跡。0x1320fc4 は `[rbp+0xbb8]` のリスト連鎖 (`[rax-8]`) で、起点 `0x1320f8c` の rax は窓外。0x1319f13 は `call [rax+0x18]` (仮想呼出・実行先は動的)。0x1320ff9 は `mov eax,[global]` の書込み元が未追跡。0x1321fc2・0x1321225 は `cmp` の左辺 (`rax` / `[rbp+0x119c]`) が窓外。
- 検算: 確定 4 + 未確定 7 = 11。

実測 (`hs_store_cov.py`・全 256 ID・基準 `base.json` と 3 通りの変更 run):

| 変更 (HS_DISP_RET_SPEC) | 基準比の新規実行 | 失われる実行 | 11 行の新規実行 |
|---|---|---|---|
| 0x40ae70:one | 0 | 0 | 0 |
| 0x40ae70:host | 0 | 0 | 0 |
| 0x40fe90:one | 4 (0x1320f72・0x13210ae・0x13211a1・0x1321efb) | 3 (0x1320fda・0x13210e8・0x1321225) | 0 |

- 基準: 静的 69 格納のうち実行 30・未実行 39。11 行のうち基準で実行されたのは 0x1321225 の 1 行 (1 ID) だけ。
- 実測の結論: 11 行のうち、供給元の値を与えて実行されたのは 0/11。実行できなかった理由は次のとおり。0x132206e・0x13220b2・0x13221be は供給元が `call 0x40ae70` の戻り値で、その呼出しブロックに基準の経路が届かない (下記)。残り 8 行は供給元がフィールド・グローバル・仮想呼出しで、`HS_DISP_RET_SPEC` (callee 戻り値のみ) では値を与えられない。
- 0x40ae70 の変更で格納が動かない理由: 呼出し位置 0x1322031・0x1322181 を含むブロック (0x1322010〜・0x1322170〜) が、基準を含むどの ID の経路にも現れない (`path` 集計で 0 件)。戻り値より手前の分岐で止まっている。その分岐は未特定。
- 0x40fe90 の変更で 0x1321225 が失われるのは、`0x1321e12 call 0x40fe90` の戻り値が 0x1321e17 の分岐を変え、0x1321225 の経路に影響するため (供給元ではなく経路の影響)。
- 測定時間・load: 基準 `hs_disp_emu.py` 既定 (`HS_DISP_PATH=1`・全 256 ID) real 1m12s、終了時 load 0.91 (`uptime`)。変更 run 3 回の合計は 20:36:56〜20:40:33 (壁時計 3m37s、load 0.98)。`hs_store_src11.py` real 0.174 秒、`hs_store_cov.py` (基準のみ) real 5.9 秒。
- 残作業 (未解決): 0x1322010 ブロックへ至る上流の分岐の特定 (これが決まれば 0x132206e・0x13220b2・0x13221be の実測が可能)。未確定 7 行の読み元 (グローバル基底・リスト起点・vtable 先・cmp 左辺) の追跡。

## 6. コード差分

- `git diff 31208b4c8 HEAD -- tools/plugins/framework/hostshim/` は `hs_store_src27.py` の新規追加と、本 REPORT の新規追加だけ。`hs_disp_emu.py`・`hostshim.c`・`hs_store_cov.py` は変更なし。
- #5422 の追加: `hs_store_src11.py` の新規追加 (測定 commit `8436217c4`)。`git diff 8436217c4 HEAD -- tools/plugins/framework/hostshim/` は本 REPORT の追記だけ。

## 7. 再現コマンド

```
FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store_src27.py
FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store_branch.py
FL_WIN64_DIR=<展開先> HS_DISP_PATH=1 HS_DISP_OUT=base.json python3 hs_disp_emu.py
FL_WIN64_DIR=<展開先> PYTHONPATH=<...> python3 hs_store_cov.py base.json
```
