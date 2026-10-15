# REPORT 付録 (#3094 KH-42): Delay の 128bit ローカルを型付きレーンにする (部分)

`REPORT_APPENDIX_3075.md` と同じく、`REPORT_APPENDIX.md` の 250 行上限のため分割した付録。正本は本付録の §10-7t。

#### 10-7t. #3094 (KH-42) run: auStack_118/128/138 を V128L に型化 (部分・emcc は未通過)
- 結論: `ghidra_to_c.py --fix lanes` で Delay の 128bit ローカル `auStack_118`・`auStack_128`・`auStack_138` (各 16 バイト) を、参照文脈で型を決めた `V128L` にした。emcc 件数は **577 → 556 (-21)**。`member reference base type` は **138 → 117** (`undefined1[16]` 32 → 11)。残りは子 [KH-64] (`undefined1[64]` 106 件) と [KH-65] (`aauStack_f8` 11 件)。Gain/Haas/Gate は **1000/1000 bit-exact** (生成 C は旧版と不変)。
- 測定 commit (コードを変えた最後の commit): `4c0c94150`。`git diff 4c0c94150 HEAD -- tools/targets/kilohearts/ghidra_route` の出力: 0 行 (本節を含む commit 時点)。
- 環境: 素材 `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B)・`toolchain-emsdk` (`[EMSDK]`・emcc 6.0.12)・[GHIDRA] 12.1.4 (repo 外に展開・zip sha256 `ddac49f9…d2db` 一致)・JDK 21 (temurin)。n=1。

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

##### Gain/Haas/Gate の回帰 (変更後の変換器・1000 trial・seed 7)
- 方法: DecompEach で gain 1・haas 5・gate 3 + also 2 の 10 関数を decompile (10/10 OK)。`ghidra_to_c.py <name> --fix bitcast,intload,stackpair,assoc,concat` (旧 = origin/main) と、`+lanes` (新) で C を出し比較。`build_cmp.sh` と同じ emcc フラグで wasm を作り、`native_ref <CORE> <name> 1000 7` と `snapins/harness/compare.mjs` で突合した。

| snapin | C 本体 (旧 = 新) | 突合 (1000 trial) | calls | wasm |
|---|---|---|---|---|
| gain | 122 行・一致 | 1000/1000 bit-exact | 4999/4999 | 15,161 B |
| haas | 301 行・一致 | 1000/1000 bit-exact | 5500/5500 | 16,878 B |
| gate | 429 行・一致 | 1000/1000 bit-exact | 4999/4999 | 17,367 B |

- 注: C の一致はヘッダ行 2 行目 (fix 一覧の文字列に `lanes` が増えるため) を除いて比較した。wasm サイズは §10-7n・§10-7q ⑤ と同じ。

##### 件数の差 (601 → 577) の注記
- §10-7p-2 / §10-7q の 601 は測定 commit `7d1d0e2e` の変換器。その後 origin/main の `ghidra_to_c.py` は rcpps/rsqrtps の 2 引数 helper を入れている (`git diff 7d1d0e2e origin/main -- ghidra_route/ghidra_to_c.py`)。本 run の main (`9e6ae331`) は 577。24 件の内訳は分解していない (推定: SIMD 系の解消)。
- lift 順と昇順のどちらで decompile しても、`lanes` 付きの件数は 556 (順序の影響なし)。

##### 未解決 (起票先付き)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| `undefined1 auVar7..33 [64]` (ZMM 系 12 ローカル)・`_8_56_`・`_16_48_` などの部分レーン代入 (配列どうしの代入) | member reference 106 件 | [KH-64] 子 issue |
| `aauStack_f8[11][16]` の混在型 (`_0_4_` を float 読み・int 書き、`_4_12_` と `undefined1[12]` の代入) | member reference 11 件 | [KH-65] 子 issue |
| `SUB84`・`SUB168`・`ZEXT416` 等の疑似関数 | census SIMD 46 件 | #3095 [KH-43] (既存) |
| Delay の native 突合 (1000 trial) | Delay は emcc 未通過のため未検証 | #3073 [KH-41] (既存) |

- 再現 (`<gr>` = repo 外の作業先・`<C>` = `HeartCore.core_64`・lift = `snapins.json` の delay.lift 141 件):
  ```
  analyzeHeadless <proj> kh -import <C> -noanalysis -scriptPath tools/targets/kilohearts/scripts/ghidra -postScript DecompEach.java <gr>/delay <lift 10進...> -deleteProject
  python3 tools/targets/kilohearts/ghidra_route/ghidra_to_c.py delay <gr>/cdelay <gr>/delay <C> --fix bitcast,intload,stackpair,assoc,concat,lanes
  emcc -c -ferror-limit=0 -I tools/targets/kilohearts/ghidra_route <gr>/cdelay/delay.c -o <gr>/cdelay/delay.o 2> <gr>/cdelay/emcc.log
  python3 tools/targets/kilohearts/ghidra_route/emcc_census.py <gr>/cdelay/emcc.log
  ```
