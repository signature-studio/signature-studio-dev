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

### 5.1 #5421 (PLG-P0b-58) — call 戻り値経路の 5 行

対象 5 行 (`0x13218c1`・`0x13219b0`・`0x1321966`・`0x1321b6c`・`0x132257d`)。解析は `hs_store5_src.py` (新規)。

| 項目 | 結果 |
|---|---|
| 受入 1 (供給元の確定) | **確定 0 / 5・未確定 5 / 5**。直前命令 (VA) と call 先は確定したが、call 先の戻り値の意味は未確定。 |
| 受入 2 (与えた値で格納が実行) | **実測 0 / 5**。戻り値 3 variant (`one`・`host`・`rcx`) で、5 行とも新規実行は 0 件 (`hs_store_cov.py`)。 |

- 直前命令: `0x13218c1` は `call 0x1313220` の後の `movsx rax, al`。`0x13219b0` は `call 0xf5b190` 経路の `call 0x1313220` の後。`0x1321966` は `call 0xf5b190` / `call 0xf5ae50` の後の `sete al; movsx`。`0x1321b6c` は `call [rax]`・`call 0x41d110`・`call 0x43d760` の後の `lea rax,[rax+rcx]`。`0x132257d` は `call 0xfdd2c0` の後の `movsxd rax, eax`。
- 基準 run で 5 行は全て未訪問 (0/256 ID)。戻り値を変えても 0 件のため、未実行の原因は戻り値ではない。
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

## 6. コード差分

- `git diff 31208b4c8 HEAD -- tools/plugins/framework/hostshim/` は `hs_store_src27.py` の新規追加と、本 REPORT の新規追加だけ。`hs_disp_emu.py`・`hostshim.c`・`hs_store_cov.py` は変更なし。

## 7. 再現コマンド

```
FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store_src27.py
FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store_branch.py
FL_WIN64_DIR=<展開先> HS_DISP_PATH=1 HS_DISP_OUT=base.json python3 hs_disp_emu.py
FL_WIN64_DIR=<展開先> PYTHONPATH=<...> python3 hs_store_cov.py base.json
```
