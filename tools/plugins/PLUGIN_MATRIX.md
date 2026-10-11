# 自動生成: `tools/plugins` plugin-matrix driver

> **人手編集禁止** (生成元を直す)。本ファイルは測定・抽出結果の**単一の正本**。
> **行数目安**: 自動生成ファイルのため行数上限はなし (`docs/DOC_MAP.md` §1)。


# PLUGIN_MATRIX — FL Studio 26.1.7 同梱 Fruity プラグイン 141 種 (Effects 90 + Generators 51) 実測マトリクス
生成: `bash tools/plugins/build_all.sh` (inventory/*.py → lift/plugin_closure.py → tier.py)。数値は全て実測 (mac: pkg_extract, win: NSIS 展開 + 自作 NSIS ヘッダ解析で復元した名称対応)。

## 0. サマリ

| Tier | 個数 | うち Effects | うち Generators | 推定工数合計(人日,推定) |
|---|---:|---:|---:|---:|
| T0 | 42 | 38 | 4 | 21.0 |
| T1 | 45 | 29 | 16 | 67.5 |
| T2 | 34 | 17 | 17 | 136 |
| T3 | 20 | 6 | 14 | 300 |
| 計 | 141 | 90 | 51 | 524.5 |

scope 別: big3p=6, gui=5, host=9, in=121 (in=通常 / host=ホスト機能統合 / gui=音声処理なし / big3p=巨大第三者エンジン)

## 1. Tier 規則

```

Tier 規則 (全て実測値ベース, 閾値は work/win_unique.json の分布の自然な切れ目):
  U      = win プラグイン所有モジュールの固有コード量 (framework 共通部を除外; vendor 同梱 lib 除外)
  ENG    = U のうち FP_DelphiPlug 以外のエンジン DLL (MSVC C++ 等) の固有コード
  T0 : U <  45 KB                    (単一 Delphi 本体モジュール, 純 DSP/UI の小規模)
  T1 : 45 KB <= U < 160 KB           (中規模 DSP / 状態機械; engine 無し〜小)
  T2 : 160 KB <= U < 700 KB          (engine 分離型 / 大型 DSP / スクリプト・エディタ系)
  T3 : U >= 700 KB, or 単一 engine >= 2 MB, or scope == big3p, or synth-big
効果工数 (推定; 人日, P0=framework+パイプライン確立後の 1 本あたり): T0 0.5 / T1 1.5 / T2 4 / T3 15。
```

## 2. 全 141 プラグイン

列: U=win 固有コード(KB, framework 共通 ~1.6MB を除く) / FP=その中の浮動小数演算命令数 / ENG=win エンジン DLL 合計 KB / mac=x86_64 slice KB (言語) / CL=Delphi 本体 (殻) の DSP エントリ(vtable override)から直接呼出で到達する固有コード閉包(KB; engine DLL は ENG 列) / LS=T0/T1 バッチ lift 状態 (V=差分試験で bit-exact 実証あり, ok=RetDec+pass鎖+`emcc -c` 通過, f80=x87 混入で未通過, NG=その他, -=未実施) / abi=Delphi 本体の FruityPlug 実装スロット(Eff=Eff_Render, Gen=Gen_Render, Voice=TriggerVoice) / params=Info.NumParams / pre=プリセット数 / demo=Data 内 .flp 82 本での出現数 / RT=Render test flp 有無

| # | Kind | Plugin | Family | Tier | U | FP | ENG | CL | LS | win modules | mac main KB (lang) | abi | params | pre | demo | RT | scope |
|--:|---|---|---|---|--:|--:|--:|--:|---|---|---|---|--:|--:|--:|---|---|
| 1 | E | Control Surface | controller | T2 | 410 | 767 | 0 | 25 | - | Control Surfac(5689K) | 2932 (FPC) | - | 2048 | 0 | 22 |  | host |
| 2 | E | Distructor | distortion | T2 | 179 | 1717 | 0 | 6 | - | Distructor(3656K)+Module(4427K) | 2231 (FPC) | Eff | 196 | 47 | 4 |  | in |
| 3 | E | Edison | audio-editor | T1 | 106 | 394 | 0 | 40 | ok | Edison(6223K)+testdll(45K) | 4341 (FPC) | Eff | 3 | 5 | 4 |  | in |
| 4 | E | Effector | multi-fx | T2 | 310 | 2943 | 498 | 15 | - | Effector(3726K)+engine(498K) | 2363 (FPC) | Eff | 12 | 0 | 10 | Y | in |
| 5 | E | Emphasis | dynamics | T1 | 90 | 469 | 0 | 26 | ok | Emphasis(4142K) | 2613 (FPC) | Eff | 10 | 21 | 4 | Y | in |
| 6 | E | Emphasizer | eq-filter | T1 | 61 | 211 | 0 | 14 | ok | Emphasizer(3776K) | 2347 (FPC) | Eff | 6 | 1 | 1 |  | in |
| 7 | E | EQUO | eq-filter | T1 | 65 | 267 | 0 | 15 | ok | EQUO(3817K) | 2397 (FPC) | Eff | 842 | 6 | 6 | Y | in |
| 8 | E | FL Studio Mobile Rack FX | mobile-rack | T3 | 5990 | 95117 | 8229 | - | - | FL Studio Mobi(8228K) | 6228 (clang) |  |  | 31 | 0 |  | big3p |
| 9 | E | Frequency Shifter | modulation | T2 | 164 | 1395 | 263 | 16 | - | Frequency Shif(3876K)+Engine(263K) | 2430 (FPC) | Eff | 10 | 9 | 3 | Y | in |
| 10 | E | Frequency Splitter | eq-filter | T3 | 2707 | 82447 | 3352 | 25 | - | Frequency Spli(4386K)+engine(3352K) | 2863 (FPC) | Eff | 14 | 9 | 4 |  | in |
| 11 | E | Fruity 7 Band EQ | eq-filter | T0 | 18 | 85 | 0 | 6 | ok | Fruity 7 Band (3670K) | 2247 (FPC) | Eff | 7 | 14 | 0 |  | in |
| 12 | E | Fruity Balance | stereo-util | T0 | 24 | 146 | 0 | 7 | V | Fruity Balance(3718K) | 2297 (FPC) | Eff | 2 | 0 | 12 | Y | in |
| 13 | E | Fruity Bass Boost | eq-filter | T0 | 13 | 45 | 0 | 3 | ok | Fruity Bass Bo(3752K) | 2330 (FPC) | Eff | 2 | 1 | 1 | Y | in |
| 14 | E | Fruity Big Clock | visual | T1 | 46 | 100 | 0 | 4 | ok | Fruity Big Clo(3598K) | 2165 (FPC) | - | 0 | 0 | 0 |  | gui |
| 15 | E | Fruity Blood Overdrive | distortion | T0 | 25 | 186 | 0 | 8 | ok | Fruity Blood O(3727K) | 2297 (FPC) | Eff | 6 | 3 | 10 | Y | in |
| 16 | E | Fruity Center | stereo-util | T0 | 41 | 59 | 0 | 2 | ok | Fruity Center(3588K) | 2148 (FPC) | Eff | 1 | 1 | 0 | Y | in |
| 17 | E | Fruity Chorus | modulation | T1 | 49 | 284 | 0 | 11 | ok | Fruity Chorus(3744K) | 2297 (FPC) | Eff | 12 | 8 | 13 | Y | in |
| 18 | E | Fruity Compressor | dynamics | T1 | 47 | 185 | 0 | 12 | ok | Fruity Compres(3722K) | 2281 (FPC) | Eff | 6 | 20 | 16 | Y | in |
| 19 | E | Fruity Convolver | reverb-delay | T1 | 120 | 463 | 0 | 56 | ok | Fruity Convolv(6156K) | 4225 (FPC) | Eff | 4 | 261 | 11 | Y | in |
| 20 | E | Fruity dB meter | visual | T0 | 17 | 102 | 0 | 2 | ok | Fruity dB mete(3662K) | 2247 (FPC) | Eff | 0 | 0 | 1 |  | in |
| 21 | E | Fruity Delay | reverb-delay | T0 | 19 | 85 | 0 | 5 | ok | Fruity Delay(3773K) | 2347 (FPC) | Eff | 6 | 6 | 52 |  | in |
| 22 | E | Fruity Delay 2 | reverb-delay | T0 | 27 | 213 | 0 | 13 | ok | Fruity Delay 2(3731K) | 2314 (FPC) | Eff | 8 | 6 | 16 | Y | in |
| 23 | E | Fruity Delay 3 | reverb-delay | T3 | 810 | 2405 | 1195 | 11 | - | Fruity Delay 3(3939K)+engine(1195K) | 2530 (FPC) | Eff | 26 | 10 | 31 |  | in |
| 24 | E | Fruity Delay Bank | reverb-delay | T1 | 63 | 312 | 0 | 19 | ok | Fruity Delay B(3917K) | 2513 (FPC) | Eff | 131 | 21 | 16 | Y | in |
| 25 | E | Fruity Fast Dist | distortion | T0 | 23 | 162 | 0 | 8 | ok | Fruity Fast Di(3703K) | 2280 (FPC) | Eff | 5 | 8 | 17 | Y | in |
| 26 | E | Fruity Fast LP | eq-filter | T0 | 13 | 32 | 0 | 4 | ok | Fruity Fast LP(3752K) | 2330 (FPC) | Eff | 2 | 0 | 3 | Y | in |
| 27 | E | Fruity Filter | eq-filter | T0 | 20 | 235 | 0 | 7 | ok | Fruity Filter(3780K) | 2363 (FPC) | Eff | 6 | 4 | 5 | Y | in |
| 28 | E | Fruity Flanger | modulation | T0 | 21 | 100 | 0 | 6 | ok | Fruity Flanger(3716K) | 2297 (FPC) | Eff | 12 | 27 | 5 | Y | in |
| 29 | E | Fruity Flangus | modulation | T0 | 19 | 98 | 0 | 7 | ok | Fruity Flangus(3686K) | 2264 (FPC) | Eff | 8 | 12 | 20 | Y | in |
| 30 | E | Fruity Formula Controller | controller | T1 | 74 | 191 | 0 | 24 | ok | Fruity Formula(3869K) | 2431 (FPC) | - | 3 | 20 | 5 |  | in |
| 31 | E | Fruity Free Filter | eq-filter | T0 | 19 | 111 | 0 | 6 | ok | Fruity Free Fi(3777K) | 2363 (FPC) | Eff | 4 | 9 | 2 | Y | in |
| 32 | E | Fruity HTML NoteBook | gui-only | T1 | 64 | 58 | 0 | 9 | ok | Fruity HTML No(3927K) | 2233 (FPC) | - | 0 | 3 | 1 |  | gui |
| 33 | E | Fruity Limiter | dynamics | T0 | 39 | 311 | 0 | 16 | ok | Fruity Limiter(3868K) | 2447 (FPC) | Eff | 18 | 13 | 52 | Y | in |
| 34 | E | Fruity Love Philter | multi-fx | T1 | 115 | 600 | 0 | 60 | ok | Fruity Love Ph(5997K) | 4025 (FPC) | Eff | 359 | 47 | 20 | Y | in |
| 35 | E | Fruity LSD | gui-fx | T2 | 301 | 125 | 0 | 9 | - | Fruity LSD(4504K) | 2198 (FPC) | Eff MIDIIn | 1 | 0 | 0 |  | in |
| 36 | E | Fruity Multiband Compressor | dynamics | T2 | 391 | 1398 | 538 | 10 | - | Fruity Multiba(3852K)+comp_eng(537K) | 2446 (FPC) | Eff | 28 | 31 | 12 | Y | in |
| 37 | E | Fruity Mute 2 | stereo-util | T0 | 12 | 15 | 0 | 2 | ok | Fruity Mute 2(3692K) | 2264 (FPC) | Eff | 2 | 0 | 0 | Y | in |
| 38 | E | Fruity NoteBook | gui-only | T0 | 41 | 56 | 0 | 2 | ok | Fruity NoteBoo(3610K) | 2215 (FPC) | - | 1 | 2 | 12 |  | gui |
| 39 | E | Fruity NoteBook 2 | gui-only | T0 | 42 | 64 | 0 | 3 | ok | Fruity NoteBoo(3612K) | 2181 (FPC) | - | 1 | 2 | 10 |  | gui |
| 40 | E | Fruity PanOMatic | stereo-util | T0 | 23 | 145 | 0 | 6 | ok | Fruity PanOMat(3759K) | 2331 (FPC) | Eff | 6 | 1 | 21 | Y | in |
| 41 | E | Fruity Parametric EQ | eq-filter | T0 | 24 | 146 | 0 | 6 | ok | Fruity Paramet(3816K) | 2397 (FPC) | Eff | 29 | 21 | 57 | Y | in |
| 42 | E | Fruity Parametric EQ 2 | eq-filter | T1 | 101 | 623 | 0 | 35 | ok | Fruity Paramet(4036K) | 2612 (FPC) | Eff | 36 | 13 | 57 | Y | in |
| 43 | E | Fruity Peak Controller | controller | T0 | 26 | 176 | 0 | 9 | ok | Fruity Peak Co(4044K) | 2514 (FPC) | Eff | 10 | 3 | 27 |  | in |
| 44 | E | Fruity Phase Inverter | stereo-util | T0 | 13 | 20 | 0 | 2 | ok | Fruity Phase I(3689K) | 2264 (FPC) | Eff | 1 | 0 | 0 | Y | in |
| 45 | E | Fruity Phaser | modulation | T0 | 21 | 136 | 0 | 6 | ok | Fruity Phaser(3708K) | 2280 (FPC) | Eff | 9 | 27 | 3 | Y | in |
| 46 | E | Fruity Reeverb | reverb-delay | T1 | 48 | 212 | 0 | 10 | ok | Fruity Reeverb(3714K) | 2280 (FPC) | Eff | 10 | 21 | 41 | Y | in |
| 47 | E | Fruity Reeverb 2 | reverb-delay | T1 | 61 | 375 | 0 | 17 | ok | Fruity Reeverb(3831K) | 2413 (FPC) | Eff | 15 | 6 | 41 | Y | in |
| 48 | E | Fruity Scratcher | pitch-time | T2 | 170 | 1563 | 165 | 19 | - | Fruity Scratch(4272K)+engine(165K) | 2630 (FPC) | Eff | 14 | 0 | 0 | Y | in |
| 49 | E | Fruity Send | stereo-util | T0 | 18 | 91 | 0 | 5 | ok | Fruity Send(3708K) | 2281 (FPC) | Eff | 3 | 0 | 1 | Y | in |
| 50 | E | Fruity Soft Clipper | distortion | T0 | 22 | 156 | 0 | 6 | ok | Fruity Soft Cl(3718K) | 2297 (FPC) | Eff | 2 | 1 | 22 | Y | in |
| 51 | E | Fruity Spectroman | visual | T0 | 25 | 156 | 0 | 10 | ok | Fruity Spectro(3756K) | 2330 (FPC) | Eff | 3 | 1 | 0 |  | in |
| 52 | E | Fruity Squeeze | distortion | T0 | 33 | 409 | 0 | 10 | ok | Fruity Squeeze(3826K) | 2397 (FPC) | Eff | 12 | 6 | 2 | Y | in |
| 53 | E | Fruity Stereo Enhancer | stereo-util | T0 | 23 | 151 | 0 | 6 | ok | Fruity Stereo (3728K) | 2314 (FPC) | Eff | 6 | 3 | 9 | Y | in |
| 54 | E | Fruity Stereo Shaper | stereo-util | T0 | 31 | 358 | 0 | 14 | ok | Fruity Stereo (3800K) | 2380 (FPC) | Eff | 6 | 25 | 31 | Y | in |
| 55 | E | Fruity Vocoder | pitch-time | T0 | 34 | 290 | 0 | 15 | ok | Fruity Vocoder(3814K) | 2396 (FPC) | Eff | 12 | 2 | 1 | Y | in |
| 56 | E | Fruity WaveShaper | distortion | T0 | 36 | 206 | 0 | 12 | ok | Fruity WaveSha(5742K) | 3842 (FPC) | Eff | 3 | 34 | 29 | Y | in |
| 57 | E | Fruity Wrapper | host-wrapper | T2 | 162 | 185 | 0 | 85 | - | Fruity Wrapper(5997K) | 3598 (FPC) | Eff MIDIIn |  | 0 | 2 |  | host |
| 58 | E | Fruity X-Y Controller | controller | T0 | 31 | 190 | 0 | 9 | ok | Fruity X-Y Con(3772K) | 2330 (FPC) | - | 10 | 8 | 4 |  | in |
| 59 | E | Fruity X-Y-Z Controller | controller | T0 | 44 | 217 | 0 | 20 | ok | Fruity X-Y-Z C(5796K) | 3892 (FPC) | - | 11 | 11 | 5 |  | in |
| 60 | E | Gross Beat | pitch-time | T1 | 143 | 1687 | 0 | 32 | ok | Gross Beat(5850K) | 3908 (FPC) | Eff | 9 | 9 | 16 | Y | in |
| 61 | E | Hardcore | distortion | T2 | 350 | 2390 | 642 | - | - | Hardcore(641K) | 402 (clang) |  |  | 0 | 1 | Y | in |
| 62 | E | Hyper Chorus | modulation | T1 | 152 | 1117 | 249 | 11 | ok | Hyper Chorus(3938K)+Engine(248K) | 2529 (FPC) | Eff | 11 | 12 | 7 |  | in |
| 63 | E | Low Lifter | eq-filter | T1 | 67 | 296 | 0 | 17 | ok | Low Lifter(3793K) | 2363 (FPC) | Eff | 15 | 7 | 2 | Y | in |
| 64 | E | LuxeVerb | reverb-delay | T1 | 84 | 303 | 0 | 38 | ok | LuxeVerb(4341K) | 2812 (FPC) | Eff | 49 | 174 | 10 |  | in |
| 65 | E | Maximus | dynamics | T1 | 124 | 973 | 0 | 46 | ok | Maximus(5904K) | 3991 (FPC) | Eff | 59 | 41 | 44 | Y | in |
| 66 | E | Multiband Delay | reverb-delay | T3 | 2463 | 76327 | 3090 | 19 | - | Multiband Dela(3932K)+engine(3090K) | 2514 (FPC) | Eff | 396 | 17 | 0 |  | in |
| 67 | E | Newtime | pitch-time | T1 | 95 | 158 | 0 | 22 | ok | Newtime(5082K) | 3195 (FPC) | Eff |  | 0 | 0 |  | in |
| 68 | E | Newtone | pitch-time | T3 | 3270 | 58902 | 4967 | 24 | - | Newtone(5077K)+Newtone_Engine(4967K) | 3195 (FPC) | Eff |  | 0 | 0 |  | in |
| 69 | E | Patcher | host-wrapper | T2 | 336 | 659 | 0 | 173 | - | Patcher(7056K) | 4682 (FPC) | Eff Gen Voice MIDIIn | 4096 | 137 | 12 | Y | host |
| 70 | E | Pitch Shifter | pitch-time | T1 | 61 | 245 | 0 | 17 | ok | Pitch Shifter(4260K) | 2729 (FPC) | Eff | 13 | 26 | 7 | Y | in |
| 71 | E | Pitcher | pitch-time | T2 | 264 | 1372 | 446 | - | - | Pitcher(446K) | 352 (clang) |  |  | 0 | 18 | Y | in |
| 72 | E | Razer Chroma | hardware | T1 | 70 | 302 | 0 | 10 | ok | Razer Chroma(4046K) | 2198 (FPC) | Eff | 10 | 0 | 0 |  | host |
| 73 | E | Soundgoodizer | dynamics | T1 | 57 | 396 | 0 | 30 | ok | Soundgoodizer(6407K) | 4519 (FPC) | Eff | 0 | 0 | 10 | Y | in |
| 74 | E | Spreader | stereo-util | T1 | 63 | 329 | 0 | 10 | ok | Spreader(3912K) | 2447 (FPC) | Eff | 5 | 0 | 8 | Y | in |
| 75 | E | Transient Processor | dynamics | T2 | 179 | 1264 | 190 | 16 | - | Transient Proc(3971K)+engine(190K) | 2563 (FPC) | Eff | 9 | 10 | 14 | Y | in |
| 76 | E | Transmitter | other-fx | T1 | 79 | 268 | 0 | 30 | ok | Transmitter(4210K) | 2679 (FPC) | Eff | 33 | 34 | 0 |  | in |
| 77 | E | Transporter | other-fx | T1 | 71 | 421 | 0 | 23 | ok | Transporter(4170K) | 2646 (FPC) | Eff | 22 | 6 | 1 | Y | in |
| 78 | E | Tuner | visual | T2 | 195 | 1958 | 227 | 11 | - | Tuner(3779K)+engine(226K) | 2380 (FPC) | Eff | 3 | 6 | 0 |  | in |
| 79 | E | VFX Color Mapper | vfx-midi | T0 | 42 | 55 | 0 | 2 | ok | VFX Color Mapp(3918K) | 2398 (FPC) | Voice | 32 | 0 | 0 |  | in |
| 80 | E | VFX Envelope | vfx-midi | T0 | 40 | 144 | 0 | 19 | ok | VFX Envelope(5758K) | 3859 (FPC) | Voice | 880 | 4 | 0 |  | in |
| 81 | E | VFX Key Mapper | vfx-midi | T0 | 23 | 82 | 0 | 6 | ok | VFX Key Mapper(4001K) | 2481 (FPC) | Voice | 5 | 34 | 0 |  | in |
| 82 | E | VFX Keyboard Splitter | vfx-midi | T0 | 31 | 122 | 0 | 10 | ok | VFX Keyboard S(5727K) | 3825 (FPC) | Voice | 0 | 17 | 0 |  | in |
| 83 | E | VFX Level Scaler | vfx-midi | T0 | 34 | 249 | 0 | 10 | ok | VFX Level Scal(4106K) | 2597 (FPC) | Voice | 36 | 0 | 0 |  | in |
| 84 | E | VFX Script | vfx-midi | T1 | 71 | 104 | 0 | 26 | ok | VFX Script(4495K) | 2947 (FPC) | Voice |  | 89 | 0 |  | in |
| 85 | E | VFX Sequencer | vfx-midi | T2 | 289 | 621 | 395 | 14 | - | VFX Sequencer(4172K)+engine(394K) | 2663 (FPC) | Voice | 513 | 0 | 0 |  | in |
| 86 | E | Vintage Chorus | modulation | T2 | 175 | 1437 | 205 | 14 | - | Vintage Chorus(3941K)+engine(204K) | 2530 (FPC) | Eff | 17 | 22 | 5 | Y | in |
| 87 | E | Vintage Phaser | modulation | T2 | 181 | 2344 | 313 | 22 | - | Vintage Phaser(3973K)+engine(313K) | 2563 (FPC) | Eff | 36 | 16 | 1 |  | in |
| 88 | E | Vocodex | pitch-time | T2 | 366 | 3469 | 0 | 74 | - | Vocodex(5957K)+Sytrus(6308K) | 4041 (FPC) | Eff | 20 | 21 | 9 | Y | in |
| 89 | E | Wave Candy | visual | T1 | 108 | 708 | 0 | 44 | ok | Wave Candy(4348K) | 2812 (FPC) | Eff | 1 | 38 | 6 |  | in |
| 90 | E | ZGameEditor Visualizer | visual | T3 | 1003 | 1327 | 0 | - | - | ZGameEditor Vi(7600K)+Processing.NDI(27128K)+SpoutLibrary(471K) | 5265 (FPC) |  |  | 230 | 9 |  | big3p |
| 91 | G | 3x Osc | synth-simple | T1 | 137 | 904 | 222 | 22 | ok | 3x Osc(4348K)+engine(221K) | 2730 (FPC) | Gen Voice | 114 | 1 | 26 | Y | in |
| 92 | G | Autogun | synth | T1 | 149 | 860 | 0 | 88 | ok | Autogun(6291K) | 4307 (FPC) | Gen Voice | 1 | 0 | 8 | Y | in |
| 93 | G | BassDrum | drum-synth | T2 | 379 | 1736 | 517 | 23 | - | BassDrum(4068K)+engine(516K) | 2547 (FPC) | Gen Voice | 23 | 52 | 4 | Y | in |
| 94 | G | BeepMap | synth-simple | T1 | 54 | 115 | 0 | 23 | ok | BeepMap(4286K) | 2680 (FPC) | Gen Voice | 106 | 7 | 0 | Y | in |
| 95 | G | BooBass | synth | T2 | 360 | 921 | 852 | - | - | BooBass_Eng(851K)+BooBass(3685K) | 396 (clang) |  |  | 0 | 2 | Y | in |
| 96 | G | Dashboard | gui-only | T2 | 526 | 957 | 0 | 128 | - | Dashboard(5036K) | 2198 (FPC) | Gen Voice | 257 | 7 | 0 |  | gui |
| 97 | G | DirectWave | sampler | T3 | 966 | 5796 | 1120 | - | - | DirectWave(1120K)+editor(6194K) | 1234 (clang) |  |  | 0 | 16 | Y | big3p |
| 98 | G | Drumaxx | drum-synth | T2 | 456 | 2360 | 577 | 34 | - | Drumaxx(4423K)+engine(577K) | 2828 (FPC) | Gen Voice | 719 | 131 | 0 | Y | in |
| 99 | G | Drumpad | drum-synth | T2 | 333 | 1830 | 450 | 20 | - | Drumpad(4104K)+engine(449K) | 2597 (FPC) | Gen Voice | 38 | 961 | 2 | Y | in |
| 100 | G | FL Keys | sampler | T1 | 74 | 351 | 0 | 19 | ok | FL Keys(4213K) | 2713 (FPC) | Gen Voice | 15 | 9 | 8 | Y | in |
| 101 | G | FL Slayer | synth | T1 | 50 | 83 | 0 | 5 | ok | FL Slayer(5743K)+Slayer_Engine(179K) | 2198 (FPC) | Gen Voice | 29 | 0 | 0 |  | in |
| 102 | G | FL Studio Mobile | mobile-rack | T3 | 9054 | 105166 | 12142 | - | - | FL Studio Mobi(12141K)+FLMManagedBrid(103K) | 14848 (clang) |  |  | 0 | 0 |  | big3p |
| 103 | G | FL Studio Mobile Rack | mobile-rack | T3 | 5992 | 95155 | 8232 | - | - | FL Studio Mobi(8231K) | 6228 (clang) |  |  | 0 | 0 |  | big3p |
| 104 | G | FLEX | synth-big | T3 | 10255 | 210169 | 13794 | 81 | - | FLEX(5194K)+engineV2(8119K)+engine(5673K) | 3513 (FPC) | Gen Voice | 45 | 0 | 14 | Y | big3p |
| 105 | G | FPC | sampler | T2 | 202 | 553 | 0 | 72 | - | FPC(6067K) | 4157 (FPC) | Gen Voice | 768 | 40 | 34 | Y | in |
| 106 | G | Fruit Kick | drum-synth | T1 | 46 | 101 | 0 | 19 | ok | Fruit Kick(4268K) | 2664 (FPC) | Gen Voice | 99 | 8 | 2 | Y | in |
| 107 | G | Fruity Dance | synth-simple | T1 | 61 | 162 | 0 | 10 | ok | Fruity dance(4163K) | 2547 (FPC) | Gen Voice | 7 | 0 | 0 |  | in |
| 108 | G | Fruity DrumSynth Live | drum-synth | T2 | 370 | 592 | 1088 | 16 | - | Fruity DrumSyn(4187K)+drumsynth_eng(1088K) | 2680 (FPC) | Gen Voice | 4560 | 2 | 1 | Y | in |
| 109 | G | Fruity DX10 | synth-simple | T1 | 57 | 305 | 0 | 22 | ok | Fruity DX10(4332K) | 2713 (FPC) | Gen Voice | 114 | 59 | 6 | Y | in |
| 110 | G | Fruity Envelope Controller | controller | T3 | 1190 | 7669 | 0 | 134 | - | Fruity Envelop(6251K) | 3875 (FPC) | Voice | 90 | 23 | 4 |  | in |
| 111 | G | Fruity Granulizer | sampler | T1 | 66 | 321 | 0 | 26 | ok | Fruity Granuli(4475K) | 2830 (FPC) | Gen Voice | 103 | 8 | 1 | Y | in |
| 112 | G | Fruity Keyboard Controller | controller | T1 | 46 | 98 | 0 | 5 | ok | Fruity Keyboar(4017K) | 2497 (FPC) | Voice | 2 | 7 | 1 |  | in |
| 113 | G | Fruity Slicer | sampler | T1 | 84 | 259 | 0 | 41 | ok | Fruity Slicer(4591K) | 2946 (FPC) | Gen Voice | 96 | 0 | 4 | Y | in |
| 114 | G | Fruity Slicer 2 | sampler | T3 | 2219 | 77363 | 2738 | 24 | - | Fruity Slicer (5930K)+engine(2738K) | 4025 (FPC) | Gen Voice | 1040 | 1 | 0 |  | in |
| 115 | G | Fruity Video Player | host-media | T1 | 89 | 181 | 0 | 19 | ok | Fruity Video P(4281K) | 2696 (FPC) | Gen Voice | 3 | 1 | 0 |  | host |
| 116 | G | Fruity Voltage Controller | controller | T1 | 69 | 486 | 0 | 27 | ok | Fruity Voltage(4087K) | 2563 (FPC) | Gen Voice | 16 | 0 | 0 | Y | in |
| 117 | G | Fruity Wrapper | host-wrapper | T2 | 162 | 198 | 0 | 85 | - | Fruity Wrapper(5998K) | 3598 (FPC) | Gen Voice MIDIIn |  | 0 | 2 |  | host |
| 118 | G | GMS | sampler | T3 | 1209 | 56174 | 1553 | - | - | GMS(1552K) | 435 (clang) |  |  | 0 | 5 | Y | in |
| 119 | G | Harmless | synth | T1 | 139 | 1695 | 0 | 99 | ok | Harmless(4776K) | 3128 (FPC) | Gen Voice | 100 | 430 | 24 | Y | in |
| 120 | G | Harmor | synth-big | T3 | 373 | 4030 | 0 | 267 | - | Harmor(6478K) | 4588 (FPC) | Gen Voice |  | 325 | 19 | Y | in |
| 121 | G | Kepler | synth | T3 | 806 | 6583 | 2718 | 18 | - | Kepler(3860K)+engine(2717K) | 2463 (FPC) | Gen Voice | 36 | 277 | 3 |  | in |
| 122 | G | Kepler Exo | synth | T3 | 896 | 7140 | 2718 | 61 | - | Kepler Exo(4418K)+engine(2717K) | 2928 (FPC) | Gen Voice | 155 | 188 | 0 |  | in |
| 123 | G | MIDI Out | host-midi | T0 | 33 | 83 | 0 | 9 | ok | MIDI Out(4047K) | 2513 (FPC) | Voice | 73 | 41 | 3 |  | host |
| 124 | G | MiniSynth | synth-simple | T2 | 298 | 2013 | 555 | - | - | MiniSynth(555K) | 369 (clang) |  |  | 1 | 2 | Y | in |
| 125 | G | Morphine | synth | T3 | 1354 | 57228 | 1745 | - | - | Morphine(1745K) | 685 (clang) |  |  | 0 | 4 |  | in |
| 126 | G | Ogun | synth | T1 | 159 | 1062 | 0 | 105 | ok | Ogun(6188K) | 4207 (FPC) | Gen Voice | 89 | 229 | 14 | Y | in |
| 127 | G | Patcher | host-wrapper | T2 | 332 | 654 | 0 | 171 | - | Patcher(7052K) | 4682 (FPC) | Eff Gen Voice MIDIIn | 4096 | 172 | 12 | Y | host |
| 128 | G | Plucked! | synth-simple | T0 | 17 | 95 | 0 | 6 | ok | Plucked!(3697K) | 2264 (FPC) | Gen Voice | 5 | 1 | 0 |  | in |
| 129 | G | PoiZone | synth | T2 | 439 | 2891 | 632 | 44 | - | PoiZone(3960K)+engine(632K) | 2596 (FPC) | Gen Voice | 203 | 385 | 1 | Y | in |
| 130 | G | ReWired | host-wrapper | T1 | 69 | 88 | 0 | 18 | f80 | ReWired(3991K) | 2198 (FPC) | Gen Voice MIDIIn | 128 | 5 | 0 |  | host |
| 131 | G | Sakura | synth | T2 | 462 | 3922 | 639 | 58 | - | Sakura(4294K)+engine(639K) | 2779 (FPC) | Gen Voice | 207 | 501 | 3 | Y | in |
| 132 | G | Sawer | synth | T2 | 470 | 3419 | 654 | 55 | - | Sawer(4310K)+engine(653K) | 2812 (FPC) | Gen Voice MIDIIn | 202 | 421 | 0 | Y | in |
| 133 | G | SimSynth | synth-simple | T2 | 393 | 1195 | 561 | - | - | SimSynth_Eng(560K)+SimSynth(3850K) | 112 (clang) |  |  | 73 | 0 | Y | in |
| 134 | G | Slicex | sampler | T2 | 164 | 1066 | 0 | 104 | - | Slicex(6282K) | 4391 (FPC) | Gen Voice | 352 | 3 | 19 | Y | in |
| 135 | G | Soundfont Player | sampler | T3 | 1080 | 6689 | 0 | 235 | - | Soundfont Play(4551K) | 2895 (FPC) | Gen Voice | 13 | 0 | 0 |  | in |
| 136 | G | Sytrus | synth-big | T3 | 229 | 1796 | 0 | 128 | - | Sytrus(6269K) | 4290 (FPC) | Gen Voice | 597 | 984 | 23 | Y | in |
| 137 | G | Toxic Biohazard | synth | T2 | 423 | 2902 | 755 | - | - | Toxic Biohazar(755K) | 534 (clang) |  |  | 0 | 2 |  | in |
| 138 | G | Transistor Bass | synth | T3 | 837 | 3510 | 1631 | 34 | - | Transistor Bas(4056K)+engine(1630K) | 2696 (FPC) | Gen Voice | 42 | 3 | 0 |  | in |
| 139 | G | Wasp | synth-simple | T0 | 15 | 44 | 0 | 1 | ok | Wasp(3597K) | 2198 (FPC) | Eff Gen Voice MIDIIn |  | 0 | 1 |  | in |
| 140 | G | Wasp XT | synth-simple | T0 | 15 | 44 | 0 | 1 | ok | Wasp XT(3597K) | 2198 (FPC) | Eff Gen Voice MIDIIn |  | 0 | 0 |  | in |
| 141 | G | Wave Traveller | synth | T2 | 328 | 2324 | 0 | 159 | - | Wave Traveller(4473K) | 2564 (FPC) | Gen Voice | 0 | 6 | 1 | Y | in |

## 3. Tier 別内訳

### T0 (42)

Fruity Mute 2, Fruity Fast LP, Fruity Bass Boost, Fruity Phase Inverter, Wasp[G], Wasp XT[G], Plucked![G], Fruity dB meter, Fruity 7 Band EQ, Fruity Send, Fruity Free Filter, Fruity Flangus, Fruity Delay, Fruity Filter, Fruity Flanger, Fruity Phaser, Fruity Soft Clipper, Fruity PanOMatic, Fruity Stereo Enhancer, VFX Key Mapper, Fruity Fast Dist, Fruity Balance, Fruity Parametric EQ, Fruity Blood Overdrive, Fruity Spectroman, Fruity Peak Controller, Fruity Delay 2, Fruity X-Y Controller, Fruity Stereo Shaper, VFX Keyboard Splitter, MIDI Out[G], Fruity Squeeze, VFX Level Scaler, Fruity Vocoder, Fruity WaveShaper, Fruity Limiter, VFX Envelope, Fruity Center, Fruity NoteBook, VFX Color Mapper, Fruity NoteBook 2, Fruity X-Y-Z Controller

### T1 (45)

Fruity Keyboard Controller[G], Fruit Kick[G], Fruity Big Clock, Fruity Compressor, Fruity Reeverb, Fruity Chorus, FL Slayer[G], BeepMap[G], Fruity DX10[G], Soundgoodizer, Pitch Shifter, Emphasizer, Fruity Dance[G], Fruity Reeverb 2, Spreader, Fruity Delay Bank, Fruity HTML NoteBook, EQUO, Fruity Granulizer[G], Low Lifter, ReWired[G], Fruity Voltage Controller[G], Razer Chroma, VFX Script, Transporter, FL Keys[G], Fruity Formula Controller, Transmitter, Fruity Slicer[G], LuxeVerb, Fruity Video Player[G], Emphasis, Newtime, Fruity Parametric EQ 2, Edison, Wave Candy, Fruity Love Philter, Fruity Convolver, Maximus, 3x Osc[G], Harmless[G], Gross Beat, Autogun[G], Hyper Chorus, Ogun[G]

### T2 (34)

Fruity Wrapper, Fruity Wrapper[G], Slicex[G], Frequency Shifter, Fruity Scratcher, Vintage Chorus, Transient Processor, Distructor, Vintage Phaser, Tuner, FPC[G], Pitcher, VFX Sequencer, MiniSynth[G], Fruity LSD, Effector, Wave Traveller[G], Patcher[G], Drumpad[G], Patcher, Hardcore, BooBass[G], Vocodex, Fruity DrumSynth Live[G], BassDrum[G], Fruity Multiband Compressor, SimSynth[G], Control Surface, Toxic Biohazard[G], PoiZone[G], Drumaxx[G], Sakura[G], Sawer[G], Dashboard[G]

### T3 (20)

Sytrus[G], Harmor[G], Kepler[G], Fruity Delay 3, Transistor Bass[G], Kepler Exo[G], DirectWave[G], ZGameEditor Visualizer, Soundfont Player[G], Fruity Envelope Controller[G], GMS[G], Morphine[G], Fruity Slicer 2[G], Multiband Delay, Frequency Splitter, Newtone, FL Studio Mobile Rack FX, FL Studio Mobile Rack[G], FL Studio Mobile[G], FLEX[G]

## 4. 優先度 (priority_score = (1 + 2*demo + 0.1*presets + 3*RT) / 推定工数) 上位 40

| rank | Plugin | Tier | score | demo | pre | RT | family |
|--:|---|---|--:|--:|--:|---|---|
| 1 | Fruity Parametric EQ | T0 | 240.2 | 57 | 21 | Y | eq-filter |
| 2 | Fruity Limiter | T0 | 218.6 | 52 | 13 | Y | dynamics |
| 3 | Fruity Delay | T0 | 211.2 | 52 | 6 |  | reverb-delay |
| 4 | Fruity Stereo Shaper | T0 | 137.0 | 31 | 25 | Y | stereo-util |
| 5 | Fruity WaveShaper | T0 | 130.8 | 29 | 34 | Y | distortion |
| 6 | Fruity Peak Controller | T0 | 110.6 | 27 | 3 |  | controller |
| 7 | Fruity Soft Clipper | T0 | 96.2 | 22 | 1 | Y | distortion |
| 8 | Fruity PanOMatic | T0 | 92.2 | 21 | 1 | Y | stereo-util |
| 9 | Fruity Flangus | T0 | 90.4 | 20 | 12 | Y | modulation |
| 10 | Fruity Parametric EQ 2 | T1 | 79.53 | 57 | 13 | Y | eq-filter |
| 11 | Fruity Fast Dist | T0 | 77.6 | 17 | 8 | Y | distortion |
| 12 | Fruity Delay 2 | T0 | 73.2 | 16 | 6 | Y | reverb-delay |
| 13 | Maximus | T1 | 64.07 | 44 | 41 | Y | dynamics |
| 14 | Harmless | T1 | 63.33 | 24 | 430 | Y | synth |
| 15 | Fruity Reeverb | T1 | 58.73 | 41 | 21 | Y | reverb-delay |
| 16 | Fruity Reeverb 2 | T1 | 57.73 | 41 | 6 | Y | reverb-delay |
| 17 | Fruity Balance | T0 | 56.0 | 12 | 0 | Y | stereo-util |
| 18 | Fruity NoteBook | T0 | 50.4 | 12 | 2 |  | gui-only |
| 19 | Fruity Blood Overdrive | T0 | 48.6 | 10 | 3 | Y | distortion |
| 20 | Fruity Stereo Enhancer | T0 | 44.6 | 9 | 3 | Y | stereo-util |
| 21 | Fruity NoteBook 2 | T0 | 42.4 | 10 | 2 |  | gui-only |
| 22 | 3x Osc | T1 | 37.4 | 26 | 1 | Y | synth-simple |
| 23 | Ogun | T1 | 36.6 | 14 | 229 | Y | synth |
| 24 | Fruity Convolver | T1 | 34.73 | 11 | 261 | Y | reverb-delay |
| 25 | Fruity Flanger | T0 | 33.4 | 5 | 27 | Y | modulation |
| 26 | Fruity Love Philter | T1 | 32.47 | 20 | 47 | Y | multi-fx |
| 27 | Fruity Filter | T0 | 28.8 | 5 | 4 | Y | eq-filter |
| 28 | Drumpad | T2 | 26.03 | 2 | 961 | Y | drum-synth |
| 29 | LuxeVerb | T1 | 25.6 | 10 | 174 |  | reverb-delay |
| 30 | Fruity Phaser | T0 | 25.4 | 3 | 27 | Y | modulation |
| 31 | Fruity Delay Bank | T1 | 25.4 | 16 | 21 | Y | reverb-delay |
| 32 | Fruity Compressor | T1 | 25.33 | 16 | 20 | Y | dynamics |
| 33 | Gross Beat | T1 | 24.6 | 16 | 9 | Y | pitch-time |
| 34 | Fruity X-Y-Z Controller | T0 | 24.2 | 5 | 11 |  | controller |
| 35 | MIDI Out | T0 | 22.2 | 3 | 41 |  | host-midi |
| 36 | Fruity Chorus | T1 | 20.53 | 13 | 8 | Y | modulation |
| 37 | Fruity Fast LP | T0 | 20.0 | 3 | 0 | Y | eq-filter |
| 38 | Fruity X-Y Controller | T0 | 19.6 | 4 | 8 |  | controller |
| 39 | FPC | T2 | 19.0 | 34 | 40 | Y | sampler |
| 40 | Fruity Free Filter | T0 | 17.8 | 2 | 9 | Y | eq-filter |

## 5. ファミリ別 (lift バッチ単位)

| family | n | 内訳 Tier | プラグイン |
|---|--:|---|---|
| synth | 14 | T1:4 T2:6 T3:4 | Autogun, BooBass, FL Slayer, Harmless, Kepler, Kepler Exo, Morphine, Ogun, PoiZone, Sakura, Sawer, Toxic Biohazard, Transistor Bass, Wave Traveller |
| eq-filter | 11 | T0:6 T1:4 T3:1 | EQUO, Emphasizer, Frequency Splitter, Fruity 7 Band EQ, Fruity Bass Boost, Fruity Fast LP, Fruity Filter, Fruity Free Filter, Fruity Parametric EQ, Fruity Parametric EQ 2, Low Lifter |
| stereo-util | 9 | T0:8 T1:1 | Fruity Balance, Fruity Center, Fruity Mute 2, Fruity PanOMatic, Fruity Phase Inverter, Fruity Send, Fruity Stereo Enhancer, Fruity Stereo Shaper, Spreader |
| reverb-delay | 9 | T0:2 T1:5 T3:2 | Fruity Convolver, Fruity Delay, Fruity Delay 2, Fruity Delay 3, Fruity Delay Bank, Fruity Reeverb, Fruity Reeverb 2, LuxeVerb, Multiband Delay |
| synth-simple | 9 | T0:3 T1:4 T2:2 | 3x Osc, BeepMap, Fruity DX10, Fruity Dance, MiniSynth, Plucked!, SimSynth, Wasp, Wasp XT |
| sampler | 9 | T1:3 T2:2 T3:4 | DirectWave, FL Keys, FPC, Fruity Granulizer, Fruity Slicer, Fruity Slicer 2, GMS, Slicex, Soundfont Player |
| controller | 8 | T0:3 T1:3 T2:1 T3:1 | Control Surface, Fruity Formula Controller, Fruity Peak Controller, Fruity X-Y Controller, Fruity X-Y-Z Controller, Fruity Envelope Controller, Fruity Keyboard Controller, Fruity Voltage Controller |
| modulation | 8 | T0:3 T1:2 T2:3 | Frequency Shifter, Fruity Chorus, Fruity Flanger, Fruity Flangus, Fruity Phaser, Hyper Chorus, Vintage Chorus, Vintage Phaser |
| pitch-time | 8 | T0:1 T1:3 T2:3 T3:1 | Fruity Scratcher, Fruity Vocoder, Gross Beat, Newtime, Newtone, Pitch Shifter, Pitcher, Vocodex |
| distortion | 7 | T0:5 T2:2 | Distructor, Fruity Blood Overdrive, Fruity Fast Dist, Fruity Soft Clipper, Fruity Squeeze, Fruity WaveShaper, Hardcore |
| dynamics | 7 | T0:1 T1:4 T2:2 | Emphasis, Fruity Compressor, Fruity Limiter, Fruity Multiband Compressor, Maximus, Soundgoodizer, Transient Processor |
| vfx-midi | 7 | T0:5 T1:1 T2:1 | VFX Color Mapper, VFX Envelope, VFX Key Mapper, VFX Keyboard Splitter, VFX Level Scaler, VFX Script, VFX Sequencer |
| visual | 6 | T0:2 T1:2 T2:1 T3:1 | Fruity Big Clock, Fruity Spectroman, Fruity dB meter, Tuner, Wave Candy, ZGameEditor Visualizer |
| host-wrapper | 5 | T1:1 T2:4 | Fruity Wrapper, Patcher, Fruity Wrapper, Patcher, ReWired |
| drum-synth | 5 | T1:1 T2:4 | BassDrum, Drumaxx, Drumpad, Fruit Kick, Fruity DrumSynth Live |
| gui-only | 4 | T0:2 T1:1 T2:1 | Fruity HTML NoteBook, Fruity NoteBook, Fruity NoteBook 2, Dashboard |
| mobile-rack | 3 | T3:3 | FL Studio Mobile Rack FX, FL Studio Mobile, FL Studio Mobile Rack |
| synth-big | 3 | T3:3 | FLEX, Harmor, Sytrus |
| multi-fx | 2 | T1:1 T2:1 | Effector, Fruity Love Philter |
| other-fx | 2 | T1:2 | Transmitter, Transporter |
| audio-editor | 1 | T1:1 | Edison |
| gui-fx | 1 | T2:1 | Fruity LSD |
| hardware | 1 | T1:1 | Razer Chroma |
| host-media | 1 | T1:1 | Fruity Video Player |
| host-midi | 1 | T0:1 | MIDI Out |
