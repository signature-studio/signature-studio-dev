=== decomp 913450 -> FUN_00913450 @00913450 size=189

longlong FUN_00913450(longlong param_1,char param_2,undefined8 param_3,char param_4)

{
  
  local_20 = auStack_48;
  local_res8 = param_1;
  puVar1 = auStack_48;
  if (param_2 != '\0') {
    local_res8 = FUN_00410320(param_1,param_2);
    puVar1 = local_20;
  }
  local_20 = puVar1;
  FUN_0040f9e0(local_res8,0);
  FUN_004133f0(local_res8 + 8,param_3);
  *(undefined1 *)(local_res8 + 0x10) = 2;
  uVar2 = FUN_00511fe0(PTR_PTR_004cf268,1);
  *(undefined8 *)(local_res8 + 0x14) = uVar2;
  *(undefined4 *)(local_res8 + 0x1c) = 0;
  FUN_004133f0(local_res8 + 0x20,&LAB_0091355c);
  if (param_4 != '\0') {
    FUN_00913720(local_res8);
  }
  if (param_2 != '\0') {
    local_res8 = FUN_00410360(local_res8);
  }
  return local_res8;
}


=== decomp 913be0 -> FUN_00913be0 @00913be0 size=188

undefined4 FUN_00913be0(longlong param_1,undefined8 param_2,undefined4 param_3)

{
  
  local_40[0] = 0;
  local_30[0] = 0;
  iVar1 = (**(code **)(**(longlong **)(param_1 + 0x14) + 0x28))();
  iVar2 = 0;
  local_44 = param_3;
  if (-1 < iVar1 + -1) {
    do {
      (**(code **)(**(longlong **)(param_1 + 0x14) + 0x18))
                (*(longlong **)(param_1 + 0x14),local_40,iVar2);
      FUN_0065de10(local_30,local_40[0],param_2);
      if (local_30[0] != 0) {
        local_44 = FUN_0043aae0(local_30[0],param_3);
        break;
      }
      iVar2 = iVar2 + 1;
      iVar1 = iVar1 + -1;
    } while (iVar1 != 0);
  }
  FUN_00412d60(local_40);
  FUN_00412d60(local_30);
  return local_44;
}


=== decomp 913d40 -> FUN_00913d40 @00913d40 size=190

undefined8 FUN_00913d40(longlong param_1,undefined8 param_2,undefined8 param_3)

{
  
  local_40[0] = 0;
  local_30[0] = 0;
  FUN_00412d60(param_2);
  iVar1 = (**(code **)(**(longlong **)(param_1 + 0x14) + 0x28))();
  iVar2 = 0;
  if (-1 < iVar1 + -1) {
    do {
      (**(code **)(**(longlong **)(param_1 + 0x14) + 0x18))
                (*(longlong **)(param_1 + 0x14),local_40,iVar2);
      FUN_0065de10(local_30,local_40[0],param_3);
      if (local_30[0] != 0) {
        FUN_004133f0(param_2,local_30[0]);
        break;
      }
      iVar2 = iVar2 + 1;
      iVar1 = iVar1 + -1;
    } while (iVar1 != 0);
  }
  FUN_00412d60(local_40);
  FUN_00412d60(local_30);
  return param_2;
}


=== decomp 913a10 -> FUN_00913a10 @00913a10 size=114

undefined8 * FUN_00913a10(undefined8 param_1,undefined8 *param_2,undefined8 param_3)

{
  
  local_30 = auStack_58;
  local_20 = 0;
  FUN_00913d40(param_1,&local_20,param_3);
  if (local_20 == 0) {
    puVar1 = (undefined8 *)(PTR_DAT_015e1f60 + 8);
    *param_2 = *(undefined8 *)PTR_DAT_015e1f60;
    param_2[1] = *puVar1;
  }
  else {
    FUN_004391c0(param_2,local_20);
  }
  FUN_00412d60(&local_20);
  return param_2;
}


=== decomp 9139f0 -> FUN_009139f0 @009139f0 size=31

undefined8 FUN_009139f0(undefined8 param_1,undefined8 param_2)

{
  
  uVar1 = FUN_00913ae0(param_1,param_2,0);
  return uVar1;
}


=== decomp 913ae0 -> FUN_00913ae0 @00913ae0 size=193

undefined8 FUN_00913ae0(longlong param_1,undefined8 param_2,undefined8 param_3)

{
  
  local_40[0] = 0;
  local_30[0] = 0;
  iVar1 = (**(code **)(**(longlong **)(param_1 + 0x14) + 0x28))();
  iVar2 = 0;
  local_48 = param_3;
  if (-1 < iVar1 + -1) {
    do {
      (**(code **)(**(longlong **)(param_1 + 0x14) + 0x18))
                (*(longlong **)(param_1 + 0x14),local_40,iVar2);
      FUN_0065de10(local_30,local_40[0],param_2);
      if (local_30[0] != 0) {
        local_48 = FUN_0043abf0(local_30[0],param_3);
        break;
      }
      iVar2 = iVar2 + 1;
      iVar1 = iVar1 + -1;
    } while (iVar1 != 0);
  }
  FUN_00412d60(local_40);
  FUN_00412d60(local_30);
  return local_48;
}


=== decomp 913960 -> FUN_00913960 @00913960 size=31

undefined4 FUN_00913960(undefined8 param_1,undefined8 param_2)

{
  
  iVar1 = FUN_00913be0(param_1,param_2,0x20);
  if (iVar1 == 0x40) {
    uVar2 = 3;
  }
  else {
    uVar2 = 2;
  }
  return uVar2;
}


=== decomp 913980 -> FUN_00913980 @00913980 size=75

undefined1 FUN_00913980(undefined8 param_1,undefined8 param_2)

{
  
  local_10 = 0;
  FUN_00913d40(param_1,&local_10,param_2);
  uVar1 = FUN_0063b830(local_10);
  FUN_00412d60(&local_10);
  return uVar1;
}


=== decomp 913cd0 -> FUN_00913cd0 @00913cd0 size=75

undefined1 FUN_00913cd0(undefined8 param_1,undefined8 param_2)

{
  
  local_10 = 0;
  FUN_00913d40(param_1,&local_10,param_2);
  uVar1 = FUN_00910590(local_10);
  FUN_00412d60(&local_10);
  return uVar1;
}


=== decomp 9138a0 -> FUN_009138a0 @009138a0 size=132

undefined8 FUN_009138a0(longlong param_1,undefined8 param_2,undefined8 param_3,int param_4)

{
  
  local_10 = 0;
  if (*(int *)(param_1 + 0x1c) != param_4) {
    FUN_0043a7e0(&local_10,param_4);
    FUN_00414c70(param_1 + 0x20,&LAB_00913954,local_10);
    *(int *)(param_1 + 0x1c) = param_4;
  }
  FUN_00414c70(param_2,param_3,*(undefined8 *)(param_1 + 0x20));
  FUN_00412d60(&local_10);
  return param_2;
}


=== decomp 914780 -> FUN_00914780 @00914780 size=91

void FUN_00914780(undefined8 param_1,undefined8 param_2,int param_3,int param_4)

{
  
  local_10 = 0;
  if (param_3 != param_4) {
    FUN_0043a7e0(&local_10,param_3);
    FUN_00913360(param_1,param_2,local_10);
  }
  FUN_00412d60(&local_10);
  return;
}


=== decomp 914880 -> FUN_00914880 @00914880 size=53

void FUN_00914880(undefined8 param_1,undefined8 param_2,undefined8 param_3,undefined8 param_4)

{
  
  iVar1 = FUN_00414e70(param_3,param_4);
  if (iVar1 != 0) {
    FUN_00913360(param_1,param_2,param_3);
  }
  return;
}


=== decomp 913e60 -> FUN_00913e60 @00913e60 size=57

void FUN_00913e60(undefined8 param_1,undefined8 param_2,char param_3)

{
  
  uVar1 = 0x20;
  if (param_3 == '\x02') {
    uVar1 = 0x20;
  }
  else if (param_3 == '\x03') {
    uVar1 = 0x40;
  }
  FUN_00914780(param_1,param_2,uVar1,0);
  return;
}


=== decomp 913ea0 -> FUN_00913ea0 @00913ea0 size=79

void FUN_00913ea0(undefined8 param_1,undefined8 param_2,undefined1 param_3)

{
  
  local_10 = 0;
  FUN_0063b800(&local_10,param_3);
  FUN_00914880(param_1,param_2,local_10,0);
  FUN_00412d60(&local_10);
  return;
}


=== decomp 913f10 -> FUN_00913f10 @00913f10 size=45

void FUN_00913f10(undefined8 param_1,undefined8 param_2,longlong param_3,longlong param_4)

{
  if (param_3 != param_4) {
    FUN_00914700(param_1,param_2,param_3,0);
  }
  return;
}


=== decomp 914690 -> FUN_00914690 @00914690 size=78

void FUN_00914690(undefined8 param_1,undefined8 param_2,undefined8 param_3)

{
  
  local_10 = 0;
  FUN_00439300(&local_10,param_3);
  FUN_00914880(param_1,param_2,local_10,0);
  FUN_00412d60(&local_10);
  return;
}


=== decomp 914700 -> FUN_00914700 @00914700 size=96

void FUN_00914700(undefined8 param_1,undefined8 param_2,longlong param_3,longlong param_4)

{
  
  local_10 = 0;
  if (param_3 != param_4) {
    FUN_0043a820(&local_10,param_3);
    FUN_00913360(param_1,param_2,local_10);
  }
  FUN_00412d60(&local_10);
  return;
}


=== decomp 914800 -> FUN_00914800 @00914800 size=93

void FUN_00914800(undefined8 param_1,undefined8 param_2,char param_3,char param_4)

{
  
  local_10 = 0;
  if (param_3 != param_4) {
    FUN_00910530(&local_10,param_3);
    FUN_00914880(param_1,param_2,local_10,0);
  }
  FUN_00412d60(&local_10);
  return;
}


=== decomp 913e30 -> FUN_00913e30 @00913e30 size=37

void FUN_00913e30(longlong param_1)

{
  (**(code **)(**(longlong **)(param_1 + 0x14) + 0x100))
            (*(longlong **)(param_1 + 0x14),*(undefined8 *)(param_1 + 8));
  return;
}


=== decomp 913720 -> FUN_00913720 @00913720 size=113

void FUN_00913720(longlong param_1)

{
  
  local_30 = auStack_78;
  local_38 = 0;
  local_40 = 0;
  local_20[0] = 0;
  (**(code **)(**(longlong **)(param_1 + 0x14) + 0xd8))
            (*(longlong **)(param_1 + 0x14),*(undefined8 *)(param_1 + 8));
  FUN_00412e40(&local_40,2);
  FUN_00412d60(local_20);
  return;
}


=== decomp 913360 -> FUN_00913360 @00913360 size=189

void FUN_00913360(longlong param_1,undefined8 param_2,undefined8 param_3)

{
  
  local_20[0] = 0;
  local_40 = 0x11;
  local_30 = 0x11;
  local_48 = param_2;
  local_38 = param_3;
  FUN_0043dd60(local_20,L"%s=%s",&local_48,1);
  if (*(char *)(param_1 + 0x10) != '\x02') {
    iVar1 = FUN_009135f0(param_1,param_2);
    if (-1 < iVar1) {
      if (*(char *)(param_1 + 0x10) == '\x01') {
        (**(code **)(**(longlong **)(param_1 + 0x14) + 0x40))
                  (*(longlong **)(param_1 + 0x14),iVar1,local_20[0]);
      }
      goto LAB_0091340d;
    }
  }
  (**(code **)(**(longlong **)(param_1 + 0x14) + 0x78))(*(longlong **)(param_1 + 0x14),local_20[0]);
LAB_0091340d:
  FUN_00412d60(local_20);
  return;
}


=== decomp 65de10 -> FUN_0065de10 @0065de10 size=260

undefined8 FUN_0065de10(undefined8 param_1,short *param_2,undefined8 param_3)

{
  
  local_20 = 0;
  local_28 = 0;
  local_30 = 0;
  DAT_013e7629 = 0;
  FUN_00412d60(param_1);
  if ((param_2 != (short *)0x0) && (*param_2 != 0x27)) {
    iVar1 = FUN_004150d0(&LAB_0065df48,param_2,1);
    if (iVar1 != 0) {
      FUN_004394e0(&local_20,param_3);
      FUN_00414ec0(&local_30,param_2,1,iVar1 + -1);
      FUN_004394e0(&local_28,local_30);
      iVar2 = FUN_00414e70(local_20,local_28);
      if (iVar2 == 0) {
        DAT_013e7629 = 1;
        iVar2 = 0;
        if (param_2 != (short *)0x0) {
          iVar2 = *(int *)(param_2 + -2);
        }
        FUN_00414ec0(param_1,param_2,iVar1 + 1,iVar2 - iVar1);
      }
    }
  }
  FUN_00412e40(&local_30,3);
  return param_1;
}


=== decomp 4391c0 -> FUN_004391c0 @004391c0 size=307

void FUN_004391c0(longlong param_1,short *param_2)

{
  
  if (((((param_2 == (short *)0x0) || (*(int *)(param_2 + -2) != 0x26)) || (*param_2 != 0x7b)) ||
      ((param_2[9] != 0x2d || (param_2[0xe] != 0x2d)))) ||
     ((param_2[0x13] != 0x2d || ((param_2[0x18] != 0x2d || (param_2[0x25] != 0x7d)))))) {
LAB_004392ba:
    local_20 = 10;
    local_28 = param_2;
    uVar2 = FUN_00448f80(PTR_PTR_00430f20,1,PTR_LAB_015e3dd8,&local_28,0);
    FUN_00411e80(uVar2);
  }
  else {
    lVar4 = 0;
    pbVar7 = &DAT_013ab018;
    do {
      uVar1 = *(undefined4 *)(param_2 + *pbVar7);
      bVar5 = (byte)uVar1;
      sVar3 = (short)uVar1;
      if (9 < (ushort)(sVar3 - 0x30U)) {
        if ((5 < (ushort)(sVar3 - 0x41U)) && (5 < (ushort)(sVar3 - 0x61U))) goto LAB_004392ba;
        bVar5 = (bVar5 & 0xdf) - 7;
      }
      bVar6 = (byte)((uint)uVar1 >> 0x10);
      sVar3 = (short)((uint)uVar1 >> 0x10);
      if (9 < (ushort)(sVar3 - 0x30U)) {
        if ((5 < (ushort)(sVar3 - 0x41U)) && (5 < (ushort)(sVar3 - 0x61U))) goto LAB_004392ba;
        bVar6 = (bVar6 & 0xdf) - 7;
      }
      *(byte *)(param_1 + lVar4) = bVar5 * '\x10' + bVar6 + -0x30;
      lVar4 = lVar4 + 1;
      pbVar7 = pbVar7 + 1;
    } while (lVar4 != 0x10);
  }
  return;
}


=== decomp 439300 -> FUN_00439300 @00439300 size=126

undefined8 * FUN_00439300(undefined8 *param_1,longlong param_2)

{
  
  FUN_00414ad0(param_1,0x26);
  puVar1 = (undefined2 *)*param_1;
  *puVar1 = 0x7b;
  puVar1[9] = 0x2d;
  puVar1[0xe] = 0x2d;
  puVar1[0x13] = 0x2d;
  puVar1[0x18] = 0x2d;
  puVar1[0x25] = 0x7d;
  lVar2 = 0;
  pbVar3 = &DAT_013ab018;
  do {
    *(undefined4 *)(puVar1 + *pbVar3) =
         *(undefined4 *)(&DAT_013aabf8 + (ulonglong)*(byte *)(param_2 + lVar2) * 4);
    lVar2 = lVar2 + 1;
    pbVar3 = pbVar3 + 1;
  } while (lVar2 != 0x10);
  return param_1;
}


=== decomp 910590 -> FUN_00910590 @00910590 size=83

byte FUN_00910590(longlong param_1)

{
  
  bVar2 = DAT_009105e4;
  if (param_1 != 0) {
    uVar1 = FUN_0043aae0(param_1,0);
    if ((uVar1 & 1) == 1) {
      bVar2 = bVar2 | 1;
    }
    if ((uVar1 & 2) == 2) {
      bVar2 = bVar2 | 2;
    }
    if ((uVar1 & 0x10) == 0x10) {
      bVar2 = bVar2 | 4;
    }
    if ((uVar1 & 0x20) == 0x20) {
      bVar2 = bVar2 | 0x10;
    }
  }
  return bVar2;
}


=== decomp 910530 -> FUN_00910530 @00910530 size=89

undefined8 FUN_00910530(undefined8 param_1,byte param_2)

{
  
  bVar1 = (param_2 & 1) != 0;
  if ((param_2 & 2) != 0) {
    bVar1 = bVar1 | 2;
  }
  if ((param_2 & 4) != 0) {
    bVar1 = bVar1 | 0x10;
  }
  if ((param_2 & 0x10) != 0) {
    bVar1 = bVar1 | 0x20;
  }
  FUN_0043a7e0(param_1,bVar1);
  return param_1;
}


=== decomp 63b830 -> FUN_0063b830 @0063b830 size=77

char FUN_0063b830(undefined8 param_1)

{
  
  cVar2 = '\0';
  puVar3 = &DAT_013e4fe8;
  do {
    iVar1 = FUN_004397d0(param_1,*puVar3);
    if (iVar1 == 0) {
      return cVar2;
    }
    cVar2 = cVar2 + '\x01';
    puVar3 = puVar3 + 1;
  } while (cVar2 != '\x04');
  return '\0';
}


=== decomp 63b800 -> FUN_0063b800 @0063b800 size=40

undefined8 FUN_0063b800(undefined8 param_1,ulonglong param_2)

{
  FUN_004133f0(param_1,(&DAT_013e4fe8)[param_2 & 0xff]);
  return param_1;
}


