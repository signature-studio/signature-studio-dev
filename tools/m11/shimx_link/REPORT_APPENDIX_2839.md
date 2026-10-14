# M11 × shimx: midiOutShortMsg の HMIDIOUT が IR で i64 と推定される根本 (SHX-T31 / #2839)

- 親: #1628 (SHX-T25)。残件の根因を特定し、修正方針を決める (受入 3 点)。
- 測定 commit: `97908347` (`tools/m11/shimx_link/hmo_rootcause.py` を最後に変更した commit)。HEAD は本 PR の head。
- 再現: `FL_WIN64_DIR=<fl-win64 の展開先> RETDEC_ROOT=<toolchain-retdec の retdec/> python3 tools/m11/shimx_link/hmo_rootcause.py --dll winmm.dll --name midiOutShortMsg` (実測 49.8 秒、rc 0)。対照: `--dll kernel32.dll --name CloseHandle` (rc 0)。
- 素材: `fl-win64` の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`、x64・ImageBase `0x400000`)。`toolchain-retdec` は RetDec v5.0 (commit `53e55b4b`)。
- 本件は静的解析 (機械語 + RetDec の該当関数 lift + 署名 DB)。全 lift の再生成 (boot_final3) と e2e は本 run で行っていない。

## 1. 結論

| 項目 | 結論 |
|---|---|
| 根因 | RetDec の署名 DB `share/retdec/support/generic/types/windows.json` で、`HMIDIOUT` の underlying 型が `unknown` (typedef 先が未定義)。この引数は IR で `i64` になる (実測。`unknown` が x86-64 のレジスタ幅に落ちる経路は観測から推定) |
| 機械語との整合 | 呼出し元は `mov rcx, qword ptr [rcx+0x7c]` で 8 バイトのハンドルを読む。x64 の HMIDIOUT は 8 バイトなので、IR の `i64` は x64 の実幅と一致する。lift の誤りではない |
| 不一致の本体 | x64 (8B) と wasm32 (4B) の target ABI の幅差。shimx は wasm32 規約で `HANDLE` = `ULONG_PTR` (4B) (`tools/shimx/src/shimx.h:63-64`、`midi_conv.c:13`) |
| 採る修正方針 | **(b) 正規化 pass を恒久策として残す** (link 時の `i64`→`i32`。実装は PR #2796 の `sx_handle_norm.py`、未 merge)。(a) IR 生成側の型変更は採らない (§4) |

## 2. 機械語 ↔ IR ↔ 署名 DB の突合 (実測・測定 commit `97908347`)

| 段 | 実測 |
|---|---|
| PE の import | `winmm.dll!midiOutShortMsg` の IAT = VA `0x1971cd0` |
| thunk | `jmp qword ptr [rip+0x130e89a]` (`0x663430`)。直接の `call [IAT]` は 0 件 |
| 呼出し元 | 1 件 (`0xba4a31`)。関数 `0xba4a20-0xba4a3b`: `cmp byte ptr [rcx+0x84],0` の後、`mov rcx, qword ptr [rcx+0x7c]` (8B 読み) → `call 0x663430` |
| RetDec の lift (該当関数 + thunk のみ) | `define i32 @function_663430(i64 %hmo, i32 %dwMsg)` → `call i32 @midiOutShortMsg(i64, i32)`。呼出し元は `load i64` (8B) を `i64` のまま渡す |
| IR の宣言 | `declare i32 @midiOutShortMsg(i64, i32)` (`REPORT.md` §10.3 の mismatch 1 と同じ組) |
| 署名 DB | `hmo`: `HMIDIOUT -> unknown` (type 14037)。`dwMsg`: `DWORD -> unsigned long` (type 4862) |
| shimx 定義 | `tools/shimx/src/midi_conv.c:163` `UINT midiOutShortMsg(HANDLE h, DWORD msg)`、HANDLE = 4B。IR の `i64` とぶつかる |

第 2 引数 `DWORD` は `i32` で一致している。食い違うのは第 1 引数の HMIDIOUT だけ。

## 3. 対照: HANDLE 系の型は pointer になる (同じ手順・測定 commit `97908347`)

| 段 | 実測 |
|---|---|
| import | `kernel32.dll!CloseHandle` の IAT = VA `0x1971290`。thunk 2 件、呼出し元 73 件 |
| RetDec の lift | `declare i1 @CloseHandle(i64*)`。引数は `i64*` (ポインタ) |
| 署名 DB | `hObject`: `HANDLE -> PVOID -> pointer` |

署名 DB が型を持つ (HANDLE 系) 場合は pointer になる。HMIDIOUT は `unknown` なので、pointer ではなく素の `i64` になる。
`windows.json` の typedef 先が `unknown` の型は全 435 件。マルチメディア系のハンドル (`HMIDI`・`HMIDIIN`・`HMIDIOUT`・`HMIDISTRM`・`HWAVEOUT`・`HWAVEIN`・`HDRVR`・`HACMDRIVER`) が含まれる。

## 4. 修正方針の判定 (受入 2)

| 案 | 内容 | 判定 | 理由 |
|---|---|---|---|
| (a1) 署名 DB を pointer に直す | HMIDIOUT を `PVOID` 系へ | 不採用 | x64 では pointer も 8B で、IR の幅は `i64` のまま。pointer になると値のハンドルを pointer として扱うため、幅の一致だけを作って意味を壊す (CloseHandle の `i64*` と同じ形になる) |
| (a2) lift 時に `i32` へ narrow | 署名 DB で HMIDIOUT を 4B 扱い | 不採用 | 機械語は 8B を読む。narrow すると x64 の値を lift 段で切り捨てた IR になり、lift の忠実性を落とす。`unknown` 型の全 435 件に波及する。署名 DB は外部 artifact (`toolchain-retdec`) で、repo の差分にならない |
| (b) 正規化 pass を恒久策 | link 時に `midiOutShortMsg` の `i64` 引数を `i32` へ trunc (`sx_handle_norm.py`、PR #2796) | **採用** | 幅変換は target (wasm32) の規約なので link 層が持つ。lift の IR は x64 に忠実なまま。実装は PR #2796 に既にある |

前提と残リスク: (b) の trunc が正しいのは、8B フィールドの上位 4B が 0 のときだけ。shimx の `midiOutOpen` は 4B の HANDLE を `LPHANDLE` に書く。上位 4B が 0 である確認は本 run で行っていない (§6)。

## 5. 検証 (HEAD で再現)

- 測定 commit `97908347` で実行 (HEAD も同じ script)。`python3 tools/m11/shimx_link/hmo_rootcause.py --dll winmm.dll --name midiOutShortMsg`: rc 0。出力 (抜粋):
  - `IAT winmm.dll!midiOutShortMsg = VA 0x1971cd0` / `thunk (jmp [IAT]) 1 件: 0x663430` / `呼出し元 1 件`
  - `declare i32 @midiOutShortMsg(i64, i32)`
  - `[db]   param hmo  type_id=14037  chain=HMIDIOUT -> unknown`
  - `[db]   param dwMsg  type_id=4862  chain=DWORD -> unsigned long`
- `python3 tools/m11/shimx_link/hmo_rootcause.py --dll kernel32.dll --name CloseHandle`: rc 0。`declare i1 @CloseHandle(i64*)`、`chain=HANDLE -> PVOID -> pointer`。
- 測定 commit から HEAD までのコード差分: `git diff 97908347 HEAD -- tools/m11/shimx_link/hmo_rootcause.py` の出力は **0 行** (測定 commit の後に変えたのは REPORT 系と DOC_MAP のみ)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (b) 前提の「8B フィールドの上位 4B が 0」を実行で確認していない | trunc が上位ビットを捨てる。ハンドルが 4B を超える値なら誤る | #2877 (SHX-T32) の HEAD 再測定で確認 (既存 issue に追記) |
| `sx_handle_norm.py` (b の実装) は未 merge | main の link は mismatch 1 のまま | PR #2796 (review 中) |
| 全 boot IR (boot_final3) の再生成と e2e は未実施 | 本件は 1 関数の lift と静的突合。全体への波及は §10.3 の測定 (mismatch 1) と整合するが、再測定はしていない | #2877 |
