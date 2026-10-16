/**
 * Zipaworld Rate Radar - Frontend Application
 * High-performance, API-driven freight rate & coverage intelligence dashboard.
 */

(function () {
  'use strict';

  // ── Global Application State ───────────────────────────────────────────────
  const state = {
    currentView: 'overview',
    config: {},
    syncState: {},
    settings: {
      radar_expiry_threshold: 14,
      radar_min_carriers: 2,
      radar_timezone: 'Asia/Kolkata',
      admin_token: localStorage.getItem('radar_admin_token') || '',
    },
    ratesQuery: {
      search: '',
      direction: '',
      mode: '',
      dest_region: '',
      dest_country: '',
      carrier: '',
      status: '',
      end_date_from: '',
      end_date_to: '',
      sort_by: 'validity_end_date',
      sort_order: 'asc',
      page: 1,
      page_size: 50,
    },
    countriesRef: [],
    syncCooldownTimer: null,
    cooldownSecondsRemaining: 0,
    selectedRate: null,
  };

  // ── API Service Helper ─────────────────────────────────────────────────────
  async function apiFetch(endpoint, options = {}) {
    const headers = options.headers || {};
    if (state.settings.admin_token) {
      headers['X-Admin-Token'] = state.settings.admin_token;
    }
    options.headers = headers;

    try {
      const res = await fetch(`/api${endpoint}`, options);
      if (!res.ok) {
        let errDetail = res.statusText;
        try {
          const errData = await res.json();
          errDetail = errData.detail || errData.message || res.statusText;
        } catch (_) {}
        throw new Error(errDetail);
      }
      return await res.json();
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  }

  // ── Toast Notification System ──────────────────────────────────────────────
  function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(20px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // ── Escape String Helper ───────────────────────────────────────────────────
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Flag Emoji Helper ──────────────────────────────────────────────────────
  function getFlagEmoji(iso2) {
    if (!iso2 || typeof iso2 !== 'string' || iso2.length !== 2) return '🌐';
    const codePoints = iso2
      .toUpperCase()
      .split('')
      .map(char => 127397 + char.charCodeAt(0));
    return String.fromCodePoint(...codePoints);
  }

  // ── Relative Time Formatter ────────────────────────────────────────────────
  function formatSyncTime(isoString) {
    if (!isoString) return 'Never';
    try {
      const date = new Date(isoString);
      if (isNaN(date.getTime())) return isoString;
      const now = new Date();
      const diffSecs = Math.floor((now - date) / 1000);
      if (diffSecs < 10) return 'Just now';
      if (diffSecs < 60) return `${diffSecs}s ago`;
      const diffMins = Math.floor(diffSecs / 60);
      if (diffMins < 60) return `${diffMins}m ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (_) {
      return isoString;
    }
  }

  // ── Navigation Manager ─────────────────────────────────────────────────────
  function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
      item.addEventListener('click', () => {
        const view = item.getAttribute('data-view');
        switchView(view);
      });
    });

    const menuToggle = document.getElementById('menu-toggle');
    const sidebar = document.getElementById('sidebar');
    if (menuToggle && sidebar) {
      menuToggle.addEventListener('click', () => {
        sidebar.classList.toggle('mobile-open');
      });
    }

    // Direct links from overview buttons
    const btnViewAllExpiries = document.getElementById('btn-view-all-expiries');
    if (btnViewAllExpiries) {
      btnViewAllExpiries.addEventListener('click', () => {
        state.ratesQuery.status = 'EXPIRING SOON';
        document.getElementById('filter-status').value = 'EXPIRING SOON';
        switchView('rates');
      });
    }

    const btnViewCoverageTab = document.getElementById('btn-view-coverage-tab');
    if (btnViewCoverageTab) {
      btnViewCoverageTab.addEventListener('click', () => switchView('countries'));
    }

    const kpiCardCountries = document.getElementById('kpi-card-countries');
    if (kpiCardCountries) {
      kpiCardCountries.addEventListener('click', () => switchView('countries'));
    }

    const kpiCardAlerts = document.getElementById('kpi-card-alerts');
    if (kpiCardAlerts) {
      kpiCardAlerts.addEventListener('click', () => switchView('alerts'));
    }

    // Clicking KPI cards to filter rates
    document.querySelectorAll('.clickable-kpi').forEach(card => {
      card.addEventListener('click', () => {
        const statusFilter = card.getAttribute('data-filter-status');
        state.ratesQuery.status = statusFilter;
        state.ratesQuery.page = 1;
        document.getElementById('filter-status').value = statusFilter;
        switchView('rates');
      });
    });

    // Hash change routing
    window.addEventListener('hashchange', () => {
      const hash = window.location.hash.replace('#', '');
      if (hash && document.getElementById(`view-${hash}`)) {
        switchView(hash, false);
      }
    });

    const initialHash = window.location.hash.replace('#', '');
    if (initialHash && document.getElementById(`view-${initialHash}`)) {
      switchView(initialHash, false);
    }
  }

  function switchView(viewName, updateHash = true) {
    state.currentView = viewName;
    document.querySelectorAll('.nav-item').forEach(item => {
      if (item.getAttribute('data-view') === viewName) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });

    document.querySelectorAll('.view-panel').forEach(panel => {
      panel.classList.remove('active');
    });

    const targetPanel = document.getElementById(`view-${viewName}`);
    if (targetPanel) {
      targetPanel.classList.add('active');
    }

    if (updateHash) {
      window.location.hash = viewName;
    }

    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.remove('mobile-open');

    // Trigger view-specific data refresh
    loadViewData(viewName);
  }

  function loadViewData(viewName) {
    switch (viewName) {
      case 'overview':
        loadOverview();
        break;
      case 'alerts':
        loadAlerts();
        break;
      case 'rates':
        loadRates();
        break;
      case 'countries':
        loadCountryCoverage();
        break;
      case 'ports':
        loadPortCoverage();
        break;
      case 'india':
        loadIndiaCoverage();
        break;
      case 'history':
        loadHistory();
        break;
      case 'settings':
        loadSettingsView();
        break;
    }
  }

  // ── Bootstrap & Initial Config ─────────────────────────────────────────────
  async function initApp() {
    try {
      setupNavigation();
      setupDrawer();
      setupRatesFilters();
      setupSettingsHandlers();
      setupWatchlistControls();
      setupManualSync();

      // Fetch system config
      const cfg = await apiFetch('/config');
      state.config = cfg;
      state.settings.radar_expiry_threshold = cfg.radar_expiry_threshold || 14;
      state.settings.radar_min_carriers = cfg.radar_min_carriers || 2;
      state.settings.radar_timezone = cfg.radar_timezone || 'Asia/Kolkata';

      // Update UI displays
      document.getElementById('sidebar-tz').textContent = state.settings.radar_timezone;
      document.getElementById('topbar-threshold').value = state.settings.radar_expiry_threshold;
      document.getElementById('topbar-threshold-val').textContent = `${state.settings.radar_expiry_threshold}d`;
      document.getElementById('topbar-min-carriers').value = state.settings.radar_min_carriers;
      document.getElementById('country-min-label').textContent = state.settings.radar_min_carriers;

      // Check mode for DEMO badge
      if (cfg.is_demo) {
        document.getElementById('sidebar-demo-badge').style.display = 'block';
        const honestyBanner = document.getElementById('honesty-banner');
        honestyBanner.style.display = 'flex';
        honestyBanner.className = 'banner-notice banner-demo';
        document.getElementById('banner-title').textContent = 'DEMO MODE ACTIVE:';
        document.getElementById('banner-desc').textContent =
          'Showing synthetic freight rates with simulated validity dates and coverage depths. No live API credentials are used.';
      } else if (!cfg.api_configured) {
        const honestyBanner = document.getElementById('honesty-banner');
        honestyBanner.style.display = 'flex';
        honestyBanner.className = 'banner-notice banner-danger';
        document.getElementById('banner-title').textContent = 'API NOT CONFIGURED:';
        const missing = cfg.missing_settings ? cfg.missing_settings.join(', ') : 'Required parameters missing';
        document.getElementById('banner-desc').textContent =
          `Live rate synchronization is disabled because settings are missing: [ ${missing} ]. Configure environment variables to connect.`;
      }

      // Load reference countries
      loadCountriesReference();

      // Initial overview load
      await loadOverview();
      await updateSyncStatusHeader();

      // Poll sync status & overview every 45s
      setInterval(() => {
        updateSyncStatusHeader();
        if (state.currentView === 'overview') loadOverview(false);
      }, 45000);

    } catch (err) {
      console.error('Initialization error:', err);
      showToast('Error connecting to backend services: ' + err.message, 'error');
    }
  }

  // ── Sync Status & Header Update ───────────────────────────────────────────
  async function updateSyncStatusHeader() {
    try {
      const statusData = await apiFetch('/sync/status');
      const connChip = document.getElementById('conn-chip');
      const topSyncTime = document.getElementById('top-sync-time');

      const stateName = statusData.state.state;
      state.syncState = statusData.state;

      // Connection chip badge
      if (state.config.is_demo) {
        connChip.className = 'status-chip chip-demo';
        connChip.textContent = 'DEMO';
      } else if (stateName === 'live') {
        connChip.className = 'status-chip chip-live';
        connChip.textContent = 'LIVE';
      } else if (stateName === 'stale') {
        connChip.className = 'status-chip chip-stale';
        connChip.textContent = 'STALE';
      } else if (stateName === 'not_configured') {
        connChip.className = 'status-chip chip-not-configured';
        connChip.textContent = 'NOT CONFIGURED';
      } else {
        connChip.className = 'status-chip chip-no-data';
        connChip.textContent = 'NO DATA';
      }

      // Last sync timestamp
      const lastOk = statusData.lastSuccessfulSync;
      topSyncTime.textContent = `Last sync: ${formatSyncTime(lastOk)}`;

    } catch (_) {}
  }

  // ── Manual Sync Action ────────────────────────────────────────────────────
  function setupManualSync() {
    const btnSyncNow = document.getElementById('btn-sync-now');
    const btnManualSyncLarge = document.getElementById('btn-manual-sync-large');

    async function triggerSync() {
      if (state.cooldownSecondsRemaining > 0) {
        showToast(`Sync rate-limited. Please wait ${state.cooldownSecondsRemaining}s.`, 'info');
        return;
      }

      const syncText = document.getElementById('btn-sync-text');
      const manualStatus = document.getElementById('manual-sync-status');
      btnSyncNow.disabled = true;
      if (btnManualSyncLarge) btnManualSyncLarge.disabled = true;
      syncText.textContent = 'Syncing...';
      if (manualStatus) manualStatus.textContent = 'Synchronizing with Zipaworld API...';

      try {
        const result = await apiFetch('/sync/now', { method: 'POST' });
        showToast(`Sync completed! ${result.records_fetched || 0} rates synchronized.`, 'success');
        startSyncCooldown(30);
        updateSyncStatusHeader();
        loadViewData(state.currentView);
      } catch (err) {
        showToast('Sync failed: ' + err.message, 'error');
        startSyncCooldown(10);
      } finally {
        syncText.textContent = 'Sync Now';
        btnSyncNow.disabled = false;
        if (btnManualSyncLarge) btnManualSyncLarge.disabled = false;
        if (manualStatus) manualStatus.textContent = '';
      }
    }

    if (btnSyncNow) btnSyncNow.addEventListener('click', triggerSync);
    if (btnManualSyncLarge) btnManualSyncLarge.addEventListener('click', triggerSync);
  }

  function startSyncCooldown(seconds) {
    state.cooldownSecondsRemaining = seconds;
    clearInterval(state.syncCooldownTimer);

    const btnSyncNow = document.getElementById('btn-sync-now');
    const syncText = document.getElementById('btn-sync-text');

    state.syncCooldownTimer = setInterval(() => {
      state.cooldownSecondsRemaining--;
      if (state.cooldownSecondsRemaining <= 0) {
        clearInterval(state.syncCooldownTimer);
        btnSyncNow.disabled = false;
        syncText.textContent = 'Sync Now';
      } else {
        btnSyncNow.disabled = true;
        syncText.textContent = `Wait (${state.cooldownSecondsRemaining}s)`;
      }
    }, 1000);
  }

  // ── View 1: Overview ──────────────────────────────────────────────────────
  async function loadOverview(showLoading = true) {
    try {
      const data = await apiFetch('/overview');

      // KPIs
      document.getElementById('kpi-total-rates').textContent = data.total_rates.toLocaleString();
      document.getElementById('kpi-total-lanes').textContent = `${data.total_lanes.toLocaleString()} unique corridors`;
      document.getElementById('kpi-active').textContent = data.active.toLocaleString();
      document.getElementById('kpi-expiring').textContent = data.expiring_soon.toLocaleString();
      document.getElementById('kpi-expired').textContent = data.expired.toLocaleString();
      document.getElementById('kpi-starts-later').textContent = data.starts_later.toLocaleString();
      document.getElementById('kpi-needs-review').textContent = data.needs_review.toLocaleString();
      document.getElementById('kpi-countries-covered').textContent = data.countries_covered.toLocaleString();
      document.getElementById('kpi-coverage-alerts').textContent = data.coverage_alerts.toLocaleString();

      // Alert badge in sidebar
      const alertTotal = (data.expiring_soon || 0) + (data.expired || 0) + (data.coverage_alerts || 0);
      const navAlertBadge = document.getElementById('nav-alert-count');
      if (navAlertBadge) {
        navAlertBadge.textContent = alertTotal;
        navAlertBadge.style.display = alertTotal > 0 ? 'inline-block' : 'none';
      }

      // Threshold labels in subheadings
      document.querySelectorAll('.threshold-display').forEach(el => {
        el.textContent = state.settings.radar_expiry_threshold;
      });

      // Distribution Bar calculations
      const total = data.total_rates || 1;
      const pctActive = Math.round((data.active / total) * 100);
      const pctExpiring = Math.round((data.expiring_soon / total) * 100);
      const pctExpired = Math.round((data.expired / total) * 100);
      const pctLater = Math.round((data.starts_later / total) * 100);
      const pctReview = Math.round((data.needs_review / total) * 100);

      document.getElementById('dist-bar-active').style.width = `${pctActive}%`;
      document.getElementById('dist-bar-expiring').style.width = `${pctExpiring}%`;
      document.getElementById('dist-bar-expired').style.width = `${pctExpired}%`;
      document.getElementById('dist-bar-later').style.width = `${pctLater}%`;
      document.getElementById('dist-bar-review').style.width = `${pctReview}%`;

      document.getElementById('pct-active').textContent = `${pctActive}%`;
      document.getElementById('pct-expiring').textContent = `${pctExpiring}%`;
      document.getElementById('pct-expired').textContent = `${pctExpired}%`;
      document.getElementById('pct-later').textContent = `${pctLater}%`;
      document.getElementById('pct-review').textContent = `${pctReview}%`;
      document.getElementById('distribution-total-label').textContent = `${data.total_rates.toLocaleString()} rates analyzed`;

      // Next Expiries Table
      const expBody = document.getElementById('overview-expiries-body');
      if (data.next_expiries && data.next_expiries.length > 0) {
        expBody.innerHTML = data.next_expiries.map(r => `
          <tr onclick="window.rateRadar.openRateDrawer('${escapeHtml(r.id)}')">
            <td>
              <div class="font-semibold">${getFlagEmoji(r.origin_iso2)} ${escapeHtml(r.origin_port_name || r.origin_code)} &rarr; ${getFlagEmoji(r.destination_iso2)} ${escapeHtml(r.destination_port_name || r.destination_code)}</div>
              <div class="text-xs text-dim font-mono">${escapeHtml(r.origin_code)} &rarr; ${escapeHtml(r.destination_code)}</div>
            </td>
            <td><span class="font-semibold text-main">${escapeHtml(r.carrier_brand || 'Unknown')}</span></td>
            <td><span class="font-mono text-blue font-semibold">${escapeHtml(r.currency || '')} ${r.rate ? Number(r.rate).toLocaleString() : '-'}</span></td>
            <td>
              <span class="badge ${getStatusBadgeClass(r.expiry?.status)}">${escapeHtml(r.expiry?.status || '')}</span>
              <div class="text-xs text-dim mt-1">${escapeHtml(r.expiry?.expiry_label || '')}</div>
            </td>
          </tr>
        `).join('');
      } else {
        expBody.innerHTML = `<tr><td colspan="4" class="text-center text-dim py-4">No impending expiries detected</td></tr>`;
      }

      // Needs Attention Panel
      const attList = document.getElementById('overview-attention-list');
      if (data.needs_attention && data.needs_attention.length > 0) {
        attList.innerHTML = data.needs_attention.map(item => `
          <div class="alert-item-card">
            <div>
              <div class="font-semibold text-main">${escapeHtml(item.title)}</div>
              <div class="text-xs text-dim mt-1">${escapeHtml(item.description)}</div>
            </div>
            <button class="btn btn-secondary btn-xs" onclick="window.rateRadar.handleAttentionClick('${item.type}', '${item.code}')">
              Inspect &rarr;
            </button>
          </div>
        `).join('');
      } else {
        attList.innerHTML = `<div class="text-center text-green text-sm py-4">✓ All watched corridors meet target carrier depth!</div>`;
      }

    } catch (err) {
      console.error('Error loading overview:', err);
    }
  }

  // ── View 2: Expiry Alerts & Action Center ──────────────────────────────────
  async function loadAlerts() {
    try {
      const data = await apiFetch('/alerts');

      // 1. Critical Coverage Gaps
      const gapsEl = document.getElementById('alerts-coverage-gaps');
      const gapBadge = document.getElementById('badge-gap-count');
      const gaps = data.critical_coverage_gaps || [];
      gapBadge.textContent = gaps.length;
      if (gaps.length > 0) {
        gapsEl.innerHTML = gaps.map(g => `
          <div class="alert-item-card">
            <div>
              <div class="flex-align-center gap-2">
                <span class="badge badge-purple">${escapeHtml(g.status)}</span>
                <span class="font-bold text-main">${escapeHtml(g.title)}</span>
              </div>
              <div class="text-xs text-dim mt-1">${escapeHtml(g.reason)}</div>
            </div>
            <div class="flex-align-center gap-2">
              <span class="alert-directive-badge">${escapeHtml(g.action)}</span>
              <button class="btn btn-secondary btn-xs" onclick="window.rateRadar.switchView('${g.scope === 'country' ? 'countries' : 'ports'}')">View Grid &rarr;</button>
            </div>
          </div>
        `).join('');
      } else {
        gapsEl.innerHTML = `<div class="text-dim text-sm py-2">No critical carrier-depth gaps on monitored lanes.</div>`;
      }

      // 2. Expired Rates
      renderAlertGroup('alerts-expired-rates', 'badge-expired-count', data.expired || [], 'Renew Contract');

      // 3. 1-3 Days
      renderAlertGroup('alerts-3d-rates', 'badge-expiring-3d-count', data.expiring_3d || [], 'Urgent Rollover');

      // 4. 4-7 Days
      renderAlertGroup('alerts-7d-rates', 'badge-expiring-7d-count', data.expiring_7d || [], 'Review Quotation');

      // 5. 8-14 Days
      renderAlertGroup('alerts-14d-rates', 'badge-expiring-14d-count', data.expiring_14d || [], 'Standard Monitor');

      // 6. Needs Review
      renderAlertGroup('alerts-review-rates', 'badge-review-count', data.needs_review || [], 'Fix In Zipaworld');

    } catch (err) {
      console.error('Error loading alerts:', err);
    }
  }

  function renderAlertGroup(containerId, badgeId, items, defaultAction) {
    const container = document.getElementById(containerId);
    const badge = document.getElementById(badgeId);
    if (!container || !badge) return;

    badge.textContent = items.length;
    if (items.length > 0) {
      container.innerHTML = items.map(r => `
        <div class="alert-item-card" onclick="window.rateRadar.openRateDrawer('${escapeHtml(r.id)}')">
          <div>
            <div class="flex-align-center gap-2">
              <span class="font-bold text-main">${getFlagEmoji(r.origin_iso2)} ${escapeHtml(r.origin_port_name || r.origin_code)} &rarr; ${getFlagEmoji(r.destination_iso2)} ${escapeHtml(r.destination_port_name || r.destination_code)}</span>
              <span class="badge badge-direction">${escapeHtml(r.direction || 'Rate')}</span>
              <span class="font-mono text-xs text-dim">#${escapeHtml(r.id)}</span>
            </div>
            <div class="text-xs text-dim mt-1">
              Carrier: <strong class="text-main">${escapeHtml(r.carrier_brand || 'Unknown')}</strong> &bull;
              Rate: <strong class="text-blue">${escapeHtml(r.currency || '')} ${r.rate ? Number(r.rate).toLocaleString() : '-'}</strong> &bull;
              Window: <span class="font-mono">${escapeHtml(r.validity_start_date || 'N/A')} to ${escapeHtml(r.validity_end_date || 'N/A')}</span>
            </div>
          </div>
          <div class="flex-align-center gap-2">
            <span class="badge ${getStatusBadgeClass(r.expiry?.status)}">${escapeHtml(r.expiry?.expiry_label || r.expiry?.status || '')}</span>
            <span class="alert-directive-badge">${defaultAction}</span>
          </div>
        </div>
      `).join('');
    } else {
      container.innerHTML = `<div class="text-dim text-sm py-2">No rates in this category.</div>`;
    }
  }

  // ── View 3: All Rates Master Table ─────────────────────────────────────────
  async function loadRates() {
    const tableBody = document.getElementById('rates-table-body');
    const countLabel = document.getElementById('rates-count-label');
    const paginationSummary = document.getElementById('pagination-summary');
    const pageIndicator = document.getElementById('page-indicator');
    const btnPrev = document.getElementById('btn-page-prev');
    const btnNext = document.getElementById('btn-page-next');

    tableBody.innerHTML = `<tr><td colspan="8" class="text-center text-dim py-6">Searching rates...</td></tr>`;

    const q = state.ratesQuery;
    const params = new URLSearchParams({
      search: q.search,
      direction: q.direction,
      mode: q.mode,
      dest_region: q.dest_region,
      dest_country: q.dest_country,
      carrier: q.carrier,
      status: q.status,
      end_date_from: q.end_date_from,
      end_date_to: q.end_date_to,
      sort_by: q.sort_by,
      sort_order: q.sort_order,
      page: q.page,
      page_size: q.page_size,
    });

    try {
      const data = await apiFetch(`/rates?${params.toString()}`);
      countLabel.textContent = `(${data.total.toLocaleString()} found)`;
      paginationSummary.textContent = `Page ${data.page} of ${data.pages} (${data.total} items)`;
      pageIndicator.textContent = `Page ${data.page} of ${data.pages}`;

      btnPrev.disabled = data.page <= 1;
      btnNext.disabled = data.page >= data.pages;

      if (!data.items || data.items.length === 0) {
        tableBody.innerHTML = `
          <tr>
            <td colspan="8" class="text-center text-dim py-8">
              <div class="text-base font-semibold text-main mb-1">No matching rates found</div>
              <div class="text-xs">Try adjusting or clearing your search filters.</div>
            </td>
          </tr>
        `;
        return;
      }

      tableBody.innerHTML = data.items.map(r => `
        <tr onclick="window.rateRadar.openRateDrawer('${escapeHtml(r.id)}')">
          <td class="font-mono font-semibold text-xs text-dim">${escapeHtml(r.id)}</td>
          <td>
            <div class="flex-align-center gap-2">
              <span class="font-semibold text-main">${getFlagEmoji(r.origin_iso2)} ${escapeHtml(r.origin_port_name || r.origin_code)} &rarr; ${getFlagEmoji(r.destination_iso2)} ${escapeHtml(r.destination_port_name || r.destination_code)}</span>
              <span class="badge badge-direction">${escapeHtml(r.direction || '')}</span>
            </div>
            <div class="font-mono text-xs text-dim">${escapeHtml(r.origin_code)} &rarr; ${escapeHtml(r.destination_code)}</div>
          </td>
          <td>
            <div class="font-semibold">${escapeHtml(r.shipment_mode || 'FCL')}</div>
            <div class="text-xs text-dim">${escapeHtml(r.container_name || '')}</div>
          </td>
          <td><span class="font-semibold text-main">${escapeHtml(r.carrier_brand || 'Unknown')}</span></td>
          <td>
            <span class="font-mono font-bold text-blue">${escapeHtml(r.currency || '')} ${r.rate ? Number(r.rate).toLocaleString() : '-'}</span>
          </td>
          <td>
            <div class="font-mono text-xs">${escapeHtml(r.validity_start_date || 'N/A')} &rarr; ${escapeHtml(r.validity_end_date || 'N/A')}</div>
          </td>
          <td>
            <span class="badge ${getStatusBadgeClass(r.expiry?.status)}">${escapeHtml(r.expiry?.status || '')}</span>
            <div class="text-xs text-dim mt-1">${escapeHtml(r.expiry?.expiry_label || '')}</div>
          </td>
          <td class="text-xs text-dim font-mono">${formatSyncTime(r.synced_at)}</td>
        </tr>
      `).join('');

    } catch (err) {
      tableBody.innerHTML = `<tr><td colspan="8" class="text-center text-red py-6">Failed to load rates: ${escapeHtml(err.message)}</td></tr>`;
    }
  }

  function setupRatesFilters() {
    const searchInput = document.getElementById('filter-search');
    let debounceTimer = null;
    searchInput.addEventListener('input', e => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        state.ratesQuery.search = e.target.value.trim();
        state.ratesQuery.page = 1;
        loadRates();
      }, 300);
    });

    document.getElementById('filter-direction').addEventListener('change', e => {
      state.ratesQuery.direction = e.target.value;
      state.ratesQuery.page = 1;
      loadRates();
    });

    document.getElementById('filter-mode').addEventListener('change', e => {
      state.ratesQuery.mode = e.target.value;
      state.ratesQuery.page = 1;
      loadRates();
    });

    document.getElementById('filter-region').addEventListener('change', e => {
      state.ratesQuery.dest_region = e.target.value;
      state.ratesQuery.page = 1;
      filterCountryDropdownByRegion(e.target.value);
      loadRates();
    });

    document.getElementById('filter-country').addEventListener('change', e => {
      state.ratesQuery.dest_country = e.target.value;
      state.ratesQuery.page = 1;
      loadRates();
    });

    document.getElementById('filter-carrier').addEventListener('change', e => {
      state.ratesQuery.carrier = e.target.value;
      state.ratesQuery.page = 1;
      loadRates();
    });

    document.getElementById('filter-status').addEventListener('change', e => {
      state.ratesQuery.status = e.target.value;
      state.ratesQuery.page = 1;
      loadRates();
    });

    document.getElementById('filter-end-from').addEventListener('change', e => {
      state.ratesQuery.end_date_from = e.target.value;
      state.ratesQuery.page = 1;
      loadRates();
    });

    document.getElementById('filter-end-to').addEventListener('change', e => {
      state.ratesQuery.end_date_to = e.target.value;
      state.ratesQuery.page = 1;
      loadRates();
    });

    document.getElementById('filter-sort').addEventListener('change', e => {
      const [col, ord] = e.target.value.split(':');
      state.ratesQuery.sort_by = col;
      state.ratesQuery.sort_order = ord;
      loadRates();
    });

    document.getElementById('btn-reset-filters').addEventListener('click', () => {
      state.ratesQuery = {
        search: '',
        direction: '',
        mode: '',
        dest_region: '',
        dest_country: '',
        carrier: '',
        status: '',
        end_date_from: '',
        end_date_to: '',
        sort_by: 'validity_end_date',
        sort_order: 'asc',
        page: 1,
        page_size: 50,
      };

      document.getElementById('filter-search').value = '';
      document.getElementById('filter-direction').value = '';
      document.getElementById('filter-mode').value = '';
      document.getElementById('filter-region').value = '';
      document.getElementById('filter-country').value = '';
      document.getElementById('filter-carrier').value = '';
      document.getElementById('filter-status').value = '';
      document.getElementById('filter-end-from').value = '';
      document.getElementById('filter-end-to').value = '';
      document.getElementById('filter-sort').value = 'validity_end_date:asc';
      populateCountryDropdown(state.countriesRef);
      loadRates();
    });

    // Pagination buttons
    document.getElementById('btn-page-prev').addEventListener('click', () => {
      if (state.ratesQuery.page > 1) {
        state.ratesQuery.page--;
        loadRates();
      }
    });

    document.getElementById('btn-page-next').addEventListener('click', () => {
      state.ratesQuery.page++;
      loadRates();
    });

    document.getElementById('rates-page-size').addEventListener('change', e => {
      state.ratesQuery.page_size = parseInt(e.target.value, 10);
      state.ratesQuery.page = 1;
      loadRates();
    });

    // CSV Exports
    const exportHandler = () => {
      const q = state.ratesQuery;
      const params = new URLSearchParams({
        search: q.search,
        direction: q.direction,
        mode: q.mode,
        dest_region: q.dest_region,
        dest_country: q.dest_country,
        carrier: q.carrier,
        status: q.status,
        end_date_from: q.end_date_from,
        end_date_to: q.end_date_to,
      });
      window.location.href = `/api/export/csv?${params.toString()}`;
    };

    const btnExportRates = document.getElementById('btn-export-rates-csv');
    if (btnExportRates) btnExportRates.addEventListener('click', exportHandler);

    const btnExportOverview = document.getElementById('btn-export-overview-rates');
    if (btnExportOverview) btnExportOverview.addEventListener('click', exportHandler);
  }

  // ── View 4: Country Coverage ──────────────────────────────────────────────
  async function loadCountryCoverage() {
    const grid = document.getElementById('country-cards-grid');
    const note = document.getElementById('country-summary-note');
    grid.innerHTML = `<div class="text-center text-dim py-6">Analyzing destination country coverage...</div>`;

    try {
      const data = await apiFetch('/coverage/countries');
      const items = data.items || [];
      const gaps = data.summary?.gaps || 0;
      const thin = data.summary?.thin || 0;

      if (gaps > 0 || thin > 0) {
        note.innerHTML = `⚠️ <strong>Attention Required:</strong> ${gaps} watched destination countries have no active rates found, and ${thin} countries are below target carrier depth (${data.min_carriers_threshold || 2}).`;
      } else {
        note.innerHTML = `✓ <strong>Optimal Network Health:</strong> All watched destination countries currently meet target carrier depth of ${data.min_carriers_threshold || 2} or more valid carriers.`;
      }

      if (items.length === 0) {
        grid.innerHTML = `<div class="text-center text-dim py-6">No countries on watchlist. Add one above.</div>`;
        return;
      }

      grid.innerHTML = items.map(c => `
        <div class="coverage-card">
          <div class="cov-card-header">
            <div class="cov-identity">
              <span class="cov-flag">${getFlagEmoji(c.country_code)}</span>
              <div>
                <div class="cov-title">${escapeHtml(c.country_name)}</div>
                <div class="cov-code font-mono">${escapeHtml(c.country_code)} &bull; ${escapeHtml(c.region || 'Other')}</div>
              </div>
            </div>
            <span class="badge ${getCoverageBadgeClass(c.status)}">${escapeHtml(c.status)}</span>
          </div>

          <div class="cov-metrics">
            <span>Valid Depth: <strong class="text-main">${c.valid_carriers} / ${data.min_carriers_threshold} carriers</strong></span>
            <span>${c.nearest_expiry_days !== null ? `Nearest expiry: <strong class="text-amber">${c.nearest_expiry_days}d</strong>` : 'No valid rates'}</span>
          </div>

          <div class="carrier-chips-container">
            ${renderCarrierChips(c.carriers)}
          </div>

          <div class="cov-actions">
            <button class="btn btn-ghost btn-xs text-blue" onclick="window.rateRadar.filterRatesByCountry('${escapeHtml(c.country_code)}')">View Rates &rarr;</button>
            <button class="btn btn-danger-ghost btn-xs" onclick="window.rateRadar.removeWatchedCountry('${escapeHtml(c.country_code)}')">Remove</button>
          </div>
        </div>
      `).join('');

    } catch (err) {
      grid.innerHTML = `<div class="text-red py-4">Error loading country coverage: ${escapeHtml(err.message)}</div>`;
    }
  }

  // ── View 5: Port Coverage ─────────────────────────────────────────────────
  async function loadPortCoverage() {
    const grid = document.getElementById('port-cards-grid');
    const note = document.getElementById('port-summary-note');
    grid.innerHTML = `<div class="text-center text-dim py-6">Analyzing port carrier depths...</div>`;

    try {
      const data = await apiFetch('/coverage/ports');
      const items = data.items || [];
      const gaps = data.summary?.gaps || 0;
      const thin = data.summary?.thin || 0;

      if (gaps > 0 || thin > 0) {
        note.innerHTML = `⚠️ <strong>Attention Required:</strong> ${gaps} watched gateway ports have no active rates found, and ${thin} ports are below target carrier depth.`;
      } else {
        note.innerHTML = `✓ <strong>All Watched Ports Covered:</strong> All monitored international ports meet or exceed required carrier redundancy.`;
      }

      if (items.length === 0) {
        grid.innerHTML = `<div class="text-center text-dim py-6">No ports on watchlist. Add one above.</div>`;
        return;
      }

      grid.innerHTML = items.map(p => `
        <div class="coverage-card">
          <div class="cov-card-header">
            <div class="cov-identity">
              <span class="cov-flag">${getFlagEmoji(p.port_code ? p.port_code.substring(0, 2) : '')}</span>
              <div>
                <div class="cov-title">${escapeHtml(p.port_name || p.port_code)}</div>
                <div class="cov-code font-mono">${escapeHtml(p.port_code)}</div>
              </div>
            </div>
            <span class="badge ${getCoverageBadgeClass(p.status)}">${escapeHtml(p.status)}</span>
          </div>

          <div class="cov-metrics">
            <span>Valid Depth: <strong class="text-main">${p.valid_carriers} / ${data.min_carriers_threshold} carriers</strong></span>
            <span>${p.nearest_expiry_days !== null ? `Nearest expiry: <strong class="text-amber">${p.nearest_expiry_days}d</strong>` : 'No valid rates'}</span>
          </div>

          <div class="carrier-chips-container">
            ${renderCarrierChips(p.carriers)}
          </div>

          <div class="cov-actions">
            <button class="btn btn-ghost btn-xs text-blue" onclick="window.rateRadar.filterRatesByPort('${escapeHtml(p.port_code)}')">View Rates &rarr;</button>
            <button class="btn btn-danger-ghost btn-xs" onclick="window.rateRadar.removeWatchedPort('${escapeHtml(p.port_code)}')">Remove</button>
          </div>
        </div>
      `).join('');

    } catch (err) {
      grid.innerHTML = `<div class="text-red py-4">Error loading port coverage: ${escapeHtml(err.message)}</div>`;
    }
  }

  // ── View 6: India Ports Board ─────────────────────────────────────────────
  async function loadIndiaCoverage() {
    const note = document.getElementById('india-summary-note');
    note.innerHTML = 'Evaluating Indian regional coverage board...';

    try {
      const data = await apiFetch('/coverage/india');
      const zones = data.zones || {};
      const detected = data.detected_not_watched || [];

      // Summary note
      const allZones = Object.values(zones);
      const totalGaps = allZones.reduce((acc, z) => acc + (z.gaps || 0), 0);
      const totalExpiring = allZones.reduce((acc, z) => acc + (z.expiring || 0), 0);

      if (totalGaps > 0) {
        note.innerHTML = `⚠️ <strong>Domestic & Gateway Gaps:</strong> ${totalGaps} monitored Indian port locations lack active contract rates. ${totalExpiring} ports have impending expiries.`;
      } else {
        note.innerHTML = `✓ <strong>Indian Port Coverage Strong:</strong> No critical gaps found across monitored coastal gateways and inland ICD facilities.`;
      }

      // Populate zone columns
      ['West', 'South', 'East', 'North', 'Central', 'Unclassified'].forEach(zoneName => {
        const zoneData = zones[zoneName] || { ports: [], summary: 'No ports' };
        const tagEl = document.getElementById(`tag-zone-${zoneName}`);
        const portsEl = document.getElementById(`ports-zone-${zoneName}`);

        if (tagEl) {
          tagEl.textContent = zoneData.summary || 'All covered';
          if (zoneData.gaps > 0) tagEl.className = 'zone-summary-tag badge badge-gap';
          else if (zoneData.expiring > 0) tagEl.className = 'zone-summary-tag badge badge-expiring';
          else tagEl.className = 'zone-summary-tag badge badge-covered';
        }

        if (portsEl) {
          if (!zoneData.ports || zoneData.ports.length === 0) {
            portsEl.innerHTML = `<div class="text-dim text-xs py-3 text-center">No ports monitored in this zone</div>`;
          } else {
            portsEl.innerHTML = zoneData.ports.map(p => `
              <div class="port-item-card">
                <div class="flex-between">
                  <div>
                    <span class="font-bold text-main">${escapeHtml(p.port_name || p.port_code)}</span>
                    <span class="font-mono text-xs text-dim ml-2">${escapeHtml(p.port_code)}</span>
                  </div>
                  <span class="badge ${getCoverageBadgeClass(p.status)}">${escapeHtml(p.status)}</span>
                </div>

                <div class="text-xs text-dim mt-2 flex-between">
                  <span>Depth: <strong class="text-main">${p.valid_carriers} carriers</strong></span>
                  <span>${p.nearest_expiry_days !== null ? `Expires: <strong class="text-amber">${p.nearest_expiry_days}d</strong>` : 'No rates'}</span>
                </div>

                <div class="carrier-chips-container">
                  ${renderCarrierChips(p.carriers)}
                </div>

                ${zoneName === 'Unclassified' ? `
                  <div class="mt-2 pt-2 border-t flex-between">
                    <span class="text-xs text-dim">Classify into Zone:</span>
                    <select class="select select-sm max-w-md" onchange="window.rateRadar.classifyIndiaPort('${escapeHtml(p.port_code)}', this.value)">
                      <option value="">Select Zone...</option>
                      <option value="West">West</option>
                      <option value="South">South</option>
                      <option value="East">East</option>
                      <option value="North">North</option>
                      <option value="Central">Central</option>
                    </select>
                  </div>
                ` : ''}

                <div class="mt-2 text-right">
                  <button class="btn btn-danger-ghost btn-xs" onclick="window.rateRadar.removeWatchedIndiaPort('${escapeHtml(p.port_code)}')">Remove</button>
                </div>
              </div>
            `).join('');
          }
        }
      });

      // Detected Indian ports
      const detectedEl = document.getElementById('detected-india-ports');
      if (detected.length > 0) {
        detectedEl.innerHTML = detected.map(d => `
          <div class="detected-port-chip">
            <div>
              <span class="font-mono font-bold text-main">${escapeHtml(d.code)}</span>
              <span class="text-xs text-dim ml-2">(${d.count} rates)</span>
            </div>
            <button class="btn btn-secondary btn-xs" onclick="window.rateRadar.addWatchedIndiaPort('${escapeHtml(d.code)}')">+ Watch</button>
          </div>
        `).join('');
      } else {
        detectedEl.innerHTML = `<div class="text-dim text-sm py-2">No unmonitored IN ports detected in dataset.</div>`;
      }

    } catch (err) {
      console.error('Error loading India board:', err);
    }
  }

  // ── View 7: Change History / Snapshot Diffs ───────────────────────────────
  async function loadHistory() {
    const tableBody = document.getElementById('history-table-body');
    tableBody.innerHTML = `<tr><td colspan="7" class="text-center text-dim py-6">Loading audit history...</td></tr>`;

    try {
      const data = await apiFetch('/history');
      const items = data.items || [];

      if (items.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="7" class="text-center text-dim py-6">No snapshot changes recorded yet. Changes will appear automatically after future sync runs.</td></tr>`;
        return;
      }

      tableBody.innerHTML = items.map(h => `
        <tr>
          <td class="font-mono text-xs text-dim">${formatSyncTime(h.timestamp)}</td>
          <td>
            <span class="badge ${getActionBadgeClass(h.action)}">${escapeHtml(h.action)}</span>
          </td>
          <td class="font-mono text-xs">${escapeHtml(h.rate_id)}</td>
          <td>
            <div class="font-semibold text-main">${escapeHtml(h.lane || 'N/A')}</div>
            <div class="text-xs text-dim">${escapeHtml(h.carrier || '')}</div>
          </td>
          <td class="font-mono text-xs text-blue">${escapeHtml(h.field_name || '-')}</td>
          <td class="font-mono text-xs text-red">${escapeHtml(h.old_value !== null ? h.old_value : '-')}</td>
          <td class="font-mono text-xs text-green">${escapeHtml(h.new_value !== null ? h.new_value : '-')}</td>
        </tr>
      `).join('');

    } catch (err) {
      tableBody.innerHTML = `<tr><td colspan="7" class="text-center text-red py-6">Failed to load history: ${escapeHtml(err.message)}</td></tr>`;
    }
  }

  // ── View 8: Settings & Sync Control ───────────────────────────────────────
  async function loadSettingsView() {
    try {
      const statusData = await apiFetch('/sync/status');
      const cfg = state.config;

      // Telemetry
      document.getElementById('settings-mode-val').innerHTML = cfg.is_demo
        ? `<strong class="text-amber">DEMO MODE (SYNTHETIC DATA)</strong>`
        : `<strong class="text-green">LIVE PRODUCTION MODE</strong>`;

      document.getElementById('settings-health-val').innerHTML = cfg.is_demo
        ? `<span class="badge badge-demo">Simulated</span>`
        : cfg.api_configured
          ? `<span class="badge badge-active">API Fully Configured</span>`
          : `<span class="badge badge-expired">Missing Required Configuration</span>`;

      document.getElementById('settings-last-sync-val').textContent = formatSyncTime(statusData.lastSuccessfulSync);

      // Checklist (Honest status, names only, NO secrets)
      const checklist = document.getElementById('config-checklist');
      const missing = new Set(cfg.missing_settings || []);

      const checkItems = [
        { label: 'API Base URL', key: 'ZIPAWORLD_API_BASE_URL' },
        { label: 'Rates Endpoint Path', key: 'ZIPAWORLD_RATES_PATH' },
        { label: 'Auth Scheme / Token', key: 'ZIPAWORLD_API_KEY' },
        { label: 'Response Items Path', key: 'ZIPAWORLD_ITEMS_PATH' },
        { label: 'Pagination Strategy', key: 'ZIPAWORLD_PAGINATION_STYLE' },
        { label: 'Field Mapping File', key: 'config/field-map.json' },
      ];

      checklist.innerHTML = checkItems.map(item => {
        const isMissing = missing.has(item.key);
        return `
          <li class="checklist-item">
            <span class="${isMissing ? 'check-missing' : 'check-ok'} font-bold">${isMissing ? '✗' : '✓'}</span>
            <span class="check-label font-semibold text-main">${item.label}</span>
            <span class="check-state font-mono ${isMissing ? 'text-red' : 'text-green'}">
              ${isMissing ? 'MISSING (Must Provide)' : 'Configured'}
            </span>
          </li>
        `;
      }).join('');

      // Thresholds Form
      document.getElementById('setting-threshold').value = state.settings.radar_expiry_threshold;
      document.getElementById('setting-threshold-val').textContent = state.settings.radar_expiry_threshold;
      document.getElementById('setting-min-carriers').value = state.settings.radar_min_carriers;
      document.getElementById('setting-timezone').value = state.settings.radar_timezone;
      document.getElementById('setting-admin-token').value = state.settings.admin_token;

      // Sync Log Table
      const logBody = document.getElementById('sync-log-body');
      const logs = statusData.recentLog || [];
      if (logs.length > 0) {
        logBody.innerHTML = logs.map(l => `
          <tr>
            <td class="font-mono text-xs">${formatSyncTime(l.synced_at)}</td>
            <td><span class="badge badge-direction">${escapeHtml(l.trigger_type || 'auto')}</span></td>
            <td>
              <span class="badge ${l.status === 'success' ? 'badge-active' : 'badge-expired'}">${escapeHtml(l.status)}</span>
            </td>
            <td class="font-mono">${l.records_synced || 0}</td>
            <td class="font-mono text-xs">${l.duration_ms ? `${l.duration_ms}ms` : '-'}</td>
          </tr>
        `).join('');
      } else {
        logBody.innerHTML = `<tr><td colspan="5" class="text-center text-dim py-4">No recent sync cycles logged</td></tr>`;
      }

    } catch (err) {
      console.error('Error loading settings:', err);
    }
  }

  function setupSettingsHandlers() {
    // Quick Threshold Slider in topbar
    const topSlider = document.getElementById('topbar-threshold');
    const topSliderVal = document.getElementById('topbar-threshold-val');
    topSlider.addEventListener('input', e => {
      const val = parseInt(e.target.value, 10);
      topSliderVal.textContent = `${val}d`;
      state.settings.radar_expiry_threshold = val;
      document.getElementById('setting-threshold').value = val;
      document.getElementById('setting-threshold-val').textContent = val;
    });

    topSlider.addEventListener('change', async e => {
      await saveThresholdSettings({ radar_expiry_threshold: parseInt(e.target.value, 10) });
    });

    // Quick Min Carriers in topbar
    const topMin = document.getElementById('topbar-min-carriers');
    topMin.addEventListener('change', async e => {
      const val = parseInt(e.target.value, 10);
      state.settings.radar_min_carriers = val;
      document.getElementById('setting-min-carriers').value = val;
      document.getElementById('country-min-label').textContent = val;
      await saveThresholdSettings({ radar_min_carriers: val });
    });

    // Form settings sliders
    const formSlider = document.getElementById('setting-threshold');
    const formSliderVal = document.getElementById('setting-threshold-val');
    formSlider.addEventListener('input', e => {
      formSliderVal.textContent = e.target.value;
      topSlider.value = e.target.value;
      topSliderVal.textContent = `${e.target.value}d`;
    });

    // Save Settings Button
    const btnSave = document.getElementById('btn-save-settings');
    btnSave.addEventListener('click', async () => {
      const threshold = parseInt(document.getElementById('setting-threshold').value, 10);
      const minCarriers = parseInt(document.getElementById('setting-min-carriers').value, 10);
      const tz = document.getElementById('setting-timezone').value;
      const adminToken = document.getElementById('setting-admin-token').value.trim();

      state.settings.radar_expiry_threshold = threshold;
      state.settings.radar_min_carriers = minCarriers;
      state.settings.radar_timezone = tz;
      state.settings.admin_token = adminToken;
      localStorage.setItem('radar_admin_token', adminToken);

      document.getElementById('sidebar-tz').textContent = tz;
      document.getElementById('country-min-label').textContent = minCarriers;

      await saveThresholdSettings({
        radar_expiry_threshold: threshold,
        radar_min_carriers: minCarriers,
        radar_timezone: tz,
      });
      showToast('Threshold and timezone settings saved successfully!', 'success');
    });
  }

  async function saveThresholdSettings(payload) {
    try {
      await apiFetch('/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      // Refresh current view math
      loadViewData(state.currentView);
    } catch (err) {
      showToast('Failed to save settings: ' + err.message, 'error');
    }
  }

  // ── Watchlists (Countries, Ports, India) ───────────────────────────────────
  function setupWatchlistControls() {
    // Add Country
    document.getElementById('btn-add-country').addEventListener('click', async () => {
      const sel = document.getElementById('select-add-country');
      const val = sel.value;
      if (!val) {
        showToast('Please select a country to add to watchlist', 'info');
        return;
      }

      try {
        const current = await apiFetch('/watchlist/countries');
        const list = new Set(current.items || []);
        list.add(val.toUpperCase());
        await apiFetch('/watchlist/countries', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: Array.from(list) }),
        });
        showToast(`Country ${val} added to monitored watchlist`, 'success');
        sel.value = '';
        loadCountryCoverage();
      } catch (err) {
        showToast('Error adding country: ' + err.message, 'error');
      }
    });

    // Add Port
    document.getElementById('btn-add-port').addEventListener('click', async () => {
      const input = document.getElementById('input-add-port');
      const code = input.value.trim().toUpperCase();
      if (!code || !/^[A-Z]{2}[A-Z0-9]{3}$/.test(code)) {
        showToast('Please enter a valid 5-character UN/LOCODE (e.g. NLRTM, SGSIN)', 'error');
        return;
      }

      try {
        const current = await apiFetch('/watchlist/ports');
        const list = new Set(current.items || []);
        list.add(code);
        await apiFetch('/watchlist/ports', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: Array.from(list) }),
        });
        showToast(`Port ${code} added to watchlist`, 'success');
        input.value = '';
        loadPortCoverage();
      } catch (err) {
        showToast('Error adding port: ' + err.message, 'error');
      }
    });

    // Add Indian Port Toggle
    const btnToggleIndia = document.getElementById('btn-add-india-port-toggle');
    const formIndia = document.getElementById('add-india-port-form');
    btnToggleIndia.addEventListener('click', () => {
      formIndia.style.display = formIndia.style.display === 'none' ? 'block' : 'none';
    });

    document.getElementById('btn-cancel-india-port').addEventListener('click', () => {
      formIndia.style.display = 'none';
    });

    document.getElementById('btn-submit-india-port').addEventListener('click', async () => {
      const input = document.getElementById('input-india-code');
      const code = input.value.trim().toUpperCase();
      if (!code || !/^IN[A-Z0-9]{3}$/.test(code)) {
        showToast('Please enter a valid Indian UN/LOCODE (e.g. INNSA, INMUN)', 'error');
        return;
      }

      await addIndiaPortToWatchlist(code);
      input.value = '';
      formIndia.style.display = 'none';
    });
  }

  async function addIndiaPortToWatchlist(code) {
    try {
      const current = await apiFetch('/watchlist/india');
      const list = new Set(current.items || []);
      list.add(code.toUpperCase());
      await apiFetch('/watchlist/india', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: Array.from(list) }),
      });
      showToast(`Indian port ${code} added to watchlist`, 'success');
      loadIndiaCoverage();
    } catch (err) {
      showToast('Error watching Indian port: ' + err.message, 'error');
    }
  }

  // ── Reference Countries Setup ─────────────────────────────────────────────
  async function loadCountriesReference() {
    try {
      const list = await apiFetch('/reference/countries');
      state.countriesRef = list;
      populateCountryDropdown(list);

      // Populate watchlist select
      const addSelect = document.getElementById('select-add-country');
      if (addSelect) {
        addSelect.innerHTML = `<option value="">Select country to watch...</option>` +
          list.map(c => `<option value="${escapeHtml(c.iso2)}">${getFlagEmoji(c.iso2)} ${escapeHtml(c.name)} (${escapeHtml(c.iso2)})</option>`).join('');
      }
    } catch (_) {}
  }

  function populateCountryDropdown(list) {
    const sel = document.getElementById('filter-country');
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = `<option value="">All Countries</option>` +
      list.map(c => `<option value="${escapeHtml(c.iso2)}" ${c.iso2 === current ? 'selected' : ''}>${getFlagEmoji(c.iso2)} ${escapeHtml(c.name)}</option>`).join('');
  }

  function filterCountryDropdownByRegion(region) {
    if (!region) {
      populateCountryDropdown(state.countriesRef);
    } else {
      const filtered = state.countriesRef.filter(c => c.region === region);
      populateCountryDropdown(filtered);
    }
  }

  // ── Rate Detail Drawer ────────────────────────────────────────────────────
  function setupDrawer() {
    const backdrop = document.getElementById('drawer-backdrop');
    const drawer = document.getElementById('rate-drawer');
    const closeBtn = document.getElementById('btn-close-drawer');

    function closeDrawer() {
      drawer.classList.remove('active');
      backdrop.classList.remove('active');
      drawer.setAttribute('aria-hidden', 'true');
    }

    closeBtn.addEventListener('click', closeDrawer);
    backdrop.addEventListener('click', closeDrawer);

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && drawer.classList.contains('active')) {
        closeDrawer();
      }
    });
  }

  async function openRateDrawer(rateId) {
    const backdrop = document.getElementById('drawer-backdrop');
    const drawer = document.getElementById('rate-drawer');
    drawer.classList.add('active');
    backdrop.classList.add('active');
    drawer.setAttribute('aria-hidden', 'false');

    document.getElementById('drawer-rate-id').textContent = rateId;
    document.getElementById('drawer-src-status').textContent = 'Loading...';

    try {
      const rate = await apiFetch(`/rates/${encodeURIComponent(rateId)}`);
      state.selectedRate = rate;

      // Section 1: Source Data (from Zipaworld API)
      document.getElementById('drawer-src-status').textContent = rate.source_status || 'Delivered';
      document.getElementById('drawer-src-origin').textContent = rate.origin_raw || 'N/A';
      document.getElementById('drawer-src-dest').textContent = rate.destination_raw || 'N/A';
      document.getElementById('drawer-src-carrier').textContent = rate.carrier_raw || 'N/A';
      document.getElementById('drawer-src-mode').textContent = rate.shipment_mode || 'FCL';
      document.getElementById('drawer-src-container').textContent = rate.container_name || 'Standard';
      document.getElementById('drawer-src-rate').textContent = `${rate.currency || ''} ${rate.rate ? Number(rate.rate).toLocaleString() : 'Not Quoted'}`;
      document.getElementById('drawer-src-start').textContent = rate.validity_start_date || 'None';
      document.getElementById('drawer-src-end').textContent = rate.validity_end_date || 'None';

      // Section 2: Calculated by Rate Radar
      const exp = rate.expiry || {};
      document.getElementById('drawer-calc-status').innerHTML = `<span class="badge ${getStatusBadgeClass(exp.status)}">${escapeHtml(exp.status || '')}</span>`;
      document.getElementById('drawer-calc-days').textContent = exp.days_remaining !== null ? `${exp.days_remaining} days` : 'N/A';
      document.getElementById('drawer-calc-label').textContent = exp.expiry_label || 'N/A';
      document.getElementById('drawer-calc-brand').textContent = rate.carrier_brand || 'Unknown';
      document.getElementById('drawer-calc-direction').textContent = rate.direction || 'Unclassified';
      document.getElementById('drawer-calc-origin-port').textContent = `${rate.origin_port_name || rate.origin_code} (${rate.origin_country || rate.origin_iso2 || ''})`;
      document.getElementById('drawer-calc-dest-port').textContent = `${rate.destination_port_name || rate.destination_code} (${rate.destination_country || rate.destination_iso2 || ''})`;
      document.getElementById('drawer-calc-dedup').textContent = rate.dedup_key || rate.id;

      // Section 3: Suggested Operational Actions
      renderSuggestedActions(rate, exp);

    } catch (err) {
      document.getElementById('drawer-src-status').textContent = 'Failed to load details: ' + err.message;
    }
  }

  function renderSuggestedActions(rate, exp) {
    const list = document.getElementById('drawer-suggested-actions');
    const actions = [];

    const carrier = rate.carrier_brand || 'carrier';

    if (exp.status === 'EXPIRED') {
      actions.push({ icon: '🛑', title: `Contact ${carrier} Pricing Desk`, desc: `Request renewed contract rate or extension on ${rate.origin_code} &rarr; ${rate.destination_code}` });
      actions.push({ icon: '🔄', title: 'Review Active Replacement Corridors', desc: 'Identify alternate carrier tariffs on this route to maintain booking capability' });
      actions.push({ icon: '⚠️', title: 'Mark Expired in Operational TMS', desc: 'Ensure expired tariff is suppressed from front-end customer quotations' });
    } else if (exp.status === 'EXPIRING SOON') {
      actions.push({ icon: '⏳', title: `Initiate Contract Rollover with ${carrier}`, desc: `Tariff expires in ${exp.days_remaining} days; request next monthly/quarterly index file` });
      actions.push({ icon: '📊', title: 'Verify Carrier Multi-Depth', desc: 'Confirm at least 2 alternate carriers remain active on this corridor' });
    } else if (exp.status === 'NEEDS REVIEW') {
      actions.push({ icon: '❓', title: 'Audit Date Schema in API Feed', desc: 'Contract dates are missing or conflicting; verify record source with Zipaworld tech support' });
      actions.push({ icon: '🚫', title: 'Hold Automated Bookings', desc: 'Prevent automated spot rating until validity period is verified' });
    } else if (exp.status === 'STARTS LATER') {
      actions.push({ icon: '📅', title: 'Schedule Contract Activation', desc: `Rate takes effect on ${rate.validity_start_date}; prepare pricing rules for deployment` });
    } else {
      actions.push({ icon: '✓', title: 'Tariff Active & Sound', desc: 'Valid carrier depth maintained. No pricing intervention required at this time.' });
    }

    list.innerHTML = actions.map(a => `
      <div class="action-pill-item">
        <span class="icon">${a.icon}</span>
        <div>
          <div class="font-semibold text-main">${escapeHtml(a.title)}</div>
          <div class="text-xs text-dim mt-1">${escapeHtml(a.desc)}</div>
        </div>
      </div>
    `).join('');
  }

  // ── Helper Badges & Chips Rendering ───────────────────────────────────────
  function getStatusBadgeClass(status) {
    switch (status) {
      case 'ACTIVE': return 'badge-active';
      case 'EXPIRING SOON': return 'badge-expiring';
      case 'EXPIRED': return 'badge-expired';
      case 'STARTS LATER': return 'badge-later';
      case 'NEEDS REVIEW': return 'badge-review';
      default: return 'badge-direction';
    }
  }

  function getCoverageBadgeClass(status) {
    switch (status) {
      case 'COVERED': return 'badge-covered';
      case 'THIN COVER': return 'badge-thin';
      case 'GAP': return 'badge-gap';
      case 'ALL EXPIRED': return 'badge-all-expired';
      default: return 'badge-direction';
    }
  }

  function getActionBadgeClass(action) {
    switch (action) {
      case 'ADDED': return 'badge-active';
      case 'UPDATED': return 'badge-later';
      case 'REMOVED': return 'badge-expired';
      default: return 'badge-direction';
    }
  }

  function renderCarrierChips(carriers) {
    if (!carriers) return '';
    const active = carriers.active || [];
    const expiring = carriers.expiring || [];
    const expired = carriers.expired || [];

    const chips = [];
    active.forEach(c => chips.push(`<span class="chip-carrier chip-carrier-active">✓ ${escapeHtml(c)}</span>`));
    expiring.forEach(c => chips.push(`<span class="chip-carrier chip-carrier-expiring">⏳ ${escapeHtml(c)}</span>`));
    expired.forEach(c => chips.push(`<span class="chip-carrier chip-carrier-expired">✕ ${escapeHtml(c)}</span>`));

    return chips.length > 0 ? chips.join('') : '<span class="text-xs text-dim">No carriers found</span>';
  }

  // ── Global Window Scope Exports for Handlers ──────────────────────────────
  window.rateRadar = {
    switchView,
    openRateDrawer,
    filterRatesByCountry: (code) => {
      state.ratesQuery.dest_country = code;
      state.ratesQuery.page = 1;
      document.getElementById('filter-country').value = code;
      switchView('rates');
    },
    filterRatesByPort: (code) => {
      state.ratesQuery.search = code;
      state.ratesQuery.page = 1;
      document.getElementById('filter-search').value = code;
      switchView('rates');
    },
    removeWatchedCountry: async (code) => {
      try {
        const current = await apiFetch('/watchlist/countries');
        const list = (current.items || []).filter(c => c !== code);
        await apiFetch('/watchlist/countries', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: list }),
        });
        showToast(`Removed ${code} from watchlist`, 'info');
        loadCountryCoverage();
      } catch (err) {
        showToast('Error removing country: ' + err.message, 'error');
      }
    },
    removeWatchedPort: async (code) => {
      try {
        const current = await apiFetch('/watchlist/ports');
        const list = (current.items || []).filter(p => p !== code);
        await apiFetch('/watchlist/ports', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: list }),
        });
        showToast(`Removed port ${code} from watchlist`, 'info');
        loadPortCoverage();
      } catch (err) {
        showToast('Error removing port: ' + err.message, 'error');
      }
    },
    removeWatchedIndiaPort: async (code) => {
      try {
        const current = await apiFetch('/watchlist/india');
        const list = (current.items || []).filter(p => p !== code);
        await apiFetch('/watchlist/india', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: list }),
        });
        showToast(`Removed Indian port ${code}`, 'info');
        loadIndiaCoverage();
      } catch (err) {
        showToast('Error removing Indian port: ' + err.message, 'error');
      }
    },
    addWatchedIndiaPort: async (code) => {
      await addIndiaPortToWatchlist(code);
    },
    classifyIndiaPort: async (code, zone) => {
      if (!zone) return;
      try {
        await apiFetch(`/watchlist/india/${encodeURIComponent(code)}/zone`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ zone }),
        });
        showToast(`Port ${code} classified to ${zone} zone`, 'success');
        loadIndiaCoverage();
      } catch (err) {
        showToast('Error classifying port: ' + err.message, 'error');
      }
    },
    handleAttentionClick: (type, code) => {
      if (type === 'country') {
        window.rateRadar.filterRatesByCountry(code);
      } else {
        window.rateRadar.filterRatesByPort(code);
      }
    },
  };

  // Start the application when DOM is ready
  document.addEventListener('DOMContentLoaded', initApp);
})();
