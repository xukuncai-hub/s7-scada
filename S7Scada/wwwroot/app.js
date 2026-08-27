/* ================================================================
   S7 SCADA — JavaScript Bridge & UI Controller
   ================================================================ */

// ── State ─────────────────────────────────────────────────────
var state = {
    connected: false,
    tags: [],
    plcInfo: null,
    scanTime: 0,
    contextTagIndex: -1,
    editingTagIndex: -1,
    view: 'table',
    screens: [],
    currentScreen: -1,
    selectedWidget: null,
    // Cached DOM element references (avoid repeated getElementById per scan)
    dashValEls: {},
    tblValEls: {},
    tblQBadges: {},
    tblTimeEls: {}
};

// Filter state (search + group)
var filter = { search: '', group: 'All' };

// ── Theme Toggle ──────────────────────────────────────────────
function applyTheme(theme) {
    var html = document.documentElement;
    if (theme === 'dark') {
        html.setAttribute('data-theme', 'dark');
    } else {
        html.removeAttribute('data-theme');
    }
    var sunIcon = document.querySelector('.theme-btn .icon-sun');
    var moonIcon = document.querySelector('.theme-btn .icon-moon');
    if (sunIcon && moonIcon) {
        sunIcon.style.display = theme === 'dark' ? 'none' : '';
        moonIcon.style.display = theme === 'dark' ? '' : 'none';
    }
    // Notify the WPF window so its chrome background matches the theme
    postToCSharp({ action: 'theme', theme: theme });
}

function toggleTheme() {
    var current = localStorage.getItem('scada-theme') || 'light';
    var next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem('scada-theme', next);
    applyTheme(next);
}

(function initTheme() {
    var saved = localStorage.getItem('scada-theme') || 'light';
    applyTheme(saved);
})();

// ── Area & Type Colors (read from CSS variables for theme support) ──
function getCssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

var AREA_COLORS = {
    DB: '#2563eb',
    M:  '#16a34a',
    I:  '#d97706',
    Q:  '#dc2626',
    T:  '#9333ea',
    C:  '#9333ea'
};

var TYPE_COLORS = {
    Bool: '#2563eb',
    Byte: '#16a34a',
    Word: '#d97706',
    DWord:'#dc2626',
    Int:  '#9333ea',
    DInt: '#2563eb',
    Real: '#d97706'
};

// ── Window Controls ───────────────────────────────────────────
// 原生标题栏负责最小化/最大化/关闭与拖动，无需自定义处理。

// ── Toast System ──────────────────────────────────────────────
var toastContainer = null;

function ensureToastContainer() {
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
    }
    return toastContainer;
}

function showToast(message, type) {
    type = type || 'info';
    var container = ensureToastContainer();
    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(function () {
        toast.style.animation = 'toast-out 0.25s ease-in forwards';
        setTimeout(function () { toast.remove(); }, 250);
    }, 3500);
}

// ── C# -> JS API (window callbacks) ──────────────────────────

window.onConnectionChanged = function (connected, statusText, connecting) {
    state.connected = connected;
    updateConnectionUI(connected, statusText, connecting);
};

window.onPlcInfo = function (info) {
    state.plcInfo = info;
    updatePlcInfoUI(info);
};

window.onDataUpdated = function (results) {
    if (!results || !Array.isArray(results)) return;
    for (var i = 0; i < results.length; i++) {
        var r = results[i];
        if (r.index >= 0 && r.index < state.tags.length) {
            state.tags[r.index].value = r.value;
            state.tags[r.index].quality = r.quality;
            state.tags[r.index].timestamp = r.timestamp;
        }
    }
    updateDashboardValues();
    updateTableValues();
    updateScreenWidgets();
};

window.onScanTime = function (ms) {
    state.scanTime = ms;
    var el = document.getElementById('statusScanTime');
    if (el) el.textContent = 'Scan: ' + ms.toFixed(1) + ' ms';
};

window.onTagsChanged = function (tags) {
    state.tags = tags || [];
    renderDashboard();
    renderTable();
    updateTagCount();
    renderProps(); // 组件绑定下拉随标签增删刷新
};

window.onError = function (message) {
    showToast(message, 'error');
};

// ── JS -> C# Bridge ──────────────────────────────────────────

function postToCSharp(obj) {
    if (window.chrome && window.chrome.webview) {
        window.chrome.webview.postMessage(JSON.stringify(obj));
    }
}

// ── C# -> JS message listener (PostWebMessageAsJson) ─────────
// All real-time data now arrives as structured JSON messages instead
// of eval'd JS strings.
if (window.chrome && window.chrome.webview) {
    window.chrome.webview.addEventListener('message', function (e) {
        var msg = e.data;
        if (!msg || !msg.type) return;
        switch (msg.type) {
            case 'connectionChanged': window.onConnectionChanged(msg.connected, msg.text, !!msg.connecting); break;
            case 'plcInfo':           window.onPlcInfo(msg.info); break;
            case 'dataUpdated':       window.onDataUpdated(msg.results); break;
            case 'scanTime':          window.onScanTime(msg.ms); break;
            case 'tagsChanged':       window.onTagsChanged(msg.tags); break;
            case 'screensChanged':    window.onScreensChanged(msg.screens); break;
            case 'toast':             showToast(msg.text, msg.kind || 'info'); break;
            case 'error':             showToast(msg.text, 'error'); break;
            default: break;
        }
    });
}

function connectPlc() {
    var ip = document.getElementById('inputIp').value.trim();
    var rack = parseInt(document.getElementById('inputRack').value) || 0;
    var slot = parseInt(document.getElementById('inputSlot').value) || 1;
    var scanInterval = parseInt(document.getElementById('inputScan').value) || 500;
    var cpu = document.getElementById('inputCpu').value;

    if (!ip) {
        showToast('Please enter a PLC IP address', 'error');
        return;
    }

    postToCSharp({
        action: 'connect',
        ip: ip,
        rack: rack,
        slot: slot,
        scanInterval: scanInterval,
        cpu: cpu
    });
}

function disconnectPlc() {
    postToCSharp({ action: 'disconnect' });
}

function addTag(tag) {
    postToCSharp({ action: 'addTag', tag: tag });
}

function editTag(index, tag) {
    postToCSharp({ action: 'editTag', index: index, tag: tag });
}

function deleteTag(index) {
    postToCSharp({ action: 'deleteTag', index: index });
}

function writeValue(index, value) {
    postToCSharp({ action: 'writeValue', index: index, value: value });
}

function saveConfig() {
    postToCSharp({ action: 'saveConfig' });
}

function loadConfig() {
    postToCSharp({ action: 'loadConfig' });
}

function saveConfigAs(path) {
    postToCSharp({ action: 'saveConfigAs', path: path });
}

function toggleScan(index) {
    postToCSharp({ action: 'toggleScan', index: index });
}

function refreshNow() {
    postToCSharp({ action: 'refreshNow' });
}

// ── Connection UI ─────────────────────────────────────────────

function updateConnectionUI(connected, statusText, connecting) {
    var header = document.getElementById('connHeader');
    var led = document.getElementById('connLed');
    var statusEl = document.getElementById('connStatus');
    var toolbarDot = document.getElementById('toolbarStatusDot');
    var toolbarText = document.getElementById('toolbarStatusText');
    var statusDot = document.getElementById('statusDot');
    var statusTextEl = document.getElementById('statusText');
    var btnConnToolbar = document.getElementById('btnConnectToolbar');
    var btnDisconnToolbar = document.getElementById('btnDisconnectToolbar');
    var btnConnSidebar = document.getElementById('btnConnectSidebar');
    var btnDisconnSidebar = document.getElementById('btnDisconnectSidebar');
    var plcDetail = document.getElementById('plcDetail');

    connecting = !!connecting;
    var label = statusText || (connected ? 'Connected' : 'Disconnected');

    // Toggle connected / connecting classes (amber pulse while attempting)
    header.classList.toggle('connected', connected);
    header.classList.toggle('connecting', connecting);
    led.classList.toggle('connected', connected);
    led.classList.toggle('connecting', connecting);
    statusEl.classList.toggle('connected', connected);
    statusDot.classList.toggle('connected', connected);
    statusDot.classList.toggle('connecting', connecting);
    toolbarDot.classList.toggle('connected', connected);
    toolbarDot.classList.toggle('connecting', connecting);

    // Status text
    statusEl.textContent = label;
    toolbarText.textContent = label;
    statusTextEl.textContent = label;

    // Statusbar left parent
    var sbl = document.querySelector('.sb-left');
    if (sbl) sbl.classList.toggle('connected', connected);

    // Button visibility + disable Connect while an attempt is in flight
    btnConnToolbar.style.display = connected ? 'none' : '';
    btnConnToolbar.disabled = connecting;
    btnDisconnToolbar.style.display = connected ? '' : 'none';
    btnConnSidebar.style.display = connected ? 'none' : '';
    btnConnSidebar.disabled = connecting;
    btnDisconnSidebar.style.display = connected ? '' : 'none';

    // Input disable state
    document.getElementById('inputIp').disabled = connected;
    document.getElementById('inputCpu').disabled = connected;
    document.getElementById('inputRack').disabled = connected;
    document.getElementById('inputSlot').disabled = connected;

    // PLC detail section
    plcDetail.style.display = connected ? '' : 'none';
}

function updatePlcInfoUI(info) {
    if (!info) return;
    var parts = [];
    if (info.module) parts.push(info.module);
    if (info.firmwareVersion) parts.push('FW:' + info.firmwareVersion);

    var connPlcInfo = document.getElementById('connPlcInfo');
    var statusPlcInfo = document.getElementById('statusPlcInfo');
    if (connPlcInfo) connPlcInfo.textContent = parts.join(' | ');
    if (statusPlcInfo) statusPlcInfo.textContent = parts.join(' | ');

    var plcModule = document.getElementById('plcModule');
    var plcFirmware = document.getElementById('plcFirmware');
    var plcSerial = document.getElementById('plcSerial');
    if (plcModule) plcModule.textContent = info.module || '-';
    if (plcFirmware) plcFirmware.textContent = info.firmwareVersion || '-';
    if (plcSerial) plcSerial.textContent = info.serialNumber || '-';
}

// ── Tag Count ─────────────────────────────────────────────────

function updateTagCount() {
    var count = state.tags.length;
    var tagCountEl = document.getElementById('tagCount');
    var dashCountEl = document.getElementById('dashboardCount');
    var statusTagEl = document.getElementById('statusTagCount');
    if (tagCountEl) tagCountEl.textContent = String(count);
    if (dashCountEl) dashCountEl.textContent = String(count);
    if (statusTagEl) statusTagEl.textContent = 'Tags: ' + count;
}

// ── Dashboard Cards ───────────────────────────────────────────

function renderDashboard() {
    var section = document.getElementById('dashboardSection');
    var container = document.getElementById('dashboardCards');
    var empty = document.getElementById('emptyState');
    var tableCont = document.getElementById('tableContainer');

    if (state.tags.length === 0) {
        section.style.display = 'none';
        empty.style.display = '';
        tableCont.style.display = 'none';
        return;
    }

    section.style.display = '';
    empty.style.display = 'none';
    tableCont.style.display = '';

    container.innerHTML = '';
    state.dashValEls = {};
    for (var i = 0; i < state.tags.length; i++) {
        var tag = state.tags[i];
        var areaColor = AREA_COLORS[tag.area] || AREA_COLORS.M;
        var typeColor = TYPE_COLORS[tag.dataType] || TYPE_COLORS.Bool;

        var card = document.createElement('div');
        card.className = 'dash-card';
        card.style.setProperty('--card-accent', areaColor);
        card.style.setProperty('--type-bg', typeColor);
        card.dataset.index = i;

        card.innerHTML =
            '<div class="dash-top">' +
                '<div class="dash-name">' + esc(tag.name) + '</div>' +
                '<div class="dash-addr">' + esc(tag.address) + '</div>' +
            '</div>' +
            '<div class="dash-bottom">' +
                '<div class="dash-value" id="dashVal' + i + '">' + formatValue(tag.value, tag.quality) + '</div>' +
                '<div class="dash-type">' + esc(tag.dataType) + '</div>' +
            '</div>';

        state.dashValEls[i] = card.querySelector('.dash-value');

        (function (idx) {
            card.addEventListener('dblclick', function () { handleDoubleClick(idx); });
        })(i);

        container.appendChild(card);
    }
}

function updateDashboardValues() {
    for (var i = 0; i < state.tags.length; i++) {
        var tag = state.tags[i];
        var el = state.dashValEls[i];
        if (el) {
            var newVal = formatValue(tag.value, tag.quality);
            if (el.textContent !== newVal) {
                el.textContent = newVal;
                el.className = 'dash-value ' + (tag.quality === 'Good' ? '' : tag.quality === 'Bad' ? 'bad' : 'unknown');
                var parentCard = el.closest('.dash-card');
                if (parentCard) {
                    parentCard.classList.add('value-updated');
                    (function (card) {
                        setTimeout(function () { card.classList.remove('value-updated'); }, 500);
                    })(parentCard);
                }
            }
        }
    }
}

// ── Tag Table ─────────────────────────────────────────────────

function renderTable() {
    var tbody = document.getElementById('tagTableBody');
    tbody.innerHTML = '';

    state.tblValEls = {};
    state.tblQBadges = {};
    state.tblTimeEls = {};
    updateGroupFilter();

    var visible = 0;
    for (var i = 0; i < state.tags.length; i++) {
        var tag = state.tags[i];
        if (!tagMatches(tag)) continue;
        visible++;

        var areaColor = AREA_COLORS[tag.area] || AREA_COLORS.M;
        var typeColor = TYPE_COLORS[tag.dataType] || TYPE_COLORS.Bool;
        var qualityClass = tag.quality === 'Good' ? 'good' : tag.quality === 'Bad' ? 'bad' : 'unknown';
        var valueClass = tag.quality === 'Good' ? '' : tag.quality === 'Bad' ? 'bad' : 'unknown';

        var tr = document.createElement('tr');
        tr.dataset.index = i;

        (function (idx, row) {
            row.addEventListener('contextmenu', function (e) { showContextMenu(e, idx); });
            row.addEventListener('dblclick', function () { handleDoubleClick(idx); });
        })(i, tr);

        tr.innerHTML =
            '<td>' +
                '<div class="cell-name">' +
                    '<span class="scan-dot ' + (tag.scanEnabled ? 'on' : 'off') + '"></span>' +
                    '<span class="area-dot" style="background:' + areaColor + '"></span>' +
                    '<span class="name-text">' + esc(tag.name) + '</span>' +
                '</div>' +
            '</td>' +
            '<td class="cell-address">' + esc(tag.address) + '</td>' +
            '<td><span class="group-badge">' + esc(tag.group || 'Default') + '</span></td>' +
            '<td><span class="type-badge" style="background:' + hexToRgba(typeColor, 0.15) + ';color:' + typeColor + '">' + esc(tag.dataType) + '</span></td>' +
            '<td><span class="cell-value ' + valueClass + '">' + formatValue(tag.value, tag.quality) + '</span></td>' +
            '<td><span class="quality-badge ' + qualityClass + '">' + qualityLabel(tag.quality) + '</span></td>' +
            '<td class="cell-time">' + esc(tag.timestamp || '--') + '</td>';

        // Cache element refs for fast per-scan updates
        state.tblValEls[i] = tr.querySelector('.cell-value');
        state.tblQBadges[i] = tr.querySelector('.quality-badge');
        state.tblTimeEls[i] = tr.querySelector('.cell-time');

        tbody.appendChild(tr);
    }

    if (visible === 0) {
        var trEmpty = document.createElement('tr');
        trEmpty.innerHTML = '<td colspan="7" class="no-results">No tags match the current filter</td>';
        tbody.appendChild(trEmpty);
    }
}

function updateTableValues() {
    for (var i = 0; i < state.tags.length; i++) {
        var tag = state.tags[i];
        var valEl = state.tblValEls[i];
        if (valEl) {
            var newVal = formatValue(tag.value, tag.quality);
            if (valEl.textContent !== newVal) {
                valEl.textContent = newVal;
                valEl.className = 'cell-value ' + (tag.quality === 'Good' ? '' : tag.quality === 'Bad' ? 'bad' : 'unknown');
                valEl.classList.add('value-updated');
                (function (el) {
                    setTimeout(function () { el.classList.remove('value-updated'); }, 500);
                })(valEl);
            }
        }
        var qBadge = state.tblQBadges[i];
        if (qBadge) {
            var qc = tag.quality === 'Good' ? 'good' : tag.quality === 'Bad' ? 'bad' : 'unknown';
            qBadge.className = 'quality-badge ' + qc;
            qBadge.textContent = qualityLabel(tag.quality);
        }
        var timeCell = state.tblTimeEls[i];
        if (timeCell && tag.timestamp) {
            timeCell.textContent = tag.timestamp;
        }
    }
}

// ── Filtering / Search ────────────────────────────────────────

function applyFilter() {
    filter.search = (document.getElementById('filterSearch').value || '').toLowerCase().trim();
    filter.group = document.getElementById('filterGroup').value;
    renderTable();
}

function tagMatches(tag) {
    if (filter.group !== 'All' && (tag.group || 'Default') !== filter.group) return false;
    if (filter.search) {
        var hay = ((tag.name || '') + ' ' + (tag.address || '') + ' ' + (tag.group || '')).toLowerCase();
        if (hay.indexOf(filter.search) < 0) return false;
    }
    return true;
}

function updateGroupFilter() {
    var sel = document.getElementById('filterGroup');
    if (!sel) return;
    var current = sel.value;
    var groups = {};
    for (var i = 0; i < state.tags.length; i++) {
        groups[state.tags[i].group || 'Default'] = true;
    }
    var keys = Object.keys(groups).sort();
    var html = '<option value="All">All Groups</option>';
    var found = false;
    for (var k = 0; k < keys.length; k++) {
        var selAttr = keys[k] === current ? ' selected' : '';
        if (selAttr) found = true;
        html += '<option value="' + esc(keys[k]) + '"' + selAttr + '>' + esc(keys[k]) + '</option>';
    }
    sel.innerHTML = html;
    // If the previously-selected group no longer exists, fall back to All
    if (!found && current !== 'All') filter.group = 'All';
}

// ── Sidebar ───────────────────────────────────────────────────

function toggleSidebar() {
    var collapsed = document.body.classList.toggle('sidebar-collapsed');
    localStorage.setItem('scada-sidebar', collapsed ? 'collapsed' : 'expanded');
}

// ── Value Formatting ──────────────────────────────────────────

function formatValue(value, quality) {
    if (quality === 'Unknown' || value === null || value === undefined) return '---';
    if (typeof value === 'boolean') return value ? 'TRUE' : 'FALSE';
    if (typeof value === 'number') {
        if (Number.isInteger(value)) {
            // Show hex for large unsigned values
            if (value > 0xFFFF) return value + ' (0x' + value.toString(16).toUpperCase() + ')';
            return value.toString();
        }
        return value.toFixed(4);
    }
    return String(value);
}

function qualityLabel(q) {
    if (q === 'Good') return 'Good';
    if (q === 'Bad') return 'Bad';
    return 'Unknown';
}

// ── Context Menu ──────────────────────────────────────────────

function showContextMenu(e, index) {
    e.preventDefault();
    state.contextTagIndex = index;

    var tag = state.tags[index];
    var menu = document.getElementById('contextMenu');
    var toggleText = document.getElementById('ctxToggleScanText');
    toggleText.textContent = tag.scanEnabled ? 'Disable Scan' : 'Enable Scan';

    var rows = document.querySelectorAll('.data-table tr.selected');
    for (var i = 0; i < rows.length; i++) rows[i].classList.remove('selected');
    e.currentTarget.classList.add('selected');

    var x = e.clientX;
    var y = e.clientY;
    menu.classList.add('visible');

    var rect = menu.getBoundingClientRect();
    if (x + rect.width > window.innerWidth) x = window.innerWidth - rect.width - 8;
    if (y + rect.height > window.innerHeight) y = window.innerHeight - rect.height - 8;

    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
}

function hideContextMenu() {
    document.getElementById('contextMenu').classList.remove('visible');
    var rows = document.querySelectorAll('.data-table tr.selected');
    for (var i = 0; i < rows.length; i++) rows[i].classList.remove('selected');
}

function contextWriteValue() {
    hideContextMenu();
    var idx = state.contextTagIndex;
    if (idx < 0 || idx >= state.tags.length) return;

    var tag = state.tags[idx];
    if (tag.dataType === 'Bool' && state.connected) {
        var currentVal = tag.value === true;
        writeValue(idx, !currentVal);
        return;
    }

    showWriteValueModal(idx);
}

function contextToggleScan() {
    hideContextMenu();
    var idx = state.contextTagIndex;
    if (idx >= 0) toggleScan(idx);
}

function contextEditTag() {
    hideContextMenu();
    var idx = state.contextTagIndex;
    if (idx >= 0 && idx < state.tags.length) {
        showEditTagModal(idx);
    }
}

function contextDeleteTag() {
    hideContextMenu();
    var idx = state.contextTagIndex;
    if (idx >= 0) {
        if (confirm('Delete tag "' + state.tags[idx].name + '"?')) {
            deleteTag(idx);
        }
    }
}

// ── Double-click handler ──────────────────────────────────────

function handleDoubleClick(index) {
    state.contextTagIndex = index;
    contextWriteValue();
}

// ── Tag Editor Modal ──────────────────────────────────────────

function showAddTagModal() {
    state.editingTagIndex = -1;
    document.getElementById('tagEditorTitle').textContent = 'Add Tag';
    document.getElementById('editorName').value = '';
    document.getElementById('editorAddress').value = '';
    document.getElementById('editorDataType').value = 'Bool';
    document.getElementById('editorGroup').value = 'Default';
    document.getElementById('editorComment').value = '';
    document.getElementById('editorScanEnabled').checked = true;
    var preview = document.getElementById('editorPreview');
    preview.textContent = 'Enter an address to auto-parse...';
    preview.className = 'field-preview';
    document.getElementById('tagEditorModal').classList.add('visible');
    document.getElementById('editorName').focus();
}

function showEditTagModal(index) {
    var tag = state.tags[index];
    if (!tag) return;

    state.editingTagIndex = index;
    document.getElementById('tagEditorTitle').textContent = 'Edit Tag';
    document.getElementById('editorName').value = tag.name;
    document.getElementById('editorAddress').value = tag.address;
    document.getElementById('editorDataType').value = tag.dataType;
    document.getElementById('editorGroup').value = tag.group;
    document.getElementById('editorComment').value = tag.comment || '';
    document.getElementById('editorScanEnabled').checked = tag.scanEnabled;
    onAddressChanged();
    document.getElementById('tagEditorModal').classList.add('visible');
}

function closeTagEditor() {
    document.getElementById('tagEditorModal').classList.remove('visible');
}

function confirmTagEditor() {
    var name = document.getElementById('editorName').value.trim();
    var address = document.getElementById('editorAddress').value.trim().toUpperCase();
    var dataType = document.getElementById('editorDataType').value;
    var group = document.getElementById('editorGroup').value.trim() || 'Default';
    var comment = document.getElementById('editorComment').value.trim();
    var scanEnabled = document.getElementById('editorScanEnabled').checked;

    if (!name) {
        showToast('Please enter a tag name', 'error');
        return;
    }
    if (!address) {
        showToast('Please enter an address', 'error');
        return;
    }

    var tag = {
        name: name,
        address: address,
        dataType: dataType,
        group: group,
        comment: comment,
        scanEnabled: scanEnabled
    };

    if (state.editingTagIndex >= 0) {
        editTag(state.editingTagIndex, tag);
    } else {
        addTag(tag);
    }

    closeTagEditor();
}

// Address auto-parse preview
function onAddressChanged() {
    var addr = document.getElementById('editorAddress').value.trim().toUpperCase();
    var preview = document.getElementById('editorPreview');

    if (!addr) {
        preview.textContent = 'Enter an address to auto-parse...';
        preview.className = 'field-preview';
        return;
    }

    var parsed = parseAddress(addr);
    if (parsed) {
        var text = 'Area: ' + parsed.area + '  |  Type: ' + parsed.dataType + '  |  Offset: ' + parsed.byteOffset;
        if (parsed.dataType === 'Bool') text += '  |  Bit: ' + parsed.bitOffset;
        preview.textContent = text;
        preview.className = 'field-preview valid';
        document.getElementById('editorDataType').value = parsed.dataType;
    } else {
        preview.textContent = 'Cannot parse address. Check format.';
        preview.className = 'field-preview invalid';
    }
}

// Client-side address parser (mirrors AddressParser.cs)
function parseAddress(addr) {
    if (!addr) return null;

    // DB: DB1.DBX0.0, DB1.DBW2, DB1.DBD4, DB1.DBB0
    var dbMatch = addr.match(/^DB(\d+)\.(DB[WXDB])(\d+)(?:\.(\d+))?$/i);
    if (dbMatch) {
        var dbNum = parseInt(dbMatch[1]);
        var suffix = dbMatch[2].toUpperCase();
        var offset = parseInt(dbMatch[3]);
        var bitPart = dbMatch[4] !== undefined ? parseInt(dbMatch[4]) : 0;
        var typeChar = suffix[2];

        var typeMap = { X: 'Bool', B: 'Byte', W: 'Word', D: 'DWord' };
        return {
            area: 'DB',
            dataType: typeMap[typeChar] || 'Word',
            dbNumber: dbNum,
            byteOffset: offset,
            bitOffset: bitPart
        };
    }

    // Non-DB: M0.0, MW2, I0.0, Q0.0, T0, C0
    var nonDb = addr.match(/^([MIQTC])([WXDB])?(\d+)(?:\.(\d+))?$/i);
    if (nonDb) {
        var areaPrefix = nonDb[1].toUpperCase();
        var tc = nonDb[2] ? nonDb[2].toUpperCase() : null;
        var off = parseInt(nonDb[3]);
        var bp = nonDb[4] !== undefined ? parseInt(nonDb[4]) : null;

        if (!tc && bp !== null) {
            return { area: areaPrefix, dataType: 'Bool', dbNumber: 0, byteOffset: off, bitOffset: bp };
        }
        if (!tc && bp === null) {
            return { area: areaPrefix, dataType: 'Word', dbNumber: 0, byteOffset: off, bitOffset: 0 };
        }
        var tm = { X: 'Bool', B: 'Byte', W: 'Word', D: 'DWord' };
        return {
            area: areaPrefix,
            dataType: tm[tc] || 'Word',
            dbNumber: 0,
            byteOffset: off,
            bitOffset: bp || 0
        };
    }

    return null;
}

// ── Write Value Modal ─────────────────────────────────────────

var writeTargetIndex = -1;

function showWriteValueModal(index) {
    var tag = state.tags[index];
    if (!tag) return;

    if (!state.connected) {
        showToast('PLC is not connected. Please connect first.', 'error');
        return;
    }

    writeTargetIndex = index;
    document.getElementById('writeTagName').textContent = tag.name;
    document.getElementById('writeTagAddr').textContent = tag.address;
    document.getElementById('writeTagCurrent').textContent = 'Current: ' + formatValue(tag.value, tag.quality);
    document.getElementById('writeValueInput').value = '';
    document.getElementById('writeValueModal').classList.add('visible');
    document.getElementById('writeValueInput').focus();
}

function closeWriteValue() {
    document.getElementById('writeValueModal').classList.remove('visible');
    writeTargetIndex = -1;
}

// ── About ─────────────────────────────────────────────────────
function openAbout() {
    document.getElementById('aboutModal').classList.add('visible');
}
function closeAbout() {
    document.getElementById('aboutModal').classList.remove('visible');
}

function confirmWriteValue() {
    var input = document.getElementById('writeValueInput').value.trim();
    if (!input) {
        showToast('Please enter a value', 'error');
        return;
    }
    if (writeTargetIndex < 0) return;

    var tag = state.tags[writeTargetIndex];
    var value;

    try {
        if (tag.dataType === 'Bool') {
            value = input.toLowerCase() === 'true' || input === '1';
        } else if (tag.dataType === 'Real') {
            value = parseFloat(input);
        } else if (['Byte', 'Word', 'DWord'].indexOf(tag.dataType) >= 0) {
            value = input.indexOf('0x') === 0 ? parseInt(input, 16) : parseInt(input);
        } else {
            value = parseInt(input);
        }

        if (isNaN(value) && tag.dataType !== 'Bool') {
            showToast('Cannot parse value: ' + input, 'error');
            return;
        }
    } catch (ex) {
        showToast('Cannot parse value: ' + input, 'error');
        return;
    }

    writeValue(writeTargetIndex, value);
    closeWriteValue();
}

// ── Window Drag ───────────────────────────────────────────────
// 原生标题栏负责拖动窗口，无需自定义处理。

// ── DOM Ready Bindings ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    document.getElementById('btnTheme').addEventListener('click', toggleTheme);

    var btnSidebar = document.getElementById('btnSidebar');
    if (btnSidebar) btnSidebar.addEventListener('click', toggleSidebar);

    // 画面组件属性栏
    var propTag = document.getElementById('propTag');
    if (propTag) propTag.addEventListener('change', function () { updateSelectedProp('tag', this.value); });
    var propLabel = document.getElementById('propLabel');
    if (propLabel) propLabel.addEventListener('input', function () { updateSelectedProp('label', this.value); });
    var propFont = document.getElementById('propFont');
    if (propFont) propFont.addEventListener('change', function () { updateSelectedProp('font', parseInt(this.value) || 14); });

    // Info-card accordions (click header to collapse/expand)
    var heads = document.querySelectorAll('.info-card-head');
    for (var i = 0; i < heads.length; i++) {
        heads[i].addEventListener('click', function () {
            this.parentElement.classList.toggle('collapsed');
        });
    }

    // Group filter + search
    var groupSel = document.getElementById('filterGroup');
    if (groupSel) groupSel.addEventListener('change', applyFilter);
    var searchEl = document.getElementById('filterSearch');
    if (searchEl) searchEl.addEventListener('input', applyFilter);

    // Restore sidebar collapsed state
    if (localStorage.getItem('scada-sidebar') === 'collapsed') {
        document.body.classList.add('sidebar-collapsed');
    }
});

// ── Keyboard Shortcuts ────────────────────────────────────────

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        hideContextMenu();
        if (document.getElementById('tagEditorModal').classList.contains('visible')) {
            closeTagEditor();
        }
        if (document.getElementById('writeValueModal').classList.contains('visible')) {
            closeWriteValue();
        }
        if (document.getElementById('aboutModal').classList.contains('visible')) {
            closeAbout();
        }
    }

    if (e.key === 'Enter') {
        if (document.getElementById('tagEditorModal').classList.contains('visible')) {
            confirmTagEditor();
            e.preventDefault();
        }
        if (document.getElementById('writeValueModal').classList.contains('visible')) {
            confirmWriteValue();
            e.preventDefault();
        }
    }

    if (e.key === 'F5') { connectPlc(); e.preventDefault(); }
    if (e.key === 'F6') { disconnectPlc(); e.preventDefault(); }

    if (e.ctrlKey && e.key === 'n') { showAddTagModal(); e.preventDefault(); }
    if (e.ctrlKey && e.key === 's') { saveConfig(); e.preventDefault(); }
    if (e.ctrlKey && e.key === 'b') { toggleSidebar(); e.preventDefault(); }
});

// ── Click Outside Handlers ────────────────────────────────────

document.addEventListener('click', function (e) {
    var menu = document.getElementById('contextMenu');
    if (menu.classList.contains('visible') && !menu.contains(e.target)) {
        hideContextMenu();
    }
});

document.getElementById('tagEditorModal').addEventListener('click', function (e) {
    if (e.target === e.currentTarget) closeTagEditor();
});
document.getElementById('writeValueModal').addEventListener('click', function (e) {
    if (e.target === e.currentTarget) closeWriteValue();
});
document.getElementById('aboutModal').addEventListener('click', function (e) {
    if (e.target === e.currentTarget) closeAbout();
});

// ══ 画面编辑器 ══════════════════════════════════════════════

window.onScreensChanged = function (screens) {
    state.screens = (screens && Array.isArray(screens)) ? screens : [];
    state.currentScreen = state.screens.length > 0 ? 0 : -1;
    state.selectedWidget = null;
    renderScreens();
};

// ── 视图切换 ────────────────────────────────────────────────
function switchView(view) {
    state.view = view;
    document.getElementById('tableView').style.display = view === 'table' ? '' : 'none';
    document.getElementById('screensView').style.display = view === 'screens' ? 'flex' : 'none';
    document.getElementById('btnViewTable').classList.toggle('active', view === 'table');
    document.getElementById('btnViewScreens').classList.toggle('active', view === 'screens');
}

// ── 画面 CRUD ────────────────────────────────────────────────
function renderScreens() {
    var tabs = document.getElementById('screenTabs');
    tabs.innerHTML = '';
    for (var i = 0; i < state.screens.length; i++) {
        (function (idx) {
            var tab = document.createElement('div');
            tab.className = 'screen-tab' + (idx === state.currentScreen ? ' active' : '');
            tab.textContent = state.screens[idx].name;
            tab.title = '点击切换 · 双击重命名';
            tab.addEventListener('click', function () { selectScreen(idx); });
            tab.addEventListener('dblclick', function () { selectScreen(idx); renameCurrentScreen(); });
            tabs.appendChild(tab);
        })(i);
    }
    renderCanvas();
    renderProps();
}

function selectScreen(i) {
    if (i < 0 || i >= state.screens.length) return;
    state.currentScreen = i;
    state.selectedWidget = null;
    renderScreens();
}

function addScreen() {
    var n = state.screens.length + 1;
    var name = '画面' + n;
    while (state.screens.some(function (s) { return s.name === name; })) n++;
    state.screens.push({ name: name, widgets: [] });
    state.currentScreen = state.screens.length - 1;
    state.selectedWidget = null;
    renderScreens();
    scheduleSaveScreens();
}

function renameCurrentScreen() {
    var screen = state.screens[state.currentScreen];
    if (!screen) return;
    var name = prompt('输入画面名称：', screen.name);
    if (name && name.trim()) {
        screen.name = name.trim();
        renderScreens();
        scheduleSaveScreens();
    }
}

function deleteCurrentScreen() {
    if (state.screens.length === 0) return;
    var screen = state.screens[state.currentScreen];
    if (!screen || !confirm('删除画面 "' + screen.name + '"？')) return;
    state.screens.splice(state.currentScreen, 1);
    if (state.currentScreen >= state.screens.length) state.currentScreen = state.screens.length - 1;
    state.selectedWidget = null;
    renderScreens();
    scheduleSaveScreens();
}

// ── 组件 CRUD ────────────────────────────────────────────────
function defaultWidget(type, id) {
    switch (type) {
        case 'value': return { id: id, type: 'value', label: '', tag: '', x: 120, y: 80, w: 180, h: 64, font: 20 };
        case 'lamp':  return { id: id, type: 'lamp',  label: '', tag: '', x: 400, y: 80, w: 56,  h: 56, font: 11 };
        case 'text':  return { id: id, type: 'text',  label: '文本', tag: '', x: 40,  y: 20, w: 160, h: 30, font: 16 };
    }
}

function getWidget(id) {
    var screen = state.screens[state.currentScreen];
    if (!screen) return null;
    for (var i = 0; i < screen.widgets.length; i++) {
        if (screen.widgets[i].id === id) return screen.widgets[i];
    }
    return null;
}

function addWidget(type) {
    var screen = state.screens[state.currentScreen];
    if (!screen) { showToast('请先添加画面', 'error'); return; }
    var w = defaultWidget(type, 'w' + Date.now().toString(36));
    screen.widgets.push(w);
    state.selectedWidget = w.id;
    renderScreens();
    scheduleSaveScreens();
}

function selectWidget(id) {
    state.selectedWidget = id;
    var widgets = document.querySelectorAll('#screenCanvas .widget');
    for (var i = 0; i < widgets.length; i++) {
        widgets[i].classList.toggle('selected', widgets[i].dataset.id === id);
    }
    renderProps();
}

function deleteSelectedWidget() {
    if (!state.selectedWidget) return;
    var screen = state.screens[state.currentScreen];
    if (!screen) return;
    screen.widgets = screen.widgets.filter(function (w) { return w.id !== state.selectedWidget; });
    state.selectedWidget = null;
    renderScreens();
    scheduleSaveScreens();
}

// ── 画布渲染 ─────────────────────────────────────────────────
function renderCanvas() {
    var canvas = document.getElementById('screenCanvas');
    var empty = document.getElementById('screenEmpty');
    canvas.innerHTML = '';
    empty.style.display = state.screens.length === 0 ? '' : 'none';
    var screen = state.screens[state.currentScreen];
    if (!screen) return;
    for (var i = 0; i < screen.widgets.length; i++) {
        canvas.appendChild(renderWidget(screen.widgets[i]));
    }
}

function renderWidget(w) {
    var el = document.createElement('div');
    el.className = 'widget widget-' + w.type + (state.selectedWidget === w.id ? ' selected' : '');
    el.dataset.id = w.id;
    el.style.left = (w.x || 0) + 'px';
    el.style.top = (w.y || 0) + 'px';
    el.style.width = (w.w || 100) + 'px';
    el.style.height = (w.h || 50) + 'px';

    if (w.type === 'value') {
        el.innerHTML = '<div class="widget-label"></div><div class="widget-value-text"></div><div class="widget-resize-handle"></div>';
    } else if (w.type === 'lamp') {
        el.innerHTML = '<div class="widget-lamp-circle"></div><div class="widget-lamp-label"></div><div class="widget-resize-handle"></div>';
    } else if (w.type === 'text') {
        el.innerHTML = '<div class="widget-text-content"></div><div class="widget-resize-handle"></div>';
    }
    updateWidgetDom(w, el);
    return el;
}

// ── 组件实时数据/样式刷新 ────────────────────────────────────
function findTagIndex(name) {
    for (var i = 0; i < state.tags.length; i++) {
        if (state.tags[i].name === name) return i;
    }
    return -1;
}

function updateWidgetDom(w, el) {
    if (!el) return;

    if (w.type === 'value') {
        var tag = findTagIndex(w.tag) >= 0 ? state.tags[findTagIndex(w.tag)] : null;
        var labelEl = el.querySelector('.widget-label');
        if (labelEl) labelEl.textContent = w.label || (tag ? tag.name : '未绑定');
        var valEl = el.querySelector('.widget-value-text');
        if (valEl) {
            var quality = tag ? tag.quality : 'Unknown';
            valEl.textContent = formatValue(tag ? tag.value : null, quality);
            valEl.className = 'widget-value-text ' +
                (quality === 'Bad' ? 'bad' : quality === 'Unknown' ? 'unknown' : '');
            valEl.style.fontSize = (w.font || 20) + 'px';
        }
    } else if (w.type === 'lamp') {
        var tag2 = findTagIndex(w.tag) >= 0 ? state.tags[findTagIndex(w.tag)] : null;
        var circ = el.querySelector('.widget-lamp-circle');
        if (circ) {
            circ.className = 'widget-lamp-circle';
            if (tag2 && tag2.quality === 'Good' && typeof tag2.value === 'boolean') {
                circ.classList.add(tag2.value ? 'on' : 'off');
            }
        }
        var lbl = el.querySelector('.widget-lamp-label');
        if (lbl) lbl.textContent = w.label || (tag2 ? tag2.name : '未绑定');
    } else if (w.type === 'text') {
        var tc = el.querySelector('.widget-text-content');
        if (tc) {
            tc.textContent = w.label || '';
            tc.style.fontSize = (w.font || 16) + 'px';
        }
    }
}

function updateScreenWidgets() {
    var screen = state.screens[state.currentScreen];
    if (!screen || state.view !== 'screens') return;
    var canvas = document.getElementById('screenCanvas');
    for (var i = 0; i < screen.widgets.length; i++) {
        var el = canvas.querySelector('.widget[data-id="' + screen.widgets[i].id + '"]');
        if (el) updateWidgetDom(screen.widgets[i], el);
    }
}

// ── 属性栏 ───────────────────────────────────────────────────
function renderProps() {
    var el = document.getElementById('widgetProps');
    var btnDel = document.getElementById('btnDeleteWidget');
    var w = state.selectedWidget ? getWidget(state.selectedWidget) : null;
    if (!w) {
        el.style.display = 'none';
        btnDel.disabled = true;
        return;
    }
    el.style.display = 'flex';
    btnDel.disabled = false;

    var sel = document.getElementById('propTag');
    var html = '<option value="">未绑定</option>';
    for (var i = 0; i < state.tags.length; i++) {
        var selAttr = w.tag === state.tags[i].name ? ' selected' : '';
        html += '<option value="' + esc(state.tags[i].name) + '"' + selAttr + '>' + esc(state.tags[i].name) + '</option>';
    }
    sel.innerHTML = html;

    document.getElementById('propLabel').value = w.label || '';
    document.getElementById('propFont').value = w.font || 14;
}

function updateSelectedProp(key, value) {
    var w = state.selectedWidget ? getWidget(state.selectedWidget) : null;
    if (!w) return;
    w[key] = value;
    var el = document.querySelector('#screenCanvas .widget[data-id="' + w.id + '"]');
    if (el) updateWidgetDom(w, el);
    scheduleSaveScreens();
}

// ── 拖拽移动 / 缩放 ──────────────────────────────────────────
var dragState = null;

(function setupCanvasInteractions() {
    var canvas = document.getElementById('screenCanvas');
    canvas.addEventListener('mousedown', function (e) {
        var wEl = e.target.closest('.widget');
        if (!wEl) { selectWidget(null); return; }
        var handle = e.target.closest('.widget-resize-handle');
        var id = wEl.dataset.id;
        selectWidget(id);
        var w = getWidget(id);
        if (!w) return;
        e.preventDefault();
        dragState = {
            id: id,
            startX: e.clientX,
            startY: e.clientY,
            origX: w.x, origY: w.y, origW: w.w, origH: w.h,
            mode: handle ? 'resize' : 'move'
        };
    });

    document.addEventListener('mousemove', function (e) {
        if (!dragState) return;
        var w = getWidget(dragState.id);
        if (!w) { dragState = null; return; }
        var dx = e.clientX - dragState.startX;
        var dy = e.clientY - dragState.startY;
        if (dragState.mode === 'move') {
            w.x = Math.max(0, Math.round(dragState.origX + dx));
            w.y = Math.max(0, Math.round(dragState.origY + dy));
        } else {
            w.w = Math.max(40, Math.round(dragState.origW + dx));
            w.h = Math.max(24, Math.round(dragState.origH + dy));
        }
        var el = canvas.querySelector('.widget[data-id="' + dragState.id + '"]');
        if (el) {
            el.style.left = w.x + 'px';
            el.style.top = w.y + 'px';
            el.style.width = w.w + 'px';
            el.style.height = w.h + 'px';
        }
    });

    document.addEventListener('mouseup', function () {
        if (dragState) {
            dragState = null;
            scheduleSaveScreens();
        }
    });
})();

// ── 自动保存（防抖） ─────────────────────────────────────────
var saveScreensTimer = null;
function scheduleSaveScreens() {
    if (saveScreensTimer) clearTimeout(saveScreensTimer);
    saveScreensTimer = setTimeout(function () {
        postToCSharp({ action: 'saveScreens', screens: state.screens });
    }, 500);
}

// ── Utility ───────────────────────────────────────────────────

function esc(str) {
    if (str === null || str === undefined) return '';
    var div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

function hexToRgba(hex, alpha) {
    var r = parseInt(hex.slice(1, 3), 16);
    var g = parseInt(hex.slice(3, 5), 16);
    var b = parseInt(hex.slice(5, 7), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
}
