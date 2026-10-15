# ildsp REPORT 付録: WaveformColouring_CreateInstance の x64c lift と native 差分 (#3216)

`REPORT.md` §7 の全文 (250 行上限のため分割移動)。手順・実測・未解決の正本はこのファイル。

## 7. WaveformColouring_CreateInstance の x64c lift と native 差分 — T-SH-52 (#3216・部分達成)

既知類型との関係: 該当なし (`docs/DEFECTS.md` D1a〜D23 に VEX 未対応・jump table 未到達の記述は無い。差分は CreateInstance と slot 0 の範囲で 0 件)。
測定 commit: `2cff3f50d` (origin/main `c2e5ba01c` の取り込み merge。コードを変えた最後の commit。以降の差分は `.md` のみ・§7-8)。検証起点: `bea685f7` (origin/main。取り込み前の PR 枝の起点)。

### 7-1 結論 (1 行)
closure の入口 70 関数は x64c で C に lift し wasm (138,754 B) にした (C 本体 60 + label 8 + IAT thunk 2)。CreateInstance → slot 0 の native 対 wasm は 64 case で全バイト一致。残りは slot 1–5 の host 前提 (native が null 参照で落ちる。§7-5) と、VEX 3 命令の未対応 (unsup 3 site)。

### 7-2 再現
```
FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<toolchain-emsdk 展開先>/emsdk/emsdk_env.sh bash tools/shared/lift/ildsp/lift_wc.sh [ok|neg-cmp|all]
FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/ildsp/probe_slots.sh   # slot 0–5 の native のみ (emcc 不要・§7-5)
```
- 入力: `extracted/block24360_PE.bin` (sha256 `f4b23b0f…`)。素材は `tar --zstd -xf fl-win64.tar.zst extracted/block24360_PE.bin` で取る。
- 段: `x64c.py` (root = CreateInstance `0x1ac470` と vtable `0x3e01b0` の slot 先 `0x1a9cf0`・`0x1a9f10`・`0x1a9e10`・`0x1a9de0`・`0x1aa0b0`・`0x1ac460`、`--closure 99`) → `wc_image.py` (DIR64 補正・IAT pseudo-VA) → `wc_cases.py` (case 0 = 元の `.data`、case 1–63 = 元の `.data` の数バイトを書き換えたもの) → emcc 6.0.12 `-O1` → `wc_native_ref.c` (gcc・ms_abi 直接実行) → `wc_run_wasm.mjs` (node) → `wc_diff_test.py`。
- vcall `0x1a9e2b` (`call [rax+0x18]` = slot 3 = `0x1a9de0`) は静的に束縛せず、x64c の `ott_dispatch` が実行時に vtable を読んで解決する。前提は instance の vptr が `0x3e01b0` (CreateInstance が `[rcx]` に置く)。
- runtime `fle_cpu.c` の既定 `imp_HeapAlloc` は host `malloc` を使い、native とポインタが一致しない。`lift_wc.sh` は `wc_glue.c` が定義する `imp_*` だけ `-D` で改名して除外し、決定的 bump heap の定義を使う。
- wasm の import は `wc_run_wasm.mjs` が全て throw する関数に置き換える (旧版は 0 を返して黙殺していた)。呼ばれれば trap として数え、差分は FAIL になる。実測の import 一覧 (`[run_wasm] imports:`): `wasi_snapshot_preview1.{fd_write, fd_read, proc_exit, clock_time_get, fd_close, fd_seek, fd_fdstat_get}`・`env._Unwind_RaiseException` (計 8)。3 回の実測で trap は 0 件 = どの import も呼ばれていない。
- native 側 (`wc_native_ref.c`): 落ちた case の後に残った SIGALRM を `ualarm(0,0)` で解除する (旧版は解除していなかった)。

### 7-3 実測 (測定 commit `2cff3f50d`・`lift_wc.sh ok` を 3 回・emcc は `[EMSDK]` の 6.0.12)
所要 = `lift_wc.sh ok` の起動から終了までの wall (source・x64c・emcc・native・wasm・差分を含む。小数 2 桁)。実ログ行:
```
[ildsp-wc] ok elapsed=2.71s load start=[0.06 0.28 0.18] end=[0.54 0.38 0.21]
[ildsp-wc] ok elapsed=2.19s load start=[0.50 0.37 0.21] end=[0.54 0.38 0.21]
[ildsp-wc] ok elapsed=2.27s load start=[0.49 0.37 0.21] end=[0.69 0.42 0.22]
```
(4 core。3 回とも rc=0・`wc diff ... PASS=64 FAIL=0`。同じ HEAD で `lift_wc.sh all` も `ALL OK`。前版 `a099ff25` の実測 (2.25 / 2.26 / 2.27 s) は merge 前の値)

| 項目 | 値 |
|---|---:|
| x64c の lift 関数 (C 本体) | 60 (`unlifted callees` 0・imports 18) |
| closure 入口 70 のうち C に現れる | 70 (60 は `f_` 関数、8 は呼出元の関数内 label、2 は IAT thunk `jmp [rip+IAT]` = `imp_` 呼出 `0x1b932c`・`0x1b9334`) |
| closure の命令数 (`ildsp_closure.py` と同じ 70 関数の線形走査) | 2,757 (`count_unlifted.py`) |
| x64c が C に出した命令数 (`/* addr: */` 注釈) | 2,656 |
| closure にあって C に無い命令 | 109 = int3 77 + nop 14 + 非 padding 18 (うち IAT thunk 2)。内訳は §7-4 |
| C にあって closure に無い命令 | 8 (`0x1aef40`–`0x1aef4f`。x64c が辿るが closure の定義は辿らない) |
| unsup (`ott_unsup`) | 3 site: `0x1ca277` vcvtss2sd・`0x1ca33f` vpmovsxdq・`0x1ca34c` vshufps (いずれも closure 内。CreateInstance の実行経路には無い) |
| wasm | 138,754 B (`emcc` 6.0.12) |
| 差分 `ok` (CreateInstance → slot 0) | cases 64 / PASS 64 / FAIL 0 / native 落ち除外 0 / wasm trap 0 |
| 差分の観測値 | 戻り値の合成値 `0x5d9b00001` (= 返り値 `0x30500000`·31 + slot 0 の返り値 1) が両側で一致。import 呼出 1 回 (HeapAlloc 0x228 B) |
| ネガティブコントロール `neg-cmp` (wasm 結果の heap 先頭 1 bit 反転) | FAIL 64/64 (`arena@+0x0`)・期待通り (`ALL OK`) |

### 7-4 closure と lift の差 (未 lift 109 命令の内訳・再現済み)
再現 (`lift_wc.sh ok` の後に実行):
```
python3 tools/shared/scripts/ildsp_closure.py "$FL_WIN64_DIR/extracted/block24360_PE.bin" --out tools/shared/work/lift/ildsp-wc/closure.json
python3 tools/shared/lift/ildsp/count_unlifted.py "$FL_WIN64_DIR/extracted/block24360_PE.bin" tools/shared/work/lift/ildsp-wc/closure.json tools/shared/work/lift/ildsp-wc/lift
```
実測出力: `functions=70 closure_insns=2757 lifted_in_C=2656 C_not_in_closure=8 missing=109`・`missing: int3=77 nop=14 nonpad=18 (IAT thunk=2)`。

| 区分 | 件数 | 番地 |
|---|---:|---|
| int3 (padding) | 77 | (関数の末尾) |
| nop (padding) | 14 | (関数の末尾) |
| IAT thunk `jmp [rip+IAT]` | 2 | `0x1b932c`・`0x1b9334` |
| 非 padding・直接分岐の先でない | 15 | `0x1ac9b8`・`0x1b8eb1`–`0x1b8ec8` (6)・`0x1bd4b0`・`0x1bd4b7`・`0x1be14e`・`0x1be156`・`0x1be158`・`0x1be160`・`0x1be162`・`0x1be167` |
| 非 padding・直接分岐の先 (分岐元 `0x1be156`・`0x1be160` も C に無い) | 1 | `0x1be16c` (`ret`) |

- 直接分岐の先でない 15 件は、直前が無条件 `jmp`・`ret` か、その直後の未 lift 命令で、closure 内の直接 call・jmp・jcc の先にならない。直接の制御流では到達せず、到達するなら間接 jump 経由 (未確定)。
- `0x1be16c` は未 lift の島 (`0x1be14e`–`0x1be167`) の中の `jae`・`jbe` の先。島の入口は直接分岐で届かないため、x64c の経路 (直接 call/jmp・認識した jump table) では届かない。
- 到達した場合の挙動: 直接 call で届けば x64c が必ず lift する。`call reg` 経由で未 lift の先に届けば `ott_unlifted` で止まる (fail-fast。silent ではない)。

### 7-4b 未 lift 非 padding 16 件の到達性 (T-SH-133 / #5072)
再現: `python3 tools/shared/lift/ildsp/unlifted_reach.py "$FL_WIN64_DIR/extracted/block24360_PE.bin" <closure.json> <lift dir>` (`lift_wc.sh ok` の後)。測定 commit `7c65af9e7` (コードを変えた最後の commit。以降のコード差分 0。`git diff 7c65af9e7 HEAD -- tools/shared/lift/ildsp` の出力は本ファイルの追記のみ (`REPORT_APPENDIX_3216.md | 22 ++`))。実測: rc 0・5.17 s (4 core・load 0.00 0.04 0.01 → 0.08 0.05 0.02)。16 件は `count_unlifted.py` の出力と一致 (closure 2,757・missing 109・非 padding 16)。

| 番地 | 命令 | 判定 | 根拠 (静的) |
|---|---|---|---|
| `0x1b8eb1`・`0x1b8eb8`・`0x1b8ebc`・`0x1b8ebf`・`0x1b8ec4`・`0x1b8ec8` (6) | `0x1b8e68` の SEH except 本体 | **例外 path のみ・未確定** | `.pdata` の UNWIND_INFO (EHANDLER。UNWIND の handler `0x1aebb4`) の scope 表: try `0x1b8eaa`–`0x1b8eb1` (`call 0x1be130`)・except target `0x1b8eb1`・filter `0x1ccb00`。直接の分岐元は 0 件 (直前は `jmp 0x1b8ed2`)。`0x1b8eb1` の 4 byte RVA は `.rdata` の scope 表 (`0x3f2db0`・`0x3f2db8`) の 2 件だけ。到達は `0x1be130` が例外を送出し、filter が実行を許可した時のみ。filter の戻り値と、送出時の wasm 側の挙動 (`_Unwind_RaiseException` の import 経路) は未確認 |
| `0x1be14e`・`0x1be156`・`0x1be158`・`0x1be160`・`0x1be162`・`0x1be167`・`0x1be16c` (7) | `ret` (`0x1be14d`) の後の島 | **静的な参照経路なし** (間接 jmp `0x1bd4e9` の実行時宛先で届く可能性は未排除) | 島の入口 `0x1be14e` への直接分岐 0 件、データ参照 (abs8・rva4・rip 相対) 0 件、直前は `ret`。内部の `jae`・`jbe` (`0x1be156`・`0x1be160`) は島の中の `0x1be16c` だけを指す。0x1be16c の `ret` も同じ島の中 |
| `0x1ac9b8` (1) | `jmp 0x1ac9c0` (alloc への stub) | **静的な参照経路なし** (間接 jmp `0x1bd4e9` の実行時宛先で届く可能性は未排除)・閉包の混入 | 直接の呼出元 109 件はすべて閉包外 (閉包内 0 件)。`0x1ac9b0` は `.pdata` 外で、近似範囲 `0x1ac9b0`–`0x1ac9c0` に入るだけ。閉包へ `0x1ac9b0` が入った経路は未確認 (未解決) |
| `0x1bd4b0`・`0x1bd4b7` (2) | `mov [G], rcx`・`ret` | **閉包外の呼出元からのみ・未確定** | 直接の呼出元は `0x1b7da8` の 1 件 (閉包外)。データ参照 0。`G` (0x3f84d0) の書込みは `0x1bd4b0` だけ。閉包内の `0x1bd4e9` (間接 jmp) が `G`・`A` に依存する (下表の注)。 |

- 6 件 (`0x1b8e*`) の扱い: x64c は try 本体の `call 0x1be130` を lift するが、landing pad は直接経路が無いため lift されない。例外が送出される path の差は、この 1 件 (`0x1be130`) が決める。
- 注 (`0x1bd4e9`): 宛先は `rax = ror(A ^ G, A & 63)` (A = 0x3f5d98・G = 0x3f84d0)。ファイル値 (A = `0x2b992ddfa232`・G = 0) では `rax` は `0xae64b77e88c8000` で、16 件のいずれでもない (画像外。CFG dispatch で止まる)。`A` は `0x1ad0d8` で実行時に書かれるため、宛先は静的に確定しない。
- jump table 候補: 閉包の間接 jmp `0x1af08b` (`jmp r9`・表 `0x442000`) の k = 0〜16 の値は `0x1af090`–`0x1af0e8` の 17 件のみ。16 件のいずれも含まない (k = 17〜19 は 0)。
- 判定の限界: 静的に見た参照の種類 (直接分岐・絶対 VA・rva4・rip 相対・SEH scope) の全件走査。間接の計算ジャンプは `0x1bd4e9` の 1 件だけで、宛先は実行時値。

### 7-4c 残り (未解決・起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1be130` が例外を送出するか・filter `0x1ccb00` が許可するか (`0x1b8e68` の except 本体 6 件の到達) | 到達すれば 6 件の lift 欠落が実行に出る。wasm 側の挙動は未確認 | [T-SH-134] #5090 (元の [T-SH-52] #3216 は CLOSED) |
| `0x1ac9b0` が閉包に入った経路 (`0x1ac9b8` の混入) | 閉包の完全性。`0x1ac9b8` の静的な直接呼出元は閉包外 109 件のみ (閉包内 0 件) | [T-SH-134] #5090 |
| `0x1bd4e9` の宛先 (A の実行時の書込み・G の値) | 残り 2 件 (`0x1bd4b0`・`0x1bd4b7`) と、島 7 件 (`0x1be14e`〜`0x1be16c`) の到達。島 7 件は静的な参照経路なしだが、間接 jmp の実行時宛先で届く可能性は未排除 | [T-SH-65] #3318 (間接 jmp の trap 化) |

### 7-5 slot 1–5 の観測 (未確定)
再現: `bash tools/shared/lift/ildsp/probe_slots.sh` (wc_image.py を `WC_CALL_SLOTS=6` で、CreateInstance → slot 0–5 の全呼出を native のみで実行)。
実測 (`2cff3f50d`): `[native] cases=64 SIGSEGV/SIGBUS=64 SIGALRM=0`・`crashed_cases=64`。全 case で sig=11 addr=0x0。
- slot 0 (`0x1a9cf0`): CreateInstance 直後に `this` = instance で呼べる (import 0 回)。差分 64 case に含めた。
- slot 1 (`0x1a9f10`): `[this+0x20]` (`0x1a9f2a`) を読む。CreateInstance が 0 にしたままなので値は 0。後続の参照で null を踏む、と推定 (deref の箇所は未特定)。
- したがって slot 1–5 は、host が事前に `this` の内部フィールドを設定する前提が要る。その前提は未確定 (子 #3274 / T-SH-57)。

### 7-6 検証範囲 / 範囲外
- 範囲: CreateInstance (1 呼出) → slot 0 (1 呼出)。引数は `rcx` = instance・`rdx` = arena+0x8000・`r8`・`r9` = 0。`.data` の事前状態 64 種。比較は rax (合成値)・import 呼出回数・heap 領域 64 KiB・`.data` 全体。
- 64 case は全て同一の実行経路。native の出力 (`res_native.bin`) で `(rax, hits)` は 64 件すべて `(0x5d9b00001, 1)`、heap 領域 (arena) の sha256 は 1 種類 (全 case 同一)。出力の `.data` は 64 種類で、入力 `.data` の差はその中にのみ残る。よって 64 PASS は「入力 `.data` に依存しない 1 経路の一致」であり、分岐の網羅ではない。
- CreateInstance の引数: native 側は引数なしで呼ぶ (rcx〜r9 は未定義)。CreateInstance 本体 (`0x1ac470`–`0x1ac49b`、12 命令) は rcx を `0x1ac476`、rdx・r8 を `0x1ac480`・`0x1ac482` で書いてから読み、r9 は現れない。呼出先 alloc `0x1ac9c0` の先頭は rcx のみ使う (`0x1ac9c6`)。よって入力の rcx〜r9 は結果に影響しない (呼出先 `0x1b6ea0` の rdx・r8 への依存は未確認)。
- 範囲外: slot 1–5 と closure 70 関数の全体差分 (子)、VEX 3 命令 (子)、stack・TEB・TLS の比較 (比較していない)、import 戻り値の実 Windows との一致 (両側で同じ手書き規約。lift の正しさだけを見る)。
- `issue #3216` 本文が参照する「REPORT.md §7-5 の未解決 (WC 以外の vptr 格納 3 件・helper `0x1aedc0`/`0x1b6f4c`)」は、現 HEAD の REPORT に記載が無い。`REPORT_CLOSURE.md` §4.6 の表が対応する。これは未実施 (子)。

### 7-7 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| slot 1–5 の host 前提の確定と、closure 70 関数の native 対 wasm 全バイト差分 | 受入 (2) の残り・gate の範囲 | 子 [T-SH-57] |
| VEX 3 命令 (vcvtss2sd・vpmovsxdq・vshufps) の x64c 対応 (unsup 3 site) | 受入 (1) の残り。実行到達時は trap | 子 [T-SH-58] |
| REPORT_CLOSURE.md §4.6 の未解決 (WC 以外の vptr 格納 3 件・helper `0x1aedc0`/`0x1b6f4c` の正常系到達) の native 確定 | 受入 (3) | 子 [T-SH-59] |
| 未 lift 非 padding 16 件 (直接分岐の先でない 15 + 島の 1。§7-4) の到達性 | closure の完全性 | [T-SH-57] の受入に含める。SEH except 6 件 (`0x1b8eb1`–`0x1b8ec8`) と `0x1ac9b8` は §7-7b で静的に判定済み (残りは ldmxcsr 入力の仮定の確認のみ) |

### 7-7b 未解決の確定 (T-SH-134 / #5090・静的判定)
再現: `FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_closure.py` (既定出力 `tools/shared/work/raw/ildsp_closure.json`) → `python3 tools/shared/lift/ildsp/seh_reach.py "$FL_WIN64_DIR/extracted/block24360_PE.bin" tools/shared/work/raw/ildsp_closure.json`。出力は A〜F 節の計算結果で、判定文は含まない。
- SEH (`0x1b8e68`): scope table は try `0x1b8eaa–0x1b8eb1` (`call 0x1be130` の 1 命令)・filter `0x1ccb00`・except `0x1b8eb1`。filter は `0xc0000005`・`0xc000001d` のときだけ 1 を返す。
- `0x1be130` は `ldmxcsr` だけの関数。閉包内の `0x1b8e68` 呼出元 (`0x1c34df`・`0x1c3727`・`0x1c37f2`) は `edx = 0xffc0` を渡し、ldmxcsr の予約 bit に影響しない前提が立つ。except 本体 6 件 (`0x1b8eb1`・`0x1b8eb8`・`0x1b8ebc`・`0x1b8ebf`・`0x1b8ec4`・`0x1b8ec8`) は、この前提の下で閉包から到達しない。
- except 本体 `0x1b8eb1`–`0x1b8ec9` への `call`・`jmp`・`jcc` の直接参照は .text 内 0 件 (E 節)。RVA 値としてのデータ参照は .rdata の `0x3f2db0`・`0x3f2db8` の 2 件 (F 節)。この 2 件が何の値かは未判定 (未確認)。
- `0x1ac9b8` (計算結果: D 節・D' 節): 閉包の根から閉包内の直接 edge で到達する命令集合 R は 2,604 命令。`0x1ac9b0` (`jmp 0x1acfe0`) は R に入る。`0x1ac9b8` (`jmp 0x1ac9c0`) は R に入らない。`0x1ac9b8` への直接 call は 109 件あり、全て閉包外 (例: `0x162004` owner `0x161fc0`・`0x16221c` owner `0x1621b1`) からで、閉包内の参照元は 0 件。閉包内の直接 edge は `0x1ac9b8` を指さないため、閉包から到達しない。`0x1ac9b8` は実行されうる命令 (死んだ断片ではない)。閉包外の呼出元からは実行されうる。
- 閉包が `0x1ac9b0` を含む経路: `0x1ac460` (`mov edx, 0x228`) → `jmp 0x1ac9b0`。`0x1ac9b0` は `.pdata` の関数先頭ではなく、`ildsp_closure.py` の「次の .pdata 先頭まで」の近似で閉包に入る。

根拠の内訳: ldmxcsr 入力 `ecx = ((~ebx | 0xffff807f) & eax) | (edi & ebx)`。閉包内の呼出では `ebx = 0xffc0` なので、ecx の上位 16 bit = eax (stmxcsr の結果) の上位 16 bit。MXCSR の bit 16–31 は x86 の予約 bit で stmxcsr は 0 を返すため、ldmxcsr の予約 bit 違反 (#GP → 0xc0000005) は閉包内の経路では起きない。except 本体は閉包から到達しない。
未確定 (残り): 閉包外の呼出元 `0x1c35ff`・`0x1c36be` (owner `0x1c35c4`) は閉包の外。「どの export からも到達しない」は seh_reach.py では計算していない (未確認)。閉包の定義を変えた場合は、この 2 呼出元の到達を確認し直す (子 [T-SH-57] の範囲)。

### 7-8 測定後のコード差分 (差分 0 の証跡)
測定 commit は `ce4f51453` (origin/main。閉包の数値を出した `ildsp_closure.py` と `seh_reach.py` の入力を含む)。`git diff ce4f51453 HEAD -- tools/shared/lift/ildsp tools/shared/scripts tools/flelift/x64c.py tools/flelift/rt tools/shared/env.sh ':!*.md'` の出力は `seh_reach.py` の 1 件のみ (125 行追加。本 PR の差し替え)。閉包の計算 (`ildsp_closure.py`) に使うファイルは差分 0。
なお `2cff3f50d` 以降の差分は main の取り込み (51 files) を含むため、本節の根拠には使わない。
