# REPORT 付録 (#3094 KH-42): Delay の 128bit ローカルを型付きレーンにする (部分)

`REPORT_APPENDIX.md` の 250 行上限のため分割した付録。正本は本付録の §10-7u (§10-7t は `REPORT_APPENDIX_3096.md` が使用中のため改番)。

#### 10-7u. #3094 (KH-42) run: auStack_118/128/138 を V128L に型化 (部分)
- 結論: `ghidra_to_c.py --fix lanes` で Delay の 128bit ローカル `auStack_118`・`auStack_128`・`auStack_138` (各 16 バイト) を、参照文脈で型を決めた `V128L` にした。emcc error 行は **統合後 (main `251d55a1b` 556 → PR head `17626eb42` 535, -21)**。旧 base `9e6ae331` 基準の 577 → 556 (-21) は履歴として残す。`member reference base type` は統合後 **138 → 117** (`undefined1[16]` 32 → 11。`[64]` 106 は不変)。残りは子 [KH-67] (#3808・`undefined1[64]` 106 件) と [KH-68] (#3809・`aauStack_f8` 11 件)。Gain/Haas/Gate は統合後 head で **1000/1000 bit-exact**。生成 C と emcc `.o` は main と一致。
- 測定 commit (コードを変えた最後の commit): `17626eb42`。`git diff 17626eb42 HEAD -- tools/targets/kilohearts/ghidra_route` の出力は 0 行 (本節を含む commit 時点)。
- 統合の経緯: main を 2 回取り込んだ (`40d3a788d` を `9c04abfa0`、`45182bf1b` を `c4bf5880a`。どちらも競合なし)。`ghidra_route` に入った差分は次の 1 行だけ (#3096 KH-44 の変更。本 PR の変更ではない。`git diff 40d3a788d 45182bf1b -- tools/targets/kilohearts/ghidra_route` は 0 行):
  ```diff
  -typedef void code;
  +typedef longlong (*code)();
  ```
- 環境 (round 3 fix run・n=1・GitHub runner 4 vCPU・RAM 15GB): 素材 `plugins-kilohearts` (`$ARTIFACTS_DIR` の実在を `ls` で確認) → `Kilohearts Offline Installer.zip` (3,833,108,300 B) → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。[GHIDRA] 12.1.4 は公式 release を取得し zip sha256 `ddac49f9…d2db` を一致確認。JDK 21 (temurin)。emcc は [EMSDK] (runner 同梱・6.0.12)。素材 `toolchain-emsdk` は展開していない。作業先はすべて repo 外。

| 項目 | 変更前 (origin/main `9e6ae331` の変換器) | 変更後 (`4c0c94150`) |
|---|---|---|
| decompile (lift 141) | 141/141 OK | 141/141 OK |
| C 行数 (delay) | 7,248 | 7,258 (helper 10 行を追加) |
| emcc error 行 (`-ferror-limit=0`) | 577 | 556 |
| `member reference base type` | 138 (`undefined1[16]` 32・`[64]` 106) | 117 (`[16]` 11・`[64]` 106) |
| census「128bit レーン型」 | 191 | 170 |
| census 他の分類 | 未関数化 5・引数 108・SIMD 46・code 21・未定義 17・型不一致 187・その他 2 | 同じ (変化なし) |

- 規則 (`lanes`): 対象は `undefined1 auStack_(118|128|138) [16];` の 3 宣言だけ (Delay の 1 関数内)。型は全参照 (16 箇所) を見て決めた。
  - `_0_8_`・`_8_8_` は `double` (`auStack_118._0_8_ = dVar29` 等の代入と `(double)auStack_118._0_8_` 等の参照)。
  - `_8_4_`・`_12_4_` は `uint32` (`SUB84(dVar29,0)`・`(int)((ulonglong)dVar29 >> 0x20)` の書込みだけ)。
- 理由: 既存の `V128` は `_0_4_`・`_8_4_`・`_12_4_` を `float` で持つ。`uint32` 値を float lane へ代入すると C は数値変換 (ビットは変わる) になり、emcc は通るのに結果が黙って狂う。`V128L` は lane 型を参照と一致させ、代入で数値変換を起こさない。
- 残件: `auStack_118._8_4_ = SUB84(dVar29,0);` の `SUB84` は未宣言の疑似関数 (census の SIMD・疑似関数の分類。#3095 の範囲)。本 run では触らない。
- 出力への影響: `lanes` を付けない限り出力は変わらない。`lanes` 付きでも `undefined1 auStack_118/128/138` を含まない snapin (Gain/Haas/Gate) は差分 0 (後述)。
- 適用範囲: `lanes` は変数名 (`auStack_118/128/138`) で一致させるため、その名前の変数を持つ全関数に効く。現状の使用先は Delay だけで、Delay 以外の snapin では付けない。参照型が違う同名変数に付けると、C は整数と浮動小数の暗黙変換を通すため emcc では検出されずに黙って型が変わる。

##### Gain/Haas/Gate の回帰 (旧 base・round 1 run の値。統合後 head の値は下の「統合後の再測定」)
- 方法: DecompEach で gain 1・haas 5・gate 3 + also 2 の 10 関数を decompile (10/10 OK)。`ghidra_to_c.py <name> --fix bitcast,intload,stackpair,assoc,concat` (旧 = origin/main) と、`+lanes` (新) で C を出し比較。`build_cmp.sh` と同じ emcc フラグで wasm を作り、`native_ref <CORE> <name> 1000 7` と `snapins/harness/compare.mjs` で突合した。

| snapin | C 本体 (旧 = 新) | 突合 (1000 trial) | calls | wasm |
|---|---|---|---|---|
| gain | 122 行・一致 | 1000/1000 bit-exact | 4999/4999 | 15,161 B |
| haas | 301 行・一致 | 1000/1000 bit-exact | 5500/5500 | 16,878 B |
| gate | 429 行・一致 | 1000/1000 bit-exact | 4999/4999 | 17,367 B |

- 注: C の一致はヘッダ行 2 行目 (fix 一覧の文字列に `lanes` が増えるため) を除いて比較した。wasm サイズは §10-7n・§10-7q ⑤ と同じ。

##### 件数の差 (601 → 577) の注記
- §10-7p-2 / §10-7q の 601 は測定 commit `7d1d0e2e` の変換器。その後 origin/main の `ghidra_to_c.py` は rcpps/rsqrtps の 2 引数 helper を入れている (`git diff 7d1d0e2e origin/main -- ghidra_route/ghidra_to_c.py`)。本 run の main (`9e6ae331`) は 577。24 件の内訳は分解していない (推定: SIMD 系の解消)。
- 統合後の件数 (535) の lift 順・昇順への依存は未確認。旧版の「順序の影響なし」の記載は撤回した。

##### 統合後の再測定 (round 3 fix run・実測)
- 対象: 変更前 = origin/main `251d55a1b` の変換器 (lanes なし)、変更後 = PR head `17626eb42` (lanes)。decompile の入力 (`scripts/ghidra`・`snapins`) は両 commit で同一。
- delay: lift 142 キー (ユニーク値 141) を一括 decompile (analyzeHeadless wall 29.3 s)。C 生成と emcc `-c -ferror-limit=0` の wall は各 15.7 s 〜 15.9 s。

| 項目 | main `251d55a1b` (lanes なし) | PR head `17626eb42` (lanes) |
|---|---|---|
| decompile (delay) | 141/141 OK | 141/141 OK |
| C 行数 (delay.c) | 7,248 | 7,258 |
| emcc error 行 (`-c -ferror-limit=0`) | **556** | **535 (-21)** |
| `member reference base type` | 138 (`undefined1[16]` 32・`[64]` 106) | 117 (`[16]` 11・`[64]` 106) |
| census「128bit レーン型」 | 191 | 170 |
| census 他の分類 | 未関数化 5・引数 108・SIMD 46・未定義 17・型不一致 187・その他 2 | 同じ (変化なし) |

- gain / haas / gate: 10 関数を一括 decompile (10/10 OK)。両 commit とも fix は `bitcast,intload,stackpair,assoc,concat` (lanes なし) で揃えて C を出した。PR head の wasm は build_cmp と同じリンクフラグで作り、1000 trial・seed 7 で突合した。

| snapin | C 行 | main と C の差分行 | emcc `-c` error | `.o` (main と PR) | 突合 (PR head・1000 trial) | calls | wasm |
|---|---|---|---|---|---|---|---|
| gain | 122 | 0 | 0 | byte 一致 (1,435 B) | 1000/1000 bit-exact | 4999/4999 | 15,161 B |
| haas | 301 | 0 | 0 | byte 一致 (3,217 B) | 1000/1000 bit-exact | 5500/5500 | 16,878 B |
| gate | 429 | 0 | 0 | byte 一致 (3,756 B) | 1000/1000 bit-exact | 4999/4999 | 17,367 B |

- `.o` の比較は `-w -O1` と `build_cmp.sh` の 3 つの `-Wno-error=...` を付けて `emcc -c` した。`.o` が同一なので、main と PR の wasm も同一になる。
- 注記: `origin/main` は本測定の後 `58ed035cf` まで進み、`tools/targets/kilohearts/{ghidra_route,scripts,snapins}` の 3 ファイルが変わっている。本 PR の数値は `45182bf1b` を取り込んだ HEAD (`17626eb42`) の測定。main をさらに取り込む場合は、その差分で再測定する (`docs/WORKFLOW.md` §6)。

##### 未解決 (起票先付き)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| `undefined1 auVar7..33 [64]` (ZMM 系 12 ローカル)・`_8_56_`・`_16_48_` などの部分レーン代入 (配列どうしの代入) | member reference 106 件 | [KH-67] (#3808) |
| `aauStack_f8[11][16]` の混在型 | member reference 11 件 | 解消済み (§10-7v・#3809) |
| `SUB84`・`SUB168`・`ZEXT416` 等の疑似関数 | census SIMD 46 件 | #3095 [KH-43] (既存) |
| Delay の native 突合 (1000 trial) | Delay は emcc 通過のみで、native 突合は未検証 | #3073 [KH-41] (既存) |
| `origin/main` (`58ed035cf`) の `ghidra_route` 変更の取り込みと再測定 | 取り込み後の件数は未確定 | 本 PR (main を取り込むときに同じ手順で再測定) |

- 再現 (`<gr>` = repo 外の作業先・`<C>` = `HeartCore.core_64`・lift = `snapins.json` の delay.lift のユニーク値 141 件):
  ```
  analyzeHeadless <proj> kh -import <C> -noanalysis -scriptPath tools/targets/kilohearts/scripts/ghidra -postScript DecompEach.java <gr>/delay <lift の 0x 付き値 141 件> -deleteProject
  python3 tools/targets/kilohearts/ghidra_route/ghidra_to_c.py delay <gr>/cdelay <gr>/delay <C> --fix bitcast,intload,stackpair,assoc,concat,lanes
  emcc -c -ferror-limit=0 -I tools/targets/kilohearts/ghidra_route <gr>/cdelay/delay.c -o <gr>/cdelay/delay.o 2> <gr>/cdelay/emcc.log
  python3 tools/targets/kilohearts/ghidra_route/emcc_census.py <gr>/cdelay/emcc.log
  ```

#### 10-7v. #3809 (KH-68) run: aauStack_f8[11][16] の混在型レーンを型付けする (完了)
- 結論: Delay の `aauStack_f8[11][16]` (128bit 一時領域の 2 次元配列) の参照 11 件 (`member reference base type 'undefined1[16]'`) を、`ghidra_to_c.py --fix lanes` の規則で解消した。emcc `member reference base type 'undefined1[16]'` は **11 → 0**。Gain/Haas/Gate は生成 C・`.o`・1000 trial の突合が旧版と一致した。
- 測定 commit (コードを変えた最後の commit): `af67b870d` (main `68d5cb3c4` を取り込んだ merge)。取り込み差分は `gtype` 規則 (#3801・`patches.py` の GTYPE) で、`gtype` を付けない限り本 PR の生成 C は変わらない (下の再測定で確認)。
- 環境 (n=1・GitHub runner 4 vCPU・RAM 15GB): 素材 `plugins-kilohearts` (`Kilohearts Offline Installer.zip` 3,833,108,300 B → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B)。[GHIDRA] 12.1.4 は公式 zip を取得し sha256 `ddac49f9…d2db` を一致確認。JDK 21 (temurin-21.0.12)。[EMSDK] 6.0.12。作業先はすべて repo 外 (`$RUNNER_TEMP`)。
- decompile: Delay 閉包 139 関数 → **139/139 OK**。gain・haas・gate (それぞれの閉包) → **9/9 OK** (gain 1・haas 5・gate 3。`work/ghidra/out` へ集約)。

##### aauStack_f8 の参照 (全 11 箇所・すべて `aauStack_f8[0]`)
| 行 (変換後 C) | 元の参照 | 型の決め方 | 変換規則 |
|---|---|---|---|
| 1175 | `aauStack_f8[0]._4_12_ = auStack_144` | `auStack_144` は `undefined1[12]` の 12 バイト。B12 と型が合わない | `memcpy(aauStack_f8[0]._4_12_, auStack_144, 12)` (バイト列の代入。値は変わらない) |
| 1176 | `aauStack_f8[0]._0_4_ = iStack_148` | int 値を書く | レーンを `uint32_t` にする (int → uint32 は同じビット幅の整数変換) |
| 1185 | `aauStack_f8[0]._4_4_ = *(undefined4 *)(...)` | int 値を書く | `uint32_t` レーン |
| 1186 | `aauStack_f8[0]._0_4_ = *(undefined4 *)(...)` | int 値を書く | `uint32_t` レーン |
| 1187 | `aauStack_f8[0]._8_8_ = 0` | 0 を書く | `uint64_t` レーン |
| 1190 | `fVar26 = aauStack_f8[0]._0_4_` | float として読む | `u2f(...)` (ビット再解釈) |
| 1191 | `fVar31 = aauStack_f8[0]._4_4_` | float として読む | `u2f(...)` (ビット再解釈) |
| 1269 | `uVar36 = aauStack_f8[0]._8_4_ ^ _UNK_...` | 整数として読む | そのまま (`uint32_t` レーン) |
| 1270 | `uVar37 = aauStack_f8[0]._12_4_ ^ _UNK_...` | 整数として読む | そのまま (`uint32_t` レーン) |
| 1274 | `auVar6._8_4_ = uVar36 & aauStack_f8[0]._8_4_` | 整数の AND を float レーンへ代入 | `u2f(...)` (ビット再解釈。数値変換にしない) |
| 1275 | `auVar6._12_4_ = uVar37 & aauStack_f8[0]._12_4_` | 同上 | `u2f(...)` |

- 型: `V128A` (新規。`lanes` 指定時だけ出力。`_0_4_`・`_4_4_`・`_8_4_`・`_12_4_` = `uint32_t`、`_4_12_` = `uint8_t[12]`、`_8_8_` = `uint64_t`)。
- 規則 (`lanes`): 対象は `undefined1 aauStack_f8 [11] [16];` の宣言 (Delay の 1 関数)。`V128A aauStack_f8 [11];` に書換え、上の 4 種 (memcpy・u2f・u2f・u2f) を正規表現で当てる。`lanes` を付けない限り出力は変わらない。
- 残る数値変換: なし。`uint ^ float` (1258・1267 行相当) と `FUN_180289ea0` の引数型 (1174 行) は `aauStack_f8` と無関係の既存の型不一致で、旧版にも同じ行が残る (エラー種別の差分は `undefined1[16]` の 11 件だけ)。
- 影響範囲: `aauStack_f8` の宣言を持つ関数は Delay の `FUN_1802ed7f0` だけ (`grep` で確認)。`lanes` を付けた Gain/Haas/Gate の生成 C は旧版と本体が一致 (下表)。

##### 測定 (測定 commit `af67b870d`・実測)
| 項目 | origin/main `68d5cb3c4` (lanes なし) | 測定 commit `af67b870d` (lanes) |
|---|---|---|
| decompile (delay 閉包) | 139/139 OK | 139/139 OK |
| C 行数 (delay.c) | 7,281 | 7,290 (+9: V128A 定義と変換行) |
| emcc error 行 (`-c -ferror-limit=0`) | 420 | **409 (-11)** |
| `member reference base type 'undefined1[16]'` | 11 | **0** |
| `member reference base type 'undefined1[64]'` | 106 | 106 (不変・#3808 の範囲) |
| エラー種別の差分 | — | `undefined1[16]` の 11 件だけ消える (他は同じ) |
| emcc wall (Delay `-c`・1 回実測) | 15.5 s | 15.7 s |

- Gain/Haas/Gate (`lanes` 付き・新旧とも `--fix bitcast,intload,stackpair,assoc,concat,lanes`):
  - 生成 C: 新旧で本体一致 (ヘッダ 1 行目の fix 一覧を除く)。gain 122 行・haas 301 行・gate 429 行。
  - `.o`: HEAD と origin/main の生成 C を同じ emcc フラグ (`-w -O1 -Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=incompatible-pointer-types-discards-qualifiers`) で `-c` した結果が **byte 一致** (gain 1,435 B・haas 3,217 B・gate 3,756 B)。
  - 突合 (`build_cmp.sh <name> 1000 7`・HEAD): gain **1000/1000** (calls 4999/4999・wasm 15,161 B)、haas **1000/1000** (calls 5500/5500・wasm 16,878 B)、gate **1000/1000** (calls 4999/4999・wasm 17,367 B)。wasm サイズは §10-7u と一致。

- 再現 (`<gr>` = repo 外の作業先・`<C>` = `HeartCore.core_64`):
  ```
  analyzeHeadless <proj> kh -import <C> -noanalysis -scriptPath tools/targets/kilohearts/scripts/ghidra -postScript DecompEach.java <gr>/delay <delay 閉包 139 件の VA> -deleteProject
  python3 tools/targets/kilohearts/ghidra_route/ghidra_to_c.py delay <gr>/cdelay <gr>/delay <C> --fix bitcast,intload,stackpair,assoc,concat,lanes
  emcc -c -ferror-limit=0 -I tools/targets/kilohearts/ghidra_route <gr>/cdelay/delay.c -o <gr>/cdelay/delay.o 2> <gr>/cdelay/emcc.log
  ```
