const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname, 'news_visibility.js'), 'utf8');
let current = '2026-11-18T22:59:59Z'; // 23:59:59 in Stockholm.
class ClockDate extends Date {
  constructor(...args) { super(...(args.length ? args : [current])); }
}
const entry = (start, end) => ({dataset: {newsPub:start,newsClose:end}, hidden:true});
const items = [entry('2026-11-19','2026-11-20'),entry('2026-01-01','2026-11-18'),
               entry('2026-11-19','2026-11-19')];
const documentEvents={},windowEvents={},timers=[];
const context = {
  Date:ClockDate, Intl,
  document:{readyState:'loading',querySelectorAll:()=>items,
    addEventListener:(event,callback)=>documentEvents[event]=callback},
  window:{setInterval:(callback,delay)=>timers.push({callback,delay}),
    addEventListener:(event,callback)=>windowEvents[event]=callback}
};
vm.runInNewContext(script,context);
assert.equal(timers.length,0);
documentEvents.DOMContentLoaded();
assert.deepEqual(items.map(item=>item.hidden),[true,false,true]);
assert.equal(timers[0].delay,60000);
current='2026-11-18T23:00:00Z';timers[0].callback();
assert.deepEqual(items.map(item=>item.hidden),[false,true,false]);
current='2026-11-19T22:59:59Z';documentEvents.visibilitychange();
assert.deepEqual(items.map(item=>item.hidden),[false,true,false]);
current='2026-11-19T23:00:00Z';windowEvents.pageshow();
assert.deepEqual(items.map(item=>item.hidden),[false,true,true]);
current='2026-11-20T23:00:00Z';windowEvents.focus();
assert.deepEqual(items.map(item=>item.hidden),[true,true,true]);
// Summer time starts at UTC+2, including for visitors in other time zones.
const summer=entry('2026-07-01','2026-07-01');items.push(summer);
current='2026-06-30T21:59:59Z';timers[0].callback();assert.equal(summer.hidden,true);
current='2026-06-30T22:00:00Z';timers[0].callback();assert.equal(summer.hidden,false);
current='2026-07-01T22:00:00Z';timers[0].callback();assert.equal(summer.hidden,true);
console.log('Browser News visibility passed: Stockholm midnight, inclusive closing day, summer time, page resume and automatic refresh.');
