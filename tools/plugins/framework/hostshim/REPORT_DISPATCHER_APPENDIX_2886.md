# PLG-P0b-25 (#2886) — Dispatcher 応答スロット `[rbp+0x11a0]` の格納元と仮想呼出し出口

親 #2782。前身の測定と経緯は `REPORT_DISPATCHER.md` §1〜§9 (#1222)。
本付録は新規ファイルで、`REPORT_DISPATCHER.md` からの分割移動ではない (本文の §11 から参照)。

- 解析 VA はすべて block00031 (ImageBase 0x10000000 系の FLE 実装)。機械語は `capstone` で逆アセンブル。
- 応答は Dispatcher 末尾 `0x1328a38` (`mov rax,[rbp+0x11a0]`) で読まれる。格納は共通初期化 `0x131873f` (`mov qword [rbp+0x11a0],0`) と case 格納 (§2 の 19 ID)、および共通後処理 `0x13281af` 以降の状態格納 (§3.2) の 3 系統。

## 1. 測定条件

- 測定 commit: 解析ツール `2d523491` (`hs_resp_src.py` 新規・`hs_disp_emu.py` に `HS_DISP_PATH=1` の追加)、
  応答表 `2dca40dd` (`hostshim.c` の 3 行追加)。§3.4 の測定: `aff22692` (`hs_disp_emu.py` に `HS_DISP_RET_SPEC` の `one` 追加・`hs_store_cov.py` 新規)。
  `hostshim.c` と `hs_resp_src.py` は `2dca40dd` 以降変更なし。
- 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 bytes) を `$RUNNER_TEMP/fl-win64` に展開 (2.3 秒)。
  `unicorn 2.1.4` / `pefile 2024.8.26` / `capstone 5.0.9` を `$RUNNER_TEMP/pylib` に導入。
- `hs_resp_src.py` (46 ID): 49.9 秒 (n=1)。終了時 load (1 分平均) 0.67。
- 既存回帰 `hs_disp_emu.py` (全 256 ID・既定): 50.9 秒 (n=1)。`distinct (rax, path) = 109` / unmapped 61 ID・5,340 件・200 組・197 ページ。
  REPORT_DISPATCHER §3.1・§3.3 の値と一致 (経路判定の既存結果は不変)。

## 2. 受入 1: 格納元 19 ID の出所 (機械語 VA)

実行経路上で最後に `[rbp+0x11a0]` へ格納した命令 (格納 VA) と、その値の出所。`hs_resp_src.py` の経路逆追跡と機械語の直読で確定。

| ID | 格納 VA | 格納値の出所 (機械語 VA) | 種別 |
|---|---|---|---|
| 0x01 | 0x1318e46 | `call 0x11ffde0` (0x1318e3e) の戻り値 eax → `movsxd` (0x1318e43) | call 戻り値 (int32) |
| 0x07 | 0x13192eb | `call 0x41d110` (0x13192da) の戻り値 + `0x2a8` (0x13192df・0x13192e7) | TLS 要素ポインタ + 0x2a8 (非 NULL) |
| 0x0e | 0x1319561 | `call 0x41d110` (0x1319550) の戻り値 + `0x2a8` (0x131955d) | 同上 |
| 0x13 | 0x1319f6e | `call 0x9636a0` (0x1319f66) の戻り値 eax → `movsxd` (0x1319f6b) | call 戻り値 (int32) |
| 0x18 | 0x131a268 | `mov rax,[rip+0x2d2030]` (0x131a261) = グローバル値 | グローバル |
| 0x1c | 0x131b8d1 | `call 0x41d110` (0x131b8c0) の戻り値 + `0x2a8` (0x131b8cd) | TLS 要素ポインタ + 0x2a8 (非 NULL) |
| 0x1d | 0x131bb50 | `call 0x41d110` (0x131bb3f) の戻り値 + `0x2a8` (0x131bb4c) | 同上 |
| 0x26 | 0x131c415 | `call 0xe4e970` (0x131c40c) の戻り値 al → `movsx` (0x131c411) | call 戻り値 (bool) |
| 0x2e | 0x1320de8 | `call 0x86c900` (0x1320de3) の戻り値 rax (rcx = `[[rip+0x2c2318]]`, 0x1320dd9〜0x1320de0) | call 戻り値 |
| 0x3d | 0x1321780 | `call 0x41d110` (0x132176f) の戻り値 + `0x2a8` (0x132177c) | 同上 |
| 0x41 | 0x1321a2f | `call 0x11d06e0` (0x1321a1b) が出力する `word [rbp+0x111c]` を `cmp`/`sete al` (0x1321a20・0x1321a28) → `movsx` | callee の出力引数 (bool) |
| 0x45 | 0x1321b89 | `movsxd rax,[[[rip+0x2bf479]]+0x3518]` (0x1321b78〜0x1321b82) | グローバル → フィールド (int32) |
| 0x46 | 0x1321bf1 | `call 0xed6780` (0x1321be8) の戻り値 al → `movsx` (0x1321bed) | call 戻り値 (bool) |
| 0x47 | 0x1321c10 | `call 0x75b3d0` (0x1321c0b) の戻り値 (rcx = `[[[rip+0x2c2b8c]]+0x30]`, 0x1321bfd〜0x1321c07) | call 戻り値 |
| 0x4e | 0x1319fd0 | `call 0x41d110` (0x1319fbf) の戻り値 + `0x2a8` (0x1319fcc) | TLS 要素ポインタ + 0x2a8 (非 NULL) |
| 0x54 | 0x13226dd | `movsxd rax,[rax+rcx*4]`、rax = `[rip+0x2bfa46]` (テーブル基底)、rcx = `[rbp+0x1880]` (0x13226cb〜0x13226d9) | グローバル配列 × フィールド (int32) |
| 0x56 | 0x131bb66 | `mov rax,[rip+0x2c9005]` (0x131bb5c) → `mov rax,[rax]` (0x131bb63) の値 = `[[rip+X]]` | グローバルの 2 段 deref (qword) |
| 0x64 | 0x1322a07 | `cmp dword [[[rip+0x2c0702]]+0x168],0` → `setg al` → `movsx` (0x13229ef〜0x1322a03) | グローバル → フィールド比較 (bool) |
| 0x65 | 0x1322b47 | `movsxd rax,[rbp+0x109c]`。0x1322a55 で `0` 格納、または 0x1322b38 で `movss` (float のビット列) | ローカル (0 か float) |

- 分類: TLS 要素ポインタ + `0x2a8` (非 NULL ポインタ) が 6 ID (0x07・0x0e・0x1c・0x1d・0x3d・0x4e)、call 戻り値が 6 ID (0x01・0x13・0x26・0x2e・0x46・0x47)、
  callee 出力引数 1 (0x41)、グローバル・フィールド 5 (0x18・0x45・0x54・0x56・0x64)、ローカル 1 (0x65)。
- `0x41d110` の戻り値は `REPORT_DISPATCHER.md` §8.1 の「有効なポインタ (TLS 配列の要素)」。整数値ではない。
- 注意: 整数・bool 値の実値 (call 先の戻り値・グローバルの中身) は emulator では確定しない (callee 0 代替)。格納元の種別までが機械語で確定した範囲。

## 3. 受入 2: 仮想呼出しで終わる出口 27 ID

emulator の経路は末端の間接 call で止まる (受け手の vtable が 0 埋め領域のため)。末端後の静的命令で後続を確定した。

### 3.1 分類

| 分類 | ID (末端 call VA) | 後続 (静的・VA) | 応答の決まり方 |
|---|---|---|---|
| **A** 戻り値をそのまま格納 (3) | 0x2f (0x1320e21 `call [rax]`) / 0x3a (0x13213ee `call [rax]`) / 0x62 (0x132296f `call [rax]`) | 0x2f: `mov [0x11a0],rax` (0x1320e23)。0x3a: `movsxd` (0x13213f0) → 格納 (0x13213f3)。0x62: 格納 (0x1322971) | 仮想呼出しの戻り値 (受け手 = `[rax]` 由来・vtable[0])。**未確定** (実機の vtable 依存) |
| **B** 戻り値を捨て `0x13281af` へ (13) | 0x04 (0x1318f4c `call [rbx+0x18]`) / 0x0a (0x1319490 `call [rbx+0x70]`) / 0x1e (0x131bba4 `call [rbx+8]`) / 0x23 (0x131bd0f `call [rbx+0x80]`) / 0x49 (0x1321dd2 `call [rbx+0x58]`) / 0x57 (0x13193eb `call [rbx+0xf0]`) / 0x5d (0x132282f `call [rbx+0x58]`) / 0x5e (0x1322893 `call [rbx+0xc0]`) / 0x5f (0x13228cc `call [rbx+0x98]`) / 0x60 (0x13228eb `call [rbx+0xb8]`) / 0x67 (0x1322b69 `call [rbx+0xc0]`、後続 `call 0x11911b0` 0x1322b6f) / 0x69 (0x1322ba7 `call [rbx+0x60]`) / 0x6a (0x1322be7 `call rax`、rax は `call 0x40ffe0` の戻り値) | 末端 call の直後、または後続 1 命令 (0x67 は `call 0x11911b0`) の後に `jmp 0x13281af`。戻り値は格納されない | **仮想呼出しの戻り値は応答に使われない**。応答は `0x13281af` 以降の状態格納 (§3.2) で決まる (値 0〜4)。状態依存で**未確定** |
| **C** 後続を一部のみ確認 (11) | 0x00 / 0x09 / 0x12 / 0x1a / 0x2c / 0x3c / 0x44 / 0x4b / 0x59 / 0x5b / 0x5c | 戻り値を格納・加工した後に分岐する (例: 0x00 `mov [rbp+0x1048],rax` 0x1318cfb、0x44 `mov [rbp+0xb58],rax` 0x1321b1b、0x59 は別関数 0x132cea0 内で `(eax&0x7fffffff)+1` を返す、0x5b は `test al,al; jne 0x13281af` 0x1320e58) | **未確定** (後続は上記の一部のみ確認。分岐の全体は未追跡) |

### 3.2 共通後処理 `0x13281af` の状態格納 (B 群の応答)

`0x13281af` 以降で `[rbp+0x11a0]` へ書く命令 (静的):

- `0x1328098`: `byte [rbp+0x89f]==2` のとき `1` (`cmp` 0x132808b, `jne` 0x1328092)。
- `0x13280a8`: `0`。
- `0x1328104`〜`0x1328131`: `byte [[[[rip+0x2bc6ba]]]+0x4c]+8 +0x41` の値に応じて `1`/`2`/`3`/`4`。`0x13280b3`〜`0x13280c9` で `byte [..+0x40]==0` なら抜ける。
- `0x132818a`〜`0x13281a4`: `byte [..+0x42]` の値に応じて `1`/`2`/`3`。
- 初期値 `0` (`0x131873f`)。したがって B 群の応答は `{0,1,2,3,4}` のいずれかで、値は実行時の object 状態 (`[rbp+0x89f]`・`[*G+0x4c]+8` のバイト) で決まる。

### 3.3 emulator の限界 (実測)

- 末端 call の受け手は vtable (HOST 0 埋め) のため target = 0 となり、経路が末端で止まる。したがって A・B・C の後続は経路実測ではなく静的読みで確定した。
- B 群の判定 (`jmp 0x13281af`) は機械語の直読であり、末端後の経路を実行していない。

### 3.4 callee 戻り値 0 への依存 (実測)

emulator は未実行の callee を戻り値 0 で代替する。その仮定が経路と応答 0 の集合を変えるかを、callee 0x40fe90 (戻り値 1) で測った。
測定 commit `aff22692` (`hs_disp_emu.py` の `HS_DISP_RET_SPEC=0x40fe90:one`・`hs_store_cov.py`)。基準 (既定) と変更の 2 回、全 256 ID・`HS_DISP_PATH=1`、各 51 秒 (n=1)。

- 0x40fe90 を経由する ID は 11 件 (0x0a 0x11 0x14 0x15 0x17 0x32 0x33 0x34 0x38 0x4c 0x4d)。戻り値 1 で **11 件すべての経路が変わる**。rax も変わるのは 4 件 (0x0a: `0x54534154`→0、0x17: 0→`0x54534154`、0x34: 1→0、0x4c: 0→`0x2a8`)。
- 応答 0 の 202 件 (共通初期化 `0x131873f` の格納だけを実行し、共通終端 `0x1328a4a` に到達する ID): 基準 202、変更 202。件数は同じだが構成が変わる (ID 0x17 が外れ、ID 0x0a が入る)。
- 未収載 25・54・64・88・128 は、基準・変更とも応答 0・共通終端 `0x1328a4a` に到達する (0x40fe90 には依らない)。**ただし 0x40fe90 以外の 81 callee の戻り値依存は未測定**。
- 未実行の格納 (静的 69 − 基準の実行被覆 30 = **39**): 変更で新たに実行されるのは 4 件 (0x1320f72 = ID 0x32、0x13210ae = 0x33、0x13211a1 = 0x34、0x1321efb = 0x4c)。変更で失われるのは 3 件 (0x1320fda・0x13210e8・0x1321225)。
- 残りの未実行格納 35 件の内訳:
  - **11 件は callee 戻り値ではなく受け手の実値に依存**: 仮想呼出し出口の後続 (A 群 0x1320e23・0x13213f3・0x1322971 の 3 件) と、共通後処理 `0x13281af` 以降 (0x1328098・0x1328104・0x1328114・0x1328124・0x1328131・0x132818a・0x1328197・0x13281a4 の 8 件)。emulator は受け手 (vtable) が 0 埋めのため末端で止まる → [PLG-P0b-27]。
  - **24 件は分岐条件が未解析** (callee 戻り値に依存するかは未確定) → [PLG-P0b-28]。
- 旧 #2888 の A-1・B-2 節は本ブランチにも main にも無いため、上記の数値はすべて本節で再導出した。

## 4. 受入 3: `hostshim.c` 応答表と Phase A 回帰

- 変更 (commit `2dca40dd`): 格納元が `0x41d110` 戻り値 + `0x2a8` の 3 ID (0x07・0x1c・0x4e) を `g_hs_obj` (非 NULL) 応答に追加 (`case` 3 行)。他の応答は不変。
- 格納元の種別と現応答表の対応 (2dca40dd 時点):
  - 非 NULL (obj): 0x07・0x0e・0x1c・0x1d・0x3d・0x4e (TLS+0x2a8)・0x2e・0x47・0x56 (ポインタ・deref 系の既定)。
  - 0 固定: 0x01・0x13・0x18・0x26・0x41・0x45・0x46・0x54・0x64・0x65 (整数・bool・グローバル値。実値は未確定 = [PLG-P0b-28] の範囲)。
  - 注意: 非 NULL 応答は `0x41d110` の戻り値 (TLS 要素) ではなく obj を返す。非 NULL 性のみ一致させた。
- Phase A (`hs_e2e.sh` の framework smoke): `[fw] Phase A (framework smoke): Halt0/RestoreContext dispatch=38 ff=0` → **PASS** (変更前後とも)。
- stage-2 (`fw_stage2.sh`・stage-1 再利用・n=1): 5 分 30.2 秒。`SMOKE PASS (Halt0/RestoreContext 到達): dispatch=38 units_done=0 va=1 heap=1 ff=0` は PASS。
  `fw_smoke_check` は **FAIL** (`runerr=1`・`init_reach=16` MISMATCH)。これは `REPORT_2425.md` §4・`REPORT_2510.md` §1 に記録済みの既存状態 (#2510 の idx 16 RunError)。
  `fw_stage2.sh` は hostshim を含まないため、本変更は stage-2 の判定に影響しない (変更前 HEAD でも同一の既存状態)。
- Phase B (`hs_e2e.sh`): `memory access out of bounds`・`status=0xffffffff plug=0x0 rec=7 pluglog=0 slotsCalled=0x0` → **FAIL**。変更前 (`2d523491` の hostshim.c) と変更後 (`2dca40dd`) で同一行 (既存 #1229・#2911 の範囲)。
- 時間: `hs_e2e.sh` 初回 (IR 生成込み) 1 分 58.8 秒 (n=1)。変更後の再実行 12.8 秒 (emcc 増分)。開始 load は未計測。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 仮想呼出し出口のうち A 群 (3 ID)・C 群 (11 ID) の応答値、B 群の状態格納 (0〜4) の実行時条件 | 受入 2 | [PLG-P0b-27] |
| 未実行格納のうち受け手の実値に依存する 11 件 (§3.4) | 受入 2 | [PLG-P0b-27] |
| 整数・bool 格納元の実値 (0x01・0x13・0x18・0x26・0x41・0x45・0x46・0x54・0x64・0x65 と call 先 `0x11ffde0`・`0x9636a0`・`0xe4e970`・`0xed6780`・`0x11d06e0`、`0x86c900`・`0x75b3d0` の戻り値の意味論) | 受入 1 の値・受入 3 の表 | [PLG-P0b-28] |
| callee 0 代替の影響: 0x40fe90 = 1 で経路が変わる 11 ID と 202 件の構成変化 (0x17 out・0x0a in) は実測済み (§3.4)。0x40fe90 以外の 81 callee は未測定 | 受入 2 の 202 件・未収載 ID の応答 0 | [PLG-P0b-28] |
| 未実行格納のうち分岐条件が未解析の 24 件 (§3.4) | 受入 1・3 | [PLG-P0b-28] |
| Phase B の OOB (本 run 変更前後で同一) | Phase B の PASS | #2911 (既存) |
| stage-2 smoke `fw_smoke_check` の `init_reach=16` | Phase A の判定 (dispatch=38 は PASS) | #2510 (既存) |
