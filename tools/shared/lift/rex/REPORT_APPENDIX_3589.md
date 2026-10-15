# tools/shared/lift/rex 付録 — movnti (閉包内 24 箇所) の到達と x64c 対応の要否 — T-SH-90 (#3589)

測定 commit: 本 PR の最後のコード commit (`tools/shared/lift/rex/` の `.c`・`.mjs`・`.py`・`.sh` を変えた commit)。以降の差分は本付録と REPORT の更新だけ。
既知類型との関係: 該当なし (不一致 0)。

## 結論 (1 行)
movnti は memset (`f_18001c8f0`・8 箇所) の大ブロック経路にだけあり、入力 a1 (= memset の長さ) が 0x70000 以上で入力だけで到達する (fn=0・16/16 で trap)。memcpy (`f_18001ca80`・16 箇所) は唯一の呼出し元が長さ 0x40 固定のため入力では到達しない。**x64c 対応は memset の 8 箇所について要** (未実装・後述)。

## 1. 静的な経路 (`lift/fle_lifted.c`・測定 HEAD で読んだ)
| 関数 | movnti | 呼出し元 | 長さ (r8) | movnti に入る条件 |
|---|---|---|---|---|
| `f_18001c8f0` (memset: rcx=dst・rdx=val・r8=count) | 8 | `f_1800011c0` (fn=0・`call` 0x1800022cb) と `f_180001130` (fn=1・`call` 0x18000213a) | `sext32(a1)` (`movsxd` で a1 を符号拡張) | `count>>6 ≥ 0x1c00` ⇒ count ≥ 0x70000 |
| `f_18001ca80` (memmove) | 16 | `f_18001bde8` のみ (`mov r8d, 0x40` 固定・0x18001be04) | 0x40 | `count>>5 ≥ 0x2000` ⇒ count ≥ 0x10000。0x40 では不成立 |

- `f_18001bde8` の呼出し元は `f_180016160`・`f_180016170` だけで、どちらも `WaitForSingleObject` の戻りが 0 / 0x80 以外のときの**エラー経路** (直後に `int3`)。harness の `imp_WaitForSingleObject` は 0 を返すので、この経路は入力でも import でも movnti に届かない。
- fn=0 は木の検索 (`f_180001de0`) の直後に memset を呼ぶ (`key_of` は rdi を壊さない・`f_1800019f0` を確認)。fn=1 は memset の前に `f_180012b50`・`f_180012b60`・`f_180012b70`・`f_1800042b0` で node の実体を辿るため、入力の値 (ランダムなポインタ) で先に落ちる (native の fault が arena 末尾 0x30110000 でなく 0x50fb16c0 などになる・推定)。

## 2. 実測 (`bash tools/shared/lift/rex/lift_x64c.sh movnti`・`all` からも実行)
| 項目 | 値 |
|---|---|
| 入力 | 20 件: reach 16 (fn=0・a1 ∈ [0x70000, 0x80000))・info 4 (fn=0・a1 ∈ [0x10000, 0x70000)) |
| wasm の trap (reach) | **16/16** が `0x18001c9a0` (`movnti qword ptr [rcx], rdx`・memset の movnti 先頭) で `ott_unsup` |
| native の fault (reach) | 16/16 が `0x30110000` (arena 末尾 = 64 KiB の外)。movnti 経路でだけ arena を越えて書く |
| wasm の trap (info) | 4/4 trap するが、`ott_unsup` を経由しない (VA = 0)。movnti ではない。**想定 (trap しない) と食い違う・原因未特定** |
| 判定 | `movnti_check.py` の reach 16/16 PASS・`all` の rc = 0 |
| 通常の本検査 (`ok`・回帰) | PASS。比較 175・一致 175・不一致 0・arena 書込 42・`.data` 書込 0・traps 0 (248 case) |
| ネガコン | neg-cmp・neg-ctx・neg-owner は期待どおり FAIL (rc 1 → 期待どおり) |
| 所要 (elapsed・load 開始→終了) | movnti 1 s (load 1.04 1.07 0.69 → 1.03 1.07 0.70)・ok 3 s・neg-ctx 3 s・neg-owner 3 s (同じ `all` 実行のログ) |

- 測定の注意: `run_wasm.mjs` は元の機械語が落ちた case を既定で実行しない。movnti モードは `REX_RUN_CRASHED=1` で実行する (元が落ちる入力でも wasm の経路を見るため)。
- 補修 (本 PR): WASI の `fd_write` が 0 を返していたため、trap 前の `fprintf(stderr)` で stdio が戻らなくなっていた。書いた長さを返し、fd 2 の内容を stderr へ流すように直した。`rex_glue.c` で `fle_ff_hook` を使い、trap した未対応命令の VA を `rex_unsup_get` で返す。

## 3. x64c 対応の要否 (判断)
- **memset の movnti 8 箇所: 要。** 入力だけで到達する (実測 16/16)。到達すると fail-fast で trap するため、そういう長さの入力が本番で来るなら x64c の対応が要る。movnti は単一スレッドの意味では普通の store と同じなので、対応は x64c で ST 系へ写すだけで済む見込み (推定。未実装)。本番の host が a1 に何を渡すかは [未確認]。
- **memcpy の movnti 16 箇所: 不要 (この閉包では到達しない)。** 唯一の呼出し元が長さ 0x40 固定で、movnti の閾値 0x10000 に届かない (静的読み・未実測)。
- 本付録では x64c を変えない (`tools/flelift/` は触らない)。対応の実装は下の未解決に残す。

## 4. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| movnti (memset 8 箇所) の x64c 対応の実装。到達時は fail-fast で trap | a1 ≥ 0x70000 の入力で wasm が trap | 未起票 (本 run の時間内に起票できず。次の run で子 issue (親 #3589) を起票する) |
| info 4 件 (a1 ∈ [0x10000, 0x70000)) が `ott_unsup` 以外で trap (VA 0)。想定と食い違う。推定: 通常の memset が arena を越えて書き、後段が壊れる (未確認) | 閾値の静的読み (0x70000) の反証が未了 | #3589 の再測定 (次の run) |
| `RUN_CRASHED=1` で 248 件すべてを流すと wasm が戻らない (時間切れで未調査。movnti モードは 20 件で完走) | 元が落ちる入力を全件 wasm で流せない | 未起票 (調査は次回) |
| fn=1 (REXGetInfo) の movnti 到達は未達 (memset の前の node 参照で落ちる) | fn=1 からの到達は未確認 | #3588 (T-SH-89・落ちる case の原因) |
| memcpy 16 箇所の到達不能は静的読みで、実測していない | 16 箇所の扱い | 本付録 §1 の静的読み (反証があれば再測定) |
| 本番の host が REXGetCreatorInfo に渡す a1 の値域 | 到達が本番で起きるかの判断 | [未確認]。依頼者が FL 側の呼出し値で確認する |
