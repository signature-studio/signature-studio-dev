# PY-5458 付録: FLEngine entry からの unicorn 実行で表 [ctx-0xc0] に届くか (#5458 受入 2)

親: #4138 (PY-4867)。前段: #5458 の停止報告 (2026-10-15・10-17)、子 #5625 (付録 `REPORT_PY73_APPENDIX_5375.md`)。
`REPORT_PY73.md` は 250 行上限のため別置きした。

## 1. 結論

- 受入 2 (表 `[ctx-0xc0]` の実行時値を取る手段が 1 run (60 分) に収まるかの実測判定) は **未達・判定不能**。
- 起点 `0xf76820` は **RVA** (PE の AddressOfEntryPoint)。VA は `0x1376820` (`tools/startup/STARTUP.md` と一致)。PM 依頼文の表記 (VA) のまま `0xf76820` を逆アセンブルすると別のコードになるため、VA `0x1376820` で扱った。
- 単純な実行 (import 738 件を全て「rax=0 で戻る」スタブに置換) は、entry から **19,956 命令・0.02 秒** で戻り、表の読出し関数 `0x40fb40` には **0 回** しか届かない。表の初期化 (`0x41d8f0` 系) は途中で例外経路に入って抜ける。
- この 0.02 秒は「途中で抜けた」時間で、表の実行時値を得るのに要する時間ではない。1 run の判定には使えない。
- 届かない原因は、import スタブが一律 0 を返すことにある (初期化中の判定が失敗する)。表を埋めるには、初期化経路で使われる import (ファイル・レジストリ・ウィンドウ・Delphi の例外機構) の戻り値と副作用を実 API に近づける必要がある。これは受入 2 の範囲を超えるため、子として切り出す (§4)。

## 2. 測定

- 素材: `$HOME/artifacts/fl-win64.tar.zst` を `tools/python/work/py5458/` (gitignore) に `*block00031_PE.bin` のみ展開。実測 1.6 秒。
- unicorn 2.1.4 (`uv pip install unicorn`・導入 0.4 秒)。pefile・capstone も同 venv (`tools/python/work/venv5458`)。
- ハーネス: `tools/python/analysis/flapi/pe_emu_entry_5458.py`。
  `FL_WIN64_DIR=tools/python/work/py5458 python3 tools/python/analysis/flapi/pe_emu_entry_5458.py 2000000 60`
- 実行結果 (上限 200 万命令・60 秒): 19,956 命令・0.02 秒・import 呼出し 1 回・終了 `正常終了`・戻り先 `0x100ffff0` (ハーネスの戻りスタブ)。
- 命令の追跡: entry → `call 0x412760` (レジスタを保存して 0 を返す。setjmp 相当 `0x412680`) → `0x41d8f0` (初期化。`0x412050` は関数ポインタ配列を逆順に呼ぶループ) と進む。初期化の途中で `0x4127bf` から `call 0x4126f0` (レジスタを復元して戻す。longjmp 相当) が実行され、setjmp 点へ戻る。2 回目の戻りでは `eax=1` となり、entry の `cmp eax,1` → `jne 0x1376884` で初期化を飛ばして戻る。
- 初期化が途中で longjmp 相当に抜ける原因 (どの import・どの判定が失敗したか) は本付録では未確定。推測の戻り値では埋めない。
- 測定 commit: §5 を参照。

## 3. 表

| 項目 | 結果 | 根拠 (VA) |
|---|---|---|
| 起点 | entry VA `0x1376820` (RVA `0xf76820`) | PE optional header の AddressOfEntryPoint |
| 初期化経路への到達 | 到達 (`call 0x41d8f0` 系まで) | `0x1376870` |
| 表 `[ctx-0xc0]` の読出し `0x40fb40` への到達 | **0 回** | ハーネス `reader hits=0` |
| 1 run 判定 | **判定不能** (途中で抜けた時間のため) | §2 |
| 抜けた原因 | import スタブ (rax=0) による初期化中の判定失敗。例外フレーム `0x4127xx` → 復帰 `0x4126f0` | §2 |
| 必要な追加 | 初期化経路の import の実戻り値・副作用 | §4 |

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 初期化経路で使う import の戻り値・副作用 (ファイル・レジストリ・Delphi の例外機構) を実 API に近づける | 表に届かず、1 run 判定が出せない | #5458 (Refs・残件) |
| 表 `[ctx-0xc0]` の実行時値そのもの | 受入 2 の本来の目的。未確定 | #5458 (Refs・残件) |

子 issue は本 run では起票していない (残件は #5458 の受入 2 として残す)。

## 5. 測定 commit と差分

- 測定 commit: `db5d64e54` (ハーネス `pe_emu_entry_5458.py` と本付録を同じ commit で入れた。コードを変えた最後の commit)。
- 測定の再現: §2 の再実行は HEAD (`db5d64e54` 以降) で同じ結果 (19,956 命令・0.02 秒・`reader hits=0`)。
- 差分 0 の証跡: `git diff db5d64e54 HEAD -- tools/python/analysis/flapi/pe_emu_entry_5458.py` の出力は 0 行 (PR 本文に記載)。
