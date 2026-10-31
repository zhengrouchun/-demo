/* Uses the project's installed TypeScript and Node's test runner; installs nothing. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const test = require('node:test');
const root = path.resolve(__dirname, '..');
const ts = require(path.join(root, 'app/frontend/node_modules/typescript'));
require.extensions['.ts'] = (module, filename) => {
  const text = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  module._compile(text, filename);
};
const dir = path.join(root, 'app/frontend/src/components/DesktopPet');
const { PetController } = require(path.join(dir, 'petActions.ts'));
const { PET_CONFIG, DEFAULT_SETTINGS, getTimeContext, petSize } = require(path.join(dir, 'petConfig.ts'));
const { selectDialogue } = require(path.join(dir, 'dialogueEngine.ts'));
const { loadPetSettings, savePetSettings, clampPosition, consumeGreeting } = require(path.join(dir, 'petStorage.ts'));
function clock(random = () => 0) {
  let now = new Date(2026, 9, 2, 15).getTime(), id = 0;
  const timers = new Map();
  const fake = { now: () => now, random, setTimer: (fn, delay) => { timers.set(++id, { at: now + delay, fn }); assert.ok(timers.size <= 1, 'only one scheduler timer'); return id; }, clearTimer: id => timers.delete(id) };
  return { fake, timers, advance: delay => { const end = now + delay; for (let i = 0; ; i++) { assert.ok(i < 10000); const next = [...timers].sort((a, b) => a[1].at - b[1].at)[0]; if (!next || next[1].at > end) break; now = next[1].at; timers.delete(next[0]); next[1].fn(); } now = end; } };
}
function storage(value = null) { return { getItem: () => value, setItem: (_, next) => { value = next; } }; }
const context = { currentTime: new Date(2026, 9, 2, 15), clickCount: 1, idleDuration: 0, currentState: 'idle', lastDialogue: null, lastCategory: null, recentDialogues: [], lastDirectAt: null };

test('time boundaries and responsive sizes', () => {
  for (const [h, m, expected] of [[5,59,'LATE_NIGHT'],[6,0,'MORNING'],[10,0,'DAY'],[18,0,'EVENING'],[23,29,'EVENING'],[23,30,'LATE_NIGHT']]) assert.equal(getTimeContext(new Date(2026,9,2,h,m)),expected);
  assert.equal(petSize(390,844,1).width,110);
  assert.equal(petSize(1440,1050,1).width,180);
});
test('malformed or blocked storage and out-of-window positions stay safe', () => {
  assert.equal(loadPetSettings(storage('{bad')).scale,1);
  assert.equal(loadPetSettings(storage('null')).visible,true);
  assert.equal(loadPetSettings(storage('{"scale":99,"position":{"x":"bad","y":0}}')).scale,1.4);
  const blocked = { getItem: () => { throw Error('blocked'); }, setItem: () => { throw Error('blocked'); } };
  assert.equal(loadPetSettings(blocked).enabled,true); savePetSettings(DEFAULT_SETTINGS,blocked);
  assert.deepEqual(clampPosition({x:9999,y:-90},180,210,390,844),{x:210,y:0});
});
test('greeting is claimed once in a day/session', () => { const s = storage(); assert.equal(consumeGreeting(new Date(2028,0,1),s),true); assert.equal(consumeGreeting(new Date(2028,0,1),s),false); });
test('no recent dialogue repetition and no late-night line in afternoon', () => {
  const recent = ['嗯。','怎么了。','想吃什么。','别闹。'];
  for (let i=0;i<200;i++) { const result=selectDialogue({...context,recentDialogues:recent,idleDuration:700000},()=>i/200); assert.ok(!recent.includes(result.text)); assert.notEqual(result.text,'……又熬夜。'); }
});
test('direct dialogue cooldown survives saved settings and repeated taps prefer minimal', () => {
  assert.equal(selectDialogue(context,()=>.99).category,'direct');
  const s=storage(); savePetSettings({...DEFAULT_SETTINGS,lastDirectAt:context.currentTime.getTime()},s);
  assert.notEqual(selectDialogue({...context,lastDirectAt:loadPetSettings(s).lastDirectAt},()=>.99).category,'direct');
  assert.equal(selectDialogue({...context,clickCount:3},()=>.3).text,'别闹。');
});
test('single/double click disambiguation, count reset, one replacing bubble', () => {
  const c=clock(), pet=new PetController({...DEFAULT_SETTINGS,randomActions:false},c.fake); pet.start();
  pet.preparePointer(); pet.queueClick(); assert.equal(pet.getSnapshot().clickCount,0);
  c.advance(100); pet.preparePointer(); pet.queueClick(); assert.equal(pet.getSnapshot().clickCount,2); assert.equal(pet.getSnapshot().state,'surprise');
  const first=pet.getSnapshot().bubble.id; c.advance(1500); pet.preparePointer(); pet.queueClick(); c.advance(300);
  assert.equal(pet.getSnapshot().clickCount,3); assert.ok(pet.getSnapshot().bubble.id>first);
  c.advance(6500); assert.equal(pet.getSnapshot().clickCount,0); assert.equal(pet.getSnapshot().bubble,null); pet.stop(); assert.equal(c.timers.size,0);
});
test('drag supersedes queued clicks and random actions', () => {
  const c=clock(), pet=new PetController(DEFAULT_SETTINGS,c.fake); pet.start(); pet.queueClick(); pet.beginDrag();
  c.advance(50000); assert.equal(pet.getSnapshot().state,'drag'); assert.equal(pet.getSnapshot().clickCount,0); assert.equal(pet.requestAction('blink'),false);
  pet.endDrag(); assert.equal(pet.getSnapshot().state,'idle'); pet.stop(); assert.equal(c.timers.size,0);
});
test('auto sleep pauses random actions, any activity wakes without a bubble', () => {
  const c=clock(), pet=new PetController(DEFAULT_SETTINGS,c.fake); pet.start(); c.advance(PET_CONFIG.sleep.timeout+2000);
  assert.equal(pet.getSnapshot().state,'sleep'); assert.equal(c.timers.size,0);
  pet.activity(); assert.equal(pet.getSnapshot().state,'idle'); assert.equal(pet.getSnapshot().bubble,null);
  pet.stop(); c.advance(900000); assert.equal(c.timers.size,0);
});
test('repeat lifecycle and options never accumulate timers; V0.2 WALK stays inactive', () => {
  const c=clock(), pet=new PetController(DEFAULT_SETTINGS,c.fake);
  for(let i=0;i<30;i++) { pet.start(); pet.start(); pet.updateOptions({...DEFAULT_SETTINGS,randomActions:false,autoSleep:false}); c.advance(10000); assert.equal(c.timers.size,0); assert.equal(pet.requestAction('walk'),false); pet.stop(); }
});
