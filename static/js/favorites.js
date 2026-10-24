/**
 * Favorites: save places to the signed-in Supabase account, and the /favorites/ page.
 *
 * Auth model: the Supabase session lives in the browser, so every API call
 * sends the access token as a Bearer header and the server verifies it.
 * Hearts rendered on cards are plain <button class="fav-btn" data-fav="<b64 payload>">
 * handled by one delegated listener, so they work on dynamically rendered cards.
 */
(function () {
    'use strict';

    const saved = new Map(); // place_key -> favorite id
    let loaded = false;

    // ---- helpers -----------------------------------------------------------
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
        (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const enc = (obj) => btoa(unescape(encodeURIComponent(JSON.stringify(obj))));
    const dec = (b64) => JSON.parse(decodeURIComponent(escape(atob(b64))));
    const toast = (msg, type) => window.SupabaseAuth && window.SupabaseAuth.showNotification(msg, type || 'info');

    // Must match favorites/keys.py make_place_key().
    function placeKey(p) {
        if (p.place_key) return p.place_key;
        if (p.osm_type && p.osm_id) return `osm:${p.osm_type}:${p.osm_id}`;
        const slug = String(p.name || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);
        const raw = `geo:${Number(p.latitude).toFixed(4)}:${Number(p.longitude).toFixed(4)}:${slug}`;
        return raw; // server hashes keys over 120 chars; those only occur for pathological names
    }

    /** Convert an Overpass element (as returned by /find-popular-places/) into a favorite payload. */
    function fromOverpass(el) {
        const t = el.tags || {};
        const c = el.center || {};
        const lat = el.lat != null ? el.lat : c.lat;
        const lon = el.lon != null ? el.lon : c.lon;
        const addr = [t['addr:street'], t['addr:city']].filter(Boolean).join(', ');
        return {
            osm_type: el.type || '', osm_id: el.id || '',
            name: t.name || t.amenity || t.shop || t.tourism || 'Place',
            category: t.amenity || t.shop || t.tourism || '',
            latitude: lat, longitude: lon, address: addr,
            potential_score: el.revenue_data ? el.revenue_data.potential_score : null,
        };
    }

    function heartHtml(payload) {
        if (payload.latitude == null || payload.longitude == null) return '';
        const key = placeKey(payload);
        const on = saved.has(key);
        return `<button type="button" class="fav-btn${on ? ' active' : ''}" data-key="${esc(key)}"
                    data-fav="${enc(payload)}" aria-pressed="${on}" title="${on ? 'Remove from favorites' : 'Save to favorites'}">
                    <i class="${on ? 'fas' : 'far'} fa-heart"></i></button>`;
    }

    function paint(root) {
        (root || document).querySelectorAll('.fav-btn').forEach((btn) => {
            const on = saved.has(btn.dataset.key);
            btn.classList.toggle('active', on);
            btn.setAttribute('aria-pressed', on);
            btn.title = on ? 'Remove from favorites' : 'Save to favorites';
            const i = btn.querySelector('i');
            if (i) i.className = (on ? 'fas' : 'far') + ' fa-heart';
        });
    }

    // ---- API ---------------------------------------------------------------
    async function api(path, opts) {
        const session = window.SupabaseAuth ? await window.SupabaseAuth.getSession() : null;
        if (!session) throw Object.assign(new Error('Sign in required'), { status: 401 });
        const resp = await fetch(path, Object.assign({}, opts, {
            headers: Object.assign({
                'Authorization': 'Bearer ' + session.access_token,
                'Content-Type': 'application/json',
            }, (opts && opts.headers) || {}),
        }));
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data.success === false) {
            throw Object.assign(new Error(data.error || 'Request failed'), { status: resp.status });
        }
        return data;
    }

    async function load() {
        const data = await api('/api/favorites/');
        saved.clear();
        data.favorites.forEach((f) => saved.set(f.place_key, f.id));
        loaded = true;
        paint();
        return data.favorites;
    }

    /** Called after cards render: mark already-saved hearts (silently no-op when signed out). */
    async function refresh() {
        try {
            if (!loaded) await load(); else paint();
        } catch (e) { /* signed out or offline: hearts just stay empty */ }
    }

    async function toggle(payload) {
        const data = await api('/api/favorites/toggle/', { method: 'POST', body: JSON.stringify(payload) });
        if (data.favorited) saved.set(data.place_key, data.favorite.id); else saved.delete(data.place_key);
        paint();
        return data;
    }

    // ---- heart clicks (all pages) -------------------------------------------
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.fav-btn');
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation(); // capture phase (see below) so the card's inline onclick never fires
        let payload;
        try { payload = dec(btn.dataset.fav); } catch (err) { return; }
        const run = async () => {
            btn.disabled = true;
            try {
                const res = await toggle(payload);
                toast(res.favorited ? 'Saved to your favorites' : 'Removed from favorites', 'success');
                document.dispatchEvent(new CustomEvent('favorites:changed'));
            } catch (err) {
                toast(err.message, 'error');
            } finally { btn.disabled = false; }
        };
        if (window.SupabaseAuth) window.SupabaseAuth.requireAuth('Favorites', run); else run();
    }, true); // capture: cards have inline onclick handlers that would otherwise run first

    window.Favorites = { heartHtml, fromOverpass, refresh, load, toggle, placeKey };

    // ---- /favorites/ page ---------------------------------------------------
    const page = document.getElementById('favorites-page');
    if (!page) return;

    const $ = (id) => document.getElementById(id);
    let all = [];
    let activeCategory = '';
    let userPos = null;

    const osmLink = (p) => `https://www.openstreetmap.org/?mlat=${p.latitude}&mlon=${p.longitude}#map=17/${p.latitude}/${p.longitude}`;
    const label = (c) => esc((c || 'place').replace(/_/g, ' '));

    function favCard(f) {
        return `<article class="fav-card">
            <div class="fav-card-top">
                <span class="fav-cat">${label(f.category)}</span>
                ${f.potential_score != null ? `<span class="fav-score">${f.potential_score}/100</span>` : ''}
            </div>
            <h3>${esc(f.name)}</h3>
            <p class="fav-addr">${esc(f.address || `${f.latitude.toFixed(4)}, ${f.longitude.toFixed(4)}`)}</p>
            <div class="fav-actions">
                <a href="${osmLink(f)}" target="_blank" rel="noopener noreferrer"><i class="fas fa-map-location-dot"></i> Map</a>
                <button type="button" class="fav-remove" data-id="${f.id}"><i class="fas fa-trash"></i> Remove</button>
            </div>
        </article>`;
    }

    function recCard(r) {
        const payload = { place_key: r.place_key, name: r.name, category: r.category, latitude: r.latitude,
                          longitude: r.longitude, address: r.address, potential_score: r.potential_score };
        return `<article class="fav-card rec">
            <div class="fav-card-top"><span class="fav-cat">${label(r.category)}</span>${heartHtml(payload)}</div>
            <h3>${esc(r.name)}</h3>
            <ul class="fav-reasons">${r.reasons.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
            <div class="fav-actions"><a href="${osmLink(r)}" target="_blank" rel="noopener noreferrer"><i class="fas fa-map-location-dot"></i> Map</a></div>
        </article>`;
    }

    function renderFavorites() {
        const cats = [...new Set(all.map((f) => f.category).filter(Boolean))].sort();
        $('fav-chips').innerHTML = cats.length > 1
            ? ['', ...cats].map((c) => `<button type="button" class="fav-chip${c === activeCategory ? ' on' : ''}" data-cat="${esc(c)}">${c ? label(c) : 'All'}</button>`).join('')
            : '';
        const shown = activeCategory ? all.filter((f) => f.category === activeCategory) : all;
        $('fav-count').textContent = all.length;
        $('fav-list').innerHTML = shown.length ? shown.map(favCard).join('')
            : `<div class="fav-empty"><i class="far fa-heart"></i><p>${all.length ? 'Nothing in this category.' : 'No favorites yet. Tap the heart on any place in the Popular Places results to save it here.'}</p>
               <a class="btn btn-primary-blue btn-sm" href="/dashboard/">Explore places</a></div>`;
    }

    async function renderRecommendations() {
        const qs = userPos ? `?lat=${userPos.lat}&lon=${userPos.lon}` : '';
        const box = $('rec-list');
        try {
            const data = await api('/api/favorites/recommendations/' + qs);
            $('rec-sub').textContent = data.personalized
                ? 'Ranked by what others save, your taste, and distance.'
                : 'Trending with other users. Save a few places to personalise this.';
            box.innerHTML = data.recommendations.length ? data.recommendations.map(recCard).join('')
                : '<div class="fav-empty"><p>No community picks yet. Be the first to save places!</p></div>';
            paint(box);
        } catch (e) {
            box.innerHTML = `<div class="fav-empty"><p>${esc(e.message)}</p></div>`;
        }
    }

    function reportCard(r) {
        const dateStr = r.created_at || 'Recently';
        const pagesStr = r.page_count ? `${r.page_count} pages` : 'Ready';
        const isReady = r.status === 'succeeded' && r.has_pdf;
        return `<article class="fav-card">
            <div class="fav-card-top">
                <span class="fav-cat text-primary"><i class="fas fa-file-pdf me-1"></i>Report</span>
                <span class="badge ${isReady ? 'bg-success-subtle text-success' : 'bg-warning-subtle text-warning'} border font-monospace" style="font-size:0.7rem;">${isReady ? pagesStr : r.status}</span>
            </div>
            <h3>${esc(r.location_name)}</h3>
            <p class="fav-addr"><i class="fas fa-clock me-1 opacity-75"></i>${esc(dateStr)}</p>
            <div class="fav-actions mt-auto pt-2">
                ${isReady ? `<button type="button" class="btn btn-primary-blue btn-sm w-100 download-report-btn" data-id="${r.id}"><i class="fas fa-download me-1"></i>Download PDF</button>` : `<span class="text-muted small">${esc(r.status)}</span>`}
            </div>
        </article>`;
    }

    async function renderReports() {
        const box = $('reports-list');
        if (!box) return;
        try {
            const data = await api('/api/reports/');
            const reports = Array.isArray(data.reports) ? data.reports : [];
            const countEl = $('reports-count');
            if (countEl) countEl.textContent = reports.length;
            box.innerHTML = reports.length ? reports.map(reportCard).join('')
                : `<div class="fav-empty"><i class="far fa-file-pdf"></i><p>No reports generated yet. Click "Full Detailed Report" on the map or Popular Places to create and store one here.</p>
                   <a class="btn btn-primary-blue btn-sm" href="/dashboard/?auto_map=true">Generate on Map</a></div>`;
        } catch (e) {
            box.innerHTML = `<div class="fav-empty"><p>${esc(e.message)}</p></div>`;
        }
    }

    async function downloadReportPdf(reportId) {
        const session = window.SupabaseAuth ? await window.SupabaseAuth.getSession() : null;
        if (!session) { toast('Please sign in to download reports', 'error'); return; }
        try {
            const res = await fetch(`/api/reports/${reportId}/download/`, {
                headers: { 'Authorization': 'Bearer ' + session.access_token }
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                toast(data.error || 'Download failed', 'error');
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
        } catch (err) {
            toast(err.message, 'error');
        }
    }

    async function downloadFavoritesReportPdf() {
        const session = window.SupabaseAuth ? await window.SupabaseAuth.getSession() : null;
        if (!session) { toast('Please sign in to download favorites report', 'error'); return; }
        const btn = $('btn-download-favs-report');
        if (btn) btn.disabled = true;
        try {
            const res = await fetch('/api/favorites/report/', {
                headers: { 'Authorization': 'Bearer ' + session.access_token }
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                toast(data.error || 'Export failed', 'error');
                return;
            }
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'favorites-summary-report.pdf';
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 30000);
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async function init() {
        const session = window.SupabaseAuth ? await window.SupabaseAuth.getSession() : null;
        if (!session) {
            $('fav-gate').classList.remove('d-none');
            $('fav-content').classList.add('d-none');
            return;
        }
        $('fav-gate').classList.add('d-none');
        $('fav-content').classList.remove('d-none');
        try { all = await load(); } catch (e) { toast(e.message, 'error'); }
        renderFavorites();
        await renderReports();
        await renderRecommendations();
        if (navigator.geolocation) { // refine picks around the user's current position, if they allow it
            navigator.geolocation.getCurrentPosition((pos) => {
                userPos = { lat: pos.coords.latitude, lon: pos.coords.longitude };
                renderRecommendations();
            }, () => {}, { timeout: 5000, maximumAge: 600000 });
        }
    }

    page.addEventListener('click', async (e) => {
        const chip = e.target.closest('.fav-chip');
        if (chip) { activeCategory = chip.dataset.cat; renderFavorites(); return; }
        const rm = e.target.closest('.fav-remove');
        if (rm) {
            rm.disabled = true;
            try {
                await api(`/api/favorites/${rm.dataset.id}/`, { method: 'DELETE' });
                all = await load();
                if (activeCategory && !all.some((f) => f.category === activeCategory)) activeCategory = '';
                renderFavorites();
                renderRecommendations();
            } catch (err) { toast(err.message, 'error'); rm.disabled = false; }
            return;
        }
        const repBtn = e.target.closest('.download-report-btn');
        if (repBtn) {
            downloadReportPdf(repBtn.dataset.id);
            return;
        }
        const favRepBtn = e.target.closest('#btn-download-favs-report');
        if (favRepBtn) {
            downloadFavoritesReportPdf();
            return;
        }
    });

    // A heart on a recommendation was toggled -> refresh the saved list and re-rank.
    document.addEventListener('favorites:changed', async () => {
        all = await load().catch(() => all);
        renderFavorites();
        renderRecommendations();
    });

    // supabase-auth.js sets up its session on DOMContentLoaded; wait for it.
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init, 0));
    else init();
})();
