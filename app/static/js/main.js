function getI18nMessages() {
    const element = document.getElementById('i18n-messages');
    if (!element) {
        return {};
    }
    try {
        return JSON.parse(element.textContent) || {};
    } catch (error) {
        return {};
    }
}

function t(key, fallback) {
    const messages = getI18nMessages();
    return messages[key] || fallback || key;
}

function stateLabel(state) {
    return t(`ups.state.${state}`, state);
}

function normalizedKey(value) {
    return String(value || '').toLowerCase();
}

function batteryStatusLabel(status) {
    const key = normalizedKey(status);
    return t(`ups.battery_status.${key}`, status || t('ups.battery_status.unknown', 'Unknown'));
}

function directionLabel(direction) {
    const key = normalizedKey(direction);
    return t(`ups.direction.${key}`, direction || '');
}

function overviewSummary(data) {
    const direction = normalizedKey(data.battery_direction);
    const status = normalizedKey(data.battery_status);

    if (data.ac && direction === 'charging') {
        return t('ups.summary.charging', 'Battery is charging from external power');
    }
    if (!data.ac && direction === 'discharging') {
        return t('ups.summary.discharging', 'Battery is powering the load');
    }
    if (status === 'full') {
        return t('ups.summary.full', 'Battery is fully charged');
    }
    if (status === 'critical') {
        return t('ups.summary.critical', 'Power needs attention and fast charging');
    }
    return t('ups.summary.stable', 'Battery state is stable');
}

async function updateData() {
    const title = document.getElementById('status-title');
    const hasLiveTargets = document.querySelector('[data-live]') || document.getElementById('battery-bar');
    if (!hasLiveTargets) {
        return;
    }

    try {
        const response = await fetch('/api/data');
        if (!response.ok) throw new Error('Network error');
        const data = await response.json();
        const statusText = stateLabel(data.state);

        if (title) {
            title.innerText = title.closest('.ups-widget') ? statusText : `${statusText} (${data.percent}%)`;
            title.className = data.state;
        }

        const bar = document.getElementById('battery-bar');
        if (bar) {
            bar.style.width = data.percent + '%';
            bar.style.background = data.color;
        }

        const gauge = document.getElementById('battery-gauge');
        if (gauge) {
            gauge.style.setProperty('--battery-level', data.percent + '%');
            gauge.style.setProperty('--battery-color', data.color);
        }

        for (const element of document.querySelectorAll('[style*="--battery-level"]')) {
            element.style.setProperty('--battery-level', data.percent + '%');
            element.style.setProperty('--battery-color', data.color);
        }

        for (const pill of document.querySelectorAll('[data-battery-status-pill]')) {
            const statusClass = normalizedKey(data.battery_status) || 'unknown';
            pill.className = `ups-overview-pill battery-status-${statusClass}`;
        }

        const batteryPercent = document.getElementById('battery-percent-widget');
        if (batteryPercent) {
            batteryPercent.innerText = data.percent + '%';
        }

        const acStatus = document.getElementById('ac-status');
        if (acStatus) {
            acStatus.style.color = data.ac ? 'var(--green)' : 'var(--red)';
        }

        const elements = {
            'val-v': Number(data.v).toFixed(2) + 'V',
            'val-i': Number(data.i).toFixed(0) + 'mA',
            'ac-status': data.ac ? t('ups.ac_ok', 'AC OK') : t('ups.ac_lost', 'AC LOST'),
            'cpu-temp': Number(data.cpu_temp).toFixed(1),
            'ram-info': `${Number(data.ram_used).toFixed(1)}MB (${Number(data.ram_percent).toFixed(1)}%)`
        };

        const liveValues = {
            state: statusText,
            ac: data.ac ? t('ups.ac_ok', 'AC OK') : t('ups.ac_lost', 'AC LOST'),
            'battery-status': batteryStatusLabel(data.battery_status),
            percent: data.percent + '%',
            voltage: Number(data.v).toFixed(2) + 'V',
            current: Number(data.i).toFixed(0) + 'mA',
            cpu: Number(data.cpu_temp).toFixed(1),
            'cpu-full': `${Number(data.cpu_temp).toFixed(1)}°C`,
            ram: `${Number(data.ram_used).toFixed(1)}MB (${Number(data.ram_percent).toFixed(1)}%)`,
            'overview-current': data.current_label || `${Number(data.i).toFixed(0)}mA`,
            'overview-direction': directionLabel(data.battery_direction),
            'overview-load': data.ac ? t('ups.load.line', 'UPS output') : t('ups.load.battery', 'Battery load'),
            'overview-mains': data.ac ? t('ups.mains.online', '220 V online') : t('ups.mains.lost', '220 V lost'),
            'overview-mode': data.ac ? t('ups.mode.line', 'Line mode') : t('ups.mode.backup', 'Battery backup'),
            'overview-power': data.power_label || '',
            'overview-route': data.ac ? t('ups.route.charger', 'Battery to charger') : t('ups.route.load', 'Battery to load'),
            'overview-summary': overviewSummary(data),
            'wifi-ssid': data.connected_ssid_label || '',
            'portal-mode': data.portal_mode_label || '',
            'wifi-ip': data.ip_address_label || ''
        };

        for (const [key, value] of Object.entries(liveValues)) {
            for (const element of document.querySelectorAll(`[data-live="${key}"]`)) {
                element.innerText = value;
            }
        }

        for (const [id, value] of Object.entries(elements)) {
            const element = document.getElementById(id);
            if (element) element.innerText = value;
        }
    } catch (error) {
        console.error('Update error:', error);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    updateData();
    setInterval(updateData, 2000);
});
