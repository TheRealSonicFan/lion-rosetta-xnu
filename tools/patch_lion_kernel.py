#!/usr/bin/python
from __future__ import print_function
import argparse, hashlib, os, struct, sys
OLD=b"/usr/libexec/oah/RosettaNonGrata\x00"
NEW_PATH=b"/usr/libexec/oah/translate\x00"
NEW=NEW_PATH+(b"\x00"*(len(OLD)-len(NEW_PATH)))
CPU_TYPE_I386=7
CPU_TYPE_X86_64=0x01000007
FAT_MAGIC=b"\xca\xfe\xba\xbe"
FAT_CIGAM=b"\xbe\xba\xfe\xca"
THIN_MAGICS={b"\xce\xfa\xed\xfe":"<",b"\xcf\xfa\xed\xfe":"<",b"\xfe\xed\xfa\xce":">",b"\xfe\xed\xfa\xcf":">"}
def sha256_bytes(data):
 h=hashlib.sha256(); h.update(data); return h.hexdigest()
def arch_name(c):
 return "i386" if c==CPU_TYPE_I386 else ("x86_64" if c==CPU_TYPE_X86_64 else "cputype=0x%08x"%c)
def parse_slices(data):
 if len(data)<8: raise ValueError("file is too small to be a Mach-O kernel")
 magic=data[:4]
 if magic in (FAT_MAGIC,FAT_CIGAM):
  endian=">" if magic==FAT_MAGIC else "<"
  nfat=struct.unpack(endian+"I",data[4:8])[0]
  if nfat<1 or nfat>32: raise ValueError("invalid fat Mach-O architecture count: %d"%nfat)
  if 8+nfat*20>len(data): raise ValueError("truncated fat Mach-O architecture table")
  out=[]
  for i in range(nfat):
   off=8+i*20
   c,sub,so,ss,align=struct.unpack(endian+"IIIII",data[off:off+20])
   if so>len(data) or ss>len(data)-so: raise ValueError("fat Mach-O slice %d extends beyond end of file"%i)
   out.append({"index":i,"cputype":c,"offset":so,"size":ss})
  return "fat",out
 if magic in THIN_MAGICS:
  c=struct.unpack(THIN_MAGICS[magic]+"I",data[4:8])[0]
  return "thin",[{"index":0,"cputype":c,"offset":0,"size":len(data)}]
 raise ValueError("input is not a recognized Mach-O or fat Mach-O kernel")
def find_all(data,needle,start,end):
 out=[]; pos=start
 while True:
  pos=data.find(needle,pos,end)
  if pos<0: break
  out.append(pos); pos+=len(needle)
 return out
def main():
 p=argparse.ArgumentParser(description="Patch Mac OS X Lion mach_kernel x86 slices to select Rosetta translate instead of RosettaNonGrata.")
 p.add_argument("input"); p.add_argument("output"); a=p.parse_args()
 ip=os.path.abspath(a.input); op=os.path.abspath(a.output)
 if ip==op: p.error("refusing to overwrite the input kernel")
 data=open(ip,"rb").read()
 try: kind,slices=parse_slices(data)
 except ValueError as e: print("error: %s"%e,file=sys.stderr); return 2
 xs=[s for s in slices if s["cputype"] in (CPU_TYPE_I386,CPU_TYPE_X86_64)]
 if not xs: print("error: no i386 or x86_64 kernel slices found",file=sys.stderr); return 2
 positions=[]; print("kernel_format   %s"%kind)
 for s in xs:
  start=s["offset"]; end=start+s["size"]
  old=find_all(data,OLD,start,end); new=find_all(data,NEW,start,end)
  print("slice           %s offset=0x%x size=%d old=%d patched=%d"%(arch_name(s["cputype"]),start,s["size"],len(old),len(new)))
  if len(old)!=1 or len(new)!=0:
   print("error: expected exactly one unpatched Rosetta handler in %s slice; found old=%d patched=%d"%(arch_name(s["cputype"]),len(old),len(new)),file=sys.stderr); return 2
  positions.extend(old)
 if sorted(find_all(data,OLD,0,len(data)))!=sorted(positions):
  print("error: found RosettaNonGrata signature(s) outside recognized x86 kernel slices",file=sys.stderr); return 2
 patched=data
 for pos in sorted(positions,reverse=True): patched=patched[:pos]+NEW+patched[pos+len(OLD):]
 if len(patched)!=len(data): print("internal error: kernel size changed",file=sys.stderr); return 4
 for s in xs:
  start=s["offset"]; end=start+s["size"]
  if find_all(patched,OLD,start,end): print("internal error: old signature remains in %s slice"%arch_name(s["cputype"]),file=sys.stderr); return 5
  if len(find_all(patched,NEW,start,end))!=1: print("internal error: patched signature count is not one in %s slice"%arch_name(s["cputype"]),file=sys.stderr); return 6
 outdir=os.path.dirname(op) or "."
 if not os.path.isdir(outdir): print("error: output directory does not exist: %s"%outdir,file=sys.stderr); return 7
 open(op,"wb").write(patched)
 try: os.chmod(op,os.stat(ip).st_mode & 0o7777)
 except Exception: pass
 print("patched_slices  %d"%len(xs)); print("input_sha256   %s"%sha256_bytes(data)); print("output_sha256  %s"%sha256_bytes(patched)); print("input_size      %d"%len(data)); print("output_size     %d"%len(patched)); print("patched         %s"%op)
 return 0
if __name__=="__main__": sys.exit(main())
