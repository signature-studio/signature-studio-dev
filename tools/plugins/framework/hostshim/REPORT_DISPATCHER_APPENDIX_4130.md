# PLG-P0b-43 (#4130) — 未実行の応答スロット格納 11 件の供給元

親 #3735。前提は `REPORT_DISPATCHER_APPENDIX_3735.md` §5 (未実行格納 39 件のうち受け手の実値に依存する 11 件)。

## 1. 測定条件

- 測定 commit: `9f225f5e0` (`hs_store_supplier.py` 追加。コードを変えた最後の commit)。基準 run と `hs_store_cov.py` の数値は `origin/main` (`8635f4546`) で測った (その時点で `hs_store_supplier.py` は未存在)。`hs_disp_emu.py`・`hs_resp_src.py`・`hs_store_cov.py` は `8635f4546` から変更なし。
- 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B) だけを `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf` で 1 件)。Python は venv に `unicorn 2.1.4`・`pefile`・`capstone 5.0.7`。
- 基準 run の再現: `HS_DISP_PATH=1` の全 256 ID (既定・callee 戻り値 0)。実測 1 分 12.8 秒 (`time` の real 72.8 秒)。`distinct (rax, path) = 109` / unmapped 61 ID・5,340 件・200 組・197 ページ。`hs_store_cov.py`: 静的 69・基準被覆 30・未実行 39・no-case-store 202。3735 の値と全て一致。
- 実行は n=1。load は測定中 0.84 前後。

## 2. 受入 1: 11 件の供給元 (機械語から確定)

再現: `FL_WIN64_DIR=<展開先> python3 hs_store_supplier.py` (出力は本 commit の script で作る)。

| 格納 VA | 格納命令 | 供給元 (機械語) | 確定度 |
|---|---|---|---|
| 0x1320e23 | `mov [rbp+0x11a0],rax` | `0x1320e21 call qword ptr [rax]` の戻り値。`rax = *(*(rbp+0x1860))` (0x1320e17〜0x1320e1e)。`[rbp+0x1860]` の値は、この窓の機械語からは確定しない (書込み元は未追跡) | 供給元の型は確定。受け手の vtable 先は未確定 |
| 0x13213f3 | `movsxd rax,eax` 後に格納 | `0x13213ee call qword ptr [rax]` の戻り値 (32bit 符号拡張)。`rax = *(*(0x15e4c00))`。`0x15e4c00` → `0x15f61a8` (ヒープ域) | 同上 |
| 0x1322971 | `mov [rbp+0x11a0],rax` | `0x132296f call qword ptr [rax]` の戻り値。`G=0x15e4790` → `P0=*G=0x141d6b8` → `O=*P0=0` (PE 内の初期値。null) → `A=*(O+0x10)` → `B=*(A+8)` → 呼出先 `*B`。`O` が null のため、以降は null 基準の読み出し | 同上。受け手は PE 内の初期値では null (§3) |
| 0x1328098 | `mov [rbp+0x11a0],1` | 即値 1 | 値は確定。到達条件は §3 |
| 0x1328104 | `mov [rbp+0x11a0],1` | 即値 1 | 同上 |
| 0x1328114 | `mov [rbp+0x11a0],2` | 即値 2 | 同上 |
| 0x1328124 | `mov [rbp+0x11a0],3` | 即値 3 | 同上 |
| 0x1328131 | `mov [rbp+0x11a0],4` | 即値 4 | 同上 |
| 0x132818a | `mov [rbp+0x11a0],1` | 即値 1 | 同上 |
| 0x1328197 | `mov [rbp+0x11a0],2` | 即値 2 | 同上 |
| 0x13281a4 | `mov [rbp+0x11a0],3` | 即値 3 | 同上 |

- 8 件 (即値) は「格納値」が機械語で確定した。未実行の理由は値ではなく到達条件である。
- 3 件 (call 戻り値) は供給元の種別 (間接 call の戻り値) が確定した。呼出先の VA は、受け手 (ヒープ上のオブジェクト) の vtable が PE 内にないため**未確定**。

### 2.1 未確定の列挙

- 呼出先 VA: 0x1320e21 (`[0x15f7190]` の vtable 先)・0x13213ee (`[0x15f61a8]` の vtable 先)・0x132296f (`[...+0x10]+8` の vtable 先)。3 件とも、実行時の受け手オブジェクトの値が無いと確定しない。
- 0x15e4790 の連鎖 `+0x10` 以降 (0x1322957〜0x1322969) は PE 外の値を読む。

## 3. 受入 1 の補足: 到達条件 (8 件の即値格納)

確定した事実 (`hs4130_gate.py` の実測・PE 内の初期値):

- 0x13280b3・0x13280cf・0x1328149・0x1328161・0x1322957 の 5 つの読み出しは、すべて同じ global `0x15e4790` から始まる。`*(0x15e4790) = 0x141d6b8`、`*(0x141d6b8) = 0` (PE 内の初期値)。したがって、この連鎖の先頭は PE 内の初期値では null オブジェクトである。
- 基準 run で 0x13280c9 と 0x132815f の gate は実行され、どちらも `je 0x13281af` で分岐する (実測 path)。そのため 0x1328098〜0x13281a4 の即値格納には到達しない。
- 0x1322971 の call 戻り値格納は、基準 run の ID 0x98 で 0x132296f の間接 call まで実行される (実測 path)。その後の経路は emulator 上で 0 ページを踏んで終わり (stop=ended・最終 callout なし・unmapped 196 件)、格納 0x1322971 には届かない。受け手の vtable が null 由来である点が根拠 (§2 の `*(0x141d6b8)=0`)。
- 0x13280c5 の gate (`cmp byte [rax+0x40],0; je 0x13281af`) と 0x132815f の gate は、この null 連鎖から読む。0x13280e1 の `al` (0x1328104〜0x1328131 の入力) も同じ連鎖 (`+0x4c`・`+8`・`+0x41`) を経由する。
- 0x132818a〜0x13281a4 の入力 `byte [rax+0x42]` も同じ連鎖 (`+0x4c`・`+8`) を経由する。
- 結論: 8 件が実行されるには、`0x15e4790` が指す null の先に、初期化で実値が入っている必要がある。PE 内の初期値では、その gate は閉じたまま。256 ID の既定 run で 8 件が一度も実行されない理由は、この null 連鎖である (本 run で確認したのは連鎖の値であり、初期化が書く値は未確定)。

未確認 (本 run では検証していない):

- 0x1328098 の `cmp byte [rbp+0x89f],2` の `[rbp+0x89f]` の書込み元 (`0x1326c34`・`0x1327f9a`) が、基準 run の経路上で実行されるか。経路は未確認。

## 4. 受入 2: hostshim.c への反映

- `hostshim.c` に、これら 11 格納の応答表は無い (`grep` で 0x1328・0x1320e・0x13213・0x1322971 に該当なし)。応答表の変更は行わない。
- 理由: 8 件の即値は値が確定したが、到達させる gate の入力が PE 外の状態で、表に入れても実行されない。3 件の call 戻り値は受け手の vtable が未確定で、値の供給元を決められない。
- `hs_e2e.sh` Phase A の回帰 (`dispatch=38 ff=0`) は**本 run では実行していない**。理由: `work-fw-stage1` の中身は `fw*.restored.ll`・`fw_map.json`・`fw_icall.dll` の 12 件で、`hs_e2e.sh` が要求する `fw_flat4_canon3.ll`・`fw_image.bin`・`fw_rt.c` 等は無い。さらに emsdk (`emsdk_env.sh`・`docs/REFERENCES.md` の `[EMSDK]`) が runner に無い。hostshim.c を変えていないため、Phase A の結果は変わらない見込みだが、実測はしていない。

## 5. 受入 3: 再現

```
FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_disp_emu.py          # 基準 (HS_DISP_PATH=1 HS_DISP_OUT=base.json)
FL_WIN64_DIR=<展開先> python3 hs_store_cov.py base.json                                    # 静的 69・未実行 39
FL_WIN64_DIR=<展開先> python3 hs_store_supplier.py                                         # 11 件の供給元
```

基準 JSON は `$RUNNER_TEMP/hs4130/base.json` に置いた (リポジトリには入れない)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 3 件 (0x1320e23・0x13213f3・0x1322971) の受け手 vtable 先と、実行時の受け手オブジェクトの値 | 応答表への反映の可否 | 子 #4443 (PLG-P0b-48) |
| 8 件の即値格納の gate 入力 (`0x15e4790` 連鎖の初期化が書く値・`[rbp+0x89f]` の書込み元の経路) | 8 件を実行させる条件 | 子 #4444 (PLG-P0b-49) |
| Phase A の回帰 (`dispatch=38 ff=0`) の実測 | 応答表は未変更のため影響なし。回帰の確認のみ | 本 PR の未解決表。素材 (`fw_flat4_canon3.ll` 等) と emsdk が揃う run で実施 |
