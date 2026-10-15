# REPORT_APPENDIX_4087: x87 leaf 12 本の異常終了の原因 (PLG-G2-44)

親 issue: #3715 (PLG-G2-31)。 本付録の対象 issue: #4087。 前段の一覧と判定: `REPORT_APPENDIX_4088.md` §3 (#4088)。

## 1. 結論

- native の SIGSEGV 6 本は、落ちる命令と読み先の実アドレスを `strace -i` の `si_addr` で確定した (§2)。
  3 本 (`10003fe0`・`100051f0`・`100085a0`) は `ecx` 基底 (OBJ 0x10F80000) からの読みが 16MB イメージ窓
  (0x10000000〜0x10FFFFFF) の外に出る。 3 本 (`100096d0`・`1000a95a`・`1000ba05`) は、引数のポインタに入る値が試験入力と合わず、読み先が不正になる。
- wasm の境界外読みは 6 本の全てで §3 に記録した。 落ちない 6 本 (`1000b6c1`・`1000b8a2`・`1000b8cd`・`1000b8cf`・`1000b8f7`・`1000b936`) は native・wasm ともに 16 行成功した。
- 空スタック読みの食い違い (`1000b8cd` 等) は #4088 付録 §3.1 のとおり。 本付録では扱わない。

## 2. native の SIGSEGV 6 本 (strace の si_addr)

測定: `strace -i` で 1 行入力 (`work/probe12_4087/one_<fn>.scen`) を実行。 入力は seed 4087 の乱数 (a0〜a4 は `uniform(-100, 100)` の float32)。 落ちた 16 行はすべて同じ結果だった (`probe12_4087_lines.py`)。

| 関数 | 落ちる命令 (VA) | si_addr (読み先) | 読みの由来 |
|---|---|---|---|
| `0x10003fe0` | `10003fe1` `fld dword ptr [ecx + 0x821700]` | `0x117a1700` | `ecx`(OBJ) + 0x821700。 イメージ窓の外 |
| `0x100051f0` | `10005211` `fcomp dword ptr [esi + 0xc]` | `0x114a0cf4` | `esi` = `ecx + 0x520ce8` (`100051ff`) + 0xc。 イメージ窓の外 |
| `0x100085a0` | `100085b1` `mov eax, [ecx + 0x520cc8]` | `0x114a0cc8` | `ecx` + 0x520cc8。 イメージ窓の外 |
| `0x100096d0` | `100096f4` `mov eax, [edx]` | `0x42a464e8` | `edx` = `[esp+0x14]` = a0 (入力の float 値 `42a464e8`)。 float をポインタとして読む |
| `0x1000a95a` | `1000a95e` `fld qword ptr [eax]` | `0x425f016a` | `eax` = `[esp+4]` = a0 (入力の float 値 `425f016a`)。 float をポインタとして読む |
| `0x1000ba05` | `1000ba05` `mov eax, [edx + 4]` | `0x00000004` | `edx` = 0。 `call_guest` が `edx` を 0 にして渡すため、基底が 0 になる |

- `10003fe0`・`100051f0`・`100085a0` は `ecx` 基底が OBJ 窓 (0x540 B) の外に出る。 読みの値は OBJ 窓の外の領域から来る。
- `100096d0`・`1000a95a` は、ポインタの位置に入る引数 a0 の float を、そのまま読み先として使っている。 試験の入力生成は引数の型 (ポインタか float か) を関数ごとに見ていない。
- `1000ba05` は、関数が `edx` を基底として読む。 試験ハーネスは `edx` に 0 を入れるため、null 近傍を読む。 引数の渡し方 (レジスタ引数) を試験が再現していない。

## 3. wasm 側の結果 (12 本)

測定: `probe12_4087.py` (関数ごとに 16 行を一括)・`probe12_4087_lines.py` (行単位)。 wasm は `node --liftoff-only`。 wasm の線形メモリは `INITIAL_MEMORY` 0x14000000・`GLOBAL_BASE` 0x11000000。

| 関数 | native (16 行) | wasm (16 行) | wasm の出力 |
|---|---|---|---|
| `0x10003fe0` | rc -11 | rc 0・16 行 | 成功。 読み先 (0x117a1700) は線形メモリ内なので trap しない |
| `0x100051f0` | rc -11 | rc 0・16 行 | 成功。 読み先 (0x114a0cf4) は線形メモリ内 |
| `0x100085a0` | rc -11 | rc 1・0 行 | `RuntimeError: memory access out of bounds` (全 16 行) |
| `0x100096d0` | rc -11 | rc 1・0 行 | `RuntimeError: memory access out of bounds` (全 16 行) |
| `0x1000a95a` | rc -11 | rc 1・0 行 | `RuntimeError: memory access out of bounds` (全 16 行) |
| `0x1000ba05` | rc -11 | rc 0・16 行 | 成功。 読み先 0x4 は線形メモリ内 |
| `0x1000b6c1` | rc 0・16 行 | rc 0・16 行 | 境界外なし |
| `0x1000b8a2` | rc 0・16 行 | rc 0・16 行 | 境界外なし |
| `0x1000b8cd` | rc 0・16 行 | rc 0・16 行 | 境界外なし (空スタックの食い違いは #4088 §3.1) |
| `0x1000b8cf` | rc 0・16 行 | rc 0・16 行 | 境界外なし |
| `0x1000b8f7` | rc 0・16 行 | rc 0・16 行 | 境界外なし |
| `0x1000b936` | rc 0・16 行 | rc 0・16 行 | 境界外なし |

- `10003fe0`・`100051f0`・`1000ba05` は、wasm は成功する。 読み先のアドレスが線形メモリ内にあり trap しないためだ。 ただし、読んだ値が native と一致するかは未測定。 native は落ちるので比較できない。 この 3 本の wasm 出力は差分試験の根拠にしない。
- `100085a0`・`100096d0`・`1000a95a` は wasm でも trap する。 wasm の trap 位置は未測定 (trap の VA を取っていない)。
- 落ちない 6 本は、native・wasm ともに 16 行成功した。 wasm の境界外読みは無い。

## 4. 検証

- 測定 commit: `46dcec20b` (main を取り込んだ merge。 本付録の試験は、この commit で再測定した)。 `46dcec20b` 以降の実行コードの差分は 0 (REPORT のみ変更)。
- 素材: `fl-win64` (`extracted/block22434_PE.bin`) を `$RUNNER_TEMP/fl-win64/` に、`toolchain-emsdk` を `$RUNNER_TEMP/emsdk-root/emsdk/` に展開 (`tar --zstd -xf`)。 emcc 6.0.12。
- 再現 (順に実行): `cd tools/plugins/slayer_engine_ia32 && python3 lift_text.py && python3 probe12_4087.py && python3 probe12_4087_lines.py`
  (`probe12_4087_lines.py` は `probe12_4087.py` の後に実行する。 引数に関数名を渡すと、その関数だけ行単位で実行する)。
- si_addr の再現 (§2): gdb は無いため `strace -i` を使う。 `work/probe12_4087/` で次を実行する。
  ```
  cd work/probe12_4087
  for f in fn_10003fe0 fn_100051f0 fn_100085a0 fn_100096d0 fn_1000a95a fn_1000ba05; do
    head -1 $f.scen > one_$f.scen
    timeout 60 strace -i -o st_$f.txt ./native_x87 ./image.bin one_$f.scen one_$f.out
    echo "$f $(grep -o 'si_addr=[^,}]*' st_$f.txt | head -1)"
  done
  ```
  6 本とも §2 の表と一致した (`0x117a1700`・`0x114a0cf4`・`0x114a0cc8`・`0x42a464e8`・`0x425f016a`・`0x4`)。 `one_<fn>.scen` は `<fn>.scen` の 1 行目。 各実行の終了は rc 139 (SIGSEGV)。 `work/` は gitignore 対象。
- 実測 (測定 commit `46dcec20b`・load1 は開始時 1.19): `lift_text.py` real 22.30 s (rc 0・load1 1.13 時点)・`probe12_4087.py` real 12.24 s (rc 0・load1 1.11 時点)。 12 本の rc と行数は §3 の表と一致。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ecx` 基底の 3 本 (`10003fe0`・`100051f0`・`100085a0`) の this の置き直し | native が落ちる。 this を用意すれば試験できる | #4147 (PLG-G2-50) |
| 引数ポインタを読む 3 本 (`100096d0`・`1000a95a`・`1000ba05`) の入力生成と引数の渡し方 | 乱数の float がポインタになる。 `edx` 基底も 0 で渡る。 入力を型ごとに作り直す必要 | #4147 (PLG-G2-50) |
| wasm が trap しない 3 本 (`10003fe0`・`100051f0`・`1000ba05`) の読んだ値の正しさ | native が落ちるため比較できない。 wasm の出力は差分の根拠にしない | #4147 (PLG-G2-50) |
