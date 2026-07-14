# -*- coding: utf-8 -*-
import os, sys, json, logging, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stream_worker import StreamWorker
from health_server import start_demo_server

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
logger = logging.getLogger(__name__)

def main():
    config_path = os.path.join(os.path.dirname(__file__), 'rooms.json')
    if not os.path.exists(config_path):
        logger.error('Config not found')
        sys.exit(1)
    
    with open(config_path, 'r', encoding='utf-8-sig') as f:
        config = json.load(f)
    
    global_config = config.get('global', {})
    rooms = config.get('rooms', [])
    
    workers = []
    for room in rooms:
        room_no = room.get('room_no')
        device_id = room.get('device_id')
        rtsp_url = room.get('rtsp_url')
        if not all([room_no, device_id, rtsp_url]):
            continue
        merged = {**global_config, **room}
        worker = StreamWorker(room_no, device_id, rtsp_url, merged)
        worker.start()
        workers.append(worker)
        logger.info('Started room {}'.format(room_no))
    
    logger.info('Demo: http://localhost:8081')
    try:
        start_demo_server(8081)
    except KeyboardInterrupt:
        for w in workers:
            w.stop()

if __name__ == '__main__':
    main()
