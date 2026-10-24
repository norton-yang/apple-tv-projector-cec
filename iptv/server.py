import json,logging,os,re,threading,time,urllib.request,urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from collections import Counter
ROOT=Path('/data')
CONFIG=json.loads((ROOT/'config.json').read_text())
UPSTREAM=CONFIG['upstream']
CACHE=ROOT/'tv.m3u'
STATUS=ROOT/'status.json'
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
lock=threading.Lock()
state={'ok':False,'counts':{}}
if STATUS.exists():
 try:state.update(json.loads(STATUS.read_text()))
 except Exception:pass

def simplify(text,base):
 lines=text.lstrip('\ufeff').splitlines()
 if not lines or not lines[0].startswith('#EXTM3U'):
  raise ValueError('Upstream did not return M3U')
 selected={}
 info=None
 for line in lines[1:]:
  line=line.strip()
  if line.startswith('#EXTINF:'):
   info=line;continue
  if not line or line.startswith('#') or info is None:continue
  meta=info;info=None
  group=re.search(r'group-title="([^"]*)"',meta)
  group=group.group(1) if group else ''
  name=meta.rsplit(',',1)[-1].strip()
  name=re.sub('[①②③④⑤⑥⑦⑧⑨⑩]','',name)
  name=re.sub(r'\(比赛开放\)','',name).strip()
  category=None
  if group=='央视 · 主频':category='央视'
  elif group=='卫视 · 主频':category='卫视'
  elif group=='上海专区':
   category='上海'
   if name in ['新闻综合','都市频道','新纪实','魔都眼','爱上海']:
    name='上海'+name
  elif group=='河南专区':
   aliases={'都市频道':'河南都市','民生频道':'河南民生',
    '法治频道':'河南法治','电视频道':'河南电视剧',
    '新闻频道':'河南新闻','公共频道':'河南公共'}
   name=aliases.get(name,name)
   if name in {'河南都市','河南民生','河南法治',
    '河南电视剧','河南新闻','河南公共'}:
    category='河南'
  if category is None:continue
  key=name.casefold().replace(' ','')
  if key in selected:continue
  # Preserve original EPG IDs, logos and per-channel attributes.
  attrs=meta.rsplit(',',1)[0]
  attrs=re.sub(r'group-title="[^"]*"','group-title="'+category+'"',attrs)
  selected[key]=(category,name,attrs+','+name,urllib.parse.urljoin(base,line))
 order={'央视':0,'卫视':1,'上海':2,'河南':3}
 entries=sorted(selected.values(),key=lambda x:order[x[0]])
 if not entries:raise ValueError('No selected channels')
 out=[lines[0]]
 counts=Counter()
 for category,name,meta,url in entries:
  counts[category]+=1;out.extend([meta,url])
 return ('\n'.join(out)+'\n').encode(),dict(counts)

def atomic(path,data):
 tmp=path.with_suffix(path.suffix+'.tmp')
 tmp.write_bytes(data);os.replace(tmp,path)

def refresh():
 global state
 try:
  request=urllib.request.Request(UPSTREAM,headers={
   'User-Agent':'APTV','Accept':'application/vnd.apple.mpegurl,*/*'})
  with urllib.request.urlopen(request,timeout=35) as response:
   content=response.read(15*1024*1024+1)
   if len(content)>15*1024*1024:raise ValueError('Playlist too large')
   payload,counts=simplify(content.decode('utf-8-sig'),response.url)
  with lock:
   atomic(CACHE,payload)
   state={'ok':True,'last_success':int(time.time()),'counts':counts,
    'total':sum(counts.values()),'last_error':None}
   atomic(STATUS,json.dumps(state,ensure_ascii=False).encode())
  logging.info('Playlist refreshed: %s channels',sum(counts.values()))
 except Exception as error:
  with lock:
   state['ok']=False;state['last_error']=type(error).__name__
  # Do not log subscription URLs or playback credentials.
  logging.warning('Refresh failed (%s); retaining last good playlist',type(error).__name__)

def updater():
 while True:
  refresh()
  time.sleep(1800 if state.get('ok') else 300)

class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  path=urllib.parse.urlparse(self.path).path
  if path in ('/tv.m3u','/tv.m3u8'):
   with lock:data=CACHE.read_bytes() if CACHE.exists() else None
   if data is None:self.send_error(503,'Playlist not ready');return
   content_type='application/vnd.apple.mpegurl; charset=utf-8'
  elif path in ('/health','/status'):
   with lock:data=json.dumps(dict(state,cached=CACHE.exists()),ensure_ascii=False).encode()
   content_type='application/json; charset=utf-8'
  else:self.send_error(404);return
  self.send_response(200);self.send_header('Content-Type',content_type)
  self.send_header('Content-Length',str(len(data)))
  self.send_header('Cache-Control','no-store');self.end_headers()
  self.wfile.write(data)
 def log_message(self,fmt,*args):pass

if __name__=='__main__':
 threading.Thread(target=updater,daemon=True).start()
 logging.info('LAN subscription server starting')
 ThreadingHTTPServer(('192.168.0.2',8787),Handler).serve_forever()
