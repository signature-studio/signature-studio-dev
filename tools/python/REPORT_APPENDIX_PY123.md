# PY-123 (#3028) 付録: 0 化の命令の特定 (REPORT_PY123.md §2-5 の全文)

本文 `REPORT_PY123.md` は 250 行上限のため、§2-5 を分割移動した (内容は削除していない。Git 履歴にも残る)。

## 2-5. 0 化の命令の特定 (3 回目・WWATCH 測定 commit `009855d26`・HEAD `cd2166181` で両ビルドを再現)

計測: `rt/fle_cpu.h` の ST8〜STF64・STX・STY に、`FLE_WWATCH` 定義時だけ働く書込みフックを入れた (既定は無効)。`fle_cpu.c` の `fle_wwatch` は、監視 slot (`0x15e1c78`・`0x15e4790`) に重なる書込みのうち値が変わるものだけ `__FILE__:__LINE__` 付きで出す。`build.sh` は `FLE_EXTRA_CCF=-DFLE_WWATCH` で有効化する。

```
[fle_wwatch] slot=0x15e1c78 a=0x15e1c70 n=16 old=0x16bb068 new=0 at .../rt/fle_cpu.h:78
[fle_wwatch] slot=0x15e4790 a=0x15e4790 n=16 old=0x141d6b8 new=0 at .../rt/fle_cpu.h:78
```

- 2 件とも 16 バイト書込み (STX/STY 系)。`__LINE__` が inline 関数の中を指すため、呼出元は次の 2 点で対応づけた (行番号は `009855d26` では fle_cpu.h:78、HEAD のコメント 1 行追加後は :79)。
- 直前の `[fill6a7b70]` 行 (fill コールバック `0x6a7b70` の dispatch 時の引数) は 6 件だけ。呼出し #5 が `dst=0x1400000`・`val=0x0`・`cnt=0x100000` (DWORD 個数 = 4 MiB)。#0〜#4 は dst=0x0 から 0x400000 刻みで、6 回で guest 0x0〜0x1800000 を 0 にする (PE image の VA 0x400000 以降を含む)。hit は #5 だけ (`old≠new` の書込みは #5 内の 2 件)。
- 陰性対照: #0〜#4 は guest 0x0〜0x1400000 だけを覆い、監視 slot (0x15e1c70 以上) に重ならない。ヒット 0 件はこの対照どおり。
- 命令 (PE の逆アセンブル `pe_disasm.py 0x6a7b70 40`・§7。lift 出力 `work/boot/lift/` は gitignore のため根拠にしない): `movd xmm0, edx` で値を 4 バイトずつ広げ、`r8` (DWORD 個数 >> 4) 回、rcx から 0x40 刻みで 4 本の `movdqu` を書く。ループ内に `call` は無い。

| VA | 命令 | 監視 slot との対応 |
|---|---|---|
| `0x6a7b84` | `movdqu xmmword ptr [rcx], xmm0` | (対象外) |
| `0x6a7b88` | `movdqu xmmword ptr [rcx + 0x10], xmm0` | `0x15e4790` (a=`0x15e4790`) |
| `0x6a7b8d` | `movdqu xmmword ptr [rcx + 0x20], xmm0` | (対象外) |
| `0x6a7b92` | `movdqu xmmword ptr [rcx + 0x30], xmm0` | `0x15e1c78` (a=`0x15e1c70`) |

- 対応の根拠 (算術・直接観測ではない): dst=`0x1400000` は 0x40 の倍数で、rcx は 0x40 刻みに進む。`0x15e1c70 − 0x1400000 = 0x1E1C70` は mod 0x40 で `0x30` → VA `0x6a7b92`。`0x15e4790 − 0x1400000 = 0x1E4790` は mod 0x40 で `0x10` → VA `0x6a7b88`。
- 結論: **0 化を行う命令は `f_6a7b70` の `movdqu` (VA `0x6a7b88`・`0x6a7b92`)** (静的は PE の VA 表で確認。動的ヒットとの対応は上の算術による)。前 run の「間接書込み・未特定」は、fill 関数の 16 バイト書込みで解消した (前 run の §2-3 の窓 `f_412c90` の外)。
- 残り: fill の幅 (`r8` = 0x100000 DWORD) と rect (w=h=1048576) の源は、呼出元 `0x815920` (callerRbp の +0x214/+0x218) で、未確定。#3090 [FLE-12] の範囲だったが、#3090 は縮小 close 済みで、残件は #3112 [FLE-13] が追う。0 化と unit 209 の icall-miss・exit の因果は未確認 (§2-4)。
- 既定ビルド (`FLE_EXTRA_CCF` 無し・shim 有・HEAD `cd2166181`・`fle6_measure.sh`): units_run 209 / 942・停止 `MessageBoxA`→`exit(0)`・getmem 2314 / freemem 1199 (WWATCH 版と同じ)。`py_events` も同じ (unit 209・site 8 で両 slot が 0)。`[fle_wwatch]` は 0 件 (フック無効)。`FLEBOOT_IPP_CHECK ok:false` は既知の NG で rc=3 (変更前と同じ)。結果 JSON は `results/boot_summary_py123def.json`。同条件の前測定 (`fee239ea2`・main 取り込み前) も units_run 209・停止同じ。
- WWATCH 版 (HEAD `cd2166181` で再現): `[fle_wwatch]` 2 件・fill 6 件・units_run 209 / 942・停止 `MessageBoxA`→`exit(0)` (前測定と同じ)。
- 最初のウィンドウ無し。`FLE_WWATCH` は計測用の既定無効フックで、`ST*`/`STX`/`STY` は未定義時に従来と同じ展開になる (コード検査。既定ビルドは上で実測)。

## 2-7. obj (`[[0x15e4790]+8]` = `0x141d6c0`) の設定経路 (5 回目・PY-201 後続・測定 commit `729a5aaab`)

本文 §2-6 の未解決 (obj を設定する書込み元) を追った。判定は「停止点 (unit 209) までに設定経路が実行されるか」。

静的 (PE・`FL_WIN64_DIR` 必須):
- `pe_xref.py 141d6c0,141d6b8`: `0x141d6c0`・`0x141d6b8` を RIP 相対で参照する命令は 9 件。書込みは 3 件で、いずれも 0 を書くか `[0x141d6b8]` に格納する (`0x976aad`・`0x976ac4`・`0x976b10`)。obj へ非 0 を直接書く命令は PE に無い。
- PE の初期値 (`block00031_PE.bin`・`.data` の file 上の u64・本 run で再読): `[0x141d6c0]` = `0x0`・`[0x141d6b8]` = `0x0`・`[0x15e4790]` = `0x141d6b8`。停止点まで obj が 0 のまま、という §2-7 の結論と整合する。
- 関数 `0x976a90` 付近 (逆アセンブル `pe_disasm.py 0x976a95 30`): `[0x141d6b8]` が 0 なら `0x976b60` で作って `[0x141d6b8]` に格納し、非 0 なら `[0x141d6c0]` の関数ポインタを呼んでから `[0x141d6c0]` を 0 にし、`[[0x141d6b8]+0x40]` の vtable 先頭を呼ぶ。この関数を以下「teardown 関数」と呼ぶ。
- 注意: teardown 関数は `[0x141d6c0]` を**関数ポインタ**として呼ぶ。PY-201 が前提にした「obj はオブジェクト (述語の VA は `[obj+0x98]`)」とは読みが食い違う。どちらが正しいかは未確定 (ここでは判定しない)。
- `pe_slot_writers.py 15e4790 8` (`[reg+8]` 経由の候補): 20 件 (dword 13・qword 7)。qword の 7 件 (`0xedffd2`・`0xeef1c2`・`0x11c44e5`・`0x11c7aec`・`0x1263571`・`0x1264145`・`0x1312884`) は未個別検証 (tool の注記どおり、逆アセンブルで確認が要る)。

動的 (`tools/flelift/boot/py301_undo_obj_probe.sh`・HEAD `729a5aaab`・shim 有):
- 書込み監視 (`FLE_WWATCH_SLOTS=0x141d6c0,0x141d6b8,0x15e4790,0x15e1c78`・値が変わる書込みだけ出す): 2 件。どちらも unit 209 の fill (`0x15e4790`・`0x15e1c78` の 0 化)。obj と `[0x141d6b8]` への値が変わる書込みは **0 件** (unit 1〜209)。
- 入口の計測 (dbg_lift で挿入・計測のみ): `0x976a95` (teardown 関数の入口) **0 件** (未到達)・`0x976b60` (作成呼出し先) **0 件** (未到達)。
- 陽性対照 `0x412a0d` (boot 末尾の MessageBoxA → exit の call site): **1 件** (`[PY301-c] 0x412a0d n=1 (control)`)。観測の仕組みは効いている。
- 制約: WWATCH は ST* マクロ経由の書込みだけを見る。`imp_memset` 等の C 側の書込みと、`rep` 系の書込みは監視外 (未確認)。0 を書く候補は値が変わらないため出ない。

結論: obj を非 0 にする経路 (teardown 関数・作成呼出し・`[reg+8]` の候補) は、**停止点 (unit 209) までの lifted 実行では 1 度も実行されない** (ST* 経由の書込みの範囲で。入口観測も 0 件)。したがって boot 停止時点では obj は 0 のままで、受入 2 (述語の VA) と 3 (singleton) は、停止点を越えて経路に届くまで測れない。停止点を越える前提は fill の修復 (#3112 [FLE-13]・OPEN)。停止点の呼出元は #3060 FLE-11 で確定済みで、#3090 [FLE-12] は PR #3114 merge・PM 判断で縮小 close 済み。その先で止まる unlifted `0x6bbc20` は #3491 (CLOSED)・#3770 (CLOSED) を経て #3771 (OPEN) に引き継がれている。

KPI (起動に関わる変更ではないが、boot 実行の前後を記録): units_run 209/942 (前後で同じ)。最初のウィンドウ: 無し (MessageBoxA → exit(0))。`FLEBOOT_IPP_CHECK` shim は既知の `ok:false` (rc=3 は変更前と同じ)。boot の挙動は変えていない (計測の追加のみ)。

測定:
- ベースライン: `FLE_BOOT_TAG=py301 FLE_BOOT_RUNS="shim" bash tools/flelift/boot/fle6_measure.sh` (lift・clang 含む) real 3 分 45.7 秒 (user 5 分 54 秒・sys 42.7 秒)。clang-plain 112 s・boot shim 25 s・開始 load `2.68 1.44 0.67`。並列 1 本。結果 JSON は `results/boot_summary_py301.json` (commit `729a5aaab`)。
- 本体 (HEAD `729a5aaab`): `bash tools/flelift/boot/py301_undo_obj_probe.sh` real 2 分 18.1 秒 (build + boot)。出力: `probes: 3 (expect 3)`・`PY301 行: 1`・`fle_wwatch` 2 件・`FLEBOOT_RESULT` units_run 209 (前記)。
- 差分 (WORKFLOW §6): 測定 commit `729a5aaab` は、この節の時点で `tools/flelift` のコードを変えた最後の commit。`git diff 729a5aaab HEAD -- tools/flelift` は REPORT の commit までで空 (差分 0)。


## 付録 §B. 既定経路 (`FLE_IPP` 未指定) での undo 状態と obj 設定経路 (PY-304・#4135)

前 run までの測定は shim 有 (`FLE_IPP=1`) で units 209 の停止点までだった。既定経路は付録 672 §C-2 で units 895 まで進むため、同じ観測を既定経路で行った (`#3112` の fill 修復を待たずに、停止点の後の値を見るため)。

- lift・root: `env -u FLE_EXTRA_ROOTS FLE_BOOT_TAG=py304root FLE_BOOT_RUNS=default bash tools/flelift/boot/fle6_measure.sh` (既定 root `0x6a7b70` + boot_roots `0x976da0`)。lift 81 s・clang-plain 81 s・boot 10 s。
- 判定 (既定 root): `units_run` **895 / 942**・停止 `exit` (code 0)・`FLEBOOT_IPP_CHECK` `ok:true` (ptr `0x7f10001c`)。§C-2 と一致。`FLE_EXTRA_ROOTS=` (root 無し) で同じ boot を流すと units は 895 (`py304def`)。
- 測定 commit: `e20037cc9` (`PY301_IPP` 切替えを入れた commit。probe はこの commit の `py301_undo_obj_probe.sh` で実行した)。`git diff e20037cc9 HEAD -- tools/flelift` の出力は空 (main 取り込み後も同じ)。`20224099e` は切替え前の commit なので測定 commit ではない。
- probe: `PY301_IPP= bash tools/flelift/boot/py301_undo_obj_probe.sh`。`probes: 3 (expect 3)`・`PY301 行: 6`・`fle_wwatch` 1 件 (`0x141d6b8`: 0 → `0x12d15e20`)・陽性対照 `[PY301-c] 0x412a0d n=1` あり。

| 観測 | 既定経路 (units 895) | shim 有 (units 209・§2-6・§2-7) |
|---|---|---|
| `0x976a95` (obj 設定経路の入口) | **4 回**入る。`obj` = `0x0` のまま | 入口 0 件 (§2-7) |
| `0x976b60` (作成呼出し先の入口) | **1 回**入る (`rcx=0x9764d8`・`dl=1`)。その時点の `[0x141d6b8]` = 0 | 入口 0 件 (§2-7) |
| `obj` (`0x141d6c0`) の書込み (WWATCH) | **0 件** (`0x141d6b8` の書込み 1 件だけ) | 0 件 |
| py_snap `last` (boot 終了時 = unit 895 の直後) | pos `0`・count `0`・`safe_obj` `0x0`・`f98`/`f88` `0x0`・`sing` `0x0` | pos 0・count 0・obj 0・sing 0 (unit 209 の直前) |
| py_snap `trace` | 1 件 (unit 0 のみ)・`over` 0 | 1 件 (unit 0 のみ) |
| `py_events` | 6 件 (site 0 の初期値のみ・unit 0)。unit 209 の 0 化は**無い** | 6 件 (初期値 + unit 209 の 0 化 3 件) |

読み取り:

- 既定経路では **作成呼出し `0x976b60` まで実行される**。shim 有では実行されなかったので、「設定経路が停止点までに未実行」は shim 有の停止点の性質で、既定経路では当てはまらない。
- ただし `obj` (`[0x141d6c0]`) は既定経路でも boot 終了まで **0 のまま**。`0x976b60` の作成結果を `obj` に入れる書込みは、WWATCH (ST* 系の書込み監視) で捕まっていない。`obj` を書く経路は ST* 以外 (直接の memory 書込み・別関数の内部) か、作成が NULL を返しているかのどちらか。ここでは区別できない。
- WWATCH 1 件 (`0x141d6b8`: 0 → `0x12d15e20`) は、`0x141d6b8` (Q スロット) の値が `0x12d15e20` になった書込みで、隣接 slot (`0x141d6c0` = obj) の書込みではない。書込み元の命令は本 run では特定していない (WWATCH の出力に呼出し元の情報が無い)。`0x12d15e20` の実体も未確認。「不明」として残す。
- **訂正 (#4135)**: 第 31 波の『`0x1263571`・`0x1264145` は obj (`[S+8]` = `0x141d6c0`) への書込み』は誤り。逆アセンブル (lift C) では `rcx = [0x15e4790]` (= S) の後に `mov rcx, [rcx]` があるので、書込み先は `[[S]+8]` (3 段の deref)。`[S+8]` (= obj) の読みは前回の probe で正しい。以下 §B-2 の実測で確定。
- singleton `[0x16b82e0]` は boot 終了時点で 0 (NULL)。ただし Python の `None` は別の静的オブジェクトのアドレスで、0 は「未設定」と同じ。受入 2 の『`None` か』は、この値では判定できない (`None` の VA の特定が要る)。
- unit 895 の `exit` は、付録 672 §C-2 の未解決 (MessageBoxW 不在の影響か) と同じ停止。その判定は #4970 [FLE-36] (OPEN) が追う (#4782 [FLE-24] は 2026-10-15 に close 済み)。fill の 0 化 (`py_events` の unit 209 の 3 件) は既定経路では起きない。

### §B-2. 書込み経路の観測 (既定経路・#4135・probe は `py301_obj_writer_probe.sh`)

- 測定 commit: `a4ba758fc` (挿入番地を直し、挿入数の判定を入れた commit)。`git diff a4ba758fc HEAD -- tools/flelift` の出力は空。
- 訂正 (#4135): 前の commit `02aee1e34` の probe は `0x1264100` を挿入できていなかった。`0x1264100` は命令境界ではなく (`0x12640ff` の命令の途中)、`dbg_lift.py` は解決できず 0 件のまま `|| true` で続行していた (挿入 4/5)。この版の `0x1264100` の「0 回」は観測ではないので採らない。関数入口は `0x1264050` (`push rbp`)。
- 既定経路: `FLE_IPP=` (未指定) で `--boot-only`。lift `fle6_measure.sh` (`FLE_EXTRA_ROOTS` 未指定 = 既定 root) の後、probe (`py301_obj_writer_probe.sh`・挿入は番地ごとに 1 回ずつ確認し、欠ければ exit 3) を実行。probe 1 回 real 1 分 52 秒 (load `1.99 1.44 0.74`)。
- 判定: `units_run` **895 / 942**・`exit`・`probes: 5 (expect 5)`・`PY301o 行: 3`。陽性対照 `[PY301o-c] 0x412a0d n=1` あり。

| 観測 | 結果 |
|---|---|
| `0x1263540` (`0x1263571` を含む関数の入口) | **1 回**入る。`S=0x141d6b8`・`P=[S]=0x12d15e20`・`[P+8]=0` |
| `0x1263571` (`mov [rcx+8], rax`・`rcx=P`) | **1 回**。`rax=0x12e99a40`・書込み先 `0x12d15e28` |
| `0x1264050` (`0x1264145` を含む関数 `f_1264050` の入口) | **0 回** (挿入 1 本を確認済み) |
| `0x1264145` (`mov [rcx+8], rax`) | **0 回** (挿入 1 本を確認済み) |

読み取り:

- 既定経路では、`0x1263540` が 1 回だけ呼ばれ、その中の `0x976a90` と `0x125da90` の後に `[[S]+8]` (`0x12d15e28`) へ作成結果 `0x12e99a40` を入れる。`obj` (`[S+8]` = `0x141d6c0`) への書込みではない。
- `0x1263571` は `0x12d15e28` の値を `0` から `0x12e99a40` へ変える。WWATCH の監視 slot は `0x141d6c0`・`0x141d6b8`・`0x15e4790`・`0x15e1c78` で `0x12d15e28` を含まないため、観測されなかった。
- `0x1264050` と `0x1264145` は、挿入が確認されたうえで既定経路の units 895 までに 0 回だった。`[[S]+8]` への作成結果の書込みは、既定経路では `0x1263571` の 1 回だけ。
- 前回 (§B) の『obj (`0x141d6c0`) は 0 のまま』は、この経路の書込みを見ていないだけで、読み自体は正しい。受入 1 の述語 `[obj+0x98]`・`[obj+0x88]` の `obj` の番地 (`0x141d6c0` か `0x12d15e28` 側か) は、ここでは決まらない。
- singleton `[0x16b82e0]` の判定は未着手 (前回と同じく `None` の VA が要る)。

KPI: units_run 895/942・最初のウィンドウ無し (`exit`)。boot 本体は変更なし。
