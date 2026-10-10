/* 探索用: 実 IPP の MulC/AddC の ±0 短絡 (x*0 → +0 全埋め, AddC v=+0 → copy) を観測した probe。ipp_min.c の短絡実装の根拠。 */
#include "pe_load.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static float fb(uint32_t b){float f;memcpy(&f,&b,4);return f;}
static uint32_t bf(float f){uint32_t b;memcpy(&b,&f,4);return b;}
int main(int argc,char**argv){
  PE pe; pe_load(argv[1],&pe); ((int (MS*)(uint64_t))pe_export(&pe,"ippSetCpuFeatures"))(~0ULL);
  int (MS*mc)(float,float*,int)=pe_export(&pe,"ippsMulC_32f_I");
  int (MS*ac)(const float*,float,float*,int)=pe_export(&pe,"ippsAddC_32f");
  int (MS*mulc)(const float*,float,float*,int)=pe_export(&pe,"ippsMulC_32f");
  float vals[]={0.f,-0.f,1.f,-1.f,0.5f,1e-40f,1e30f,INFINITY,NAN};
  float xs[]={0.f,-0.f,1.f,-1.f,3.f,1e-40f,-1e-40f,INFINITY,-INFINITY,NAN};
  printf("MulC_32f_I: mismatches vs IEEE (x*v):\n");
  for(int a=0;a<9;a++)for(int b=0;b<10;b++){ float x[16]; for(int i=0;i<16;i++)x[i]=xs[b]; mc(vals[a],x,16); float e=xs[b]*vals[a]; for(int i=0;i<16;i++) if(bf(x[i])!=bf(e)&&!(e!=e&&x[i]!=x[i])){ printf("  v=%g(%08x) x=%g(%08x) -> ipp %08x ieee %08x idx %d\n",vals[a],bf(vals[a]),xs[b],bf(xs[b]),bf(x[i]),bf(e),i); break;} }
  printf("AddC_32f mismatches vs IEEE:\n");
  for(int a=0;a<9;a++)for(int b=0;b<10;b++){ float x[16],d[16]; for(int i=0;i<16;i++)x[i]=xs[b]; ac(x,vals[a],d,16); float e=xs[b]+vals[a]; for(int i=0;i<16;i++) if(bf(d[i])!=bf(e)&&!(e!=e&&d[i]!=d[i])){ printf("  v=%g(%08x) x=%g(%08x) -> ipp %08x ieee %08x idx %d\n",vals[a],bf(vals[a]),xs[b],bf(xs[b]),bf(d[i]),bf(e),i); break;} }
  printf("MulC_32f mismatches vs IEEE:\n");
  for(int a=0;a<9;a++)for(int b=0;b<10;b++){ float x[16],d[16]; for(int i=0;i<16;i++)x[i]=xs[b]; mulc(x,vals[a],d,16); float e=xs[b]*vals[a]; for(int i=0;i<16;i++) if(bf(d[i])!=bf(e)&&!(e!=e&&d[i]!=d[i])){ printf("  v=%g(%08x) x=%g(%08x) -> ipp %08x ieee %08x idx %d\n",vals[a],bf(vals[a]),xs[b],bf(xs[b]),bf(d[i]),bf(e),i); break;} }
  return 0;}
