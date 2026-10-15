# tools/plugins/f2 REPORT_APPENDIX_3295 — PLG-F3-35 (#3295): DllMain の初期化列を harness で最後まで走らせる (部分)

- 測定 commit: **0e612588** (`unicorn_trace.py` の `-L`・`-N` を追加した最後のコード commit)。
- 鮮度: `git diff 0e612588 HEAD -- tools/plugins/f2/*.py` は出力なし (本節を含む commit は md のみ。§6)。
- 親: #2574 (付録 `REPORT_APPENDIX_2574.md` §8、測定 commit 959e608f)。前提: #2468 (PR #2526)。
- 担当 dir: `tools/plugins/f2/` のみ。入力: `$RUNNER_TEMP/fl-win64/extracted/block19148_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 extracted/block19148_PE.bin`、約 3 秒)。
- 依存: `uv venv $RUNNER_TEMP/f2venv && VIRTUAL_ENV=$RUNNER_TEMP/f2venv uv pip install unicorn==2.1.4 pefile capstone` (unicorn 2.1.4 / pefile 2024.8.26 / capstone 5.0.9)。
- 実 FL の host 値は得られない。locale の値は en-US の Windows 既定値 (下記 §2 の表) で、実機の値は未取得。

## 0. 結論 (先出し)

1. **受入 1 は達成** (`-L`)。`GetThreadLocale` は 0x409 (en-US)、`GetLocaleInfoW` は en-US の値を書く (59 件中 57 件が表どおり、表外の LCTYPE 0x79・0x1005 の 2 件は 0 を返す)、`LCMapStringW` は大文字・小文字変換を行い文字数を返す。既定 (`-L` なし) の挙動は変えない (§1 M-A と従来値が一致)。
2. `-L` で、列の 19 件目 (`0x44e8e0`) の `LCMapStringW` 失敗による `RaiseException` が消えた (`RaiseException` 3 件 → 1 件、`GetLastError` 2 件 → 0 件)。
3. **残る例外**: 列の 21 件目 (`0x45c760`) の中で、`0x410ef0` 関数の最後の `RaiseException(0xeedfade, 1, 8, args)` (`0x411017`) が出る。この raise は **条件に関わらず必ず通る** (§3)。harness は SEH を配送できないため、stub は 0 を返し、DllMain は `0x411a80` の致命経路 (`rcx=0xcb`) → longjmp で `rax=0` に戻る。
4. **受入 2 (例外の扱いの決定) は未達**。戻り先の決定は、この raise を捕まえる Delphi の try フレームの特定が前提で、本 run では決めきれていない (子 issue へ)。
5. **受入 3・4 は未達**。`-L` でも列は `0x5e0340` (240 件目) に届かず、`rax=0`。`[0x8cd068]` は 0 → 0 のまま。
6. **受入 5 の文言どおりの `0x83efb0 -H -V -S -L -p 0x409090` は未達**。`UC_ERR_INSN_INVALID rip=0x50138d06` (#2574 §8.2 M1 と同じ。DllMain 前処理が前提)。
7. 新しい観測: `[0x8bf040]` (Delphi の例外まわりの 1 語。0 だと 0x411000 へ直行) は列の途中で `rip=0x44569f` が `0x4455a0` を書く (§3)。書込みの関数は未特定。

## 1. 測定 (測定 commit 0e612588、逐次。負荷 1 分値 0.13)

検証コマンドは §5。wall は各 1.8 秒前後。

| 実行 | 結果 | stub 件数 (抜粋) |
|---|---|---|
| M-A 既定 (`-L` なし) `0x8525f0 -H -V -S -p 0x409090 -r rdx=1` | `status: returned to sentinel rax=0x0`。`[0x8cd068]` 0 → 0。`0x411a80` は `rcx=0xcb` で入場 | GetLocaleInfoW 59・GetThreadLocale 2・LCMapStringW 2・GetLastError 2・RaiseException 3・LoadStringW 75 (#2574 §8.2 M6 と一致) |
| M-B `-L` (`-N` は stub 順序の表示) | `status: returned to sentinel rax=0x0`。`[0x8cd068]` 0 → 0。`0x5e0340` 入場 0 | GetLocaleInfoW 59 (全て LCID=0x409)・GetThreadLocale 2・LCMapStringW 2・GetLastError 0・RaiseException 1・LoadStringW 36 |
| M-D 受入 5 の文言 `0x83efb0 -H -V -S -L -p 0x409090` | `UC_ERR_INSN_INVALID rip=0x50138d06`。`0x411a80`・`0x411bb8`・`0x5e0340` の入場 0 | — |

- 変更前 (#2574 §8.2 M6): GetThreadLocale の戻り値は 0 (stub の既定)。GetLocaleInfoW は LCID=0 で呼ばれ、全件が失敗 (0)。これが LCMapStringW の失敗と例外の発生順の起点。
- M-B の `LoadStringW` が 75 → 36 に減るのは、例外経路の分岐が変わったためと見られる (例外メッセージを組む経路の差。未特定)。stub の戻り値は変えていない (`-S` の挙動は同じ)。

### 1.1 GetLocaleInfoW の LCTYPE (M-B。`-N` の出力を集計)

- 59 件の LCTYPE は全て LCID=0x409。内訳: 曜日名 `0x2a`〜`0x30`・短縮曜日 `0x31`〜`0x37`・月名 `0x38`〜`0x43`・短縮月名 `0x44`〜`0x4f`・`0x100b` (LOCALE_IOPTIONALCALENDAR) ほか。
- 表外 (0 を返す): `0x79`・`0x1005` (各 1 件)。値を確認していないため表に入れていない。

## 2. 変更点 (`tools/plugins/f2/unicorn_trace.py`、commit 0e612588)

- `-L`: `kernel32!GetThreadLocale` → 0x409。`kernel32!GetLocaleInfoW` → LCID=0x409 かつ表 `EN_US` にあれば文字列 (NUL 込み) を書いて文字数+1 を返す (`cchData=0` は必要長、不足は 0)。`kernel32!LCMapStringW` → `LCMAP_LOWERCASE` (0x100)・`LCMAP_UPPERCASE` (0x200) の変換 (長さは保つ)、`cchSrc=-1` は NUL まで、`cchDst=0` は必要長。
- `EN_US` 表の出典: winnls.h (Wine の `include/winnls.h` の LOCALE_* 値) と en-US の既定値。曜日・月名・日付/時刻の書式・小数/桁区切り・通貨・AM/PM・コードページ (437/1252)。
- `-N`: stub の呼出しを順に出す (名前・rcx/rdx/r8/r9・戻り番地)。デバッグ用、既定オフ。
- 既定 (`-L`・`-N` なし) の挙動は変えない (M-A と従来値の一致で確認)。

## 3. 残る Delphi 例外 (`RaiseException` 0xeedfade) の構造

- 経路 (`-t` の実測。`-L -N`): `0x412290` (関数 `0x412290`..`0x4122d8`) → `oleaut32!SysAllocStringLen` (`rdx=5`、戻り `0x4122b3`) → `0x411ee0` (`rcx=0x5012c4c0` = 文字列) → `0x410ef0` (関数 `0x410ef0`..`0x411029`、`rcx=0x50141c90` = 例外オブジェクト、`[rcx]=0x42d2b8` の VMT) → `0x410f63` → `0x411000` → `RaiseException` (戻り `0x41101d`)。例外クラスの名前は未特定 (VMT `0x42d2b8` から読むのは次の作業)。
- `0x410ef0` の分岐 (逆アセンブル): `0x410f63` で `cmp [0x8bf040], 0`。0 なら `0x411000` へ直行、非 0 でも `test dil, dil` が非 0 なら `0x411000` へ。`dil` が 0 の経路だけ、`0x410ffa` の間接 call (`[rip+0x4ae040]`) を経て `0x411000` に落ちる。**どの経路も `0x411000` の `RaiseException(0xeedfade, 1, 8, &[rbp+0xc0])` で終わる** (非継続の例外)。
- `[0x8bf040]` は `before` 0 → `after` `0x4455a0`。書込みは `rip=0x44569f` (`-w 0x8bf040:0x8bf048`)。列の途中で書かれる。関数は未特定。
- `RaiseException` の戻り 0 の後: `0x41101d` の `lea rsp,[rbp+0x108]; pop...; ret` で `0x410ef0` が返り、その呼出し元が `0x411a80` (致命、`MessageBoxA` を呼ぶ `0x411a5b`) → `0x4118c0` (longjmp、rdx=2) で DllMain が 0 で戻る。
- 戻り先の決定 (受入 2) に必要なこと: (a) この raise を囲む Delphi の `try` フレーム (SEH の scope table) の特定、(b) その handler の戻り番地への巻戻し方式。本 run では (a) を未特定のまま残した。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 2: `0x411017` の `RaiseException(0xeedfade)` を harness でどう扱うか (SEH 配送、または捕まえる try フレームの戻り先の決定) | 列が 21 件目 (`0x45c760`) で止まる。`rax=0` | 子 issue (PLG-F3 `#A`) |
| 受入 3・4: 列を 240 件目 (`0x5e0340`) まで走らせ、`[0x8cd068]` の最終値と書込み元を記録する | 受入 2 が前提 | 子 issue (`#B`) |
| 受入 5〜7: `0x83efb0` 経路で `0x411a80` に届かせ、`0x411bb8` の `[0x8c3c80]`・`[[rcx]+0x28]`、空き obj `[obj-8]` の書込み元を記録する | 受入 2〜4 が前提 (#2574 §8.3) | 子 issue (`#C`) |
| 表外 LCTYPE `0x79`・`0x1005` の値 (0 を返す) | 2 件。影響は列の後続で未確認 | 子 `#B` (列を通すときに確認) |
| `[0x8bf040]` を書く関数 (`rip=0x44569f`) の特定 | raise の経路の前提 (0 か否か) | 子 `#A` |

## 5. 検証コマンド (リポジトリ直下、`PE=$RUNNER_TEMP/fl-win64/extracted/block19148_PE.bin`、`T=$RUNNER_TEMP/f2venv/bin/python`)

- M-A: `$T tools/plugins/f2/unicorn_trace.py $PE 0x8525f0 -H -V -S -p 0x409090 -r rdx=1 -t 0x411a80 -t 0x5e0340 -q 0x8cd068 -w 0x8cd068:0x8cd070 -w 0x8bf040:0x8bf048 -q 0x8bf040 -m 2000000`
- M-B: M-A に `-L -N` を付ける
- M-D: `$T tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -V -S -L -p 0x409090 -t 0x411a80 -t 0x411940 -t 0x411bb8 -t 0x5e0340 -q 0x8cd068 -w 0x8cd068:0x8cd070 -m 2000000`

## 6. 鮮度

- 測定 commit: `0e612588`。`git diff 0e612588 HEAD -- tools/plugins/f2/*.py` は、本節を含む commit で出力なし (本 commit は `REPORT_APPENDIX_3295.md` と `DOC_MAP.md` のみ)。
