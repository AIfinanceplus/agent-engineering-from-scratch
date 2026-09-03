/* Optional end-to-end check. Requires Playwright and a Chromium executable.
   CHROMIUM_EXECUTABLE=/path/to/chromium node test_rate_console_browser.cjs */
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const { chromium } = require('playwright');

(async () => {
  // The real HTTP handler and Agent run against a clearly labelled test fixture.
  const server = spawn(process.env.PYTHON || 'python', ['-u', '-c', `
import json, time
from http.server import ThreadingHTTPServer
import serve_rates
from rate_agent import RateStrategyAgent
from rate_parallel import RateParallelAgent
from test_rate_strategy import completed_steepener_history
def fetch(start_date):
    time.sleep(0.7)
    result = completed_steepener_history()
    result.update(provider="TEST FIXTURE", source_freshness="TEST FIXTURE")
    return result
serve_rates.RATE_AGENT = RateStrategyAgent({"fetch_public_rate_history": fetch})
serve_rates.PARALLEL_RATE_AGENT = RateParallelAgent({"fetch_public_rate_history": fetch})
server = ThreadingHTTPServer(("127.0.0.1", 0), serve_rates.RateStrategyHandler)
print(server.server_address[1], flush=True)
server.serve_forever()
`], { cwd: __dirname, stdio: ['ignore', 'pipe', 'pipe'] });
  let browser;
  let logs = '';
  server.stderr.on('data', data => { logs += data; });
  try {
    const port = await new Promise((resolve, reject) => {
      server.stdout.once('data', data => resolve(Number(String(data).trim())));
      server.once('error', reject);
      server.once('exit', code => reject(new Error(`Server exited ${code}: ${logs}`)));
    });
    browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE || undefined, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const url = `http://127.0.0.1:${port}`;
    await page.goto(url);
    assert.equal(await page.locator('.graph-node').count(), 12);
    assert.equal(await page.locator('script').count(), 2);
    await page.locator('#scenario').selectOption('live');
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/rate-console-idle.png`, fullPage: true });
    await page.locator('#run-button').click();
    await page.waitForSelector('[data-node="D1"][data-status="running"]');
    assert.equal(await page.locator('.event-row[data-kind="call"]').count(), 1);
    assert.equal(await page.locator('#run-button').isDisabled(), true);
    await page.waitForSelector('#run-status[data-phase="completed"]');
    assert.equal(await page.locator('.graph-node[data-status="completed"]').count(), 12);
    const eventCount = await page.locator('.event-row').count();
    assert.ok(eventCount > 35);
    assert.match(await page.locator('.event-time').first().innerText(), /^\d{2}:\d{2}:\d{2}\.\d{3}$/);
    assert.match(await page.locator('#source-note').innerText(), /TEST FIXTURE/);
    await page.locator('.graph-node[data-node="D1"]').click();
    assert.equal(await page.locator('.event-row:visible').count(), 6);
    const result = page.locator('.event-row[data-kind="result"][data-node="D1"]');
    await result.locator('summary').click();
    assert.match(await result.locator('pre').innerText(), /observations/);
    assert.match(await result.locator('pre').innerText(), /2026-03-22/);
    await page.locator('#clear-filter').click();
    assert.equal(await page.locator('.event-row:visible').count(), eventCount);
    if (process.env.SCREENSHOT_DIR) {
      await page.locator('#follow').uncheck();
      await page.locator('#stream-scroll').evaluate(el => { el.scrollTop = 0; });
      await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/rate-console-completed.png`, fullPage: true });
    }
    const downloadWait = page.waitForEvent('download');
    await page.locator('#download').click();
    const download = await downloadWait;
    assert.match(download.suggestedFilename(), /^RATE-RUN-.*\.json$/);

    // Observation success is not enough: V1 rejects, P1 replans, then V1 accepts.
    await page.locator('#scenario').selectOption('replan_success');
    await page.locator('#run-button').click();
    await page.waitForSelector('#run-status[data-phase="completed"]');
    const replanKinds = await page.locator('.event-kind').allTextContents();
    assert.ok(replanKinds.includes('GATE REJECT'));
    assert.ok(replanKinds.includes('FEEDBACK ↺'));
    assert.ok(replanKinds.includes('PLAN v1'));
    assert.ok(replanKinds.includes('GATE PASS'));
    assert.equal(await page.locator('.graph-node[data-node="V1"]').getAttribute('data-status'), 'completed');

    // A repeated plan is stopped before D1 can be called a second time.
    await page.locator('#scenario').selectOption('replan_loop');
    await page.locator('#run-button').click();
    await page.waitForSelector('#run-status[data-phase="failed"]');
    assert.equal(await page.locator('.event-row[data-node="D1"][data-kind="call"]').count(), 1);
    assert.ok((await page.locator('.event-kind').allTextContents()).includes('LOOP STOP'));

    // A real strategy validation failure must not erase the successful D1 node.
    await page.locator('#settings summary').click();
    await page.locator('[name="holding_days"]').fill('9999');
    await page.locator('#run-button').click();
    await page.waitForSelector('#run-status[data-phase="failed"]');
    assert.equal(await page.locator('.graph-node[data-node="D1"]').getAttribute('data-status'), 'completed');
    assert.equal(await page.locator('.graph-node[data-node="S1"]').getAttribute('data-status'), 'failed');
    assert.equal(await page.locator('.graph-node[data-node="E1"]').getAttribute('data-status'), 'blocked');
    assert.equal(await page.locator('#run-button').isDisabled(), false);
    await page.locator('#settings summary').click();
    await page.locator('[name="holding_days"]').fill('20');

    // Circuit breaker opens after two failures, waits, probes once, then closes.
    await page.locator('#scenario').selectOption('breaker_recovery');
    await page.locator('#run-button').click();
    await page.waitForSelector('.graph-node[data-node="C1"][data-status="open"]');
    await page.waitForSelector('.graph-node[data-node="C1"][data-status="completed"]');
    await page.waitForSelector('#run-status[data-phase="completed"]');
    assert.ok((await page.locator('.event-kind').allTextContents()).includes('SHORT-CIRCUIT') === false);
    assert.ok((await page.locator('.event-title').allTextContents()).some(text => text.includes('OPEN → HALF_OPEN')));

    // Backpressure keeps the second task out of the Tool until its permit arrives.
    await page.locator('#scenario').selectOption('backpressure');
    await page.locator('#run-button').click();
    await page.waitForSelector('.graph-node[data-node="Q1"][data-status="queued"]');
    await page.waitForSelector('.graph-node[data-node="Q1"][data-status="completed"]');
    await page.waitForSelector('#run-status[data-phase="completed"]');
    const kinds = await page.locator('.event-kind').allTextContents();
    assert.ok(kinds.includes('QUEUED'));
    assert.ok(kinds.includes('DEQUEUED'));

    // A zero-capacity waiting room rejects overload before the Tool call.
    await page.locator('#scenario').selectOption('overload_rejected');
    await page.locator('#run-button').click();
    await page.waitForSelector('.graph-node[data-node="Q1"][data-status="rejected"]');
    await page.waitForSelector('#run-status[data-phase="failed"]');
    assert.equal(await page.locator('.event-row[data-node="A10"][data-kind="call"]').count(), 0);
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/rate-console-failed.png`, fullPage: true });

    // An abruptly closed stream is not a successful run.
    await page.route('**/api/rates/stream', route => route.fulfill({ contentType: 'application/x-ndjson', body: JSON.stringify({ protocol: 'rate-ndjson-v1', type: 'start', run_id: 'TRUNCATED' }) + '\n' }));
    await page.locator('#run-button').click();
    await page.waitForSelector('#run-status[data-phase="failed"]');
    assert.match(await page.locator('#stream-footer').innerText(), /未收到最终结果/);
    await page.unroute('**/api/rates/stream');

    await page.locator('#settings summary').click();
    await page.locator('[name="holding_days"]').fill('20');
    await page.locator('#scenario').selectOption('two_year_slow');
    await page.locator('#run-button').click();
    await page.waitForSelector('.graph-node[data-node="A2"][data-status="running"]');
    await page.waitForSelector('.graph-node[data-node="A10"][data-status="running"]');
    await page.waitForSelector('.graph-node[data-node="A10"][data-status="completed"]');
    assert.equal(await page.locator('.graph-node[data-node="A2"]').getAttribute('data-status'), 'running');
    await page.waitForFunction(() => document.querySelector('[data-node="J1"] .node-status').textContent === '等待 1/2');
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/rate-parallel-waiting.png`, fullPage: true });
    await page.waitForSelector('#run-status[data-phase="completed"]');
    assert.match(await page.locator('#source-note').innerText(), /离线快照/);
    await page.locator('#scenario').selectOption('ten_year_fail');
    await page.locator('#run-button').click();
    await page.waitForSelector('.graph-node[data-node="A10"][data-status="failed"]');
    assert.equal(await page.locator('.graph-node[data-node="A2"]').getAttribute('data-status'), 'running');
    await page.waitForSelector('#run-status[data-phase="failed"]');
    assert.equal(await page.locator('.graph-node[data-node="A2"]').getAttribute('data-status'), 'completed');
    assert.equal(await page.locator('.graph-node[data-node="J1"]').getAttribute('data-status'), 'blocked');

    // Stop does not abort the stream: wait for the actual Tool acknowledgment.
    await page.locator('#scenario').selectOption('manual_cancel');
    await page.locator('#run-button').click();
    await page.waitForSelector('.graph-node[data-node="A2"][data-status="running"]');
    await page.locator('#stop-button').click();
    await page.waitForSelector('#run-status[data-phase="cancelled"]');
    assert.ok((await page.locator('.event-kind').allTextContents()).includes('STOP ACK'));
    assert.equal(await page.locator('.graph-node[data-node="D1"]').getAttribute('data-status'), 'completed');
    assert.equal(await page.locator('.graph-node[data-node="J1"]').getAttribute('data-status'), 'blocked');

    await page.locator('#scenario').selectOption('late_result');
    await page.locator('#run-button').click();
    await page.waitForSelector('#run-status[data-phase="cancelling"]');
    assert.equal(await page.locator('.graph-node[data-node="A2"]').getAttribute('data-status'), 'cancelling');
    assert.equal(await page.locator('#run-button').isDisabled(), true);
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/rate-control-stopping.png`, fullPage: true });
    await page.waitForSelector('#run-status[data-phase="timed_out"]');
    assert.ok((await page.locator('.event-kind').allTextContents()).includes('DISCARDED'));
    assert.equal(await page.locator('.graph-node[data-node="A10"]').getAttribute('data-status'), 'completed');
    assert.equal(await page.locator('.graph-node[data-node="S1"]').getAttribute('data-status'), 'blocked');
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/rate-control-timed-out.png`, fullPage: true });

    await page.locator('#scenario').selectOption('deadline');
    await page.locator('#run-button').click();
    await page.waitForSelector('#run-status[data-phase="timed_out"]');
    assert.equal(await page.locator('#run-button').isDisabled(), false);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(url);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.locator('#scenario').selectOption('two_year_slow');
    await page.locator('#run-button').click();
    await page.waitForSelector('#run-status[data-phase="completed"]');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/rate-console-mobile.png`, fullPage: true });
    assert.deepEqual(errors, []);
    console.log('Browser PASS: Circuit Breaker, backpressure, overload rejection, concurrency, cancellation, full stream, filtering, export and responsive layout. Fixture/snapshot teaching data only.');
  } finally {
    if (browser) await browser.close();
    server.kill();
    if (server.exitCode === null) await once(server, 'exit');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
