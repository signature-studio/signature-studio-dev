# REPORT_APPENDIX_4080 — x87 独立入口の突合と断片の親入口 (#4080 PLG-G2-43)

既知類型との関係: float64 の 1 ulp 差は既存の f80→f64 類型 (D28)。 `10009bc4` の ST(0) 不一致は未分類 (§2)。 `docs/DEFECTS.md` の既存 ID へは当てていない。

- 親: #4066 (判定の正本は `REPORT_APPENDIX_4066.md` §1)。 前提 #4084 は merge 済み。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` と乱数 (seed 2989)。 静的解析と x87 命令の突合のみ。
- 測定 commit: `fc5445ee8` (コードを変えた最後の commit)。

## 1. 独立入口 4 本の引数形 (逆アセンブルで確定)

| 入口 | 呼出し規約 | 根拠 | 試験 |
|---|---|---|---|
| `0x100052d0` | thiscall (ecx = this・float a0..a2・`ret 0xc`) | 本体は `[ecx+...]` と `[esp+0x10..0x14]` を読む。 leaf (call 無し) | TARGETS (`state_update`) |
| `0x10005550` | thiscall (同上・`ret 0xc`) | 本体の `call 0x10002ee0` は TARGETS の lift 済み関数 | TARGETS (`state_update`) |
| `0x1000bf1e` | cdecl (a0 = double、`[ebp+8]`・`[ebp+0xc]` の 8 バイト。 `[ebp+0xe]` はその上位語の一部) | `ret` (引数は caller が捨てる)。 呼出し元 `0x1000bd7b`・`0x1000bd89` は double を `push` 2 つ + `add esp,8` | PROBE (`double1`) |
| `0x10009bc4` | cdecl (a0 = double) | `ret` のみ。 `call 0x1000b503`・`0x1000b3cb`・`0x1000acd8` は lift 済み | PROBE (`double1`) |

## 2. 突合の実測 (commit は §4)

既定ゲート (TARGETS 7 本): `python3 x87_fn_diff.py` → PASS、rc 0、所要 12.8 s (build native 0.12 s・wasm emcc 5.46 s / run native 0.660 s・wasm 0.867 s / load1 0.85)。

| 関数 | 行 | bit 一致 | 構造 (eax・x87 深さ・非自明性) | 差の中身 |
|---|---:|---:|---|---|
| `0x100052d0` | 4000 | 3761 | eax 0・深さ 0・OBJ 窓変化 4000 | float64 のみ 1 ulp 239 語 (f80→f64) |
| `0x10005550` | 4000 | 3363 | eax 0・深さ 0・OBJ 窓変化 4000 | float64 のみ 1 ulp 637 語 (f80→f64) |
| `0x1000bf1e` | 4000 | 4000 | eax 0・深さ 0・OBJ 窓変化 **0** (OBJ を書かない) | なし |
| `0x10009bc4` | 4000 | 0 | eax 0・深さ 0・OBJ 窓変化 0 | ST(0) (float32 と float64) が全行 `nan-num` 4000 (片方が NaN でない) |

- `1000bf1e` は OBJ 窓を書かない関数なので、既存の effect 判定 (非自明性) が 0 件になり FAIL する。 そのため PROBE に置いた。 値の一致は 4000/4000。 非自明性は OBJ 窓の代わりに eax の使用で別に示す必要がある (未実施。 子 #4858 へ移す)。
- `10009bc4` は ST(0) の不一致が全行。 native と wasm のどちらが NaN かは未確認 (`nan-num` 分類)。 原因は未確定。 子 issue へ移す。

## 3. 断片 6 本の親入口 (`0x1000c077`)

- `0x1000c077`: `83ec2c` (sub esp,0x2c) → `83e03f` (and eax,0x3f) → `ff24853e4e0210` (`jmp [eax*4+0x10024e3e]`)。 直接の call/jmp と絶対 dword 参照は PE 全体で 0 件。 **親の入口は参照関係だけでは確定できない**。
- 断片 6 本 (`0x1000c084`〜`0x1000c0ac`) は jump table の case 先で、各 case は `x87 命令; add esp,0x2c; ret` (`0x1000c08a`・`0x1000c095` のように `int 6` の死枝もある)。
- 試験: 未試験。 本 PR の TARGETS・PROBE は `0x1000c077` を含まず、この入口の突合はこの PR のコードから再現できない (以前の文面の 4000 行 bit 一致は再現手順が無いため削除)。
- 結論: 親の入口は未確定。 呼出し元の追跡 (`0x1000c077` を指す間接参照の由来) が要る。 子 #4837 へ移す。

## 4. 測定 commit と検証

- 変更は `tools/plugins/slayer_engine_ia32/x87_fn_diff.py` (TARGETS 2 本・PROBE 2 本・`double1` 生成器) のみ。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/plugins/slayer_engine_ia32/lift_text.py` の後 `python3 x87_fn_diff.py` (rc 0)、`--nega` (bit 一致 22619 → 22618)、`--nega-lower` (f32 不一致 4000/4000)。
