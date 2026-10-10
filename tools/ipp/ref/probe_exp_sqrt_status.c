/* 探索用: Exp/Sqrt_A11 の戻りステータス (overflow=12, underflow=17, sqrt 負引数=19) を観測した probe。 */
#include "pe_load.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static float fb(uint32_t b){float f;memcpy(&f,&b,4);return f;}
int main(int argc,char**argv){
  PE pe; pe_load(argv[1],&pe); ((int (MS*)(uint64_t))pe_export(&pe,"ippSetCpuFeatures"))(~0ULL);
  int (MS*ex)(const float*,float*,int)=pe_export(&pe,"ippsExp_32f_A11");
  int (MS*sq)(const float*,float*,int)=pe_export(&pe,"ippsSqrt_32f_A11");
  float xs[]={0,1,88.f,88.72f,88.73f,89.f,100.f,-80.f,-87.f,-88.f,-90.f,-103.f,-104.f,-110.f,INFINITY,-INFINITY,NAN,fb(0xFFC00001),1e-40f,-0.f,-1.f};
  for(unsigned i=0;i<sizeof xs/sizeof*xs;i++){ float d[4]; for(int k=0;k<4;k++){} float s[4]={xs[i],xs[i],xs[i],xs[i]}; int st=ex(s,d,4); printf("exp(%g): st=%d out=%g exp=%g\n",xs[i],st,d[0],expf(xs[i])); }
  for(unsigned i=0;i<sizeof xs/sizeof*xs;i++){ float d[4]; float s[4]={xs[i],xs[i],xs[i],xs[i]}; int st=sq(s,d,4); printf("sqrt(%g): st=%d out=%g\n",xs[i],st,d[0]); }
  return 0;}
