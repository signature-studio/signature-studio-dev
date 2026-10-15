# reverb_delay REPORT 付録 (#3445 PLG-F4-3: 19165 の IPPCODE 呼出元の切り分け)

親 #523 ([PLG-F4-2])。 本付録は REPORT §7 の「IPP の static link と推定・殻との結合は未解析」への静的な回答。 engine の正しさ・lift の可否は示さない。

- **測定 commit**: `02b230d19` (道具 `ipp_callers.py` のコードを変えた最後の commit)。 初版 `ca5a642e8` からの変更は、pdata 外の呼出元を箇所ごとに数える修正 (件数の定義) のみ。 区分と pdata 基準・線形の件数は初版と同じ。 base は `origin/main` `10daa391b`。 本付録の commit は docs のみ。
- **素材**: `fl-win64` の `block19164_PE.bin` (殻) と `block19165_PE.bin` (engine) のみを展開 (`tar --zstd -xf … --wildcards '*block19164_PE.bin' '*block19165_PE.bin'`)。 RetDec・emsdk は使わない (静的解析のみ)。 測定 (`02b230d19`) の開始時 load average (1 分) 0.22。
- **道具**: `tools/plugins/reverb_delay/ipp_callers.py` (pefile + capstone)。 `02b230d19` で実行 31 秒、rc 0。 実行はしない (解析のみ・対象の機械語は走らせない)。

## 1. IPPCODE の呼出元・呼出先 (受入 1)

IPPCODE 節は VA `0x1801e2000`–`0x180266b4d` (vsize 543,565 B)。 `.pdata` の関数は 272 件・513,403 B (節の 94.4%)。 2 通りで数えた。
- **pdata 基準**: `.pdata` の関数 (lift 範囲 = `engine_ranges.py` と同じ) の命令だけ。 下限。
- **線形走査**: `.text` と IPPCODE を先頭から逆アセンブル (不正命令は 1 byte 飛ばす)。 pdata に載らない本体を拾う。 上限寄り。

| IPPCODE の関数先頭の区分 | pdata 基準 | 線形走査 |
|---|--:|--:|
| `.text` の直接 call/jmp が着地 | 88 | 94 |
| IPPCODE 内の直接 call/jmp が着地 (IPP 内部呼出し) | 4 | 4 |
| データ中の絶対ポインタが指す | 1 | 1 |
| rip 相対参照が指す (`lea` 等) のみ | 0 | 0 |
| **静的に呼出元が見つからない** | **179** (302,761 B) | **173** |
| 合計 | 272 | 272 |

- 直接辺 (関数の境界をまたぐもの) で IPPCODE に着地するのは pdata 基準 635 本・線形 649 本。 同一関数内の `jmp` (分岐) は数えていない (初回の集計で混入したため除外に直した)。
- 線形走査で pdata 関数の外に着地する IPP 入口は 2 件 (`0x180266270`・`0x180266290`)。 IPPCODE のうち pdata に載らない 30,162 B の内側で、lift 範囲の外になる。
- IPPCODE 内の pdata 関数から画像の外・`.text` への直接辺は 0 (pdata 基準)。 線形走査では 33 件 (うち 32 件は画像外 = 誤デコードとみなす・1 件は `.text`)。 この 33 件は `elastique` の REPORT_152 §1.3 と同型。
- 間接 call/jmp (`.text` の pdata 関数に 466 サイト、線形では 520 サイト) は宛先を静的に解決していない。

### 呼出元の切り分け

- **殻 (block 19164) からの参照: 0** (PE 上の参照として)。 殻は別イメージで、 import 表に engine の DLL は無い。 殻の文字列に `engine_x64` は無い (ASCII・UTF-16 とも 0)。 engine の呼出しは `LoadLibrary`/`GetProcAddress` で得る export に限られ、 export は `VSTPluginMain` と `main` (同じ VA `0x1801d77f0`・`.text`) の 2 本だけ。 IPPCODE は export されない。
- 殻の `dsp_ippv2` 系の文字列 (UTF-16 で `ipps` 342 件・`ippsFFT` 28 件) は、 殻が framework の `dsp_ippv2.dll` を読むための名前表と推定 (`ipp_use.py` の対象)。 engine の静的 IPPCODE とは別経路。
- **engine 内の `.text` から**: 直接 call で入る IPP 入口は 88 (pdata 基準) / 94 (線形)。 呼出元の `.text` 関数 (pdata 内) は 1 入口あたり最大 4 件 (線形)。 pdata 外の `.text` の呼出し箇所は関数に数えず、箇所ごとに数える (線形で 14 箇所)。 内訳は入口 `0x180266270` に 8 箇所、pdata 入口 6 件 (`0x180238a60`・`0x180238dc0`・`0x180239120`・`0x180239e80`・`0x180239f80`・`0x18023a080`) に各 1 箇所。 後者の 6 件は pdata 内の呼出元が 0 で、線形の 94 件に含まれる。 pdata 外の箇所は線形走査の結果で、誤デコードの可能性を含む (未確認)。
- **export から直接辺だけで到達する IPP 入口: 0**。 export から直接辺で辿れる `.text` 関数は 74 件 (pdata 基準)。 IPP の `.text` 呼出元の多くは、この直接の到達集合の外にあり、間接 call 経由と推定 (未確定)。

### 呼出元の無い 179 入口

- pdata 基準で、直接 call・ポインタ・rip 相対参照のどれも見つからない入口。 302,761 B (pdata の IPP の 59%)。 静的な呼出元が無いため、 殻・export・`.text` のどこから来るかは静的には同定できない。
- 候補 (未切り分け): (a) 初期化時に書かれる動的な関数表 (`.data`・IPPDATA への書込み)、(b) 相対オフセット表 (IPPDATA 2,112 B を `base + 4 byte` で試行した結果は、 有意な一致 0 件・値 0 のノイズのみ)、(c) 静的に辿れない間接経路。 (a)〜(c) の切り分けは実行または追加の逆解析が要る (本付録の範囲外)。
- 関数ポインタ表は 1 箇所のみ: `.rdata` `0x1802caf7c` が IPPCODE 先頭 `0x1801e2000` を指す。 表の一部かは未確認。

## 2. 扱いの候補 (受入 2・PM 判断待ち)

| 候補 | 根拠 (本付録) | 未確定・要判断 |
|---|---|---|
| (a) #38 の代替実装で置換 | `.text` からの直接呼出しは 88〜94 入口。 入口を置換すれば IPPCODE の残りは不要 | 入口の ABI と機能の対応が未同定。 mac 側 Multiband Delay の 57 関数 (FFT・Conj・Mul・Sin・Cos、`tools/shared/REPORT.md`) との対応が未確定。 #140 (ipp-fft)・#137 (ipp-fill) の範囲に依存 |
| (b) そのまま lift | pdata 関数 272 本・513,403 B。 直接呼出しは lift 範囲内で閉じる | **未測定**。 IPP 本体が AVX 系を含むなら、`.text` 側の E5 (78 関数) と同型の再発がありうる。 pdata 外の 2 入口 (30,162 B 側) は範囲外のまま |
| (c) 除外を正式化 | 現状の除外 (#3453 枝の gate。 19165 は 2,602/2,608 define で PASS と記録されているが、 旧 stub (`b2fc00a71`) での値で、 新 gate・新 stub での再測定は未実施。 出典は #3453 枝の `REPORT_APPENDIX.md` §17) | gate は到達性だけを見る。 `.text` の 88〜94 入口からの呼出しは、lift 後に未定義の外部参照として残る (リンク段での検出は未検証) |

**暫定推奨: (a)**。 理由: (c) では `.text` の呼出し先が 88〜94 件残るため、gate の PASS は engine の完全性を示さない。 (b) は 272 関数の lift 鎖が未測定で、AVX 系の再発が懸念。 ただし (a) の前提は入口の ABI 同定で、これは未了。

**確定: (a)** (PM 判断。 根拠は `docs/DECISIONS.md` D20 の表の「Intel IPP 本体 `dsp_ippv2`: lift しない。 API は自前実装に置換する (#38 の既存方針を確定)」と、PR #3472 の PM コメント)。 前提の入口 ABI の同定は未了で、#3445 の作業として残す (§5)。

## 3. gate の実測 (受入 3・未達)

- `engine_f80_subset.sh` は main に無い。 #523 の f80 除外 gate は PR #3453 (枝 `523-plg-f4-2-engine-subset`、 open・未 merge)。
- 19165 の lift (`engine_lift.sh`) は RetDec 鎖で、`toolchain-retdec` と `toolchain-emsdk` が要る。 本 run では `fl-win64` のみ取得 (他の素材は無い)。
- よって候補ごとの gate の結果は、本 run では出せない。 必要: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk` と、#3453 の merge (または gate の取り込み)。

## 4. 再現手順

```
tar --zstd -xf <fl-win64.tar.zst> -C <DIR> --wildcards '*block19164_PE.bin' '*block19165_PE.bin'
FL_WIN64_DIR=<DIR> python3 tools/plugins/reverb_delay/ipp_callers.py --json <OUT.json> 19165
```

`<DIR>/extracted/block19165_PE.bin` が要る (`FL_WIN64_DIR` は `<DIR>` を指す)。 出力は一覧 (区分の件数・直接辺・export 到達・殻の文字列)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) の前提: 入口の ABI と機能の対応の同定 | (a) の置換実装の範囲が決まらない。 扱いは (a) に確定済み (§2) | #3445 (PM が #3445 の作業として残す) |
| gate の実測 (受入 3) | (b)/(c) の判定に gate の結果が無い | #3445 (#3453 の merge と `toolchain-retdec`・`toolchain-emsdk` の取得後) |
| 呼出元の無い 179 入口の経路 | 殻・export からの実到達が未確定 | #3445 (実行トレースまたは逆解析が要る) |
| pdata 外の `.text` 呼出し箇所 14 件 (入口 `0x180266270` の 8 件と pdata 入口 6 件の各 1 件) の実在 | 線形走査の誤デコードかどうかで、6 入口の「呼出元あり」の扱いが変わる | #3445 (逆解析が要る) |
