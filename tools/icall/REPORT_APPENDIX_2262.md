# 付録: icall #2262 (ICALL-69) — site 0x1810553e6 の間接 call target 0xb77e88c8000 の由来

> 親: #2079 (ICALL-56)。前付録: `REPORT_APPENDIX_2079.md`・`REPORT_APPENDIX_2120.md`・`REPORT_APPENDIX_2081.md`。
> 本 run は受入条件 1 (由来の特定) と受入条件 3 (`fa_sweep.sh 8 60` の再測定) を達成。受入条件 2 (表への包含判定) は子 issue へ移管 (§5)。

## 1. 結論

- **由来の特定**: 値 `0xb77e88c8000` は、`0x1810553d0` の decode 関数 `0x181055400` が読む slot `0x1813068f8` (値 0) を
  復号した結果 `ror(cookie, 50)` の下位 44 bit と一致する。`cookie` は `0x18125eaa8` (8 byte)。
  - native は 64bit で `ror(0x2b992ddfa232, 50) = 0xae64b77e88c8000` を得る (下位 44 bit が `0xb77e88c8000`)。
  - lifted IR は cookie を **`load i32`** (`load i32, i32* @global_var_18125eaa8`) で読むため、上位 32 bit が落ち、wasm 側は `0xb77e88c8000` になる。
- **機構**: `0x1810553e6` は `call [0x1810c4828]` で、`.rdata` の slot は `0x1810806a0` (CFG thunk `jmp rax`)。thunk は rax (= decode 結果) へ飛ぶ。
  decode 結果が 0 なら call を skip する (`test rax,rax; je`) が、lifted では cookie 幅の不一致で `enc(NULL)=cookie` の初期化後も非 0 になる (§3)。
- **解釈の修正**: #2079 は「encoded 関数ポインタを復号せずに使っている」と疑ったが、実際は**復号は行われている**。
  誤りは復号値そのものにあり、slot が 0 のままの経路 (未初期化) と cookie の load 幅 (lift 欠陥) の 2 つが重なっている。
- **#2120 との関係**: #2120 が読んだ slot `0x1813068f8` (decode `0x18105541a`) は、本 site の target 値の源そのもの。

## 2. 測定 (SlateCore.core_64、closure 131 関数の artifact `work-icall`)

測定 commit: `a1d55799` (main。本 run のコード変更なし)。

| 項目 | 値 |
|---|---|
| `slot_trace.sh` (SLOT_ENC_INIT=1) | funcs 131 / rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8 / zero-fill VA 10 / 既知 12 hit 3・miss 9 (#2120・#2197 と一致) |
| `slot_trace` 単独 `1810553d0` (SLOT_ENC_INIT 無し) | ACC `1813068f8 18105541a 1` / fatal `sig=11 rip=0x1810806a0 addr=(nil)` (native は thunk の `jmp rax` で SIGSEGV) |
| `slot_trace` 単独 `1810553d0` (SLOT_ENC_INIT=1) | ACC `1813068f8 18105541a 1` / rc=0 (enc(NULL)=cookie 後は call を skip) |
| `fa_route_build.sh` (FA_ENC_INIT 未設定 = OFF) | 成功 (`fa_route.wasm`) |
| `fa_route_build.sh` (FA_ENC_INIT=1 = ON) | 成功 |
| wasm `1810553d0` (OFF) | `FAIL-FAST: unresolved indirect target 0x310806a0 at site VA 0x310553e6` (abort) |
| wasm `1810553d0` (ON) | 同上 (abort) |
| `fa_sweep.sh 8 60` (OFF, 所要 1m10.7s real, load 0.46 開始時) | **funcs 131 / bit一致 47 / native crash・timeout 66 / wasm のみ err 9 / 値の不一致 9** |

- `0x1810553d0` の wasm abort は OFF/ON とも維持。この artifact の closure (131 関数) には `0x1810806a0` が無く、
  `icall_cfg_n = 0` のため thunk が解けず、target は `0x1810806a0` のまま `lookup` に失敗する (`0x310806a0` 表示)。
  #2079 が記録した `0xb77e88c8000` は、thunk を登録した 152 関数 closure (`fa_ranges_2079.txt` 由来) で得られる値である。
- 本 run の artifact は 131 関数で、152 関数 closure の再生成は行っていない。`fa_sweep` の件数は 131 関数の値で、#2079 の 142 件 (152 closure) とは母集団が違う。

## 3. 機構の根拠 (数値)

```
native zero slot   ror(cookie64,50)            = 0xae64b77e88c8000
lifted zero slot   ror(sext32(cookie),50)      = 0x000b77e88c8000   (wasm FAIL-FAST 値と一致)
native enc(NULL)   ror(cookie64 ^ cookie64,50) = 0                   -> call skip
lifted enc(NULL)   ror(cookie64 ^ sext32,50)   = 0xae6400000000000   -> call taken (非 0)
```

- lifted の `function_181055400` (`after.0.restored.ll`) は cookie を `load i32, @global_var_18125eaa8` で読む。
  native の `181055400`〜`181055421` は `mov rbx,[0x18125eaa8]` (64bit) である。
- 幅が落ちる段は未特定 (RetDec 段か restore 段)。`REPORT_APPENDIX_2081.md` の decode 形式 (`mov r10,[cookie]`) とは整合しない。
- `fa_data.c` の ON 敷設 (`*(uint64_t*)0x313068f8u = *(uint64_t*)0x3125eaa8u`) は 64bit 複写で正しい。欠陥は decode 側の幅にある。

## 4. 再現

```
bash tools/ott/native/build.sh
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
tar --zstd -xf "$HOME/artifacts/work-icall.tar.zst"             # リポジトリ直下 (tools/icall/work/ を含む)
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh              # 約 12 秒
bash tools/icall/fa_route_build.sh                               # OFF
bash tools/icall/diff/fa_sweep.sh 8 60                           # 約 71 秒
```

- `work-icall.tar.zst` は repo 直下相対 (`tools/icall/work/...`) で格納されている。`-C tools/icall` で展開すると二重になるので注意。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| cookie の load 幅 (i32 → 64bit) の欠陥の段特定と修復。修復後に `0x1810553e6` が skip されるかの再測定 | 受入条件 (site 0x1810553e6 の wasm abort の解消) | #2280 (ICALL-70) |
| 0x1813068f8 が encoded 表 (T1/T2 の外・#2197) のどの表に属するかの判定 | 受入条件 (表への包含判定) | #2224 (ICALL-64)・#2226 (ICALL-66) |
| 152 関数 closure (`fa_ranges_2079.txt`) での `fa_sweep` 再測定 (本 run は 131 関数 artifact) | #2079 の 142 件との比較 | #2079 (ICALL-56) |

## 6. 測定コードの鮮度

```
$ git diff a1d55799 HEAD -- tools/icall tools/ott tools/targets/freshair
(測定後のコード変更は本付録のみ・0 行)
```
