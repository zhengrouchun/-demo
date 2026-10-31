"""Read-only verification of the real numbered-note repair on port 8876."""
import base64
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/growmate-qa/numbered-note-fix"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
URL = "http://127.0.0.1:8876"
NOTE_ID = "e22796030f684285801bef930d372e22"


def main():
    with urllib.request.urlopen(URL + "/api/state", timeout=5) as response:
        state = json.load(response)
    note = next(n for n in state["notes"] if n["id"] == NOTE_ID)
    assert len(note["tasks"]) == 7 and not any(t["completed"] for t in note["tasks"])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="growmate-live-note-readonly-") as temporary, ExitStack() as stack:
        profile = Path(temporary)
        browser = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            active = profile / "DevToolsActivePort"
            for _ in range(60):
                if active.exists(): break
                time.sleep(.2)
            port = active.read_text().splitlines()[0]
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list") as response:
                target = next(t for t in json.load(response) if t["type"] == "page")
            ws = stack.enter_context(connect(target["webSocketDebuggerUrl"], max_size=20_000_000))
            sequence = 0
            errors = []

            def call(method, params=None):
                nonlocal sequence
                sequence += 1
                ws.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
                while True:
                    response = json.loads(ws.recv(timeout=20))
                    if response.get("method") == "Runtime.exceptionThrown": errors.append(response["params"])
                    if response.get("id") == sequence:
                        if "error" in response: raise RuntimeError(response["error"])
                        return response.get("result", {})

            def evaluate(expression):
                result = call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
                if "exceptionDetails" in result: raise RuntimeError(result["exceptionDetails"])
                return result.get("result", {}).get("value")

            def wait(expression):
                for _ in range(80):
                    if evaluate(expression): return
                    time.sleep(.1)
                raise AssertionError(expression)

            def screenshot(name):
                content = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                (OUTPUT / name).write_bytes(base64.b64decode(content["data"]))

            call("Page.enable"); call("Runtime.enable")
            # Private profile only: keep the pet from covering task controls in QA screenshots.
            call("Page.addScriptToEvaluateOnNewDocument", {"source": "localStorage.setItem('desktopPet.settings',JSON.stringify({version:1,enabled:true,visible:false,scale:1,randomActions:true,dialogueBubble:true,autoSleep:true,walkEnabled:false,position:null,lastDirectAt:null}));"})
            call("Emulation.setDeviceMetricsOverride", {"width":1440,"height":1000,"deviceScaleFactor":1,"mobile":False})
            call("Page.navigate", {"url": URL})
            wait("!!document.querySelector('.gm-sidebar nav')")
            evaluate("[...document.querySelectorAll('.gm-sidebar nav button')].find(e=>e.textContent.includes('记录')).click()")
            wait("!!document.querySelector('.gm-tabs')")
            evaluate("[...document.querySelectorAll('.gm-tabs button')].find(e=>e.textContent.includes('备忘录')).click()")
            wait("!!document.querySelector('.gm-note-list button')")
            evaluate("[...document.querySelectorAll('.gm-note-list button')].find(e=>e.textContent.includes('10.3学习要求')).click()")
            wait("document.querySelectorAll('.gm-learning-task').length===7")
            assert evaluate("document.querySelector('.gm-note-grid textarea').value") == note["markdown"]
            assert evaluate("document.querySelector('.gm-task-progress-label strong').textContent") == "已完成 0 / 7"
            assert evaluate("[...document.querySelectorAll('.gm-learning-task')].map(e=>e.dataset.taskId)") == [t["id"] for t in note["tasks"]]
            evaluate("document.querySelector('.gm-show-note-preview').click()")
            wait("(()=>{const r=document.querySelector('#gm-note-preview').getBoundingClientRect();return r.y>=0&&r.y<innerHeight/2})()")
            screenshot("actual-learning-note-desktop.png")
            call("Emulation.setDeviceMetricsOverride", {"width":390,"height":844,"deviceScaleFactor":1,"mobile":True})
            evaluate("document.querySelector('.gm-show-note-preview').click()")
            wait("(()=>{const r=document.querySelector('#gm-note-preview').getBoundingClientRect();return r.y>=0&&r.y<innerHeight/2})()")
            assert evaluate("(()=>{const row=document.querySelector('.gm-learning-task-main'),box=row.querySelector('input').getBoundingClientRect(),text=row.querySelector('.gm-task-text').getBoundingClientRect();return Math.abs(box.y-text.y)<8&&box.right<=text.left})()")
            assert evaluate("document.documentElement.scrollWidth<=innerWidth")
            screenshot("actual-learning-note-mobile.png")
            assert not errors, errors
            report = {"ok":True,"origin":URL,"note_id":NOTE_ID,"tasks":7,"completed":0,"source_matches_saved_note":True,"ids_match_database":True,"mobile_checkbox_before_text":True,"console_errors":len(errors),"read_only":True}
            (OUTPUT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report))
            call("Browser.close")
        finally:
            stack.close()
            if browser.poll() is None:
                subprocess.run(["taskkill.exe","/PID",str(browser.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            browser.wait(timeout=10)
            time.sleep(.3)


if __name__ == "__main__":
    main()

