# REPORT 付録 (#3835 KH-70): Delay の残件 `LAB_180fd2aab`・`PTR__guard_dispatch_icall_1813a1d38` の機械語での確定

#3802 (KH-66) の付録 `REPORT_APPENDIX_3802.md` §⑦ の子 issue の結果。前節の census 基準は同 §⑦ の 534 件 (測定 commit `6323671e7`)。本付録の件数は main (`01e296f2f`) の converter で同じ入力を流した値に揃えて比較する。

#### 3835-①. 結論

- Delay の emcc 残件から `LAB_180fd2aab`・`PTR__guard_dispatch_icall_1813a1d38` の 2 件を消した。census は main 341 → HEAD 339 件 (差 −2・`LAB_`・`PTR__` 残件 0)。
- 2 件とも機械語で確定し、`ghidra_to_c.py` の `DELAY_RULES` (件数 assert 付き) で書き換える。他の Delay の残件 339 件は本 issue の範囲外 (下の ⑤)。
- Gain/Haas/Gate の生成 C は main と **byte 一致** (3 本)。HEAD の emcc と突合 (`compare.mjs`・1000 trial・seed 7) は **3 本とも 1000/1000 bit-exact** (calls: Gain 4999/4999・Haas 5500/5500・Gate 4999/4999)。

#### 3835-②. 環境 (repo 外。`work/` は使わない)

- 素材 `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。取り出し先は repo 外の作業ディレクトリ。
- [GHIDRA] 12.1.4: 公式 release の asset `ghidra_12.1.4_PUBLIC_20260921.zip` (569,649,598 B・sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)。repo 外に展開。
- [EMSDK] emcc: `toolchain-emsdk` の emcc を使用。[JDK21] `temurin-21-jdk-amd64`。
- decompile: Delay 閉包 139 関数 → **139/139 OK** (`analyzeHeadless` wall 37.3 s、n=1)。Gain/Haas/Gate の 10 関数 → **10/10 OK**。

#### 3835-③. 機械語による確定 (capstone・`HeartCore.core_64` の .text)

**(a) `LAB_180fd2aab` (`FUN_180fd2a60` 内)**
- 機械語: `call 0x180fb5c6c` (`mov r8d,1; mov edx,0x40000015; lea ecx,[r8+2]`) の直後の番地が `0x180fd2aab`。`je 0x180fd2aab` (0x180fd2a7f) の飛び先でもある。
- Ghidra は同関数の `*(undefined8 *)(puVar4 + -8) = 0x180fd2ab5;` (既存行) と同じ形の、戻り番地の 8 byte 書込みとして `&LAB_180fd2aab` を出す。
- 規則: `*(undefined1 **)(puVar4 + -8) = &LAB_180fd2aab;` を `*(undefined8 *)(puVar4 + -8) = 0x180fd2aab;` に書換える (`DELAY_RULES` の 1 行目)。型の違いは `undefined1 *` と `undefined8` の 8 byte 書込みの違いだけで、書込む値は同じ。
- 戻り先の確定: `FUN_180fb5c6c` が戻るときは `0x180fd2aab` へ (`mov ecx,3; call 0x180fd0b50`)。継続点は fall-through と同じ。fail-fast stub にはしない (通常経路で到達する)。

**(b) `PTR__guard_dispatch_icall_1813a1d38` (`FUN_180fa8534` 内)**
- 機械語 (0x180fa8534〜0x180fa856a): `rbx=rdx` (元の `param_2`)・`rsi=rcx` (元の `param_1`)。`rcx = [rsi] - 8` (this)・`rax = [this]` (vtable)・`rbx = [vtable+0x30]`・`call [vtable+0x40]` (rcx = this・rdx = 呼出し時点の `rdx` = 元の `param_2`)。
- `PTR__guard_dispatch_icall_1813a1d38` (0x1813a1d38) の値は `0x181383e30` (`jmp rax` の thunk)。つまり呼出先は `rax` (= `vtable[0x40]`)。
- 戻り値は使わない (直後の `call` の戻りは `eax=0` で上書き)。
- 規則: `param_2 = *(byte **)(*(longlong *)(*param_1 + -8) + 0x30);` と直後の `(*(code *)PTR__guard_dispatch_icall_1813a1d38)();` の 2 行を、this・vtable を分けて書いた 1 ブロックに置換える (`DELAY_RULES` の 2 行目)。
- 注意: C 上の `(*(code *)PTR__…)()` は引数を取らないため、rcx・rdx の受け渡しを書かないと呼出先の意味が落ちる。そのため `(void (*)(longlong, byte *))` のキャストで rcx (this)・rdx (元の `param_2`) を渡す。

#### 3835-④. 測定 (HEAD で再測定)

| 項目 | main `01e296f2f` | HEAD (本 PR) | 備考 |
|---|---|---|---|
| Delay census (emcc `-ferror-limit=0`・全 fix) | 341 | **339** | 差 −2 = `LAB_`・`PTR__` |
| Delay の `LAB_`・`PTR__` 残件 | 2 | **0** | |
| Gain / Haas / Gate の生成 C | — | main と byte 一致 (cmp・3 本) | 出力不変 |
| Gain / Haas / Gate の wasm bytes | — | 15,161 / 16,878 / 17,367 | REPORT_APPENDIX_3802 §⑥ と一致 |
| 突合 (`compare.mjs`・1000 trial・seed 7) | — | Gain **1000/1000** (4999/4999)・Haas **1000/1000** (5500/5500)・Gate **1000/1000** (4999/4999) | |

- Delay の突合 (1000 trial) は未実施。emcc が通らない (残り 339 件) ため。#3073 [KH-41] が正本。

#### 3835-⑤. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Delay の emcc 残件 339 件 (レーン型 134・引数数不一致 86・演算・代入の型不一致 118・未関数化 callee 1 ほか) | Delay の wasm 化が未完 | レーン型 = #3808 [KH-67] (106 件)・#3953 [KH-78] (残り)。引数数不一致 = #3844 [KH-79] (33 件)・#3847 [KH-73] (53 件)。型の不一致 = #3837 [KH-72] (87 件)・#4672 [KH-107] (14 件)・#4671 [KH-106] (9 件)・#4685 [KH-108] (残り)。未関数化 callee = #4014 [KH-85]。#3094・#3095・#3800・#3801 は CLOSED のため使わない。各 issue の件数は本文の値 (HEAD が異なる) で、census での照合は #4685 等の子の作業で行う |
| `(ulonglong)dVarN` の double ビット再解釈 | 数値が誤る可能性 (emcc は通る) | #3836 [KH-71] (既存) |
| 既存 shim (`dint`・`fint`) を使うか | 現状は fail-fast stub (abort) | PM 判断 (`REPORT_APPENDIX_3802.md` §⑦) |
| Stereo・Resonator の生成 C | 規則は `name == 'delay'` の時だけ適用 (コードで確認) ため出力は不変。ただし両者の emcc 結果は未測定 | Stereo #3109 [KH-46]・Resonator #3764 [KH-63] (既存) |
