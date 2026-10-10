/* 探索用: VectorSlope の実 IPP 出力ダンプ (ブロック累積方式の観測)。ISA 経路に依存しない決定的出力だが bit 再現は未解決。 */
#include "pe_load.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char**argv){
  PE pe; pe_load(argv[1],&pe); ((int (MS*)(uint64_t))pe_export(&pe,"ippSetCpuFeatures"))(strtoull(argv[2],0,0));
  int (MS*vs)(float*,int,float,float)=pe_export(&pe,"ippsVectorSlope_32f");
  float offs[]={0.5f,0.f,65536.f,-0.00375f,1.f,0.1f}; float sls[]={0.3f,1.f,0.3f,0.1f,1.2345678f,0.7f}; int ns[]={40,64,37,200,129,33};
  for(int k=0;k<6;k++){ int n=ns[k]; static float d[512]; vs(d,n,offs[k],sls[k]); printf("%.9g %.9g %d",offs[k],sls[k],n); for(int i=0;i<n;i++){uint32_t b;memcpy(&b,&d[i],4);printf(" %08x",b);} printf("\n"); }
  return 0;}
