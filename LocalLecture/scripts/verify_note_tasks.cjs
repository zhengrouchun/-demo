/* Existing TypeScript + Node test runner; no packages are installed. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const test = require('node:test');
const ts = require('../app/frontend/node_modules/typescript');
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, filename);
const { markdownLines, setMarkdownTask, numberedTaskConversion } = require('../app/frontend/src/growmate/markdownTasks.ts');
const tasks = text => markdownLines(text).filter(line => line.task);

test('the actual seven numbered study items become tasks only through explicit conversion', () => {
  const original = '1.收到后端的资料，开始测试搭建测试电路\n2.数码管显示（基础）\n3数码管显示（进阶）\n4.按键控制\n5.外部中断\n6.oled屏幕显示（上）\n7.整理知识点\n';
  assert.equal(tasks(original).length, 0);
  const converted = numberedTaskConversion(original);
  assert.equal(converted.count, 7);
  assert.deepEqual(tasks(converted.markdown).map(line => line.task.text), ['收到后端的资料，开始测试搭建测试电路', '数码管显示（基础）', '数码管显示（进阶）', '按键控制', '外部中断', 'oled屏幕显示（上）', '整理知识点']);
  assert.ok(converted.markdown.endsWith('\n'));
  assert.deepEqual(numberedTaskConversion(converted.markdown), { markdown: converted.markdown, count: 0 });
});

test('numbered conversion preserves code, dates, versions, paragraphs, existing tasks and CRLF', () => {
  const before = '# 10.3学习要求\r\n2026.10.03\r\n1.2\r\n2.3\r\n\r\n```text\r\n1.代码示例\r\n2.代码示例\r\n```\r\n    1.缩进代码\r\n    2.缩进代码\r\n正文\r\n- [x] 原有任务\r\n1、学习 GPIO\r\n2)学习中断\r\n';
  const after = numberedTaskConversion(before);
  assert.equal(after.count, 2);
  assert.equal(after.markdown, before.replace('1、学习 GPIO', '- [ ] 学习 GPIO').replace('2)学习中断', '- [ ] 学习中断'));
  assert.equal(tasks(after.markdown)[0].task.completed, true);
});

test('only Markdown task markers become checkboxes in mixed notes', () => {
  const text = '# 学习计划\n1. 按键控制\n- 普通列表\nTIM2 是定时器。\n`- [ ] 示例`\n- [ ] 外部中断\n- [x] GPIO\n- [X] 完成\n- [v] 非任务\n- [ ]没有分隔空格';
  assert.deepEqual(tasks(text).map(line => [line.task.text, line.task.completed]), [['外部中断', false], ['GPIO', true], ['完成', true]]);
});
test('complete and undo preserve every task and unrelated Markdown', () => {
  const text = '# 今天学习\n\n- [ ] **按键控制**  \n- [x] GPIO基础\n\n## 知识点\nTIM2\n![图片](/api/images/example.png)\n';
  const checked = setMarkdownTask(text, 2, true);
  assert.equal(checked, text.replace('- [ ] **按键控制**', '- [x] **按键控制**'));
  assert.equal(setMarkdownTask(checked, 2, false), text);
  assert.equal(tasks(checked).length, 2);
});
test('identical labels update only the clicked source line', () => {
  const text = '- [ ] 整理知识点\n\n- [ ] 整理知识点\n- [ ] 整理知识点';
  assert.equal(setMarkdownTask(text, 2, true), '- [ ] 整理知识点\n\n- [x] 整理知识点\n- [ ] 整理知识点');
});
test('CRLF, whitespace, Unicode and uppercase completion are preserved', () => {
  const text = '# 学习\r\n  - [ ] OLED（上）  \r\n- [X] GPIO\r\n';
  assert.equal(setMarkdownTask(text, 1, true), '# 学习\r\n  - [x] OLED（上）  \r\n- [X] GPIO\r\n');
  assert.equal(setMarkdownTask(text, 2, true), text);
  assert.equal(setMarkdownTask(text, 2, false), '# 学习\r\n  - [ ] OLED（上）  \r\n- [ ] GPIO\r\n');
});
test('backtick and tilde code fences never expose clickable examples', () => {
  for (const text of ['```c\nHAL_TIM_Base_Start_IT(&htim2);\n- [ ] 示例\n```\n- [ ] 学习', '~~~~markdown\n- [x] 示例\n~~~\n- [ ] 仍在代码中\n~~~~\n- [ ] 学习', '````\n```\n- [ ] 示例\n~~~\n````\n- [ ] 学习']) {
    assert.deepEqual(tasks(text).map(line => line.task.text), ['学习']);
    assert.equal(setMarkdownTask(text, 2, true), text);
  }
  assert.equal(tasks('```\n- [ ] 未闭合的代码示例').length, 0);
});
test('indented code remains code while lightly indented tasks are editable', () => {
  const text = '    - [ ] 代码\n\t- [x] 代码\n - [ ] 学习';
  assert.deepEqual(tasks(text).map(line => line.index), [2]);
  assert.equal(setMarkdownTask(text, 0, true), text);
  assert.equal(setMarkdownTask(text, 2, true), '    - [ ] 代码\n\t- [x] 代码\n - [x] 学习');
});
test('invalid indexes, non-tasks and repeated completion are safe no-ops', () => {
  const text = '普通文字\n- [x] 完成';
  for (const index of [-1, 2, 200, 0.5, NaN, 0]) assert.equal(setMarkdownTask(text, index, true), text);
  assert.equal(setMarkdownTask(text, 1, true), text);
});
const { reconcileTasks, taskProgress, presentTasks, dueLabel, dateOffset, defaultTaskView } = require('../app/frontend/src/growmate/noteTaskData.ts');
let taskCounter = 0;
const newTaskId = () => (++taskCounter).toString(16).padStart(32, '0');
test('stable UUIDs survive duplicate labels, toggles, ordinary renaming and cleanup', () => {
  let tasks = reconcileTasks('- [ ] 复习\n- [ ] 复习', [], newTaskId);
  const ids = tasks.map(t => t.id); assert.notEqual(ids[0], ids[1]);
  tasks[1].tags = ['STM32']; tasks[1].due_date = '2026-10-07';
  tasks = reconcileTasks('- [x] 复习\n- [ ] 复习第二部分', tasks, newTaskId);
  assert.deepEqual(tasks.map(t=>t.id),ids); assert.deepEqual(tasks[1].tags,['STM32']);
  tasks = reconcileTasks('- [ ] 新任务\n- [x] 复习\n- [ ] 复习第二部分',tasks,newTaskId);
  assert.equal(tasks[2].id,ids[1]);
  tasks = reconcileTasks('- [ ] 复习第二部分',tasks,newTaskId);
  assert.equal(tasks.length,1); assert.equal(tasks[0].id,ids[1]); assert.equal(tasks[0].due_date,'2026-10-07');
});
test('progress includes all tasks and rounds 2 of 7 to 29 percent', () => {
  const tasks = reconcileTasks(Array.from({length:7},(_,i)=>'- ['+(i<2?'x':' ')+'] 任务'+i).join('\n'),[],newTaskId);
  assert.deepEqual(taskProgress(tasks),{completed:2,total:7,percent:29});
  assert.deepEqual(taskProgress([]),{completed:0,total:0,percent:0});
});
test('hidden/completed-first presentation keeps original source indexes and delays movement', () => {
  const markdown='# 学习\n- [x] 已完成\n\n- [ ] 未完成\n正文';
  const tasks=reconcileTasks(markdown,[],newTaskId);
  assert.deepEqual(presentTasks(markdown,tasks,{...defaultTaskView,order:'incomplete'},{}).map(l=>l.index),[3,1]);
  assert.deepEqual(presentTasks(markdown,tasks,{...defaultTaskView,showCompleted:false},{}).map(l=>l.index),[3]);
  assert.deepEqual(presentTasks(markdown,tasks,{...defaultTaskView,showCompleted:false},{[tasks[0].id]:false}).map(l=>l.index),[1,3]);
  tasks[1].tags=['Java'];
  assert.deepEqual(presentTasks(markdown,tasks,{...defaultTaskView,tag:'Java'},{}).map(l=>l.index),[3]);
  assert.equal(markdown,'# 学习\n- [x] 已完成\n\n- [ ] 未完成\n正文');
});
test('deadline labels respect calendar boundaries and completed tasks have no overdue emphasis', () => {
  assert.equal(dateOffset('2026-12-31',1),'2027-01-01');
  assert.equal(dateOffset('2028-02-28',1),'2028-02-29');
  assert.equal(dueLabel('2026-10-03','2026-10-03',false),'今天');
  assert.equal(dueLabel('2026-10-04','2026-10-03',false),'明天');
  assert.equal(dueLabel('2026-10-02','2026-10-03',false),'已逾期');
  assert.equal(dueLabel('2026-10-02','2026-10-03',true),'10月2日');
  assert.equal(dueLabel(null,'2026-10-03',false),'');
});
