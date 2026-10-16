set pagination off
set architecture i386:x86-64
handle SIGUSR1 nostop noprint pass
set $n = 0
break *__ADDR__
commands
silent
set $n = $n + 1
printf "HIT n=%d dl=0x%02x rcx=0x%016lx ret=0x%016lx\n", $n, $dl, $rcx, *(unsigned long*)$rsp
if $n <= 40
  x/10gx $rcx - 0x20
  x/4gx $rsp
end
continue
end
continue
