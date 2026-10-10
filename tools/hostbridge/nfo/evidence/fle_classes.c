=== decomp 8ef860 -> FUN_008ef860 @008ef860 size=706

undefined8 FUN_008ef860(undefined8 param_1,int param_2,char param_3)

{
  FUN_00412d60(param_1);
  if (param_2 < 8) {
    if (param_2 == 7) {
      if (param_3 == '\0') {
        FUN_004133f0(param_1,L"VST3 (fx)");
      }
      else {
        FUN_004133f0(param_1,L"VST3");
      }
    }
    else if (param_2 < 4) {
      if (param_2 == 3) {
        if (param_3 == '\0') {
          FUN_004133f0(param_1,L"FL (gen)");
        }
        else {
          FUN_004133f0(param_1,&DAT_008efba0);
        }
      }
      else if (param_2 == 0) {
        if (param_3 == '\0') {
          FUN_004133f0(param_1,L"VST (fx)");
        }
        else {
          FUN_004133f0(param_1,&DAT_008efb30);
        }
      }
      else if (param_2 == 1) {
        if (param_3 == '\0') {
          FUN_004133f0(param_1,L"DirectX (fx)");
        }
        else {
          FUN_004133f0(param_1,&DAT_008efb64);
        }
      }
      else if (param_2 == 2) {
        if (param_3 == '\0') {
          FUN_004133f0(param_1,L"FL (fx)");
        }
        else {
          FUN_004133f0(param_1,&DAT_008efba0);
        }
      }
    }
    else if (param_2 == 4) {
      if (param_3 == '\0') {
        FUN_004133f0(param_1,L"VST (gen)");
      }
      else {
        FUN_004133f0(param_1,L"VSTi");
      }
    }
    else if (param_2 == 5) {
      if (param_3 == '\0') {
        FUN_004133f0(param_1,L"DirectX (gen)");
      }
      else {
        FUN_004133f0(param_1,&DAT_008efc28);
      }
    }
  }
  else if (param_2 < 0xb) {
    if (param_2 == 10) {
      if (param_3 == '\0') {
        FUN_004133f0(param_1,L"AudioUnit (gen)");
      }
      else {
        FUN_004133f0(param_1,&DAT_008efcc0);
      }
    }
    else if (param_2 == 8) {
      if (param_3 == '\0') {
        FUN_004133f0(param_1,L"VST3 (gen)");
      }
      else {
        FUN_004133f0(param_1,L"VST3");
      }
    }
    else if (param_2 == 9) {
      if (param_3 == '\0') {
        FUN_004133f0(param_1,L"AudioUnit (fx)");
      }
      else {
        FUN_004133f0(param_1,&DAT_008efcc0);
      }
    }
  }
  else if (param_2 == 0xb) {
    if (param_3 == '\0') {
      FUN_004133f0(param_1,L"CLAP (fx)");
    }
    else {
      FUN_004133f0(param_1,L"CLAP");
    }
  }
  else if (param_2 == 0xc) {
    if (param_3 == '\0') {
      FUN_004133f0(param_1,L"CLAP (gen)");
    }
    else {
      FUN_004133f0(param_1,L"CLAP");
    }
  }
  return param_1;
}


=== decomp 8f0300 -> FUN_008f0300 @008f0300 size=323

undefined8 FUN_008f0300(undefined8 param_1,undefined8 param_2,ulonglong param_3)

{
  
  uVar2 = (uint)param_2;
  bVar1 = (byte)param_2;
  if (uVar2 < 8) {
    uVar3 = (int)CONCAT71((int7)(param_3 >> 8),1) << (bVar1 & 0x1f);
    param_3 = (ulonglong)uVar3;
    bVar4 = ((byte)uVar3 & DAT_008f0444) != 0;
  }
  else {
    bVar4 = false;
  }
  if (bVar4) {
    FUN_004133f0(param_1,L"Fruity\\");
  }
  else {
    if (uVar2 < 8) {
      uVar3 = (int)CONCAT71((int7)(param_3 >> 8),1) << (bVar1 & 0x1f);
      param_3 = (ulonglong)uVar3;
      bVar4 = ((byte)uVar3 & DAT_008f0464) != 0;
    }
    else {
      bVar4 = false;
    }
    if (bVar4) {
      FUN_004133f0(param_1,L"VST\\");
    }
    else {
      if (uVar2 < 0x10) {
        uVar3 = (int)CONCAT62((int6)(param_3 >> 0x10),1) << (bVar1 & 0x1f);
        param_3 = (ulonglong)uVar3;
        bVar4 = ((ushort)uVar3 & DAT_008f047e) != 0;
      }
      else {
        bVar4 = false;
      }
      if (bVar4) {
        FUN_004133f0(param_1,L"VST3\\");
      }
      else {
        if (uVar2 - 8 < 8) {
          bVar4 = ((byte)((int)CONCAT71((int7)(param_3 >> 8),1) << ((byte)(uVar2 - 8) & 0x1f)) &
                  DAT_008f0498) != 0;
        }
        else {
          bVar4 = false;
        }
        if (bVar4) {
          FUN_004133f0(param_1,L"AudioUnit\\");
        }
        else {
          if (uVar2 - 8 < 8) {
            bVar4 = ((byte)((int)CONCAT71((int7)((ulonglong)param_2 >> 8),1) <<
                           ((byte)(uVar2 - 8) & 0x1f)) & DAT_008f04be) != 0;
          }
          else {
            bVar4 = false;
          }
          if (bVar4) {
            FUN_004133f0(param_1,L"CLAP\\");
          }
          else {
            FUN_00412d60(param_1);
          }
        }
      }
    }
  }
  return param_1;
}


=== decomp 8f0ab0 -> FUN_008f0ab0 @008f0ab0 size=257

int FUN_008f0ab0(char param_1,int param_2)

{
  if (param_2 < 8) {
    if (param_2 == 7) {
      if (param_1 == '\0') {
        param_2 = 8;
      }
    }
    else if (param_2 < 4) {
      if (param_2 == 3) {
        if (param_1 != '\0') {
          param_2 = 2;
        }
      }
      else if (param_2 == 0) {
        if (param_1 == '\0') {
          param_2 = 4;
        }
      }
      else if (param_2 == 1) {
        if (param_1 == '\0') {
          param_2 = 5;
        }
      }
      else if ((param_2 == 2) && (param_1 == '\0')) {
        param_2 = 3;
      }
    }
    else if (param_2 == 4) {
      if (param_1 != '\0') {
        param_2 = 0;
      }
    }
    else if ((param_2 == 5) && (param_1 != '\0')) {
      param_2 = 1;
    }
  }
  else if (param_2 < 0xb) {
    if (param_2 == 10) {
      if (param_1 != '\0') {
        param_2 = 9;
      }
    }
    else if (param_2 == 8) {
      if (param_1 != '\0') {
        param_2 = 7;
      }
    }
    else if ((param_2 == 9) && (param_1 == '\0')) {
      param_2 = 10;
    }
  }
  else if (param_2 == 0xb) {
    if (param_1 == '\0') {
      param_2 = 0xc;
    }
  }
  else if ((param_2 == 0xc) && (param_1 != '\0')) {
    param_2 = 0xb;
  }
  return param_2;
}


=== decomp 8f0bc0 -> FUN_008f0bc0 @008f0bc0 size=89

int FUN_008f0bc0(int param_1)

{
  if (param_1 < 9) {
    if (param_1 == 8) {
      param_1 = 7;
    }
    else if (param_1 == 3) {
      param_1 = 2;
    }
    else if (param_1 == 4) {
      param_1 = 0;
    }
    else if (param_1 == 5) {
      param_1 = 1;
    }
  }
  else if (param_1 == 10) {
    param_1 = 9;
  }
  else if (param_1 == 0xc) {
    param_1 = 0xb;
  }
  return param_1;
}


=== decomp 8f6990 -> FUN_008f6990 @008f6990 size=306

undefined8 FUN_008f6990(undefined8 param_1,undefined8 param_2,char param_3,ulonglong param_4)

{
  
  uVar1 = 0xffffffff;
  bVar3 = (byte)param_2;
  if (((char)bVar3 < '\0') || (7 < bVar3)) {
    bVar5 = false;
  }
  else {
    uVar4 = (int)CONCAT71((int7)(param_4 >> 8),1) << (bVar3 & 0x1f);
    param_4 = (ulonglong)uVar4;
    bVar5 = ((byte)uVar4 & DAT_008f6ac4) != 0;
  }
  if (bVar5) {
    if (param_3 == '\x03') {
      uVar1 = 1;
    }
    else {
      uVar1 = 0;
    }
  }
  else {
    if (((char)bVar3 < '\0') || (7 < bVar3)) {
      bVar5 = false;
    }
    else {
      uVar4 = (int)CONCAT71((int7)(param_4 >> 8),1) << (bVar3 & 0x1f);
      param_4 = (ulonglong)uVar4;
      bVar5 = ((byte)uVar4 & DAT_008f6ac5) != 0;
    }
    if (bVar5) {
      if (param_3 == '\x03') {
        uVar1 = 3;
      }
      else {
        uVar1 = 2;
      }
    }
    else {
      if (((char)bVar3 < '\0') || (0xf < bVar3)) {
        bVar5 = false;
      }
      else {
        uVar4 = (int)CONCAT62((int6)(param_4 >> 0x10),1) << (bVar3 & 0x1f);
        param_4 = (ulonglong)uVar4;
        bVar5 = ((ushort)uVar4 & DAT_008f6ac6) != 0;
      }
      if (bVar5) {
        if (param_3 == '\x03') {
          uVar1 = 5;
        }
        else {
          uVar1 = 4;
        }
      }
      else {
        bVar2 = bVar3 - 8;
        if (((char)bVar2 < '\0') || (7 < bVar2)) {
          bVar5 = false;
        }
        else {
          bVar5 = ((byte)((int)CONCAT71((int7)(param_4 >> 8),1) << (bVar2 & 0x1f)) & DAT_008f6ac8)
                  != 0;
        }
        if (bVar5) {
          if (param_3 == '\x03') {
            uVar1 = 6;
          }
        }
        else {
          bVar3 = bVar3 - 8;
          if (((char)bVar3 < '\0') || (7 < bVar3)) {
            bVar5 = false;
          }
          else {
            bVar5 = ((byte)((int)CONCAT71((int7)((ulonglong)param_2 >> 8),1) << (bVar3 & 0x1f)) &
                    DAT_008f6ac9) != 0;
          }
          if ((bVar5) && (param_3 == '\x03')) {
            uVar1 = 7;
          }
        }
      }
    }
  }
  return uVar1;
}


=== decomp 8f0740 -> FUN_008f0740 @008f0740 size=683

longlong * FUN_008f0740(longlong *param_1,undefined8 param_2)

{
  
  local_50 = 0;
  local_48 = 0;
  local_40 = 0;
  local_38 = 0;
  local_30 = 0;
  local_28 = 0;
  local_20 = 0;
  local_18 = 0;
  local_10 = 0;
  FUN_004133f0(param_1,param_2);
  FUN_0044bc50(&local_10,*param_1,&DAT_008f0a18,&DAT_008f0a28,DAT_008f0a2c);
  FUN_004133f0(param_1,local_10);
  FUN_0044bc50(&local_18,*param_1,&DAT_008f0a3c,&DAT_008f0a28,DAT_008f0a2c);
  FUN_004133f0(param_1,local_18);
  FUN_0044bc50(&local_20,*param_1,&DAT_008f0a4c,&DAT_008f0a28,DAT_008f0a2c);
  FUN_004133f0(param_1,local_20);
  FUN_0044bc50(&local_28,*param_1,&DAT_008f0a5c,&DAT_008f0a28,DAT_008f0a2c);
  FUN_004133f0(param_1,local_28);
  FUN_0044bc50(&local_30,*param_1,&DAT_008f0a6c,&DAT_008f0a28,DAT_008f0a2c);
  FUN_004133f0(param_1,local_30);
  FUN_0044bc50(&local_38,*param_1,&DAT_008f0a7c,&DAT_008f0a28,DAT_008f0a2c);
  FUN_004133f0(param_1,local_38);
  FUN_0044bc50(&local_40,*param_1,&DAT_008f0a8c,&DAT_008f0a28,DAT_008f0a2c);
  FUN_004133f0(param_1,local_40);
  FUN_0044bc50(&local_48,*param_1,&DAT_008f0a9c,&DAT_008f0a28,DAT_008f0a2c);
  FUN_004133f0(param_1,local_48);
  FUN_0044bc50(&local_50,*param_1,&DAT_008f0aac,&DAT_008f0a28,DAT_008f0a2c);
  FUN_004133f0(param_1,local_50);
  if ((*param_1 != 0) && (*(short *)*param_1 == 0x2e)) {
    puVar1 = (undefined2 *)FUN_00413760(param_1);
    *puVar1 = 0x2d;
  }
  FUN_00412e40(&local_50,9);
  return param_1;
}


=== decomp 8f19b0 -> FUN_008f19b0 @008f19b0 size=171

undefined8 FUN_008f19b0(undefined8 param_1,undefined8 param_2,undefined8 param_3,undefined8 param_4)

{
  
  local_10 = 0;
  FUN_00439550(&local_10,param_3);
  if (local_10 != 0) {
    iVar1 = 0;
    if (local_10 != 0) {
      iVar1 = *(int *)(local_10 + -4);
    }
    if (*(short *)(local_10 + -2 + (longlong)iVar1 * 2) == 0x5c) {
      iVar1 = 0;
      if (local_10 != 0) {
        iVar1 = *(int *)(local_10 + -4);
      }
      FUN_00414ec0(&local_10,local_10,1,iVar1 + -1);
    }
  }
  FUN_0044bc50(param_1,param_2,param_4,local_10,DAT_008f1a78);
  FUN_00412d60(&local_10);
  return param_1;
}


=== decomp 8f1820 -> FUN_008f1820 @008f1820 size=351

undefined8 FUN_008f1820(undefined8 param_1,longlong param_2,longlong param_3,longlong param_4)

{
  
  local_40 = 0;
  local_38 = 0;
  local_30[0] = 0;
  local_20[0] = 0;
  if (((param_2 == 0) || (param_3 == 0)) || (param_4 == 0)) {
    FUN_004133f0(param_1,param_2);
  }
  else {
    FUN_00439550(local_20,param_3);
    if (local_20[0] != 0) {
      iVar2 = 0;
      if (local_20[0] != 0) {
        iVar2 = *(int *)(local_20[0] + -4);
      }
      if (*(short *)(local_20[0] + -2 + (longlong)iVar2 * 2) == 0x5c) {
        iVar2 = 0;
        if (local_20[0] != 0) {
          iVar2 = *(int *)(local_20[0] + -4);
        }
        FUN_00414ec0(local_20,local_20[0],1,iVar2 + -1);
      }
    }
    FUN_00439550(local_30,local_20[0]);
    uVar1 = local_30[0];
    FUN_00439550(&local_38,param_2);
    iVar2 = FUN_004150d0(uVar1,local_38,1);
    if (iVar2 == 1) {
      iVar2 = 0;
      if (local_20[0] != 0) {
        iVar2 = *(int *)(local_20[0] + -4);
      }
      FUN_00414ec0(&local_40,param_2,iVar2 + 1,0x7fffffff);
      FUN_00414c70(param_1,param_4,local_40);
    }
    else {
      FUN_004133f0(param_1,param_2);
    }
  }
  FUN_00412e40(&local_40,3);
  FUN_00412d60(local_20);
  return param_1;
}


=== decomp 8f0c20 -> FUN_008f0c20 @008f0c20 size=148

undefined4 FUN_008f0c20(undefined8 param_1)

{
  
  local_20[0] = 0;
  local_10 = 0;
  FUN_0043c8f0(local_20,param_1);
  FUN_004394e0(&local_10,local_20[0]);
  iVar1 = FUN_00414e70(local_10,L".VST3");
  if (iVar1 == 0) {
    local_24 = 7;
  }
  else {
    iVar1 = FUN_00414e70(local_10,L".COMPONENT");
    if (iVar1 == 0) {
      local_24 = 9;
    }
    else {
      local_24 = 0;
    }
  }
  FUN_00412d60(local_20);
  FUN_00412d60(&local_10);
  return local_24;
}


=== decomp 8f0d30 -> FUN_008f0d30 @008f0d30 size=805

undefined8
FUN_008f0d30(undefined8 param_1,undefined8 param_2,uint param_3,char param_4,byte param_5)

{
  
  local_60 = 0;
  local_68 = 0;
  local_70 = 0;
  local_78 = 0;
  local_80 = 0;
  local_20[0] = 0;
  local_28 = 0;
  local_30 = 0;
  local_38 = 0;
  local_40 = 0;
  if (param_4 == '\0') {
    local_58[0] = 0x565354;
  }
  else {
    local_58[0] = 0x565345;
  }
  local_50 = 0;
  FUN_0043dd60(local_20,L"%.6x",local_58,0);
  local_50 = 0;
  local_58[0] = param_3;
  FUN_0043dd60(&local_28,L"%.8x",local_58,0);
  FUN_00414c70(&local_30,local_20[0],local_28);
  FUN_00439550(&local_38,param_2);
  FUN_00412d60(&local_40);
  iVar2 = 0;
  do {
    iVar1 = 0;
    if (local_38 != 0) {
      iVar1 = *(int *)(local_38 + -4);
    }
    if (iVar2 < iVar1) {
      local_58[0] = (uint)*(byte *)(local_38 + -2 + (longlong)(iVar2 + 1) * 2);
    }
    else {
      local_58[0] = 0;
    }
    local_50 = 0;
    FUN_0043dd60(&local_40,L"%.2x",local_58,0);
    FUN_00414bb0(&local_30,local_40);
    iVar2 = iVar2 + 1;
  } while (iVar2 != 9);
  if ((param_5 & 1) == 0) {
    FUN_00414ec0(&local_60,local_30,1,8);
    FUN_00414ec0(&local_68,local_30,9,4);
    FUN_00414ec0(&local_70,local_30,0xd,4);
    FUN_00414ec0(&local_78,local_30,0x11,4);
    FUN_00414ec0(&local_80,local_30,0x15,0x7fffffff);
    FUN_00414da0(&local_30,9,local_60,&DAT_008f10e8,local_68,&DAT_008f10e8,local_70,&DAT_008f10e8,
                 local_78,&DAT_008f10e8,local_80);
    FUN_00414da0(&local_30,3,&DAT_008f10f8,local_30,&DAT_008f1108);
  }
  FUN_004133f0(param_1,local_30);
  FUN_00412e40(&local_80,5);
  FUN_00412e40(&local_40,5);
  return param_1;
}


=== decomp 8f1110 -> FUN_008f1110 @008f1110 size=160

void FUN_008f1110(undefined8 param_1,undefined4 param_2,undefined8 *param_3,undefined1 param_4)

{
  
  local_40 = auStack_78;
  local_20 = 0;
  puVar1 = (undefined8 *)(PTR_DAT_015e1f60 + 8);
  *param_3 = *(undefined8 *)PTR_DAT_015e1f60;
  param_3[1] = *puVar1;
  local_58 = DAT_008f1208;
  FUN_008f0d30(&local_20,param_1,param_2,param_4);
  FUN_004391c0(&local_30,local_20);
  *param_3 = local_30;
  param_3[1] = uStack_28;
  FUN_00412d60(&local_20);
  return;
}


=== decomp 8f6dc0 -> FUN_008f6dc0 @008f6dc0 size=129

undefined8 * FUN_008f6dc0(longlong param_1,undefined8 *param_2)

{
  
  if (*(uint *)(param_1 + 0x18) < 8) {
    bVar2 = ((byte)((int)CONCAT71((int7)((ulonglong)param_2 >> 8),1) <<
                   ((byte)*(uint *)(param_1 + 0x18) & 0x1f)) & DAT_008f6e44) != 0;
  }
  else {
    bVar2 = false;
  }
  if ((bVar2) && (*(int *)(param_1 + 0x20) != 0)) {
    cVar1 = IsEqualGUID(param_1 + 0x24,PTR_DAT_015e1f60);
    if ((cVar1 != '\0') && (*(longlong *)(param_1 + 8) != 0)) {
      FUN_008f1110(*(undefined8 *)(param_1 + 8),*(undefined4 *)(param_1 + 0x20),param_1 + 0x24,0);
    }
  }
  *param_2 = *(undefined8 *)(param_1 + 0x24);
  param_2[1] = *(undefined8 *)(param_1 + 0x2c);
  return param_2;
}


=== decomp 8f6380 -> FUN_008f6380 @008f6380 size=106

ulonglong FUN_008f6380(undefined8 param_1,undefined8 param_2)

{
  
  uVar4 = (undefined7)((ulonglong)unaff_RSI >> 8);
  uVar3 = CONCAT71(uVar4,2);
  uVar1 = FUN_008f5ca0(param_1);
  if ((uVar1 & 1) == 0) goto LAB_008f63e0;
  lVar2 = FUN_008f5e70(param_1);
  if (*(short *)(lVar2 + 0x1c) == 1) {
LAB_008f63d8:
    uVar3 = 0;
  }
  else {
    if (*(short *)(lVar2 + 0x1c) == 0) {
      if (*(uint *)(lVar2 + 0x18) < 0x10) {
        bVar5 = ((ushort)((int)CONCAT62((int6)((ulonglong)param_2 >> 0x10),1) <<
                         ((byte)*(uint *)(lVar2 + 0x18) & 0x1f)) & DAT_008f63ec) != 0;
      }
      else {
        bVar5 = false;
      }
      if (bVar5) goto LAB_008f63d8;
    }
    uVar3 = CONCAT71(uVar4,1);
  }
LAB_008f63e0:
  return uVar3 & 0xffffffff;
}


=== decomp 8f64f0 -> FUN_008f64f0 @008f64f0 size=106

ulonglong FUN_008f64f0(undefined8 param_1,undefined8 param_2)

{
  
  uVar4 = (undefined7)((ulonglong)unaff_RSI >> 8);
  uVar3 = CONCAT71(uVar4,2);
  uVar1 = FUN_008f5ca0(param_1);
  if ((uVar1 & 1) == 0) goto LAB_008f6550;
  lVar2 = FUN_008f5e70(param_1);
  if (*(short *)(lVar2 + 0x1c) == 2) {
LAB_008f6548:
    uVar3 = 0;
  }
  else {
    if (*(short *)(lVar2 + 0x1c) == 0) {
      if (*(uint *)(lVar2 + 0x18) < 0x10) {
        bVar5 = ((ushort)((int)CONCAT62((int6)((ulonglong)param_2 >> 0x10),1) <<
                         ((byte)*(uint *)(lVar2 + 0x18) & 0x1f)) & DAT_008f655c) != 0;
      }
      else {
        bVar5 = false;
      }
      if (bVar5) goto LAB_008f6548;
    }
    uVar3 = CONCAT71(uVar4,1);
  }
LAB_008f6550:
  return uVar3 & 0xffffffff;
}


=== decomp 8f6110 -> FUN_008f6110 @008f6110 size=143

undefined1 FUN_008f6110(longlong param_1)

{
  
  local_40 = auStack_68;
  local_21 = 0;
  local_20 = (longlong *)0x0;
  local_20 = (longlong *)FUN_008fa140(*(undefined8 *)(param_1 + 8));
  do {
    cVar1 = thunk_FUN_008faa90(local_20);
    if (cVar1 == '\0') {
      if (local_20 == (longlong *)0x0) {
        return local_21;
      }
      (**(code **)(*local_20 + -0x20))(local_20,1);
      return local_21;
    }
    FUN_008fa940(local_20,local_38);
  } while ((*(byte *)(local_30 + 0x4c) & 1) == 0);
  local_21 = 1;
  FUN_008f61a0(0,local_40);
  return local_21;
}


=== decomp 8f6050 -> FUN_008f6050 @008f6050 size=143

undefined1 FUN_008f6050(longlong param_1)

{
  
  local_40 = auStack_68;
  local_21 = 0;
  local_20 = (longlong *)0x0;
  local_20 = (longlong *)FUN_008fa140(*(undefined8 *)(param_1 + 8));
  do {
    cVar1 = thunk_FUN_008faa90(local_20);
    if (cVar1 == '\0') {
      if (local_20 == (longlong *)0x0) {
        return local_21;
      }
      (**(code **)(*local_20 + -0x20))(local_20,1);
      return local_21;
    }
    FUN_008fa940(local_20,local_38);
  } while ((*(byte *)(local_30 + 0x4c) & 2) != 0);
  local_21 = 1;
  FUN_008f60e0(0,local_40);
  return local_21;
}


=== decomp 8f6560 -> FUN_008f6560 @008f6560 size=143

undefined1 FUN_008f6560(longlong param_1)

{
  
  local_40 = auStack_68;
  local_21 = 0;
  local_20 = (longlong *)0x0;
  local_20 = (longlong *)FUN_008fa140(*(undefined8 *)(param_1 + 8));
  do {
    cVar1 = thunk_FUN_008faa90(local_20);
    if (cVar1 == '\0') {
      if (local_20 == (longlong *)0x0) {
        return local_21;
      }
      (**(code **)(*local_20 + -0x20))(local_20,1);
      return local_21;
    }
    FUN_008fa940(local_20,local_38);
  } while ((*(byte *)(local_30 + 0x4c) & 8) == 0);
  local_21 = 1;
  FUN_008f65f0(0,local_40);
  return local_21;
}


=== decomp 8f5cd0 -> FUN_008f5cd0 @008f5cd0 size=41

void FUN_008f5cd0(longlong param_1,undefined8 param_2,undefined8 param_3,undefined8 param_4)

{
  
  uVar1 = FUN_008f6990(param_1);
  FUN_008fa020(*(undefined8 *)(param_1 + 8),uVar1,param_4);
  return;
}


=== decomp 8f49e0 -> FUN_008f49e0 @008f49e0 size=299

void FUN_008f49e0(longlong param_1,longlong param_2,char param_3)

{
  
  local_20[0] = 0;
  uVar2 = FUN_008f6990(param_1,*(undefined1 *)(param_2 + 0x18),*(undefined1 *)(param_2 + 0x1e));
  cVar1 = FUN_008fa080(*(undefined8 *)(param_1 + 8),uVar2);
  if (cVar1 != '\0') {
    FUN_008f9ec0(*(undefined8 *)(param_1 + 8),uVar2);
  }
  FUN_008f9e30(*(undefined8 *)(param_1 + 8),uVar2,param_2);
  if ((*(longlong *)(*(longlong *)(param_1 + 8) + 0x10) == 1) &&
     (*(longlong *)(param_1 + 0x18) == 0)) {
    if (*(longlong *)(param_2 + 8) == 0) {
      if (*(longlong *)(param_2 + 0x10) != 0) {
        FUN_00661970(local_20,*(undefined8 *)(param_2 + 0x10));
        FUN_004133f0(param_1 + 0x18,local_20[0]);
      }
    }
    else {
      FUN_004133f0(param_1 + 0x18,*(undefined8 *)(param_2 + 8));
    }
  }
  FUN_008f67e0(param_1,*(undefined4 *)(param_2 + 0x18),*(undefined1 *)(param_2 + 0x1e),
               *(undefined8 *)(param_2 + 0x10),0);
  FUN_008f5300(param_1);
  if (param_3 != '\0') {
    FUN_008f4b50(param_1);
  }
  FUN_00412d60(local_20);
  return;
}


=== decomp 8f4b50 -> FUN_008f4b50 @008f4b50 size=510

void FUN_008f4b50(longlong param_1)

{
  
  local_40 = auStack_e8;
  local_48 = 0;
  local_c0 = 0;
  local_38 = 0;
  FUN_00412d60(param_1 + 0x20);
  local_20 = (longlong *)0x0;
  local_20 = (longlong *)FUN_008fa140(*(undefined8 *)(param_1 + 8));
  while( true ) {
    cVar1 = thunk_FUN_008faa90(local_20);
    if (cVar1 == '\0') break;
    FUN_008fa940(local_20,local_30);
    FUN_00412d60(&local_38);
    cVar1 = IsEqualGUID(local_28 + 0x24,PTR_DAT_015e1f60);
    if (cVar1 == '\0') {
      FUN_00439300(&local_38,local_28 + 0x24);
    }
    if (local_38 == 0) {
      FUN_00413480(&local_38,*(undefined8 *)(local_28 + 0x60));
    }
    local_b8[0] = FUN_008f0bc0(*(undefined4 *)(local_28 + 0x18));
    local_b0 = 0;
    FUN_00439550(&local_c0,*(undefined8 *)(local_28 + 0x10));
    local_a8 = local_c0;
    local_a0 = 0x11;
    local_98 = (uint)*(byte *)(local_28 + 0x1e);
    local_90 = 0;
    local_88 = (uint)*(byte *)(local_28 + 0x1f);
    local_80 = 0;
    local_78 = *(undefined4 *)(local_28 + 0x20);
    local_70 = 0;
    local_68 = local_38;
    local_60 = 0x11;
    local_58 = *(undefined8 *)(local_28 + 8);
    local_50 = 0x11;
    FUN_0043dd60(&local_48,L"|%d|%s|%d|%d|%d|%s|%s",local_b8,6);
    FUN_00414bb0(param_1 + 0x20,local_48);
  }
  if (local_20 != (longlong *)0x0) {
    (**(code **)(*local_20 + -0x20))(local_20,1);
  }
  FUN_00412d60(&local_c0);
  FUN_00412d60(&local_48);
  FUN_00412d60(&local_38);
  return;
}


