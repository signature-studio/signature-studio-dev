# PLG-P0b-42 (#4075) — 応答スロット格納 27 行の分岐条件と供給元

親 #3735。入力は `REPORT_DISPATCHER_APPENDIX_3735.md` §5 の 27 行 (未実行格納 24 件 + 失う格納 3 件)。
本付録は新規ファイル。解析スクリプトは `hs_store_branch.py`。

## 1. 測定条件

- 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B) を `$RUNNER_TEMP` に `tar --zstd -xf` で当該 1 件だけ展開。
- Python: venv に `unicorn 2.1.4`・`pefile`・`capstone 5.0.7`。
- 解析 (`hs_store_branch.py`): 関数 `[0x13173a0, 0x1330000)` の逆アセンブル 12,834 命令、入口から到達 12,814 命令、間接 `jmp` 0 件、`ret` 1 件。0.45 秒。
- 基準 run (`hs_disp_emu.py` 既定・`HS_DISP_PATH=1`・全 256 ID): 72.2 秒、rc=0、実行 load 0.77 (1 分平均・終了時)。

## 2. 検算: 確定 + 未確定 = 27

| 項目 | 件数 |
|---|---|
| 分岐条件を機械語から確定 (支配する jcc と枝を VA 付きで列挙できた) | 27 |
| 未確定 | 0 |
| 検算 | 27 + 0 = 27 |

ただし「確定」は **分岐の枝 (jcc と taken/fall の向き)** までであり、その jcc のフラグの供給元 (§4) は別である。

## 3. 基準 run での実行の有無 (実測)

基準 run の経路 (`path`) に各格納が現れるかを数えた (全 256 ID)。

| 区分 | 件数 | 格納 VA |
|---|---|---|
| 基準で未実行 | 24 | 0x1319f13・0x1319f1f・0x1320fc4・0x1320ff9・0x13218c1・0x1321966・0x13219b0・0x1321b6c・0x1321bb0・0x1321f0e・0x1321f34・0x1321f6c・0x1321fc2・0x132206e・0x13220b2・0x13220be・0x13220ef・0x132210a・0x13221be・0x132257d・0x132268e・0x132415e・0x132567c・0x1326b9a |
| 基準で 1 ID だけ実行 (失う格納) | 3 | 0x1320fda・0x13210e8・0x1321225 |

- 注: 0x1320fda・0x13210e8・0x1321225 は基準で 1 ID ずつ実行される (それぞれ `path` に現れる ID は 1 件)。
- 「未実行 24」は `REPORT_DISPATCHER_APPENDIX_3735.md` §5.1 の 24 件と同じ集合。0x1319f13・0x1319f1f・0x1320fc4 は本 run の基準でも未実行。

## 4. 分岐条件 (受入 1 の確定部分)

各格納を支配する jcc のうち、直近の枝 (格納への全経路が必ず通る枝) を示す。格納の番地ごとの全支配 jcc の一覧は `hs_store_branch.py` の出力で得られる (`python3 hs_store_branch.py`)。

| 格納 | 直近の支配 jcc | 枝 | 直前のフラグ命令 (flags) |
|---|---|---|---|
| 0x1319f13 | 0x1319f06 je 0x1319f1f | fall | 0x1319efe cmp qword ptr [rbp+0x10a8],0 |
| 0x1319f1f | 0x1319f06 je 0x1319f1f | taken | 0x1319efe cmp qword ptr [rbp+0x10a8],0 |
| 0x1320fc4 | 0x1320f2a jne 0x1320f7e | taken | 0x1320f22 cmp qword ptr [rbp+0x1878],0 |
| 0x1320ff9 | 0x1320fd8 jne 0x1320fea | taken | 0x1320fd0 cmp qword ptr [rbp+0x1878],0 |
| 0x13218c1 | 0x132188d je 0x13218c8 | fall | 0x1321885 cmp qword ptr [rax+0xdc],0 |
| 0x1321966 | 0x13218d0 jne 0x132196d | fall | 0x13218c8 cmp qword ptr [rbp+0x11a0],0 |
| 0x13219b0 | 0x1321984 je 0x13219b7 | fall | 0x132197e test rax,1 |
| 0x1321b6c | 0x1318ad4 jne 0x13281af | fall | 0x1318ad2 test eax,eax |
| 0x1321bb0 | 0x1321b9d jne 0x1321bc0 | fall | 0x1321b95 cmp qword ptr [rbp+0x1878],2 |
| 0x1321f0e | 0x1321e50 je 0x1321f07 | taken | 0x1321e4e test eax,eax |
| 0x1321f34 | 0x1321e5b je 0x1321f1a | taken | 0x1321e59 test eax,eax |
| 0x1321f6c | 0x1321e66 jne 0x13281af | fall | 0x1321e64 test eax,eax |
| 0x1321fc2 | 0x1321e40 je 0x1321f78 | taken | 0x1321e3d cmp eax,4 |
| 0x132206e | 0x1321e76 je 0x1321fce | taken | 0x1321e74 test eax,eax |
| 0x13220b2 | 0x1321e81 je 0x132207a | taken | 0x1321e7f test eax,eax |
| 0x13220be | 0x1321e8c je 0x13220be | taken | 0x1321e8a test eax,eax |
| 0x13220ef | 0x13220ed jne 0x13220f7 | fall | 0x13220e6 cmp byte ptr [rax+0x49e],0 |
| 0x132210a | 0x1322104 je 0x13281af | fall | 0x1322102 test al,al |
| 0x13221be | 0x1321e97 jne 0x13281af | fall | 0x1321e95 test eax,eax |
| 0x132257d | 0x1322550 je 0x13281af | fall | 0x132254e test al,al |
| 0x132268e | 0x132268c jne 0x132269e | fall | 0x1322684 cmp qword ptr [rbp+0x1880],-1 |
| 0x132415e | 0x132415c jne 0x132416e | fall | 0x1324155 cmp byte ptr [rbp+0xaf7],2 |
| 0x132567c | 0x132567a jne 0x132568c | fall | 0x1325673 cmp byte ptr [rbp+0xa2f],2 |
| 0x1326b9a | 0x1326b98 jne 0x1326baa | fall | 0x1326b91 cmp byte ptr [rbp+0x967],2 |
| 0x1320fda | 0x1320fd8 jne 0x1320fea | fall | 0x1320fd0 cmp qword ptr [rbp+0x1878],0 |
| 0x13210e8 | 0x132101a je 0x13210e8 | taken | 0x1321018 test al,al |
| 0x1321225 | 0x132110d je 0x13211db | taken | 0x132110b test al,al |

- 同じ格納でも、支配 jcc の列 (ID の二分木) は複数ある。表は直近の 1 件だけ。全件は `hs_store_branch.py` の出力を参照。
- 0x13210e8・0x1321225 の直近枝は、`0x40fe90` の戻り値 (`al`) で分岐する。

## 5. 供給元 (未確定)

各フラグ命令のオペランドの直前書込み (線形・候補) は `hs_store_branch.py` が出す。ただし **分岐をまたぐ線形探索のため候補であって確定ではない**。
- 直前書込みが `call` の戻り値 (`call 0x40fe90`・`call 0x127c0c0`) の行は、その callee の戻り値を供給元として §4 の枝に結びつけた。
- `(窓内に書込みなし)` の行 (0x1320fc4・0x1320ff9・0x13218c1・0x1321bb0・0x13220ef・0x132268e・0x1320fda) は、フラグの対象が構造体フィールド (`[rbp+0x1878]`・`[rbp+0x1880]`・`[rax+0xdc]`・`[rax+0x49e]`) で、その値の書込みが関数の外か窓の外にある。確定できていない。
- 結果: 27 行のうち、供給元まで機械語から確定できた行は 0 件。

## 6. 実測 (受入 2): 未実施

供給元の値を与えて格納が実行されることを示す emulator の実測は行っていない。
理由: 供給元が確定していないため、与える値を決められない。確定した枝 (§4) を満たす値の探索は、§5 の供給元確定の後にできる。

## 7. 受入 3: 回帰は不変

- `hostshim.c`・`hs_disp_emu.py`・`hs_store_cov.py` は変更していない。既定の全 256 ID run は基準 (72.2 秒) を取り直し、`distinct (rax, path) = 109` を確認 (`REPORT_DISPATCHER.md` §3.1 と一致)。

## 8. 再現コマンド

```
FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store_branch.py
FL_WIN64_DIR=<展開先> HS_DISP_PATH=1 HS_DISP_OUT=base.json python3 hs_disp_emu.py
```

## 9. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 27 行の供給元 (フラグの値の書込み元) の機械語からの確定 (§5) | 受入 1 の後半・受入 2 の前提 | #4849 (PLG-P0b-54: 27 行 (0x1319f13〜0x1326b9a の 24 件と 0x1320fda・0x13210e8・0x1321225) の供給元)。既存の #4130・#4443・#4444 は 27 行の VA を含まない (#4130: 11 件、#4443: 3 件、#4444: 8 件)。#4385 は 0x11a0 格納元 6 ID の書込み関数で VA 指定なし |
| 供給元の値を与えた emulator の実測 (受入 2) | 27 行の到達性は未確認 | #4849 (PLG-P0b-54。受入 2 を含む) |
