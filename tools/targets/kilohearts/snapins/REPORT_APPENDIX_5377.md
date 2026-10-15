# KH-155 (#5377): GraphicEqDsp process 経路 (slot 14) の ctx / self / buf レイアウト (機械語から)

- 親: #4863 (KH-122) の分割 / 元 issue: #5377。素材 = `plugins-kilohearts` の Windows 側 `HeartCore.core_64` (`Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/*`)。
- 再現手順 (`tools/targets/kilohearts/` で実行。`work/` は gitignore):

```sh
unzip -q -o "$KH_SRC/Kilohearts Offline Installer.zip" -d work/win
unzip -q -o work/win/payload.dat index.json 'windows.zip/*' -d work/blobs
W=$(ls work/blobs/windows.zip/* | grep -v '/$' | head -1); unzip -q -o "$W" -d work/winpkg
python3 scripts/rtti_walk.py work/winpkg/HeartCore.core_64 work/rtti_vtables.json
python3 snapins/scripts/ksge_process_layout.py work/winpkg/HeartCore.core_64 work/rtti_vtables.json work/ksge_layout.txt
```

- 測定: `rtti_walk.py` 1.9 s。`ksge_process_layout.py` は objdump の集計のみ (1 s 未満)。

## 0. 結論

- 関数: `GraphicEqDsp` の vtable slot 14 = `0x18037d210` (RTTI `sizes[14]` = 4,413 B。base `0x180000000`)。REPORT_APPENDIX_781 §5 の `0x37d210` と同じ。
- 引数 (Win64 ABI): `rcx` = this (self) → `rdi`、`rdx` = ctx → `rbx`、`r8` = AudioBuffer* → `rsi`。
- 直接参照する基底は `rdi` (self)・`rbx` (ctx)・`rsi` (buf) の 3 つ。それ以外は、これらから読んだポインタ (`rax`・`rcx`・`r10`・`r14` 等) 経由。
- 参照された最大オフセット: self `+0x1654` (float)、ctx `+0x4db0` (ポインタ)、buf `+0x60` (byte)。ctx の全体サイズは本測定では決まらない (`+0x4db8` 以上の有無は未確認)。
- self の float 配列 2 本: `+0xe4` と `+0x160` (0x7c = 31×4 B 離れる)。ループ (`rdx` −434 → 0、step 14) が 31 回で両方を歩く。
- ctx の band テーブル: `[rbx+rdx*4+0x38c0]` と `[rbx+rdx*4+0x3f88]` (同じ添字、31 回)。添字の 1 step が 56 B 相当。
- 初期化・run の順序・slot 7 (`0x18037c980`) / slot 13 (`0x18037cbe0`) との関係は未確定 (§4)。

## 1. 基底レジスタ別オフセット (機械語の実測)

`ksge_process_layout.py` の集計 (`refs` = そのオフセットを `[base+disp]` で参照する命令数、`first` = 初出 VA)。意味づけは §2。

| 基底 | オフセット | refs | 初出 | 機械語上の使われ方 (実測) |
|---|---|--:|---|---|
| self (rdi) | +0x60 | 3 | 0x18037da79 | ポインタを読み、vector shim `0x18037e5e0` の第 1 引数に渡す |
| self | +0x70 / +0x74 / +0x80 / +0x84 | 1/3/1/3 | 0x18037dde6〜 | float。+0x74・+0x84 は読み書き |
| self | +0xa0 / +0xa4 / +0xa8 | 2/3/1 | 0x18037df03 / 0x18037de11 / 0x18037def0 | float 系 |
| self | +0xb0 | 1 | 0x18037ddf8 | |
| self | +0xcc / +0xd0 / +0xd4 / +0xdc | 2/3/1/1 | 0x18037de34〜 | float 系 |
| self | +0xe0 | 4 | 0x18037d2e8 | byte。`movzx` で読み、`mov [rdi+0xe0],r10b` で書く (dirty 蓄積) |
| self | +0xe1 | 1 | 0x18037d9ab | byte。`mov [rdi+0xe1],0` |
| self | +0xe4 | 1 | 0x18037d2da | float 配列 A の先頭 (`lea r8`)。31 要素 |
| self | +0x160 | 1 | 0x18037d2e1 | float 配列 B の先頭 (`lea r14`)。31 要素 (A の +0x7c) |
| self | +0x1560 | 2 | 0x18037d36f | サブオブジェクト (`lea r15`)。0x180389700 / 0x18038a510 の first 引数 |
| self | +0x15a0 | 4 | 0x18037d9b2 | int。ループ上限 (`cmp`・`movsxd`) |
| self | +0x15b0 | 1 | 0x18037da8b | サブオブジェクト (`lea r14`)。0x180c240c0 の first 引数 |
| self | +0x1e0 / +0x2d8 | 2/2 | 0x18037d376 / 0x18037d385 | サブオブジェクト (`lea`)。0x180389700 の第 2 引数・第 3 引数 |
| self | +0xda0 | 1 | 0x18037dac3 | 配列先頭 (`lea rax`) |
| self | +0x3d4 / +0x3d8 / +0x3dc / +0x3e0 / +0x3e4 / +0x3e8 | 3/2/2/3/3/2 | 0x18037dbd4〜 | float / byte 系。`mov qword [rdi+0x3d4],0` を含む。+0x3e8 は byte flag (`cmp byte ...,1`) |
| self | +0x3f0 | 1 | 0x18037daca | 配列先頭 (`lea rcx`) |
| self | +0x1650 / +0x1654 | 2/1 | 0x18037d2bb / 0x18037d2c3 | float。+0x1650 は `addss`・`movss` で更新 (clamp の結果を保存)。+0x1654 は係数 (`mulss`)。+0x1654 は `[rcx+0x1654]` で読む (rcx は `mov rdi,rcx` の後も entry 時の self のまま) ため、基底名 `rdi` だけを数える集計には出ない |
| self | +0x3d0 / +0xe1 (rcx 経由) | 2 / 2 | 0x18037d277 / 0x18037d281 | float / byte。`ucomiss xmm7,[rcx+0x3d0]` で前回値と比べ、`movss [rcx+0x3d0],xmm7` で更新。`[rcx+0xe1]` は dirty byte への `or`・`mov`。rcx = self (同じ理由で集計に出ない) |
| ctx (rbx) | +0x3188 | 1 | 0x18037df76 | ポインタ。`cmp dword [rax],1` |
| ctx | +0x31c0 | 2 | 0x18037da6c | ポインタ。`test byte [rax+4],1` で真なら vector shim を呼ぶ |
| ctx | +0x3f88 | 1 (+ 添字 31) | 0x18037dbbb | ポインタ。添字形 `[rbx+rdx*4+0x3f88]` でも 31 回読む (§3) |
| ctx | +0x38c0 (添字形) | 31 | 0x18037d300 | 添字形 `[rbx+rdx*4+0x38c0]`。ポインタを読む |
| ctx | +0x4d80 | 4 | 0x18037e198 | **int** (`mov eax,[rbx+0x4d80]`) |
| ctx | +0x4d88 | 5 | 0x18037e0bf | ポインタ。`movsxd rcx,[rcx+0x30]` で index を読む |
| ctx | +0x4d98 | 4 | 0x18037e180 | ポインタ |
| ctx | +0x4da8 | 1 | 0x18037e0c6 | ポインタ表。`lea rcx,[rcx+rcx*2]`・`mov r14,[rdx+rcx*8]` で 24 B 刻み |
| ctx | +0x4db0 | 4 | 0x18037e191 | ポインタ |
| buf (rsi) | +0x08 | 3 | 0x18037dea9 | ポインタ (`mov rcx,[rsi+8]`) |
| buf | +0x18 | 3 | 0x18037df86 | ポインタ (`mov rdx,[rsi+0x18]`) |
| buf | +0x28 | 13 | 0x18037da5b | int (frame 数)。最多 |
| buf | +0x60 | 1 | 0x18037e0ac | byte。`cmp byte [rsi+0x60],1` |

- 注: 集計は `[base+disp]` の直接形だけを数える。添字形 `[rbx+rdx*4+disp]` (band テーブル) は表の中で別に書いた。`[rdi+rax*2+0x430]` (0x18037da36) は出力への band 単位の書込 (宛先の根拠は未確定)。

## 2. 意味づけ (推定)

以下は機械語の使われ方からの推定で、native 実行による確認はしていない。

- ctx `+0x3f88` / `+0x3188` (ポインタ → 先頭 int が mode): `cmp [ptr],1` で分岐。Gain の `P.mode` (`scen_gain.h`) と同じ区別 (1 と 0/2) と推定。
- ctx `+0x31c0` (ポインタ → byte flag、bit 0): 真のときだけ `0x18037e5e0` (float ベクトル加算 `addps` の shim) を呼ぶ。Gain の変更通知 vector (`V`) とは別物と推定。
- ctx の band テーブル (`+0x38c0`・`+0x3f88` の添字形、31 band): 各 band の target (`[r10]`・`[rcx]`) を self の float 配列 A (`+0xe4`) と B (`+0x160`) と `ucomiss` で比べ、差があれば dirty byte `+0xe0` を立てる。A・B は band の前回値・現在値と推定。
- self `+0x1650`: `clamp(0, x, [0x1813a9da0])` の結果を保存。`+0x1654` は `mulss` の係数 (`[0x181536600]` と掛けて `divss` の分母)。
- buf `+0x28` (int): ループ上限として 13 箇所で使う。`+0x18`・`+0x08` (ポインタ) は sample 配列と推定。

## 3. 呼出先 (機械語の実測。引数の意味は推定)

| 呼出 site | 先 | 引数 (実測の範囲) | 推定 |
|---|---|---|---|
| 0x18037d380 / 0x18037d392 | 0x180389700 | rcx = self+0x1560, rdx = self+0x1e0 / +0x2d8, r8 = r14 | 2 本の float 配列を 1 つの状態へ畳む (band 処理) |
| 0x18037d98c / 0x18037d9a6 | 0x18038a510 | rcx = self+0x1560, rdx = `rsp+0x20` / `rsp+0x500`, r8 = self+0x1e0 / +0x2d8, xmm3 = 係数 | 同系統の float 更新 |
| 0x18037da67 | 0x180c23d90 | rcx = `rsp+0x20`, rdx = buf, r8d = frame 数 | buf の sample 取り込み (推定) |
| 0x18037da86 | 0x18037e5e0 | rcx = [self+0x60] (ポインタ), rdx = `rsp+0x20`, r8d = frame 数 | float ベクトル加算 shim (§2) |
| 0x18037daa1 | 0x180c240c0 | rcx = self+0x15b0, rdx = `rsp+0x20`, r8d = frame 数, xmm3 = 係数 | 出力混合 (推定) |
| 0x18037dbcf | 0x180fbc1f4 | 引数は未確認 | |
| 0x18037ddc5 / 0x18037ddd4 / 0x18037df8f | 0x180c242c0 / 0x180c23ec0 / 0x180c23d90 | buf 系 (未確認) | |
| 0x18037e12f / 0x18037e164 | 0x181384040 | memmove shim | |
| 0x18037e1c4 / 0x18037e224 / 0x18037e283 / 0x18037e2e3 | 0x18004cf20 | vector 再確保 callee (REPORT §5 と同じ) | |

- この関数の `call` は 17 箇所で、全て直接 `call`。間接 call (`call reg`・`call [mem]`) は無い。
- 中身は読んでいない callee: `0x18037e5e0` (引数形のみ)、`0x180c*` 系、`0x180fbc1f4`。

## 4. 未解決 (起票先は PR 本文の表)

- 各オフセットの型・単位・初期値は推定。native 実行で ctx/self を実際に埋めて trace していないため、scenario 入力に使う前に確定が要る。
- ctx `+0x3188`・`+0x31c0`・`+0x3f88`・band テーブル・`+0x4d80` 以降の初期化元 (どの関数が書くか) は未確認。process は読むだけなので、初期化は別経路 (slot 7 `0x18037c980` の prepare 系と推定) にある。slot 7・13 の native 呼出確認は未了 (KH-130 #4895)。
- 呼出先 `0x180c*`・`0x180fbc1f4`・`0x18037e5e0` の中身と引数の確定は本付録の範囲外。
- scenario 入力への反映 (`harness/` の `scen_*.h` 追加) は本付録の範囲外。親 #4863 の受入 1 で行う。
