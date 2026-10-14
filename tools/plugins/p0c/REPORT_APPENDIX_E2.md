# tools/plugins/p0c REPORT 付録 E2 (§14.6〜§14.8)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)・`REPORT_APPENDIX_E.md` (§14 本体)。本ファイルは `REPORT_APPENDIX_E.md` から **無変更で分割移動**した節の全文 (`docs/DOC_MAP.md` §1 の 250 行上限・内容は削除しない)。節番号・見出しは移動前のまま。

### 14.6 #983: 残差 3 kernel の原因確定と修復 (検証 HEAD `cb34601`)

原因 (機械語を capstone で読んで確定。lift 前段で RetDec が落としていた):

- **0x5dee90 / 0x5df040** (buf_diff 2,565,360 / 2,565,277): 先頭の `movups xmm7,[r10]` (r10 = r9 = 第 4 引数 arg4) の読み元が、
  IR で arg4 でなく未初期化 `alloca %r9` になっていた。修復後も `fix_asm_stores` を通さないと 993 cell 残る (下記)。
- **0x5e02b0** (buf_diff 2,578,706): `mov rdx,[rdx]` (record の第 1 qword を base にする) が落ち、2 本目の出力 base が arg2 自体になっていた。

修復: `k80_deref_fix.py` (新規、関数単位の置換で 1 箇所一致を assert、負論対照 `K80_NO_DEREF_FIX=1` は no-op)。
`p0c3_e2e.sh` / `p0c4_abi_e2e.py` の chain に組み込み。`p0c3` は lift 後段と揃えるため `fix_asm_stores` を前段に追加した。

| 実測 (HEAD `cb34601`、素材 `fl-win64` のみ、2000 case) | 結果 |
|---|---|
| `p0c4_abi_e2e.py 2000` | rc=0、27.0 s (load 0.14〜0.38)、`run=67 ok=67 sig11=0`、3 kernel とも buf_diff=0 |
| `p0c3_e2e.sh 2000` | rc=0、50.1 s (load 0.41〜0.44)、回帰 11 + 3 kernel とも buf_diff=0 |
| 修復前 (同じ素材・同じ chain) | 0x5dee90=2,565,360 / 0x5df040=2,565,277 / 0x5e02b0=2,578,706 |

注意: `p0c3` で `fix_asm_stores` を外すと 0x5dee90 / 0x5df040 は buf_diff=993 になる (`p0c4` は 0)。
pass の順序依存で、lift 後段の順序 (`fix_asm_stores` → f80_lower) に揃えた。

### 14.5 再現

```sh
export TMPDIR=$PWD/tools/plugins/p0c/work/tmp
python3 tools/plugins/p0c/f80_assess.py                       # work/f80_classes.json
python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000                # sig11=0 / B6 ok を判定に含む
for v in WRITTEN_BASE ARGORD IDX_NOT_BASE CLIPRANGE PARTIAL_LOAD MEMW REGSRC STACKW INTERSECT; do
  env K80_NO_$v=1 python3 tools/plugins/p0c/p0c4_abi_e2e.py 2000  # 負論対照 (rc は下記)
done
```
負論対照の rc (merge 後 HEAD 実測): **MEMW と REGSRC は rc=0** (受入判定を通る。MEMW は §14.2 のとおり buf_diff が
増えるが判定対象外、REGSRC は差なし)。**それ以外の 7 種は rc=1** (WRITTEN_BASE `run=67 ok=63 sig11=4` / ARGORD
`ok=65 sig11=2` / IDX_NOT_BASE `ok=66 sig11=1` / CLIPRANGE `ok=66 sig11=1` / PARTIAL_LOAD `run=65` / STACKW `run=66` /
INTERSECT `run=66`)。MEMW の差は CSV の buf_diff でのみ検出できる。
前提: `k80.lift.ll` は `bash tools/plugins/lift/lift_ranges.sh <PE> work/k80_ranges.txt tools/plugins/p0c/work k80 2400`
で再生成。`llvm-as` / `clang` は PATH に必要 (runner では `/usr/lib/llvm-18/bin`)。
`/opt/retdec` と `/home/ubuntu/work/{analysis,webstudio}` は runner 上の symlink で代替 (§12.4)。

### 14.7 0x5de3e0 の上位 dword store 復元 (#982、親 #331)

機械語 `fistp qword [rbp+8]` の後に `mov [rdx], eax` (上位 dword) と `mov [r8], eax` (下位 dword) の 2 store がある。
RetDec IR は下位 store (`%arg3`) のみで、`%arg2` の `inttoptr` が未使用だった (lift 欠落、§14.4 の未解決)。

- 修復: `tools/plugins/lift/passes/fix_fistp_hi_store.py` [P-S2] (opt-in、関数指定)。下位 dword store の直後に
  `lshr 32` → `trunc` → 未使用 `inttoptr` への store を挿入する。対象形が 1 関数に 1 つだけ成立するときのみ書き換え、曖昧なら何もしない。
  `p0c4_abi_e2e.py` は `K80_NO_FISTP_HI=1` で外せる。`lift_ranges.sh` は `PLUG_FISTP_HI_FUNCS` で指定する。
- 実測は §14.7 末尾の最新 HEAD (`84202772`) の表が現行値。以下は pass 初版時の旧測定 (過去の検証 HEAD、記録のみ):

| 条件 | 検証 HEAD | rc | 所要 | load (開始時) | 0x5de3e0 buf_diff | ok かつ buf_diff=0 |
|---|---|---:|---:|---:|---:|---:|
| 修復なし (`K80_NO_FISTP_HI=1`) | 作業ツリー (コミット前、内容は `7a8e5b1f` と同一) | 0 | 27.1 s | 0.14 | 2000 | 45 |
| 修復あり | `7a8e5b1f` (コミット済み、#983 取り込み前) | 0 | 27.2 s | 0.28 | **0** | **46** |

- 差分は 0x5de3e0 の 1 行のみ (他 79 kernel の `run / ok / sig11 / buf_diff` は不変)。`run=67 ok=67 sig11=0`。
- `lift_ranges.sh` の opt-in 経路: `PLUG_FISTP_HI_FUNCS=function_5de3e0` で `on.final.ll` に `fhi_s` が 2 箇所、未指定で 0 箇所。
- レビュー指摘への対応 (支配チェック): 下位 store より後で定義される `%H` への挿入は、`llvm-as` が
  `Instruction does not dominate all uses!` で落ちるため候補から除外した。`%fhi_s` / `%fhi_v` が既存のときも書き換えない。
  回帰テストは `tools/plugins/lift/passes/test_fix_fistp_hi_store.sh` (`llvm-as` で検査。ok / dom / name / 旧 pass の負論対照)。
  実行結果は `OK` (4 ケースとも期待どおり)。`887d59fb` でも `test_fix_fistp_hi_store.sh` → `OK` (rc=0)。支配チェック後の pass で 0x5de3e0 の候補は落ちず `fixed` になる。
  最新 HEAD `84202772` (main `a0e6ed71` 取り込み後) での実測。素材 `fl-win64` `toolchain-retdec` `toolchain-emsdk` `work-liftlib` を展開。`k80.lift.ll` は `kernel_table.py` → `lift_ranges.sh` (80 defines) → `f80_assess.py` → `p0c4` の順で再生成。クリーン worktree、各 1 回・直列。

  | 条件 | 検証 HEAD | rc | 所要 | load (開始時 1 分) | 0x5de3e0 buf_diff | ok かつ buf_diff=0 | run / ok / sig11 | 0x5dee90 / 0x5df040 / 0x5e02b0 |
  |---|---|---:|---:|---:|---:|---:|---|---|
  | 修復なし (`K80_NO_FISTP_HI=1 p0c4_abi_e2e.py 2000`) | `84202772` | 0 | 15.3 s | 0.40 | 2000 | 48 | 67 / 67 / 0 | 0 / 0 / 0 |
  | 修復あり (`p0c4_abi_e2e.py 2000`) | `84202772` | 0 | 15.6 s | 0.32 | 0 | 49 | 67 / 67 / 0 | 0 / 0 / 0 |

  - 修復なしと修復ありの kernel 行の差分は 0x5de3e0 の 1 行 (buf_diff 2000 → 0) のみ (`diff` で確認)。
  - kernel 表 80 implementations / 45 variables / 10,886 B / x87 28 は一致。`test_fix_fistp_hi_store.sh` → OK (rc 0)。
  - 修復ありの IR: `on.final.ll` に `fhi_s` が 2 箇所 (`PLUG_FISTP_HI_FUNCS=function_5de3e0` 指定時、`[P-S2] function_5de3e0: fixed`)。

  過去の検証 HEAD (記録のみ・現 HEAD の値ではない):
  - `887d59fb` (main `b53f24e0` 取り込み前): 修復なし 0x5de3e0 buf_diff 2000 / ok かつ buf_diff=0 は 45、修復あり 0 / 46。残差 0x5dee90 / 0x5df040 / 0x5e02b0 は修復ありでも buf_diff 2,565,360 / 2,565,277 / 2,578,706 のまま (main の #983 `k80_deref_fix.py` を含まなかったため)。
  - `7a8e5b1f`: 修復あり 0x5de3e0 buf_diff 0 / ok かつ buf_diff=0 は 46 (#983 取り込み前、修復なしの測定は作業ツリー)。

  - 未検証: `p0c3_e2e.sh` (0x5de3e0 を回帰判定から除外する別経路)、`p0c_e2e.sh` / `p0c2_e2e.sh`。
- 未検証: 0x5e12b0 (#331)。`p0c3_e2e.sh` の回帰判定 (0x5de3e0 除外の既存処理) の見直しは #331。

### 14.8 #331 の残件の現況 (main `60932d35`、実測)

#331 の残差 5 kernel のうち 4 kernel (0x5de3e0 / 0x5dee90 / 0x5df040 / 0x5e02b0) は、#982 (PR #1013) と #983 (PR #1031) で main に取り込み済み。
main で再測定すると 4 kernel とも buf_diff=0 (ok)。残るのは 0x5e12b0 のみ。

- **0x5e12b0 (未解決)**: 機械語は `ucomiss xmm0,xmm1; ja; movaps xmm0,xmm1; ret` (= max)。RetDec IR は xmm 入力を `xor i128 0,0` に、
  flags を `xor i1 0,0` に定数化し、`define i64 @function_5e12b0()` (引数ゼロ・戻り値定数 0) になる。
  `k80abi.json` は xmm0/xmm1 を正しく抽出しており、ABI 抽出ではなく IR 側の欠落。
  xmm 戻り値 kernel の判定 (ret_diff を合否にするか) を含めて、汎用 IR pass 側の #938 [T-SH-22] が追跡する。
- 実測 (`60932d35`, 素材 `fl-win64` / `toolchain-retdec` / `toolchain-emsdk`、`llvm-as` は clang 18 の shim で代替):
  - `p0c_e2e.sh`: rc=0, 7 分 52 秒, `== e2e OK ==`
  - `p0c4_abi_e2e.py 2000`: rc=0, 30.2 秒, `run=67 ok=67 sig11=0`。0x5de3e0 / 0x5dee90 / 0x5df040 / 0x5e02b0 は buf_diff=0。
    回帰 11 kernel (0x5de820 0x5dedf0 0x5dfb60 0x5df210 0x5df240 0x5e0760 0x5e0b70 0x5e0bb0 0x5e1590 0x5e1780 0x5e0330) は buf_diff=0。
    0x5e12b0 は差分表に出ず abi-mismatch のまま。
