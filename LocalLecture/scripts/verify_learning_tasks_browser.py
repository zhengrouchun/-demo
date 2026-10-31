"""Verify note tasks with a private Chrome profile + temporary DB; never uses real notes."""
import base64
from contextlib import ExitStack
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
PORT = 5173
URL = f"http://127.0.0.1:{PORT}"
OUTPUT = ROOT / "data" / "growmate-qa" / "note-task-upgrade"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
BODY = """# 学习计划

- [ ] 收到后端的资料，开始测试搭建测试电路
- [ ] 数码管显示（基础）
- [x] 数码管显示（进阶）
- [ ] 按键控制
- [ ] 外部中断
- [ ] OLED屏幕显示（上）
- [ ] 整理知识点

## 今日知识点

TIM2 是 STM32 的通用定时器。

```c
HAL_TIM_Base_Start_IT(&htim2);
- [ ] 代码里的示例
```

1. 普通有序列表
- 普通无序列表
**重要**：使用 `TIM2`。
<script>window.__unsafe=true</script>
"""


def main():
    with socket.socket() as probe: probe.bind(("127.0.0.1", PORT))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="growmate-note-tasks-") as temporary:
        folder = Path(temporary)
        browser = server = ws = None
        connections = ExitStack()
        errors = []
        try:
            code = "from pathlib import Path\nfrom datetime import timedelta\nfrom meetingbro.growmate.web import create_app\nimport uvicorn,sys\napp=create_app(Path(sys.argv[1]),enable_notifications=False)\nclock={'seconds':0,'original':None}\n@app.post('/__qa/advance')\nasync def advance(data:dict):\n    if clock['original'] is None:\n        clock['original']=app.state.repo.clock\n        app.state.repo.clock=lambda:clock['original']()+timedelta(seconds=clock['seconds'])\n    clock['seconds']+=int(data['seconds'])\n    return app.state.repo.state()\napp.router.routes.insert(0,app.router.routes.pop())\nuvicorn.run(app,host='127.0.0.1',port=5173,log_level='warning')"
            server = subprocess.Popen([sys.executable, "-c", code, str(folder / "data")], cwd=ROOT / "app/backend", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            for _ in range(60):
                if server.poll() is not None: raise RuntimeError("Temporary QA backend exited")
                try:
                    with urllib.request.urlopen(URL + "/health", timeout=1) as response: assert json.load(response)["app"] == "GrowMate"
                    break
                except Exception: time.sleep(.2)
            else: raise RuntimeError("Temporary QA backend failed to start")

            def request(path, data=None, raw=False):
                if data is not None and not raw: data = json.dumps(data).encode()
                req = urllib.request.Request(URL + "/api" + path, data=data, headers={"Content-Type": "application/octet-stream" if raw else "application/json", "X-GrowMate-Request": "1"})
                with urllib.request.urlopen(req, timeout=10) as response: return response.read()

            def api(path, data=None): return json.loads(request(path, data))
            note_id = api("/notes", {"title": "学习计划", "markdown": BODY})["id"]
            other_id = api("/notes", {"title": "另一本备忘录", "markdown": "# 原有正文\n\n其他内容不能丢失。"})["id"]
            uri = json.loads(request(f"/notes/{note_id}/images", PNG, raw=True))["uri"]
            markdown = BODY + f"\n![记录图片]({uri})\n"
            api("/notes", {"id": note_id, "title": "学习计划", "markdown": markdown})
            original = api("/state")
            baseline = next(n for n in original["notes"] if n["id"] == note_id)
            other = next(n for n in original["notes"] if n["id"] == other_id)

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
                for _ in range(80):
                    if evaluate(expression): return
                    time.sleep(.1)
                raise AssertionError("Condition failed: " + expression)

            def click_text(selector, text):
                expression = f"(() => {{const e=[...document.querySelectorAll({json.dumps(selector)})].find(e=>e.textContent.trim()==={json.dumps(text)}); if(!e)throw Error('Button missing: '+{json.dumps(text)}); e.click();}})()"
                evaluate(expression); time.sleep(.1)

            def set_value(selector, value):
                evaluate(f"(() => {{const e=document.querySelector({json.dumps(selector)}),p=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:e.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(p,'value').set.call(e,{json.dumps(value)});e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{{bubbles:true}}));}})()")
                time.sleep(.1)

            def open_notes():
                wait("!!document.querySelector('.gm-sidebar nav')")
                click_text(".gm-sidebar nav button", "📝记录")
                wait("!!document.querySelector('.gm-tabs')")
                click_text(".gm-tabs button", "📝 备忘录")
                wait("!!document.querySelector('.gm-note-grid textarea')")

            def task_click(label):
                selector = ".gm-markdown input[aria-label=" + json.dumps(label, ensure_ascii=False) + "]"
                evaluate(f"document.querySelector({json.dumps(selector)}).scrollIntoView({{block:'center'}})")
                rect = evaluate(f"(() => {{const r=document.querySelector({json.dumps(selector)}).getBoundingClientRect();return {{x:r.x+r.width/2,y:r.y+r.height/2}}}})()")
                call("Input.dispatchMouseEvent", {"type": "mousePressed", **rect, "button": "left", "buttons": 1, "clickCount": 1})
                call("Input.dispatchMouseEvent", {"type": "mouseReleased", **rect, "button": "left", "buttons": 0, "clickCount": 1})

            def saved():
                wait("document.querySelector('.gm-note-grid textarea') && !document.querySelector('.gm-note-grid textarea').disabled && ![...document.querySelectorAll('.gm-note-grid [role=status]')].some(e=>e.textContent.includes('草稿未保存'))")

            def current_note(): return next(n for n in api("/state")["notes"] if n["id"] == note_id)
            def screenshot(name):
                data = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                (OUTPUT / name).write_bytes(base64.b64decode(data["data"]))

            call("Page.enable"); call("Runtime.enable")
            call("Page.addScriptToEvaluateOnNewDocument", {"source": "if(!localStorage.getItem('desktopPet.settings'))localStorage.setItem('desktopPet.settings',JSON.stringify({version:1,enabled:true,visible:false,scale:1,randomActions:true,dialogueBubble:true,autoSleep:true,walkEnabled:false,position:null,lastDirectAt:null}));"})
            call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1050, "deviceScaleFactor": 1, "mobile": False})
            call("Page.navigate", {"url": URL})
            open_notes()
            click_text(".gm-note-list button strong", "学习计划")
            assert evaluate("document.querySelectorAll('.gm-markdown input[type=checkbox]').length") == 7
            assert evaluate("document.querySelectorAll('.gm-markdown input:checked').length") == 1
            assert evaluate("document.querySelector('.gm-markdown').textContent.includes('TIM2 是 STM32')")
            assert evaluate("document.querySelector('.gm-markdown pre').textContent.includes('HAL_TIM_Base_Start_IT')")
            assert not evaluate("!!document.querySelector('.gm-markdown script') || !!window.__unsafe")
            assert evaluate("document.querySelector('.gm-markdown img').getAttribute('src')") == uri

            task_click("按键控制"); saved()
            expected = markdown.replace("- [ ] 按键控制", "- [x] 按键控制")
            assert current_note()["markdown"] == expected
            assert evaluate("document.querySelector('.gm-note-grid textarea').value") == expected
            assert evaluate("(() => {const t=[...document.querySelectorAll('.gm-learning-task .gm-task-text')].find(e=>e.textContent==='按键控制');const s=getComputedStyle(t);return t.classList.contains('completed') && s.textDecorationLine.includes('line-through') && Number(s.opacity)<1})()")
            assert len(api("/state")["notes"]) == 2

            # Progress/visibility/order are presentation only: never rewrite or delete source tasks.
            assert evaluate("document.querySelector('.gm-task-progress-label strong').textContent") == "已完成 2 / 7"
            assert evaluate("document.querySelector('.gm-task-progress-label span').textContent") == "29%"
            baseline_ids = {t["text"]: t["id"] for t in current_note()["tasks"]}
            evaluate("document.querySelector('.gm-task-filters input[type=checkbox]').click()")
            wait("document.querySelectorAll('.gm-learning-task').length===5")
            assert current_note()["markdown"] == expected
            evaluate("document.querySelector('.gm-task-filters input[type=checkbox]').click()")
            wait("document.querySelectorAll('.gm-learning-task').length===7")
            set_value(".gm-task-filters select", "incomplete")
            assert evaluate("[...document.querySelectorAll('.gm-learning-task .gm-task-text')].slice(-2).every(e=>e.classList.contains('completed'))")
            assert current_note()["markdown"] == expected
            set_value(".gm-task-filters select", "original")

            evaluate("""document.querySelector('[aria-label="设置任务：外部中断"]').click()""")
            set_value(".gm-task-editor input:not([type=date])", "STM32, Proteus")
            click_text(".gm-task-editor button", "今天")
            assert evaluate("document.querySelector('.gm-task-editor input[type=date]').value") == api("/state")["today"]
            click_text(".gm-task-editor button", "明天")
            assert evaluate("document.querySelector('.gm-task-editor input[type=date]').value") > api("/state")["today"]
            click_text(".gm-task-editor button", "无日期")
            assert evaluate("document.querySelector('.gm-task-editor input[type=date]').value") == ""
            set_value(".gm-task-editor input[type=date]", "2026-10-07")
            click_text(".gm-task-editor button", "保存任务信息"); saved()
            wait("!document.querySelector('.gm-task-editor')")
            tagged = next(t for t in current_note()["tasks"] if t["text"]=="外部中断")
            assert tagged["tags"]==["STM32","Proteus"] and tagged["due_date"]=="2026-10-07"
            assert tagged["id"]==baseline_ids["外部中断"]
            set_value(".gm-task-filters select:nth-of-type(1)", "original")
            # The second select is the tag selector (each select lives inside its own label).
            set_value(".gm-task-filters label:nth-child(3) select", "STM32")
            assert evaluate("document.querySelectorAll('.gm-learning-task').length") == 1
            assert evaluate("document.querySelector('.gm-learning-task .gm-task-text').textContent") == "外部中断"
            assert current_note()["markdown"] == expected
            set_value(".gm-task-filters label:nth-child(3) select", "")

            call("Page.reload"); open_notes()
            assert evaluate("""document.querySelector('.gm-markdown input[aria-label="按键控制"]').checked""") is True
            reopened = next(t for t in current_note()["tasks"] if t["id"]==tagged["id"])
            assert reopened["tags"]==["STM32","Proteus"] and reopened["due_date"]=="2026-10-07"
            assert {t["text"]:t["id"] for t in current_note()["tasks"]}==baseline_ids
            # Switch away and back via saved records; state is not a transient checkbox flag.
            click_text(".gm-note-list button strong", "另一本备忘录")
            assert evaluate("document.querySelectorAll('.gm-markdown input').length") == 0
            click_text(".gm-note-list button strong", "学习计划")
            assert evaluate("""document.querySelector('.gm-markdown input[aria-label="按键控制"]').checked""") is True
            task_click("按键控制"); saved()
            assert current_note()["markdown"] == markdown
            assert not evaluate("[...document.querySelectorAll('.gm-learning-task .gm-task-text')].find(e=>e.textContent==='按键控制').classList.contains('completed')")

            # Unsaved ordinary edits must be included, not overwritten by task updates.
            edited = markdown + "\n今天整理了 TIM2 的配置步骤。\n"
            set_value(".gm-note-grid textarea", edited)
            task_click("外部中断"); saved()
            expected = edited.replace("- [ ] 外部中断", "- [x] 外部中断")
            assert current_note()["markdown"] == expected
            task_click("按键控制"); saved()
            expected = expected.replace("- [ ] 按键控制", "- [x] 按键控制")

            # Real keyboard space toggles the native checkbox.
            evaluate("""document.querySelector('.gm-markdown input[aria-label="整理知识点"]').focus()""")
            call("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": " ", "code": "Space", "windowsVirtualKeyCode": 32})
            call("Input.dispatchKeyEvent", {"type": "keyUp", "key": " ", "code": "Space", "windowsVirtualKeyCode": 32})
            saved()
            expected = expected.replace("- [ ] 整理知识点", "- [x] 整理知识点")
            assert current_note()["markdown"] == expected
            evaluate("document.querySelector('.gm-task-overview').scrollIntoView({block:'start'})")
            time.sleep(.1); screenshot("tasks-desktop.png")

            # Failed writes preserve draft and dirty state, and manual retry survives a reload.
            evaluate("window.__noteOriginalFetch=window.fetch;window.fetch=(url,options)=>url==='/api/notes'&&options?.method==='POST'?Promise.resolve(new Response(JSON.stringify({detail:'测试：保存暂时失败'}),{status:503,headers:{'Content-Type':'application/json'}})):window.__noteOriginalFetch(url,options)")
            task_click("OLED屏幕显示（上）")
            wait("document.body.innerText.includes('测试：保存暂时失败')")
            wait("!document.querySelector('.gm-note-grid textarea').disabled")
            failed_draft = expected.replace("- [ ] OLED屏幕显示（上）", "- [x] OLED屏幕显示（上）")
            assert current_note()["markdown"] == expected
            assert evaluate("JSON.parse(localStorage.getItem('growmate.note-draft')).markdown") == failed_draft
            call("Page.reload"); open_notes()
            assert evaluate("document.querySelector('.gm-note-grid textarea').value") == failed_draft
            assert evaluate("document.querySelector('.gm-note-grid [role=status]').textContent.includes('草稿未保存')")
            click_text(".gm-note-grid button", "保存备忘录"); saved()
            expected = failed_draft
            assert current_note()["markdown"] == expected

            # Export and existing image metadata are unchanged apart from the checkbox markers.
            state = api("/state")
            assert len(state["notes"]) == 2
            assert next(n for n in state["notes"] if n["id"] == other_id) == other
            assert current_note()["created_at"] == baseline["created_at"]
            assert state["images"] == original["images"]
            archive = zipfile.ZipFile(io.BytesIO(request(f"/notes/{note_id}/download")))
            image_path = "images/" + uri.rsplit("/", 1)[-1]
            exported = expected.replace(uri, image_path)
            assert archive.read("学习计划.md").decode("utf-8") == "# 学习计划\n\n" + exported + "\n"
            assert archive.read(image_path) == PNG

            call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
            evaluate("document.querySelector('.gm-task-overview').scrollIntoView({block:'start'})")
            assert evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert evaluate("document.querySelectorAll('.gm-markdown input[type=checkbox]').length") == 7
            screenshot("tasks-mobile.png")

            # A fresh note can be completed without a prior manual save.
            # Delay the write, change tabs, then check that the returned note id is remembered.
            call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1050, "deviceScaleFactor": 1, "mobile": False})
            click_text(".gm-note-grid button", "新建备忘录")
            set_value(".gm-note-grid input:not([type=file])", "自动保存新备忘录")
            set_value(".gm-note-grid textarea", "- [ ] 新任务\n\n说明")
            evaluate("window.__noteOriginalFetch=window.fetch;window.fetch=(url,options)=>url==='/api/notes'&&options?.method==='POST'?new Promise(resolve=>setTimeout(()=>resolve(window.__noteOriginalFetch(url,options)),500)):window.__noteOriginalFetch(url,options)")
            task_click("新任务")
            wait("document.querySelector('.gm-note-grid textarea').disabled && [...document.querySelectorAll('.gm-note-grid button')].every(e=>e.disabled)")
            click_text(".gm-tabs button", "🥣 养胃记录")
            time.sleep(.8)
            new = next(n for n in api("/state")["notes"] if n["title"] == "自动保存新备忘录")
            assert new["markdown"] == "- [x] 新任务\n\n说明"
            assert evaluate("JSON.parse(localStorage.getItem('growmate.note-draft')).id") == new["id"]
            evaluate("window.fetch=window.__noteOriginalFetch")
            click_text(".gm-tabs button", "📝 备忘录")
            assert evaluate("""document.querySelector('.gm-markdown input[aria-label="新任务"]').checked""") is True
            task_click("新任务"); saved()
            assert len(api("/state")["notes"]) == 3
            assert next(n for n in api("/state")["notes"] if n["id"] == new["id"])["markdown"] == "- [ ] 新任务\n\n说明"
            click_text(".gm-tabs button", "🎙️ 实时转文字")
            wait("document.body.innerText.includes('实时录音转文字')")
            # Duplicate task instances use different ids, and editor rename/delete synchronizes metadata.
            duplicate = api("/notes", {"title":"同名任务验证","markdown":"- [ ] 复习\n- [ ] 复习"})["note"]
            first_id,second_id = [t["id"] for t in duplicate["tasks"]]
            assert first_id!=second_id
            call("Page.reload"); open_notes()
            click_text(".gm-note-list button strong","同名任务验证")
            selector = f'.gm-learning-task[data-task-id="{second_id}"] .gm-task-edit'
            evaluate(f"document.querySelector({json.dumps(selector)}).click()")
            set_value(".gm-task-editor input:not([type=date])","Java")
            set_value(".gm-task-editor input[type=date]","2026-10-07")
            click_text(".gm-task-editor button","保存任务信息"); saved()
            set_value(".gm-note-grid textarea","- [ ] 复习\n- [ ] 复习第二部分")
            click_text(".gm-note-grid button","保存备忘录"); saved()
            changed = next(n for n in api("/state")["notes"] if n["id"]==duplicate["id"])
            assert [t["id"] for t in changed["tasks"]]==[first_id,second_id]
            assert changed["tasks"][1]["tags"]==["Java"]
            set_value(".gm-note-grid textarea","- [ ] 复习第二部分")
            click_text(".gm-note-grid button","保存备忘录"); saved()
            changed = next(n for n in api("/state")["notes"] if n["id"]==duplicate["id"])
            assert len(changed["tasks"])==1 and changed["tasks"][0]["id"]==second_id
            assert changed["tasks"][0]["due_date"]=="2026-10-07"

            def advance(seconds):
                req=urllib.request.Request(URL+"/__qa/advance",data=json.dumps({"seconds":seconds}).encode(),headers={"Content-Type":"application/json"})
                with urllib.request.urlopen(req,timeout=10): pass
                evaluate("document.dispatchEvent(new Event('visibilitychange'))")

            before_balance=api("/state")["water_balance"]
            click_text(".gm-learning-task button","▶ 开始专注")
            wait("document.body.innerText.includes('专注一会儿')")
            active=api("/state")["timer"]
            assert active["task_id"]==second_id and active["task_note_id"]==duplicate["id"]
            first_session=active["session_id"]
            assert evaluate("document.body.innerText.includes('正在专注：复习第二部分')")
            advance(25*60)
            wait("!!document.querySelector('.gm-task-focus-result')")
            focused=next(n for n in api("/state")["notes"] if n["id"]==duplicate["id"])["tasks"][0]
            assert focused["focus_seconds"]==1500 and not focused["completed"]
            assert api("/state")["water_balance"]==before_balance+7
            for _ in range(3): api("/state")
            assert api("/state")["water_balance"]==before_balance+7
            screenshot("task-focus-result.png")
            click_text(".gm-task-focus-result button","继续保持未完成")
            wait("!document.querySelector('.gm-task-focus-result')")
            api(f"/focus/{first_session}/task-decision",{"completed":True})
            assert not next(n for n in api("/state")["notes"] if n["id"]==duplicate["id"])["tasks"][0]["completed"]
            open_notes()
            click_text(".gm-learning-task button","▶ 开始专注")
            wait("document.body.innerText.includes('专注一会儿')")
            second_session=api("/state")["timer"]["session_id"]
            assert second_session!=first_session
            advance(25*60)
            wait("!!document.querySelector('.gm-task-focus-result')")
            click_text(".gm-task-focus-result button","完成任务")
            wait("!document.querySelector('.gm-task-focus-result')")
            latest=next(n for n in api("/state")["notes"] if n["id"]==duplicate["id"])
            assert latest["markdown"]=="- [x] 复习第二部分"
            assert latest["tasks"][0]["focus_seconds"]==3000
            assert api("/state")["water_balance"]==before_balance+15
            api(f"/focus/{second_session}/task-decision",{"completed":True})
            assert api("/state")["water_balance"]==before_balance+15
            open_notes()
            assert evaluate("document.querySelector('.gm-learning-task input').checked") is True
            task_click("复习第二部分"); saved()
            task_click("复习第二部分"); saved()
            assert api("/state")["water_balance"]==before_balance+15
            assert evaluate("document.querySelector('.gm-task-time').textContent.includes('50 min')")
            growth=api("/state")["trees"][0]["growth"]
            api("/tree/water",{"amount":1})
            assert api("/state")["trees"][0]["growth"]==growth+1
            assert api("/state")["water_balance"]==before_balance+14
            # Plain non-task Markdown has no progress or task controls.
            click_text(".gm-note-list button strong","另一本备忘录")
            assert not evaluate("!!document.querySelector('.gm-task-overview')")
            click_text(".gm-tabs button","🥣 养胃记录")
            wait("document.body.innerText.includes('今天有好好吃饭吗')")
            click_text(".gm-tabs button","💚 心情日记")
            wait("document.body.innerText.includes('今天过得怎么样')")
            click_text(".gm-tabs button","🎙️ 实时转文字")
            wait("document.body.innerText.includes('实时录音转文字')")

            # A running Pomodoro survives reload and displays its real settings.
            api("/focus/start", {"mode":"pomodoro","minutes":45,"rest":7,"cycles":2,"task_id":second_id})
            running_timer=api("/state")["timer"]
            call("Page.reload")
            wait("!!document.querySelector('.gm-sidebar nav')")
            evaluate("[...document.querySelectorAll('.gm-sidebar nav button')].find(e=>e.textContent.includes('专注')).click()")
            wait("document.body.innerText.includes('专注一会儿')")
            wait("document.querySelector('.gm-segmented .selected')?.textContent==='番茄钟'")
            assert evaluate("[...document.querySelectorAll('.gm-stack input[type=number]')].map(e=>e.value)")==["45","7","2"]
            assert evaluate("document.querySelector('.gm-stack select').value")==second_id
            assert api("/state")["timer"]["session_id"]==running_timer["session_id"]
            assert api("/state")["timer"]["deadline"]==running_timer["deadline"]
            api("/focus/interrupt",{})

            # Reproduce the user's existing numbered note, including the missing dot after 3.
            numbered_body="1.收到后端的资料，开始测试搭建测试电路\n2.数码管显示（基础）\n3数码管显示（进阶）\n4.按键控制\n5.外部中断\n6.oled屏幕显示（上）\n7.整理知识点\n"
            numbered_id=api("/notes",{"title":"10.3学习要求","markdown":numbered_body})["id"]
            call("Page.reload"); open_notes()
            click_text(".gm-note-list button strong","10.3学习要求")
            assert not evaluate("!!document.querySelector('.gm-task-overview')")
            assert evaluate("document.querySelector('.gm-numbered-task-hint').textContent.includes('7 条编号内容')")
            click_text(".gm-convert-tasks","编号列表转为任务（7）"); saved()
            wait("document.querySelectorAll('.gm-learning-task').length===7")
            converted_note=next(n for n in api("/state")["notes"] if n["id"]==numbered_id)
            assert len(converted_note["tasks"])==7
            assert converted_note["markdown"].count('- [ ] ')==7
            assert converted_note["tasks"][2]["text"]=="数码管显示（进阶）"
            assert api("/state")["water_balance"]==before_balance+14
            converted_ids=[t["id"] for t in converted_note["tasks"]]
            call("Page.reload"); open_notes()
            click_text(".gm-note-list button strong","10.3学习要求")
            assert [t["id"] for t in next(n for n in api("/state")["notes"] if n["id"]==numbered_id)["tasks"]]==converted_ids
            click_text(".gm-show-note-preview","查看任务（7）")
            wait("(()=>{const r=document.querySelector('#gm-note-preview').getBoundingClientRect();return r.y>=0&&r.y<innerHeight/2})()")
            screenshot("numbered-note-converted-desktop.png")
            call("Emulation.setDeviceMetricsOverride", {"width":390,"height":844,"deviceScaleFactor":1,"mobile":True})
            click_text(".gm-show-note-preview","查看任务（7）")
            wait("(()=>{const r=document.querySelector('#gm-note-preview').getBoundingClientRect();return r.y>=0&&r.y<innerHeight/2})()")
            screenshot("numbered-note-converted-mobile.png")
            assert evaluate("(()=>{const row=document.querySelector('.gm-learning-task-main'),box=row.querySelector('input').getBoundingClientRect(),text=row.querySelector('.gm-task-text').getBoundingClientRect();return Math.abs(box.y-text.y)<8&&box.right<=text.left})()")

            assert not errors, errors
            result = {"ok": True, "tasks_rendered": 7, "native_mouse_and_keyboard": True, "complete_and_undo": True, "completed_style": True, "refresh_and_note_switch": True, "ordinary_edits_preserved": True, "fenced_code_and_html_safe": True, "failed_save_draft_retry": True, "pending_edit_lock": True, "new_note_tab_switch_no_duplicate": True, "other_notes_and_images_preserved": True, "markdown_export": True, "mobile_width": 390, "voice_tab_present": True, "console_errors": len(errors), "screenshots": str(OUTPUT)}
            result.update({"progress_2_of_7_29_percent":True,"hide_and_sort_source_unchanged":True,"tags_and_dates_reload":True,"stable_duplicate_ids_and_cleanup":True,"task_focus_binding_and_50_minutes":True,"focus_does_not_auto_complete":True,"rewards_no_repeat":True,"tree_growth_same_balance":True,"health_mood_voice_tabs":True,"running_pomodoro_settings_survive_reload":True})
            result.update({"actual_numbered_note_conversion":True,"converted_note_refresh_and_stable_ids":True,"mobile_preview_shortcut":True})
            (OUTPUT / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(result, ensure_ascii=False))
            call("Browser.close")
        finally:
            if ws:
                try: ws.close()
                except Exception: pass
            connections.close()
            for process in (browser, server):
                if process and process.poll() is None:
                    subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                    process.wait(timeout=10)
            time.sleep(.3)


if __name__ == "__main__": main()
