=== decomp 74a5b0 -> FUN_0074a5b0 @0074a5b0 size=21

void FUN_0074a5b0(undefined8 *param_1,undefined8 param_2,undefined1 param_3)

{
  *param_1 = param_2;
  *(undefined1 *)(param_1 + 1) = param_3;
  return;
}


=== decomp 74a8e0 -> FUN_0074a8e0 @0074a8e0 size=140

void FUN_0074a8e0(undefined8 *param_1,int *param_2)

{
  longlong *plVar1;
  undefined8 uVar2;
  int local_24;
  undefined8 local_20;
  
  plVar1 = (longlong *)*param_1;
  (**(code **)(*plVar1 + 0x30))(plVar1,&local_24,0xc);
  *param_2 = local_24;
  *(undefined8 *)(param_2 + 1) = local_20;
  uVar2 = FUN_00501350(plVar1);
  *(undefined8 *)(param_2 + 3) = uVar2;
  param_2[5] = local_24;
  *(undefined8 *)(param_2 + 6) = local_20;
  *(undefined8 *)(param_2 + 8) = *(undefined8 *)(param_2 + 3);
  if (local_24 == 0) {
    (**(code **)(*plVar1 + 0x30))(plVar1,&local_24,0xc);
    *param_2 = local_24;
    *(undefined8 *)(param_2 + 1) = local_20;
    uVar2 = FUN_00501350(plVar1);
    *(undefined8 *)(param_2 + 3) = uVar2;
  }
  return;
}


=== decomp 74a970 -> FUN_0074a970 @0074a970 size=200

ulonglong FUN_0074a970(undefined8 *param_1,ulonglong param_2,longlong param_3,int *param_4,
                      char param_5)

{
  ulonglong uVar1;
  ulonglong uVar2;
  
  uVar1 = 0;
  if (*param_4 != 0) {
    if ((param_5 != '\0') && (0 < (longlong)param_2)) {
      (**(code **)PTR_DAT_008f6868)(param_3,param_2 & 0xffffffff);
    }
    uVar2 = *(ulonglong *)(param_4 + 1);
    uVar1 = param_2;
    if ((longlong)uVar2 < (longlong)param_2) {
      param_2 = uVar2;
      uVar1 = uVar2;
    }
    for (; 0 < (longlong)param_2; param_2 = param_2 - (longlong)(int)uVar2) {
      if ((longlong)param_2 < 0x80000000) {
        uVar2 = param_2 & 0xffffffff;
      }
      else {
        uVar2 = 0x7fffffff;
      }
      (**(code **)(*(longlong *)*param_1 + 0x30))((longlong *)*param_1,param_3,uVar2);
      param_3 = param_3 + (int)uVar2;
    }
    FUN_00501370(*param_1,*(longlong *)(param_4 + 3) + *(longlong *)(param_4 + 1));
  }
  return uVar1;
}


=== decomp 74aa40 -> FUN_0074aa40 @0074aa40 size=348

undefined8 FUN_0074aa40(undefined8 param_1,undefined8 *param_2,ulonglong param_3,char param_4)

{
  ulonglong uVar1;
  longlong lVar2;
  int iVar3;
  char local_39;
  longlong local_38;
  longlong local_30 [2];
  
  local_30[0] = 0;
  local_38 = 0;
  FUN_00411f10(param_1);
  if (0 < (longlong)param_3) {
    local_39 = param_4;
    if (param_4 == '\0') {
      if ((*(byte *)(param_2 + 1) & 1) == 0) {
        if ((*(byte *)(param_2 + 1) & 2) == 0) {
          local_39 = '\x01';
        }
        else {
          local_39 = '\x03';
        }
      }
      else {
        local_39 = '\x02';
      }
    }
    if (local_39 == '\x02') {
      uVar1 = (longlong)param_3 >> 1;
      if ((longlong)uVar1 < 0) {
        uVar1 = uVar1 + ((param_3 & 1) != 0);
      }
      FUN_00413ac0(local_30,uVar1 & 0xffffffff);
      lVar2 = local_30[0];
    }
    else {
      FUN_004131a0(&local_38,param_3,0);
      lVar2 = local_38;
    }
    for (; 0 < (longlong)param_3; param_3 = param_3 - (longlong)iVar3) {
      if ((longlong)param_3 < 0x80000000) {
        iVar3 = (int)param_3;
      }
      else {
        iVar3 = 0x7fffffff;
      }
      (**(code **)(*(longlong *)*param_2 + 0x30))((longlong *)*param_2,lVar2,iVar3);
      lVar2 = lVar2 + iVar3;
    }
    if (local_39 == '\x02') {
      FUN_004125a0(param_1,local_30[0]);
    }
    else if (local_39 == '\x03') {
      FUN_0041b530(param_1,local_38);
    }
    else {
      FUN_00413970(param_1,local_38);
    }
  }
  FUN_00411f60(&local_38);
  FUN_00411f10(local_30);
  return param_1;
}


=== decomp 74abd0 -> FUN_0074abd0 @0074abd0 size=29

void FUN_0074abd0(undefined8 *param_1,longlong param_2)

{
  FUN_00501370(*param_1,*(longlong *)(param_2 + 0x20) + *(longlong *)(param_2 + 0x18));
  return;
}


=== decomp 74a6a0 -> FUN_0074a6a0 @0074a6a0 size=146

undefined8 FUN_0074a6a0(undefined8 *param_1,undefined4 param_2,longlong param_3,longlong param_4)

{
  undefined8 uVar1;
  int iVar2;
  undefined4 local_34;
  longlong local_30;
  
  uVar1 = FUN_00501350(*param_1);
  local_34 = param_2;
  local_30 = param_3;
  (**(code **)(*(longlong *)*param_1 + 0x38))((longlong *)*param_1,&local_34,0xc);
  for (; 0 < param_3; param_3 = param_3 - iVar2) {
    if (param_3 < 0x80000000) {
      iVar2 = (int)param_3;
    }
    else {
      iVar2 = 0x7fffffff;
    }
    (**(code **)(*(longlong *)*param_1 + 0x38))((longlong *)*param_1,param_4,iVar2);
    param_4 = param_4 + iVar2;
  }
  return uVar1;
}


=== decomp 74a740 -> FUN_0074a740 @0074a740 size=373

void FUN_0074a740(undefined8 *param_1,undefined4 param_2,longlong param_3)

{
  int iVar1;
  int iVar2;
  longlong lVar3;
  longlong local_40;
  undefined4 local_34;
  longlong local_30;
  
  local_40 = 0;
  local_34 = param_2;
  if ((*(byte *)(param_1 + 1) & 1) == 0) {
    if ((*(byte *)(param_1 + 1) & 2) == 0) {
      FUN_00413280(&local_40,param_3,0);
    }
    else {
      FUN_0041b300(&local_40,param_3);
    }
    iVar2 = 0;
    if (local_40 != 0) {
      iVar2 = *(int *)(local_40 + -4);
    }
    local_30 = (longlong)iVar2;
    (**(code **)(*(longlong *)*param_1 + 0x38))((longlong *)*param_1,&local_34,0xc);
    iVar1 = 1;
    iVar2 = (int)local_30;
    if (0 < (int)local_30) {
      do {
        lVar3 = FUN_00412920(&local_40);
        (**(code **)(*(longlong *)*param_1 + 0x38))
                  ((longlong *)*param_1,lVar3 + -1 + (longlong)iVar1,1);
        iVar1 = iVar1 + 1;
        iVar2 = iVar2 + -1;
      } while (iVar2 != 0);
    }
  }
  else {
    iVar2 = 0;
    if (param_3 != 0) {
      iVar2 = *(int *)(param_3 + -4);
    }
    local_30 = (longlong)(iVar2 * 2);
    (**(code **)(*(longlong *)*param_1 + 0x38))((longlong *)*param_1,&local_34,0xc);
    for (lVar3 = local_30; 0 < lVar3; lVar3 = lVar3 - iVar2) {
      if (lVar3 < 0x80000000) {
        iVar2 = (int)lVar3;
      }
      else {
        iVar2 = 0x7fffffff;
      }
      (**(code **)(*(longlong *)*param_1 + 0x38))((longlong *)*param_1,param_3,iVar2);
      param_3 = param_3 + iVar2;
    }
  }
  FUN_00411f60(&local_40);
  return;
}


=== decomp 44acd0 -> FUN_0044acd0 @0044acd0 size=132

undefined8
FUN_0044acd0(undefined8 *param_1,undefined8 param_2,undefined2 param_3,undefined2 param_4)

{
  undefined8 local_18;
  undefined8 local_10;
  
  local_10 = 0;
  local_18 = 0;
  FUN_00413880(&local_10,param_3);
  FUN_00413880(&local_18,param_4);
  FUN_00447880(param_2,*param_1,local_10,local_18,DAT_0044ad7c);
  FUN_00411ff0(&local_18,2);
  return param_2;
}


