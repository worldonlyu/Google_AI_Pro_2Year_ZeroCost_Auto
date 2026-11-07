// Pure rendering test; no browser, saved accounts, HTTP requests or credentials.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, '../templates/index.html'), 'utf8');
const start = html.indexOf('    function renderAccounts(');
const end = html.indexOf('    function renderLogs(', start);
assert(start >= 0 && end > start);
const tbody = {innerHTML: ''};
const ctx = vm.createContext({
  document: {getElementById: id => {assert.equal(id, 'accountsTbody'); return tbody;}},
  selectedStartSteps: {}, openedBrowserMap: {}, copiedAccountMap: {},
  statusBadgeHtml: s => s, stepDotsHtml: () => '',
});
vm.runInContext(html.slice(start, end), ctx);

for (const [fields, disabledCount] of [
  [{automation_locked: true, status: 'error'}, 4],
  [{status: 'completed'}, 4],
  [{run_locked: true, is_running: true, status: 'running'}, 3],
  [{status: 'pending'}, 0],
]) {
  ctx.accounts = [{id: 'fixture', email: '', password: '', ...fields}];
  vm.runInContext('renderAccounts(accounts)', ctx);
  assert.equal((tbody.innerHTML.match(/\bdisabled\b/g) || []).length, disabledCount);
  assert.equal(tbody.innerHTML.includes('Protected from reuse'), disabledCount > 0);
  if (fields.is_running) {
    const button = tbody.innerHTML.match(/<button\b[^>]*onclick="stopSingle[^>]*>/s);
    assert(button);
    assert(!button[0].includes('disabled'));
  }
}
console.log('PASS: four UI fixtures; Run/Browser/Reset protected, Stop remains available.');
