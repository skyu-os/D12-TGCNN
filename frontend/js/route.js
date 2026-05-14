/**
 * 路径规划交互逻辑
 * 处理用户输入、API调用和结果展示
 */

// API 基础路径
const API_BASE = '/api';

// 当前路径规划状态
let currentRoute = null;
let allRoutes = [];
let selectedRouteIndex = 0;

/**
 * 初始化路由模块
 */
function initRouteModule() {
    // 绑定按钮事件
    const routeBtn = document.getElementById('btn-route');
    const resetBtn = document.getElementById('btn-reset');
    
    if (routeBtn) {
        routeBtn.addEventListener('click', handleRouteCalculation);
    }
    
    if (resetBtn) {
        resetBtn.addEventListener('click', handleReset);
    }
    
    // 监听优化模式变化
    const modeSelect = document.getElementById('optimization-mode');
    const vehicleSelect = document.getElementById('vehicle-type');
    const timeSlider = document.getElementById('time-of-day');
    const hourLabel = document.getElementById('hour-label');

    // Hour slider → update label
    if (timeSlider && hourLabel) {
        const hourNames = {0:'0:00 深夜',1:'1:00',2:'2:00',3:'3:00',4:'4:00',5:'5:00',6:'6:00 清晨',7:'7:00 早高峰',8:'8:00 早高峰',9:'9:00',10:'10:00',11:'11:00',12:'12:00 正常',13:'13:00',14:'14:00',15:'15:00',16:'16:00',17:'17:00 晚高峰',18:'18:00 晚高峰',19:'19:00',20:'20:00',21:'21:00',22:'22:00 夜间',23:'23:00 深夜'};
        timeSlider.addEventListener('input', () => {
            const h = parseInt(timeSlider.value);
            hourLabel.textContent = hourNames[h] || (h + ':00');
            if (currentRoute) handleRouteCalculation();
        });
    }

    const selectors = [modeSelect, objectiveSelect, vehicleSelect];
    selectors.forEach(select => {
        if (select) {
            select.addEventListener('change', () => {
                updateUIForMode();
                if (currentRoute) handleRouteCalculation();
            });
        }
    });

    // Time slider also triggers recalculation
    if (timeSlider) {
        timeSlider.addEventListener('change', () => {
            updateUIForMode();
            if (currentRoute) handleRouteCalculation();
        });
    }
    
    console.log('✅ 路径规划模块初始化完成');
}

/**
 * 更新UI显示状态
 */
function updateUIForMode() {
    const mode = document.getElementById('optimization-mode').value;
    const vehicleSection = document.getElementById('vehicle-section');
    const timeSection = document.getElementById('time-section');

    // Full mode always shows all options
    vehicleSection.classList.toggle('hidden', mode === 'standard');
    timeSection.classList.toggle('hidden', mode === 'standard');
}

/**
 * 处理路径计算
 */
async function handleRouteCalculation() {
    // 隐藏旧结果和错误
    hideError();
    hideResult();

    // 获取起点和终点
    const startPoint = window.mapFunctions.getStartPoint();
    const endPoint = window.mapFunctions.getEndPoint();

    if (!startPoint.lat || !startPoint.lng || !endPoint.lat || !endPoint.lng) {
        showError('请先在地图上选择起点和终点');
        return;
    }

    // 显示加载状态
    showLoading();

    try {
        const mode = document.getElementById('optimization-mode').value;
        const requestData = {
            start_lat: parseFloat(startPoint.lat),
            start_lon: parseFloat(startPoint.lng),
            end_lat: parseFloat(endPoint.lat),
            end_lon: parseFloat(endPoint.lng),
            mode: mode,
            vehicle_type: document.getElementById('vehicle-type').value,
            hour: parseInt(document.getElementById('time-of-day').value || 12),
        };

        console.log('Multi-route request:', requestData);

        const response = await fetch(`${API_BASE}/routes/compare`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        const result = await response.json();
        hideLoading();

        if (!response.ok || !result.success) {
            throw new Error(result.error || '路径规划失败');
        }

        // 去重：相同 path 的路线合并标签
        const seen = new Map();
        allRoutes = [];
        for (const r of result.routes) {
            const key = JSON.stringify(r.path);
            if (seen.has(key)) {
                seen.get(key).label += ' / ' + r.label;
            } else {
                seen.set(key, r);
                allRoutes.push(r);
            }
        }

        selectedRouteIndex = 0;
        currentRoute = allRoutes[0];

        // 画第一条路线
        window.mapFunctions.drawRoute(currentRoute.coords);

        // 显示多方案卡片
        showMultiRouteResult(allRoutes, mode);

        console.log('Routes computed:', allRoutes.length);

    } catch (error) {
        hideLoading();
        showError(error.message || '网络请求失败');
        console.error('Route planning failed:', error);
    }
}

/**
 * 显示多方案路线卡片
 */
function showMultiRouteResult(routes, mode) {
    const resultDiv = document.getElementById('result');
    const cardsDiv = document.getElementById('route-cards');

    const icons = { time: '⚡', distance: '📍', energy: '🔋', carbon: '🌿', comfort: '🛣️', balanced: '⭐' };
    const colors = { time: '#ef4444', distance: '#f59e0b', energy: '#22c55e', carbon: '#10b981', comfort: '#3b82f6', balanced: '#8b5cf6' };

    cardsDiv.innerHTML = routes.map((r, i) => {
        const t = r.time_min >= 60
            ? Math.floor(r.time_min / 60) + 'h' + (r.time_min % 60).toFixed(0) + 'm'
            : r.time_min.toFixed(1) + 'min';
        const d = r.distance_km >= 1 ? r.distance_km.toFixed(1) + 'km' : r.distance_m.toFixed(0) + 'm';
        const e = r.energy_mj ? r.energy_mj.toFixed(1) + 'MJ' : '-';
        const c = r.carbon_kg ? r.carbon_kg.toFixed(1) + 'kg' : '-';
        const f = r.avg_comfort ? (r.avg_comfort * 100).toFixed(0) + '%' : '-';
        const active = i === 0 ? ' active' : '';

        return `<div class="route-card${active}" data-index="${i}"
            style="border-left:4px solid ${colors[r.objective]}; cursor:pointer; padding:10px; margin-bottom:6px; background:rgba(255,255,255,0.04); border-radius:6px; transition:all 0.2s;"
            onmouseover="this.style.background='rgba(255,255,255,0.1)'"
            onmouseout="if(!this.classList.contains('active'))this.style.background='rgba(255,255,255,0.04)'"
            onclick="selectRouteCard(${i})">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:bold;font-size:14px;">${icons[r.objective] || ''} ${r.label}</span>
                <span style="font-size:13px;color:${colors[r.objective]};font-weight:bold;">${t}</span>
            </div>
            <div style="display:flex; gap:12px; font-size:11px; color:#999; margin-top:4px;">
                <span>${d}</span><span>⚡${e}</span><span>🌿${c}</span><span>🛣️${f}</span>
            </div>
        </div>`;
    }).join('');

    selectRouteCard(0, false);  // draw first route without re-rendering cards
    resultDiv.classList.remove('hidden');

    const overlayBtn = document.getElementById('btn-route-overlay');
    if (overlayBtn) overlayBtn.disabled = false;
}

function selectRouteCard(index, redraw = true) {
    if (index < 0 || index >= allRoutes.length) return;
    selectedRouteIndex = index;
    currentRoute = allRoutes[index];

    // Update active card style
    document.querySelectorAll('.route-card').forEach((el, i) => {
        el.classList.toggle('active', i === index);
    });

    // Draw selected route
    window.mapFunctions.drawRoute(currentRoute.coords);

    // Update detail stats
    const r = currentRoute;
    document.getElementById('stat-distance').textContent =
        r.distance_km >= 1 ? r.distance_km.toFixed(2) + ' km' : r.distance_m.toFixed(0) + ' m';
    document.getElementById('stat-time').textContent =
        r.time_min >= 60 ? Math.floor(r.time_min / 60) + 'h' + (r.time_min % 60).toFixed(0) + 'min' : r.time_min.toFixed(1) + ' min';
    document.getElementById('stat-energy').textContent = (r.energy_mj ? r.energy_mj.toFixed(2) + ' MJ' : '-');
    document.getElementById('stat-carbon').textContent = (r.carbon_kg ? r.carbon_kg.toFixed(3) + ' kg' : '-');
    document.getElementById('stat-comfort').textContent = (r.avg_comfort ? (r.avg_comfort * 100).toFixed(0) + '%' : '-');
    const tc = r.total_constraint_s;
    if (tc) {
        document.getElementById('stat-constraint').textContent =
            tc >= 60 ? Math.floor(tc / 60) + '分' + (tc % 60).toFixed(0) + '秒' : tc.toFixed(0) + '秒';
    }
}

/**
 * 隐藏结果
 */
function hideResult() {
    document.getElementById('result').classList.add('hidden');
    document.getElementById('route-traffic-analysis').classList.add('hidden');
    const overlayBtn = document.getElementById('btn-route-overlay');
    if (overlayBtn) overlayBtn.disabled = true;
    if (routeTrafficLayer && window.map) { window.map.removeLayer(routeTrafficLayer); routeTrafficLayer = null; }
    allRoutes = [];
    selectedRouteIndex = 0;
}

/**
 * 显示错误信息
 */
function showError(message) {
    const errorDiv = document.getElementById('error');
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
    
    // 5秒后自动隐藏
    setTimeout(() => {
        errorDiv.classList.add('hidden');
    }, 5000);
}

/**
 * 隐藏错误信息
 */
function hideError() {
    document.getElementById('error').classList.add('hidden');
}

/**
 * 显示加载状态
 */
function showLoading() {
    document.getElementById('loading').classList.remove('hidden');
}

/**
 * 隐藏加载状态
 */
function hideLoading() {
    document.getElementById('loading').classList.add('hidden');
}

/**
 * 处理重置
 */
function handleReset() {
    // 重置地图
    window.mapFunctions.resetAll();
    
    // 清空当前路径
    currentRoute = null;

    // 清除交通叠加层
    if (routeTrafficLayer && window.map) { window.map.removeLayer(routeTrafficLayer); routeTrafficLayer = null; }

    // 隐藏结果和错误
    hideResult();
    hideError();

    // 同步清理交通预测状态
    if (window.predictionFunctions && window.predictionFunctions.clear) {
        window.predictionFunctions.clear();
    }
    
    console.log('🔄 已重置所有状态');
}

/**
 * 获取路网统计信息
 */
async function fetchGraphStats() {
    try {
        const response = await fetch(`${API_BASE}/graph/stats`);
        const result = await response.json();
        
        if (result.success) {
            console.log('📊 路网统计:', result.stats);
            return result.stats;
        }
    } catch (error) {
        console.error('❌ 获取路网统计失败:', error);
    }
    return null;
}

/**
 * 在控制台显示欢迎信息
 */
function showWelcomeMessage() {
    console.log('%c🚗 PeMS D12 路径规划系统', 'font-size: 20px; font-weight: bold; color: #667eea;');
    console.log('%c基于 A* 算法的智能路径规划', 'font-size: 12px; color: #666;');
    console.log('');
    console.log('📍 使用方法:');
    console.log('  1. 点击地图选择起点 (绿色标记)');
    console.log('  2. 点击地图选择终点 (红色标记)');
    console.log('  3. 选择优化目标 (最短时间/最短距离)');
    console.log('  4. 点击"计算路径"按钮');
    console.log('');
    console.log('💡 提示: 可以使用滚轮缩放地图,拖动地图浏览区域');
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    // 等待地图模块加载完成
    setTimeout(() => {
        initRouteModule();
        initRouteOverlayButton();
        updateUIForMode(); // 初始化UI状态
        showWelcomeMessage();

        // 可选:获取并显示路网统计
        fetchGraphStats().then(stats => {
            if (stats) {
                console.log(`%c✓ 路网已加载: ${stats.nodes} 节点, ${stats.edges} 边`,
                    'color: #22c55e; font-weight: bold;');
            }
        });
    }, 100);
});

// ── 路线交通预测叠加 ──

let routeTrafficLayer = null;

function initRouteOverlayButton() {
    const overlayBtn = document.getElementById('btn-route-overlay');
    if (overlayBtn) {
        overlayBtn.addEventListener('click', handleRouteOverlay);
    }
}

async function handleRouteOverlay() {
    if (!currentRoute || !currentRoute.path || currentRoute.path.length < 2) {
        showError('请先计算一条路径');
        return;
    }

    const btn = document.getElementById('btn-route-overlay');
    const step = parseInt(document.getElementById('prediction-step').value || 1);
    btn.disabled = true; btn.textContent = '正在加载TGCN预测模型...';
    showLoading();

    try {
        const resp = await fetch('/api/traffic/route-overlay', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: currentRoute.path, step })
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error);

        // Draw color-coded route: yellow = uncovered (no sensor nearby), green/red = covered
        if (routeTrafficLayer && window.map) window.map.removeLayer(routeTrafficLayer);
        routeTrafficLayer = L.layerGroup();

        data.segments.forEach(seg => {
            let color = '#f59e0b';  // default: yellow = uncovered
            if (seg.covered) {
                color = seg.congestion === 'congested' ? '#ef4444' : '#22c55e';
            }
            const dash = seg.covered ? null : '5,5';
            L.polyline(seg.coords, { color, weight: 6, opacity: 0.7, dashArray: dash }).addTo(routeTrafficLayer);
        });
        if (window.map) routeTrafficLayer.addTo(window.map);

        // Update analysis panel
        document.getElementById('rta-avg-speed').textContent = data.summary.avg_speed_kmh + ' km/h';
        document.getElementById('rta-congested').textContent = data.summary.congested_segments + '/' + data.summary.total_segments;
        document.getElementById('rta-congested-pct').textContent = data.summary.congested_pct + '%';
        document.getElementById('rta-threshold').textContent = data.summary.threshold_kmh + ' km/h';
        // Show coverage info
        const covPct = data.summary.covered_pct || 0;
        document.getElementById('rta-congested').textContent += ' | 覆盖 ' + covPct + '%';
        document.getElementById('route-traffic-analysis').classList.remove('hidden');

        console.log('Traffic overlay:', data.summary);
    } catch (e) {
        showError('交通叠加失败: ' + e.message);
    } finally {
        hideLoading();
        btn.disabled = false; btn.textContent = '交通预测叠加';
    }
}

// 导出函数供外部调用
window.routeFunctions = {
    calculateRoute: handleRouteCalculation,
    reset: handleReset,
    fetchStats: fetchGraphStats
};
