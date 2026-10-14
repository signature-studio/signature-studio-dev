# PY-67 (#2159): PY-66 の残り — 0x196eba0 の書込み元・0xffe370 の所属・0xec60ae/0x8ed012 の対象 (部分・未達)

親: #2078 (PY-66)・前段: `REPORT_PY66.md`・`REPORT_PY58.md`。既知類型との関係: 該当なし (lift 作業ではない)。

> 2 回目 (2026-10-14 run) の結果は **§4**。受入条件 1 は書込み元 (PE 解析箇所) まで特定し、書込み先の型は未確定。受入条件 2〜4 は 1 回目と同じく未達。

## 1 回目の結論

- 受入条件 1 (`0x196eba0` の書込み元) は**未達**。RIP 相対の store・`lea`・disp32 絶対参照の全てで 0 件。`.data` の slot (VA `0x15e3d38`) 経由の書込みは未確認 (下記「未完」)。
- 受入条件 2 (`0xffe370` の所属・呼出し元) は**未達**。`0xffe370` への直接 call/jmp は 0 件。`0xfe2e98` 表 (`.text` 内、`0xffe370`・`0xffa930` の 2 エントリ) を参照する RIP 相対・絶対参照も 0 件。表自体の参照元が見つからない。
- 受入条件 3 (`0xec60ae` の対象型) は**未達**。`0xec60ae` の対象は `[rbp+0x120]` 上 (`cmp [rax+0x7e0],1` の分岐内)。REPORT_PY58 と同じ判断で、chan 系フィールドは見当たらない。型は未確定。
- 受入条件 4 (`0x8ed012` の `[rbp+0x70]` が chan か) は**未達**。直前に `[rbp+0x70]` へ `+0x18`・`+0x6dc`・`+0x75c`・`+0x10`・`+0x20`・`+0x28` を書く。chan の判定材料は得られず、判断保留のまま。

## 測定条件

- 測定 commit: `3be69c80` (`tools/python/analysis/py67_indirect.py` 追加。解析コードはこの commit で初めて作った)。基点 `6444b186` (origin/main)。
- 素材: `fl-win64` の `block00031_PE.bin` を `tar --zstd -xf "$HOME/artifacts/fl-win64.tar.zst" -C tools/python/work/py67 --wildcards '*block00031_PE.bin'` で展開 (22,227,016 バイト)。`work/` は gitignore。
- 実測 (wall):
  - `py55_fieldwrites.py $P 0x794`: 0.114 秒 (`PY-58` の 20 件と一致)
  - `py58_context.py $P 0x1306dbf,0x130760f 0x60 0x40`: 命令境界は REPORT_PY66 と一致
  - `py67_indirect.py $P 0x196eba0`: 59.4 秒 (1 回・5,022,467 命令)
  - `py67_indirect.py $P 0x196eba0,0xffe370,0xffa930,0xec60ae,0x8ed012`: 60.0 秒 (1 回)
  - load average の測定は行っていない。

### 差分 0 の証跡

測定 commit `3be69c80` 以後にコードは変更していない。REPORT 追加のみ。

```
$ git diff 3be69c80 HEAD -- tools/python/analysis tools/python/src
(出力 0 行)
```

## 1. 解析結果

### 0x196eba0 (`.bss`)

- RIP 相対参照 64 件 (`0x1306db8`・`0x1306dc6`・…・`0x1310b06`)。全て load・比較。RIP 相対の store 0 件、`lea` 0 件。
- disp32 絶対参照 0 件。
- ファイル内の絶対値 `0x196eba0` の 8 バイト一致は `.data` の 1 箇所のみ (file offset `0x11e2738`、VA `0x15e3d38`)。ImageBase (`0x400000`) を足していない値のため、再配置済みポインタかどうかは未確定。
- `0x15e3d38` を RIP 相対で load する箇所は 40 件以上 (`0xd5c8f4`・`0xfc6ffb`…)。この slot の store 元は未確認 (下記「未完」)。

### 0xffe370 / 0xffa930 (`0xfe2e98` の表)

- `0xbe2298` (file offset) に `0xffe370`、`0xbe22a0` に `0xffa930` の 8 バイト絶対値。表を指す絶対値・RIP 相対参照は 0 件。
- `0xffe370` の命令: `mov dword [rcx+0x794], edx`・続けて `[rcx+0x9c]` への書込み、`[rcx+0x7ac]` の読込み。`rcx` が受ける対象は引数で、所属クラスは不明。
- 直接 call/jmp 0 件。間接呼出し (vtable 経由) の経路は未特定。

### 0xec60ae (`[rbp+0x120]` 上)

- 直前で `[rax+0x79c]` (dword) を書き、直後に `[rax+0x798]`・`[rax+0x7c4]`… を書く。REPORT_PY58 と一致。chan 系フィールド (`+0x714`・`+0x718`・`+0x739`) は範囲内に無い。

### 0x8ed012 ([rbp+0x70] 上)

- 直前の `call 0x511fe0` の戻り値を `[rcx+0x794]` に格納。`[rbp+0x70]` は同関数内で `+0x18`・`+0x6dc`・`+0x75c`・`+0x10`・`+0x20`・`+0x28`・`+0x77c` を書く。`+0x718` (chan 判定に使われるフィールド) の参照は無い。

## 未完

- `.data` slot `0x15e3d38` を load した直後のレジスタ経由 store の追跡は、Python ワンライナーがタイムアウト (300 秒) したため未完。`py67_indirect.py` への追加は未実施。
- `0x196eba0` の `.data` 一致が本当に再配置済みポインタかは未確定 (ImageBase を含まない値)。

## 2. 未確定

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x196eba0` の書込み元 (`.data` slot `0x15e3d38` 経由を含む) | chan 上の `+0x794` 書込みが確定しない | #2159 (PY-67 の続き) |
| `0xfe2e98` 表の参照元と `0xffe370` の所属・呼出し元 | `0xffe370` の書込み対象の型が確定しない | #2159 (PY-67 の続き) |
| `0xec60ae` の `[rbp+0x120]` の型 | chan 以外と確定できない | #2159 (PY-67 の続き) |
| `0x8ed012` の `[rbp+0x70]` が chan か | 判断保留 | #2159 (PY-67 の続き) |

## 3. 次の手順 (提案)

- `.data` slot `0x15e3d38` の load 直後の store を `py67_indirect.py` 内で 1 関数にまとめて追う (ワンライナーは使わない)。
- `0xfe2e98` の表が vtable かどうかを、`.rdata` / `.data` の vtable 候補 (絶対値の連続配置) で確認する。
- `0xec60ae`・`0x8ed012` の対象型は、所属関数の引数の由来 (`rbp+0x120`・`rbp+0x70` の代入元) を遡る。

## 4. 2 回目: slot `0x15e3d38` 経由の書込み元 (受入条件 1・部分達成)

### 結論

- `0x196eba0` (g) は `.bss` の 8 バイト変数で、値 P (= `*g`) が `0x1306dbf`・`0x130760f` の `[P+0x794]` 書込みの基底。1 回目の「`0x196eba0` が指すオブジェクト」の読みは正しい。
- g 自体への store は、手動の逆アセンブルで次の 2 件を確認した (追跡器は depth 1 で 0 件を返す。下記「取りこぼし」)。
  - `0x86a4e1: mov qword ptr [rax], rcx` (関数 `0x86a470`)。`rax` = `[rbp+0x80]` = 第 3 引数 r8 = `&g`。`rcx` = `[rbp+0x48]` = `0x86a4cf` の `call qword ptr [rax-0x30]` の戻り値。
  - 同関数の `0x86a504: mov qword ptr [rax], 0` (`rax` = `[rbp+0x80]` = `&g`) は g = 0 を書く。
- 「g への書込みは上の 2 件だけ」とは言えない。確認していないのは、スタック経由・呼出しをまたぐ経路・base+offset で作った `&g` への store。
- 呼出し経路: `0x11be449: mov rcx,[rip+0x147eb0]` (rcx = A = `*(0x1306300)`) → `0x11be450: mov rdx,[rip+0x4258e1]` (rdx = slot の中身 = `&g`) → `0x11be457: call 0x11c8950` → `0x11c896d: call 0x86a470`。
- `0x11c8950` は `0x11c8954`〜`0x11c895e` で `rax = *(*(0x15e30f8))` を読み、元の rcx・rdx を r8・r9 に退避する。`0x11c8964`〜`0x11c896a` で rcx = rax (X)、rdx = 元の rcx (A)、r8 = 元の rdx (&g) に組み直してから `0x86a470` を呼ぶ。`0x86a470` の引数対応は rcx = X = `*(*(0x15e30f8))`、rdx = A = `*(0x1306300)`、r8 = `&g`。`0x86a470` の rcx は呼出し元 `0x11be457` の rcx (= A) ではない。
- 未確定 (受入条件 1 の後半): P の型。`0x86a4cf` の間接呼出し先 `*(A-0x30)` の戻り値型が決まらない。A と X の由来は未追跡。

### 根拠 (実測)

- `&g` の出所の確認範囲: `0x196eba0` の 8 バイト・4 バイト絶対値一致は 1 件 (file offset `0x11e2738`・`.data`。slot の中身そのもの)、命令の即値一致 0 件、RIP 相対 `lea` 0 件。slot `0x15e3d38` のアドレス自体の絶対値一致は 0 件。base+offset の計算 (レジスタ + 定数で `&g` を作る経路) は未検査。よって「`&g` の出所は slot だけ」とは言えず、「確認範囲では slot 以外の出所は見つからなかった」が上限。
- slot の RIP 相対 load (`mov reg,[rip+slot]`) は 75 件。全件 load。
- 追跡 (`py67_slot.py`・window 400・call/ret で打ち切り):
  - `&g` (depth 1) からの mov store: 0 件 (取りこぼし。下記)。
  - `*g` (depth 2) からの mov store: 1 件 (`0x1037608: mov byte ptr [rcx+0x79c], al`)。
  - `&g` を引数 (rcx/rdx/r8/r9) に渡す direct call: 1 件 (`0x11be457`・rdx)。
- 取りこぼしの例 (ネガティブコントロール): 既知の g への store `0x86a4e1` は depth 1 で 0 件になる。理由は 2 つ。(a) 追跡器は `call` で値を破棄し、呼出し先 (`0x86a470`) の本体へ値を持ち込まない。`0x86a470` は `0x11be450` より低いアドレスで線形走査され、その時点で追跡中の値は無い。(b) `0x86a470` は r8 を `[rbp+0x80]` に退避し (`0x86a485`)、`0x86a4d6`・`0x86a4fd` で読み直すため、レジスタ追跡では `&g` の流れが途切れる。したがって depth 1 の 0 件は「g への書込み無し」の根拠にならない。
- `py67_callers.py` の結果: `0x86a470` の direct 呼出し元は 2 件 (`0x11c8950` 経由の `0x11c896d`、`0x10dc775`。後者は r8 = ローカル `[rbp+0x68]` で g ではない)。`0x11c8950` の direct 呼出し元は 23 件で、slot 由来の追跡で `&g` を渡すのは `0x11be457` だけ。

### 関数 `0x86a470` (g への書込み関数) の要点

- 引数 (`0x11c8950` 経由): rcx = X = `*(*(0x15e30f8))`、rdx = A = `*(0x1306300)`、r8 = `&g`。
- rcx (= X) の `+0x179` へ `al` を書く (`0x86a4b8`)。
- 第 2 引数 rdx (= A) を `[rbp+0x78]` に保存し、`0x86a4cf` で `call [A-0x30]` を呼ぶ。戻り値を `0x86a4e1` で `[&g]` に書く。
- 型の手がかり: 書いた直後 (`0x86a4ef`〜`0x86a4f6`) で P (= `[rbp+0x48]`) の vtable を読み、`call [vtable+0x78]` (第 2 引数 dl = 0xff、第 3 引数 r8 = X) を呼ぶ。P は仮想関数を持つオブジェクトで、この vtable スロットの実装を読むと P の型を絞れる (次の手順)。

### 他の P 書込み (参考・深さ 2)

- `P` を引数で受けて書く呼出し先: `0x1307ae0` (`mov dword ptr [rcx+0x788], edx`・`0x12d492f` ほか 2 件から呼出し)、`0x13105d0` (`mov dword ptr [rcx+0x7a8], eax`・`0x1037593` ほか 2 件)。P 上の同一フィールドかは未確認。

### 限界

- 追跡はレジスタの複写と `mov r,[r]` (深さ 2 まで) だけ。`call` で caller-saved レジスタを破棄するため、呼出しをまたぐ store は見ない。スタック (`[rbp+...]`) を経由する値も追わない。間接呼出し (`call [reg]`) の先は追わない。
- 線形走査。store 箇所 `0x86a4e1`・`0x86a504` は `py58_context.py` で命令境界を確認済み (`<==` 付きで出力)。
- 1 回目の追跡器 (本節の前段の版) は、レジスタの上書きで追跡を止めず、store 374 件の出力を出した。誤りだったため採用しない。

### 測定

- 測定 commit: `6cc14f57` (`py67_callers.py` 追加。解析コードの最後の変更)。`py67_slot.py` は `06c29d90` で追加。
- 検証 HEAD: `8aa87bae` (本 fix の前の HEAD。解析コードは測定 commit と同一)。
- 差分 (測定 commit から検証 HEAD まで・コード範囲 `tools/python/analysis`・`tools/python/src`): 0 行 (`git diff 6cc14f57 8aa87bae -- tools/python/analysis tools/python/src` の出力 0 行)。
- 実測 (wall・逐次・他プロセス並列なし・n=3。load は各 run 開始時の 1 分平均):
  - `py67_slot.py work/py67/extracted/block00031_PE.bin 0x15e3d38 0x196eba0 400`: 64.3 / 65.1 / 65.1 秒 (min–max 64.3–65.1 秒)。load 0.40 / 0.80 / 0.93。3 回の出力は `cmp` で同一。
  - `py67_callers.py ... 0x11c8950,0x86a470`: 32.4 / 32.1 / 31.9 秒 (min–max 31.9–32.4 秒)。load 0.96 / 0.98 / 0.99。3 回の出力は同一。
  - レビュワー側の 1 回 (同 commit・同引数): `py67_slot.py` 104.6 秒。本 run の最大 65.1 秒と約 1.6 倍の差があり、原因 (load・I/O 等) は未特定。所要時間はこの範囲で扱う。
- 再現: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C work/py67 --wildcards '*block00031_PE.bin'` → `cd tools/python` → 上記 2 コマンド。

### 未確定 (2 回目)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| P (= `*g`) の型: `0x86a4cf` の `call [A-0x30]` の戻り値型と、A = `*(0x1306300)` の由来 | `0x1306dbf`・`0x130760f` の `+0x794` の対象型が確定しない (受入条件 1 後半) | 子 issue #2501 (`[PY-71]`) |
| 受入条件 2〜4 (`0xffe370` の所属・`0xec60ae` の型・`0x8ed012` の chan 判定) | 未達のまま | 子 issue #2501 (`[PY-71]`) |
| g への書込みの網羅 (スタック経由・呼出しをまたぐ経路・base+offset で作った `&g`) | depth 1 の 0 件から「書込み無し」は言えない。書込み元の列挙は未了 | 親 #2159 への提案 (PM 判断) |

## 5. PY-71 (#2501): g の値 P の型・0xffe370 の所属 (追加解析)

§1 の「未完」の `.data` slot `0x15e3d38` は本節 5.1 で解決した (値は `&g`)。

| # | 受入条件 (#2501) | 結果 |
|---|---|---|
| 1 | `0x86a4cf` の `call [A-0x30]` の戻り値型と g の値 P の型 | **達成**。P は vptr `0x13063c8`・サイズ `0x840` のクラス (クラス名は TGraphEditorForm。RTTI に残る。`REPORT_PY71.md` §1・§2) |
| 2 | `0xffe370` の所属クラスと呼出し元 | 所属は**達成** (vptr `0xfe2cf8`・サイズ `0x8a8` のクラス、仮想スロット 52)。呼出し元は**未達** |
| 3 | `0xec60ae` の対象型 (chan 以外なら除外) | **未達** (`[rbp+0x120]` の出所を追えず) |
| 4 | `0x8ed012` の `[rbp+0x70]` が chan か | **未達** (判定材料を得られず) |

- 測定 commit: `ea3c0c27` (コードを変えた最後の commit)。`8360e1da` (main 取り込みの merge) からの変更は `py67_vtable.py` → `py71_vtable.py` の改名と `py71_callers.py` の docstring 1 行のみ。基点 `origin/main` (`5d33ba04`)。
- 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 バイト)。`tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'` で展開。`tools/**/work/` は使わない。
- 再現 (全コマンド共通。`tools/python` で実行):
  ```
  P=$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin
  T=0xfe2c80,0xfe2c88,0xfe2c90,0xfe2c98,0xfe2ca0,0xfe2ca8,0xfe2cb0,0xfe2cb8,0xfe2cc0,0xfe2cc8,0xfe2cd0,0xfe2cd8,0xfe2ce0,0xfe2ce8,0xfe2cf0,0xfe2cf8,0xfe2d00,0xfe2d08,0xfe2d10,0xfe2d18,0xfe2d20,0xfe2d28,0xfe2d30,0xfe2d38,0xfe2d40,0xfe2d48,0xfe2d50,0xfe2d58,0xfe2d60,0xfe2d68,0xfe2d70,0xfe2d78,0xfe2d80,0xfe2d88,0xfe2d90,0xfe2d98,0xfe2da0,0xfe2da8,0xfe2db0,0xfe2db8,0xfe2dc0,0xfe2dc8,0xfe2dd0,0xfe2dd8,0xfe2de0,0xfe2de8,0xfe2df0,0xfe2df8,0xfe2e00,0xfe2e08,0xfe2e10,0xfe2e18,0xfe2e20,0xfe2e28,0xfe2e30,0xfe2e38,0xfe2e40,0xfe2e48,0xfe2e50,0xfe2e58,0xfe2e60,0xfe2e68,0xfe2e70,0xfe2e78,0xfe2e80,0xfe2e88,0xfe2e90,0xfe2e98,0xfe2ea0
  ```

### 実測 (コミット済み `ea3c0c27`・件数のみ)

所要時間は受入判定に使わないため記録しない。出力の件数で再現を確かめた。

- `python3 analysis/py71_callers.py "$P" 0x86a470,0x11c8950 8`: 直接 call 25 件 (`0x11c8950` 23 件 + `0x86a470` 2 件)。出力 254 行。
- `python3 analysis/py71_slot.py "$P" 0x1306300,0x13a5c90,0x15e3d38 16 16`: 出力 178 行。
- `python3 analysis/py71_callers.py "$P" "$T" 0` (表スキャン・受入 2a/2b の根拠): `[imm]`・`[load]`・`STORE`・`[lea]` 0 件。絶対 8 バイト `0xfe2cf8` の格納 2 件 (VA `0xfe2c30`・`0xfe2ed8`)。
- `python3 analysis/py71_vtable.py "$P" 0x13063c8 0x714,0x718,0x739,0x794` と `... 0xfe2cf8 ...`: 5.4 の表の値。
- 差分 0 の証跡は本節末尾。

### 差分 0 の証跡 (§5)

```
$ git diff ea3c0c27 HEAD -- tools/python/analysis tools/python/src
(出力 0 行)
```

### ネガティブコントロール

- RIP 経路 (正の対照): `python3 analysis/py71_callers.py "$P" 0x1306300 0` → `[load]` 1 件 (`0x11be449`・`mov rcx, [rip+0x147eb0]`)。既知の RIP 参照は検出される。表スキャンの RIP 0 件はこの検出器で見た 0 件。
- 即値経路: `$RUNNER_TEMP/py71_nc/` (`$RUNNER_TEMP` 下・`tools/**/work/` は使わない) に PE の写しを作り、`0x4074ff` の `mov ecx, 0xa` (`b9 0a 00 00 00`) の即値を `0xfe2c88` (表の 1 要素) に書き換える (差分 3 バイト)。以下を `$RUNNER_TEMP/py71_nc/nc_patch.py` として保存する。
  ```python
  import struct, sys, pefile, capstone
  src, dst = sys.argv[1], sys.argv[2]
  pe = pefile.PE(src, fast_load=True)
  data = bytearray(open(src, "rb").read())
  text = next(s for s in pe.sections if s.Name.startswith(b".text"))
  base = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
  off0 = text.PointerToRawData
  md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
  off = 0
  while off < text.SizeOfRawData:
      ins = next(md.disasm(bytes(data[off0 + off:off0 + off + 15]), base + off, 1), None)
      if ins is None:
          off += 1
          continue
      if ins.mnemonic == "mov" and ins.size == 5 and ins.bytes[0] == 0xB9:
          data[off0 + off + 1:off0 + off + 5] = struct.pack("<I", 0xFE2C88)
          break
      off += ins.size
  open(dst, "wb").write(data)
  ```
  `python3 $RUNNER_TEMP/py71_nc/nc_patch.py "$P" "$RUNNER_TEMP/py71_nc/block00031_PE_nc.bin"` の後、`python3 analysis/py71_callers.py "$RUNNER_TEMP/py71_nc/block00031_PE_nc.bin" "$T" 0` を実行すると `[imm]` は 0 件 → 1 件 (`0x4074ff: mov ecx, 0xfe2c88  [imm]`)。元の PE に同じコマンドを実行すると `[imm]` は 0 件のまま。表スキャンの即値 0 件は、この検出器が即値経路で動くことを確かめた上での 0 件。

### 5.1 g ← P の経路 (静的)

1. 書込み: `0x86a4e1` の `mov [rax], rcx` (P を `*r8` へ)。`r8 = &g`。関数 `0x86a470` は `this=rcx`・`A=rdx`・`out=r8`。
2. 直接 call は 2 件。`0x10dc775` は `out=&[rbp+0x68]` (ローカル。g ではない)。もう 1 件は thunk `0x11c8950` (`0x11c896d`) で、`this=*(0x15e50f8)`・`A=rcx`・`out=rdx` に並べ替える。
3. thunk `0x11c8950` の呼出しは 23 件。g へ書くのは fn `0x11be0a0` (11 件の内) の `0x11be457`。その直前で `rcx=*(0x1306300)=A`、`rdx=*(0x15e3d38)=&g` (`0x11be450`)。
4. `A = *(0x1306300) = 0x13063c8` (`.text` の静的値)。`0x1306300` への RIP 相対の書込みは 0 件。
5. `call [A-0x30]`: `[0x1306398] = 0x40f960` (F)。F は `size = dword[this-0x80] = 0x840` を読み、`0x409410(size)` で確保、`0x40fb40(this, X)` で `*X = this` (vptr = A) を書いて `X` を返す。よって P = X (新規 `0x840` バイトのオブジェクト)。
6. `0x409410` の確保は `call [0x13a5c90]` の間接呼出しで、`0x13a5c90` は `.data` の静的値 `0x407a50`。`0x407a50` は先頭 `push rbp` で、同関数内 (int3 を挟まない線形逆アセンブル) の `0x407b06`・`0x407b15`・`0x407b28`・`0x407b56` に `f0 0f b0 23` (`lock cmpxchg byte ptr [rbx], ah`) がある。アロケータと見なす根拠はこの 4 件。

### 5.2 P の型 (vptr `0x13063c8`)

- `[A]=0x619200` (先頭スロット) で、vtable は 110 スロット。`0x86a4ef`〜`0x86a4f6` は `mov rax,[P]`・`mov rax,[rax]` (vptr) の後に `call [rax+0x78]` を呼ぶ (vtable スロット 15 = `0x80c850`)。
- `0x1306dbf` (`mov [rcx+0x794], rax`・`rcx=g`) と `0x130760f` (`mov [rax+0x794], r14`・`rax=g`) はどちらも P の `+0x794` へ書く。`0x794 < 0x840` で、対象型は vptr A のクラス。
- 訂正: 「クラス名は無い (stripped)」は誤り。クラス名は TGraphEditorForm で RTTI に残る (`REPORT_PY71.md` §1)。非 chan の判定は 5.4 の近似ではなく、この名前で行う。

### 5.3 0xffe370 の所属 (vptr `0xfe2cf8`)

- `V = 0xfe2cf8` (クラス名 TPublicChannel。親 TChannel。`REPORT_PY71.md` §1): `[V-0x80] = 0x8a8` (サイズ)、`[V-0x30] = 0x40f960` (A と同じ factory F)。`0xfe2c78..0xfe2cf0` (V-0x80..V-0x8) は V の 16 語のメタデータ (A の `A-0x80..A-0x8` と同じ形)。
- 仮想表 `0xfe2cf8..0xfe2ea0` は 54 スロット。`0xffe370` = スロット 52 (`+0x1a0`)、`0xffa930` = スロット 53。`0xffe370` は `[rcx+0x794]`・`[rcx+0x9c]` を書き、`[rcx+0x7ac]` を読む (V のメソッドとして整合)。
- 表を指す参照は、RIP 相対・即値の参照 0 件 (`0xfe2c80+8k` の 69 個全て。「ネガティブコントロール」節の検出器で確認)。絶対 8 バイト値 `0xfe2cf8` は 2 件 (`.text` の `0xfe2c30`・`0xfe2ed8` に格納)。同じスキャンで `0xfe2d00`・`0xfe2e00` にも絶対値の格納が 1 件ずつある (VA `0x94ab97`・`0x94aba7`)。隣接値は `0x15ec29800` と交互に並び、V の vtable 列とは別の構造。未調査。
- 未解決: 呼出し元 (V のインスタンスの `call [reg+0x1a0]`) と、V の vptr を書く箇所。`0xfe2c30`・`0xfe2ed8` の格納元も未追跡。

### 5.4 chan 判定の材料 (近似。vtable 単位・ベース不問の disp 一致)

| クラス (vptr) | サイズ | `+0x714` | `+0x718` | `+0x739` | `+0x794` |
|---|---|---|---|---|---|
| P: A `0x13063c8` | `0x840` | 1/110 | 1/110 | 0/110 | 0/110 |
| V `0xfe2cf8` | `0x8a8` | 0/54 | 0/54 | 0/54 | 12/54 |

(数値はスロット数。`py71_vtable.py`。chan の判定根拠 (`+0x714`・`+0x718`・`+0x739`) は両クラスとも弱く、chan とは確定できない。)

### 5.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0xec60ae` の `[rbp+0x120]` の出所 (`push rbp` を 0x3000 バイト内に見つけられず) | 受入条件 3 | #2501 (Refs で残す) |
| `0x8ed012` の `[rbp+0x70]` の出所 (関数先頭は未特定。直前の `push rbp` `0x8ea780` は `sub rsp,0x28` の別関数で、`[rbp+0x70]` の代入元ではない) | 受入条件 4 | #2501 |
| V (`0xfe2cf8`) のインスタンス生成箇所と、`call [reg+0x1a0]` の呼出し元 | 受入条件 2 (呼出し元) | #2501 |
| A (`0x13063c8`) の chan 判定 | クラス名 TGraphEditorForm で非 chan と確定 (`REPORT_PY71.md` §2)。解決済み | — |

### 名称

- `py67_vtable.py` は PR 初版の名前 (main に同名は無い)。他の 2 本 (`py71_callers.py`・`py71_slot.py`) と揃えて `py71_vtable.py` に改名した (`ea3c0c27`)。
