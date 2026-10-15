# SHX-T28 (#2444): 親フレーム共有 site の機械語検出と unit 18 の baseline (D23 候補, 親 #1630)

## 1. 結論

- 機械語 (capstone・.pdata 区間の線型逆アセンブル) から、**親が `mov rcx, rbp` で rbp 自体を callee へ渡し、callee が rcx 経由で親フレームを読み書きする site** を検出する検出器を追加した (`tools/m11/frame_share/detect.py`)。受入条件 1 はこれで満たす。
- 閉包 7,421 関数 (新 IR `work/boot_final3.ll`) では、`mov rcx, rbp` 直後の call が **307 site**。そのうち callee の rbp 基準アクセスが親の rbp 基準アクセスと重なるもの (D23 の検出信号) は **301 site・親 63 関数・callee 94 関数**。
- `function_448490` → `function_4483f0` は **8 site** (`0x448588`〜`0x44872c`)。REPORT_SHX-T27 §5 の「8 箇所」と一致する。
- **親 IR の欠落 (新しい観測・静的)**: 機械語 `0x4484e4` の `mov dword ptr [rbp+0x4c], 1` (親の局所。IR 名 `-28`) に対応する store が IR に無い。`function_448490` の IR で `store i32 1` は `-32` (`rbp+0x48`) への 1 本だけで、`stack_var_-28` という名前は 0 件。callee は `[rbp+0x4c]` を読み書き (+76) するので、この欠落は修復が要る候補。§6。
- **修復 pass と修復前後の実測 (受入条件 2・3) は本 run では未実施**。1 run の上限内で検証まで閉じられないため、子 issue `[SHX-T40]` に移す (§9)。
- baseline (修復前・新 IR) は T27 §4-A と一致: `units_run=17`・`dllmain_done=true`・unit 18 で `VirtualAlloc(0x76910000)` → OOM → NULL → `MessageBoxA "Runtime error 0 at …"`。

## 2. 測定条件

- ベース: `origin/main` `56778a14`。ブランチ `2444-shx-t28-nested-frame`、worktree `ws-2444`。main の共有ツリーは触っていない。
- 素材: `work-m11` を worktree に展開 (`tools/m11/work/`・gitignore)。PE は `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B、sha256 `b2c64da4…9f9496d`)。
- IR の作り直し: `work/lift_pe.sha256` に上記 PE の sha256 を手で書いてから `bash tools/m11/m11_gen_ir2.sh` (非 `--full`。lift は素材の `boot0〜4.lift.ll`・`boot5` を使う)。46 s・ok。続けて `bash tools/m11/m11_build.sh` 22 s・`[m11build] OK … signature mismatch: 0, undefined symbol: 0`。
  - 前提 (T27 §2 と同じ): 指紋は手で書いた。素材の lift を生成した PE との一致は未検証。`--full` は Ghidra (`functions_dll.csv`) が runner に無いため未実施。
- shimx: `bash tools/m11/shimx_link/build.sh --trace --soft` rc 0・13.2 s (commit 前の初回)・`signature mismatch=0 undefined symbol=0 duplicate=0`。実 boot は `SHIMX_TRACE_FILE=/ftrace.jsonl node tools/m11/shimx_link/run_trace.mjs <cjs> --out DIR` で rc 0・0.41 s。
- 負荷: 測定時の uptime 1 分平均 1.09 (nproc 4)。

## 3. 検出器 `tools/m11/frame_share/detect.py`

- 入力: 閉包 = 新 IR の `define … @function_<hex>` の集合。機械語は `ldfix/ldmach.py` の `Machine` (.pdata の関数境界で線型 disasm) を流用。
- 手順:
  1. 親関数の各 `call <imm>` について、直前 12 命令以内 (分岐・call・ret を越えない) に rcx への `mov rcx, rbp` があるかを見る。`lea rcx, [rbp+K]` は別扱い (`how=lea`)。
  2. callee を線型に走査し、rcx の別名 (`mov reg, rcx`・`lea reg, [alias+d]`・`add/sub reg, imm`) を追って、別名を base にしたメモリ命令を集める。オフセットは親の rbp 基準 (= rcx の初期値 + disp)。call で caller-saved の別名は捨てる。
  3. callee のアクセス範囲が親の rbp 基準アクセス (親が `[rbp+K]` で触る範囲) と重なれば `shared` (D23 の信号)。重ならなければ `callee_only`。
- 制限: 制御フローを無視した線型走査。32bit 書込みは 64bit 名に畳む。`lea` の site は局所 1 個の番地渡し (通常の var 参照渡し) が大半なので、D23 の信号からは外し、件数だけ参考に出す。
- 出力: 件数の summary と site 一覧 (`--out` で JSON)。JSON は `work/` に置き、commit しない。

## 4. 実測 (閉包全体・新 IR `work/boot_final3.ll`)

| 項目 | 件数 |
|---|---|
| 閉包の関数 (IR の `define`) | 7,421 |
| うち .pdata の関数境界が取れず disasm 不能 | 452 |
| `rcx` が `rbp` 由来の call (mov または lea) | 5,798 |
| うち `mov rcx, rbp` (rbp そのものを渡す) で callee が rcx 経由のメモリを触る site | **307** |
| うち D23 の信号 (callee の rbp 基準アクセスが親の rbp 基準アクセスと重なる) | **301** |
| 　　その親関数 | 63 |
| 　　その callee 関数 | 94 |
| `mov rcx, rbp` で callee の rbp 基準アクセスが親と重ならない (callee_only) | 6 |
| 参考: `lea rcx, [rbp+K]` で callee が触る site (D23 の信号からは外す) | 2,531 |

- 最多の親 (D23 信号 site 数): `function_43f800` 24・`function_443490` 24・`function_457c70` 22・`function_1042d20` 17・`function_e3ef60` 16・`function_e2a0c0` 15。
- 最多の callee: `function_457c40` 22・`function_1042d00` 17・`function_e3eef0` 16・`function_43f440` 15・`function_e2a080` 15・`function_443030` 11。
- D23 信号の親関数 (63): `1006ec0 10348b0 1042d20 11ca4e0 11e7430 125d9b0 127d420 1280530 12a4450 12a93b0 12c6630 12cab20 12cb680 12d4480 12e60b0 13105d0 408b60 40b620 40f210 43ae60 43f800 441380 441730 441b20 443490 444dd0 447f40 448490 457c70 497e60 517b50 5c5500 612aa0 6905f0 6a09b0 6a25b0 6a2820 6b97e0 6cdee0 6ed9e0 72df20 8675c0 977f50 9ce9e0 a96df0 a9e7a0 c55dc0 cb9eb0 cc7c50 d23c00 d26460 dc2130 dd8380 ddd1f0 ddeca0 de10c0 de43b0 e25380 e2a0c0 e3ef60 e4f310 f40840 fed8c0` (`function_` 接頭辞を省略)
- D23 信号の callee 関数 (94): `1006ce0 1006dd0 1034780 1042d00 11ca410 11e6c00 11e7310 125d960 127d120 1280170 1280250 1280380 12a4390 12a92d0 12a9350 12c6570 12ca640 12cb4c0 12cb4f0 12cb570 12cb5e0 12d42f0 12e5ef0 12e5fd0 13104e0 1310550 408970 40b290 40f160 43adf0 43f440 43f490 43f550 43f580 440d30 441500 441530 441560 4415a0 4416a0 441900 441930 441a90 443030 443080 4430c0 444c90 444d20 447ee0 4483f0 448430 457c40 497e40 517a40 517ac0 5c53e0 6129d0 690580 6a0760 6a23d0 6a26e0 6b94b0 6b9690 6cd900 6ed7f0 72de70 867540 977870 977e40 9ce950 a96d40 a9e430 a9e4d0 a9e570 a9e610 c55d60 cb9e00 cc7c00 d23b80 d26430 dc20d0 dd8230 ddd1a0 dde970 dde9f0 ddea70 de0fc0 de4120 e25310 e2a080 e3eef0 e4f2d0 f3d5e0 fed830`

注: 301 site は「親が rbp 基準で触る範囲と callee の触る範囲が重なる」ことしか見ていない。通常の Delphi の「親の局所を `rbp` 渡しで受ける」パターンも含みうる。真の D23 (callee が親の別の値を読む) かどうかは site ごとの突合が要り、本 PR では確認していない (§9 の子 issue に含める)。

## 5. `function_448490` の `mov rcx, rbp` site (10 件)

| call (VA) | callee | callee の rbp 基準アクセス (off:size:kind) | 親と重なる親のオフセット |
|---|---|---|---|
| `0x448588` | `function_4483f0` | `0x70:8:load`・`0x4c:4:load`・`0x4c:4:rmw`・`0x48:4:rmw` | `0x48`・`0x4c`・`0x70` |
| `0x4485c6` | `function_4483f0` | 同上 | 同上 |
| `0x44864a` | `function_448430` | `0x70:8:load`・`0x4c:4:load`・`0x4c:4:rmw` | `0x4c`・`0x70` |
| `0x44865b` | `function_448430` | 同上 | 同上 |
| `0x448692` | `function_4483f0` | `0x70:8:load`・`0x4c:4:load`・`0x4c:4:rmw`・`0x48:4:rmw` | `0x48`・`0x4c`・`0x70` |
| `0x4486ca` | `function_4483f0` | 同上 | 同上 |
| `0x4486e0` | `function_4483f0` | 同上 | 同上 |
| `0x448708` | `function_4483f0` | 同上 | 同上 |
| `0x448720` | `function_4483f0` | 同上 | 同上 |
| `0x44872c` | `function_4483f0` | 同上 | 同上 |

- `function_4483f0` (`Append`) の機械語 (静的): `[rcx+0x70]` を読み (親の引数 home slot)、`[rcx+0x4c]` を読み・+1、`[rcx+0x48]` を +1 (REPORT_SHX-T27 §5 と一致)。

## 6. 親の機械語と IR の突合 (`function_448490`)

- 親の prologue (機械語): `push rbp; push rsi; push rbx; sub rsp, 0x50; mov rbp, rsp` → `rbp = entry_rsp − 104`。IR の `stack_var_-N` は entry_rsp 基準の名前と**推定**する (`%stack_var_-104` を rbp の object とみると、callee の +0x48・+0x4c が IR の `-32`・`-28` に一致するため。推定。確認は未実施)。この前提では `rbp+K` は IR 名 `-104+K`。
  - `[rbp+0x48]` = `-32`・`[rbp+0x4c]` = `-28`・`[rbp+0x70]` = `+8` (entry の rcx home slot)。
  - IR の `%stack_var_-104` は `alloca [6 x i64]` (48 B、`-104`〜`-56`)。callee が触る `+0x70` まで含めると 120 B 必要で、alloca が足りない。
- 機械語の対応 (親):
  - `0x4484b3`: `mov [rbp+0x70], rcx` → IR の `%arg1` (SSA)。
  - `0x4484d3`: `mov dword [rbp+0x48], 1` → IR `store i32 1, ptr %stack_var_-32.0.reg2mem` (1 本)。
  - `0x4484e4`: `mov dword [rbp+0x4c], 1` → **IR に対応する store が無い** (`-28` の名前は `function_448490` に 0 件)。
  - `0x448536`: `movsxd rdx, dword [rbp+0x4c]` → IR の対応する読みは未特定。
- したがって親の IR は `[rbp+0x4c]` の初期値を持たない。callee の `[+76]` の読み・加算は親の値を経由しない。原因 (RetDec の stack var 検出か後段 pass のどれか) は未確認。
- 親の `[rbp+0x48]` (`-32`) は loop 変数として `stack_var_-32.*.reg2mem` の SSA 分解で扱われ、callee の `[+72]` の rmw (+1) が IR の値に反映されない。D23 の機構 (callee が親の値を別の場所から読む) と整合する。

## 7. baseline (修復前・新 IR・測定 commit は `e0ff2fa0` (検出器のコミット)。c14f55eb で再現済み。main 取り込み後の HEAD は §8)

| 段階 | 結果 |
|---|---|
| `bash tools/m11/shimx_link/build.sh --trace --soft` | rc 0・`[sxlink] OK trace_soft: signature mismatch=0 undefined symbol=0 duplicate=0` (commit 前の初回・HEAD `e0ff2fa0` の 2 回とも同じ) |
| 実 boot (`run_trace.mjs`) | rc 0・0.41 s・`units_run=17` `icall_ok=24` `icall_miss=1` `dllmain_done=true` `longjmp_hit=1` `boot_rc="1"` `threw=null` |
| trace | `total_calls=106` `distinct_called=29` `dropped=0`・ftrace 0 行 (T27 §4-A と一致) |
| 停止の証跡 (stderr) | `[m11][VA] #1 addr=0 size=1989214208 (0x76910000)` → `Cannot enlarge memory … limit is 2147483648 bytes` → `[m11][VA] OOM want=1989.2MB … (NULL を返す)` → `[m11][MessageBoxA] caption='Error' text='Runtime error   0 at 00000000102A0410'` |

- 注: T27 §4-A は `signature mismatch=1` と記録しているが、本 run の 2 回の build はいずれも 0 だった。差の原因は未確認 (`tools/m11/work/shimx_link/link_trace_soft.log` は現在 0 件)。重複・未定義は両者とも 0。
- 修復 OFF のネガコンと修復 ON の比較は、修復を入れた子 issue で行う (本 PR は修復を含まない)。

## 8. 検証の鮮度

- 測定 commit: `e0ff2fa0` (検出器 `tools/m11/frame_share/detect.py` を追加したコミット。§4・§7 の数値はこの commit の検出器で採取した)。
- `e0ff2fa0` で再実行 (HEAD と同じ IR・同じ手順): 検出 `closure 7421`・`mov 渡し 307`・`D23 信号 301`・親 63・callee 94 (§4 と一致)。shimx `build.sh --trace --soft` は `mismatch=0`、実 boot は `units_run=17`・`dllmain_done=true`・`total_calls=106`・ftrace 0 行 (§7 と一致)。
- `e0ff2fa0` から HEAD までのコード差分: `git diff e0ff2fa0 HEAD -- tools/m11/frame_share tools/m11/shimx_link tools/m11/*.py tools/m11/*.sh tools/m11/ldfix` の出力は、c14f55eb 時点では 0 行 (本 REPORT の文言修正のみ)。main 取り込み merge `871e59d3` 後は 7 files・+313/-7 で、main 側の変更 (`m11_lb_unit_diff.py`・`m11_lb_tolerant_repro.sh`・`ldfix/fix_ld108.py`・`ldfix/fix_ld116.py`・`ldfix/dyn_ld115.mjs`・`ldfix/ld116_e2e.sh`・`ldfix/REPORT_2513.md`) を含む。IR の既定経路 (`m11_gen_ir2.sh` → `ldfix/fix_ld108.py`) は、環境変数 `M11_LB_BASE` 未設定時の出力文字列が従来と同一 (コード読解)。`fix912/` (既定 OFF) も既定では変化しない。ただし `work-m11` 素材 (lift 済み `boot0〜5`) が本 run に無く、HEAD `871e59d3` での再現・再測定は**未実施**。この REPORT の数値は `e0ff2fa0` の測定値のまま。

## 9. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 親フレームを callee の view に結線する修復 pass (`function_448490` の `-28` store の欠落の補完、`this` object の拡幅 (`-104`〜`+16`)、call 前後の count・length・arg1 の同期) | unit 18 を越えられず、逐次 boot の ftrace が 0 のまま | `[SHX-T40]` (親 #2444 の子) |
| 修復 OFF/ON の before-after 実測 (`units_run ≥ 18`・`VirtualAlloc(0x76910000)` 不発・`MessageBoxA` 不発・ネガコン) と、`docs/DEFECTS.md` D23 の「修復」列 | 受入条件 2・3・4 の残り | `[SHX-T40]` |
| 301 site の真偽 (真の D23 か、通常の rbp 渡しの局所参照か) | 修復範囲の決定 | `[SHX-T40]` (修復の受入に含める) |
