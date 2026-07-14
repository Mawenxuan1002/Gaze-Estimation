# -*- coding: utf-8 -*-
import json, os, time, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from datetime import datetime
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stream_worker import get_frame, stats_cache, stats_lock, StreamWorker

DEMO_PORT = int(os.environ.get('DEMO_PORT', '8081'))

# Active workers
workers = {}
workers_lock = threading.Lock()

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            path = self.path.split('?')[0]
            if path == '/health' or path == '/status':
                self._json_response(self._get_all_status())
            elif path == '/' or path == '/demo':
                self._html_response(self._get_demo_page())
            elif path.startswith('/video/'):
                room_no = path.split('/')[2]
                self._stream_video(room_no)
            elif path == '/api/rooms':
                self._json_response(self._get_rooms())
            else:
                self.send_response(404)
                self.end_headers()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def do_POST(self):
        try:
            path = self.path.split('?')[0]
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body) if body else {}

            if path == '/api/start':
                self._handle_start(data)
            elif path == '/api/stop':
                self._handle_stop(data)
            elif path == '/api/config':
                self._handle_config(data)
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            self._json_response({'code': 500, 'msg': str(e)})

    def _handle_start(self, data):
        rtsp_url = data.get('rtspUrl', '')
        key = data.get('key', '{}')
        if isinstance(key, str):
            key = json.loads(key)
        room_no = key.get('roomNo', '')
        device_id = key.get('deviceId', '')

        if not all([rtsp_url, room_no, device_id]):
            self._json_response({'code': 400, 'msg': 'Missing rtspUrl, roomNo or deviceId'})
            return

        global_config = self._load_global_config()
        config = {**global_config, 'rtsp_url': rtsp_url}
        
        with workers_lock:
            if room_no in workers:
                workers[room_no].stop()
            worker = StreamWorker(room_no, device_id, rtsp_url, config)
            worker.start()
            workers[room_no] = worker

        self._json_response({'code': 200, 'msg': 'Started room {}'.format(room_no)})

    def _handle_stop(self, data):
        rtsp_url = data.get('rtspUrl', '')
        with workers_lock:
            for room_no, worker in list(workers.items()):
                if worker.rtsp_url == rtsp_url:
                    worker.stop()
                    del workers[room_no]
                    self._json_response({'code': 200, 'msg': 'Stopped room {}'.format(room_no)})
                    return
        self._json_response({'code': 404, 'msg': 'Room not found'})

    def _handle_config(self, data):
        api_url = data.get('api_url', '')
        username = data.get('username', '')
        password = data.get('password', '')
        if api_url:
            config_path = os.path.join(os.path.dirname(__file__), 'rooms.json')
            config = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8-sig') as f:
                    config = json.load(f)
            if 'global' not in config:
                config['global'] = {}
            if api_url:
                config['global']['api_url'] = api_url
            if username:
                config['global']['username'] = username
            if password:
                config['global']['password'] = password
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self._json_response({'code': 200, 'msg': 'Config updated'})
        else:
            self._json_response({'code': 400, 'msg': 'Missing api_url'})

    def _get_rooms(self):
        with workers_lock:
            rooms = {}
            for room_no, worker in workers.items():
                rooms[room_no] = {
                    'room_no': room_no,
                    'device_id': worker.device_id,
                    'rtsp_url': worker.rtsp_url,
                    'status': 'running'
                }
            return {'code': 200, 'data': rooms}

    def _load_global_config(self):
        config_path = os.path.join(os.path.dirname(__file__), 'rooms.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8-sig') as f:
                config = json.load(f)
                return config.get('global', {})
        return {}

    def _json_response(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _html_response(self, html):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def _stream_video(self, room_no):
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
.wrap{padding:20px;display:flex;justify-content:center;flex-wrap:wrap;gap:20px}
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
<div class="wrap" id="rooms"></div>
<script>
var loaded={};
function loadData(){
var x=new XMLHttpRequest();x.open('GET','/status?t='+Date.now(),true);x.timeout=3000;
x.onload=function(){if(x.status==200){try{
var d=JSON.parse(x.responseText);var s=d.streams||{};
for(var r in s){var v=s[r];
if(!loaded[r]){
var h='<div class="card" id="card-'+r+'"><div class="card-hdr"><span class="t">Room '+r+'</span><span class="i" id="info-'+r+'"></span></div>';
h+='<div class="vid"><img id="stream-'+r+'" src="/video/'+r+'"><div class="ov"><div class="hud">';
h+='<div class="hi"><div class="hl">GAZE</div><div class="hv" id="gaze-'+r+'">--</div></div>';
h+='<div class="hi"><div class="hl">EYE</div><div class="hv" id="eye-'+r+'">--</div></div>';
h+='<div class="hi"><div class="hl">DROWSY</div><div class="hv" id="drowsy-'+r+'">--</div></div>';
h+='<div class="hi"><div class="hl">EAR</div><div class="hv" id="ear-'+r+'">--</div></div>';
h+='<div class="hi"><div class="hl">FACE</div><div class="hv" id="face-'+r+'">--</div></div>';
h+='<div class="hi"><div class="hl">FPS</div><div class="hv" id="fps-'+r+'">--</div></div>';
h+='</div></div></div><div class="bar">';
h+='<div class="st"><div class="sn" id="s1-'+r+'">0</div><div class="sl">FPS</div></div>';
h+='<div class="st"><div class="sn" id="s2-'+r+'">0</div><div class="sl">FRAMES</div></div>';
h+='<div class="st"><div class="sn" id="s3-'+r+'">0</div><div class="sl">ALERTS</div></div>';
h+='<div class="st"><div class="sn" id="s4-'+r+'">--</div><div class="sl">EAR</div></div>';
h+='</div></div>';
document.getElementById('rooms').innerHTML+=h;loaded[r]=true;}
var el;
el=document.getElementById('gaze-'+r);if(el){el.textContent=v.gaze||'--';el.className='hv '+(v.gaze==='CENTER'?'g':'y');}
el=document.getElementById('eye-'+r);if(el){el.textContent=v.eye_state||'--';el.className='hv '+(v.eye_state==='OPEN'?'g':(v.eye_state==='CLOSED'?'r':'y'));}
el=document.getElementById('drowsy-'+r);if(el){el.textContent=v.drowsy?'YES':'NO';el.className='hv '+(v.drowsy?'r':'g');}
el=document.getElementById('ear-'+r);if(el){el.textContent=v.ear||'--';}
el=document.getElementById('face-'+r);if(el){el.textContent=v.face_detected?'OK':'NONE';el.className='hv '+(v.face_detected?'g':'r');}
el=document.getElementById('fps-'+r);if(el){el.textContent=v.fps||0;}
el=document.getElementById('s1-'+r);if(el){el.textContent=v.fps||0;}
el=document.getElementById('s2-'+r);if(el){el.textContent=v.frames||0;}
el=document.getElementById('s3-'+r);if(el){el.textContent=v.pushes||0;}
el=document.getElementById('s4-'+r);if(el){el.textContent=v.ear||'--';}
el=document.getElementById('info-'+r);if(el){el.textContent='FPS: '+(v.fps||0)+' | Frames: '+(v.frames||0);}
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
    print('API: POST /api/start - Start room')
    print('API: POST /api/stop - Stop room')
    print('API: GET /api/rooms - List rooms')
    server.serve_forever()

if __name__ == '__main__':
    start_demo_server()
