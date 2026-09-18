const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const source = fs.readFileSync(path.join(__dirname, '../src/platforms/hkticketing.py'), 'utf8');
const script = source.match(/HKTICKETING_PRIVILEGE_SCRIPT = r'''([\s\S]*?)'''/)[1];
const fixture = fs.readFileSync(path.join(__dirname, 'fixtures/hkt_privilege.html'), 'utf8');
let tests = 0;
function page(html = fixture) {
  const dom = new JSDOM(html, {runScripts: 'outside-only', url: 'https://hkt.hkticketing.com/#/allEvents/detail?projectId=test'});
  const w = dom.window;
  w.HTMLElement.prototype.getClientRects = function() {return this.hidden ? [] : [{}]};
  const input = w.document.querySelector('input');
  const buttons = w.document.querySelectorAll('.mz-modal-mobile-footer-btn');
  let confirmed = 0, cancelled = 0, changes = 0;
  buttons[0]?.addEventListener('click', () => cancelled++);
  buttons[1]?.addEventListener('click', () => confirmed++);
  input?.addEventListener('input', () => changes++);
  return {w, input, buttons, run: (answers=[]) => w.eval(script.replace('__ANSWERS__', JSON.stringify(answers))),
    counts: () => ({confirmed, cancelled, changes})};
}
function test(name, fn) {fn(); tests++; console.log('PASS', name)}
test('captured form fills leading zeroes, updates framework, submits once', () => {
  const p=page();
  // Emulate React's per-element value tracker: native setter must bypass it.
  Object.defineProperty(p.input, 'value', {configurable:true,
    get() { return p.w.HTMLInputElement.prototype.__lookupGetter__('value').call(this) },
    set() { throw Error('must use native input setter') }});
  assert.equal(p.run(['012345']).status, 'filled');
  assert.equal(p.input.value, '012345');
  assert.deepEqual(p.counts(), {confirmed:0,cancelled:0,changes:1});
  assert.equal(p.run(['012345']).status, 'submitted');
  assert.equal(p.run(['012345']).status, 'already_submitted');
  assert.deepEqual(p.counts(), {confirmed:1,cancelled:0,changes:1});
  p.w.document.body.innerHTML=fixture;
  assert.equal(p.run(['012345']).status, 'already_submitted');
});
test('no answer, full card number and wrong length never submit', () => {
  const p=page();
  for(const a of [[],['12345'],['1234567890123456'],['ABCDEF']])
    assert.equal(p.run(a).status, 'missing_answer');
  assert.equal(p.input.value, '');
  assert.equal(p.counts().confirmed,0);
});
test('manual input is preserved', () => {
  const p=page(); p.input.value='999999';
  assert.equal(p.run(['012345']).status,'manual_value');
  assert.equal(p.input.value,'999999');
});
test('hidden form ignored; disabled confirmation waits', () => {
  const p=page(); p.input.hidden=true;
  assert.equal(p.run(['012345']).status,'absent');
  p.input.hidden=false;
  p.run(['012345']); p.buttons[1].setAttribute('aria-disabled','true');
  assert.equal(p.run(['012345']).status,'waiting_button');
  assert.equal(p.counts().confirmed,0);
});
test('traditional and English six digit questions', () => {
  for(const prompt of ['請輸入付款卡前六碼','Please enter the first six digits of your card']) {
    const p=page(fixture.replace('请输入付款卡前6位数字作购票',prompt));
    assert.equal(p.run(['1234']).status,'missing_answer');
    assert.equal(p.run(['012345']).status,'filled');
  }
});
test('generic membership codes preserve punctuation and safe JS quoting', () => {
  const p=page(fixture.replace('请输入付款卡前6位数字作购票','请输入会员优先购代码'));
  const answer='member"\\code';
  assert.equal(p.run([answer]).status,'filled');
  assert.equal(p.input.value,answer);
});
test('desktop confirmation button and no cancel fallback', () => {
  const p=page(fixture.replace('<div class="mz-modal-mobile-footer-btn">确定</div>', '<button>Confirm</button>'));
  p.run(['012345']); assert.equal(p.run(['012345']).status,'submitted');
  const q=page(fixture.replace('<div class="mz-modal-mobile-footer-btn">确定</div>',''));
  q.run(['012345']); assert.equal(q.run(['012345']).status,'waiting_button');
  assert.equal(q.counts().cancelled,0);
});
test('unrelated login or payment inputs untouched', () => {
  const p=page('<input name="password"><input name="cardNumber">');
  assert.equal(p.run(['012345']).status,'absent');
  assert.equal(p.input.value,'');
});
console.log(`${tests} DOM regression tests passed`);
