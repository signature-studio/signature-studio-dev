# REPORT — [SR-34 #2053] Serum 2 間接呼出 (vtable 0x180a24048 slot 12 / 0x180a24158 slot 5) の呼出元と 0x18004ffc0 の到達経路 (静的)

- 日付: 2026-10-14 / 親: #2000 (SR-30) / 前段: `REPORT_SR30.md` §4
- 範囲: 静的解析のみ。入力・sha256 は SR-30 と一致 (`501e7bb3…5283` / 19,236,864 B)。
- 測定 commit: `e471f856` (旧 `mem_re` で測定した最後の commit)。その後 `0a3077ae` で `mem_re` から rip 相対を除外したが、**修正後の件数は未測定** (下記 §0・§1-3 参照)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. vtable `0x180a24048` slot 12 (`+0x60`) の間接呼出元の列挙 | **未達**。`call [reg+0x60]` の件数は旧 regex で 311 件だったが、これは `rip` 相対 (`call [rip+0x60]`) を含む**誤計数**の疑いがある。`0x18098e73e` (in `0x18098e580`) 以外の確定はなし。rip 除外後の件数は**未測定** (素材 `plugins-serum2` が `$ARTIFACTS_DIR` に無いため)。vtable 由来の絞り込みは未完 (A) |
| 2. vtable `0x180a24158` slot 5 (`+0x28`) の間接呼出元の列挙 | **未達**。`call [reg+0x28]` は旧 regex で 708 件 (1 と同じ理由で rip 込みの疑い。rip 除外後は**未測定**)。同上 (A) |
| 3. `0x18004ffc0` の到達経路 | **未達**。直接 call 0 件・`.rdata` 8 byte 0 件・4 byte 表 2 件のみ。4 byte 表の参照元は未特定 (子 B) |
| 4. overlay_demo_version(_mini) と demo ダイアログ `0x1800501c0` の到達不能判定 | **未達**。3 が未完のため判定できない |
| 5. REPORT への追記 | 本ファイル |

## 1. 確定事項

### 1-1. 両 vtable の書込元は同一のコンストラクタ

| vtable | RTTI | 書込 (`lea rax, [rip+…]`) | 所属関数 |
|---|---|---|---|
| `0x180a24048` | `.?AVSerumDSP@@` | `0x18003ddf5` | `0x18003dcf0` |
| `0x180a24158` | `.?AVSerumDSP@@` | `0x18003de1c` | `0x18003dcf0` |

- `0x18003dcf0` の直接呼出元は 2 件: `0x180002ac2` (所属 `0x180002a80`) と `0x180002cb2` (所属 `0x180002c70`)。
- `0x180002a80` / `0x180002c70` は関数 local static の初期化を持つ getter 形 (`lea rcx,[rip+…]; call 0x1809a8ee0` の後に `0x13ada8` の確保)。両者の直接呼出元は 0 件。
- したがって SerumDSP の生成は、この getter を経由する間接経路で起きる。getter の呼出元 (間接) は未特定。

### 1-2. 0x18004ffc0 の参照

| 参照形式 | 結果 |
|---|---|
| `.text` の直接 call / jmp | 0 件 |
| `.text` の rip 相対 lea | 0 件 |
| `.rdata` の 8 byte (関数ポインタ) | 0 件 |
| `.rdata` の 4 byte (RVA) | 2 件: `0x180ff041c` `0x180ff0464` |

- `0x180ff0400` 付近の 4 byte 表は (key, handler RVA) の組に見える。`0x18004fad0` (vtable 0x180a24048 slot 12 の宛先) も同じ表に載る (`0x180ff0424`)。
- この表を指す rip 相対参照は `.text` に無い (`0x180ff0400`–`0x180ff0480` 範囲で 0 件)。表の base は別の形 (レジスタ加算等) で参照されると見られるが、未特定。
- ここから先は SR-30 と同様、静的 xref では閉じない。

### 1-3. 間接 call の件数 (参考値・絞り込み前)

| 形式 | 件数 (`.text` 全体) | 備考 |
|---|---|---|
| `call [reg+0x60]` | 311 (旧 regex, rip 込み) / 未測定 (rip 除外後) | `0x18098e73e` (in `0x18098e580`) ほか。vtable 0x180a24048 由来かは未確認 |
| `call [reg+0x28]` | 708 (旧 regex, rip 込み) / 未測定 (rip 除外後) | 同上 |
| `call [reg+disp]` 全体 | 27,743 (旧 regex, rip 込み) / 未測定 | 間接 call の母数 |

- 旧 regex `^qword ptr \[(r[a-z0-9]+)...` は `rip` に一致し、`call qword ptr [rip + 0x60]` を `call [reg+0x60]` として数えていた (capstone の出力形式で確認済み)。修正 `r(?!ip\b)[a-z0-9]+` は `[rip + 0x60]` を除外し、`[rax+0x60]`・`[r11+0x28]`・`[rsp+0x28]`・`[r8]` は一致することを合成バイト列で確認した (`0a3077ae`)。
- 修正後の件数は実バイナリが無いため未測定。311 / 708 は上限値の参考で、確定値として使わない。
- 件数は vtable を辿らないと、受入条件 1・2 の「オブジェクト種別」に結び付かない。SR-28 の検算 (40 件超) と同じ理由で、この段階では絞り込めない。

## 2. 再現手順

```sh
cd $S   # runner の _temp 配下の作業 dir (リポジトリ外)
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/vtable_dump.py Serum2_win64.vst3 0x180a24048 16
venv/bin/python $P/vtable_dump.py Serum2_win64.vst3 0x180a24158 8
venv/bin/python $P/indirect_calls.py Serum2_win64.vst3 0x180a24048 0x60
venv/bin/python $P/indirect_calls.py Serum2_win64.vst3 0x180a24158 0x28
```

- `$P` は本ディレクトリ (`tools/targets/serum2/gui`)。依存: `pefile` `capstone` `zstandard`。
- 実測 (n=1, 逐次): `vtable_dump.py` 0x180a24048 16 slot で real 2.436 s。`indirect_calls.py` (1 回) で real 6.170 s (load は実行直前の uptime 1 分平均で未計測)。

## 3. 残る作業 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (A) `call [reg+0x60]` / `call [reg+0x28]` (rip 除外後の件数を含む) のうち、SerumDSP object 由来のものの絞り込み (getter `0x180002a80` / `0x180002c70` の呼出元を含む) | 受入 1・2 | PM 判断 (未起票。解析の続きで子 issue は未起票) |
| (B) `.rdata` 4 byte 表 `0x180ff0400` の参照経路 (間接 base 参照の特定) と `0x18004ffc0` の到達 | 受入 3・4 | PM 判断 (未起票。同上) |
| (C) 実 VSTGUI 上の動的確認 | SR-30 受入 4 と同じ | `#68` 残作業 (GUI lift 時) |
