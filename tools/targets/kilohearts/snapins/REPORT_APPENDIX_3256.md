# REPORT_APPENDIX_3256 — KH-48 (#3256) 検証の生出力 (全行)

`REPORT_APPENDIX.md` §12-2 の要約の元になった生出力。測定 commit `d7603d630` (コード変更の最後の commit・以降は docs のみ) で `snapins/scripts/ymm_vocab_check.py 20000 1` と `snapins/scripts/fma_vocab_check.py 20000 1` を 1 回ずつ実行した stdout をそのまま載せる (再現は同コマンド)。

## ymm_vocab_check.py 20000 1 (rc=0・real 1.143 s・load 0.16 0.25 0.12)

```text
[gen_simd] helpers 4, undefined(abort stub) 1 ['void __asm_vmovaps.2(i256,i256)'] approx_tables=none
== 本検証 (生成 IR 定義 vs ホスト AVX2) n=20000 seed=1
  vaddps calls=20000 lanes=160000 mismatch=0
  vsubps calls=20000 lanes=160000 mismatch=0
  vmulps calls=20000 lanes=160000 mismatch=0
  vmovaps calls=20000 lanes=160000 mismatch=0
== ネガコン (a) 語彙定義なし (リンクが通らなければ FAIL)
  link rc=1 -> FAIL (期待どおり)
== ネガコン (b) vaddps の演算を fsub に改変 (不一致 > 0 で FAIL)
    MISMATCH vaddps i=0 a0=0c011441 b0=555d8025 got0=d55d8025 want0=555d8025
    MISMATCH vaddps i=1 a0=00800000 b0=ea4ef7fd got0=6a4ef7fd want0=ea4ef7fd
    MISMATCH vaddps i=2 a0=ff800000 b0=7aa1c0b3 got0=ff800000 want0=ff800000
  vaddps calls=20000 lanes=160000 mismatch=19971
  vsubps calls=20000 lanes=160000 mismatch=0
  vmulps calls=20000 lanes=160000 mismatch=0
  vmovaps calls=20000 lanes=160000 mismatch=0
  rc=1 vaddps mismatch=19971 -> FAIL (期待どおり)
== ネガコン (c) 未対応の i256 宣言 vfmadd231ps (abort スタブ化 + 呼出で abort しなければ FAIL)
  [gen_simd] helpers 0, undefined(abort stub) 1 ['i256 __asm_vfmadd231ps(i256,i256,i256)'] approx_tables=none
  stub=あり call rc=-6 -> FAIL (期待どおり)
== ネガコン (d) vmovaps 定義を ret i256 0 に改変 (不一致 > 0 で FAIL)
  vaddps calls=20000 lanes=160000 mismatch=0
  vsubps calls=20000 lanes=160000 mismatch=0
  vmulps calls=20000 lanes=160000 mismatch=0
    MISMATCH vmovaps i=0 a0=df0ce790 b0=c9cfe3ab got0=00000000 want0=df0ce790
    MISMATCH vmovaps i=1 a0=b8a29698 b0=3155261e got0=00000000 want0=b8a29698
    MISMATCH vmovaps i=2 a0=4831b4e3 b0=813b94d4 got0=00000000 want0=4831b4e3
  vmovaps calls=20000 lanes=160000 mismatch=20000
  rc=1 vmovaps mismatch=20000 -> FAIL (期待どおり)
== store 形 void __asm_vmovaps.2(i256,i256) は abort スタブのまま (定義されていれば FAIL)
  stub=あり -> OK
== 判定: 本検証 PASS / ネガコン(a) FAIL / ネガコン(b) FAIL / ネガコン(c) FAIL / ネガコン(d) FAIL / store 形 stub OK -> PASS
```

## fma_vocab_check.py 20000 1 (rc=0・real 0.842 s・load 0.18 0.25 0.12)

```text
[gen_simd] helpers 7, undefined(abort stub) 0 [] approx_tables=none
== 本検証 (生成 C 実装 vs ホスト FMA3・128bit 全 bit・NaN 含む) n=20000 seed=1
  vfmadd213sd calls=20000 bits=128 mismatch=0
  vfmadd213ss calls=20000 bits=128 mismatch=0
  vfmsub213ss calls=20000 bits=128 mismatch=0
  vfmadd231sd calls=20000 bits=128 mismatch=0
  vfmadd231ss calls=20000 bits=128 mismatch=0
  vfnmadd231sd calls=20000 bits=128 mismatch=0
  vfmadd132sd calls=20000 bits=128 mismatch=0
== ネガコン (a) 語彙定義なし (リンクが通らなければ FAIL)
  link rc=1 -> FAIL (期待どおり)
== ネガコン (b) vfmadd213ss の fmaf を単精度 2 段丸め x*y+z に改変 (不一致 > 0 で FAIL)
  vfmadd213sd calls=20000 bits=128 mismatch=0
    MISMATCH vfmadd213ss i=9 d0=00000000b82cf9b0 s2=00000000475f857a s3=000000003f000000 got0=00000000bfee0f60 want0=00000000bfee0f61
    MISMATCH vfmadd213ss i=79 d0=0000000044a7ec93 s2=00000000c4f7bd14 s3=000000003d4e09cc got0=00000000ca228149 want0=00000000ca228148
    MISMATCH vfmadd213ss i=81 d0=000000004438ed30 s2=00000000423577ac s3=00000000408b0968 got0=0000000047031a7d want0=0000000047031a7e
  vfmadd213ss calls=20000 bits=128 mismatch=604
  vfmsub213ss calls=20000 bits=128 mismatch=0
  vfmadd231sd calls=20000 bits=128 mismatch=0
  vfmadd231ss calls=20000 bits=128 mismatch=0
  vfnmadd231sd calls=20000 bits=128 mismatch=0
  vfmadd132sd calls=20000 bits=128 mismatch=0
  rc=1 vfmadd213ss mismatch=604 -> FAIL (期待どおり)
== ネガコン (c) vfmadd213ss の被演算子順を 231 形 fmaf(s2, s3, d) に改変 (不一致 > 0 で FAIL)
  vfmadd213sd calls=20000 bits=128 mismatch=0
    MISMATCH vfmadd213ss i=3 d0=000000003f76d4a2 s2=000000004319b8b7 s3=00000000bd48e9b5 got0=00000000c0d26eb5 want0=0000000043142a9f
    MISMATCH vfmadd213ss i=4 d0=0000000040490fdb s2=00000000a56c27b8 s3=00000000c97e958d got0=0000000040490fdb want0=00000000c97e958d
    MISMATCH vfmadd213ss i=5 d0=000000003d3a58a8 s2=00000000435ca855 s3=00000000e9c1f44d got0=00000000eda72d7b want0=00000000e9c1f44d
  vfmadd213ss calls=20000 bits=128 mismatch=15804
  vfmsub213ss calls=20000 bits=128 mismatch=0
  vfmadd231sd calls=20000 bits=128 mismatch=0
  vfmadd231ss calls=20000 bits=128 mismatch=0
  vfnmadd231sd calls=20000 bits=128 mismatch=0
  vfmadd132sd calls=20000 bits=128 mismatch=0
  rc=1 vfmadd213ss mismatch=15804 -> FAIL (期待どおり)
== 判定: 本検証 PASS (全 bit 不一致 0) / ネガコン(a) FAIL / ネガコン(b) FAIL / ネガコン(c) FAIL -> PASS
== wall 0.82 秒 (N=20000 語彙 7 件/各)
```
