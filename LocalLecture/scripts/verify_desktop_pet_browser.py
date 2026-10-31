"""Private Chrome profile + temporary DB; never touches the user's records or mic."""
import base64
from contextlib import ExitStack
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
OUTPUT = ROOT / "data" / "growmate-qa"
PORT = 5173
URL = f"http://127.0.0.1:{PORT}"
TIMER_PROBE = """
(() => {
  const originalNow = Date.now.bind(Date), originalSet = window.setTimeout.bind(window), originalClear = window.clearTimeout.bind(window);
  let shift = 0;
  const timers = new Map();
  Date.now = () => originalNow() + shift;
  window.setTimeout = (callback, delay = 0, ...args) => {
    let id = originalSet(() => { timers.delete(id); callback(...args); }, delay);
    timers.set(id, { at: Date.now() + delay, callback: () => callback(...args) });
    return id;
  };
  window.clearTimeout = id => { timers.delete(id); originalClear(id); };
  window.__petQA = {
    count: () => timers.size,
    advance: delta => {
      shift += delta;
      for (const [id, entry] of [...timers]) if (entry.at <= Date.now()) { window.clearTimeout(id); entry.callback(); }
    }
  };
})();
"""


def main():
    # Fail safely if the development port belongs to another process.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", PORT))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="growmate-pet-qa-") as temporary:
        folder = Path(temporary)
        browser = server = ws = None
        connections = ExitStack()
        errors = []
        try:
            code = "from pathlib import Path; from meetingbro.growmate.web import create_app; import uvicorn,sys; uvicorn.run(create_app(Path(sys.argv[1]),enable_notifications=False),host='127.0.0.1',port=5173,log_level='warning')"
            server = subprocess.Popen([sys.executable, "-c", code, str(folder / "data")], cwd=ROOT / "app/backend", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            for _ in range(60):
                if server.poll() is not None: raise RuntimeError("QA backend exited")
                try:
                    with urllib.request.urlopen(URL + "/health", timeout=1) as response: assert json.load(response)["app"] == "GrowMate"
                    break
                except Exception: time.sleep(.2)
            else: raise RuntimeError("QA backend failed to start")
            profile = folder / "chrome-profile"
            browser = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            active = profile / "DevToolsActivePort"
            for _ in range(60):
                if active.exists(): break
                time.sleep(.2)
            port = active.read_text().splitlines()[0]
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list") as response: targets = json.load(response)
            target = next(t for t in targets if t["type"] == "page")
            ws = connections.enter_context(connect(target["webSocketDebuggerUrl"], max_size=20_000_000))
            sequence = 0

            def call(method, params=None):
                nonlocal sequence
                sequence += 1
                ws.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
                while True:
                    result = json.loads(ws.recv(timeout=20))
                    if result.get("method") == "Runtime.exceptionThrown": errors.append(result["params"])
                    if result.get("method") == "Runtime.consoleAPICalled" and result["params"].get("type") == "error": errors.append(result["params"])
                    if result.get("id") == sequence:
                        if "error" in result: raise RuntimeError(result["error"])
                        return result.get("result", {})

            def evaluate(expression):
                result = call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
                if "exceptionDetails" in result: raise RuntimeError(result["exceptionDetails"])
                return result.get("result", {}).get("value")

            def wait(expression):
                for _ in range(60):
                    if evaluate(expression): return
                    time.sleep(.1)
                raise AssertionError("Condition failed: " + expression)

            def click(selector):
                evaluate(f"document.querySelector({json.dumps(selector)}).click()")
                time.sleep(.1)

            def rect(selector=".gsp-character"):
                return evaluate(f"(() => {{const r=document.querySelector({json.dumps(selector)}).getBoundingClientRect();return {{x:r.x,y:r.y,width:r.width,height:r.height}}}})()")

            def mouse(kind, x, y, **extra):
                call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, **extra})

            def tap(x, y, count=1):
                mouse("mousePressed", x, y, button="left", buttons=1, clickCount=count)
                mouse("mouseReleased", x, y, button="left", buttons=0, clickCount=count)

            def screenshot(name):
                shot = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                (OUTPUT / name).write_bytes(base64.b64decode(shot["data"]))

            call("Page.enable"); call("Runtime.enable")
            call("Page.addScriptToEvaluateOnNewDocument", {"source": TIMER_PROBE})
            call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1050, "deviceScaleFactor": 1, "mobile": False})
            call("Page.navigate", {"url": URL})
            wait("document.body?.innerText.includes('今天也慢慢来') && !!document.querySelector('.gsp-image')")
            wait("document.querySelector('.gsp-image').naturalWidth > 0")
            assert evaluate("getComputedStyle(document.querySelector('.gsp-character')).backgroundColor === 'rgba(0, 0, 0, 0)'")
            assert evaluate("document.querySelector('.gsp-image').draggable === false")
            wait("!!document.querySelector('.gsp-bubble[data-phase=visible]')")
            screenshot("pet-desktop.png")
            for label, heading in [("专注", "专注一会儿"), ("森林", "我的森林"), ("记录", "实时录音转文字"), ("陪伴", "陪伴你的每一天")]:
                evaluate(f"Array.from(document.querySelectorAll('.gm-sidebar nav button')).find(e => e.textContent.endsWith({json.dumps(label)})).click()")
                wait(f"document.body.innerText.includes({json.dumps(heading)})")
                assert evaluate("!!document.querySelector('.desktop-pet')")
            evaluate("document.querySelector('.gm-sidebar nav button').click()")
            wait("document.body.innerText.includes('今天也慢慢来')")
            r = rect(); x, y = r["x"] + r["width"] / 2, r["y"] + r["height"] / 2
            tap(x, y); wait("document.querySelector('.desktop-pet').dataset.clickCount === '1'")
            assert evaluate("document.querySelectorAll('.gsp-bubble').length === 1")
            tap(x,y); tap(x,y,2)
            wait("document.querySelector('.desktop-pet').dataset.state === 'surprise'")
            before = evaluate("document.querySelector('.desktop-pet').dataset.clickCount")
            mouse("mousePressed", x, y, button="left", buttons=1, clickCount=1)
            mouse("mouseMoved", x - 280, y - 160, button="left", buttons=1)
            wait("document.querySelector('.desktop-pet').dataset.state === 'drag'")
            mouse("mouseReleased", x - 280, y - 160, button="left", buttons=0, clickCount=1)
            wait("document.querySelector('.desktop-pet').dataset.state === 'idle'")
            assert evaluate("document.querySelector('.desktop-pet').dataset.clickCount") == before
            saved = evaluate("JSON.parse(localStorage.getItem('desktopPet.settings')).position")
            call("Page.reload")
            wait("!!document.querySelector('.gsp-image')")
            restored = rect(".desktop-pet")
            assert abs(restored["x"] - saved["x"]) < 1 and abs(restored["y"] - saved["y"]) < 1
            time.sleep(.4)
            assert not evaluate("!!document.querySelector('.gsp-bubble')"), "greeting repeated on refresh"
            evaluate("window.__petQA.advance(302000)")
            wait("document.querySelector('.desktop-pet').dataset.state === 'sleep' && document.querySelector('.gsp-image').src.endsWith('/sleep.png')")
            assert evaluate("window.__petQA.count()") == 0
            mouse("mouseMoved",10,100)
            wait("document.querySelector('.desktop-pet').dataset.state === 'idle'")
            click('[aria-label="隐藏顾时夜"]')
            wait("!document.querySelector('.desktop-pet') && !!document.querySelector('.gsp-recall')")
            assert evaluate("window.__petQA.count()") == 0, "hidden pet leaked a timer"
            call("Page.reload"); wait("!!document.querySelector('.gsp-recall')")
            click('.gsp-recall'); wait("!!document.querySelector('.desktop-pet')")
            click('[aria-label="打开桌宠设置"]'); wait("!!document.querySelector('.gsp-menu')")
            screenshot("pet-settings.png")
            click('[aria-label="关闭桌宠设置"]')
            call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
            wait("document.querySelector('.gsp-character').getBoundingClientRect().width === 110")
            mobile = rect(".desktop-pet")
            assert mobile["x"] >= 0 and mobile["x"] + mobile["width"] <= 390
            assert mobile["y"] >= 0 and mobile["y"] + mobile["height"] <= 844 - 72
            r = rect(); x,y = r["x"] + r["width"] / 2, r["y"] + r["height"] / 2
            call("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x,"y": y}]})
            call("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x-80,"y": y-100}]})
            call("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            wait("document.querySelector('.desktop-pet').dataset.state === 'idle'")
            touched = rect(".desktop-pet")
            assert touched["x"] < mobile["x"] - 50 and touched["y"] < mobile["y"] - 50, "touch drag did not move"
            click('.gsp-character'); wait("!!document.querySelector('.gsp-bubble[data-phase=visible]')")
            bubble = rect('.gsp-bubble')
            assert bubble["x"] >= 0 and bubble["x"] + bubble["width"] <= 390
            assert bubble["y"] >= 0 and bubble["y"] + bubble["height"] <= 844
            assert evaluate("document.documentElement.scrollWidth <= innerWidth")
            screenshot("pet-mobile.png")
            call("Network.enable"); call("Network.setCacheDisabled", {"cacheDisabled": True}); call("Network.setBlockedURLs", {"urls": ["*wave.png"]})
            call("Page.reload"); wait("!!document.querySelector('.gsp-image')")
            click('[aria-label="打开桌宠设置"]')
            evaluate("Array.from(document.querySelectorAll('.gsp-menu button')).find(e=>e.textContent==='打个招呼').click()")
            wait("document.querySelector('.desktop-pet').dataset.state === 'wave' && document.querySelector('.gsp-image').src.endsWith('/idle.png')")
            assert not errors, errors
            result = {"ok": True,"existing_pages_checked": 5,"native_mouse_click": True,"double_click": True,"drag_no_click": True,"position_reload": True,"greeting_once": True,"sleep_wake_accelerated_clock": True,"hidden_timer_count": 0,"hide_recall_reload": True,"native_touch_drag": True,"mobile_width": 390,"bubble_in_view": True,"missing_action_fallback": True,"console_errors": len(errors),"screenshots": str(OUTPUT)}
            (OUTPUT / "pet-verification.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(result,ensure_ascii=False))
            call("Browser.close")
        finally:
            if ws:
                try: ws.close()
                except Exception: pass
            connections.close()
            for process in (browser, server):
                if process and process.poll() is None:
                    subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
                    process.wait(timeout=10)
            time.sleep(.3)


if __name__ == "__main__": main()
