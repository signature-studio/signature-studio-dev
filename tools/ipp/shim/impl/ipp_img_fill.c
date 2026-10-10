/* CAB-136 (IPP-2 ipp-fill): 優先順上位 stub の実装 — imaging (ippi) 系。
   契約: ../impl/README.md — 宣言は ../gen/ipp_proto.h (生成) と一致 = コンパイラが署名検査する。
   引数順序の根拠 (win 呼出実績, tools/ipp/shim/REPORT §10 と work/fill/callsite_dump.py):
   - ippiCopy_8u_C3R/C4R/C1C4R/C3AC4R/AC4C3R: pSrc=rcx / srcStep=rdx / pDst=r8 / dstStep=r9 /
     roiSize=r9..stk の 8B 値渡し (block00031 0x6bb00e ほか 145 モジュール)
   - ippiCopyManaged_8u_C1R: 同形 + flags=stk[1] (block00031 0x6bb195)
   - ippiSet_8u_C3R: value=rcx (lea ローカル) / pDst=rdx / dstStep=r8d / roiSize=r9 (0x6c76e5)
   - ippiAlphaPremul_8u_AC4IR: pSrcDst=rcx / step=rdx / roiSize=r8 (0x6c9265)
   - ippiFilterBox_8u_C3IR/C4IR: pSrcDst=rcx / step=rdx / dstRoiSize=r8 / maskSize=r9 / anchor=stk[0] (0x6ca662)
   - ippiAddC/SubC/MulC_8u_C3IRSfs: value=rcx / pSrcDst=rdx / step=r8d / roiSize=r9 / sfs=stk[0] 即値 (0x6c77b0)
   - ippiAlphaCompC_8u_C3R/C4R: pSrc1=rcx / src1Step=rdx / alpha1=r8 (byte) / pSrc2=r9 / src2Step=stk0 /
     alpha2=stk1 (0xff 即値) / pDst=stk2 / dstStep=stk3 / roiSize=stk4 / alphaType=stk5=0 即値 (0x6c001b)
   - ippiCopyReplicateBorder_8u_C3R: pSrc=rcx / srcStep=rdx / srcRoiSize=r8 / pDst=r9 / dstStep=stk0 /
     dstRoiSize=stk1 / top=stk2 / left=stk3 (0x6bb532)。CopyConstBorder は同形 (実績 weak, オラクルで検証)。
   数式の根拠: arm64 dsp_ippv2 (data/arm64_ipp_map.json 参照用) の逆アセンブル + 実 DLL とのオラクル突合
   (work/fill/fill_oracle.c, 結果は shim/REPORT §10)。 */
#include "ipp_min.h"
#include "../gen/ipp_proto.h"
#include <string.h>
#include <stdlib.h>

#define IPP_STS_BADARG     (-5)  /* ippStsBadArgErr — 実 IPP 観測 (arm64) */
#define IPP_STS_NOTSUPPORT (-22) /* 実 DLL が「未対応モード」で返すコード (Resize 系, probe.c 観測) */

/* 共通: ROI 検査。実 IPP と同じ優先順 (NULL → -8, サイズ → -6)。 */
static IppStatus roi_chk2(const void *p1, const void *p2, IppiSize roi) {
  if (!p1 || !p2) return ippStsNullPtrErr;
  if (roi.width < 1 || roi.height < 1) return ippStsSizeErr;
  return ippStsNoErr;
}
static IppStatus roi_chk1(const void *p1, IppiSize roi) { return roi_chk2(p1, p1, roi); }

/* ---- コピー系 (ch = 1..4, alpha 補完の有無で分岐) ---- */
static IppStatus copy_ch(const Ipp8u *s, int ss, Ipp8u *d, int ds, IppiSize roi, int ch) {
  IppStatus st = roi_chk2(s, d, roi); if (st) return st;
  for (int y = 0; y < roi.height; y++)
    memcpy(d + (size_t)y * ds, s + (size_t)y * ss, (size_t)roi.width * (size_t)ch);
  return ippStsNoErr;
}

IppStatus ippiCopy_8u_C3R(const Ipp8u *pSrc, int srcStep, Ipp8u *pDst, int dstStep, IppiSize roiSize) {
  return copy_ch(pSrc, srcStep, pDst, dstStep, roiSize, 3);
}
IppStatus ippiCopy_8u_C4R(const Ipp8u *pSrc, int srcStep, Ipp8u *pDst, int dstStep, IppiSize roiSize) {
  return copy_ch(pSrc, srcStep, pDst, dstStep, roiSize, 4);
}
/* C1 → C4: 1 チャネルを C4 の ch0 へコピーし、他チャネルは触らない (実 DLL 実測, fit2)。 */
IppStatus ippiCopy_8u_C1C4R(const Ipp8u *pSrc, int srcStep, Ipp8u *pDst, int dstStep, IppiSize roiSize) {
  IppStatus st = roi_chk2(pSrc, pDst, roiSize); if (st) return st;
  for (int y = 0; y < roiSize.height; y++) {
    const Ipp8u *sr = pSrc + (size_t)y * srcStep;
    Ipp8u *dr = pDst + (size_t)y * dstStep;
    for (int x = 0; x < roiSize.width; x++) dr[4 * x] = sr[x];
  }
  return ippStsNoErr;
}
/* C3 → C4 (AC4): RGB を AC4 の ch0..2 へコピーし、alpha (ch3) は触らない (実 DLL 実測, fit2)。 */
IppStatus ippiCopy_8u_C3AC4R(const Ipp8u *pSrc, int srcStep, Ipp8u *pDst, int dstStep, IppiSize roiSize) {
  IppStatus st = roi_chk2(pSrc, pDst, roiSize); if (st) return st;
  for (int y = 0; y < roiSize.height; y++) {
    const Ipp8u *sr = pSrc + (size_t)y * srcStep;
    Ipp8u *dr = pDst + (size_t)y * dstStep;
    for (int x = 0; x < roiSize.width; x++) {
      dr[4 * x + 0] = sr[3 * x + 0];
      dr[4 * x + 1] = sr[3 * x + 1];
      dr[4 * x + 2] = sr[3 * x + 2];
    }
  }
  return ippStsNoErr;
}
/* AC4 → C3: alpha を落としてコピー (arm64 = vImageConvert_RGBA8888toRGB888 相当) */
IppStatus ippiCopy_8u_AC4C3R(const Ipp8u *pSrc, int srcStep, Ipp8u *pDst, int dstStep, IppiSize roiSize) {
  IppStatus st = roi_chk2(pSrc, pDst, roiSize); if (st) return st;
  for (int y = 0; y < roiSize.height; y++) {
    const Ipp8u *sr = pSrc + (size_t)y * srcStep;
    Ipp8u *dr = pDst + (size_t)y * dstStep;
    for (int x = 0; x < roiSize.width; x++) {
      dr[3 * x + 0] = sr[4 * x + 0];
      dr[3 * x + 1] = sr[4 * x + 1];
      dr[3 * x + 2] = sr[4 * x + 2];
    }
  }
  return ippStsNoErr;
}
/* CopyManaged (C1): flags はキャッシュヒント系で出力に影響しないことをオラクルで確認 (§10) */
IppStatus ippiCopyManaged_8u_C1R(const Ipp8u *pSrc, int srcStep, Ipp8u *pDst, int dstStep, IppiSize roiSize, int flags) {
  (void)flags;
  return copy_ch(pSrc, srcStep, pDst, dstStep, roiSize, 1);
}

/* ---- ippiSet_8u_C3R ---- */
IppStatus ippiSet_8u_C3R(const Ipp8u *value, Ipp8u *pDst, int dstStep, IppiSize roiSize) {
  IppStatus st = roi_chk2(value, pDst, roiSize); if (st) return st;
  for (int y = 0; y < roiSize.height; y++) {
    Ipp8u *dr = pDst + (size_t)y * dstStep;
    for (int x = 0; x < roiSize.width; x++) {
      dr[3 * x + 0] = value[0]; dr[3 * x + 1] = value[1]; dr[3 * x + 2] = value[2];
    }
  }
  return ippStsNoErr;
}

/* ---- ippiAlphaPremul_8u_AC4IR: rgb' = round(rgb * a / 255)。
      丸めは (v*a + 127)/255 (= 実 IPP と bit 一致をオラクルで確認, §10)。 ---- */
static inline Ipp8u premul1(Ipp8u v, Ipp8u a) { return (Ipp8u)((v * a + 127) / 255); }
IppStatus ippiAlphaPremul_8u_AC4IR(Ipp8u *pSrcDst, int srcDstStep, IppiSize roiSize) {
  IppStatus st = roi_chk1(pSrcDst, roiSize); if (st) return st;
  for (int y = 0; y < roiSize.height; y++) {
    Ipp8u *r = pSrcDst + (size_t)y * srcDstStep;
    for (int x = 0; x < roiSize.width; x++) {
      Ipp8u a = r[4 * x + 3];
      r[4 * x + 0] = premul1(r[4 * x + 0], a);
      r[4 * x + 1] = premul1(r[4 * x + 1], a);
      r[4 * x + 2] = premul1(r[4 * x + 2], a);
    }
  }
  return ippStsNoErr;
}

/* ---- ippiFilterBox_8u_C3IR / C4IR: in-place box filter。
      実 DLL 実測 (work/fill fit_box): 出力 = floor(マスク窓和 / 面積) — 丸めなしの切り捨て。
      非 Border 版は ROI 外 (バッファ内) の画素もそのまま読む (IPP の仕様)。in-place は
      ROI 行を一旦スナップショットしてから書き戻す (読み直しによる汚染を避ける)。 ---- */
/* ---- ippiFilterBox_8u_C3IR / C4IR: in-place box filter。
      実 DLL 実測 (work/fill fit_box/fit3): 出力 = floor(マスク窓和 / 面積) — 丸めなしの切り捨て。
      窓は ROI 外 (バッファ内の隣接バイト) も生読みする。in-place は ROI 内画素のみ
      スナップショットして元値を参照 (ROI 外は書き換わらないので実読みでよい)。 ---- */
static IppStatus filter_box_ir(Ipp8u *buf, int step, IppiSize roi, IppiSize mask, IppiPoint anchor, int ch) {
  IppStatus st = roi_chk1(buf, roi); if (st) return st;
  if (mask.width < 1 || mask.height < 1) return IPP_STS_BADARG;
  if (anchor.x < 0 || anchor.y < 0 || anchor.x >= mask.width || anchor.y >= mask.height) return IPP_STS_BADARG;
  const int area = mask.width * mask.height;
  /* 実 IPP の狭義 quirk (fit10/fit11 で実測): H == mh+1 かつ ay == mh-1 のとき縦ウィンドウが
     row 0 位置に凍結する (ただし 3x3 マスクは専用カーネルのため例外)。全 row で再現する。 */
  int freeze = (roi.height == mask.height + 1 && anchor.y == mask.height - 1) &&
               !(mask.width == 3 && mask.height == 3);
  /* スナップショットは「ROI + 各行の左ハロ (anchor.x 画素分)」: 左ハロは前ロ末尾 = ROI 内画素で
     in-place により書き換わるため、実 IPP と同じく元値を読む (fit14 実測) */
  int lb = anchor.x; /* 左ハロ画素数 */
  size_t rowlen = (size_t)(roi.width + lb) * (size_t)ch;
  Ipp8u *snap = (Ipp8u *)malloc(rowlen * (size_t)roi.height);
  if (!snap) return (-9); /* ippStsMemAllocErr */
  for (int y = 0; y < roi.height; y++)
    memcpy(snap + rowlen * (size_t)y, buf + (ptrdiff_t)y * step - (ptrdiff_t)lb * ch, rowlen);
  for (int y = 0; y < roi.height; y++) {
    Ipp8u *dr = buf + (size_t)y * step;
    int wy = freeze ? 0 : y; /* 窓の基準行 (凍結時は row 0) */
    for (int x = 0; x < roi.width; x++) {
      for (int c = 0; c < ch; c++) {
        int sum = 0;
        for (int my = 0; my < mask.height; my++) {
          int sy = wy - anchor.y + my;
          const Ipp8u *srow = buf + (ptrdiff_t)sy * step;
          for (int mx = 0; mx < mask.width; mx++) {
            int sx = x - anchor.x + mx;
            /* ROI 内 (とその左ハロ) は元値 (snap)、それ以外は生バッファ (書き換わらない) */
            int v = (sx >= -lb && sx < roi.width && sy >= 0 && sy < roi.height)
                        ? snap[(size_t)sy * rowlen + (size_t)(sx + lb) * ch + c]
                        : srow[(ptrdiff_t)sx * ch + c];
            sum += v;
          }
        }
        dr[x * ch + c] = (Ipp8u)(sum / area);
      }
    }
  }
  free(snap);
  return ippStsNoErr;
}
IppStatus ippiFilterBox_8u_C3IR(Ipp8u *pSrcDst, int srcDstStep, IppiSize dstRoiSize, IppiSize maskSize, IppiPoint anchor) {
  return filter_box_ir(pSrcDst, srcDstStep, dstRoiSize, maskSize, anchor, 3);
}
IppStatus ippiFilterBox_8u_C4IR(Ipp8u *pSrcDst, int srcDstStep, IppiSize dstRoiSize, IppiSize maskSize, IppiPoint anchor) {
  return filter_box_ir(pSrcDst, srcDstStep, dstRoiSize, maskSize, anchor, 4);
}

/* ---- ippiAddC/SubC/MulC_8u_C{3,4}IRSfs: 32bit 中間 → 2^-sfs 倍 → 0..255 飽和。
      実 DLL 実測 (work/fill grid, 全数 720,896 ケース/関数): 3 関数とも偶数丸め
      (round-half-to-even — float + cvtps 系カーネルと整合) → 不一致 0。 ---- */
static inline int sfs_round_even(int v, int sfs) {
  if (sfs <= 0) return v << (-sfs);
  int neg = v < 0;
  unsigned u = neg ? -(unsigned)v : (unsigned)v;
  unsigned q = u >> sfs, r = u & ((1u << sfs) - 1), half = 1u << (sfs - 1);
  if (r > half || (r == half && (q & 1u))) q++;
  return neg ? -(int)q : (int)q;
}
static inline Ipp8u sat_u8(int v) { return (Ipp8u)(v < 0 ? 0 : v > 255 ? 255 : v); }

static IppStatus addc_ir(const Ipp8u *value, Ipp8u *buf, int step, IppiSize roi, int sfs, int ch) {
  IppStatus st = roi_chk2(value, buf, roi); if (st) return st;
  for (int y = 0; y < roi.height; y++) {
    Ipp8u *r = buf + (size_t)y * step;
    for (int x = 0; x < roi.width; x++)
      for (int c = 0; c < ch; c++)
        r[x * ch + c] = sat_u8(sfs_round_even(r[x * ch + c] + value[c], sfs));
  }
  return ippStsNoErr;
}
static IppStatus subc_ir(const Ipp8u *value, Ipp8u *buf, int step, IppiSize roi, int sfs, int ch) {
  IppStatus st = roi_chk2(value, buf, roi); if (st) return st;
  for (int y = 0; y < roi.height; y++) {
    Ipp8u *r = buf + (size_t)y * step;
    for (int x = 0; x < roi.width; x++)
      for (int c = 0; c < ch; c++)
        r[x * ch + c] = sat_u8(sfs_round_even(r[x * ch + c] - value[c], sfs));
  }
  return ippStsNoErr;
}
static IppStatus mulc_ir(const Ipp8u *value, Ipp8u *buf, int step, IppiSize roi, int sfs, int ch) {
  IppStatus st = roi_chk2(value, buf, roi); if (st) return st;
  for (int y = 0; y < roi.height; y++) {
    Ipp8u *r = buf + (size_t)y * step;
    for (int x = 0; x < roi.width; x++)
      for (int c = 0; c < ch; c++)
        r[x * ch + c] = sat_u8(sfs_round_even(r[x * ch + c] * value[c], sfs));
  }
  return ippStsNoErr;
}

IppStatus ippiAddC_8u_C3IRSfs(const Ipp8u *value, Ipp8u *pSrcDst, int srcDstStep, IppiSize roiSize, int scaleFactor) {
  return addc_ir(value, pSrcDst, srcDstStep, roiSize, scaleFactor, 3);
}
IppStatus ippiAddC_8u_C4IRSfs(const Ipp8u *value, Ipp8u *pSrcDst, int srcDstStep, IppiSize roiSize, int scaleFactor) {
  return addc_ir(value, pSrcDst, srcDstStep, roiSize, scaleFactor, 4);
}
IppStatus ippiSubC_8u_C3IRSfs(const Ipp8u *value, Ipp8u *pSrcDst, int srcDstStep, IppiSize roiSize, int scaleFactor) {
  return subc_ir(value, pSrcDst, srcDstStep, roiSize, scaleFactor, 3);
}
IppStatus ippiSubC_8u_C4IRSfs(const Ipp8u *value, Ipp8u *pSrcDst, int srcDstStep, IppiSize roiSize, int scaleFactor) {
  return subc_ir(value, pSrcDst, srcDstStep, roiSize, scaleFactor, 4);
}
IppStatus ippiMulC_8u_C3IRSfs(const Ipp8u *value, Ipp8u *pSrcDst, int srcDstStep, IppiSize roiSize, int scaleFactor) {
  return mulc_ir(value, pSrcDst, srcDstStep, roiSize, scaleFactor, 3);
}

/* ---- ippiAlphaCompC_8u_C3R / C4R: アルファ合成。
      実 DLL (win) 実測 (work/fill fit2/fit5 + 全数 grid) による 6 モードの式:
        t0: round((s1*a1 + s2*co)/255),        co = round(a2*(255-a1)/255)
        t1: round(s1*a1*a2/65025)
        t2: round(s1*a1*(255-a2)/65025)
        t3: round((s1*a1*a2 + s2*a2*(255-a1))/65025)
        t4: round((s1*a1*(255-a2) + s2*a2*(255-a1))/65025)
        t5: round((s1*a1 + s2*a2)/255)
      除数 255/65025 は奇数ゆえ同数なし → round = (2x+d)/(2d)。255 を超えると飽和。
      alphaType 0..5 以外は実 DLL 観測どおり -50。FL の呼出実績は t0 (alpha2=0xff)。 ---- */
static inline unsigned rnd_div(unsigned x, unsigned d) { return (2u * x + d) / (2u * d); } /* d は奇数 */

static IppStatus alpha_compc(const Ipp8u *s1, int st1, Ipp8u a1, const Ipp8u *s2, int st2, Ipp8u a2,
                             Ipp8u *d, int dstep, IppiSize roi, int atype, int ch) {
  IppStatus st = roi_chk2(s1, s2, roi); if (st) return st;
  if (!d) return ippStsNullPtrErr;
  if (atype < 0 || atype > 5) return (-50); /* 実 DLL 観測 (probe: 99 → -50) */
  for (int y = 0; y < roi.height; y++) {
    const Ipp8u *r1 = s1 + (size_t)y * st1, *r2 = s2 + (size_t)y * st2;
    Ipp8u *dr = d + (size_t)y * dstep;
    for (int x = 0; x < roi.width; x++)
      for (int c = 0; c < ch; c++) {
        unsigned p = r1[x * ch + c], q = r2[x * ch + c];
        unsigned v;
        switch (atype) {
          case 0: { /* co を丸めず float 融合: (255*s1*a1 + s2*a2*(255-a1)) / 65025 (fit2 の co 表と全数一致) */
                    v = rnd_div(255u * p * a1 + q * a2 * (255u - a1), 65025u); break; }
          case 1: v = rnd_div(p * a1 * a2, 65025u); break;
          case 2: v = rnd_div(p * a1 * (255u - a2), 65025u); break;
          case 3: v = rnd_div(p * a1 * a2 + q * a2 * (255u - a1), 65025u); break;
          case 4: v = rnd_div(p * a1 * (255u - a2) + q * a2 * (255u - a1), 65025u); break;
          default: v = rnd_div(p * a1 + q * a2, 255u); break; /* t5 */
        }
        dr[x * ch + c] = (Ipp8u)(v > 255 ? 255 : v);
      }
  }
  return ippStsNoErr;
}
IppStatus ippiAlphaCompC_8u_C3R(const Ipp8u *pSrc1, int src1Step, Ipp8u alpha1, const Ipp8u *pSrc2, int src2Step, Ipp8u alpha2,
                                Ipp8u *pDst, int dstStep, IppiSize roiSize, int alphaType) {
  return alpha_compc(pSrc1, src1Step, alpha1, pSrc2, src2Step, alpha2, pDst, dstStep, roiSize, alphaType, 3);
}
IppStatus ippiAlphaCompC_8u_C4R(const Ipp8u *pSrc1, int src1Step, Ipp8u alpha1, const Ipp8u *pSrc2, int src2Step, Ipp8u alpha2,
                                Ipp8u *pDst, int dstStep, IppiSize roiSize, int alphaType) {
  return alpha_compc(pSrc1, src1Step, alpha1, pSrc2, src2Step, alpha2, pDst, dstStep, roiSize, alphaType, 4);
}

/* ---- 境界コピー: src ROI を (left,top) に置き, 外周を複製/定数で埋める。
      実 DLL 実測 (fit3): dstRoi が srcRoi + (left,top) より小さいと -6 (step は検査しない)。 ---- */
static IppStatus border_copy(const Ipp8u *s, int ss, IppiSize sroi, Ipp8u *d, int ds, IppiSize droi,
                             int top, int left, const Ipp8u *value, int ch, int replicate) {
  IppStatus st = roi_chk2(s, d, droi); if (st) return st;
  if (sroi.width < 1 || sroi.height < 1) return ippStsSizeErr;
  if (droi.width < sroi.width + left || droi.height < sroi.height + top) return ippStsSizeErr;
  if (top < 0 || left < 0) return IPP_STS_BADARG;
  for (int y = 0; y < droi.height; y++) {
    Ipp8u *dr = d + (size_t)y * ds;
    int sy = y - top;
    for (int x = 0; x < droi.width; x++) {
      int sx = x - left;
      for (int c = 0; c < ch; c++) {
        Ipp8u v;
        if (sx >= 0 && sx < sroi.width && sy >= 0 && sy < sroi.height)
          v = s[(size_t)sy * ss + (size_t)sx * ch + c];
        else if (replicate) {
          int cx = sx < 0 ? 0 : sx >= sroi.width ? sroi.width - 1 : sx;
          int cy = sy < 0 ? 0 : sy >= sroi.height ? sroi.height - 1 : sy;
          v = s[(size_t)cy * ss + (size_t)cx * ch + c];
        } else
          v = value[c];
        dr[x * ch + c] = v;
      }
    }
  }
  return ippStsNoErr;
}
IppStatus ippiCopyReplicateBorder_8u_C3R(const Ipp8u *pSrc, int srcStep, IppiSize srcRoiSize, Ipp8u *pDst, int dstStep,
                                         IppiSize dstRoiSize, int topBorderHeight, int leftBorderWidth) {
  return border_copy(pSrc, srcStep, srcRoiSize, pDst, dstStep, dstRoiSize, topBorderHeight, leftBorderWidth, NULL, 3, 1);
}
IppStatus ippiCopyReplicateBorder_8u_C4R(const Ipp8u *pSrc, int srcStep, IppiSize srcRoiSize, Ipp8u *pDst, int dstStep,
                                         IppiSize dstRoiSize, int topBorderHeight, int leftBorderWidth) {
  return border_copy(pSrc, srcStep, srcRoiSize, pDst, dstStep, dstRoiSize, topBorderHeight, leftBorderWidth, NULL, 4, 1);
}
IppStatus ippiCopyConstBorder_8u_C3R(const Ipp8u *pSrc, int srcStep, IppiSize srcRoiSize, Ipp8u *pDst, int dstStep,
                                     IppiSize dstRoiSize, int topBorderHeight, int leftBorderWidth, const Ipp8u *value) {
  return border_copy(pSrc, srcStep, srcRoiSize, pDst, dstStep, dstRoiSize, topBorderHeight, leftBorderWidth, value, 3, 0);
}
IppStatus ippiCopyConstBorder_8u_C4R(const Ipp8u *pSrc, int srcStep, IppiSize srcRoiSize, Ipp8u *pDst, int dstStep,
                                     IppiSize dstRoiSize, int topBorderHeight, int leftBorderWidth, const Ipp8u *value) {
  return border_copy(pSrc, srcStep, srcRoiSize, pDst, dstStep, dstRoiSize, topBorderHeight, leftBorderWidth, value, 4, 0);
}

/* ---- GetBufSize 系 (FilterBox/FilterRound): エラーコード返却 (CAB-134 検収決定)。
      Resize 系 2 関数は CAB-245 で実測式を実装 (impl/ipp_resize.c) のため移設済み。 ---- */
static IppStatus getsize_err(int *pSize) {
  if (!pSize) return ippStsNullPtrErr;
  return IPP_STS_NOTSUPPORT;
}
IppStatus ippiFilterBoxBorderGetBufferSize(IppiSize dstRoiSize, IppiSize maskSize, int dataType, int numChannels, int *pBufferSize) {
  (void)dstRoiSize; (void)maskSize;
  if (dataType != 1) return IPP_STS_BADARG; /* 実 DLL (arm64) は ipp8u 以外を拒否 */
  if (numChannels < 1 || numChannels > 4) return IPP_STS_BADARG;
  return getsize_err(pBufferSize);
}
IppStatus ippiFilterRoundGetBufSize32f_8u_C1R(IppiSize roiSize, IppiSize kernelSize, int *pBufferSize) {
  (void)roiSize; (void)kernelSize;
  return getsize_err(pBufferSize);
}
