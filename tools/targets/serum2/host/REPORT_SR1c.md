# REPORT 付録 — [SR-1c #256] controller ゲート (+0x10c / IEditController this+0xdc) の writer 探索と API 一覧化

- 日付: 2026-10-13 / 検証起点: `33fd25a2` (main) / 作業ブランチ: `256-sr1c-ctrl-gate`
- 検証 HEAD (本付録の全実測の実行 commit): **`23337740ca2e1a4ee9c0a4e8e7ab64acd0f1f1d6`** (完全 SHA は `git rev-parse` の値。下記 §1)。reviewer の再実行は `3552cabc` で行われ、e2e・relay・API 突合の判定は一致した。`23337740..3552cabc` の差分は本 REPORT・DOC_MAP・TSV のみで、script と e2e 本体は変更なし。
- 既知類型との関係 (`docs/DEFECTS.md`): 該当なし (実 DLL の静的・動的観測。lift 前)
- 本付録は `REPORT.md` §3-3・§4 #3・§5-2 の追補。本体の結論は変えない。

## 0. 結論 (先出し)

1. **受入 #3 (呼出 Win32 API 一覧) は件数と名前一覧まで**。PE import **327 件** (`sr1c_api_surface.py` の実出力) のうち **110 件が relay で呼出確認**、**217 件は未呼出**。名前一覧は `host/sr1c_api_surface.tsv` (commit 済み、§2)。「Serum2 が直接必要とする面」の判定は未了。
2. **+0x10c の writer 特定は未達**。静的に全 `.text` を走査すると、`+0x10c` への書込は 29 件。ゲート値の由来は有力候補 1 件 (copy ctor 0x18000d1b0, §3) まで絞れたが、実行時に値が 2 になる経路は確認していない。
3. **0x800010 受信観測は未達** (本付録の範囲で再確認はしていない。e2e 50/50 の再現で `REPORT.md` §3-6 の既存結果と一致、§4)。

## 1. 検証環境と実行

- 実行 commit: `23337740` (`git rev-parse HEAD` の完全 SHA: `23337740ca2e1a4ee9c0a4e8e7ab64acd0f1f1d6`)。下記の e2e・relay・静的走査・API 突合は **すべてこの commit の worktree** (`256-sr1c-ctrl-gate`) で 2026-10-13 に実行した。
- 素材: `plugins-serum2` (`$ARTIFACTS_DIR/plugins-serum2.tar.zst`、2,633,162,886 B)。展開物は `Install_Xfer_Serum2_2.1.5.exe` + `Xfer Serum2 v2.1.5.pkg`。
  - `7z x Install_Xfer_Serum2_2.1.5.exe -oexe` で Windows 版を取得。`exe/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3` = **19,236,864 B**、sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283`。REPORT §0 の 19,236,864 B と一致。
  - `.pkg` の VST3 Payload は macOS 版 (`Contents/MacOS/Serum2`) のため使わない。
- 配置: e2e.sh は `tools/targets/serum2/work/` 直下に `Serum2_win64.vst3` と `exe_extract/` を前提とする (`e2e.sh` の `S2=..`)。本 run では上の DLL と installer 展開物を `work/` にコピーして配置した。`PLUGINS_DIR` (WORKFLOW §11) 経由の自動配置は e2e.sh に無い。
- 環境: wine-9.0 (`wine64`, Ubuntu 9.0~repack-4build3)、`g++-mingw-w64-x86-64`、`host/setup_sdk.sh` で vst3sdk ヘッダ取得、Python venv (`pefile` 2024.8.26, `capstone`)。`license/authstub/mpatch.py` は `python3` 直呼びのため venv の python を PATH に通して実行。
- 負荷: 4 core。e2e 開始時 load average 0.71 (1 分値) → 終了時 0.20。

### 1-1. e2e `bash tools/targets/serum2/host/e2e.sh` (HEAD `23337740`)

- 実測: **50/50 OK, 72 s** (exit 0)。REPORT.md §3-6 の 66.94–66.98 s より遅い。
- NC1/NC2 は期待どおり (exit=1, NG=1)。

ログ末尾 (`e2e.sh` が出力するログ (`host/work/*.console` と e2e 結果) の末尾 10 行。run 外には残らないため本文に保存):

```
  [OK] patched+g1+lowver: demo bit 0・0x800010 無し (authstub が pv<2.0.20 経路も中和)
  [OK] patched+g1+demo_payload: demo bit 0・0x800010 無し (authstub がマーカ経路を中和)
  [OK] unpatched+g1+lowver: 保存 controller state にマーカ有り (bit 1 → getState が書込)
  [OK] unpatched+g1+lic_sent: 保存 controller state にマーカ無し
  [OK] patched+g1+lic_sent: 保存 controller state にマーカ無し (bit 1 でも N3 が書込を抑止)
  [OK] [KNOWN-DIVERGENCE] patched+g1+lic_sent: demo bit == 1 (IR pass は 0 の設計。#623)
  [OK] patched+licensed: restartComponent 自体は観測される

合計: 50/50 OK
== ネガティブコントロール ==
  NC1 (契約チェックを壊す): summarize exit=1, NG=1 (期待: exit!=0 かつ NG>=1)
  NC2 (gate==2 無影響チェックを壊す): summarize exit=1, NG=1 (期待: exit!=0 かつ NG>=1)
```

### 1-2. relay 取得

- `WINEDEBUG=+relay wine64 work/build/vst3host.exe <authstub DLL> work/cases/licensed <out> 16 <exe_extract>`
- 実測: **7 s, exit 0**, relay.log **2,596,923 行** (192,758,917 B)。`Call ` を含む行 1,298,416 (`LC_ALL=C grep -a`)。
- 参考: 旧版の 2,592,952 行は別 run の値 (取得条件が同一か未確認のため、本付録は今回の実測を採る)。reviewer の再実行では 2,592,798 行だった。relay の行数と per-API 呼出回数は run ごとに数十〜数百の揺れがあるため、判定に使うのは **呼出の有無** のみ (件数は目安)。

## 2. 受入 #3: 呼出 Win32 API 一覧

- 突合: `host/sr1c_api_surface.py` (PE import テーブルと relay 呼出 `Call <dll>.<name>` の完全一致)。
- 実出力 (そのまま): `import 327 件 / relay で呼出確認 110 件 / 未呼出 217 件`
- 全 327 行の一覧: **`host/sr1c_api_surface.tsv`** (commit 済み。列 = dll, name, imported, relay_calls, status)。TSV の再集計も 110 件で一致。

| DLL | import | 呼出確認 | 未呼出 |
|---|---:|---:|---:|
| kernel32.dll | 186 | 75 | 111 |
| user32.dll | 77 | 23 | 54 |
| ole32.dll | 12 | 0 | 12 |
| ws2_32.dll | 13 | 0 | 13 |
| gdi32.dll | 12 | 1 | 11 |
| shell32.dll | 8 | 1 | 7 |
| advapi32.dll | 8 | 8 | 0 |
| wininet / dwmapi / shlwapi / dwrite / d3d11 | 11 | 2 | 9 |
| **合計** | **327** | **110** | **217** |

- 行の内訳は PE 側 (pefile, `fast_load` + import directory) の実測で、重複を除いた named import。wininet 6 / dwmapi 2 / shlwapi 1 / dwrite 1 / d3d11 1。呼出確認は dwrite 1 / d3d11 1 (他 0)。
- 呼出回数の上位 (kernel32): `HeapFree` 188,988、`MultiByteToWideChar` 11,106、`GetLastError` 870、`CompareStringW` 726、`GetProcAddress` 489 ほか。`HeapFree` 等は wine 内部の経路を含む件数で、Serum2 の直接呼出数ではない。
- `Call ntdll.*` (heap・SRW lock 等) は PE import に無いため突合対象外。
- 未呼出の大半は user32 / gdi32 / dwmapi (GUI)・wininet / ws2_32 (ネット) で、headless 実行では到達しない想定 (**推定**。GUI open 未実施のため未確認)。
- 名前照合の限界: `sr1c_api_surface.py` は PE import 名と `Call <dll>.<name>` の完全一致で判定するため、`kernelbase` 経由の呼出 (kernel32 名での import を kernelbase が実装する経路) は拾えない。未呼出 217 件には、この経路で実際には呼ばれたものが含まれ得る (**未確認**)。

shim 候補 (SR-3/SR-4 入力) は呼出確認 110 件のうち kernel32 (メモリ・文字変換・ファイル I/O・同期) と advapi32 が中心。ole32 は呼出 0 件で、COM は PE import 外の経路 (CoCreate 相当の手動 vtable) と推定 (**推定**)。

## 3. +0x10c / +0xdc の writer 探索 (静的)

- 走査: `host/sr1c_writer_scan.py` (capstone。`.text` 全体の mov/add/sub/or/and/xor/inc/dec/bts 等で `[reg+disp]` を宛先とする命令)。
- 結果 (HEAD `23337740` で再実行): `disp=0x10c` **29 件**、`disp=0xdc` **37 件** (下限。間接参照・多段の base 計算は拾えない)。PR 記載と一致。
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

- e2e 50/50 は `REPORT.md` §3-6 と一致 (本付録のベースライン、§1-1)。ゲート `+0xdc` = 2 のまま、0x800010 は既定 host で未受信。
- 強制ゲート (`S2HOST_FORCE_GATE=1`) での 0x800010 観測は既存結果 (§3-6) を引用。本付録での追加実測は無し。

## 4-1. 実行時 writer の観測 (DR0 watch, #256 次回 run の前段)

- 追加: `vst3host.cpp` に `S2HOST_WATCH=1` の opt-in 計測 (既定は無変更)。controller 生成直後に `ctrl iface+0xdc` (= controller base+0x10c) へ x86 デバッグレジスタ DR0 の 4 byte 書込 watch を張り、VEH で書込 RIP と値を記録する。
- **観測範囲**: DR は**スレッド単位**。`armWatch` は `SetThreadContext(GetCurrentThread())` で**呼出スレッド (main) の DR0 のみ**を張る。他スレッドの書込は**未観測**。Serum2 は `CreateThread` を 25 回呼ぶ (`sr1c_api_surface.tsv`) ため、別スレッドからの書込の有無は本計測では判定できない。
- 全スレッド対象化の試行 (不採用): 既存スレッドの列挙 (`CreateToolhelp32Snapshot`) と kernel32!CreateThread の IAT 差替え (`CREATE_SUSPENDED` で DR0 を張ってから再開) を試作した。wine 9.0 では Toolhelp の `th32OwnerProcessID` が 0〜1 となり他プロセスのスレッドも混ざる (`own_pid=0`, 全 44 件)。plugin DLL の IAT hook も licensed / 既定 host 双方で 0 回しか呼ばれず (`CreateThread#` 0 件)、新規スレッドへの張りを確認できなかった。試作コードは捨てた (commit しない)。全スレッド化には別手段 (Windows 上の実機、または gdb の thread 全列挙) が要る。
- 実測 (`S2HOST_WATCH=1`, 既定 host, 4 blocks, HEAD `c9fbfc54` (`vst3host.cpp` は `35737960` と同一) で再実行):
  ```
  [watch] armed DR0=00007f87cf47d28c (controller iface+0xdc)
  [watch] hit#1 RIP=00006ffff8af1338 (base=00006ffff8a40000, Serum2_win64.vst3) value=2
  [gate] ctrl iface+0xdc 初期値=2 — 1 への遷移を最大 3 秒ポーリング
  [gate] 最終 +0xdc=2 (観測ヒストグラム 0:0 1:0 2:61 3:0)
  ```
  - 再現コマンド: `cd tools/targets/serum2/host && S2HOST_WATCH=1 wine64 work/build/vst3host.exe 'Z:…\work\Serum2_win64.vst3' - 'Z:…\host\work\out_watch_head' 4 'Z:…\work\exe_extract' > watch.console` (`PATH=/usr/lib/wine:$PATH WINEPREFIX=work/wineprefix WINEDEBUG=-all`、`Z:…` は repo の絶対パスを `\` 区切りにしたもの)。
  - hit は `[gate]` より前 (比較の根拠: 同一 console の行番号。`hit#1` が 36 行目、`[gate] ctrl iface+0xdc 初期値=2` が 103 行目)。`armed` (32 行) → `hit#1` (36 行) → `controller->initialize` の順。`initialize / setComponentHandler / createView` のどれの内側かは未分離。
  - 本 run の `hit` は 1 件。上記は同一 run のログ行をそのまま貼った。
- 書込命令: DLL 内 RVA **`0xb1332` `mov [rcx+0xfc], eax`** (trap 後の RIP は `0xb1338`)。書込値 `eax` は `0x180037600` の戻り値。関数は `0xacf70`〜`0xb142a`。
- 値 2 の意味 (逆アセンブル、未再現の読み): `0x180037600` は `queryInterface` を 2 回試し、A 成功なら 1、A 失敗かつ B 成功なら 0、両方失敗なら **2** を返す。実測の 2 は「両 QI 失敗」と読む。下記は `capstone` の出力 (`host/work/disasm_sr1c.txt`、commit 外)。分岐 `0x180037656 mov eax,2` が両失敗の経路。
  ```
  1800b132b: mov rcx, qword ptr [rbp + 0x7e8]
  1800b1332: mov dword ptr [rcx + 0xfc], eax      ; watch hit の書込 (RIP は次命令 0xb1338)
  180037600: push rbp ... call qword ptr [rax]    ; QI A (rdx = rip 相対計算で 0x1811be750 = RVA 0x11be750)
  180037633: test eax, eax ; je 0x180037662       ; A 成功 → return 1 経路
  180037637: ... call qword ptr [rax]             ; QI B
  180037654: test eax, eax ; je 0x180037678       ; B 成功 → return 0 経路
  180037656: mov eax, 2                           ; 両方失敗 → 2
  ```
- QI の IID (rdata の `0x11be750` / `0x11be8e8`) は未復号 (rdata 読出の範囲判定が未完)。どの interface を探しているかは未確定。
- 書込元 `0xacf70` の address は rdata `0xa2bf00` の qword に現れる (vtable 内の位置・所属 class は未確認。IEditController の `0xa2bf58` とは別位置)。直接 call の呼出元は無し。
- 結論: `armWatch` を呼んだスレッド上では、+0x10c は **controller 生成〜editor 準備の区間で、QI 結果から値 2 が格納される経路**を通る (main スレッドで 1 回のみ観測。他スレッドの書込は未観測)。REPORT §3-3 の「copy ctor 0x18000d1b0 が候補」との関係は未検証。0x800010 の観測 (= 1 への遷移) は、この QI 結果が変わる条件の解明が前提。
- 未検証: IID の内容 / 所属 class / `0xacf70` の呼出元 / 0x800010 の既定 host 受信。

- e2e (`S2HOST_WATCH` 未設定, 実行 commit **`c9fbfc54`** = `git rev-parse` `c9fbfc5473f98cc8902f6ee8daffca3e5446eb1f`、`vst3host.cpp` は `35737960` と同一): **50/50 OK, 67.93 s** (`bash tools/targets/serum2/host/e2e.sh`、exit 0)、NC1/NC2 期待どおり (exit=1, NG=1)、load 0.09 → 0.14。(同コードの `35737960` 時点の run は 71.40 s。)

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| +0x10c の実行時 writer 確定 (wine watchpoint 未実施) | 既定 host で +0xdc が 2 のまま。0x800010 経路の前提が未解明 | #256 (本 issue、次回 run) |
| 0x800010 の既定 host での受信 | 同上 | #256 |
| 未呼出 217 件の shim 分類 (GUI / ネット経路の到達可否と kernelbase 経由の呼出) | SR-3/SR-4 の入力 | #256 |
| 静的走査は下限 (間接参照・多段 base を拾えない) | writer の取りこぼし | #256 (watchpoint で補完) |

## 6. 再現

```sh
bash tools/targets/serum2/host/e2e.sh                       # 50/50, 72 s (HEAD 23337740)
python3 tools/targets/serum2/host/sr1c_writer_scan.py tools/targets/serum2/work/Serum2_win64.vst3 0x10c out.tsv
WINEDEBUG=+relay wine64 tools/targets/serum2/host/work/build/vst3host.exe <DLL> <case> <out> 16 <exe_extract> > relay.log 2>&1
python3 tools/targets/serum2/host/sr1c_api_surface.py tools/targets/serum2/work/Serum2_win64.vst3 relay.log api.tsv
```

- 前提: `wine64` `g++-mingw-w64-x86-64` `plugins-serum2` 素材 (installer を `7z x` して Windows 版 DLL を `work/Serum2_win64.vst3` に配置。`work/exe_extract/` に installer の展開物), Python `pefile capstone`。
- 検証範囲外: 既定 host 以外の構成 (GUI open 後の状態)、gdb watchpoint、macOS 版。
