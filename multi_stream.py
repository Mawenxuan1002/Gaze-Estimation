# -*- coding: utf-8 -*-
import os, sys, json, logging, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stream_worker import StreamWorker
from health_server import start_demo_server, workers, workers_lock
from stream_identity import make_stream_id

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
logger = logging.getLogger(__name__)

DEMO_PORT = int(os.environ.get('DEMO_PORT', '8081'))

def main():
    config_path = os.path.join(os.path.dirname(__file__), 'rooms.json')
    if not os.path.exists(config_path):
        logger.error('Config not found')
        sys.exit(1)
    
    with open(config_path, 'r', encoding='utf-8-sig') as f:
        config = json.load(f)
    
    global_config = config.get('global', {})
    rooms = config.get('rooms', [])
    
    for room in rooms:
        room_no = room.get('room_no')
        device_id = room.get('device_id')
        rtsp_url = room.get('rtsp_url')
        if not all([room_no, device_id, rtsp_url]):
            continue
        merged = {**global_config, **room}
        worker = StreamWorker(room_no, device_id, rtsp_url, merged)
        worker.start()
        with workers_lock:
            workers[make_stream_id(room_no, device_id)] = worker
        logger.info('Started room {}'.format(room_no))
    
    logger.info('Demo: http://localhost:{}'.format(DEMO_PORT))
    logger.info('API: POST /api/start {"rtspUrl":"...","key":"{\"roomNo\":\"001\",\"deviceId\":\"1\"}"}')
    try:
        start_demo_server(DEMO_PORT)
    except KeyboardInterrupt:
        with workers_lock:
            for w in workers.values():
                w.stop(timeout=5.0)

if __name__ == '__main__':
    main()
