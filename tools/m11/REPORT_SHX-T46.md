# SHX-T46 (#5203): function_448490 の count (-32) をメモリに統合する修復 pass (D23 段 1・既定 OFF)

## 1. 結論

- `ldfix/fix_shx_t46.py` を追加した。`M11_FIX_SHX_T46=1` のときだけ、count (IR `-32`) の 6 つの reg2mem スロットを、親 object `%stack_var_-104` の `+0x48` を指す GEP (`%fx46cnt`) への load/store に置き換える。object は `[15 x i64]` (120 B) に拡幅する。
- 実測 (ON): IR 生成 rc 0・build rc 0・trace build rc 0 (`mismatch=0 undefined=0 duplicate=0`)。実 boot は `memory access out of bounds` (`dllmain_done=false`・`va_calls=1`)。既定 OFF の baseline は従来どおり。ON は baseline より悪化した。
- 受入 1 の一部 (count の統合と拡幅) のみ。`-28` の store 補完・length (`-28`)・arg1 の同期は未実装 (段 2 の opt-in `M11_FIX_SHX_T46_LEN` を §1.1 に示す。ON は hang)。

## 1.1 追記 (SHX-T46 段 2: entry の +0x70 / +0x4c 初期化・`M11_FIX_SHX_T46_LEN=1`・既定 OFF)

- `fix_shx_t46.py --length` は、既存の統合に加えて entry の `+0x70` (`store i64 %arg1`・機械語 `0x4484b3`) と `+0x4c` (`store i32 1`・機械語 `0x4484e4`) を入れる。`m11_gen_ir2.sh` は `M11_FIX_SHX_T46=1 M11_FIX_SHX_T46_LEN=1` のときだけ付ける。`ir_conditions.json` は `shx_t46=applied-length`。
- 実測 (ON・length): IR 生成 rc 0 (490,795 行)・build rc 0 (mismatch 0・undefined 0)・trace build rc 0 (mismatch 0・undefined 0・duplicate 0)。実 boot (`run_trace.mjs`・上限 150 s) は **rc 124 (hang)**・出力なし。T40 の `+0x4c` 初期 store と同じ症状。
- 既定 OFF の IR sha は変更前と一致 (`b202c157a80807f2`)。OFF の実 boot は `units_run=17`・`dllmain_done=true`・`va_calls=2`・`icall_ok=24`・`boot_rc="1"`・0.24 s。
- 同じ環境で T46 単独 (`M11_FIX_SHX_T46=1`) を再測: `dllmain_done=false`・`va_calls=1`・`threw="memory access out of bounds"` (§2 の ON と一致)。
- `+0x70` のみの変種は、IR 指紋 (`ir_conditions.json`) の不一致で build が止まったため **未測定**。機序の切り分けは未完。
- 受入 1 の残り (`-28` の初期化の位置・call 前後の length/arg1 同期) は未達。ON は hang のため既定にできない。

## 2. 実測

測定 commit: `f93b0feaf` (コードを変えた最後の commit)。`git diff f93b0feaf HEAD -- tools/m11/ldfix/fix_shx_t46.py tools/m11/m11_gen_ir2.sh` の出力は 0 行。

| 条件 | IR 生成 | build / trace build | 実 boot (`run_trace.mjs`) |
|---|---|---|---|
| OFF (既定・`shx_t46=not-applied`) | rc 0・`fx46cnt` 0 件 | rc 0・mismatch 0・undefined 0 / trace rc 0 | rc 0・`units_run=17`・`dllmain_done=true`・`va_calls=2`・`icall_ok=24`・`icall_miss=1`・`longjmp_hit=1`・`boot_rc="1"`・`threw=null` (REPORT_SHX-T61 と一致) |
| ON (`M11_FIX_SHX_T46=1`・`shx_t46=applied`) | rc 0・`fx46cnt` 29 件・`llvm-as` rc 0 | rc 0・mismatch 0・undefined 0 / trace rc 0 | rc 0・`units_run=17`・`dllmain_done=false`・`va_calls=1`・`icall_ok=24`・`icall_miss=1`・`threw="memory access out of bounds"` |

- 実 boot の時間は OFF・ON とも 0.5 s 以下 (`time` の real)。
- 素材: `docs/REFERENCES.md` `[WIN64]` の `extracted/block00031_PE.bin` (`fl-win64` 展開物)。展開先は環境変数 `FL_WIN64_DIR` で指定。`work-m11` は `tools/m11/work/`。

## 3. 機械語・IR の確認

- 機械語では count は親の `[rbp+0x48]` (= IR `-104 + 72` = `-32`) の 1 か所。callee `function_4483f0` は `this+0x48` を `+1` する (IR で `load`・`add`・`store`)。
- lift 後の IR では count が `%stack_var_-32.{0,1.lcssa,124,1249091,2,12768}.reg2mem` の 6 スロットに分かれ、callee の書込みと結び付いていなかった。6 スロットへのアクセスは `store i32`/`load i32` のみで、形は揃っていた (検査で確認)。
- 本 pass は 10 site ごとの before/after 表を作らずに、6 スロットを同じ 1 つのメモリ (`%fx46cnt`) に置く。これは callee の書込みが次の親の読出しに届くことを意図した設計である。ON の実測では効果は確認できなかった (boot は OOB で止まる)。読出し・書込みの対応は未測定。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `-28` (length) の store 補完・call 前後の length/arg1 同期 | ON の OOB が残る見込み。受入 1 の残り | #5203 (本 issue に残す) |
| ON の OOB の原因の切り分け | 本 pass 単独では boot が通らない | #5203 (本 issue) |
| 受入 2 (OFF/ON の実測) | 本 PR で一部実施。ON は未達 | #5204 |
