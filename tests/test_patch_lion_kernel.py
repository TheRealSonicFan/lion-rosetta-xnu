from __future__ import print_function
import os,shutil,struct,subprocess,sys,tempfile,unittest
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); PATCHER=os.path.join(ROOT,"tools","patch_lion_kernel.py"); VERIFIER=os.path.join(ROOT,"tools","verify_lion_kernel.py")
OLD=b"/usr/libexec/oah/RosettaNonGrata\x00"; NEW_PATH=b"/usr/libexec/oah/translate\x00"; NEW=NEW_PATH+(b"\x00"*(len(OLD)-len(NEW_PATH)))
I386=7; X64=0x01000007
def thin(c,payload):
 magic=b"\xce\xfa\xed\xfe" if c==I386 else b"\xcf\xfa\xed\xfe"; return magic+struct.pack("<I",c)+(b"\x00"*24)+payload
def fat(slices):
 hs=8+20*len(slices); off=hs; es=[]; body=[]
 for c,b in slices:
  es.append(struct.pack(">IIIII",c,3,off,len(b),0)); body.append(b); off+=len(b)
 return b"\xca\xfe\xba\xbe"+struct.pack(">I",len(slices))+b"".join(es)+b"".join(body)
class T(unittest.TestCase):
 def setUp(self): self.d=tempfile.mkdtemp()
 def tearDown(self): shutil.rmtree(self.d)
 def runp(self,data):
  src=os.path.join(self.d,"in"); dst=os.path.join(self.d,"out"); open(src,"wb").write(data); p=subprocess.Popen([sys.executable,PATCHER,src,dst],stdout=subprocess.PIPE,stderr=subprocess.PIPE); o,e=p.communicate(); return p.returncode,dst,o,e
 def runv(self,path):
  p=subprocess.Popen([sys.executable,VERIFIER,path],stdout=subprocess.PIPE,stderr=subprocess.PIPE); o,e=p.communicate(); return p.returncode,o,e
 def test_thin(self):
  orig=thin(X64,b"AAA"+OLD+b"BBB"); rc,dst,o,e=self.runp(orig); self.assertEqual(rc,0,e); out=open(dst,"rb").read(); self.assertEqual(len(out),len(orig)); self.assertEqual(out.count(OLD),0); self.assertEqual(out.count(NEW),1); self.assertEqual(self.runv(dst)[0],0)
 def test_fat_two_slices(self):
  orig=fat([(I386,thin(I386,b"I"+OLD)),(X64,thin(X64,b"X"+OLD))]); self.assertEqual(orig.count(OLD),2); rc,dst,o,e=self.runp(orig); self.assertEqual(rc,0,e); out=open(dst,"rb").read(); self.assertEqual(out.count(OLD),0); self.assertEqual(out.count(NEW),2); self.assertEqual(self.runv(dst)[0],0)
 def test_missing(self):
  rc,dst,o,e=self.runp(thin(X64,b"none")); self.assertEqual(rc,2); self.assertFalse(os.path.exists(dst))
 def test_ambiguous_in_slice(self):
  rc,dst,o,e=self.runp(thin(X64,OLD+OLD)); self.assertEqual(rc,2); self.assertFalse(os.path.exists(dst))
 def test_extra_non_x86(self):
  orig=fat([(I386,thin(I386,OLD)),(X64,thin(X64,OLD)),(18,b"PPC"+OLD)]); rc,dst,o,e=self.runp(orig); self.assertEqual(rc,2); self.assertFalse(os.path.exists(dst))
if __name__=="__main__": unittest.main()
