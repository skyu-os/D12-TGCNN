/**
 * Leaflet 地图初始化和交互
 * PeMS D12 路径规划系统
 */

// Orange County 中心坐标
const ORANGE_COUNTY_CENTER = [33.7175, -117.8311];

// 路网边界 (与传感器检测点范围一致)
const NETWORK_BOUNDS = {
    north: 33.9423,  // 传感器最北端
    south: 33.4049,  // 传感器最南端
    east: -117.5487,  // 传感器最东端
    west: -118.0939   // 传感器最西端
};

// 全局地图实例
let map = null;
let startMarker = null;
let endMarker = null;
let routeLayer = null;
let boundaryLayer = null;

// 传感器图层
let sensorLayer = L.layerGroup();
let predictionLayer = L.layerGroup();
let congestionLayer = L.layerGroup();
let sensorData = [];
let baseLayers = {};

// 自定义图标
const createIcon = (type) => {
    const color = type === 'start' ? '#22c55e' : '#ef4444';
    const size = 24;
    
    return L.divIcon({
        className: `custom-marker ${type}`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
        popupAnchor: [0, -size / 2],
        html: `<div style="
            background: ${color};
            border: 3px solid white;
            border-radius: 50%;
            width: ${size}px;
            height: ${size}px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        "></div>`
    });
};

// 初始化地图
function initMap() {
    // 创建地图实例
    map = L.map('map', {
        zoomControl: false, // 禁用默认缩放控件,稍后自定义位置
        attributionControl: false
    }).setView(ORANGE_COUNTY_CENTER, 11);

    // 添加 OSM 底图（存入 baseLayers 以便图层控制器管理）
    baseLayers.osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // 添加缩放控件到右下角
    L.control.zoom({
        position: 'bottomright'
    }).addTo(map);

    // 添加比例尺
    L.control.scale({
        position: 'bottomleft',
        imperial: false
    }).addTo(map);

    // 绘制路网边界
    drawNetworkBoundary();

    // 图层控制器：底图 + 传感器覆盖层
    L.control.layers(baseLayers, {
        '检测点（传感器站点）': sensorLayer,
        '交通预测图层': predictionLayer,
        '预测拥堵路段': congestionLayer
    }, { position: 'topright' }).addTo(map);

    // 加载传感器数据
    loadSensors();

    // 地图点击事件
    map.on('click', handleMapClick);

    console.log('✅ 地图初始化完成');
    console.log('📍 路网边界:', NETWORK_BOUNDS);
}

// 绘制路网边界
function drawNetworkBoundary() {
    const bounds = [
        [NETWORK_BOUNDS.south, NETWORK_BOUNDS.west],
        [NETWORK_BOUNDS.north, NETWORK_BOUNDS.west],
        [NETWORK_BOUNDS.north, NETWORK_BOUNDS.east],
        [NETWORK_BOUNDS.south, NETWORK_BOUNDS.east],
        [NETWORK_BOUNDS.south, NETWORK_BOUNDS.west]
    ];

    boundaryLayer = L.rectangle(bounds, {
        color: '#667eea',
        weight: 3,
        fillColor: '#667eea',
        fillOpacity: 0.1,
        dashArray: '10, 5'
    }).addTo(map);

    // 添加边界标签
    L.popup()
        .setLatLng([NETWORK_BOUNDS.north, NETWORK_BOUNDS.east])
        .setContent(`
            <div style="text-align: center;">
                <strong>📍 路网覆盖范围</strong><br>
                <small>
                    纬度: ${NETWORK_BOUNDS.south.toFixed(4)}° ~ ${NETWORK_BOUNDS.north.toFixed(4)}°N<br>
                    经度: ${NETWORK_BOUNDS.west.toFixed(4)}° ~ ${NETWORK_BOUNDS.east.toFixed(4)}°W
                </small>
            </div>
        `)
        .openOn(map);
}

// ── 传感器图层 ──

// 传感器类型 -> 颜色
const SENSOR_TYPE_COLORS = {
    'ML': '#3b82f6',  // 主线 - 蓝色
    'OR': '#22c55e',  // 入口匝道 - 绿色
    'FR': '#f97316',  // 出口匝道 - 橙色
    'HV': '#a855f7',  // HOV - 紫色
};
const SENSOR_DEFAULT_COLOR = '#94a3b8';

function getPredictionColor(speed) {
    if (speed < 40) return '#dc2626';
    if (speed < 55) return '#f97316';
    if (speed < 70) return '#facc15';
    return '#22c55e';
}

function drawPredictionSensors(sensorPredictions, horizonMinutes = 5) {
    clearPredictionLayer();

    if (!Array.isArray(sensorPredictions) || sensorPredictions.length === 0) {
        console.warn('⚠️ 无可绘制的预测传感器数据');
        return;
    }

    sensorPredictions.forEach(item => {
        if (typeof item.latitude !== 'number' || typeof item.longitude !== 'number') {
            return;
        }

        const speed = Number(item.pred_speed_kmh || 0);
        const color = getPredictionColor(speed);

        const marker = L.circleMarker([item.latitude, item.longitude], {
            radius: 5.5,
            fillColor: color,
            fillOpacity: 0.85,
            color: '#111827',
            weight: 1,
            opacity: 0.9,
        });

        marker.bindPopup(`
            <div style="min-width:200px;font-size:13px;line-height:1.6;">
                <b style="font-size:14px;">预测速度: ${speed.toFixed(2)} km/h</b><br>
                预测时距: +${horizonMinutes} 分钟<br>
                传感器ID: ${item.sensor_id ?? '-'}<br>
                线路: I-${item.fwy ?? '-'} ${item.dir ?? ''}<br>
                站点: ${item.name ?? '-'}
            </div>
        `, { maxWidth: 280 });

        predictionLayer.addLayer(marker);
    });

    if (!map.hasLayer(predictionLayer)) {
        map.addLayer(predictionLayer);
    }
}

function clearPredictionLayer() {
    predictionLayer.clearLayers();
}

function getRoadCongestionColor(speed) {
    if (speed < 35) return '#b91c1c';
    if (speed < 50) return '#ef4444';
    if (speed < 65) return '#f59e0b';
    return '#22c55e';
}

function drawCongestionSegments(segments) {
    clearCongestionLayer();

    if (!Array.isArray(segments) || segments.length === 0) {
        console.warn('⚠️ 无可绘制的拥堵路段数据');
        return;
    }

    segments.forEach(seg => {
        const coords = seg.coords;
        if (!Array.isArray(coords) || coords.length < 2) {
            return;
        }

        const speed = Number(seg.speed_kmh || 0);
        const color = getRoadCongestionColor(speed);

        const line = L.polyline(coords, {
            color,
            weight: 4,
            opacity: 0.78,
            lineCap: 'butt',
            lineJoin: 'round',
        });

        line.bindPopup(`
            <div style="min-width:200px;font-size:13px;line-height:1.6;">
                <b>预测路段速度: ${speed.toFixed(2)} km/h</b><br>
                拥堵等级: ${seg.congestion_level || '-'}<br>
                路段长度: ${Number(seg.length_m || 0).toFixed(1)} m
            </div>
        `, { maxWidth: 260 });

        congestionLayer.addLayer(line);
    });

    if (!map.hasLayer(congestionLayer)) {
        map.addLayer(congestionLayer);
    }
}

function clearCongestionLayer() {
    congestionLayer.clearLayers();
}

async function loadSensors() {
    try {
        const resp = await fetch('/api/sensors');
        const result = await resp.json();

        if (!result.success) {
            console.warn('⚠️ 加载传感器数据失败:', result.error);
            return;
        }

        sensorData = result.sensors;
        console.log(`📍 已加载 ${sensorData.length} 个传感器站点`);

        // 将传感器标记添加到图层（图层默认不显示，用户勾选后显示）
        sensorData.forEach(s => {
            const color = SENSOR_TYPE_COLORS[s.type] || SENSOR_DEFAULT_COLOR;

            const marker = L.circleMarker([s.latitude, s.longitude], {
                radius: 4,
                fillColor: color,
                fillOpacity: 0.85,
                color: '#fff',
                weight: 1.5,
            });

            const dirLabel = s.dir === 'N' ? '北行' : s.dir === 'S' ? '南行' : s.dir === 'E' ? '东行' : '西行';
            const lengthStr = s.length > 0 ? `${s.length.toFixed(3)} mi` : '-';

            marker.bindPopup(`
                <div style="min-width:180px;font-size:13px;line-height:1.6;">
                    <b style="font-size:14px;">ID: ${s.id}</b><br>
                    <b>I-${s.fwy} ${dirLabel}</b><br>
                    名称: ${s.name}<br>
                    类型: ${s.type_desc}<br>
                    车道数: ${s.lanes}<br>
                    检测长度: ${lengthStr}<br>
                    <span style="color:#888;font-size:11px;">${s.latitude.toFixed(6)}°N, ${s.longitude.toFixed(6)}°W</span>
                </div>
            `, { maxWidth: 250 });

            sensorLayer.addLayer(marker);
        });
    } catch (err) {
        console.error('❌ 请求传感器数据异常:', err);
    }
}

// 处理地图点击
function handleMapClick(e) {
    const lat = e.latlng.lat.toFixed(6);
    const lng = e.latlng.lng.toFixed(6);
    
    // 检查点击位置是否在路网范围内
    const latNum = parseFloat(lat);
    const lngNum = parseFloat(lng);
    
    if (latNum < NETWORK_BOUNDS.south || latNum > NETWORK_BOUNDS.north ||
        lngNum < NETWORK_BOUNDS.west || lngNum > NETWORK_BOUNDS.east) {
        showError(`⚠️ 点击位置超出路网范围!

📍 有效范围:
• 纬度: ${NETWORK_BOUNDS.south.toFixed(4)}° ~ ${NETWORK_BOUNDS.north.toFixed(4)}°N
• 经度: ${NETWORK_BOUNDS.west.toFixed(4)}° ~ ${NETWORK_BOUNDS.east.toFixed(4)}°W

💡 请点击蓝色虚线矩形内的区域`);
        return;
    }
    
    // 检查当前应该设置起点还是终点
    const startDisplay = document.getElementById('start-display');
    const endDisplay = document.getElementById('end-display');
    
    if (!startDisplay.dataset.lat) {
        // 设置起点
        setStartPoint(lat, lng);
    } else if (!endDisplay.dataset.lat) {
        // 设置终点
        setEndPoint(lat, lng);
    } else {
        // 两者都有,询问用户
        const choice = confirm('起点和终点已设置,是否重新设置起点?\n\n取消则重新设置终点');
        if (choice) {
            setStartPoint(lat, lng);
        } else {
            setEndPoint(lat, lng);
        }
    }
}

// 设置起点
function setStartPoint(lat, lng) {
    const latNum = parseFloat(lat);
    const lngNum = parseFloat(lng);
    
    // 移除旧标记
    if (startMarker) {
        map.removeLayer(startMarker);
    }
    
    // 添加新标记
    startMarker = L.marker([latNum, lngNum], {
        icon: createIcon('start')
    }).addTo(map);
    
    startMarker.bindPopup(`<b>起点</b><br>${lat}, ${lng}`).openPopup();
    
    // 更新显示
    const display = document.getElementById('start-display');
    display.textContent = `${lat}, ${lng}`;
    display.dataset.lat = lat;
    display.dataset.lng = lng;
    display.classList.add('has-value');
    
    // 启用计算按钮
    updateRouteButton();
    
    // 如果有终点,绘制预览线
    if (endMarker) {
        drawPreviewLine();
    }
}

// 设置终点
function setEndPoint(lat, lng) {
    const latNum = parseFloat(lat);
    const lngNum = parseFloat(lng);
    
    // 移除旧标记
    if (endMarker) {
        map.removeLayer(endMarker);
    }
    
    // 添加新标记
    endMarker = L.marker([latNum, lngNum], {
        icon: createIcon('end')
    }).addTo(map);
    
    endMarker.bindPopup(`<b>终点</b><br>${lat}, ${lng}`).openPopup();
    
    // 更新显示
    const display = document.getElementById('end-display');
    display.textContent = `${lat}, ${lng}`;
    display.dataset.lat = lat;
    display.dataset.lng = lng;
    display.classList.add('has-value');
    
    // 启用计算按钮
    updateRouteButton();
    
    // 如果有起点,绘制预览线
    if (startMarker) {
        drawPreviewLine();
    }
}

// 绘制直线预览
function drawPreviewLine() {
    // 移除旧的预览线
    if (routeLayer) {
        map.removeLayer(routeLayer);
    }
    
    const startLatLng = startMarker.getLatLng();
    const endLatLng = endMarker.getLatLng();
    
    // 绘制虚线预览
    routeLayer = L.polyline([startLatLng, endLatLng], {
        color: '#667eea',
        weight: 3,
        opacity: 0.5,
        dashArray: '10, 10'
    }).addTo(map);
}

// 绘制规划路径
function drawRoute(coords, styleOptions = {}) {
    // 移除旧路径
    if (routeLayer) {
        map.removeLayer(routeLayer);
    }
    
    // 绘制新路径
    routeLayer = L.polyline(coords, {
        color: '#667eea',
        weight: 5,
        opacity: 0.8,
        smoothFactor: 0,
        noClip: true,
        ...styleOptions
    }).addTo(map);
    
    // 缩放地图以显示完整路径
    map.fitBounds(routeLayer.getBounds(), {
        padding: [50, 50],
        animate: true
    });
}

// 清除路径
function clearRoute() {
    if (routeLayer) {
        map.removeLayer(routeLayer);
        routeLayer = null;
    }
}

// 清除起点
function clearStartPoint() {
    if (startMarker) {
        map.removeLayer(startMarker);
        startMarker = null;
    }
    
    const display = document.getElementById('start-display');
    display.textContent = '点击地图选择起点';
    display.dataset.lat = '';
    display.dataset.lng = '';
    display.classList.remove('has-value');
}

// 清除终点
function clearEndPoint() {
    if (endMarker) {
        map.removeLayer(endMarker);
        endMarker = null;
    }
    
    const display = document.getElementById('end-display');
    display.textContent = '点击地图选择终点';
    display.dataset.lat = '';
    display.dataset.lng = '';
    display.classList.remove('has-value');
}

// 重置所有
function resetAll() {
    clearRoute();
    clearPredictionLayer();
    clearCongestionLayer();
    clearStartPoint();
    clearEndPoint();
    updateRouteButton();
    
    // 重置地图视图
    map.setView(ORANGE_COUNTY_CENTER, 11);
    
    // 重新绘制边界
    drawNetworkBoundary();
    
    // 隐藏结果
    document.getElementById('result').classList.add('hidden');
    document.getElementById('error').classList.add('hidden');
    
    console.log('🔄 已重置所有标记和路径');
}

// 更新计算按钮状态
function updateRouteButton() {
    const startLat = document.getElementById('start-display').dataset.lat;
    const endLat = document.getElementById('end-display').dataset.lat;
    const btn = document.getElementById('btn-route');
    
    btn.disabled = !(startLat && endLat);
}

// 显示错误信息
function showError(message) {
    const errorDiv = document.getElementById('error');
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
    
    // 5秒后自动隐藏
    setTimeout(() => {
        errorDiv.classList.add('hidden');
    }, 5000);
}

// 地图飞到指定位置
function flyToLocation(lat, lng, zoom = 14) {
    map.flyTo([lat, lng], zoom, {
        animate: true,
        duration: 1.5
    });
}

// 页面加载完成后初始化地图
document.addEventListener('DOMContentLoaded', () => {
    initMap();

    // 在地图初始化后设置全局地图实例
    window.map = map;
    console.log('✅ window.map has been set:', map);
});

// ── 共享工具函数 ──

function formatNumber(value, digits = 2) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : '-';
}

function formatMinutes(seconds) {
    const s = Number(seconds);
    if (!Number.isFinite(s)) return '-';
    if (s >= 3600) {
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        return h + 'h ' + m + 'min';
    }
    return (s / 60).toFixed(1) + ' min';
}

function getSpeedClass(speed) {
    if (speed >= 60) return 'speed-excellent';
    if (speed >= 40) return 'speed-good';
    if (speed >= 20) return 'speed-fair';
    return 'speed-poor';
}

function getSpeedIcon(speed) {
    if (speed >= 60) return '🟢';
    if (speed >= 40) return '🟡';
    if (speed >= 20) return '🟠';
    return '🔴';
}

function getBreakdownPercentage(count, total) {
    return total > 0 ? (count / total) * 100 : 0;
}

// 导出函数供其他模块使用
window.mapFunctions = {
    drawRoute,
    clearRoute,
    drawPredictionSensors,
    clearPredictionLayer,
    drawCongestionSegments,
    clearCongestionLayer,
    resetAll,
    flyToLocation,
    getStartPoint: () => ({
        lat: document.getElementById('start-display').dataset.lat,
        lng: document.getElementById('start-display').dataset.lng
    }),
    getEndPoint: () => ({
        lat: document.getElementById('end-display').dataset.lat,
        lng: document.getElementById('end-display').dataset.lng
    }),
    getNetworkBounds: () => NETWORK_BOUNDS,
    formatNumber,
    formatMinutes,
    getSpeedClass,
    getSpeedIcon,
    getBreakdownPercentage
};
