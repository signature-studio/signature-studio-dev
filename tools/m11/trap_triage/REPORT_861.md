# #861: unit 189 (409470 ReallocMem) の deref 脱落の修復の検証

親: #417 (残 8 の 1 件)。前提: `main` `986e7415`。`m11_ov.c` は無変更 (転記は #474 で既に採用済み)。

## 1. IR と逆アセンブルの突合 (受入 1)

逆アセンブル (`disasm_fn.py 409470`、PE `block00031_PE.bin`):

- `409479: cmp qword ptr [rbx], 0` / `484: mov rcx, qword ptr [rbx]` が *P (1 段 deref) の読み出し。
- `4094b4: mov qword ptr [rbx], rsi` / `4094da: mov qword ptr [rbx], rsi` が *P への書き戻し。

IR (`work/boot_final.ll` の `function_409470`, `ldfix` 適用後):

- 先頭が `icmp eq ptr %arg1, null` (P 自体の null 判定) で、*P (`load ptr %arg1`) を読んでいない。
- `dec_label_pc_409484` は `ptrtoint ptr %arg1` を `function_408040` に渡している。つまり P のアドレスを
  ヒープ先頭として扱っている。
- 対応する類型は `docs/DEFECTS.md` の D4 (1 段 deref 脱落)。REPORT.md §3-2・REPORT_418.md の記述と一致する。

## 2. 修復の状態と実測 (受入 2)

修復 (C 転記 `function_409470`, `m11_ov.c` L626-L648) は main に既に入っている。本 PR はコード変更なし。

build: `bash tools/m11/m11_build.sh` (IR は `m11_gen_ir2.sh` で再生成、ldfix=applied)。

| 構成 | ok | miss | other | halt0 | oob | noproc | 測定 |
|---|--:|--:|--:|--:|--:|--:|---|
| HEAD (転記あり) ×2 | 869 | 47 | 1 | 8 | 16 | 1 | 2 回とも同一 (per-unit 差 0) |
| ネガコン (転記を `nc_409470` に改名) | 846 | 47 | 0 | 19 | 29 | 1 | 1 回 |

unit 189 (`CharLowerBuffW` の stub 経由):

- HEAD: `kind: ok`。ただし `CharLowerBuffW` の未実装 stub (0 を返して継続) を 7 回踏んでいる。
  `ok` は stub 依存で、真の修復とはまだ言えない。
- ネガコン: `kind: halt0`。frames は `function_409470` → `function_409730` (Error)。
  転記が 189 の ok に効いている。

## 3. ネガコン (受入 3)

転記を無効化すると unit 189 は `ok → halt0`。per-unit JSON での遷移 (HEAD → ネガコン):

- `ok → halt0`: 12 件 (53 54 58 59 60 61 62 63 **189** 311 884 888)
- `ok → oob`: 12 件 (45 95 101 138 291 296 307 503 891 898 935 936)
- `other → halt0`: 1 件 (56)、`halt0 → oob`: 1 件 (114)、`halt0 → ok`: 1 件 (368)

転記が無いと 24 件の ok が非 ok になる。つまり転記は多くの unit の ok を支えている。

## 4. 回帰 (受入 4) と未解決

「修復で他 unit が ok→非 ok にならないか」は、修復なし (ネガコン) を基準にすると **非 ok になるのは unit 368 の 1 件のみ**
(転記ありで `halt0`、なしで `ok`)。転記あり HEAD を 2 回測って unit 368 の結果は同一 (決定的)。

unit 368 の内容: 転記ありでは `function_409470` 経由の VA-big 確保 2 回目 `size=2427797504` が
`Cannot enlarge memory (limit 2 GiB)` で halt0。転記なしでは同じ確保が 1 回目の時点で止まり ok。
転記が 832 MB 確保の回数を変えたことによると見られるが、呼び出し元の切り分けは未実施。

**受入 4 は未達**。unit 368 の ok→halt0 回帰は本 PR 内では解消していない。原因切り分けと修復は #1043 (`[M11-N61]`、親 #861) へ持ち越す。

## 5. 未解決 (起票先付き)

- unit 189 の `CharLowerBuffW` 未実装 stub。stub を実装しないと 189 の ok が真の ok か判定できない。 → #172 (SHX-T5) へ。
- unit 368 の VA-big 確保 (HEAD で halt0、転記なしで ok) の原因切り分けと回帰の解消。 → #1043 (`[M11-N61]`、親 #861)。受入 4 の持ち越し先。
- 転記 ON の利得 24 件 (ネガコンで非 ok になる unit) の中身 (各 unit の trap 原因) は未調査。

## 6. 再現

```sh
export FL_WIN64_DIR=$HOME/analysis/win64 ANALYSIS_DIR=$HOME/analysis LD_M11_PE=$FL_WIN64_DIR/extracted/block00031_PE.bin
bash tools/m11/m11_gen_ir2.sh     # ldfix=applied の ir_conditions.json を作る (work-m11 の IR は古い)
bash tools/m11/m11_build.sh
node tools/m11/trap_triage/survey_units.mjs out.json   # 約 10 s
python3 tools/m11/trap_triage/disasm_fn.py 409470
```
