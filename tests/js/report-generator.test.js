// Frontend tests for static/js/report-generator.js (run: npm run test:js).
// The script runs inside jsdom with the main.js globals it uses stubbed.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM, VirtualConsole } = require('jsdom');

const SCRIPT = fs.readFileSync(path.join(__dirname, '../../static/js/report-generator.js'), 'utf8');
const LOC = { lat: 12.9716, lng: 77.5946, name: 'MG Road, Bengaluru', type: '' };

function json(status, body) {
    return { ok: status >= 200 && status < 300, status, json: async () => body,
             headers: { get: () => 'attachment; filename="business-report.pdf"' }, blob: async () => new Blob(['%PDF-']) };
}

// jsdom cannot follow the blob: link the download creates; ignore only that notice.
function quietConsole() {
    const vc = new VirtualConsole();
    vc.sendTo(console, { omitJSDOMErrors: true });
    vc.on('jsdomError', e => { if (!/navigation/.test(e.message)) console.error(e); });
    return vc;
}

function setup({ location = LOC, session = { access_token: 'tok' }, heatmapAt = LOC, responses = [] } = {}) {
    const dom = new JSDOM(`<!DOCTYPE html><body>
        <div id="dynamic-map-container"><div id="dashboard-map"></div></div>
        <button id="btn-generate-report" data-report-trigger>Generate Detailed Report</button></body>`,
        { runScripts: 'outside-only', url: 'http://127.0.0.1:8000/dashboard/', virtualConsole: quietConsole() });
    const w = dom.window;
    const calls = [];
    const queue = responses.slice();
    w.fetch = async (url, opts = {}) => {
        calls.push({ url, opts });
        const next = queue.shift();
        if (!next) throw new Error('unexpected fetch ' + url);
        return typeof next === 'function' ? next(url, opts) : next;
    };
    const chat = [];
    const container = w.document.getElementById('dashboard-map');
    container.getBoundingClientRect = () => ({ left: 0, top: 0, width: 800, height: 500 });
    w.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, {
        get: (_t, prop) => prop === 'measureText' ? () => ({ width: 100 }) : () => {},
        set: () => true,
    });
    w.HTMLCanvasElement.prototype.toDataURL = () => 'data:image/jpeg;base64,AAAA';
    w.URL.createObjectURL = () => 'blob:report';
    w.URL.revokeObjectURL = () => {};
    w.L = { TileLayer: function () {} };
    Object.assign(w, {
        getSelectedLocation: () => location,
        getCookie: () => 'csrf123',
        isDashboardPage: () => true,
        addChatMessage: (msg, sender, actions) => chat.push({ msg, actions }),
        updateCrowdIntensityDropdown: async (lat, lon) => {
            w.lastHeatmapAnalysis = { lat, lon, counts: { high: 2, medium: 1, low: 0 }, ts: Date.now() };
        },
        lastHeatmapAnalysis: heatmapAt ? { lat: heatmapAt.lat, lon: heatmapAt.lng, counts: { high: 2, medium: 1, low: 0 } } : null,
        SupabaseAuth: { getSession: async () => session },
        requireSupabaseAuth: (name) => { w.__authGate = name; },
        dashboardMap: {
            getContainer: () => container,
            getBounds: () => ({ contains: () => true }),
            setView: () => {}, invalidateSize: () => {}, getZoom: () => 14,
            getCenter: () => ({ lat: LOC.lat, lng: LOC.lng }),
            eachLayer: () => {},
        },
    });
    w.eval(SCRIPT);
    w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
    return { w, calls, chat };
}

const until = async (cond, ms = 8000) => {
    const t = Date.now();
    while (!cond()) {
        if (Date.now() - t > ms) throw new Error('timed out');
        await new Promise(r => setTimeout(r, 20));
    }
};
const panelText = w => (w.document.getElementById('report-progress-panel') || { textContent: '' }).textContent;
const STAGES = [{ key: 'collect', label: 'Collecting location data', state: 'active' }];

test('recognises the same report requests as the server', () => {
    const { w } = setup();
    const yes = ['Generate a detailed report.', 'Create a PDF for this location.', 'Give me a business feasibility report.',
                 'Generate a comprehensive report with heatmap and revenue analysis.'];
    const no = ['What does the report include?', 'How do I generate a report?', 'show popular places'];
    yes.forEach(m => assert.equal(w.ReportGenerator.looksLikeReportRequest(m), true, m));
    no.forEach(m => assert.equal(w.ReportGenerator.looksLikeReportRequest(m), false, m));
});

test('no location selected: asks for one and sends nothing', async () => {
    const { w, calls } = setup({ location: null });
    w.ReportGenerator.start({ source: 'dashboard' });
    await until(() => panelText(w).includes('Select a location first'));
    assert.equal(calls.length, 0);
});

test('not signed in: opens the auth gate', async () => {
    const { w, calls } = setup({ session: null });
    w.ReportGenerator.start({ source: 'dashboard' });
    await until(() => w.__authGate === 'Detailed Report');
    assert.equal(calls.length, 0);
});

test('successful generation: loading state, capture payload, polling and download', async () => {
    const { w, calls } = setup({ responses: [
        json(202, { report_id: 'abc', stages: STAGES }),
        json(200, { status: 'succeeded', stages: [{ key: 'ready', label: 'Report ready', state: 'done' }], page_count: 21, ai_used: true, location: LOC.name }),
        json(200, {}),
    ] });
    const btn = w.document.getElementById('btn-generate-report');
    btn.click();
    await until(() => btn.disabled === true);                 // loading state
    await until(() => panelText(w).includes('Download PDF'));
    assert.equal(btn.disabled, false);

    const post = calls[0];
    assert.equal(post.url, '/api/reports/generate/');
    assert.equal(post.opts.headers.Authorization, 'Bearer tok');
    assert.equal(post.opts.headers['X-CSRFToken'], 'csrf123');
    const body = JSON.parse(post.opts.body);
    assert.deepEqual(body.location, { name: LOC.name, latitude: LOC.lat, longitude: LOC.lng });
    assert.equal(body.radius_m, 2000);
    assert.match(body.heatmap.image, /^data:image\/jpeg;base64,/);
    assert.equal(body.heatmap.analysed_lat, LOC.lat);
    assert.equal(calls[1].url, '/api/reports/abc/status/');

    const download = [...w.document.querySelectorAll('#report-progress-panel button')].find(b => b.textContent.includes('Download'));
    download.click();
    await until(() => calls.length === 3);
    assert.equal(calls[2].url, '/api/reports/abc/download/');
    assert.equal(calls[2].opts.headers.Authorization, 'Bearer tok');
});

test('stale heatmap for another location is re-analysed before capture', async () => {
    const { w, calls } = setup({ heatmapAt: { lat: 19.07, lng: 72.87 }, responses: [
        json(202, { report_id: 'r1', stages: STAGES }),
        json(200, { status: 'succeeded', stages: [], page_count: 20, location: LOC.name }),
    ] });
    w.ReportGenerator.start({ source: 'dashboard' });
    await until(() => calls.length === 2);
    const body = JSON.parse(calls[0].opts.body);
    assert.equal(body.heatmap.analysed_lat, LOC.lat);
    assert.equal(body.heatmap.analysed_lon, LOC.lng);
});

test('capture failure is reported to the server instead of faking an image', async () => {
    const { w, calls } = setup({ responses: [
        json(202, { report_id: 'r2', stages: STAGES }),
        json(200, { status: 'succeeded', stages: [], page_count: 20, location: LOC.name }),
    ] });
    w.HTMLCanvasElement.prototype.toDataURL = () => { throw new Error('SecurityError'); };
    w.ReportGenerator.start({ source: 'dashboard' });
    await until(() => calls.length === 2);
    const body = JSON.parse(calls[0].opts.body);
    assert.equal(body.heatmap.image, undefined);
    assert.match(body.heatmap.capture_error, /blocked reading the map image/);
});

test('API failure shows the server error', async () => {
    const { w } = setup({ responses: [json(429, { success: false, error: 'Hourly report limit reached.' })] });
    w.ReportGenerator.start({ source: 'dashboard' });
    await until(() => panelText(w).includes('Hourly report limit reached.'));
    assert.equal(w.document.getElementById('btn-generate-report').disabled, false);
});

test('generation failure reported by the status endpoint is shown', async () => {
    const { w, chat } = setup({ responses: [
        json(202, { report_id: 'r3', stages: STAGES }),
        json(200, { status: 'failed', error: 'OpenStreetMap data could not be retrieved', stages: [] }),
    ] });
    w.ReportGenerator.start({ source: 'chat' });
    await until(() => panelText(w).includes('OpenStreetMap data could not be retrieved'));
    assert.ok(chat.some(c => c.msg.includes('could not be generated')));
});

test('duplicate clicks start only one generation', async () => {
    let release;
    const gate = new Promise(r => { release = r; });
    const { w, calls } = setup({ responses: [
        async () => { await gate; return json(202, { report_id: 'r4', stages: STAGES }); },
        json(200, { status: 'succeeded', stages: [], page_count: 20, location: LOC.name }),
    ] });
    w.ReportGenerator.start({ source: 'dashboard' });
    await until(() => calls.length === 1);
    w.ReportGenerator.start({ source: 'dashboard' });
    w.ReportGenerator.start({ source: 'chat' });
    release();
    await until(() => calls.length === 2);
    await new Promise(r => setTimeout(r, 200));
    assert.equal(calls.filter(c => c.url === '/api/reports/generate/').length, 1);
});

test('server says a job is already running: follows that job', async () => {
    const { w, calls } = setup({ responses: [
        json(409, { code: 'busy', report_id: 'existing', error: 'A report is already being generated' }),
        json(200, { status: 'succeeded', stages: [], page_count: 20, location: LOC.name }),
    ] });
    w.ReportGenerator.start({ source: 'dashboard' });
    await until(() => calls.length === 2);
    assert.equal(calls[1].url, '/api/reports/existing/status/');
});
