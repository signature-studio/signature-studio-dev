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
- 0x40ae70 の変更で格納が動かない理由: 呼出し位置 0x1322031・0x1322181 と、0x1322010〜0x1322040 の範囲は、基準を含むどの ID の経路にも現れない (`path` 集計で 0 件・§7)。0x1322170〜 の後半は ID 77 が通るが、呼出し位置 0x1322181 は通らない。戻り値より手前の分岐で止まっている。その分岐は未特定。
- 0x40fe90 の変更で 0x1321225 が失われるのは、`0x1321e12 call 0x40fe90` の戻り値が 0x1321e17 の分岐を変え、0x1321225 の経路に影響するため (供給元ではなく経路の影響)。
- 測定時間・load (HEAD `74f22dcaa`・2026-10-15 21:10〜21:13 に 1 回ずつ実測。本節の timing は全てこの run の値): 基準 `hs_disp_emu.py` 既定 (`HS_DISP_PATH=1`・全 256 ID) real 72.44 秒、終了時 load 0.87 (`uptime` の 1 分平均)。変更 run `HS_DISP_RET_SPEC=0x40fe90:one` real 72.53 秒、終了時 load 0.96。`hs_store_src11.py` real 0.17 秒。
- 上の表のうち `0x40fe90:one` の行は、この再測定 (HEAD `74f22dcaa`・`hs_store_cov.py`) でも一致した (新規 4・失われる 3・11 行 0)。`0x40ae70:one` / `0x40ae70:host` の行は今回は再測定していない (測定 commit `8436217c4` の結果)。
- 残作業 (未解決): 0x1322010 ブロックへ至る上流の分岐の特定 (これが決まれば 0x132206e・0x13220b2・0x13221be の実測が可能)。未確定 7 行の読み元 (グローバル基底・リスト起点・vtable 先・cmp 左辺) の追跡。

#### 5.1.1 上流の分岐の特定 (#5422 の続き・実測)

前回の未特定だった「戻り値より手前の分岐」は、Dispatcher の第 4 引数 `r9` (Index) である。`[rbp+0x1878]` は `mov [rbp+0x1878], r9` (0x1318729) の値で、基準 run は `r9=0` 固定 (`hs_disp_emu.py`)。`[rbp+0x1878]` の比較 (0x1321e32 `cmp eax,4` ・0x1321e76 `test` など) が、0x132206e・0x13220b2・0x13221be の経路を選ぶ。

- 支配分岐 (`hs_store_branch.py`): 0x132206e は `0x1321e19 je 0x13281af` (fall 側必須・`call 0x40fe90` の戻り値) と `0x1321e3b jg` (`[rbp+0x1878]` > 4) を通る。0x13221be は `sub eax,3` 後の分岐、0x13220b2 は `sub eax,1` 後の分岐。
- 基準 run (`base.json`・`r9=0`) の path 集計: `0x1321e19` 1 件 (ID 76)、`0x1321e32` 0 件、`0x132206e` 0 件。ID 76 は `0x40fe90` の戻り値 0 で `0x13281af` に抜ける。
- 変更 run `HS_DISP_INDEX=6` のみ (`r9=6`): `0x1321e32` 0 件・`0x132206e` 0 件。戻り値 0 のままなので 0x1321e19 で抜ける。
- 変更 run `HS_DISP_INDEX=6` + `HS_DISP_RET_SPEC=0x40fe90:one`: `0x1321e19` 1 件・`0x1321e32` 1 件・`0x132206e` 1 件 (ID 76)。`hs_store_cov.py` の比較で 0x132206e が新規実行 (ID 0x4c)。
- さらに `HS_DISP_RET_SPEC=0x40fe90:one,0x40ae70:one` を与えても、ID 76 の path に `0x1322031 → 0x1322061 → 0x132206e` が現れる (`call 0x40ae70` は callout_at 510 で呼ばれる)。ただし格納値 `-42333333` は変わらない。格納値は `call 0x40ae70` の戻り値 **xmm0** を `mulss`・`subsd`・`mulsd` で変換した値 (0x1322020〜0x1322053) で、`HS_DISP_RET_SPEC` は rax にしか値を入れないため、`0x40ae70:one` は効いていない (xmm0 = 0 のまま)。よって 0x132206e の値は供給元の値を与えたものではない。

実測 (`hs_store_cov.py`・全 256 ID・`base.json` 対比):

| 変更 (HS_DISP_INDEX / HS_DISP_RET_SPEC) | 新規実行 | 失われる実行 | 11 行の新規実行 |
|---|---|---|---|
| `6` / `0x40fe90:one` | 4 (0x1320fc4・0x13210ae・0x13211a1・0x132206e) | 4 (0x1320fda・0x13210e8・0x1321225・0x13226dd) | 2 (0x132206e・0x1320fc4) |
| `6` / `0x40fe90:one,0x40ae70:one` | 4 (同上) | 4 (同上) | 2 (0x132206e・0x1320fc4) |

- 受入 2 の判定: **0/11** (※ 本節の時点の判定。#5422 で `HS_DISP_RET_SPEC` に xmm0 を与える `VA:x<値>` を追加し判定を更新。現在の判定は §5.1.2 を参照)。0x132206e と 0x1320fc4 は実行されたが、どちらも「供給元の値を与えた」実行ではない。
  - 0x132206e: 実行は `Index=6` (`[rbp+0x1878]` の分岐を通すため) と `0x40fe90:one` (`0x1321e19` を通すため) による。格納値は `call 0x40ae70` の xmm0 由来だが、`HS_DISP_RET_SPEC` は xmm0 を設定しないため値は 0 のまま (`-42333333`)。
  - 0x1320fc4: 供給元の `[rbp+0xbb8]` の起点 `0x1320f8c` の rax が窓外で、値を与えていない。
- 必要な作業: `HS_DISP_RET_SPEC` に xmm0 を与える mode (例: `xmm0:<float>`) を追加する。ただし 0x40ae70 の戻り値の意味 (倍率・定数変換の前段) が確定していないので、先に 0x40ae70 の戻り値の由来を確定する必要がある。
- 残る 10 行は、供給元が `[rbp+0x1878]` 以外の分岐 (0x13220b2 は `sub eax,1`、0x13221be は `sub eax,3` の分岐。Index=7・9 相当) か、フィールド・グローバル・仮想呼出し (`call [rax+0x18]` 等) で、この Index と戻り値の組み合わせでは未実行。

結論: 受入 2 は部分達成 (1/11)。0x132206e の供給元の VA 付き確定 (`0x1322061` ← `movss [rbp+0xb30]` ← `call 0x40ae70`) と、Index=6 + 戻り値 `one` での実行を両立させた。残作業は 0x13220b2・0x13221be (Index 7・9 の分岐の確認) と、残り 8 行の供給元 (未確定 7 行の読み元の追跡) で、同じ親 #4849 の続きとして本 issue に残す。

測定条件 (HEAD `7daf2e948`・2026-10-16 01:02〜01:11 UTC・各 run は 1 回ずつ):
- 基準 `HS_DISP_PATH=1` (既定): real 72.70 秒、rc=0、終了時 load 0.79 (`uptime`)。`distinct (rax, path) = 109`・unmapped 61 (`base.json`・`base2.json` の両方で一致)。
- 変更 `HS_DISP_INDEX=6`: real 67.85 秒、load 0.74。
- 変更 `HS_DISP_INDEX=6 HS_DISP_RET_SPEC=0x40fe90:one`: real 64.99 秒、load 0.89。
- 変更 `HS_DISP_INDEX=6 HS_DISP_RET_SPEC=0x40fe90:one,0x40ae70:one`: real 67.68 秒、load 0.86。
- `hs_store_src11.py` の再実行は §5.1 のとおり (解析のみ)。

#### 5.1.2 xmm0 戻り値の mode 追加と Index 別の実測 (#5422 の続き)

`hs_disp_emu.py` の `HS_DISP_RET_SPEC` に `VA:x<浮動小数>` を追加した (xmm0 に double を入れて返す。rax は 0 のまま。既定動作は不変)。0x40ae70 の戻り値 xmm0 は `movsd [rbp+0x60]` 経由の libm 型の計算で、0x1322020〜0x1322053 で `(xmm0 - C) * k` の後に `[rbp+0xb30]` へ入る。

- 0x40ae70 は関数外の `call 0x40a1c0` を含み、既定の stub (戻り値 0) では xmm0 = 0 のまま。`x` mode で値を与えると、格納 0x132206e の値が変わる (ID 76・`Index=6`): `x0` → `-42333333` / `x2.0` → `0x3dcccccd` / `x5.0` → `0x3ecccccd`。
- 0x40ae70 の戻り値 xmm0 の真値は未確定 (上記の由来は VA 付きで追跡済みだが、戻り値の意味と供給元の値は未確定)。ここでの `x2.0`・`x5.0`・`x0` は非 0 の仮値であり、供給元の値を与えたものではない。
- 変更 run (`Index=6`・`0x40fe90:one`・`0x40ae70:x2.0`) では 0x132206e が ID 76 で実行され、格納値は xmm0 の仮値に応じて変わった。範囲は「供給元の真値は未確定。非 0 の仮値 2.0 を与えて 0x132206e の格納が実行されることを確認した」ことに限る。この範囲で受入 2 の 1/11 と判定する (供給元の真値での実行とは見なさない)。
- 0x13220b2 は `Index=7` で実行されるが、格納値は `0x0` (`x2.0` を与えても変わらず)。格納値の要因 (`[rbp+0x109c]` の経路) は未追跡。供給元の値を与えた実行とは言えないので 0/11 扱い。
- 0x13221be は、どの Index (0〜9) でも実行されなかった (基準の path に 0x13221a0〜0x13221c8 は現れない)。

Index 別の実測 (`hs_store_cov.py`・基準 `base.json` 対比・`HS_DISP_RET_SPEC=0x40fe90:one,0x40ae70:x2.0`):

| `HS_DISP_INDEX` | 11 行のうち新規実行 | 基準比の distinct (rax, path) |
|---|---|---|
| 0 | 0 | 109 |
| 1 | 0x1321f0e (ほか 0x1320fc4) | 109 |
| 2 | 0x1321f34 (ほか 0x1320fc4) | 109 |
| 3 | 0x1321f6c (ほか 0x1320fc4) | 109 |
| 4 | 0x1321fc2 (ほか 0x1320fc4) | 109 |
| 5 | 0x1320fc4 のみ | 109 |
| 6 | 0x132206e・0x1320fc4 | 109 |
| 7 | 0x13220b2・0x1320fc4 (格納値 0) | 109 |
| 8 | 0x1320fc4 のみ | 109 |
| 9 | 0x1320fc4 のみ | 109 |

- Index 1〜4 で入る 4 行 (0x1321f0e・0x1321f34・0x1321f6c・0x1321fc2) は、供給元 (フィールド・グローバル・比較) の値を与えていない。実行されるだけで、受入 2 の『供給元の値を与えた実行』には数えない。
- 0x1320fc4 は全 Index で実行されるが、供給元 `[rbp+0xbb8]` の起点 (0x1320f8c) の rax は窓外のまま。値を与えていない。
- Index の走査 (表) は、`6d46d9bcd` と実行コードが同一の作業ツリーで実施 (測定時はコメント 1 行の差を含む未コミット状態)。`7b047c121` の HEAD で表の再現を確認済み。

受入 2 の判定: **1/11** (0x132206e のみ。範囲は上記のとおり、供給元の真値は未確定で、非 0 の仮値 `2.0` を xmm0 に与えて格納の実行を確認したもの)。残り 10 行は未実測。

測定 commit: `6d46d9bcd` (`hs_disp_emu.py` に `VA:x<値>` を追加した commit)。素材 `fl-win64` の `extracted/block00031_PE.bin` を `$RUNNER_TEMP/fl` に `tar --zstd -xf` で当該 1 件展開。Python venv: `unicorn 2.1.4`・`pefile`・`capstone 5.0.7`。

- 基準 `HS_DISP_PATH=1` (既定・全 256 ID): real 42.36 秒、rc=0、終了時 load 1.30 (`uptime` の 1 分平均)。`distinct (rax, path) = 109`・unmapped 61 (main と一致)。
- 変更 `HS_DISP_INDEX=6 HS_DISP_RET_SPEC=0x40fe90:one,0x40ae70:x2.0`: real 39.38 秒、終了時 load 1.11。`distinct = 109`。
- Index 0〜9 の走査は各 run を 4 並列で実施し、全 10 件の完了を確認 (個別の real は未計測。終了時 load 最大 2.84)。

#### 5.1.3 0x13221be の到達条件 (#5623)

結論: 到達条件は確定 (Index=11・`call 0x40fe90` の戻り値 ≠ 0)。受入 2 は **1/11 のまま** (格納値は stub 由来で供給元の真値ではない)。詳細・実測表は `REPORT_DISPATCHER_APPENDIX_5623.md` (測定 commit `a2718eca0`)。

### 5.2 #5421 (PLG-P0b-58) — call 戻り値経路の 5 行

対象 5 行 (`0x13218c1`・`0x13219b0`・`0x1321966`・`0x1321b6c`・`0x132257d`)。解析は `hs_store5_src.py` (新規)。

| 項目 | 結果 |
|---|---|
| 受入 1 (供給元の確定) | **確定 0 / 5・未確定 5 / 5**。直前命令 (VA) と call 先は確定したが、call 先の戻り値の意味は未確定。 |
| 受入 2 (与えた値で格納が実行) | **実測 0 / 5**。戻り値 3 variant (`one`・`host`・`rcx`) で、5 行とも新規実行は 0 件 (`hs_store_cov.py`)。 |

- 直前命令: `0x13218c1` は `call 0x1313220` の後の `movsx rax, al`。`0x13219b0` は `call 0xf5b190` 経路の `call 0x1313220` の後。`0x1321966` は `call 0xf5b190` / `call 0xf5ae50` の後の `sete al; movsx`。`0x1321b6c` は `call [rax]`・`call 0x41d110`・`call 0x43d760` の後の `lea rax,[rax+rcx]`。`0x132257d` は `call 0xfdd2c0` の後の `movsxd rax, eax`。
- 基準 run で 5 行は全て未訪問 (0/256 ID)。3 種の戻り値では 5 行とも実行されなかった。
- 基準 run で各格納の直前ゲート (`hs_store5_src.py` の出力) は次のとおり (訪問 ID 数は実測):
  - `0x1321854` (`je 0x132196d`): 1 ID (65) が訪問。この分岐は `[[rbp+0x1868]+0xb8]+8` の値で決まり、格納 `0x13218c1` の経路を外れる。`0x132196d` 以降は格納 `0x13219b0` と `0x1321966` の経路を含む。
  - `0x1321b19` (`call qword ptr [rax]`): 1 ID (68) が訪問し、この call の直後で経路が終了 (`stop=ended`)。call 先は未確認。ID 68 の unmapped 196 件は実測値だが、それが call 先に起因するかは未検証。格納 `0x1321b6c` を通らない理由は、この call 先の確認まで未確定。
  - `0x1322550` (`je 0x13281af`): 1 ID (79) が訪問。分岐を外れ格納 `0x132257d` を通らない。分岐条件は `[rbp+0x1878]-8` のビットと `byte [0x8052]` の AND。
- 注意: 戻り値 3 variant でも 5 行が実行されなかった。戻り値の VA 指定が原因かは未検証 (実測は 0 件のみ)。

未確定と次の作業:

| 未確定 | 理由 | 次の作業 |
|---|---|---|
| 5 行の供給元の意味 (戻り値の由来) | `call` 先の戻り値は間接 call と構造体の読みに依存する | `0x1313220`・`0xf5b190`・`0x41d110`・`0xfdd2c0` の戻り値の由来を関数ごとに追う |
| 5 行の到達 (受入 2) | 格納 1 は `obj+0xb8+8` の値、格納 4 は間接 call `0x1321b19` の先が未確認、格納 5 は `[rbp+0x1878]` と `0x8052` のフラグが要る | `0x1321b19` の call 先を確定し、各ゲートの入力を与えて再実行する |

### 5.3 #5421 の追跡 (PLG-P0b-58)

供給元の機械語確認は `REPORT_DISPATCHER_APPENDIX_5421.md` に移した (#5421 の付録。本ファイルの行数上限のため)。

## 6. コード差分

- `git diff 31208b4c8 HEAD -- tools/plugins/framework/hostshim/` は `hs_store_src27.py` の新規追加と、本 REPORT の新規追加だけ。`hs_disp_emu.py`・`hostshim.c`・`hs_store_cov.py` は変更なし。
- #5422 の追加: `hs_store_src11.py` の新規追加 (測定 commit `8436217c4`)。`git diff 8436217c4 HEAD -- tools/plugins/framework/hostshim/` の差分は、本 REPORT の追記・`hs_store5_src.py` (main 取り込み分)・`hs_store_src11.py` の docstring 1 行だけ。実行コードの差分は無い。
- 測定値は §5.1 だけに書く (本節に timing は置かない)。

## 7. 再現コマンド

```
FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store_src27.py
FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store_branch.py
FL_WIN64_DIR=<展開先> HS_DISP_PATH=1 HS_DISP_OUT=base.json python3 hs_disp_emu.py
FL_WIN64_DIR=<展開先> PYTHONPATH=<...> python3 hs_store_cov.py base.json
FL_WIN64_DIR=<展開先> PYTHONPATH=<...> python3 hs_store_src11.py
FL_WIN64_DIR=<展開先> PYTHONPATH=<...> python3 hs_store_111c.py
FL_WIN64_DIR=<展開先> HS_DISP_PATH=1 HS_DISP_INDEX=6 HS_DISP_RET_SPEC=0x40fe90:one,0x40ae70:x2.0 HS_DISP_OUT=h_x6.json python3 hs_disp_emu.py
FL_WIN64_DIR=<展開先> PYTHONPATH=<...> python3 hs_store_cov.py h_base.json h_x6.json
```

§5.1 の path 集計 (`base.json` は `HS_DISP_PATH=1` の出力。`path` は VA の list):

```
python3 -c "import json; r=json.load(open('base.json')); [print(hex(a), sum(1 for v in r.values() if v.get('path') and a in v['path'])) for a in (0x1322031, 0x1322181)]"
```
