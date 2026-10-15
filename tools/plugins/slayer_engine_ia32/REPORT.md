# tools/plugins/slayer_engine_ia32/REPORT.md — FL Slayer x86 engine (Slayer_Engine.dll) の ia32 decode 基準値 (#674 中間)

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/slayer_engine_ia32/` のみ / 親 #536 (結合方式は決定済み・PR #677 は未マージ。本件はその成果に依存しない独立計測) / 本 issue #674 の**中間成果** (受入条件 5 項目は 0/5 達成)
- 対象: block22434 (`extracted/block22434_PE.bin`, 179,512 B, sha256 `84b64c43…de724a9`) = FL Slayer の x86 engine と推定。 根拠は AEffect 構築 store (§9.1、magic 即値) と opcode 25 の dispatch 構造 (§9)。 他の ia32 PE (§9.5) は engine か未確認
- 検証起点 commit: `5574803` (修正版。 検証記録は §6)。 初版は `bd8690c`。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 $PY tools/plugins/slayer_engine_ia32/measure.py --dump` (gate) と `… measure.py --nega` (ネガコン)。 `$PY` は `uv venv $RUNNER_TEMP/venv_ia32 && uv pip install --python $RUNNER_TEMP/venv_ia32/bin/python capstone==5.0.7`。 capstone の版が 5.0.7 以外、または入力の SHA-256 (`84b64c43cc6528401e1c4e84074785e100e8453c4db4c8322a5d5f608de724a9`) が一致しない場合は gate の前に exit 1 (`[pin]` / `[input] FAIL`)。
- 既知類型との関係 (`docs/DEFECTS.md`): **該当なし**。 本件は decode の静的計測で lift 出力は作っていない (silent miscompile の観測対象外)。 新類型の候補は §7 の行案のみ (DEFECTS.md は未編集)

## 1. 結論 (先出し)

1. **PE は想定どおり**: machine 0x14c (i386)、`.text` VirtualSize 73,002 B (SizeOfRawData 73,728 B、file offset 0x1000、VA 0x1000、ImageBase 0x10000000)。 #536 の既知事実 (x87 4,203・SIMD 0・間接 call 302) を同じ数で再現した。 機械語 25,349 命令は capstone の線形掃引の値 (objdump 2.42 では 25,312、§3 検算)。
2. **線形掃引 (CS_MODE_32) のデコード不能は capstone で 4 B (0.0055%)、最大連続 1 B**。 ia32 の命令デコード自体は capstone で全域ほぼ通る。
3. **x64c は ia32 の経路を持たない** (`tools/ott/lift/x64c.py` は `Cs(CS_ARCH_X86, CS_MODE_64)` の 1 箇所のみ、1,560 行、32bit 固有の分岐なし)。 同じバイト列を 64bit で読むと **573 命令 (2.26%) が命令境界か mnemonic を取り違える** (inc/dec の REX 誤認が主)。 x64c の mnemonic 扱いは 82.77% の命令をカバーするが、x87 系と一部の 32bit 固有命令は未対応 (§4)。
4. **ia32 front-end で新規に必要になるもの** (推定を含む。 数字は実測): x87 の全系統 (f* 4,203 件・うち fldcw/fnstcw 50 件)、絶対 disp32 のメモリ参照 1,270 件、FS セグメント (TEB) 20 件、`0x66` 付き命令 132 件、`0x67` 1 件、`rep` 系 110 件、32bit 固有の `cdq`/`movzx`/`movsx`/`pushfd`/`popfd`/`leave`/`sahf`/`into`/`imul` 等。
5. **gate は 4 本 (C1〜C4)、ネガコン 3/3 が期待どおり FAIL** (miss 0)。 C3 (不能率) は粗い gate で、乱数破壊は検出できない (§5)。 検出は C4 (特権命令件数) が担う。

受入条件の達成 (issue #674): 0/5。 emcc -c 通過・x87 方針・marshal 表・native vs wasm 差分試験・LoadLibrary shim はいずれも未着手 (§6 未解決)。

## 2. PE ヘッダ (実測)

| 項目 | 実測 |
|---|---|
| machine | 0x14c (i386) — 期待どおり |
| optional header magic / ImageBase | 0x10b (PE32) / 0x10000000 |
| セクション | `.text` (VA 0x1000, VirtualSize 73,002, SizeOfRawData 73,728, rawptr 0x1000), `.rdata` (VA 0x13000, 5,765), `.data` (VA 0x15000, 345,696), `.rsrc`, `.reloc` |
| .text 逆アセンブル範囲 | VirtualSize 73,002 B (SizeOfRawData の末尾 726 B は掃引しない) |

## 3. 逆アセンブル実測 (線形掃引, CS_MODE_32, capstone 5.0.7)

| 項目 | 値 | 数え方 |
|---|---|---|
| 命令数 | 25,349 | 1 回のデコードで得た命令の数 |
| デコード不能 | 4 B (0.0055%)、最大連続 1 B | 掃引位置で decode 失敗 → 1 B 捨てて続行。 分母は .text VirtualSize |
| 所要 / load average / 並列数 | gate: in-process 0.55–0.60 s、wall 622–676 ms (n=3)。 load 1 分 0.27 → 0.27・並列数 1 (cpu 4) | `measure.py` の `[timing]` 行 (単一プロセス)。 min–max は §6 |
| x87 (mnemonic `f*`) | 4,203 | 指定どおりの生数。 `fxsave`/`fxrstor`/`femms` を除いた数も 4,203 (該当 0) |
| x87 制御系 | fldcw 32・fnstcw 18・fstcw 0・fnstenv 2・fldenv 2 | 指定の 5 種 |
| SIMD (xmm/mm/ymm またはグループ) | 0 | 指定どおり (#536 C7 と一致) |
| 間接 call / 間接 jmp | 302 / 53 | operand が reg/mem。 直接 call は 727 |
| 特権命令 (C4 の対象) | 15 | 内訳 out 3・outsb 2・insb 3・insd 1・outsd 1・in 2・iretd 3 (hlt/cli/sti は 0)。 baseline の正体は未確認 (§6) |
| メモリ参照形 | abs (disp のみ) 1,270・sib (index あり) 468・base のみ 7,528 | 命令ごとの memory operand 分類 |
| FS セグメント | 20 | TEB 参照 (Win32 の TLS/SEH 相当) |
| prefix | 0x66: 132・0x67: 1・rep 系: 110 | 先頭の legacy prefix |

mnemonic 頻度 (上位 30, 件数): mov 4755 / push 2581 / nop 1376 / pop 1201 / call 1029 / cmp 1020 / fld 996 / add 940 / je 858 / test 799 / ret 779 / fstp 753 / fmul 672 / jne 671 / jmp 652 / lea 590 / and 484 / xor 379 / or 336 / inc 310 / sub 274 / fadd 272 / dec 216 / fxch 204 / int3 182 / fnstsw 172 / fst 153 / fsub 144 / jl 130 / jge 112

ia32 で要注意の mnemonic (件数): cdq 21 / movzx 51 / movsx 54 / lea 590 / pushfd 2 / popfd 1 / xchg 5 / bt 2 / bts 2 / shld 2 / leave 90 / enter 1 / into 3 / sahf 33 / jecxz 1 / int 17 / imul 14 / mul 8 / div 8 / idiv 17。 `cwde`/`cbw`/`cwd`/`pushad`/`popad`/`cmpxchg`/`xadd`/`bswap`/`bsf`/`bsr`/`cpuid`/`rdtsc` は 0。

**特権命令 15 件の位置** (.text オフセット、capstone と objdump で同一): 0x11f4 out / 0x1204 outsb / 0x312c insd / 0x6c6d insb / 0x6c70 insb / 0x6c71 outsb / 0x6c74 in / 0x6c75 outsd / 0x6c84 in / 0x908c out / 0xc535・0xc539・0xc53d iretd / 0xc540 out / 0xfe40 insb。 0x6c6d〜0x6c84 の 6 件と 0xc535〜0xc53d の 3 件が密集する。 「データ領域の誤復号」という推定と整合するが、該当範囲の内容は未確認 (§6)。

### 検算: 別デコーダ (GNU objdump 2.42)

再現: `FL_WIN64_DIR=… $PY tools/plugins/slayer_engine_ia32/xcheck_objdump.py` (同じ .text を `objdump -D -b binary -m i386 -M intel` で逆アセンブルして集計。 capstone と独立した別デコーダでの検算)。 下表の objdump 列はそのスクリプトの出力。

| 項目 | capstone 5.0.7 (上表) | objdump 2.42 |
|---|---:|---:|
| 命令数 (mnemonic を持つ行) | 25,349 | 25,312 (`(bad)` 3 行を除く) |
| x87 (`f*`、fwait を除く) | 4,203 | 4,204 |
| fldcw / fnstenv / fldenv | 32 / 2 / 2 | 32 / 2 / 2 |
| fnstcw + fstcw | 18 (18 + 0) | 18 (10 + 8) |
| call (直接 + 間接) | 1,029 (727 + 302) | 1,029 (727 + 302) |
| 特権命令 | 15 | 15 (同じ 15 オフセット) |

- 命令数の差 37 (25,349 − 25,312) は、両者の命令境界の取り方の差による (推定。 差の内訳は未確認)。 **25,349 は capstone の線形掃引に依存する値**であり、そのまま「命令数」の正本としない。
- fnstcw/fstcw の内訳が 18/0 と 10/8 に分かれるのは 9B (fwait) の扱いの差と推定。 合計 18 は一致。
- 不能バイトの位置 (.text オフセット): capstone は 0x91a4・0x924a・0xc530・0x10e60 (4 B)。 objdump の `(bad)` は 0x924a・0xc530・0x10e60 の 3 件で、0x91a4 は objdump では `lock mov eax,ds:0x468a1000` と復号される (不一致 1 件)。

## 4. x64c との対比

- **x64c の decode モード**: `CS_MODE_64` 固定 (1 箇所)。 ia32 の経路 (`CS_MODE_32`・32bit レジスタ幅・32bit アドレッシング) は無い → **「持たない」を確認**。
- **同じバイト列を 64bit で読んだ差分**: 573 命令 (2.26%) が mnemonic か命令長が一致しない。 上位: inc 247・dec 179・mov 111・push 16・pop 8・into 3・pushfd 2・pushal 2・arpl 1・popfd 1・les 1・aam 1・jecxz 1。 64bit では 0x40〜0x4F が REX 接頭辞になるため。 64bit 側で先頭位置が復号不能な命令は 35 件 (`x64_undecoded=35`)。
- **mnemonic 単位のカバレッジ** (`x64c.py` の `i_<mnemonic>` 定義と接頭辞規則 `cmov*`/`set*`/`j*`/`cmp*ss|sd`/`vcmp*`/`vf*`/`rep movs|stos` から機械判定、近似): 扱う命令 20,981 / 25,349 (82.77%)。 扱わない mnemonic 種は 80 件。 上位 40 件 (件数):
  fld 996, fstp 753, fmul 672, fadd 272, fxch 204, fnstsw 172, fst 153, fsub 144, fcomp 98, fistp 88, faddp 72, fild 70, fsubr 57, wait 50, fdiv 48, fcom 46, fsubp 41, fchs 40, sahf 33, fldcw 32, fmulp 28, repne scasb 27, fabs 18, fnstcw 18, fld1 17, fdivr 16, fsin 15, fscale 14, fdivp 13, frndint 13, fldz 11, stosd 9, fldl2e 8, f2xm1 8, std 8, fsubrp 7, fprem 7, fyl2x 5, fdivrp 5, fiadd 4
  - x64c は x87 を一切持たない (`i_f*` は `fnop` のみ)。 x87 は**全系統が新規**。
  - `stosd` (rep なし) 9 件・`std` 8 件・`sahf` 33 件は未対応。
  - 注意: 「扱う」判定は mnemonic 単位。 `cdq` (21 件) など x64c が扱う 32bit 系の命令も、x64c の実装は 64bit 幅を前提にしているため**意味の再確認が必要** (推定。 差分試験で確定)。

## 5. ネガティブコントロール (`measure.py --nega`)

判定器 (同じ `analyze`) に壊した入力を与え、**期待した gate だけが FAIL すること**を確認する。 出力 (`work/nega/` に壊したコピーを書く):

| NC | 壊した箇所 | 期待 FAIL | 実測 FAIL | 判定 |
|---|---|---|---|---|
| N1 | PE machine 0x14c → 0x8664 | C1 | C1 (machine=0x8664) | HIT |
| N2 | .text 先頭 300 B を seed 674 の乱数で上書き | C4 | C4 (priv=22 > 15) | HIT |
| N3 | .text VirtualSize 73,002 → 73,003 | C2 | C2 (73003) | HIT |

`nega: 0/3 miss` (exit 0)。 期待が外れた件数 miss=0 のため exit 0。

**C3 がランダム破壊を検出できない理由 (実測)**: 乱数で増える不能バイトは、先頭 300 B で baseline 4 B から +1〜+10 B (seed 674 は 8 B、seed 0〜7 は 5〜10 B)。 x86-32 は乱数をほぼ復号してしまう。 そのため C3 は「大きく壊れた」(不能率 >0.1% = 73 B 超) だけを検出する粗い gate として残し、乱数破壊は C4 が検出する。 C4 の上限 15 は baseline の実測値 (推定: データ領域の誤復号。 未確認)。

**N2 の数値 (再現)**: `FL_WIN64_DIR=… $PY tools/plugins/slayer_engine_ia32/measure.py --nega --seed S --bytes B` の出力のうち `[nega N2]` 節の `[C3]` 行 (不能 B) と `[C4]` 行 (priv)。 seed 674 と 0〜7、B = 300 / 512 の 18 本 (`measure.py` の既定は seed 674・300 B):

| seed | 300 B: 不能 B / priv | 512 B: 不能 B / priv |
|---:|---:|---:|
| 674 (既定) | 8 / 22 | 10 / 31 |
| 0 | 5 / 22 | 11 / 28 |
| 1 | 7 / 21 | 11 / 23 |
| 2 | 8 / 23 | 11 / 29 |
| 3 | 8 / 18 | 8 / 21 |
| 4 | 10 / 19 | 14 / 24 |
| 5 | 5 / 21 | 13 / 26 |
| 6 | 8 / 22 | 12 / 29 |
| 7 | 10 / 24 | 13 / 26 |

18 本すべて priv > 15 (C4 FAIL)・C3 は PASS (上限 73 B)、`nega: 0/3 miss`。 priv の範囲は 300 B で 18〜24、512 B で 21〜31。

## 6. 検証の実行記録 / 範囲外 / 未解決

検証 (worktree 再現) は本 REPORT を含む修正 commit の HEAD で行う。 `git worktree add --detach $RUNNER_TEMP/wt_verify HEAD` で展開し、§6 冒頭の再現コマンドを実行して §3・§4・§5 の数値と照合する。 結果は下表 (検証起点 `5574803`、クリーン HEAD で実行)。

| 項目 | 値 |
|---|---|
| 検証起点 commit | `5574803` (`git worktree add --detach $RUNNER_TEMP/wt_verify HEAD` で展開・実行後に `worktree remove --force`) |
| gate (`measure.py --dump`、n=3) | `[measure] OK (4/4)` ×3。 in-process 0.55–0.60 s、wall 622–676 ms、load 1 分 0.27 → 0.27、並列数 1 (cpu 4) |
| nega (`measure.py --nega`、n=3) | `nega: 0/3 miss` ×3。 wall 1,623–1,674 ms (load は nega で未記録。 同じ run の gate 側は 0.27) |
| 修正前の作業ツリー出力との照合 | gate の出力は `[timing]` 行を除き完全一致 (`diff` 0 行)。 §3・§4・§5 の数値は同 commit で再現 |
| N2 の seed 表 (§5) | 18 本 (seed 674・0〜7 × 300 / 512 B) を同 commit で再実行し、表の値と全件一致 |
| 検算 (`xcheck_objdump.py`) | 命令 25,312・`(bad)` 3 (0x924a・0xc530・0x10e60)・x87 4,204・fldcw 32・fnstcw 10 / fstcw 8・fnstenv 2・fldenv 2・call 1,029 (727 / 302)・jmp 652・priv 15 (§3 の位置と一致) |
| `git status --porcelain=v1 -- tools/plugins/slayer_engine_ia32` | 空 (検証 worktree) |
| 20 MiB 超の blob | 無し (`find tools/plugins/slayer_engine_ia32 -type f -size +20M -not -path '*/work/*'` は 0 件) |

範囲外 (受入条件のうち今回やらなかったもの): **emcc -c 通過** (ia32 front-end 本体が無い) / **x87 方針と差分試験** (f80→f64 の bit 差分は未実測) / **marshal 表** (殻↔engine の 32/64bit 構造体) / **native vs wasm 差分試験** / **LoadLibrary shim**。 いずれも #674 の継続。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ia32 front-end 本体 (CS_MODE_32 の lift 経路、32bit レジスタ幅・アドレッシング・prefix 0x66) と `emcc -c` 通過 | 受入条件 1 | #674 (`Refs #674`) |
| x87 方針 (f80 の扱い、x87 4,203 命令・fldcw/fnstcw 50 件) と差分試験 | 受入条件 2 | #674 |
| marshal 表 (殻 x64 ↔ engine ILP32 の `AEffect`/`ERect`/`VstEvents`) | 受入条件 3 | #674 |
| native vs wasm の差分試験 (engine 単体・bit-exact) | 受入条件 4 | #674 |
| `LoadLibrary("Slayer_Engine.dll")` の shim (土台は #94) | 受入条件 5 | #674 |
| 特権命令 15 件の内容 (§3 の位置、0x6c6d〜0x6c84 と 0xc535〜0xc53d に密集) がデータ領域の誤復号かどうか | gate C4 の意味 (推定。 未確認) | #674 (該当範囲の逆アセンブル全文を見て確認) |
| gate の強さ: C4 の上限 15 は実測値そのものの自己参照 gate。 C3 は乱数破壊を検出しない (§5) | 「gate 通過」の意味が限定される | #674 (上限を別の根拠で定める) |
| 閾値 C3 (0.1%) と C4 (15) は実測 baseline 由来の**運用値**で、他の対象へは流用しない | 再利用時の誤判定 | #674 (他の対象へ使う前に再設定) |
| 25,349 命令は capstone の線形掃引の値 (objdump 2.42 では 25,312、§3 検算)。 件数は掃引方式に依存する | 数値の比較・引用 | #674 (比較時は版と掃引方式を明記) |
| capstone の版差で件数が変わる可能性。 版は 5.0.7 に固定 (他版は gate 前に exit 1) したが、別版での件数は未計測 | 数値の再現 | #674 |

## 7. DEFECTS.md 新類型の行案 (編集はしない・PM 判断用)

| 案 ID | 区分 | 症状 (仮) | 検出 (仮) |
|---|---|---|---|
| D18 (案) | fe | **x64c に 32bit 機械語を渡すと、inc/dec (0x40〜0x4F) を REX と誤認して silent に別命令を生成する** (実測: 同 .text の 573 命令 / 2.26%) | 入力の PE machine が 0x14c なのに x64c (`CS_MODE_64`) を通す。 decode モードと PE machine の不一致を入口で fail-fast |
| D19 (案) | fe | **絶対 disp32 (ImageBase 基準 VA) の 32bit メモリ参照** (実測 1,270 件)。 wasm32 で VA→窓の写像が必要。 D11 と同型の VA リテラル問題 | `[disp32]` (base=0, index=0) 形の memory operand を数える |

いずれも推定。 D18 は「機械語と IR の取り違え」で D1〜D17 に該当する行が無い。 D19 は D11 の 32bit 版として統合できる可能性がある (推定)。

## 8. 成果物

| ファイル | 内容 |
|---|---|
| `measure.py` | 実測・gate C1〜C4 (`--dump` で `work/` に全命令の逆アセンブル、`--nega` でネガコン N1〜N3、`--seed`/`--bytes` で N2 の乱数条件を変える)。 capstone 5.0.7 と入力 SHA-256 を検証してから実行 |
| `xcheck_objdump.py` | objdump 2.42 による別デコーダの検算 (§3) |
| `REPORT.md` | 本ファイル |
| `work/` | gitignore 対象 (`tools/plugins/.gitignore`)。 逆アセンブル全文 (`block22434.ia32.disasm.txt`) と `nega/*.dll` |

## 9. AEffect marshal 表 (#674 受入 3) の実測

仕様は `MARSHAL.md` (本書は測定値の正本)。 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 $PY tools/plugins/slayer_engine_ia32/marshal.py` (gate) と `… marshal.py --nega` (ネガコン)。 `$PY` は §8 と同じ capstone 5.0.7 の venv。

### 9.1 engine の AEffect 構築 store 列 (ctor RVA 0x10E0〜0x1196、静的実測)

| 欄 (AE+off) | store 値 | 出所 |
|---|---|---|
| magic (0x00) | 0x56737450 | 即値 |
| dispatcher / process / setParameter / getParameter (0x04 / 0x08 / 0x0c / 0x10) | 0x10001000 / 0x100010a0 / 0x10001080 / 0x10001060 | 即値 (ポインタ) |
| **numPrograms (0x14)** | **`ebp`** (0x1139 `mov [edx+0x34],ebp`、`ebp` = `[esp+0x10]`) | 引数由来 (即値でない) |
| **numParams (0x18)** | **`eax`** (0x111e `mov [edx+0x38],eax`、`eax` = `[esp+0x1c]`) | 引数由来 (即値でない) |
| numInputs / numOutputs / flags (0x1c / 0x20 / 0x24) | 1 / 2 / 0 | 即値 |
| object (0x40) | `edx` (= this) | レジスタ (AEffect 自身ではない) |
| ioRatio (0x3c) / uniqueID (0x48) / version (0x4c) | 0x3f800000 / 0x4e6f4566 / 1 | 即値 |
| processReplacing (0x50) | 0x100010c0 | 即値 (ポインタ) |

- `rep stosd` の 0 埋めは `ecx = 0x24` dword = **0x90 B** (= sizeof)。 未 store の processDoubleReplacing (0x54) は 0 埋め由来。
- gate の `want` に numPrograms `ebp`・numParams `eax` を追加した (以前は未検査で `<- ebp`・`<- eax` のまま PASS していた)。

### 9.2 gate とネガコン (marshal.py)

| 項目 | 実測 |
|---|---|
| gate (`marshal.py`) | `[marshal] OK`・exit 0。 wall 88–110 ms (n=3)。 実行前 load 1 分 0.53・cpu 4 |
| nega (`marshal.py --nega`) | `nega: 0/6 miss`・exit 0。 wall 98–126 ms (n=3)。 実行前 load 1 分 0.53・cpu 4 |

- 所要は merge 後の HEAD で再測定 (`time` 相当の wall を `date +%s%N` で計測・各 n=3 の min–max)。 旧版の単発値 (0.065 s / 0.056 s) は本表で置き換えた。
- 本節 (§9.2) の表は marshal.py の gate と N1〜N6 の結果。 route 突合 (N5・N6) は §9.3 の注意を参照。

| NC | 壊した入力・期待 | 実測 FAIL |
|---|---|---|
| N1 | magic 即値を 1 bit 壊した複製 (値突合のみ、sha 検査は外す) | `engine magic = 1450406993, want 1450406992` (HIT) |
| N2 | x32 sizeof 期待を 0xA0 に誤る | `x32 sizeof 0x90 != 0xa0` (HIT) |
| N3 | 期待 magic を 1 ずらす | `engine magic @0x0 = 1450406992, want 1450406993` (HIT) |
| N4 | dispatcher の switch 上限 `cmp eax,0x18` → `0x19` (opcode 25 が範囲内に入る) | `opcode 25 (effProcessEvents) is inside the switch (bound 0x19)` (HIT) |
| N5 | effEditGetRect の子 vtable slot 期待を 5 に誤る | `route erect_child_slot = 4, want 5` (HIT) |
| N6 | effProcessEvents(25) が switch 内で処理される、と誤った期待 | `route opcode25_default = True, want False` (HIT) |

### 9.3 dispatcher の実測 (#894 受入 1・2)

`marshal.py` の `dispatch_facts` が検証する (RVA は ImageBase 0x10000000 からの相対)。

| 項目 | 実測 |
|---|---|
| dispatcher (vtable[+0x18] の転送先) | RVA 0x1300 の opcode switch。 上限 `cmp eax,0x18` (= 24)、`ja` 先 0x149C |
| opcode 25 (effProcessEvents) | 範囲外 → 既定分岐 0x149C (`mov eax,esi; ret 0x14`)。 VstEvents は読まれない |
| opcode 13 (effEditGetRect) | 分岐先 0x1406: `ecx=[ecx+8]` (editor) → `vtable[+4]` へ `ERect**` を渡す |
| ctor の `this+8` | 0 に初期化 (RVA 0x10E0 の `mov [edx+8],esi`、esi=0) |

- **ERect の実書込みは block22434 の外 (editor クラス)**。 受入 2 は「書込み箇所の特定」まで。 実測の書込み箇所は別 block の探索が要る。
- **VstEvents の読取箇所は、この dispatcher では見つからない**。 engine の events 読取は別経路 (process 系や別 block) にあると推定 (未確認)。 受入 1 は未達。
- 殻 (x64) 側の VstEvents / ERect の実物定義は、リポジトリ内 (`vst2_abi.h` を含む) に無い。 受入 3 は未達。

`marshal.py` (gate) は `[marshal] OK`・exit 0。 `marshal.py --nega` は `nega: 0/6 miss`・exit 0 (N1〜N6 すべて期待どおりの理由で FAIL)。 **実測値は下の §9.2 の表 (HEAD で再測定) を正とする**。

### 9.4 未解決 (起票先: #674)

§6 の未解決と同じ (VstEvents / ERect の engine 側読取、殻側の実物構造体、engine の store 値の実行確認)。 受入 1・2 は「dispatcher 内に読取・書込みが無い」ことまで確定し、実際の箇所は未特定。
- route 突合 (`ROUTE_EXPECT`: `bound`・`opcode25_default`・`erect_child_slot`) は現在の静的構造の**観測値**を守る回帰ガードである。 VstEvents の読取・ERect の書込みを証明するものではない。 gate の N5・N6 はこの突合の FAIL を検査する。
- `opcode25_default` は `PROCESS_EVENTS > bound` の**定数比較** (`marshal.py` の `route_facts`) であり、実バイナリの読取ではない。 既定分岐 (0x1000149c) の内容は `default_returns_zero` で別途検査する (`mov eax,esi; ret 0x14` を逆アセンブルで読んだ結果)。

### 9.5 events[] 読取の探索 (#894 受入 1 の追加調査・未達)

- 結論 1 行: 添字 `*4+8` の単独 `events[i]` 読取は確認できず、受入 1 は未達 (全文・再現手順は [REPORT_APPENDIX_894.md](REPORT_APPENDIX_894.md) §9.5)。

### 9.6 `mov r,[X+8]` → `[r+idx*4]` の形による events[] 候補の列挙 (#894 受入 1 の追加調査・未達)

- 結論 1 行: 候補 5 件はいずれも `events[i]` 読取と判定できず、受入 1 は未達のまま (表・再現・所要・鮮度証跡は [REPORT_APPENDIX_894.md](REPORT_APPENDIX_894.md) §9.6)。

## 10. emcc -c の再測定 (#674 受入 1 の入口, main `5a45be80`)

- 入力: `block22434_PE.bin` (sha256 `84b64c43…de724a9`、fl-win64 素材)。 root = export `main` (0x10007ca0)、`--arch ia32 --closure 2`。
- 再現: `python3 tools/ott/lift/x64c.py --pe <PE> --entries <roots=[0x10007ca0]> --out <dir> --closure 2 --arch ia32` → `emcc -c -O1 -w -I tools/ott/rt <dir>/ott_lifted.c`。
- lift: `functions 8, insns 301, unlifted callees 8, imports 0`。 unsup は x87 4 件 (`fld` 2・`fcomp` 1・`fnstsw` 1)、いずれも生成 C では `ott_unsup(...)` 呼び出しとして残る (実行時の扱いは未定義・未検証)。
- `emcc -c` (toolchain-emsdk 6.0.12): rc 0、object 5,836 B。 所要 0.15 s (lift wall)。
- 範囲: これは closure 2 (8 関数) のみ。 受入 1 の「.text 全体 (73,002 B)」は未達 (#1098)。 x87 の意味論は未実装 (#1099)。 gate C1〜C4 は本節では通していない。
- 注意: `0x10001300` (opcode dispatcher) を root にした場合の jump table 検証は `tools/ott/REPORT.md` §14 を参照。

## 11. .text の ia32 lift (#1098、測定 commit `fc2e70be`)

- 結論: `.text` の大部分を ia32 x64c で lift した (起点は export・関数ポインタ・code 即値、直接 call の再帰降下)。 「全体」は未達で、残りの未被覆域は子 #2814 (PLG-G2-22) へ。
- 未解決の `sahf` の AF 未反映と `fs:` の 0 埋め模型は silent divergence の候補で、#1223 へ送る (付録 §7)。
- 測定値・区間内訳・再現手順は [REPORT_APPENDIX_1098.md](REPORT_APPENDIX_1098.md) (数値の正本は付録 §2・§3)。
- 子 #2814 (PLG-G2-22): 未被覆域を (a)(b)(c) に分類し、(b) の区間を追加 lift した。 結論と測定値は [REPORT_APPENDIX_2814.md](REPORT_APPENDIX_2814.md) (§6)。 残りは子 #3546 (PLG-G2-28)。

## 12. x87 subset の ia32 lowering と差分試験 (#1099、測定 commit `ce0f0872`)

- 結論: x87 subset を ia32 で lower し、実 x87 との差分は主に 1 ulp。 x64 の出力は不変。 残りの x87 (超越関数ほか) は未 lower。
- 方式 `docs/DECISIONS.md` D28 (f80→f64)。 測定値・ネガコン・検算・未解決は [REPORT_APPENDIX_1099.md](REPORT_APPENDIX_1099.md) (正本)。

## 13. native vs wasm の差分試験 (#1223、測定は付録)

- 結論: leaf 関数 4 本 (`0x10001b40`・`0x10009300`・`0x1000d77e`・`0x10008630`) を native 機械語と wasm (ia32 lift) で実行し、eax と OBJ 領域 128 B を bit 単位で突合した。 全件一致。 ネガコン 1 bit で FAIL を確認。 export `main` (子 #3127)・x87 関数 (#2989) は未達。 実行時の間接 call・sahf の AF・fs: の TEB は未検証 (子 #3128)。
- 測定値・方式・制約・再現は [REPORT_APPENDIX_1223.md](REPORT_APPENDIX_1223.md) (正本)。
