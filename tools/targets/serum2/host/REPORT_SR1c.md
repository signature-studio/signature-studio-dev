# REPORT 付録 — [SR-1c #256] controller ゲート (+0x10c / IEditController this+0xdc) の writer 探索と API 一覧化

- 日付: 2026-10-13 / 検証起点: `33fd25a2` (main) / 作業ブランチ: `256-sr1c-ctrl-gate`
- 既知類型との関係 (`docs/DEFECTS.md`): 該当なし (実 DLL の静的・動的観測。lift 前)
- 本付録は `REPORT.md` §3-3・§4 #3・§5-2 の追補。本体の結論は変えない。

## 0. 結論 (先出し)

1. **受入 #3 (呼出 Win32 API 一覧) は一覧化まで完了**。`WINEDEBUG=+relay` の実 host 実行 (licensed, 16 block) で relay 行 2,592,952。PE import 327 件のうち **110 件が呼出確認**、217 件は未呼出 (§2)。API 名の分類と「Serum2 が直接必要とする面」の判定は未了。
2. **+0x10c の writer 特定は未達**。静的に全 `.text` を走査すると、`+0x10c` への書込は 29 件。ゲート値の由来は有力候補 1 件 (copy ctor 0x18000d1b0, §3) まで絞れたが、実行時に値が 2 になる経路は確認していない。
3. **0x800010 受信観測は未達** (本付録の範囲で再確認はしていない。e2e 50/50 の再現で `REPORT.md` §3-6 の既存結果と一致、§4)。

## 1. 検証環境と実行

- 素材: `plugins-serum2` (`Install_Xfer_Serum2_2.1.5.exe` + pkg)。`7z x` で `Serum2.vst3/Contents/x86_64-win/Serum2.vst3` (19,236,864 B) を抽出。REPORT §0 の 19,236,864 B と一致。
- wine 9.0 (`apt install wine`)、`g++-mingw-w64-x86-64`、Python venv (`pefile` `capstone` `numpy` `zstandard`)。
- VST3 SDK ヘッダ: `setup_sdk.sh` (初回のみ取得)。
- e2e ベースライン: `bash tools/targets/serum2/host/e2e.sh` = **50/50 OK, 71 s**, 開始時 load average 1.17 (1 分値) / 終了時 0.51。NC1/NC2 とも期待どおり (exit=1, NG=1)。`REPORT.md` §3-6 の 66.94–66.98 s より遅いが、初回 run のため wine prefix・SDK 取得を含む。

## 2. 受入 #3: 呼出 Win32 API 一覧

- 取得: `WINEDEBUG=+relay wine64 vst3host.exe <authstub DLL> cases/licensed out_relay 16` (7 s、exit 0)。
- 突合: `host/sr1c_api_surface.py` (PE import テーブルと relay 呼出 `Call <dll>.<name>` を照合)。
- 結果: **import 327 件 / 呼出確認 110 件 / 未呼出 217 件** (`sr1c_api_surface.py` 出力)。

| DLL | import | 呼出確認 | 未呼出 |
|---|---:|---:|---:|
| kernel32.dll | 186 | 75 | 111 |
| user32.dll | 77 | 23 | 54 |
| ole32.dll | 12 | 0 | 12 |
| ws2_32.dll | 13 | 0 | 13 |
| gdi32.dll | 12 | 1 | 11 |
| shell32.dll | 8 | 1 | 7 |
| advapi32.dll | 8 | 8 | 0 |
| wininet / dwmapi / shlwapi / dwrite / d3d11 | 18 | 2 | 16 |

- 呼出回数の上位 (kernel32): `HeapFree` 188,988、`MultiByteToWideChar` 11,106、`GetLastError` 870、`CompareStringW` 726、`GetProcAddress` 489 ほか。`HeapFree` 等は wine 内部の経路を含む件数で、Serum2 の直接呼出数ではない。
- `Call ntdll.*` (heap・SRW lock 等 130 万行超) は PE import に無いため突合対象外。
- 未呼出の大半は user32 / gdi32 / dwmapi (GUI)・wininet / ws2_32 (ネット) で、headless 実行では到達しない想定 (**推定**。GUI open 未実施のため未確認)。
- 全行の一覧: `host/work/sr1c/api_surface.tsv` (gitignore, 再現は `sr1c_api_surface.py`)。

shim 候補 (SR-3/SR-4 入力) は呼出確認 110 件のうち kernel32 (メモリ・文字変換・ファイル I/O・同期) と advapi32 が中心。ole32 は呼出 0 件で、COM は PE import 外の経路 (CoCreate 相当の手動 vtable) と推定 (**推定**)。

## 3. +0x10c / +0xdc の writer 探索 (静的)

- 走査: `host/sr1c_writer_scan.py` (capstone。`.text` 全体の mov/add/sub/or/and/xor/inc/dec/bts 等で `[reg+disp]` を宛先とする命令)。
- 結果: `disp=0x10c` **29 件**、`disp=0xdc` **37 件** (下限。間接参照・多段の base 計算は拾えない)。
- 注意: 同じ `+0x10c`/`+0xdc` の組でも別構造体の同 offset が多数含まれる。関数 pdata で絞ると以下のとおり。

| 書込アドレス | 関数 | 内容 | 評価 |
|---|---|---|---|
| 0x18000d24b `mov [rsi+0x10c], eax` (eax = [rdi+0x30]) | copy ctor 0x18000d1b0 (size 179) | 元オブジェクトの config+0x30 を新オブジェクトの +0x10c へ写す | **有力候補 (med)**。REPORT §3-3 の「copy ctor 風」と一致 |
| 0x18009a369 `mov [rsi+0x10c], eax` (eax = [rsi+0x10c]+1) | 0x18009a3d0 (size 9,204) | +0x10c を inc する (カウンタ) | ゲート値 2 のままの観測と矛盾。ゲートの writer ではない可能性が高い (high) |
| 0x18009b01e / 0x18009b607 等 | 0x18009a3d0 | `dword [rsi+0x10c], 0` | リセット。値 2 の由来ではない |
| 0x1800c2b50 (setState) | ゲート読み (`cmp [this+0xdc],1`) | 読みのみ | — |

- 結論: 値 2 の由来は copy ctor 0x18000d1b0 が config+0x30 から写す経路が最有力。ただし実行時に config+0x30 が何の値かは未確認。
- 次の一手 (未実施): wine の gdb data breakpoint (`watch *(int*)(ctrl+0x10c)`) で、host 実行中の全書込 PC を列挙する。ctrl アドレスは `vst3host.cpp` の slot ログから取得可能。

## 4. 0x800010 と e2e の再現

- e2e 50/50 は `REPORT.md` §3-6 と一致 (本付録のベースライン)。ゲート `+0xdc` = 2 のまま、0x800010 は既定 host で未受信。
- 強制ゲート (`S2HOST_FORCE_GATE=1`) での 0x800010 観測は既存結果 (§3-6) を引用。本付録での追加実測は無し。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| +0x10c の実行時 writer 確定 (wine watchpoint 未実施) | 既定 host で +0xdc が 2 のまま。0x800010 経路の前提が未解明 | #256 (本 issue、次回 run) |
| 0x800010 の既定 host での受信 | 同上 | #256 |
| 呼出 API の shim 分類 (kernel32 同期・COM 系の詳細) | SR-3/SR-4 の入力が粗い | #256 (本付録 §2 の表を入力に) |
| 静的走査は下限 (間接参照・多段 base を拾えない) | writer の取りこぼし | #256 (watchpoint で補完) |

## 6. 再現

```sh
bash tools/targets/serum2/host/e2e.sh                       # 50/50, 71 s (初回)
python3 tools/targets/serum2/host/sr1c_writer_scan.py tools/targets/serum2/work/Serum2_win64.vst3 0x10c out.tsv
WINEDEBUG=+relay wine64 tools/targets/serum2/host/work/build/vst3host.exe <DLL> <case> <out> 16 <exe_extract> > relay.log 2>&1
python3 tools/targets/serum2/host/sr1c_api_surface.py tools/targets/serum2/work/Serum2_win64.vst3 relay.log api.tsv
```

- 前提: `wine` `g++-mingw-w64-x86-64` `plugins-serum2` 素材 (`7z x` で DLL を抽出), Python `pefile capstone`。
- 検証範囲外: 既定 host 以外の構成 (GUI open 後の状態)、gdb watchpoint、macOS 版。
