"""Chrome UI smoke test against temporary data; no audio devices are opened."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
OUTPUT = ROOT / "data" / "growmate-qa"
OUTPUT.mkdir(parents=True, exist_ok=True)


def main():
    with tempfile.TemporaryDirectory(prefix="growmate-ui-") as temporary:
        folder = Path(temporary)
        assert folder.resolve().parent == Path(tempfile.gettempdir()).resolve()
        server = None
        browser = None
        errors = []
        ws = None
        try:
            code = "from pathlib import Path; from meetingbro.growmate.web import create_app; import uvicorn,sys; uvicorn.run(create_app(Path(sys.argv[1]),enable_notifications=False),host='127.0.0.1',port=8876,log_level='warning')"
            server = subprocess.Popen([sys.executable, "-c", code, str(folder / "data")], cwd=ROOT / "app" / "backend", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            for _ in range(40):
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8876/health", timeout=1) as response:
                        assert json.load(response)["app"] == "GrowMate"
                    break
                except Exception: time.sleep(.2)
            else: raise RuntimeError("UI test backend did not start")
            profile = folder / "chrome-profile"
            browser = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            active = profile / "DevToolsActivePort"
            for _ in range(60):
                if active.exists(): break
                time.sleep(.2)
            port = active.read_text().splitlines()[0]
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list") as response: targets = json.load(response)
            target = next(t for t in targets if t["type"] == "page")
            ws = connect(target["webSocketDebuggerUrl"], max_size=20_000_000)
            command_id = 0

            def call(method, params=None):
                nonlocal command_id
                command_id += 1
                ws.send(json.dumps({"id": command_id, "method": method, "params": params or {}}))
                while True:
                    result = json.loads(ws.recv(timeout=20))
                    if result.get("method") == "Runtime.exceptionThrown": errors.append(result["params"])
                    if result.get("method") == "Runtime.consoleAPICalled" and result["params"].get("type") == "error": errors.append(result["params"])
                    if result.get("id") == command_id:
                        if "error" in result: raise RuntimeError(result["error"])
                        return result.get("result", {})

            def evaluate(expression):
                result = call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
                if "exceptionDetails" in result: raise RuntimeError(result["exceptionDetails"])
                return result.get("result", {}).get("value")

            def wait_text(text):
                for _ in range(50):
                    if evaluate(f"document.body.innerText.includes({json.dumps(text)})"): return
                    time.sleep(.1)
                raise AssertionError("Text not found: " + text)

            def click_text(selector, text):
                evaluate(f"Array.from(document.querySelectorAll({json.dumps(selector)})).find(e => e.textContent.trim() === {json.dumps(text)} || e.textContent.trim().endsWith({json.dumps(text)})).click()")
                time.sleep(.2)

            def set_value(selector, value):
                evaluate(f"(() => {{const e=document.querySelector({json.dumps(selector)}); const p=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(p,'value').set.call(e,{json.dumps(value)});e.dispatchEvent(new Event('input',{{bubbles:true}}));}})()")
                time.sleep(.1)

            def screenshot(name):
                data = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                (OUTPUT / name).write_bytes(base64.b64decode(data["data"]))

            call("Page.enable")
            call("Runtime.enable")
            call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1050, "deviceScaleFactor": 1, "mobile": False})
            call("Page.navigate", {"url": "http://127.0.0.1:8876"})
            wait_text("今天也慢慢来")
            screenshot("home-desktop.png")
            for label, heading in [("专注", "专注一会儿"), ("森林", "我的森林"), ("记录", "实时录音转文字"), ("陪伴", "陪伴你的每一天")]:
                click_text(".gm-sidebar nav button", label)
                wait_text(heading)
                assert evaluate("document.documentElement.scrollWidth <= window.innerWidth"), label
            click_text(".gm-sidebar nav button", "记录")
            wait_text("实时录音转文字")
            screenshot("records-desktop.png")
            click_text(".gm-tabs button", "📝 备忘录")
            set_value(".gm-note-grid input:not([type=file])", "浏览器验证笔记")
            set_value(".gm-note-grid textarea", "# 我的任务\n\n- [ ] 学习网络\n<script>unsafe</script>")
            click_text(".gm-note-grid button", "保存备忘录")
            wait_text("备忘录已保存到电脑")
            assert evaluate("document.querySelector('.gm-markdown').textContent.includes('学习网络')")
            assert not evaluate("!!document.querySelector('.gm-markdown script')")
            click_text(".gm-tabs button", "🥣 养胃记录")
            set_value(".gm-form-grid textarea", "粥和鸡蛋")
            click_text(".gm-card button", "保存养胃记录")
            wait_text("这一天的饮食与感受已保存")
            click_text(".gm-tabs button", "💚 心情日记")
            set_value(".gm-card textarea", "页面操作验证完成")
            click_text(".gm-card button", "保存心情")
            wait_text("今天的心情已记下")
            click_text(".gm-sidebar nav button", "专注")
            click_text(".gm-timer-card button", "开始专注")
            wait_text("结束本次专注")
            evaluate("window.confirm=()=>true")
            click_text(".gm-timer-card button", "结束本次专注")
            wait_text("本次专注已结束，没有获得水滴")
            call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
            click_text(".gm-bottom-nav button", "首页")
            wait_text("今天也慢慢来")
            assert evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "mobile home overflow"
            screenshot("home-mobile.png")
            for label in ["专注", "森林", "记录", "陪伴"]:
                click_text(".gm-bottom-nav button", label)
                assert evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "mobile " + label
            click_text(".gm-bottom-nav button", "记录")
            evaluate("document.documentElement.style.fontSize='200%'")
            time.sleep(.2)
            assert evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "200 percent text overflow"
            assert not errors, errors
            print(json.dumps({"ok": True, "pages_checked": 5, "notes_saved": True, "health_saved": True, "mood_saved": True, "focus_started_and_stopped": True, "raw_html_blocked": True, "mobile_width": 390, "text_enlargement": "200%", "console_errors": len(errors), "screenshots": str(OUTPUT)}, ensure_ascii=False))
            call("Browser.close")
        finally:
            if ws:
                try: ws.close()
                except Exception: pass
            for process in (browser, server):
                if process and process.poll() is None:
                    subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    process.wait(timeout=10)
            time.sleep(.3)


if __name__ == "__main__":
    main()
