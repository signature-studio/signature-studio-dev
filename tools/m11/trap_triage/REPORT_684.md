# #684 単発 OOB 4 unit (95 / 275 / 477 / 895) の個別原因

親: #596 (PR #675)。対象: `tools/m11/trap_triage/REPORT.md` §8.2 の OOB 13 件のうち単発の 4 unit。
検証起点: `6c1a34f` (本 PR の最終コード HEAD。以降は docs のみ)。素材: work-m11 (`tools/m11/work` の複製) + fl-win64 (`$RUNNER_TEMP/fl-win64`)。

既知類型との関係 (`docs/DEFECTS.md`): **477 は D11 の変種と判定** (10 進 `inttoptr` 形の VA 未変換)。95 / 275 / 895 は未判定。
`tools/icall/REPORT.md` §4 の D 体系とは対応させていない。

## 0. 結論

1. **測定の訂正 (重要)**: `REPORT.md` §8.2 の「OOB 最上位 frame」は **すべて 1 段上の caller** だった。
   `survey_units.mjs` が `frames` を `slice(1)` で切り、trap 直上の wasm frame を落としていたため (§1)。
   この訂正で §8.3 の「`414ad0` は OOB 最上位 frame に現れない」は**誤り** (訂正後は 4 unit が `414ad0` を最上位とする)。
2. **477 は原因を特定** (実測): `function_abfd60` の 10 進 `inttoptr i64 22953608` が VA 0x15E3E88 のまま LVA 変換されていない。
   この 1 箇所だけ LVA (18759304) に直すと unit 477 だけが oob → ok (他 941 unit の遷移 0)。元に戻すと oob に戻る (§4-1)。
   ok になったことは意味の正しさ (G の中身 `0x11F94B0` も VA 形式で、LVA 変換が要る可能性) の証明ではない。
3. **275 / 95 / 895 は最上位命令まで特定、原因は未特定**。275 は this 引数の不正 (推定: Win32 stub の返り値との関係、未検証)。
4. D11 変種の DEFECTS 行案は §3。DEFECTS.md 本体は PM 判断 (WORKFLOW §5) のため未編集。

## 1. survey の frame 訂正 (`survey_units.mjs`、修正は `be5c84d`)

- 原因: `RuntimeError: memory access out of bounds` の行は `/wasm-function|at /` に一致しないため、`slice(1)` が**先頭の実 frame** を落とした。
  生 stack (`SV_RAW=1` で出力) と突合すると、旧 `frames[0]` は常に生 stack の 2 行目だった。
- 修正: `filter(/^\s*at /).slice(0, 30)` (集計は不変: ok 828 / halt0 54 / miss 46 / oob 13 / noproc 1)。
- ネガコン (旧版の出力 `head684_before_fix.json` と新版の比較): **OOB 13 件すべて旧 `frames[0]` == 新 `frames[1]`**。

| unit | VA | 旧 (§8.2) 最上位 | 新 最上位 (trap 直上) | 生 stack の先頭 (wasm index, offset) |
|--:|---|---|---|---|
| 95 | 0x1d2680 | `536da0` | **`47ad70`** | [3067] 0x18f8df |
| 149 | 0x264260 | `414bb0` | **`414ad0`** | [733] 0xbc57d |
| 158 | 0x26d1a0 | `414bb0` | **`414ad0`** | [733] 0xbc57d |
| 275 | 0x40e170 | `80e040` | **`864fe0`** | [388] 0x935bf |
| 280 | 0x416010 | `414bb0` | **`414ad0`** | [733] 0xbc57d |
| 291 | 0x432660 | `4f9ff0` | **`4f9f40`** | [3134] 0x193d5b |
| 296 | 0x446130 | `4f9ff0` | **`4f9f40`** | [3134] 0x193d5b |
| 304 | 0x483140 | `4f9ff0` | **`4f9f40`** | [3134] 0x193ccf |
| 477 | 0x6bfd60 | `904190` | **`903d20`** | [5373] 0x2775c0 |
| 555 | 0x7f2500 | `4f9ff0` | **`4f9f40`** | [3134] 0x193ccf |
| 659 | 0x8eaa30 | `414bb0` | **`414ad0`** | [733] 0xbc57d |
| 895 | 0xeddfe0 | `40ffe0` | **`40ff70`** | [2001] 0x149cb9 |
| 923 | 0xf6c660 | `4f9ff0` | **`4f9f40`** | [3134] 0x193ccf |

## 2. 最上位命令と caller 連鎖 (wasm バイトオフセット → 命令、`trap_triage/oob_insn.py`)

命令境界の検証: 4 unit の offset はすべて命令境界に一致。境界でないオフセット `0x18f8e0` は `not an instruction boundary` で失敗 (ネガコン)。

- **95** `function_47ad70` @ `0x18f8df` = `i64.load offset=0`。直前は `local.get 5; i64.const 3; 0x86 (i64.shl); local.get 0; 0x7c (i64.add); 0xa7 (i32.wrap_i64)` (`oob_insn.py` の実出力)。`i32.wrap_i64` は `i64.add` の後・`i64.load offset=0` の前にある。
  ループ内で `*(arg0 + (v << 3))` を読む (v = record の `+8` の値)。caller: `536da0` ← `4fe150` ← `5d2680` (unit 本体)。
  この unit の直前に GDI 系 stub (GetDC / GetDeviceCaps / CreatePalette / GetStockObject / LoadIconW / MulDiv) が呼ばれる。
- **275** `function_864fe0` @ `0x935bf` = `i64.load offset=0` (`this+8` = `GetMonitorInfoW` の hMonitor)。`this` (arg1) が不正。
  caller: `80e040` のループ (項目を `function_8657b0` で取得し 864fe0 へ) ← `80e140` ← `80e170` (unit 本体)。
  unit 内で `GetMonitorInfoW` が 20 回、`EnumDisplayMonitors` が 1 回呼ばれる。両 stub は常に 0 を返し、コールバックを呼ばない (`tools/m11/work/m11_winstubs.c`)。
- **477** `function_903d20` @ `0x2775c0` = `i64.load offset=0` = `*(p-8)` (p = `[arg1+8]`、非 0)。`arg1+8` の読みは成功している。
  役割は推定 (動的配列の長さ/容量ヘッダ)。caller: `904190` (`[arg1+16] < [arg1+32]` が偽のとき 903d20) ← `abfd60` (unit 本体)。
- **895** `function_40ff70` @ `0x149cb9` = `i64.load offset=0` = `*(p-144)`。`p = [p]` を繰り返すリスト走査。
  caller: `40ffe0` ← `60a270` ← `e3ef60` ← `12d0f80` ← `12d0c10` ← `12d0cc0` ← `12ddfe0` (unit 本体)。

## 3. 477 の原因 (実測 + 1 箇所の実験)

実測 (`trap_triage/oob684_probe.mjs`、survey と同順で unit を実行):
- unit 477 の直前、wasm アドレス **22953608 (`0x15E3E88`) の値は 0**。
- 同じ直前で `[0] = 0x9daa01` (`watch` モードで unit 15, 17, 22, 35, 37, 95, 135, 220, 232, 233, 426, 427 が address 0 を書換え)。
  つまり `abfd60` の `this = [[G]] = [0]` は、先行 unit が 0 番地 (NULL 相当) に書いた残骸を読んでいる。

IR (`work/boot_final3.ll`): `function_abfd60` 内の `%ce0n11_function_abfd60 = inttoptr i64 22953608 to ptr` が唯一の参照。
- PE 解析 (pefile): VA 0x15E3E88 は RVA 0x11E3E88 = `.data` 内 (`.data` RVA 0xFA5000–0x11E5008)。LVA は RVA + LB (LB=0) なので、**定数は VA のまま**。
- 10 進 `inttoptr` 定数の全数: 4449 件中 **4364 件が VA 範囲 (0x400000–0x1AC0000)**。REPORT.md §6-2 の 4364 と一致 (HEAD `6c1a34f` で再確認)。

**実験** (`work/` の複製のみ、コミットなし): `abfd60` の 22953608 だけを 18759304 (= 0x11E3E88 = LVA) に置換して再 build → survey。
| 構成 | ok | halt0 | miss | oob | 遷移 (HEAD 比) |
|---|--:|--:|--:|--:|---|
| HEAD `6c1a34f` | 828 | 54 | 46 | 13 | — |
| **1 箇所 LVA 化** | **829** | 54 | 46 | 12 | **477: oob → ok (他 941 unit の遷移 0)** |
| ネガコン (元 IR で再 build) | 828 | 54 | 46 | 13 | 遷移 0 (477 は再び oob) |

判定: **477 の OOB は D11 の変種 (10 進 `inttoptr` 形の VA 未変換) で説明できる** (実測・1 箇所の実験で確認、ネガコン済み)。
限界: ok になった先の値 (`[G]` = `0x11F94B0`) も VA 形式に見え、LVA 変換が必要かもしれない。意味の正しさは未検証。
全数修正 (`M11_M2P=1`) は REPORT.md §6-2 で unit 503 のハングが出ているため、本件では採らない。

## 4. 275 / 95 / 895 (未特定)

- 275: this 不正の出所は未特定。`80e040` の項目取得 (`function_8657b0`) が返す値を実測していない。
  stub (GetMonitorInfoW / EnumDisplayMonitors が 0 を返す) が項目の作り方に影響する**推定** (未検証)。
  次の一手: 80e040 直前の項目列の実測、または monitor enumeration の stub を仮に実装して差を測る (ネガコン付き)。
- 95: `47ad70` の index `v` の出所 (record `+8`) と `arg0` の由来は未確認。caller の GDI stub 系との関係は**推定**。
- 895: リスト先頭 (`40ffe0` の引数) の出所は未確認。`p-144` が指す構造体の定義は未特定。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 477 の D11 変種の全数修正 (10 進 VA 4364 件の扱い、ok 後の値の正しさ) | 単発 OOB 1 件・全体の OOB 原因 | PM 判断: 親 #596 へのコメント or 新規子チケット (DEFECTS 行の採番を含む) |
| 275: this 不正の出所 (monitor 列挙の stub 仮説) | 単発 OOB 1 件 | 新規子チケット案 (親 #596 配下、M11) |
| 95: index と record の出所 | 単発 OOB 1 件 | 同上 (親 #596 にコメント) |
| 895: リスト先頭の出所 | 単発 OOB 1 件 | 同上 (親 #596 にコメント) |
| `survey_units.mjs` の旧 frame を前提にした #419 §8.2 / §8.3 の記述 | §8.3 (`414ad0` と #307 の関係) の結論が逆転 | 本 PR で訂正注記 (`REPORT.md` §8.2 直下)。#307 との関係は再検証が必要 (未実施) |

## 6. DEFECTS.md 行案 (PM 判断。本 PR では未編集)

| 型 | 出所 | 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|
| D11 (M11 変種) | ours | 10 進 `inttoptr i64 N to ptr` の N が PE の絶対 VA のまま残り、wasm 上で別アドレスを読んで OOB | M2 pass が 16 進 `inttoptr` のみ remap し、10 進形 4449 件中 4364 件が VA 範囲に残る (既定 OFF の `M11_M2P=1` で全数対応) | unit 477 (`function_abfd60`, N=22953608): 1 箇所 LVA 化で oob → ok、ネガコン oob | `inttoptr i64 N` で N が [0x400000, 0x1AC0000) (機械的に検出可) | 10 進形も VA→LVA remap (ハング対策の仕分けが要る) |

## 7. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64          # PE: $FL_WIN64_DIR/extracted/block00031_PE.bin
cd tools/m11
mkdir -p work/trap_triage
uv run --with capstone --with pefile bash m11_e2e.sh      # e2e (30.5〜30.7 s)
SV_RAW=1 node trap_triage/survey_units.mjs work/trap_triage/head.json   # survey (12.4〜12.6 s) + 生 frame
python3 trap_triage/oob_insn.py work/m11_boot.cjs.wasm 3067 18f8df 3   # 命令逆引き (wasm index, offset)
node trap_triage/oob684_probe.mjs 477 0,22953608                          # unit 477 直前の値
node trap_triage/oob684_probe.mjs 477 0 watch                             # address 0 の書込み元 unit
```

`work-m11` 素材には `work/trap_triage/` が含まれず (`tar --zstd -tf` の grep で 0 件)、`survey_units.mjs` も出力先を作らないため、survey の前に `mkdir -p` が要る。

## 8. 検証結果 (実測、HEAD `6c1a34f`)

- e2e `m11_e2e.sh` n=3: 30.5 / 30.6 / 30.7 s、load 0.45 / 0.67 / 0.80 (1 並列)。3 回とも reached_stage 4/6、units 22/942、survey ok 864 / trap 31 (oom 1) / miss 46 / noproc 1 / clobber 0。
  §8.2 (c) の e2e 値 (864 / 31 / 46 / 1) と一致。
- survey `survey_units.mjs` n=3: 12.6 / 12.4 / 12.6 s、load 0.89 / 0.91 / 1.00。3 回とも ok 828 / halt0 54 / miss 46 / oob 13 / noproc 1。
- 旧 frame との差: 13/13 (§1)。decoder の境界ネガコン (§2)。477 の 1 箇所実験 + ネガコン (§3)。
- 修正の影響範囲: `survey_units.mjs` の `frames` (OOB と abort のみ影響)。`annotate.py` の最上位 frame 集計は新しい値になる。

## 9. 変更点と範囲

- `m11_gen_ir2.sh` / `m11_e2e.sh`: PE パスを `FL_WIN64_DIR` で上書き可能に (既定値は従来どおり)。`m11_e2e.sh` は `M11_PE` も既定導出。
- `trap_triage/survey_units.mjs`: frame 修正 (`be5c84d`)、`SV_RAW=1` で生 frame (既定 OFF)。
- `trap_triage/oob_insn.py` / `oob684_probe.mjs`: 新規 (診断用、既定の survey には影響しない)。
- 範囲外: `m11_survey.mjs` (e2e の survey) は frame の取り方が別 (`fn#` 表示) のため未確認。DEFECTS.md 本体・icall の番号体系は未変更。
