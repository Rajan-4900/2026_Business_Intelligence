/**
 * AI-Powered Business Intelligence Report Generator (frontend).
 *
 * One flow serves the dashboard button and the chatbot:
 *   1. resolve the selected location (localStorage 'selectedLocation')
 *   2. make sure the live heatmap on the dashboard map belongs to that location
 *   3. capture the map (tiles + heatmap overlays + markers) onto a canvas
 *   4. POST /api/reports/generate/ (Supabase bearer token + CSRF)
 *   5. poll /api/reports/<id>/status/ and show the server's real stages
 *   6. download the PDF with the same bearer token
 *
 * Depends on globals from main.js: getSelectedLocation, getCookie, map,
 * dashboardMap, updateCrowdIntensityDropdown, isDashboardPage, addChatMessage.
 */
(function () {
    'use strict';

    // Keep in sync with report_generator/intent.py (the server decides; this only
    // stops main.js's map-command parser from acting on report requests).
    const REQUEST_RE = /\b(generate|create|make|build|prepare|produce|export|download|give\s+me|get\s+me|send\s+me|i\s+(?:want|need|would\s+like))\b[\s\S]{0,80}?\b(report|pdf)\b/i;
    const QUESTION_RE = /^\s*(how|what|why|when|where|which|explain|tell\s+me\s+about)\b/i;

    const MAX_CAPTURE_OFFSET_M = 30;   // same tolerance as report_generator/validators.py
    const MAX_IMAGE_CHARS = 2.6e6;     // stays under Django's 2.5 MB request body default
    const POLL_MS = 1500;
    const POLL_TIMEOUT_MS = 6 * 60 * 1000;

    let inFlight = false;
    let panel = null;

    function looksLikeReportRequest(text) {
        const t = String(text || '').trim();
        return !!t && t.length <= 500 && !QUESTION_RE.test(t) && REQUEST_RE.test(t);
    }

    function distanceM(lat1, lon1, lat2, lon2) {
        const R = 6371000, toRad = Math.PI / 180;
        const dLat = (lat2 - lat1) * toRad, dLon = (lon2 - lon1) * toRad;
        const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2;
        return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

    // ---------------------------------------------------------------- UI ----

    function ensurePanel() {
        if (panel) return panel;
        panel = document.createElement('div');
        panel.id = 'report-progress-panel';
        panel.className = 'report-progress-panel d-none';
        panel.setAttribute('role', 'status');
        panel.setAttribute('aria-live', 'polite');
        panel.innerHTML = `
            <div class="report-progress-head">
                <span><i class="fas fa-file-pdf me-2"></i>Detailed report</span>
                <button type="button" class="report-progress-close" aria-label="Close">&times;</button>
            </div>
            <div class="report-progress-location"></div>
            <ol class="report-progress-stages"></ol>
            <div class="report-progress-message"></div>
            <div class="report-progress-actions"></div>`;
        document.body.appendChild(panel);
        panel.querySelector('.report-progress-close').addEventListener('click', () => {
            panel.classList.add('d-none');
        });
        return panel;
    }

    function showPanel(locationName) {
        const p = ensurePanel();
        p.classList.remove('d-none');
        p.querySelector('.report-progress-location').textContent = locationName || '';
        p.querySelector('.report-progress-message').textContent = '';
        p.querySelector('.report-progress-message').className = 'report-progress-message';
        p.querySelector('.report-progress-actions').innerHTML = '';
        renderStages([{ key: 'capture', label: 'Capturing the heatmap', state: 'active' }]);
    }

    function renderStages(stages) {
        const list = ensurePanel().querySelector('.report-progress-stages');
        list.innerHTML = '';
        stages.forEach(st => {
            const li = document.createElement('li');
            li.className = 'stage-' + st.state;
            const icon = { done: 'fa-check-circle', active: 'fa-spinner fa-spin', failed: 'fa-times-circle',
                           skipped: 'fa-minus-circle', pending: 'fa-circle' }[st.state] || 'fa-circle';
            li.innerHTML = `<i class="fas ${icon}"></i> `;
            li.appendChild(document.createTextNode(st.label + (st.state === 'skipped' ? ' (not available)' : '')));
            list.appendChild(li);
        });
    }

    function setMessage(text, kind) {
        const el = ensurePanel().querySelector('.report-progress-message');
        el.textContent = text;
        el.className = 'report-progress-message ' + (kind || '');
    }

    function setButtonBusy(busy) {
        document.querySelectorAll('[data-report-trigger]').forEach(btn => {
            btn.disabled = busy;
            btn.setAttribute('aria-busy', busy ? 'true' : 'false');
        });
    }

    function chat(text, actions) {
        if (typeof addChatMessage === 'function') addChatMessage(text, 'bot', actions);
    }

    // -------------------------------------------------------------- auth ----

    async function authHeaders() {
        const session = window.SupabaseAuth ? await window.SupabaseAuth.getSession() : null;
        if (!session || !session.access_token) return null;
        return {
            'Authorization': 'Bearer ' + session.access_token,
            'X-CSRFToken': typeof getCookie === 'function' ? (getCookie('csrftoken') || '') : '',
        };
    }

    // ------------------------------------------------------- map / state ----

    function activeMap() {
        if (typeof dashboardMap !== 'undefined' && dashboardMap) return dashboardMap;
        if (typeof map !== 'undefined' && map && typeof map.getContainer === 'function') return map;
        return null;
    }

    function openDashboardMap() {
        const container = document.getElementById('dynamic-map-container');
        if (container && container.classList.contains('d-none')) {
            const btn = document.getElementById('btn-show-map');
            if (btn) btn.click();
        }
    }

    function heatmapMatches(loc) {
        const h = window.lastHeatmapAnalysis;
        return !!(h && distanceM(h.lat, h.lon, loc.lat, loc.lng) <= MAX_CAPTURE_OFFSET_M);
    }

    async function ensureHeatmapFor(loc) {
        openDashboardMap();
        await sleep(300);
        const m = activeMap();
        if (!m) throw new Error('The dashboard map is not available on this page.');
        if (!heatmapMatches(loc)) {
            if (typeof updateCrowdIntensityDropdown !== 'function') {
                throw new Error('The heatmap for the selected location has not been analysed yet.');
            }
            setMessage('Running the heatmap for the selected location…');
            await updateCrowdIntensityDropdown(loc.lat, loc.lng);
            if (!heatmapMatches(loc)) throw new Error('The heatmap analysis for the selected location did not complete.');
        }
        // Keep the user's zoom; only pan if the location is outside the visible map.
        if (!m.getBounds().contains([loc.lat, loc.lng])) {
            m.setView([loc.lat, loc.lng], m.getZoom(), { animate: false });
        }
        m.invalidateSize();
        return m;
    }

    function waitForTiles(m, timeoutMs) {
        const layers = [];
        m.eachLayer(l => { if (l instanceof L.TileLayer) layers.push(l); });
        const pending = layers.filter(l => typeof l.isLoading === 'function' && l.isLoading());
        if (!pending.length) return sleep(250);
        return Promise.race([
            Promise.all(pending.map(l => new Promise(res => l.once('load', res)))),
            sleep(timeoutMs),
        ]).then(() => sleep(250));
    }

    // ------------------------------------------------------------ capture ----

    function loadImage(src, crossOrigin) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            if (crossOrigin) img.crossOrigin = 'anonymous';
            const timer = setTimeout(() => reject(new Error('timeout')), 6000);
            img.onload = () => { clearTimeout(timer); resolve(img); };
            img.onerror = () => { clearTimeout(timer); reject(new Error('load failed')); };
            img.src = src;
        });
    }

    // Draw a DOM <img> without tainting the canvas: re-request it with CORS
    // unless it was already loaded that way (dashboard tiles use crossOrigin).
    async function corsCopy(img) {
        if (img.crossOrigin === 'anonymous' && img.complete && img.naturalWidth) return img;
        if (img.src.startsWith('data:')) return img;
        const sep = img.src.includes('?') ? '&' : '?';
        return loadImage(img.src + sep + 'rgcors=1', true);
    }

    async function captureMap(m) {
        const container = m.getContainer();
        const box = container.getBoundingClientRect();
        if (box.width < 300 || box.height < 200) throw new Error('The map is too small or hidden to capture.');
        const scale = Math.min(window.devicePixelRatio || 1, 1600 / box.width, 2);
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(box.width * scale);
        canvas.height = Math.round(box.height * scale);
        const ctx = canvas.getContext('2d');
        ctx.scale(scale, scale);
        ctx.fillStyle = '#e5e7eb';
        ctx.fillRect(0, 0, box.width, box.height);

        const at = el => {
            const r = el.getBoundingClientRect();
            return { x: r.left - box.left, y: r.top - box.top, w: r.width, h: r.height };
        };
        let skipped = 0;

        // 1. Base map tiles
        const tiles = container.querySelectorAll('.leaflet-tile-pane img.leaflet-tile-loaded');
        for (const tile of tiles) {
            const r = at(tile);
            if (r.x > box.width || r.y > box.height || r.x + r.w < 0 || r.y + r.h < 0) continue;
            try {
                ctx.drawImage(await corsCopy(tile), r.x, r.y, r.w, r.h);
            } catch (_e) { skipped += 1; }
        }
        if (tiles.length && skipped === tiles.length) throw new Error('The map tiles could not be read (cross-origin restriction).');

        // 2. Vector overlays (heatmap circles, radius ring, route) drawn by Leaflet's SVG renderer
        for (const svg of container.querySelectorAll('.leaflet-overlay-pane svg')) {
            const r = at(svg);
            const clone = svg.cloneNode(true);
            clone.removeAttribute('style');
            clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
            clone.setAttribute('width', r.w);
            clone.setAttribute('height', r.h);
            const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(clone));
            try { ctx.drawImage(await loadImage(url, false), r.x, r.y, r.w, r.h); } catch (_e) { skipped += 1; }
        }
        for (const cv of container.querySelectorAll('.leaflet-overlay-pane canvas')) {
            const r = at(cv);
            try { ctx.drawImage(cv, r.x, r.y, r.w, r.h); } catch (_e) { skipped += 1; }
        }

        // 3. Marker shadows and icons
        for (const img of container.querySelectorAll('.leaflet-shadow-pane img, .leaflet-marker-pane img')) {
            const r = at(img);
            try { ctx.drawImage(await corsCopy(img), r.x, r.y, r.w, r.h); } catch (_e) { skipped += 1; }
        }

        // 4. Legend and attribution, as on the website
        ctx.font = '12px sans-serif';
        const legend = [['#ff0000', 'High'], ['#ffaa00', 'Medium'], ['#00cc00', 'Low']];
        ctx.fillStyle = 'rgba(255,255,255,0.9)';
        ctx.fillRect(8, box.height - 30, 210, 22);
        legend.forEach(([color, label], i) => {
            ctx.fillStyle = color;
            ctx.beginPath(); ctx.arc(20 + i * 70, box.height - 19, 5, 0, 2 * Math.PI); ctx.fill();
            ctx.fillStyle = '#111827'; ctx.fillText(label, 29 + i * 70, box.height - 15);
        });
        const attribution = '© MapTiler © OpenStreetMap contributors';
        const aw = ctx.measureText(attribution).width + 10;
        ctx.fillStyle = 'rgba(255,255,255,0.85)';
        ctx.fillRect(box.width - aw - 4, box.height - 20, aw, 16);
        ctx.fillStyle = '#374151';
        ctx.fillText(attribution, box.width - aw + 1, box.height - 8);

        let dataUrl;
        try {
            dataUrl = canvas.toDataURL('image/jpeg', 0.88);
            if (dataUrl.length > MAX_IMAGE_CHARS) dataUrl = canvas.toDataURL('image/jpeg', 0.7);
        } catch (_e) {
            throw new Error('The browser blocked reading the map image (cross-origin restriction).');
        }
        if (dataUrl.length > MAX_IMAGE_CHARS) throw new Error('The map screenshot is too large to upload.');
        return { dataUrl, skipped };
    }

    // --------------------------------------------------------- generation ----

    async function postGenerate(headers, body) {
        const res = await fetch('/api/reports/generate/', {
            method: 'POST',
            headers: Object.assign({ 'Content-Type': 'application/json' }, headers),
            body: JSON.stringify(body),
        });
        let data = {};
        try { data = await res.json(); } catch (_e) { /* non-JSON error page */ }
        return { res, data };
    }

    async function poll(headers, reportId) {
        const started = Date.now();
        while (Date.now() - started < POLL_TIMEOUT_MS) {
            const res = await fetch(`/api/reports/${reportId}/status/`, { headers });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.error || `Status check failed (${res.status}).`);
            renderStages(data.stages || []);
            if (data.status === 'succeeded') return data;
            if (data.status === 'failed') throw new Error(data.error || 'Report generation failed.');
            await sleep(POLL_MS);
        }
        throw new Error('The report is taking longer than expected. Please try again later.');
    }

    async function download(reportId) {
        const headers = await authHeaders();
        if (!headers) { setMessage('Please sign in again to download the report.', 'error'); return; }
        const res = await fetch(`/api/reports/${reportId}/download/`, { headers });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            setMessage(data.error || `Download failed (${res.status}).`, 'error');
            return;
        }
        const blob = await res.blob();
        const disposition = res.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="([^"]+)"/);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = match ? match[1] : 'business-report.pdf';
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 30000);
    }

    function showDownload(reportId, info) {
        const actions = ensurePanel().querySelector('.report-progress-actions');
        actions.innerHTML = '';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-primary-blue btn-sm';
        btn.innerHTML = '<i class="fas fa-download me-2"></i>Download PDF';
        btn.addEventListener('click', () => download(reportId));
        actions.appendChild(btn);
        const pages = info && info.page_count ? `${info.page_count} pages. ` : '';
        setMessage(`${pages}${info && info.ai_used ? '' : 'AI commentary was unavailable; template explanations were used. '}Available for 24 hours.`, 'success');
    }

    async function run(source) {
        let loc = typeof getSelectedLocation === 'function' ? getSelectedLocation() : null;
        if (!loc && typeof userMarker !== 'undefined' && userMarker && typeof userMarker.getLatLng === 'function') {
            const pt = userMarker.getLatLng();
            loc = { lat: pt.lat, lng: pt.lng, name: 'Current Location' };
        } else if (!loc && window.lastHeatmapAnalysis) {
            loc = { lat: window.lastHeatmapAnalysis.lat, lng: window.lastHeatmapAnalysis.lon, name: 'Scanned Location' };
        }
        if (!loc) {
            const msg = 'Select a location first: search for a place or click the map.';
            if (source === 'chat') chat('📍 ' + msg);
            ensurePanel(); showPanel(''); setMessage(msg, 'error');
            renderStages([]);
            return;
        }
        if (typeof isDashboardPage === 'function' && !isDashboardPage()) {
            chat('📄 Reports are generated from the dashboard map, where the heatmap can be captured. Open the dashboard, select the location, then ask again.',
                 [{ intent: 'open_dashboard', label: '📈 Open Dashboard' }]);
            return;
        }
        const headers = await authHeaders();
        if (!headers) {
            if (window.requireSupabaseAuth) window.requireSupabaseAuth('Detailed Report', () => start({ source }));
            return;
        }

        inFlight = true;
        setButtonBusy(true);
        showPanel(loc.name || `${Number(loc.lat).toFixed(4)}, ${Number(loc.lng).toFixed(4)}`);

        try {
            const lat = Number(loc.lat), lng = Number(loc.lng);
            const heatmap = {};
            try {
                const m = await ensureHeatmapFor({ lat, lng });
                await waitForTiles(m, 8000);
                setMessage('Capturing the heatmap…');
                const shot = await captureMap(m);
                const h = window.lastHeatmapAnalysis;
                const centre = m.getCenter();
                Object.assign(heatmap, {
                    image: shot.dataUrl,
                    analysed_lat: h.lat, analysed_lon: h.lon,
                    center_lat: centre.lat, center_lon: centre.lng, zoom: m.getZoom(),
                    sector_counts: h.counts, captured_at: Date.now(),
                });
            } catch (err) {
                // Generate anyway: the server reconstructs the sectors and the PDF
                // states clearly that the screenshot is missing and why.
                heatmap.capture_error = String(err && err.message || err).slice(0, 200);
                setMessage('Heatmap capture failed: ' + heatmap.capture_error + ' The report will say so.', 'warning');
            }

            const body = {
                location: { name: loc.name || '', latitude: lat, longitude: lng },
                radius_m: 2000,
                business_type: loc.type || '',
                scope: 'full',
                source: source,
                heatmap: heatmap,
            };
            let { res, data } = await postGenerate(headers, body);
            if (res.status === 409 && data.code === 'busy' && data.report_id) {
                setMessage('A report is already being generated; showing its progress.');
            } else if (res.status === 409 && data.code === 'heatmap_mismatch') {
                // The map changed under us: retry once without the screenshot.
                delete body.heatmap.image;
                body.heatmap = { capture_error: 'the map on screen no longer matched the selected location' };
                ({ res, data } = await postGenerate(headers, body));
            }
            if (!(res.status === 202 || (res.status === 409 && data.report_id))) {
                if (res.status === 403) throw new Error('Security check failed. Reload the page and try again.');
                throw new Error(data.error || `Report request failed (${res.status}).`);
            }
            const reportId = data.report_id;
            if (data.stages) renderStages(data.stages);
            const done = await poll(headers, reportId);
            showDownload(reportId, done);
            if (source === 'chat') {
                chat(`✅ Your report for **${done.location}** is ready (${done.page_count} pages).`,
                     [{ intent: 'download_report', report_id: reportId, label: '⬇️ Download PDF' }]);
            }
        } catch (err) {
            const msg = String(err && err.message || err);
            setMessage(msg, 'error');
            if (source === 'chat') chat('⚠️ The report could not be generated: ' + msg);
        } finally {
            inFlight = false;
            setButtonBusy(false);
        }
    }

    function start(options) {
        if (inFlight) {
            ensurePanel().classList.remove('d-none');
            return;
        }
        run((options && options.source) || 'dashboard');
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('[data-report-trigger]').forEach(btn => {
            btn.addEventListener('click', e => { e.preventDefault(); start({ source: 'dashboard' }); });
        });
    });

    window.ReportGenerator = { start, download, looksLikeReportRequest, captureMap };
})();
