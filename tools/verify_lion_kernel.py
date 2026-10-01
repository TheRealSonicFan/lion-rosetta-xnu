#!/usr/bin/python
from __future__ import print_function
import argparse,hashlib,struct,sys
OLD=b"/usr/libexec/oah/RosettaNonGrata\x00"
NEW_PATH=b"/usr/libexec/oah/translate\x00"
NEW=NEW_PATH+(b"\x00"*(len(OLD)-len(NEW_PATH)))
CPU_TYPE_I386=7; CPU_TYPE_X86_64=0x01000007
FAT_MAGIC=b"\xca\xfe\xba\xbe"; FAT_CIGAM=b"\xbe\xba\xfe\xca"
THIN_MAGICS={b"\xce\xfa\xed\xfe":"<",b"\xcf\xfa\xed\xfe":"<",b"\xfe\xed\xfa\xce":">",b"\xfe\xed\xfa\xcf":">"}
def arch_name(c): return "i386" if c==CPU_TYPE_I386 else ("x86_64" if c==CPU_TYPE_X86_64 else "cputype=0x%08x"%c)
def parse_slices(data):
 if len(data)<8: raise ValueError("file is too small to be a Mach-O kernel")
 m=data[:4]
 if m in (FAT_MAGIC,FAT_CIGAM):
  e=">" if m==FAT_MAGIC else "<"; n=struct.unpack(e+"I",data[4:8])[0]
  if n<1 or n>32 or 8+n*20>len(data): raise ValueError("invalid or truncated fat Mach-O architecture table")
  out=[]
  for i in range(n):
   off=8+i*20; c,sub,so,ss,align=struct.unpack(e+"IIIII",data[off:off+20])
   if so>len(data) or ss>len(data)-so: raise ValueError("fat Mach-O slice %d extends beyond end of file"%i)
   out.append({"cputype":c,"offset":so,"size":ss})
  return "fat",out
 if m in THIN_MAGICS:
  c=struct.unpack(THIN_MAGICS[m]+"I",data[4:8])[0]; return "thin",[{"cputype":c,"offset":0,"size":len(data)}]
 raise ValueError("input is not a recognized Mach-O or fat Mach-O kernel")
def find_all(data,n,start,end):
 out=[]; pos=start
 while True:
  pos=data.find(n,pos,end)
  if pos<0: break
  out.append(pos); pos+=len(n)
 return out
def main():
 p=argparse.ArgumentParser(); p.add_argument("kernel"); a=p.parse_args(); data=open(a.kernel,"rb").read()
 try: kind,slices=parse_slices(data)
 except ValueError as e: print("error: %s"%e,file=sys.stderr); return 2
 xs=[s for s in slices if s["cputype"] in (CPU_TYPE_I386,CPU_TYPE_X86_64)]
 if not xs: print("state: ambiguous; no x86 kernel slices found"); return 2
 print("sha256: %s"%hashlib.sha256(data).hexdigest()); print("size: %d"%len(data)); print("format: %s"%kind)
 states=[]; ro=[]; rn=[]
 for s in xs:
  st=s["offset"]; en=st+s["size"]; old=find_all(data,OLD,st,en); new=find_all(data,NEW,st,en); ro+=old; rn+=new
  state="unpatched" if len(old)==1 and len(new)==0 else ("patched" if len(old)==0 and len(new)==1 else "ambiguous")
  states.append(state); print("%s: offset=0x%x size=%d old=%d patched=%d state=%s"%(arch_name(s["cputype"]),st,s["size"],len(old),len(new),state))
 if sorted(find_all(data,OLD,0,len(data)))!=sorted(ro) or sorted(find_all(data,NEW,0,len(data)))!=sorted(rn): print("state: ambiguous; Rosetta signature outside recognized x86 kernel slices"); return 2
 if all(s=="patched" for s in states): print("state: Rosetta translate handler present in all x86 slices"); return 0
 if all(s=="unpatched" for s in states): print("state: unpatched Lion-style handler in all x86 slices"); return 1
 print("state: ambiguous or partially patched; do not install this kernel"); return 2
if __name__=="__main__": sys.exit(main())
