=== decomp 7ad040 -> FUN_007ad040 @007ad040 size=179

void FUN_007ad040(longlong param_1,undefined8 param_2,undefined8 param_3,undefined4 param_4)

{
  FUN_007b2280(param_1,*(undefined1 *)(param_1 + 0x755));
  if (*(char *)(param_1 + 0x755) != '\0') {
    (**(code **)(*(longlong *)(param_1 + 0x9b4) + 8))
              (*(longlong *)(param_1 + 0x9b4),0x19,0,0,*(undefined8 *)(param_1 + 0x8c0),DAT_007ad0f4
              );
  }
  if ((*(uint *)(param_1 + 0x758) & 0x100) == 0) {
    (**(code **)(*(longlong *)(param_1 + 0x9b4) + 0x10))
              (*(longlong *)(param_1 + 0x9b4),param_2,param_3,param_4);
  }
  else {
    (**(code **)(*(longlong *)(param_1 + 0x9b4) + 0x78))
              (*(longlong *)(param_1 + 0x9b4),param_2,param_3,param_4);
  }
  FUN_007b3300(param_1);
  return;
}


=== decomp 7acfa0 -> FUN_007acfa0 @007acfa0 size=152

void FUN_007acfa0(longlong param_1,undefined8 *param_2,undefined8 *param_3,undefined4 param_4)

{
  longlong lVar1;
  
  FUN_007b2280(param_1,*(undefined1 *)(param_1 + 0x755));
  if (*(char *)(param_1 + 0x755) != '\0') {
    (**(code **)(*(longlong *)(param_1 + 0x9b4) + 8))
              (*(longlong *)(param_1 + 0x9b4),0x19,0,0,*(undefined8 *)(param_1 + 0x8c0),DAT_007ad038
              );
  }
  lVar1 = *(longlong *)(param_1 + 0x9b4);
  if ((*(uint *)(lVar1 + 0x38) & 0x80000000) != 0) {
    (**(code **)(lVar1 + 0x78))(lVar1,*param_2,*param_3,param_4);
  }
  FUN_007b3300(param_1);
  return;
}


=== decomp 7ac960 -> FUN_007ac960 @007ac960 size=89

ulonglong FUN_007ac960(longlong param_1,undefined4 param_2)

{
  ulonglong uVar1;
  
  uVar1 = (ulonglong)DAT_007ac9bc;
  if (*(longlong *)(param_1 + 0x9b4) != 0) {
    FUN_005bf650();
    FUN_005bf680();
    uVar1 = (**(code **)(*(longlong *)(param_1 + 0x9b4) + 0x20))
                      (*(longlong *)(param_1 + 0x9b4),param_2);
    FUN_005bf650();
    FUN_005bf680();
  }
  return uVar1;
}


=== decomp 7afab0 -> FUN_007afab0 @007afab0 size=223

void FUN_007afab0(longlong param_1,undefined4 param_2,undefined4 param_3,undefined1 param_4,
                 undefined1 param_5)

{
  undefined1 *puVar1;
  undefined1 auStack_58 [32];
  undefined1 local_38;
  undefined1 *local_20;
  
  local_20 = auStack_58;
  puVar1 = auStack_58;
  if (*(longlong *)(param_1 + 0x9b4) != 0) {
    puVar1 = auStack_58;
    if (*(char *)(param_1 + 0x96) != '\0') {
      (**(code **)(**(longlong **)(param_1 + 0x78) + 0x68))(*(longlong **)(param_1 + 0x78),1);
      puVar1 = local_20;
    }
    local_20 = puVar1;
    FUN_005bf650();
    FUN_005bf680();
    (**(code **)(*(longlong *)(param_1 + 0x9b4) + 0x18))
              (*(longlong *)(param_1 + 0x9b4),param_2,param_3);
    FUN_005bf650();
    FUN_005bf680();
    if (*(char *)(param_1 + 0x96) != '\0') {
      (**(code **)(**(longlong **)(param_1 + 0x78) + 0x68))(*(longlong **)(param_1 + 0x78),0);
    }
    FUN_00745480(param_1,param_4);
    puVar1 = local_20;
  }
  local_20 = puVar1;
  local_38 = param_5;
  FUN_00745040(param_1,param_2,param_3,param_4);
  return;
}


=== decomp 7ac880 -> FUN_007ac880 @007ac880 size=208

undefined8 FUN_007ac880(longlong param_1,undefined8 param_2,int param_3)

{
  longlong *plVar1;
  int iVar2;
  undefined1 local_229 [521];
  
  FUN_00411f10(param_2);
  if ((-1 < param_3) && (param_3 < *(int *)(param_1 + 0x70c))) {
    plVar1 = *(longlong **)(param_1 + 0x8e4);
    if ((plVar1 != (longlong *)0x0) &&
       (iVar2 = (**(code **)(*plVar1 + 0x28))(plVar1), param_3 < iVar2)) {
      (**(code **)(**(longlong **)(param_1 + 0x8e4) + 0x18))
                (*(longlong **)(param_1 + 0x8e4),param_2,param_3);
      return param_2;
    }
    (**(code **)PTR_DAT_008f6868)(local_229,0x201);
    (**(code **)(*(longlong *)(param_1 + 0x9b4) + 8))
              (*(longlong *)(param_1 + 0x9b4),8,param_3,0,local_229,DAT_007ac950);
    FUN_005bf650();
    FUN_005bf680();
    FUN_00413900(param_2,local_229,0x201);
  }
  return param_2;
}


