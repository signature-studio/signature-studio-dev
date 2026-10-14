# REPORT — [SR-30 #2000] Splice 選択関数の特定と demo ダイアログ到達性の間接経路確認 (静的)

- 日付: 2026-10-14 / 親: #1917 (SR-28 残件) / 前段: `gui/REPORT_SR28.md`
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は受入条件 4 (範囲外・GUI lift 時)。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3`。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-24・SR-28 と一致)。作業用 dir はリポジトリ外 (runner の `_temp` 配下)。
- 測定 commit: `5cb65195` (解析スクリプト 4 本を追加した commit。以降このディレクトリのコードは未変更)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. `0x180498198` / `0x180498734` の呼出元と、Splice テンプレート選択の state 条件 | **部分達成**。2 アドレスは関数先頭ではなく、`0x180498090` / `0x1804986d0` の内部の `lea` 位置と確定。直接の呼出元は `0x1800c9680` (1 件) と 10 件の小ラッパ。選択の state 条件は未特定 (子 A) |
| 2. 分岐が demo bit (+0x22792) に依存するかの静的確認 | **未達**。`+0x22792` の参照は `.text` 全体で 4 件あり、関数 `0x1800c2b50` (書込 2・読込 1) と `0x1800c6090` (読込 1) に限られる。Splice 系の上流 (`0x1800c9680` ほか) には無い。結線は未確認 (子 B) |
| 3. `0x18004fad0` / `0x1800506b0` の間接呼出元と `0x18004ffc0` の到達経路 | **未達**。間接呼出元は未特定。`0x18004ffc0` は直接呼出・`.rdata` 8 byte 参照とも 0 件 (子 C) |
| 4. 実 VSTGUI の動的確認 | 範囲外 (GUI lift 時、`#68` 残作業) |

### 0-1. 前段 (REPORT_SR28) の前提の訂正

- REPORT_SR28 §2-2 は「vtable head `0x180a86b88` は SpliceController」としている。**RTTI と照合すると誤り**。
  `0x180a86b88` の COL (signature 1) の TypeDescriptor は `.?AVSerumEditor@@`、COL offset は `0x78` (= `0x180498734` が `[rsi+0x78]` に格納する位置と一致)。
  SpliceController の RTTI の vtable は別 (`license/REPORT.md` 記載の `0x180ae31f8`。本 run では未検証)。
- したがって `0x180498198` / `0x180498734` は **SpliceController の生成ではなく、SerumEditor の sub-object (`+0x78`) を初期化するコード**。Splice 選択の上流として扱っていた前提は取り下げる。

## 1. 再現手順・実測 (本 run, runner 上)

```sh
# $S: リポジトリ外の作業用 dir (runner の _temp 配下)。$P: 本ディレクトリ
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/splice_chain.py Serum2_win64.vst3 0x180498090 0x1804986d0 0x1800c9680 0x1800c2b50 0x1800c6090 0x18004fad0 0x1800506b0 0x18004ffc0 0x1800501c0
venv/bin/python $P/splice_disasm.py Serum2_win64.vst3 0x1800c9680 8 4 0x180498090
venv/bin/python $P/splice_demo_bit.py Serum2_win64.vst3 0x1800c2b50 0x1800c6090 0x1800c9680 0x180498090 0x1804986d0 0x18004fad0 0x1800506b0
venv/bin/python $P/vtable_dump.py Serum2_win64.vst3 0x180a86b88 3
```

- 依存: `pefile` `capstone` `zstandard`。
- 入力 sha256 は SR-24・SR-28 と一致。
- 実測 (n=1, 逐次, load は実行直前の `uptime` 1 分平均): `splice_chain.py` (9 対象) real 10.113 s, load 0.21 (08:30)。`splice_demo_bit.py` (7 関数) は未計時 (出力のみ確認)。

## 2. Splice 生成経路 (受入条件 1)

### 2-1. 2 つの lea 位置の所属

| lea 位置 | 所属関数 (.pdata 先頭) | 書き込み先 |
|---|---|---|
| `0x180498198` | `0x180498090` (size 791) | `[rdi+0x78]` (`0x180498198`→`mov` `0x18049819f`) |
| `0x180498734` | `0x1804986d0` (size 694) | `[rsi+0x78]` (`0x180498734`→`mov` `0x18049873b`) |

### 2-2. 直接呼出元

| 関数 | 直接呼出元 (call rel32) | 備考 |
|---|---|---|
| `0x180498090` | `0x1800c995b` (所属 `0x1800c9680`, size 834) の 1 件 | 直前で `mov ecx, 0x3a0; call 0x1809a4b80` (0x3a0 byte の確保) → 確保領域を rcx に渡して呼ぶ。生成関数の形 |
| `0x1804986d0` | `0x1804a321b` `0x1804a3262` `0x1804a32a2` `0x1804a3352` `0x1804a33a2` `0x1804a33e5` `0x1804a3465` `0x1804a34a5` `0x1804a34e5` `0x1804a3525` の 10 件。所属は `0x1804a3210` `0x1804a3250` `0x1804a3290` `0x1804a3340` `0x1804a3390` `0x1804a33d0` `0x1804a3450` `0x1804a3490` `0x1804a34d0` `0x1804a3510` の 10 関数 | 各ラッパは `mov edi, edx` で flag を保持し、呼出後に `test edi,edi; je` する (役割は未検証) |

- 10 ラッパの vtable 位置 (`.rdata` 8 byte 参照): `0x180a869b8` `0x180a86af8` `0x180a86b08` `0x180a86b88` `0x180a86bf8` `0x180a86c18` `0x180a86c98` `0x180a86cb8` `0x180a86cd8` `0x180a86d18` の各 slot (`0x1804a3340` のみ `0x180a86b88` の slot 0)。`0x180a86bf8` の RTTI も `SerumEditor`。
- `0x1800c9680` の vtable 位置: `.rdata` `0x180a2bfe0` (slot 0)。COL の読みは失敗 (signature 不一致)。所属クラスは未確定。
- `0x180498090` の `.rdata` 4 byte 一致 (`0x181076fa0`) は偶然一致の可能性があり、根拠にしない。

### 2-3. 未達の理由

- `0x1800c9680` より上流 (そこが呼ばれる条件) と、`0x180a2bfe0` の所属クラスが未確定。ここに state → Splice 選択の分岐がある見込みだが、本 run では未追跡。

## 3. demo bit (+0x22792) との結線 (受入条件 2)

`.text` 全体で `[reg+0x22792]` を持つ命令は 4 件。

| 命令 | 所属関数 | 種類 |
|---|---|---|
| `0x1800c2cfe` `mov byte ptr [rsi+0x22792], al` | `0x1800c2b50` (size 1097) | 書込 |
| `0x1800c2d42` `mov byte ptr [rsi+0x22792], 1` | `0x1800c2b50` | 書込 |
| `0x1800c2d52` `test byte ptr [rsi+0x22792], 1` | `0x1800c2b50` | 読込 |
| `0x1800c6874` `cmp byte ptr [rsi+0x22792], 1` | `0x1800c6090` (size 2338) | 読込 |

- 上記 7 対象関数 (`0x180498090` `0x1804986d0` `0x1800c9680` `0x1804a3210` `0x1804a3340` `0x18004fad0` `0x1800506b0` ほか) の中に `+0x22792` の参照は**無い**。
- つまり Splice 生成経路 (2-2) は demo bit を直接読まない。demo bit との結線は、`0x1800c2b50` / `0x1800c6090` から Splice 生成への呼出関係を示せて初めて確定する。未確認 (子 B)。

## 4. demo ダイアログ `0x1800501c0` の到達性 (受入条件 3)

| 対象 | 直接呼出元 | `.rdata` 8 byte 参照 | 判定 |
|---|---|---|---|
| `0x18004fad0` (size 1263) | 0 件 | `0x180a240a8` (vtable 0x180a24048 の slot 12) | 直接呼出元は 0 件。本関数は `0x1800501c0` を 2 箇所 (`0x18004fc9c` `0x18004fdaf`) から直接呼ぶ |
| `0x1800506b0` (size 9340) | `0x18004feb0` (所属 `0x18004fad0`), `0x1800711f5` (所属 `0x1800709e0`) | `0x180a24180` (vtable 0x180a24158 の slot 5) | 直接呼出元 2 件 |
| `0x18004ffc0` (size 283) | **0 件** | **0 件** | 到達経路を示せず |
| `0x1800501c0` (demo ダイアログ) | 所属 `0x18004fad0` 2 件, `0x18004ffc0` 1 件, `0x1800506b0` 1 件, `0x180075d90` 1 件 | `0x180ff0518` (4 byte 一致・偶然の可能性) | 直接呼出元 5 件 |

- `0x18004fad0` は vtable `0x180a24048` の slot 12 (`.rdata` 0xa240a8) から参照される。この vtable を呼ぶ間接呼出 (`call [reg+0x60]`) の宛先は未解決 (REPORT_SR28 と同じ制約)。
- `0x1800506b0` は vtable `0x180a24158` の slot 5 から参照される (`call [reg+0x28]`)。同様に未解決。
- `0x18004ffc0` は直接・`.rdata` 8 byte のどちらからも参照が無い。間接経路 (4 byte 表の一致 `0x180ff041c` `0x180ff0464` は偶然の可能性あり) も未確定。
- 結論: patch 後に overlay_demo_version(_mini) と demo ダイアログ `0x1800501c0` が到達不能かは**示せていない**。`0x18004fad0` は vtable 経由で残る。

## 5. 残る作業 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (A) `0x1800c9680` の呼出元 (上流の state 条件) と vtable `0x180a2bfe0` の所属クラス | 受入 1 | #2054 (SR-32) |
| (B) `0x1800c2b50` / `0x1800c6090` (demo bit 読書) から Splice 生成への呼出関係 | 受入 2・3 (demo bit 結線) | #2055 (SR-33) |
| (C) vtable 0x180a24048 slot 12 (0x18004fad0) / 0x180a24158 slot 5 (0x1800506b0) の間接呼出元と、0x18004ffc0 の到達経路 | 受入 3 (間接経路) | #2053 (SR-34) |
| (D) 実 VSTGUI 上の動的確認 | 受入 4 | `#68` 残作業 (GUI lift 時) |
