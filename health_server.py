# -*- coding: utf-8 -*-
import json, os, time, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from datetime import datetime
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stream_worker import get_frame, stats_cache, stats_lock

DEMO_PORT = int(os.environ.get('DEMO_PORT', '8081'))

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            path = self.path.split('?')[0]
            if path == '/health' or path == '/status':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(self._get_all_status(), ensure_ascii=False).encode())
            elif path == '/' or path == '/demo':
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(self._get_demo_page().encode('utf-8'))
            elif path.startswith('/video/'):
                room_no = path.split('/')[2]
                self.send_response(200)
                self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                while True:
                    frame = get_frame(room_no)
                    if frame:
                        try:
                            self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                            self.wfile.flush()
                        except:
                            break
                    time.sleep(0.033)
            else:
                self.send_response(404)
                self.end_headers()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def _get_all_status(self):
        result = {'server': 'running', 'time': datetime.now().isoformat(), 'streams': {}}
        with stats_lock:
            for room_no, data in stats_cache.items():
                result['streams'][room_no] = data
        return result

    def _get_demo_page(self):
        return '''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Gaze Tracker Demo</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}body{background:#0f0f0f;color:#fff;font-family:Arial}
.hdr{background:#1a1a1a;padding:12px 20px;border-bottom:3px solid #4CAF50;display:flex;justify-content:space-between}
.hdr h1{color:#4CAF50;font-size:20px}#dbg{color:#888;font-size:12px;align-self:center}
.wrap{padding:20px;display:flex;justify-content:center}
.card{background:#1a1a1a;border-radius:10px;overflow:hidden;border:1px solid #333;width:900px}
.card-hdr{background:#222;padding:10px 16px;display:flex;justify-content:space-between}
.card-hdr .t{color:#4CAF50;font-size:16px}.card-hdr .i{color:#888;font-size:12px}
.vid{position:relative;background:#000;min-height:400px;display:flex;align-items:center;justify-content:center}
.vid img{width:100%;display:block}
.ov{position:absolute;top:0;left:0;right:0;z-index:2;padding:8px;background:linear-gradient(to bottom,rgba(0,0,0,0.8),transparent);pointer-events:none}
.hud{display:grid;grid-template-columns:repeat(3,1fr);gap:5px}
.hi{background:rgba(0,0,0,0.7);padding:6px;border-radius:4px;text-align:center}
.hl{font-size:9px;color:#888;text-transform:uppercase}.hv{font-size:16px;font-weight:bold;margin-top:2px}
.g{color:#4CAF50}.y{color:#ffc107}.r{color:#f44336}.b{color:#2196F3}
.bar{display:grid;grid-template-columns:repeat(4,1fr);background:#1e1e1e}
.st{padding:10px;text-align:center;border-right:1px solid #333}
.sn{font-size:20px;font-weight:bold;color:#4CAF50}.sl{font-size:9px;color:#666;margin-top:2px}
</style></head><body>
<div class="hdr"><h1>Gaze Tracker Demo</h1><span id="dbg">Connecting...</span></div>
<div class="wrap"><div id="rooms"><div class="card"><div class="vid"><span style="color:#666">Loading...</span></div></div></div></div>
<script>
var loaded=false;
function loadData(){
var x=new XMLHttpRequest();x.open('GET','/status?t='+Date.now(),true);x.timeout=3000;
x.onload=function(){if(x.status==200){try{
var d=JSON.parse(x.responseText);var s=d.streams||{};
for(var r in s){var v=s[r];
if(!loaded){var h='<div class="card"><div class="card-hdr"><span class="t">Room '+r+'</span><span class="i" id="info"></span></div>';
h+='<div class="vid"><img id="stream" src="/video/'+r+'"><div class="ov"><div class="hud">';
h+='<div class="hi"><div class="hl">GAZE</div><div class="hv" id="gaze">--</div></div>';
h+='<div class="hi"><div class="hl">EYE</div><div class="hv" id="eye">--</div></div>';
h+='<div class="hi"><div class="hl">DROWSY</div><div class="hv" id="drowsy">--</div></div>';
h+='<div class="hi"><div class="hl">EAR</div><div class="hv" id="ear">--</div></div>';
h+='<div class="hi"><div class="hl">FACE</div><div class="hv" id="face">--</div></div>';
h+='<div class="hi"><div class="hl">FPS</div><div class="hv" id="sfps">--</div></div>';
h+='</div></div></div><div class="bar">';
h+='<div class="st"><div class="sn" id="s1">0</div><div class="sl">FPS</div></div>';
h+='<div class="st"><div class="sn" id="s2">0</div><div class="sl">FRAMES</div></div>';
h+='<div class="st"><div class="sn" id="s3">0</div><div class="sl">ALERTS</div></div>';
h+='<div class="st"><div class="sn" id="s4">--</div><div class="sl">EAR</div></div>';
h+='</div></div>';
document.getElementById('rooms').innerHTML=h;loaded=true;}
var el;
el=document.getElementById('gaze');if(el){el.textContent=v.gaze||'--';el.className='hv '+(v.gaze==='CENTER'?'g':'y');}
el=document.getElementById('eye');if(el){el.textContent=v.eye_state||'--';el.className='hv '+(v.eye_state==='OPEN'?'g':(v.eye_state==='CLOSED'?'r':'y'));}
el=document.getElementById('drowsy');if(el){el.textContent=v.drowsy?'YES':'NO';el.className='hv '+(v.drowsy?'r':'g');}
el=document.getElementById('ear');if(el){el.textContent=v.ear||'--';}
el=document.getElementById('face');if(el){el.textContent=v.face_detected?'OK':'NONE';el.className='hv '+(v.face_detected?'g':'r');}
el=document.getElementById('sfps');if(el){el.textContent=v.fps||0;}
el=document.getElementById('s1');if(el){el.textContent=v.fps||0;}
el=document.getElementById('s2');if(el){el.textContent=v.frames||0;}
el=document.getElementById('s3');if(el){el.textContent=v.pushes||0;}
el=document.getElementById('s4');if(el){el.textContent=v.ear||'--';}
el=document.getElementById('info');if(el){el.textContent='FPS: '+(v.fps||0)+' | Frames: '+(v.frames||0);}
}
document.getElementById('dbg').innerHTML='OK | '+d.time;
}catch(e){document.getElementById('dbg').innerHTML='Error';}}
};
x.onerror=function(){document.getElementById('dbg').innerHTML='Error';};x.send();}
setInterval(loadData,1000);loadData();
</script></body></html>'''

    def log_message(self, format, *args):
        pass

def start_demo_server(port=None):
    if port is None:
        port = DEMO_PORT
    server = ThreadingHTTPServer(('0.0.0.0', port), DemoHandler)
    print('Demo: http://0.0.0.0:{}'.format(port))
    server.serve_forever()

if __name__ == '__main__':
    start_demo_server()
