import socket, threading, time, urllib.request, json
import pytest
import uni.webui.server as srv

def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1",0)); p=s.getsockname()[1]; s.close(); return p

@pytest.fixture
def server():
    port=_free_port()
    httpd=srv.ThreadingHTTPServer(("127.0.0.1",port), srv._Handler)
    t=threading.Thread(target=httpd.serve_forever, daemon=True); t.start(); time.sleep(0.6)
    base=f"http://127.0.0.1:{port}"
    try: yield base
    finally: httpd.shutdown(); httpd.server_close()

def test_debug_fixture(server):
    with urllib.request.urlopen(server+"/api/heartbeats", timeout=5) as r:
        data=json.loads(r.read().decode())
    print("\nDEBUG RESP names:", sorted(p["name"] for p in data.get("participants",[])))
    print("DEBUG ROOT:", srv._ROOT)
    parts=srv._gather_participants()
    print("DEBUG gather2:", sorted(p["name"] for p in parts))
