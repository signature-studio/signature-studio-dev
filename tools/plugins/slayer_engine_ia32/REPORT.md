# tools/plugins/slayer_engine_ia32/REPORT.md — FL Slayer x86 engine (Slayer_Engine.dll) の ia32 decode 基準値 (#674 中間)

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/slayer_engine_ia32/` のみ / 親 #536 (結合方式は決定済み・PR #677 は未マージ。本件はその成果に依存しない独立計測) / 本 issue #674 の**中間成果** (受入条件 5 項目は 0/5 達成)
- 対象: block22434 (`extracted/block22434_PE.bin`, 179,512 B, sha256 `84b64c43…de724a9`) = FL Slayer の x86 engine
- 検証起点 commit: `bd8690c` (実装 commit。検証記録は §6)
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 $PY tools/plugins/slayer_engine_ia32/measure.py --dump` (gate) と `… measure.py --nega` (ネガコン)。 `$PY` は `uv venv $RUNNER_TEMP/venv_ia32 && uv pip install --python $RUNNER_TEMP/venv_ia32/bin/python capstone` (capstone 5.0.7)
- 既知類型との関係 (`docs/DEFECTS.md`): **該当なし**。 本件は decode の静的計測で lift 出力は作っていない (silent miscompile の観測対象外)。 新類型の候補は §7 の行案のみ (DEFECTS.md は未編集)

## 1. 結論 (先出し)

1. **PE は想定どおり**: machine 0x14c (i386)、`.text` VirtualSize 73,002 B (SizeOfRawData 73,728 B、file offset 0x1000、VA 0x1000、ImageBase 0x10000000)。 #536 の既知事実 (機械語 25,349 命令・x87 4,203・SIMD 0・間接 call 302) を**同じ数で再現**した。
2. **線形掃引 (CS_MODE_32) のデコード不能は 4 B (0.0055%)、最大連続 1 B**。 ia32 の命令デコード自体は capstone で全域ほぼ通る。
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
| 所要 / load average / 並列数 | 0.81 s (Python 内計測) / 1 分 load 0.01 → 0.01 / 1 (cpu 4) | `measure.py` の `[timing]` 行 (単一プロセス) |
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

## 4. x64c との対比

- **x64c の decode モード**: `CS_MODE_64` 固定 (1 箇所)。 ia32 の経路 (`CS_MODE_32`・32bit レジスタ幅・32bit アドレッシング) は無い → **「持たない」を確認**。
- **同じバイト列を 64bit で読んだ差分**: 573 命令 (2.26%) が mnemonic か命令長が一致しない。 上位: inc 247・dec 179・mov 111・push 16・pop 8・into 3・pushfd 2・pushal 2・arpl 1・popfd 1・les 1・aam 1・jecxz 1。 64bit では 0x40〜0x4F が REX 接頭辞になるため。 64bit 側で先頭位置が復号不能な命令は 34 件。
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

**C3 がランダム破壊を検出できない理由 (実測)**: 300 B の乱数で増える不能バイトは seed 0〜7 で +1〜+6 B (`N2` は 8 B = baseline 4 B + 4 B)。 x86-32 は乱数をほぼ復号してしまう。 そのため C3 は「大きく壊れた」(不能率 >0.1% = 73 B 超) だけを検出する粗い gate として残し、乱数破壊は C4 が検出する。 C4 の上限 15 は baseline の実測値 (推定: データ領域の誤復号。 未確認)。 乱数 300 B で件数は seed 674/0/1/2/3/4 の 6 本で 22/22/21/23/18/19 (全て 15 超 = FAIL)。 一時実験 (コミットしないスクリプト、同じ 6 seed) で 512 B にすると 21〜31 件 (全て 15 超)。 本スクリプトは 300 B 固定。

## 6. 検証の実行記録 / 範囲外 / 未解決

検証 (worktree 再現) は本 commit の後に `git worktree add --detach $RUNNER_TEMP/wt_verify HEAD` で展開し、同じ 2 コマンドを実行して §3・§5 の数値と一致するかを確認する。 結果は下表 (検証後の commit で記録)。

| 項目 | 値 |
|---|---|
| 検証起点 commit | `bd8690c` (`git worktree add --detach $RUNNER_TEMP/wt_verify HEAD` で展開・実行後に `worktree remove --force`) |
| 1 回目 (作業ツリー) | gate OK (4/4)・nega 0/3 miss・命令 25,349・不能 4 B・x87 4,203・priv 15 |
| worktree 再現 | 一致: `[measure] OK (4/4)`・`nega: 0/3 miss`・§3・§4 の全数値が作業ツリーの出力と同一 (`diff` で差分なし。 timing 行と入力パス行を除く) |
| 所要 (worktree, gate + nega 直列) | 3.23 s (壁時計)・gate 単独 0.82 s・load average 1 分 0.04 → 0.04・並列数 1 |
| `git status --porcelain=v1 -- tools/plugins/slayer_engine_ia32` | 空 (commit 後) |
| 20 MiB 超の blob | 無し (`find tools/plugins/slayer_engine_ia32 -type f -size +20M -not -path '*/work/*'` は 0 件) |

範囲外 (受入条件のうち今回やらなかったもの): **emcc -c 通過** (ia32 front-end 本体が無い) / **x87 方針と差分試験** (f80→f64 の bit 差分は未実測) / **marshal 表** (殻↔engine の 32/64bit 構造体) / **native vs wasm 差分試験** / **LoadLibrary shim**。 いずれも #674 の継続。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ia32 front-end 本体 (CS_MODE_32 の lift 経路、32bit レジスタ幅・アドレッシング・prefix 0x66) と `emcc -c` 通過 | 受入条件 1 | #674 (`Refs #674`) |
| x87 方針 (f80 の扱い、x87 4,203 命令・fldcw/fnstcw 50 件) と差分試験 | 受入条件 2 | #674 |
| marshal 表 (殻 x64 ↔ engine ILP32 の `AEffect`/`ERect`/`VstEvents`) | 受入条件 3 | #674 |
| native vs wasm の差分試験 (engine 単体・bit-exact) | 受入条件 4 | #674 |
| `LoadLibrary("Slayer_Engine.dll")` の shim (土台は #94) | 受入条件 5 | #674 |
| C4 の上限 15 と baseline 特権命令 15 件の正体 (データ領域の誤復号かどうか) | gate の意味 (推定) | #674 (逆アセンブル全文を見て確認) |
| 閾値 C3 (0.1%) と C4 (15) は実測 baseline 由来の**運用値**で、他の対象へは流用しない | 再利用時の誤判定 | 本 PR レビューで確認 |
| capstone 版差で件数が変わる可能性 (5.0.7 で固定して計測) | 数値の再現 | 本 REPORT §0 の版を記録 |

## 7. DEFECTS.md 新類型の行案 (編集はしない・PM 判断用)

| 案 ID | 区分 | 症状 (仮) | 検出 (仮) |
|---|---|---|---|
| D18 (案) | fe | **x64c に 32bit 機械語を渡すと、inc/dec (0x40〜0x4F) を REX と誤認して silent に別命令を生成する** (実測: 同 .text の 573 命令 / 2.26%) | 入力の PE machine が 0x14c なのに x64c (`CS_MODE_64`) を通す。 decode モードと PE machine の不一致を入口で fail-fast |
| D19 (案) | fe | **絶対 disp32 (ImageBase 基準 VA) の 32bit メモリ参照** (実測 1,270 件)。 wasm32 で VA→窓の写像が必要。 D11 と同型の VA リテラル問題 | `[disp32]` (base=0, index=0) 形の memory operand を数える |

いずれも推定。 D18 は「機械語と IR の取り違え」で D1〜D17 に該当する行が無い。 D19 は D11 の 32bit 版として統合できる可能性がある (推定)。

## 8. 成果物

| ファイル | 内容 |
|---|---|
| `measure.py` | 実測・gate C1〜C4 (`--dump` で `work/` に全命令の逆アセンブル、`--nega` でネガコン N1〜N3) |
| `REPORT.md` | 本ファイル |
| `work/` | gitignore 対象 (`tools/plugins/.gitignore`)。 逆アセンブル全文 (`block22434.ia32.disasm.txt`) と `nega/*.dll` |
