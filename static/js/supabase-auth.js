/**
 * Supabase Authentication & Project DB Logging Service
 * Handles user authentication state, feature gating, and database activity logging.
 */

(function () {
    'use strict';

    // Global Supabase configuration (fallback to defaults if not set in DOM)
    const SUPABASE_URL = (window.SUPABASE_CONFIG && window.SUPABASE_CONFIG.url) 
        || 'https://ijsfmdgysmwovaighumv.supabase.co';
    const SUPABASE_ANON_KEY = (window.SUPABASE_CONFIG && window.SUPABASE_CONFIG.key) 
        || 'sb_publishable_EdW1JxXZSkEA1uV4Yl4eIg_F9dvq-2h';

    let supabaseClient = null;
    let currentUserSession = null;
    let pendingFeatureCallback = null;
    let pendingFeatureName = null;

    // Initialize Supabase Client
    function initSupabase() {
        if (typeof window.supabase === 'undefined' || !window.supabase.createClient) {
            console.warn('[Supabase] SDK not loaded yet. Waiting...');
            return null;
        }
        if (!supabaseClient) {
            try {
                supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
                    auth: {
                        persistSession: true,
                        autoRefreshToken: true,
                        detectSessionInUrl: true
                    }
                });
                console.log('[Supabase] Initialized client successfully for:', SUPABASE_URL);
            } catch (err) {
                console.error('[Supabase] Initialization error:', err);
            }
        }
        return supabaseClient;
    }

    // Get current session asynchronously
    async function getSession() {
        const client = initSupabase();
        if (!client) return null;
        try {
            const { data, error } = await client.auth.getSession();
            if (error) {
                console.warn('[Supabase] getSession error:', error.message);
                return null;
            }
            currentUserSession = data.session;
            return currentUserSession;
        } catch (e) {
            console.warn('[Supabase] Error retrieving session:', e);
            return null;
        }
    }

    // Check if user is logged in
    function isAuthenticated() {
        return !!(currentUserSession && currentUserSession.user);
    }

    // Record activity in Supabase project database
    async function logSupabaseActivity(eventType, featureName, details) {
        const client = initSupabase();
        const user = currentUserSession ? currentUserSession.user : null;
        const payload = {
            event_type: eventType || 'action',
            feature_name: featureName || '',
            user_id: user ? user.id : null,
            user_email: user ? user.email : 'guest',
            details: details || {},
            timestamp: new Date().toISOString()
        };

        // Cache in local storage for developer inspection / offline fallback
        try {
            const logs = JSON.parse(localStorage.getItem('supabase_activity_logs') || '[]');
            logs.unshift(payload);
            if (logs.length > 50) logs.pop();
            localStorage.setItem('supabase_activity_logs', JSON.stringify(logs));
        } catch (err) {
            // ignore storage quota errors
        }

        // 1. Direct Supabase PostgREST table insert
        if (client) {
            try {
                const { data, error } = await client
                    .from('user_activity_logs')
                    .insert([{
                        event_type: payload.event_type,
                        feature_name: payload.feature_name,
                        user_id: payload.user_id,
                        user_email: payload.user_email,
                        details: payload.details
                    }]);
                if (error) {
                    console.info('[Supabase Log] Note on project table user_activity_logs:', error.message);
                } else {
                    console.log('[Supabase Log] Logged to Supabase DB table successfully:', payload.event_type, featureName);
                }
            } catch (e) {
                console.info('[Supabase Log] Database table insert notice:', e.message || e);
            }
        }

        // 2. Server-side endpoint backup logging
        try {
            fetch('/api/log-activity/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(res => res.json()).then(resp => {
                if (resp && resp.success) {
                    console.log('[Supabase Log] Server confirmed database log record.');
                }
            }).catch(() => {});
        } catch (e) {
            // ignore fetch errors
        }
    }

    // Avatar and initials helper
    function getAvatarHtml(user, sizeClass = '') {
        const meta = (user && user.user_metadata) || {};
        const avatarUrl = meta.avatar_base64 || meta.avatar_url;
        const name = meta.full_name || meta.name || (user && user.email ? user.email.split('@')[0] : 'U');

        if (avatarUrl) {
            return `<img src="${avatarUrl}" alt="${name}" class="${sizeClass}" onerror="this.onerror=null; this.parentElement.innerHTML='${getInitials(name)}';">`;
        }
        return `<span>${getInitials(name)}</span>`;
    }

    function getInitials(name) {
        if (!name) return 'U';
        const parts = name.trim().split(/\s+/);
        if (parts.length >= 2) {
            return (parts[0][0] + parts[1][0]).toUpperCase();
        }
        return (name[0] || 'U').toUpperCase();
    }

    // Update UI elements based on authentication state
    function updateAuthUI(user) {
        const sidebarFooter = document.querySelector('.sidebar-footer');
        const navAuthContainer = document.getElementById('navbar-auth-section');

        if (user) {
            const meta = user.user_metadata || {};
            const displayName = meta.full_name || meta.name || user.email.split('@')[0];
            const avatarHtml = getAvatarHtml(user);

            // Clean up any old stacked buttons from sidebar
            const oldProfileBtn = document.getElementById('sidebar-supabase-profile');
            if (oldProfileBtn) oldProfileBtn.remove();
            const oldLogoutBtn = document.getElementById('sidebar-supabase-logout');
            if (oldLogoutBtn) oldLogoutBtn.remove();
            const oldLoginBtn = document.getElementById('sidebar-supabase-login');
            if (oldLoginBtn) oldLoginBtn.remove();

            // Update sidebar user card placeholders (avatar + name inside existing dropdown)
            const sidebarAvatarHolder = document.getElementById('sidebar-user-avatar-placeholder');
            if (sidebarAvatarHolder) sidebarAvatarHolder.innerHTML = avatarHtml;
            const sidebarNameHolder = document.getElementById('sidebar-user-name-placeholder');
            if (sidebarNameHolder) { sidebarNameHolder.textContent = displayName; sidebarNameHolder.title = user.email; }
            // Wire sidebar dropdown logout
            const sidebarDropLogout = document.getElementById('sidebar-dropdown-logout');
            if (sidebarDropLogout) sidebarDropLogout.addEventListener('click', handleSignOut);

            // Navbar auth dropdown: only name and profile picture visible on trigger!
            if (navAuthContainer) {
                navAuthContainer.innerHTML = `
                    <div class="dropdown nav-user-dropdown" id="nav-user-dropdown-container">
                        <button class="nav-user-btn" type="button" id="navUserMenuBtn" data-bs-toggle="dropdown" data-bs-auto-close="true" aria-expanded="false" title="${displayName} (${user.email})">
                            <div class="nav-user-avatar">
                                ${avatarHtml}
                            </div>
                            <span class="nav-user-name">${displayName}</span>
                            <i class="fas fa-chevron-down nav-user-chevron"></i>
                        </button>
                        <div class="dropdown-menu dropdown-menu-end nav-user-menu" aria-labelledby="navUserMenuBtn">
                            <div class="nav-user-header">
                                <div class="nav-user-header-avatar">
                                    ${avatarHtml}
                                </div>
                                <div class="nav-user-header-info">
                                    <div class="nav-user-header-name">${displayName}</div>
                                    <div class="nav-user-header-email">${user.email}</div>
                                </div>
                            </div>
                            <a class="nav-user-item" href="/profile/">
                                <i class="fas fa-user-circle text-success" style="font-size: 1rem;"></i>
                                <span>Profile Settings</span>
                            </a>
                            <a class="nav-user-item" href="/dashboard/">
                                <i class="fas fa-th-large text-info" style="font-size: 1rem;"></i>
                                <span>Dashboard</span>
                            </a>
                            <a class="nav-user-item" href="/favorites/">
                                <i class="fas fa-heart text-danger" style="font-size: 1rem;"></i>
                                <span>My Favorites</span>
                            </a>
                            <hr class="nav-user-divider">
                            <button class="nav-user-item item-danger" id="nav-supabase-logout" type="button">
                                <i class="fas fa-sign-out-alt" style="font-size: 1rem;"></i>
                                <span>Sign Out</span>
                            </button>
                        </div>
                    </div>
                `;

                const navLogout = document.getElementById('nav-supabase-logout');
                if (navLogout) navLogout.addEventListener('click', handleSignOut);

                // Bootstrap handles open/close via data-bs-toggle="dropdown"
                // Add safety net: close dropdown when clicking outside
                const dropMenu = navAuthContainer.querySelector('.nav-user-menu');
                const menuBtn = document.getElementById('navUserMenuBtn');
                const dropContainer = document.getElementById('nav-user-dropdown-container');
                if (dropMenu && menuBtn) {
                    document.addEventListener('click', function onOutsideClick(e) {
                        if (!navAuthContainer.contains(e.target)) {
                            dropMenu.classList.remove('show');
                            menuBtn.setAttribute('aria-expanded', 'false');
                            if (dropContainer) dropContainer.classList.remove('show');
                        }
                    }, { capture: false });
                }
            }
        } else {
            const oldProfileBtn = document.getElementById('sidebar-supabase-profile');
            if (oldProfileBtn) oldProfileBtn.remove();
            const logoutBtn = document.getElementById('sidebar-supabase-logout');
            if (logoutBtn) logoutBtn.remove();

            const sidebarAvatarHolder = document.getElementById('sidebar-user-avatar-placeholder');
            if (sidebarAvatarHolder) sidebarAvatarHolder.innerHTML = '<i class="fas fa-user" style="color:#94a3b8;"></i>';
            const sidebarNameHolder = document.getElementById('sidebar-user-name-placeholder');
            if (sidebarNameHolder) sidebarNameHolder.textContent = 'Guest User';

            // Replace logout button with Sign In button
            let loginBtn = document.getElementById('sidebar-supabase-login');
            if (!loginBtn && sidebarFooter) {
                loginBtn = document.createElement('a');
                loginBtn.id = 'sidebar-supabase-login';
                loginBtn.href = '/login/?next=/dashboard/';
                loginBtn.className = 'btn btn-sm btn-outline-info w-100 mt-2';
                loginBtn.innerHTML = '<i class="fas fa-sign-in-alt me-1"></i>Sign In with Supabase';
                sidebarFooter.appendChild(loginBtn);
            }

            // Navbar auth status
            if (navAuthContainer) {
                const currentPath = window.location.pathname || '/dashboard/';
                navAuthContainer.innerHTML = `
                    <a href="/login/?next=${encodeURIComponent(currentPath)}" class="btn btn-outline-light btn-sm px-3">
                        <i class="fas fa-sign-in-alt me-1"></i>Sign In
                    </a>
                `;
            }
        }
    }

    // Sign out handler
    async function handleSignOut(e) {
        if (e) e.preventDefault();
        const client = initSupabase();
        if (client) {
            await logSupabaseActivity('auth_logout', 'Dashboard', { action: 'User clicked Sign Out' });
            await client.auth.signOut();
        }
        currentUserSession = null;
        updateAuthUI(null);
        showAuthNotification('Signed out successfully.', 'info');
        setTimeout(() => {
            window.location.href = '/dashboard/';
        }, 500);
    }

    // Gatekeeper function: check if authenticated, otherwise trigger auth gate modal
    function requireSupabaseAuth(featureName, callback) {
        if (isAuthenticated()) {
            logSupabaseActivity('feature_accessed', featureName, { authorized: true });
            if (typeof callback === 'function') {
                callback();
            }
            return true;
        }

        // Unauthenticated: log blocked access & trigger modal
        logSupabaseActivity('feature_access_blocked', featureName, { authorized: false, reason: 'unauthenticated' });
        pendingFeatureCallback = callback;
        pendingFeatureName = featureName;
        openAuthGateModal(featureName);
        return false;
    }

    // Open Auth Gate Modal
    function openAuthGateModal(featureName) {
        const modal = document.getElementById('supabase-auth-gate-modal');
        if (!modal) {
            // If modal doesn't exist, redirect directly to login page
            const nextUrl = encodeURIComponent(window.location.pathname + window.location.search);
            window.location.href = `/login/?feature=${encodeURIComponent(featureName || 'Dashboard Feature')}&next=${nextUrl}`;
            return;
        }

        const featureNameSpan = document.getElementById('auth-gate-feature-name');
        if (featureNameSpan) {
            featureNameSpan.textContent = featureName || 'This Feature';
        }

        const fullLoginBtn = document.getElementById('auth-gate-full-login-btn');
        if (fullLoginBtn) {
            const nextUrl = encodeURIComponent(window.location.pathname + window.location.search);
            fullLoginBtn.href = `/login/?feature=${encodeURIComponent(featureName || '')}&next=${nextUrl}`;
        }

        modal.classList.add('show');
        modal.style.display = 'flex';
        document.body.classList.add('modal-open');
    }

    // Close Auth Gate Modal
    function closeAuthGateModal() {
        const modal = document.getElementById('supabase-auth-gate-modal');
        if (modal) {
            modal.classList.remove('show');
            modal.style.display = 'none';
            document.body.classList.remove('modal-open');
        }
    }

    // Display temporary notification
    function showAuthNotification(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `alert alert-${type === 'error' ? 'danger' : type} position-fixed top-0 end-0 m-4 shadow-lg`;
        toast.style.zIndex = '99999';
        toast.style.minWidth = '280px';
        toast.innerHTML = `<i class="fas fa-${type === 'error' ? 'exclamation-circle' : 'check-circle'} me-2"></i>${message}`;
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.style.transition = 'opacity 0.4s';
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 400);
        }, 3500);
    }

    // Execute pending action after successful authentication
    function executePendingAction() {
        if (typeof pendingFeatureCallback === 'function') {
            const cb = pendingFeatureCallback;
            const feat = pendingFeatureName;
            pendingFeatureCallback = null;
            pendingFeatureName = null;
            closeAuthGateModal();
            showAuthNotification(`Access granted to ${feat || 'feature'}!`, 'success');
            setTimeout(() => {
                cb();
            }, 250);
        } else {
            closeAuthGateModal();
        }
    }

    // Initialize listeners when DOM is loaded
    document.addEventListener('DOMContentLoaded', async () => {
        const client = initSupabase();
        if (!client) {
            console.warn('[Supabase] Supabase SDK not found. Retrying in 500ms...');
            setTimeout(async () => {
                const retryClient = initSupabase();
                if (retryClient) setupAuthListeners(retryClient);
            }, 500);
            return;
        }
        await setupAuthListeners(client);
    });

    async function setupAuthListeners(client) {
        // Fetch current session
        const session = await getSession();
        if (session && session.user) {
            updateAuthUI(session.user);
            console.log('[Supabase Auth] Active user session:', session.user.email);
        } else {
            updateAuthUI(null);
            console.log('[Supabase Auth] Browsing in guest mode.');
        }

        // Listen for authentication changes
        client.auth.onAuthStateChange(async (event, newSession) => {
            console.log('[Supabase Auth] Auth event triggered:', event);
            currentUserSession = newSession;
            if (newSession && newSession.user) {
                updateAuthUI(newSession.user);
                if (event === 'SIGNED_IN') {
                    await logSupabaseActivity('auth_login', 'Supabase Auth', { email: newSession.user.email });
                    executePendingAction();
                }
            } else if (event === 'SIGNED_OUT') {
                updateAuthUI(null);
            }
        });

        // Wire up modal elements
        setupModalListeners();
    }

    function setupModalListeners() {
        const modal = document.getElementById('supabase-auth-gate-modal');
        if (!modal) return;

        // Close button
        const closeBtn = modal.querySelector('.btn-close-modal');
        if (closeBtn) {
            closeBtn.addEventListener('click', closeAuthGateModal);
        }
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeAuthGateModal();
        });

        // Quick Login Form in Modal
        const quickForm = document.getElementById('modal-supabase-login-form');
        const errorAlert = document.getElementById('modal-auth-error');
        const submitBtn = document.getElementById('modal-login-btn');

        if (quickForm) {
            quickForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const email = document.getElementById('modal-auth-email').value.trim();
                const password = document.getElementById('modal-auth-password').value;

                if (!email || !password) {
                    if (errorAlert) {
                        errorAlert.textContent = 'Please provide both email and password.';
                        errorAlert.classList.remove('d-none');
                    }
                    return;
                }

                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Signing In...';
                }
                if (errorAlert) errorAlert.classList.add('d-none');

                const client = initSupabase();
                if (!client) {
                    if (errorAlert) {
                        errorAlert.textContent = 'Supabase client could not connect.';
                        errorAlert.classList.remove('d-none');
                    }
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = '<i class="fas fa-sign-in-alt me-2"></i>Sign In';
                    }
                    return;
                }

                try {
                    const { data, error } = await client.auth.signInWithPassword({ email, password });
                    if (error) {
                        if (errorAlert) {
                            errorAlert.textContent = error.message || 'Invalid login credentials.';
                            errorAlert.classList.remove('d-none');
                        }
                    } else {
                        currentUserSession = data.session;
                        updateAuthUI(data.user);
                        await logSupabaseActivity('auth_login', pendingFeatureName || 'Modal Quick Login', { email: data.user.email });
                        executePendingAction();
                    }
                } catch (err) {
                    if (errorAlert) {
                        errorAlert.textContent = err.message || 'Login failed. Please try again.';
                        errorAlert.classList.remove('d-none');
                    }
                } finally {
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = '<i class="fas fa-sign-in-alt me-2"></i>Sign In';
                    }
                }
            });
        }
    }

    // Export functions to global window namespace
    window.SupabaseAuth = {
        init: initSupabase,
        getSession: getSession,
        isAuthenticated: isAuthenticated,
        requireAuth: requireSupabaseAuth,
        logActivity: logSupabaseActivity,
        signOut: handleSignOut,
        openModal: openAuthGateModal,
        closeModal: closeAuthGateModal,
        showNotification: showAuthNotification,
        updateUI: updateAuthUI
    };

    // Global alias for compatibility
    window.requireSupabaseAuth = requireSupabaseAuth;
    window.logSupabaseActivity = logSupabaseActivity;

})();
