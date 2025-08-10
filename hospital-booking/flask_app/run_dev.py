# flask_app/run_dev.py
from app import create_app
import threading
import time

def run_app(port, host='0.0.0.0'):
    app = create_app()
    app.run(host=host, port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    # รัน Flask บน port หลายตัว
    ports = [5001, 5002, 5003]
    
    threads = []
    for port in ports:
        thread = threading.Thread(target=run_app, args=(port,))
        thread.daemon = True
        thread.start()
        threads.append(thread)
        print(f"Starting Flask on port {port}")
        time.sleep(1)  # รอให้แต่ละ port start
    
    try:
        # รอให้ทุก thread ทำงาน
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print("Stopping all servers...")