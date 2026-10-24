import re,time,logging
from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.sign_pythonrsa import PythonRSASigner
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
signer=PythonRSASigner.FromRSAKeyPath('/keys/adbkey')
last=None
initialized=False
while True:
 d=None
 try:
  d=AdbDeviceTcp('192.168.0.111',5555,default_transport_timeout_s=8)
  d.connect(rsa_keys=[signer],auth_timeout_s=8)
  logging.info('Connected to projector; monitoring Apple TV CEC standby')
  while True:
   hdmi=d.shell('dumpsys hdmi_control',read_timeout_s=8)
   events=[s.strip() for s in hdmi.splitlines()
    if '[R]' in s and '<Standby>' in s
    and re.search(r'src: 4, dst: (0|15)\b',s)]
   event=events[-1] if events else None
   if not initialized:
    last=event
    initialized=True
   elif event and event!=last:
    last=event
    power=d.shell('dumpsys power',read_timeout_s=8)
    if 'mWakefulness=Awake' in power:
     # Fixed installation: Apple TV on HDMI 1, CEC source 4.
     logging.info('New Apple TV standby; putting projector to sleep')
     d.shell('input keyevent KEYCODE_SLEEP',read_timeout_s=8)
   time.sleep(2)
 except Exception as e:
  logging.warning('Connection retry: %s',type(e).__name__)
  time.sleep(5)
 finally:
  if d:
   try:d.close()
   except Exception:pass
