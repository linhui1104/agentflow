"""测试 WS 事件流 + 运行快照"""
import asyncio, json, urllib.request

async def main():
    import websockets
    events = []
    async with websockets.connect("ws://127.0.0.1:8900/ws/runs") as ws:
        try:
            while len(events) < 40:
                try:
                    ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
                    events.append(ev)
                    print(f"[{ev.get('run_id','')[:9]}] {ev.get('node_id',''):<10} {ev.get('status','')} "
                          f"score={ev.get('score','')} round={ev.get('round','')}")
                    if ev.get("status") == "done" and ev.get("node_id") == "publish":
                        break
                except asyncio.TimeoutError:
                    break
        except Exception as e:
            print("WS异常:", e)
    print(f"\n共收到 {len(events)} 个事件")

    # 查快照
    r = urllib.request.urlopen("http://127.0.0.1:8900/api/runs", timeout=10)
    runs = json.load(r)
    print("历史运行:", [(x["id"][:12], x["status"]) for x in runs])

asyncio.run(main())
