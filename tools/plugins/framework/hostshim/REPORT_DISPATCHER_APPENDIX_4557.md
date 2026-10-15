# PLG-P0b-51 (#4557) — G18 書込み関数の呼出し元と P45 分岐の前提

親 #4385 (PLG-P0b-47)。前身は `REPORT_DISPATCHER_APPENDIX_3673.md` §2・§4.1 (6 ID の書込み元 VA と未確定)。
本付録は新規ファイル。#4385 の付録 (`REPORT_DISPATCHER_APPENDIX_4385.md`) は未作成のため、本 issue の計装結果をここに書く。

## 0. 結論

| 受入 | 結果 | 状態 |
|---|---|---|
| 1 0x41d8f0 の呼出し元 0x1376870 の経路と `r9` の値 | 0x41d8f0 の直接呼出しは 0x1376870 の 1 件 (E8 走査)。その外側 0x1376820 は直接・間接の参照が画像内に無い (下 §2)。`r9 == 1` で G18 書込み (0x41d919) に到達。`r9` の実行時の値は**未確定** | 部分 |
| 2 P45 の分岐 0x11fbb4f の前提と書込み | 分岐は `[[rbp+0x140]+0x10] == 0xb` (0x11fbb4f)。`[rbp+0x140]` は 0x6668d0 の戻り値。0x11fc2b3 の到達は戻り値の `+0x10 == 0xb` のとき。0x6668d0 の戻り値の実体は**未確定** | 部分 |
| 3 G18・P45 の実行時の値 | 未確定 (上の 1・2 の未確定部分)。書込み条件 (`r9==1`・`[+0x10]==0xb`) までを確定 | 部分 |

## 1. 測定条件

- 測定 commit: `ebd21817e` (`hs_val_probe.py` に `g18caller`・`p45caller` を追加。コードを変えた最後の commit)。基点は main `566304b53`。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (5.7 秒)。`work-fw-stage1` はリポジトリ root 基準のパスで `tools/plugins/work/fw/` に展開 (12 ファイル)。
- Python: `$RUNNER_TEMP/hsvenv` (`unicorn 2.1.4` / `pefile` / `capstone`)。
- 負の確認: `g18caller` の `edx=0` と `edx=2` で G18 書込みが無いこと、`p45caller` の `+0x10=0` で P45 書込みが無いことで、観測点が効いていることを確かめた。

## 2. 呼出し元の探索 (静的)

| 対象 | 探索 | 結果 |
|---|---|---|
| 0x41d8f0 | rel32 直接呼出し | 0x1376870 の 1 件 |
| 0x1376820 | rel32 直接呼出し・jmp・rip 相対 lea・8 バイト絶対参照・4 バイト RVA・即値 | 0 件 (`.pdata` の unwind 項目のみ)。直接の呼出し元は無い |
| 0x11fba90 | rel32 直接呼出し | 0x124e621 の 1 件 |
| 0x124e410 | rel32・RVA・lea | 0 件 (`.pdata` のみ)。直接の呼出し元は無い |
| 0x6668d0 | rel32 直接呼出し | 0x946622・0x11fbb23 の 2 件 |

0x1376820 と 0x124e410 はどちらも静的に参照されず、実行時に間接的に呼ばれる。呼出し元を辿れるのは、この 2 関数の一段上まで。

## 3. 受入 1: G18 (0x41d919 `mov [G18], rdi`)

`hs_val_probe.py g18caller` (n=1・各 6.4 秒)。0x1376820 を `edx` ごとに単独実行 (`rcx=HOST, r8=0x18`):

| edx (= 0x41d8f0 の r9d) | 0x41d919 (G18 書込み) | 書込み値 |
|---|---|---|
| 0 | 到達せず | - |
| 1 | 到達 | `rdi` = `[rbp+0x30]` = 0x40000000 (stub 入力) |
| 2 | 到達せず | - |

0x41d8f0 の `r9d == 1` の分岐 (0x41d905) が条件。書込み値は 0x41d8f0 の第 3 引数 `r8` (`rdi`)。0x1376820 では `r8` = `[rbp+0x30]`、つまり 0x1376820 の第 1 引数 (rcx)。

**未確定**: 0x1376820 の呼出し元が `edx` に何を入れるか。静的参照が無いため、実行時の値は測れていない。

## 4. 受入 2: P45 (0x11fc2b3 `mov [P45], rax`)

`hs_val_probe.py p45caller` (n=1・各 6.4 秒)。0x11fba90 を単独実行 (`rcx=obj`, `[obj+0x34a8]=0`, `[obj+0x3518]=0x77`)。0x6668d0 は stub で `[+0x10]` を指定:

| 0x6668d0 戻り値の `[+0x10]` | 0x11fbb4f (cmp eax,0xb) | 0x11fc2b3 (P45 書込み) |
|---|---|---|
| 0xb | je 0x11fc2ac へ分岐 | 到達 (rax = rcx = this) |
| 0x0 | 0x11fc53b へ | 到達せず |

書込み値は `rax` = `[rbp+0x170]` = 0x11fba90 の第 1 引数 (rcx = this)。

**未確定**: 0x6668d0 の戻り値の実体 (受け手のオブジェクトと `+0x10`)。P45 = this は確定、`[this+0x3518]` の値 (ID 0x45 の応答) は未確定。

## 5. 回帰 (Phase A)

- `fw_stage2.sh` (`FW_W` 既定): 6 分 53 秒・rc=1。`[fw] SMOKE PASS (Halt0/RestoreContext 到達): dispatch=38 units_done=0 va=1 heap=1 ff=0`。`fw_smoke_check` の FAIL (`runerr` / `init_reach`) は既存 #2510 の既知の失敗。
- `hs_e2e.sh`: 2 分 38 秒・rc=1。Phase A `[fw] Phase A (framework smoke): Halt0/RestoreContext dispatch=38 ff=0` → PASS。Phase B `memory access out of bounds` は既存 #2911 の既知の失敗。
- load average: 開始時 0.52、終了時は未採取。
- 注: 本 run の hostshim コードは変えていない (`hs_val_probe.py` の観測モード追加のみ)。`hostshim.c` と e2e 経路は変わらない。

## 6. 未解決 (起票先)

| 0x1376820 の呼出し元 (静的参照なし・間接呼出し) と `edx` (= `r9`) の実行時の値 | G18 (ID 0x18) の値 | #4385 ([PLG-P0b-47]) |
| 0x124e410 の呼出し元と、0x6668d0 の戻り値 (`[+0x10]`) の実体 (0x946622 の経路を含む) | P45 (ID 0x45) の値と応答 | #4385 ([PLG-P0b-47]) |
