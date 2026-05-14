/**
 * 交通预测模块 — 传感器预测 + 路段可视化 + 拥堵热点
 * 依赖：map.js 先加载（提供 window.map, window.mapFunctions）
 */

const TRAFFIC_API_BASE = '/api';
let latestPrediction = null;

// ── 工具函数（委托给 map.js 共享函数） ──
const fmt = (v, d) => window.mapFunctions?.formatNumber(v, d) ?? Number(v).toFixed(d || 2);
const fmtMin = (s) => window.mapFunctions?.formatMinutes(s) ?? ((s / 60).toFixed(1) + ' min');
const speedCls = (s) => window.mapFunctions?.getSpeedClass(s) ?? (s >= 60 ? 'speed-excellent' : s >= 40 ? 'speed-good' : s >= 20 ? 'speed-fair' : 'speed-poor');
const speedIco = (s) => window.mapFunctions?.getSpeedIcon(s) ?? (s >= 60 ? '🟢' : s >= 40 ? '🟡' : s >= 20 ? '🟠' : '🔴');
const bdownPct = (c, t) => t > 0 ? (c / t) * 100 : 0;


// ═══════════════════════════════════════════════
//  SegmentTrafficVisualizer — 路段级交通可视化
// ═══════════════════════════════════════════════

class SegmentTrafficVisualizer {
    constructor(map) {
        this._map = map;
        this.layerGroup = null;
        this.hotspotsGroup = null;
        this.legendControl = null;
    }

    /** 绘制路段交通预测 */
    async drawSegmentTraffic(segments, options = {}) {
        const map = this._map;
        if (!map) { console.error('Map not available'); return; }

        this.clear();

        const config = { showLabels: false, opacity: 0.78, weight: 1, ...options };
        this.layerGroup = L.layerGroup();

        const colors = { smooth: '#34a853', moderate: '#fbbc04', congested: '#ea4335', severe: '#dc2626' };

        segments.forEach(seg => {
            const speed = seg.speed || 0;
            let status, color, weight;
            if (speed >= 60) { status = 'smooth'; color = colors.smooth; weight = 3; }
            else if (speed >= 40) { status = 'moderate'; color = colors.moderate; weight = 3; }
            else if (speed >= 20) { status = 'congested'; color = colors.congested; weight = 4; }
            else { status = 'severe'; color = colors.severe; weight = 4; }

            const polyline = L.polyline(seg.coordinates, {
                color, weight: weight * config.weight, opacity: config.opacity,
                smoothFactor: 1, interactive: false
            });
            this.layerGroup.addLayer(polyline);
        });

        this.layerGroup.addTo(map);
        this._addLegend(map);
    }

    /** 绘制拥堵热点 */
    drawCongestionHotspots(hotspots) {
        const map = this._map;
        if (!map) return;

        this.clearHotspots();
        this.hotspotsGroup = L.layerGroup();

        hotspots.forEach((h, i) => {
            const color = h.status === '严重拥堵' ? '#dc2626' : h.status === '拥堵' ? '#ea4335' : h.status === '缓行' ? '#fbbc04' : '#34a853';

            L.polyline(h.coordinates, { color, weight: (6 - i) || 2, opacity: 0.9, dashArray: h.status === '严重拥堵' ? '10,10' : null })
                .bindPopup(this._hotspotPopup(h, i + 1)).addTo(this.hotspotsGroup);

            const ctr = h.coordinates.reduce((a, c) => [a[0] + c[0], a[1] + c[1]], [0, 0]);
            const center = [ctr[0] / h.coordinates.length, ctr[1] / h.coordinates.length];

            L.circleMarker(center, { radius: 8 + i, fillColor: color, color: '#fff', weight: 2, fillOpacity: 0.8 })
                .bindPopup(this._hotspotPopup(h, i + 1)).addTo(this.hotspotsGroup);
        });

        this.hotspotsGroup.addTo(map);
    }

    clear() {
        if (this.layerGroup && this._map) { this._map.removeLayer(this.layerGroup); this.layerGroup = null; }
        if (this.legendControl && this._map) { this._map.removeControl(this.legendControl); this.legendControl = null; }
    }

    clearHotspots() {
        if (this.hotspotsGroup && this._map) { this._map.removeLayer(this.hotspotsGroup); this.hotspotsGroup = null; }
    }

    clearAll() { this.clear(); this.clearHotspots(); }

    fitToTrafficBounds() {
        try {
            if (this.layerGroup && this._map && typeof this.layerGroup.getBounds === 'function') {
                const layers = this.layerGroup.getLayers();
                if (layers && layers.length > 0) {
                    const bounds = this.layerGroup.getBounds();
                    if (bounds && bounds.isValid()) this._map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
                }
            }
        } catch (e) { console.warn('fitToTrafficBounds error:', e.message); }
    }

    _addLegend(map) {
        const LegendCtrl = L.Control.extend({
            onAdd: () => {
                const div = L.DomUtil.create('div', 'simple-legend-container');
                div.innerHTML = `<div class="simple-traffic-legend">
                    <div class="legend-header">Traffic Status</div>
                    <div class="legend-items">
                        <div class="legend-item"><div class="legend-line-smooth"></div><span>Smooth</span></div>
                        <div class="legend-item"><div class="legend-line-moderate"></div><span>Moderate</span></div>
                        <div class="legend-item"><div class="legend-line-congested"></div><span>Congested</span></div>
                        <div class="legend-item"><div class="legend-line-severe"></div><span>Severe</span></div>
                    </div></div>`;
                return div;
            }
        });
        if (this.legendControl) map.removeControl(this.legendControl);
        this.legendControl = new LegendCtrl({ position: 'bottomright' }).addTo(map);
    }

    _hotspotPopup(h, rank) {
        return L.popup({ maxWidth: 350 }).setContent(`
            <div style="min-width:200px;font-size:13px;line-height:1.6;">
                <b>🔥 TOP ${rank}</b> ${h.status}<br>
                道路: ${h.road_name || '-'}<br>
                预测速度: ${h.speed.toFixed(1)} km/h<br>
                路段长度: ${(h.length / 1000).toFixed(1)} km
            </div>`);
    }
}


// ═══════════════════════════════════════════════
//  交通预测模块
// ═══════════════════════════════════════════════

function initPredictionModule() {
    document.getElementById('btn-predict')?.addEventListener('click', handleTrafficPrediction);
    document.getElementById('btn-predictive-route')?.addEventListener('click', handlePredictiveRoutePlanning);
    document.getElementById('btn-segment-prediction')?.addEventListener('click', handleSegmentTrafficPrediction);
    document.getElementById('btn-show-hotspots')?.addEventListener('click', handleShowCongestionHotspots);
    document.getElementById('btn-clear-prediction')?.addEventListener('click', clearTrafficPrediction);
    console.log('Prediction module initialized');
}

// ── API helpers ──

async function fetchTrafficPrediction(step, topK = 12) {
    const resp = await fetch(`${TRAFFIC_API_BASE}/traffic/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step, top_k: topK })
    });
    const result = await resp.json();
    if (!resp.ok || !result.success) throw new Error(result.error || 'Prediction failed');
    if (!result.prediction) throw new Error('Empty prediction data');
    return result.prediction;
}

async function ensurePrediction(step, opts = {}) {
    if (!opts.forceRefresh && latestPrediction && Number(latestPrediction.selected_step) === Number(step)) {
        return latestPrediction;
    }
    const pred = await fetchTrafficPrediction(step, 12);
    latestPrediction = pred;
    renderPredictionResult(pred);
    window.mapFunctions?.drawPredictionSensors?.(pred.sensor_predictions, pred.selected_horizon_minutes);
    return pred;
}

// ── Button handlers ──

async function handleTrafficPrediction() {
    const btn = document.getElementById('btn-predict');
    const step = parseInt(document.getElementById('prediction-step').value, 10);
    hidePredError();
    btn.disabled = true; btn.textContent = 'Predicting...';
    try {
        await ensurePrediction(step, { forceRefresh: true });
    } catch (e) {
        showPredError(e.message);
    } finally {
        btn.disabled = false; btn.textContent = '生成交通预测';
    }
}

async function handlePredictiveRoutePlanning() {
    const btn = document.getElementById('btn-predictive-route');
    const step = parseInt(document.getElementById('prediction-step').value, 10);
    const sp = window.mapFunctions?.getStartPoint?.();
    const ep = window.mapFunctions?.getEndPoint?.();

    if (!sp?.lat || !ep?.lat) { showPredError('请先选择起点和终点'); return; }
    hidePredError();
    btn.disabled = true; btn.textContent = 'Re-planning...';

    try {
        await ensurePrediction(step, { forceRefresh: true });

        const resp = await fetch(`${TRAFFIC_API_BASE}/traffic/predictive-route`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start_lat: parseFloat(sp.lat), start_lon: parseFloat(sp.lng),
                end_lat: parseFloat(ep.lat), end_lon: parseFloat(ep.lng),
                step, weight_type: 'time', congestion_top_n: 350
            })
        });
        const result = await resp.json();
        if (!resp.ok || !result.success) throw new Error(result.error || 'Re-planning failed');

        window.mapFunctions?.drawCongestionSegments?.(result.congestion?.segments || []);
        window.mapFunctions?.drawRoute?.(result.predictive_route.coords, { color: '#ef4444', weight: 6, opacity: 0.9 });
        renderPredictiveImpact(result.comparison || {});
        renderRouteSummary(result.predictive_route);
    } catch (e) {
        showPredError(e.message);
    } finally {
        btn.disabled = false; btn.textContent = '预测拥堵重规划路径';
    }
}

async function handleSegmentTrafficPrediction() {
    if (!window.segmentVisualizer && window.map) {
        window.segmentVisualizer = new SegmentTrafficVisualizer(window.map);
    }
    const btn = document.getElementById('btn-segment-prediction');
    const step = parseInt(document.getElementById('prediction-step').value, 10);
    hidePredError();
    btn.disabled = true; btn.textContent = 'Predicting...';

    try {
        const ts = Date.now();
        const resp = await fetch(`/api/traffic/segments?step=${step}&t=${ts}`, { cache: 'no-store' });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'Segment prediction failed');

        if (!window.segmentVisualizer && window.map) {
            window.segmentVisualizer = new SegmentTrafficVisualizer(window.map);
        }
        if (window.segmentVisualizer) {
            await window.segmentVisualizer.drawSegmentTraffic(data.segments);
            window.segmentVisualizer.fitToTrafficBounds();
        }
        displaySegmentTrafficStats(data.stats);
    } catch (e) {
        showPredError(e.message);
    } finally {
        btn.disabled = false; btn.textContent = '路段级交通预测';
    }
}

async function handleShowCongestionHotspots() {
    const btn = document.getElementById('btn-show-hotspots');
    hidePredError();
    btn.disabled = true; btn.textContent = 'Loading...';

    try {
        const resp = await fetch('/api/traffic/hotspots?top_k=10');
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'Hotspot query failed');

        if (!window.segmentVisualizer && window.map) {
            window.segmentVisualizer = new SegmentTrafficVisualizer(window.map);
        }
        window.segmentVisualizer?.drawCongestionHotspots(data.hotspots);
        displayHotspotInfo(data.hotspots);
    } catch (e) {
        showPredError(e.message);
    } finally {
        btn.disabled = false; btn.textContent = '显示拥堵热点';
    }
}

// ── Rendering ──

function renderPredictionResult(pred) {
    const s = pred.summary || {};
    document.getElementById('pred-horizon').textContent = `+${pred.selected_horizon_minutes} min`;
    document.getElementById('pred-avg-speed').textContent = `${fmt(s.avg_speed_kmh)} km/h`;
    document.getElementById('pred-speed-range').textContent = `${fmt(s.min_speed_kmh, 1)} ~ ${fmt(s.max_speed_kmh, 1)}`;
    document.getElementById('pred-congestion').textContent = `${s.low_speed_count ?? 0} / ${pred.num_nodes}`;

    const tbody = document.getElementById('prediction-topk-body');
    tbody.innerHTML = (pred.top_congested || []).map((item, idx) =>
        `<tr><td>${idx + 1}</td><td>${item.sensor_id}</td><td>${item.fwy ? 'I-' + item.fwy : '-'}</td><td>${item.dir || '-'}</td><td>${Number(item.pred_speed_kmh).toFixed(2)}</td></tr>`
    ).join('');
    document.getElementById('prediction-result').classList.remove('hidden');
}

function renderRouteSummary(route) {
    if (!route) return;
    document.getElementById('stat-distance').textContent =
        route.distance_km >= 1 ? `${Number(route.distance_km).toFixed(2)} km` : `${Number(route.distance_m).toFixed(0)} m`;
    document.getElementById('stat-time').textContent =
        route.time_min >= 60 ? `${Math.floor(route.time_min / 60)}h${(route.time_min % 60).toFixed(0)}m` : `${Number(route.time_min).toFixed(1)} min`;
    ['stat-energy-item', 'stat-carbon-item', 'stat-comfort-item', 'stat-constraint-item'].forEach(id => {
        document.getElementById(id)?.classList.add('hidden');
    });
    document.getElementById('result').classList.remove('hidden');
}

function renderPredictiveImpact(cmp) {
    const panel = document.getElementById('predictive-impact');
    if (!panel) return;
    document.getElementById('impact-baseline-time').textContent = fmtMin(cmp.baseline_time_s);
    document.getElementById('impact-predictive-time').textContent = fmtMin(cmp.predictive_time_s);

    const tc = Number(cmp.time_change_s || 0);
    const tp = Number(cmp.time_change_percent || 0);
    const dc = Number(cmp.distance_change_km || 0);
    document.getElementById('impact-time-change').textContent = `${tc > 0 ? '+' : ''}${tc.toFixed(1)}s (${tp > 0 ? '+' : ''}${tp.toFixed(2)}%)`;
    document.getElementById('impact-distance-change').textContent = `${dc > 0 ? '+' : ''}${dc.toFixed(3)} km`;

    const note = document.getElementById('impact-note');
    if (cmp.reroute_reason === 'no_predicted_congestion') note.textContent = '未检测到预测拥堵，路径与基线一致。';
    else if (cmp.predictive_better) note.textContent = '预测路径优于基线：已避开预测拥堵路段。';
    else if (tc === 0) note.textContent = '预测路径与基线相似：当前预测拥堵对该OD影响有限。';
    else note.textContent = '预测路径未优于基线：路网整体较通畅或拥堵分布有限。';
    panel.classList.remove('hidden');
}

function displaySegmentTrafficStats(stats) {
    let panel = document.getElementById('segment-traffic-stats');
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'segment-traffic-stats';
        panel.className = 'segment-stats hidden';
        document.getElementById('panel').appendChild(panel);
    }

    const s = stats.congestion_counts || { smooth: 0, moderate: 0, congested: 0, severe: 0 };
    panel.innerHTML = `<div class="segment-stats-header">
        <h3>Traffic Prediction Statistics</h3>
        <button class="close-btn" onclick="document.getElementById('segment-traffic-stats').classList.add('hidden')">✕</button>
    </div>
    <div class="stats-grid">
        <div class="stat-card"><span class="stat-label">Total Segments</span><span class="stat-value">${stats.total_segments.toLocaleString()}</span></div>
        <div class="stat-card"><span class="stat-label">Sensors</span><span class="stat-value">${stats.total_sensors.toLocaleString()}</span></div>
        <div class="stat-card"><span class="stat-label">Coverage</span><span class="stat-value">${(stats.coverage_ratio * 100).toFixed(1)}%</span></div>
    </div>
    <div class="stats-grid">
        <div class="stat-card"><span class="stat-label">Avg Speed</span><span class="stat-value ${speedCls(stats.avg_speed)}">${stats.avg_speed.toFixed(1)} km/h</span></div>
        <div class="stat-card"><span class="stat-label">Range</span><span class="stat-value">${stats.min_speed.toFixed(1)} ~ ${stats.max_speed.toFixed(1)} km/h</span></div>
        <div class="stat-card"><span class="stat-label">Congestion Ratio</span><span class="stat-value">${(stats.congestion_ratio * 100).toFixed(1)}%</span></div>
    </div>
    <div class="congestion-breakdown"><h4>Distribution</h4><div class="breakdown-grid">
        <div class="breakdown-item smooth"><div class="breakdown-bar" style="width:${bdownPct(s.smooth, stats.total_segments)}%"></div><span>${s.smooth} Smooth</span></div>
        <div class="breakdown-item moderate"><div class="breakdown-bar" style="width:${bdownPct(s.moderate, stats.total_segments)}%"></div><span>${s.moderate} Moderate</span></div>
        <div class="breakdown-item congested"><div class="breakdown-bar" style="width:${bdownPct(s.congested, stats.total_segments)}%"></div><span>${s.congested} Congested</span></div>
        <div class="breakdown-item severe"><div class="breakdown-bar" style="width:${bdownPct(s.severe, stats.total_segments)}%"></div><span>${s.severe} Severe</span></div>
    </div></div>`;
    panel.classList.remove('hidden');
}

function displayHotspotInfo(hotspots) {
    let panel = document.getElementById('hotspot-info-panel');
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'hotspot-info-panel';
        panel.className = 'hotspot-panel hidden';
        document.getElementById('panel').appendChild(panel);
    }
    panel.innerHTML = `<div class="hotspot-panel-header">
        <h3>TOP ${hotspots.length} Congestion Hotspots</h3>
        <button class="close-btn" onclick="document.getElementById('hotspot-info-panel').classList.add('hidden')">✕</button>
    </div>
    <div class="hotspot-list">${hotspots.map((h, i) => `
        <div class="hotspot-item">
            <div class="hotspot-rank">#${i + 1}</div>
            <div class="hotspot-details">
                <div class="hotspot-title">${speedIco(h.speed)} ${h.road_name || '-'} <span class="status-badge status-${h.status}">${h.status}</span></div>
                <div class="hotspot-metrics">
                    <div><span>Speed:</span><span class="${speedCls(h.speed)}">${h.speed.toFixed(1)} km/h</span></div>
                    <div><span>Length:</span><span>${(h.length / 1000).toFixed(1)} km</span></div>
                </div>
            </div>
        </div>`).join('')}</div>`;
    panel.classList.remove('hidden');
}

function clearTrafficPrediction() {
    latestPrediction = null;
    document.getElementById('prediction-result').classList.add('hidden');
    document.getElementById('predictive-impact')?.classList.add('hidden');
    document.getElementById('segment-traffic-stats')?.classList.add('hidden');
    document.getElementById('hotspot-info-panel')?.classList.add('hidden');
    window.mapFunctions?.clearPredictionLayer?.();
    window.mapFunctions?.clearCongestionLayer?.();
    window.segmentVisualizer?.clearAll();
    hidePredError();
}

function showPredError(msg) {
    const el = document.getElementById('error');
    el.textContent = msg; el.classList.remove('hidden');
}
function hidePredError() { document.getElementById('error').classList.add('hidden'); }


// ═══════════════════════════════════════════════
//  初始化
// ═══════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    const init = () => {
        if (!window.map) { setTimeout(init, 100); return; }
        window.segmentVisualizer = new SegmentTrafficVisualizer(window.map);
        initPredictionModule();
        console.log('Prediction modules initialized');
    };
    init();
});

window.SegmentTrafficVisualizer = SegmentTrafficVisualizer;
window.predictionFunctions = {
    run: handleTrafficPrediction,
    runPredictiveRoute: handlePredictiveRoutePlanning,
    runSegmentPrediction: handleSegmentTrafficPrediction,
    showHotspots: handleShowCongestionHotspots,
    clear: clearTrafficPrediction
};
