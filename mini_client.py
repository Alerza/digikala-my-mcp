"""
mini-client: بجای curl، چون stdio یعنی پایپ stdin/out.
این اسکریپت کل lifecycle جلوی چشم‌ت اجرا می‌کند:
  initialize  →  notifications/initialized  →  tools/list  →  tools/call
"""
import subprocess, json, sys, os

SERVER = ["./.venv/bin/python", "server.py"]


def run_rpc():
    p = subprocess.Popen(SERVER, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)

    import selectors, time

    def read_line(fd, timeout=60):
        sel = selectors.DefaultSelector()
        sel.register(fd, selectors.EVENT_READ)
        ready = sel.select(timeout)
        if not ready:
            return ""
        return os.read(fd.fileno(), 65536).decode()

    def send(obj, timeout=60):
        p.stdin.write(json.dumps(obj) + "\n"); p.stdin.flush()
        line = read_line(p.stdout, timeout)
        if line.strip().startswith("{"):
            return json.loads(line)
        return None  # notification یا قائم نبود

    # 1) initialize — دست‌دادن نسخه پروتکل و قابلیت‌ها
    r = send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "hermes-mini", "version": "0.1"}}})
    print("== initialize →", json.dumps(r["result"]["serverInfo"], ensure_ascii=False))

    # 2) notify — بدون id یعنی notification، جواب نمی‌خواهد
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    # 3) tools/list — فهرست ابزارها + schema هرکدام
    r = send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = r["result"]["tools"]
    print("== Tools:", [t["name"] for t in tools])
    print("   schema search_digikala:", json.dumps(tools[0].get("inputSchema"), ensure_ascii=False))

    # 4) tools/call — یک فراخووانی واقعی
    r = send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "search_digikala", "arguments": {"query": "گوشی سامسونگ", "page_size": 3}}})
    txt = r["result"]["content"][0]["text"]
    data = json.loads(txt)
    for it in data.get("items", []):
        print(f"   - {it['title'][:55]} | {it['price_toman']:,} T | ⭐{it.get('rating_pct')} | dkp-{it['id']}")

    # 5) tools/call با شناسه نامعتبر — خطای صادقانه‌یサーバ را ببین
    r = send({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
        "name": "product_details", "arguments": {"product_id": 123}}})
    print("== product_details(123) →", r["result"]["content"][0]["text"][:200])

    p.terminate()


if __name__ == "__main__":
    run_rpc()
