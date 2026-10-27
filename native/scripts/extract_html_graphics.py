"""Extract original embedded RCCAD artwork, preserving the source in a manifest."""
import base64,hashlib,json,re
from pathlib import Path
from html.parser import HTMLParser
root=Path(__file__).resolve().parents[2]
source=(root/'RCCAD.html').read_text()
out=root/'native/rccad/assets/html';out.mkdir(parents=True,exist_ok=True)
records=[]
for i,m in enumerate(re.finditer(r'data:image/([a-zA-Z+]+);base64,([A-Za-z0-9+/=]+)',source)):
 kind=m[1].replace('svg+xml','svg');data=base64.b64decode(m[2]);name=f'image_{i:02d}.{kind}'
 (out/name).write_bytes(data);records.append(dict(file=name,sha256=hashlib.sha256(data).hexdigest(),format=kind))
class Attr(HTMLParser):
 def handle_starttag(self,t,a):self.attrs=dict(a)
buttons={};controls=[]
for i,m in enumerate(re.finditer(r'<button\b([^>]*)>(.*?)</button>',source,re.S)):
 parser=Attr();parser.feed('<button'+m[1]+'>');attrs=parser.attrs;key=attrs.get('id') or attrs.get('data-shape')
 controls.append(dict(attributes=attrs,text=re.sub('<[^>]+>','',m[2]).strip()))
 if not key:continue
 content=m[2];info=dict(title=attrs.get('title',''),source_attributes=attrs)
 png=re.search(r'data:image/(\w+);base64,([A-Za-z0-9+/=]+)',content)
 svg=re.search(r'<svg\b.*?</svg>',content,re.S)
 if png:
  name=key+'.'+png[1];(out/name).write_bytes(base64.b64decode(png[2]));info['file']=name
 elif svg:
  raw=svg[0];name=key+'.svg'
  if not (out/name).exists():
   # In HTML these root properties are inherited from CSS; materialise them for Qt SVG.
   inherited=' xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
   artwork=raw.replace('<svg','<svg'+inherited,1)
   (out/name).write_text(artwork);(out/(key+'.source.svg')).write_text(raw)
  info['file']=name
 if key in ('moveTool','rotateTool','home'):info['glyph']=re.sub('<[^>]+>','',content).strip()
 if 'file' in info or 'glyph' in info:buttons[key]=info
(out/'catalog.json').write_text(json.dumps(dict(source='RCCAD.html',source_sha256=hashlib.sha256(source.encode()).hexdigest(),images=records,buttons=buttons,controls=controls),ensure_ascii=False,indent=2))
print(f'{len(records)} embedded images; {len(buttons)} button graphics')
