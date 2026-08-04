# -*- coding: utf-8 -*-
import json, os, time, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from datetime import datetime
from .identity import make_stream_id, parse_platform_key
from .paths import config_path
from .worker import get_frame, stats_cache, stats_lock, StreamWorker

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

            if path == '/api/start' or path == '/analyze_start':
                self._handle_start(data)
            elif path == '/api/stop' or path == '/analyze_end':
                self._handle_stop(data)
            elif path == '/analyze_status':
                self._handle_status(data)
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
        room_no, device_id = parse_platform_key(key)
        stream_id = make_stream_id(room_no, device_id)

        if not all([rtsp_url, room_no, device_id]):
            self._json_response({'code': 0, 'msg': '缺少摄像头地址或房间参数'})
            return

        global_config = self._load_global_config()
        config = {**global_config, 'rtsp_url': rtsp_url}
        
        with workers_lock:
            old_worker = workers.get(stream_id)
        if old_worker and not old_worker.stop(timeout=5.0):
            self._json_response({'code': 0, 'msg': '旧任务停止超时，请稍后重试'})
            return

        with workers_lock:
            if workers.get(stream_id) is not old_worker:
                self._json_response({'code': 0, 'msg': '房间任务已被其他请求更新，请重试'})
                return
            worker = StreamWorker(room_no, device_id, rtsp_url, config)
            worker.start()
            workers[stream_id] = worker

        self._json_response({'code': 1, 'msg': 'Started', 'startTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})

    def _handle_stop(self, data):
        rtsp_url = data.get('rtspUrl', '')
        requested_stream_id = self._stream_id_from_optional_key(data.get('key'))
        with workers_lock:
            for stream_id, worker in list(workers.items()):
                if requested_stream_id:
                    matched = stream_id == requested_stream_id
                else:
                    matched = worker.rtsp_url == rtsp_url
                if matched:
                    break
            else:
                self._json_response({'code': 0, 'msg': '房间未找到'})
                return

        if not worker.stop(timeout=5.0):
            self._json_response({'code': 0, 'msg': '任务停止超时'})
            return
        with workers_lock:
            if workers.get(stream_id) is worker:
                del workers[stream_id]
        self._json_response({'code': 1, 'msg': 'Stopped', 'endTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})

    def _handle_config(self, data):
        api_url = data.get('api_url', '')
        username = data.get('username', '')
        password = data.get('password', '')
        if api_url:
            path = config_path()
            config = {}
            if path.exists():
                with path.open('r', encoding='utf-8-sig') as f:
                    config = json.load(f)
            if 'global' not in config:
                config['global'] = {}
            if api_url:
                config['global']['api_url'] = api_url
            if username:
                config['global']['username'] = username
            if password:
                config['global']['password'] = password
            with path.open('w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self._json_response({'code': 200, 'msg': 'Config updated'})
        else:
            self._json_response({'code': 400, 'msg': 'Missing api_url'})

    def _handle_status(self, data):
        rtsp_url = data.get('rtspUrl', '')
        requested_stream_id = self._stream_id_from_optional_key(data.get('key'))
        with workers_lock:
            for stream_id, worker in workers.items():
                if requested_stream_id:
                    matched = stream_id == requested_stream_id
                else:
                    matched = worker.rtsp_url == rtsp_url
                if matched:
                    status = worker.get_status()
                    self._json_response({
                        'code': 1 if status['alive'] else 0,
                        'msg': status['status'],
                        'stream_id': stream_id,
                        'room_no': worker.room_no,
                        'device_id': worker.device_id,
                        'last_error': status['last_error'],
                    })
                    return
        self._json_response({'code': 0, 'msg': '未找到'})

    def _get_rooms(self):
        with workers_lock:
            rooms = {}
            for stream_id, worker in workers.items():
                worker_status = worker.get_status()
                rooms[stream_id] = {
                    'stream_id': stream_id,
                    'room_no': worker.room_no,
                    'device_id': worker.device_id,
                    'rtsp_url': worker.rtsp_url,
                    'status': worker_status['status'],
                    'alive': worker_status['alive'],
                    'last_error': worker_status['last_error']
                }
            return {'code': 200, 'data': rooms}

    def _load_global_config(self):
        path = config_path()
        if path.exists():
            with path.open('r', encoding='utf-8-sig') as f:
                config = json.load(f)
                return config.get('global', {})
        return {}

    def _stream_id_from_optional_key(self, key):
        if key in (None, '', {}):
            return None
        room_no, device_id = parse_platform_key(key)
        if not room_no or not device_id:
            return None
        return make_stream_id(room_no, device_id)

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
h+='<div class="hi"><div class="hl">HEAD DOWN</div><div class="hv" id="hd-'+r+'">--</div></div>';
h+='<div class="hi"><div class="hl">RATIO RISE</div><div class="hv" id="rise-'+r+'">--</div></div>';
h+='<div class="hi"><div class="hl">FACE</div><div class="hv" id="face-'+r+'">--</div></div>';
h+='<div class="hi"><div class="hl">FPS</div><div class="hv" id="fps-'+r+'">--</div></div>';
h+='<div class="hi"><div class="hl">PUSH OK</div><div class="hv" id="ok-'+r+'">0</div></div>';
h+='<div class="hi"><div class="hl">PUSH FAILED</div><div class="hv" id="fail-'+r+'">0</div></div>';
h+='</div></div></div><div class="bar">';
h+='<div class="st"><div class="sn" id="s1-'+r+'">0</div><div class="sl">FPS</div></div>';
h+='<div class="st"><div class="sn" id="s2-'+r+'">0</div><div class="sl">FRAMES</div></div>';
h+='<div class="st"><div class="sn" id="s3-'+r+'">0</div><div class="sl">ALERTS</div></div>';
h+='<div class="st"><div class="sn" id="s4-'+r+'">--</div><div class="sl">RATIO RISE</div></div>';
h+='</div></div>';
document.getElementById('rooms').innerHTML+=h;loaded[r]=true;}
var el;
el=document.getElementById('hd-'+r);if(el){el.textContent=v.head_down?'YES':'NO';el.className='hv '+(v.head_down?'r':'g')};
el=document.getElementById('rise-'+r);if(el){el.textContent=v.ratio_rise==null?'--':v.ratio_rise;el.className='hv '+(v.head_down?'r':'g')};
el=document.getElementById('face-'+r);if(el){el.textContent=v.face_detected?'OK':'NONE';el.className='hv '+(v.face_detected?'g':'r');}
el=document.getElementById('fps-'+r);if(el){el.textContent=v.fps||0;}
el=document.getElementById('ok-'+r);if(el){el.textContent=v.push_successes||0;el.className='hv g';}
el=document.getElementById('fail-'+r);if(el){el.textContent=v.push_failures||0;el.className='hv '+(v.push_failures?'r':'g');}
el=document.getElementById('s1-'+r);if(el){el.textContent=v.fps||0;}
el=document.getElementById('s2-'+r);if(el){el.textContent=v.frames||0;}
el=document.getElementById('s3-'+r);if(el){el.textContent=v.detected_count||0;}
el=document.getElementById('s4-'+r);if(el){el.textContent=v.ratio_rise==null?'--':v.ratio_rise;}
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
    print('API: POST /api/start or /analyze_start - Start room')
    print('API: POST /api/stop or /analyze_end - Stop room')
    print('API: POST /analyze_status - Check status')
    print('API: GET /api/rooms - List rooms')
    server.serve_forever()

if __name__ == '__main__':
    start_demo_server()
