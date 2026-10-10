=== decomp 770a80 -> FUN_00770a80 @00770a80 size=440

void FUN_00770a80(longlong param_1)

{
  char cVar1;
  longlong lVar2;
  longlong lVar3;
  undefined8 local_48;
  undefined8 local_40 [2];
  undefined8 local_30;
  undefined8 local_28;
  longlong local_20 [2];
  
  local_48 = 0;
  local_40[0] = 0;
  local_20[0] = 0;
  local_28 = 0;
  local_30 = 0;
  lVar2 = FUN_0040eb90(PTR_DAT_00770908,1);
  if (lVar2 == 0) {
    lVar3 = 0;
  }
  else {
    lVar3 = lVar2 + 0x10;
  }
  FUN_004196a0(&local_30,lVar3);
  *(longlong *)(lVar2 + 0x18) = param_1;
  *(undefined8 *)(*(longlong *)(param_1 + 0x7c0) + 200) = 0;
  FUN_00411f10(local_20);
  cVar1 = *(char *)(*(longlong *)(lVar2 + 0x18) + 0x761);
  if (cVar1 == '\x02') {
    FUN_00765db0(local_40);
    FUN_00413c60(local_20,local_40[0],*(undefined8 *)PTR_PTR_008f7448);
  }
  else {
    if (cVar1 != '\x03') {
      *(undefined1 *)(*(longlong *)(lVar2 + 0x18) + 0x94) = 0;
      goto LAB_00770c0c;
    }
    FUN_00765db0(&local_48);
    FUN_00413c60(local_20,local_48,*(undefined8 *)PTR_PTR_008f6718);
  }
  if (local_20[0] != 0) {
    cVar1 = FUN_006f7550(local_20[0]);
    if (cVar1 != '\0') {
      FUN_00765bf0(&local_28,*(undefined8 *)(*(longlong *)(*(longlong *)(lVar2 + 0x18) + 0x7c0) + 8)
                   ,(*(uint *)(*(longlong *)(lVar2 + 0x18) + 0x4c0) & 8) == 8);
      if (lVar2 == 0) {
        lVar3 = 0;
      }
      else {
        lVar3 = lVar2 + 0x20;
      }
      FUN_00765dd0(*(undefined8 *)PTR_DAT_008f6a00,local_20[0],local_28,lVar3);
      FUN_0075d1e0(*(undefined8 *)(*(longlong *)(lVar2 + 0x18) + 0x7c0),5000);
      if (*(char *)(*(longlong *)(*(longlong *)(lVar2 + 0x18) + 0x7c0) + 0x10) != '\0') {
        FUN_00770060(*(longlong *)(lVar2 + 0x18));
      }
    }
  }
  *(undefined1 *)(*(longlong *)(lVar2 + 0x18) + 0x94) = 0;
LAB_00770c0c:
  FUN_00411ff0(&local_48,2);
  FUN_00419660(&local_30);
  FUN_00411ff0(&local_28,2);
  return;
}


=== decomp 76f3f0 -> FUN_0076f3f0 @0076f3f0 size=198

undefined1 FUN_0076f3f0(undefined8 param_1,uint *param_2)

{
  uint uVar1;
  char cVar2;
  longlong lVar3;
  bool bVar4;
  undefined1 local_21;
  undefined8 local_20 [2];
  
  local_20[0] = 0;
  local_21 = 0;
  uVar1 = *param_2;
  if (uVar1 < 8) {
    bVar4 = ((byte)((int)CONCAT71((int7)((ulonglong)param_2 >> 8),1) << ((byte)uVar1 & 0x1f)) &
            DAT_0076f4d8) != 0;
  }
  else {
    bVar4 = false;
  }
  if (bVar4) {
    local_21 = 2;
  }
  else {
    bVar4 = false;
    lVar3 = FUN_0076c8e0(*(undefined8 *)PTR_DAT_008f7800,uVar1);
    if (lVar3 != 0) {
      bVar4 = (*(ushort *)(lVar3 + 0x1c) & 2) != 0;
    }
    if (bVar4) {
      FUN_00413930(local_20,(longlong)param_2 + 0x20e,0x105);
      cVar2 = FUN_005bfe50(local_20[0]);
      if (cVar2 == '\x06') {
        local_21 = 3;
      }
      else if (cVar2 == '\a') {
        local_21 = 2;
      }
    }
  }
  FUN_00411f10(local_20);
  return local_21;
}


=== decomp 76f320 -> FUN_0076f320 @0076f320 size=168

undefined1 FUN_0076f320(undefined8 param_1,uint *param_2)

{
  uint uVar1;
  longlong lVar2;
  bool bVar3;
  undefined1 local_21;
  undefined8 local_20 [2];
  
  local_20[0] = 0;
  local_21 = 0;
  uVar1 = *param_2;
  if (uVar1 < 8) {
    bVar3 = ((byte)((int)CONCAT71((int7)((ulonglong)param_2 >> 8),1) << ((byte)uVar1 & 0x1f)) &
            DAT_0076f3e8) != 0;
  }
  else {
    bVar3 = false;
  }
  if (!bVar3) {
    bVar3 = false;
    lVar2 = FUN_0076c8e0(*(undefined8 *)PTR_DAT_008f7800,uVar1);
    if (lVar2 != 0) {
      bVar3 = (*(ushort *)(lVar2 + 0x1c) & 2) != 0;
    }
    if (bVar3) {
      FUN_00413930(local_20,(longlong)param_2 + 0x20e,0x105);
      local_21 = FUN_005c0080(local_20[0]);
    }
  }
  FUN_00411f10(local_20);
  return local_21;
}


=== decomp 7729c0 -> FUN_007729c0 @007729c0 size=581

undefined8 FUN_007729c0(undefined8 param_1,int *param_2,longlong *param_3,char param_4)

{
  int iVar1;
  char cVar2;
  char local_49;
  undefined8 local_48;
  undefined8 local_40;
  undefined8 local_38;
  undefined8 local_30;
  longlong local_28;
  undefined8 local_20 [2];
  
  local_48 = 0;
  local_40 = 0;
  local_20[0] = 0;
  local_28 = 0;
  local_30 = 0;
  local_38 = 0;
  iVar1 = *param_2;
  FUN_0074b040(local_20,iVar1,1);
  if ((iVar1 == 0) || (iVar1 == 4)) {
    if (param_3 != (longlong *)0x0) {
      if (*(char *)((longlong)param_3 + 0x757) == '\0') {
        FUN_00412630(local_20,&DAT_00772c50);
      }
      else {
        FUN_00412630(local_20,L"VSTi");
      }
      (**(code **)(*param_3 + 0x2b0))(param_3,&local_40);
      FUN_00413d90(local_20,3,local_20[0],&DAT_00772c64,local_40);
    }
  }
  else if ((iVar1 - 7U < 2) && (param_3 != (longlong *)0x0)) {
    (**(code **)(*param_3 + 0x2b0))(param_3,&local_48);
    FUN_004381f0(&local_28,local_48);
    if (local_28 != 0) {
      FUN_00412630(local_20,local_28);
    }
  }
  FUN_00411f10(&local_30);
  local_49 = param_4;
  if (param_3 != (longlong *)0x0) {
    local_49 = *(char *)((longlong)param_3 + 0x761);
  }
  if (local_49 == '\x02') {
    FUN_00412630(&local_30,L"32bit");
  }
  else if (local_49 == '\x03') {
    FUN_00412630(&local_30,L"64bit");
  }
  cVar2 = FUN_0040f040(param_3,PTR_PTR_0076e6e0);
  if (cVar2 == '\0') {
    FUN_00412630(&local_38,L"native");
  }
  else {
    FUN_00412630(&local_38,L"bridged");
  }
  FUN_00413d90(param_1,6,local_20[0],&DAT_00772ce0,local_30,&DAT_00772cf4,local_38,&LAB_00772d08);
  FUN_00411ff0(&local_48,6);
  return param_1;
}


=== decomp 5bfe50 -> FUN_005bfe50 @005bfe50 size=99

undefined1 FUN_005bfe50(undefined8 param_1)

{
  char cVar1;
  undefined1 auStack_48 [40];
  undefined1 *local_20;
  undefined1 local_11;
  undefined8 local_10;
  
  local_20 = auStack_48;
  local_11 = 0;
  cVar1 = FUN_00439ba0(param_1,1);
  if (cVar1 != '\0') {
    local_10 = FUN_00502130(PTR_PTR_004c64a8,1,param_1,0x40);
    local_11 = FUN_005bfc30(local_10);
    FUN_0040ec50(local_10);
  }
  return local_11;
}


