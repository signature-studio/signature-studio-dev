# #1676 (#1507 の残り): unit 275 の list B が base=0 で生成される経路

親: #1507 (REPORT_881 §10)。前提: `tools/m11/trap_triage/REPORT_881.md` §10。

## 0. 結論

1. **list B は unit 114 で生成され、生成時点で `base(+8)=0`・`cnt=1` になる** (`probe1676_listB_writes.mjs`、n=1)。base は後から 0 になるのではなく、作られた時点で 0。
2. base=0 のまま `50a830` が `[base+8*cnt]` に書くため、unit 114 の callback は `mem[0]` に書き (REPORT_881 §10 の `mem[0]` 一致と同じ)、unit 275 の callback は `mem[8]` (= list A の base 番地) を書き換える。
3. 生成経路の **IR と機械語は一致しない**。`function_410320` / `function_410360` は IR 上 `ret arg1` (identity) だが、機械語はそれぞれ `call qword ptr [rax-0x30]` / `call qword ptr [rbx-0x50]` の **メモリ間接 call** を含む。IR にはこの間接 call が無い。`40f9e0` (list を作る 8651a0 が呼ぶ) はこの 2 関数を経由する。
4. よって base=0 の原因は **間接 call 脱落 (DEFECTS D15 と同類型、メモリ間接 `call [reg+disp]`)** が第一候補。ただし脱落先の vtable 実体で list の base を入れているかは **未確認** (次段で確定)。
5. survey は HEAD で n=2 再現 (`ok 872 / oob 15 / halt0 7`、unit 275 は oob)。

## 1. 実測の基準

- 素材: `fl-win64` (`block00031_PE.bin` sha256 `b2c64da4…`)、`toolchain-retdec` (`/opt/retdec`)、`toolchain-emsdk` (`/opt/emsdk`)、`work-m11`。
- `work/lift_pe.sha256` は手作業で PE 指紋を記録 (REPORT_881 §10.2 と同じ手順)。
- 全再生成は実行: `m11_e2e.sh` (foreground、rc=0、165 s、load 約 1.0)。reached_stage 4、survey_ok 872、IR sha256 `6909f85d…` (REPORT_881 §10 と一致)。
- 注意: 展開直後の `work-m11` の wasm (`m11_boot.cjs`) は `_m11_icall_cnt_n` を持たず、survey が `TypeError` で落ちた。e2e の再ビルドで解消。

## 2. list B の生成と監視 (n=1)

`trap_triage/probe1676_listB_writes.mjs` (全 942 unit、unit ごとに `[G2+188]`・base・cnt を監視):

| unit | 結果 | list B | base | cnt |
|---|---|---|---|---|
| init | - | 0 | - | - |
| 114 | halt0 | 0x10bd4c20 (新規生成) | **0** | 0→1 |
| 275 | trap (oob) | 同 | 0 | 1→2 |
| 830 | trap | 0 (消失) | - | - |

- 変化した unit は 114・275・830 の 3 件のみ。
- 114 で list B が初めて非 0 になり、そのとき base は既に 0。**生成時の base 初期化が無い**。

## 3. 生成経路 (IR と機械語の突合)

- `function_867510` は `8674a0` (list を走査) の後 `EnumDisplayMonitors(… [G2+188])` を呼ぶ。`8674a0` は `50aa70` と `40faa0` を呼ぶ。
- list の生成元は `function_8651a0` (object 構築)。`[obj+188]` は `40f9e0(0xC9A40, 1)` の戻り値。
- `40f9e0` → `410320` (alloc 相当) / `410360` (固定サイズ helper)。IR はどちらも `ret arg1`。
- 機械語 (`disasm_img.py`):
  - `410320`: `test dl,dl; ...; call qword ptr [rax-0x30]` (**vtable 間接 call**)。
  - `410360`: `call qword ptr [rbx-0x50]` (**vtable 間接 call**、`rbx = [rax]`)。
  - `8651a0` 内の call 列 (`40f9e0`×6、`5c0d40`×5 など) は IR と一致。
- 既知類型: `tools/m11/REPORT.md` 行 34 の「間接 call が IR から全滅 (4,175 件中 IR 0)」と、`docs/DEFECTS.md` の D15 (メモリ間接 call の空ブロック)。

## 4. 未達と起票先

| 未達 | 理由 | 起票先 |
|---|---|---|
| list B の base 初期化の実体 (vtable 間接 call の実 target と戻り値) の確定 | 間接 call 先の target を `m11_icall` 相当で解決する必要がある | 子 issue (親 #1676) |
| DEFECTS 行の確定 (D15 同類型か、別類型か) | 上記確定後 | 子 issue |
| n≥2 の list B 監視 (probe 1676 の繰り返し) | 本 run は n=1 | 子 issue (再測定) |

## 5. 検証結果 (実測)

- e2e `m11_e2e.sh` (foreground、rc=0、165 s、reached_stage 4、survey_ok 872)。
- survey `SV_RAW=1 survey_units.mjs` n=2: 両回 `{"ok":872,"miss":46,"other":1,"halt0":7,"oob":15,"noproc":1}`。
- probe `probe1507_listB.mjs` n=2: 両回で list B `base(+8)=0`、unit 114 halt0、275 の callback が `mem[8]` を `0x10bd5280` に書換え (REPORT_881 §10 と一致)。
- probe `probe1676_listB_writes.mjs` n=1: list B は unit 114 で base=0 のまま生成。
- 注意: 本 run の確定は n=1 (監視 probe)。n≥2 は未実施。

## 6. #1931 の追補 (n=2 再現・thunk の逆アセンブル)

- 測定 commit: 検証起点 `8f4c6379` (main)。素材: `fl-win64` (sha256 `b2c64da4…`)・`toolchain-retdec`・`toolchain-emsdk`・`work-m11`。
- `work-m11` には `lift_pe.sha256` が無く、`m11_e2e.sh` の全再生成は `m11_bounds.py` が `m2/work/ghidra_dll/functions_dll.csv` を要求して落ちた (素材に無い Ghidra 中間物)。
  PE 指紋 `b2c64da4…` が一致したため `work/lift_pe.sha256` を手で記録し、非 `--full` 経路で再ビルドした。
- e2e `m11_e2e.sh` (foreground、rc=0、166 s、load 0.5): reached_stage 4、survey_ok 872、survey_trap 23、miss 46、IR sha256 `6909f85d…` (§10 と一致)。
- probe `probe1676_listB_writes.mjs` n=2: 両回とも unit 114 で `L=0x10bd4c20`・`base=0`・`cnt=1` の生成、unit 275 で trap。n=1 の結論が n=2 でも再現。
- thunk の逆アセンブル (`trap_triage/dis1676_thunks.py`):
  - `410320`: `rax=rcx`。`dl<0` 以外のとき `call qword ptr [rax-0x30]` (引数 `rcx=rax`)。
  - `410360`: `rbx=[rax]`、`call qword ptr [rbx-0x50]`。
  - `40f9e0`: `dl≠0` のとき `410320` → `410360` の順に呼ぶ。`dl=0x81` の分岐には `call qword ptr [rbx-0x20]` がある。
  - 補足: IR の `function_410320` / `410360` は `ret arg1` のみで、上記 2 つの間接 call は IR から脱落している。
- 未確定: 間接 call の**実 target** (vtable の中身) と、list B の base を入れる関数。object→vtable の対応は未特定。
  線形逆アセンブルの call 元走査が 0 件だったため、呼出し元の追跡は未完。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `[rax-0x30]`・`[rbx-0x50]` の実 target と base 設定関数の確定 | list B の base=0 の原因特定 | 既存 #1783 [LD-63] (410320 スロットの書き込み元の実行時 watch) |
| DEFECTS 行 (D15 同類型か) | 分類 | 上記確定後 (#1931 の残件) |
| `SV_RAW=1 survey_units.mjs` の n≥2 は未実施 (本 run は e2e 内の survey n=1) | survey 側の再現性が未確認 | 既存 #1783 の再測定に含める |
