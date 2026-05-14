/**
 * Leaflet 地图初始化和交互 - 比对分析版本
 * 支持显示多条路径进行对比
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
let routeLayers = {};  // 存储多条路径
let boundaryLayer = null;

// 算法颜色配置
const ALGORITHM_COLORS = {
    'astar': '#22c55e',      // 绿色
    'dijkstra': '#3b82f6',   // 蓝色
    'greedy': '#f59e0b',     // 橙色
    'alt': '#a855f7'         // 紫色
};

// 算法名称映射
const ALGORITHM_NAMES = {
    'astar': 'A* 算法',
    'dijkstra': 'Dijkstra 算法',
    'greedy': '贪心算法',
    'alt': 'ALT 算法'
};

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
        zoomControl: false,
        attributionControl: false
    }).setView(ORANGE_COUNTY_CENTER, 11);

    // 添加 OSM 底图
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
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

    // 添加图例
    addLegend();

    // 地图点击事件
    map.on('click', handleMapClick);

    console.log('✅ 比对分析地图初始化完成');
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

// 添加图例
function addLegend() {
    const legend = L.control({ position: 'bottomright' });
    
    legend.onAdd = function(map) {
        const div = L.DomUtil.create('div', 'legend');
        div.innerHTML = '<strong>路径图例</strong><br>';
        
        // 动态生成图例项
        Object.keys(ALGORITHM_NAMES).forEach(algo => {
            const color = ALGORITHM_COLORS[algo];
            const name = ALGORITHM_NAMES[algo];
            div.innerHTML += `
                <div class="legend-item">
                    <div class="legend-color" style="background: ${color};"></div>
                    <span>${name}</span>
                </div>
            `;
        });
        
        return div;
    };
    
    legend.addTo(map);
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
    
    // 启用比对按钮
    updateCompareButton();
    
    // 如果有终点,清除旧路径
    if (endMarker) {
        clearAllRoutes();
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
    
    // 启用比对按钮
    updateCompareButton();
    
    // 如果有起点,清除旧路径
    if (startMarker) {
        clearAllRoutes();
    }
}

// 绘制单条路径
function drawRoute(algorithm, coords) {
    // 移除该算法的旧路径
    if (routeLayers[algorithm]) {
        map.removeLayer(routeLayers[algorithm]);
    }
    
    // 绘制新路径
    const color = ALGORITHM_COLORS[algorithm];
    routeLayers[algorithm] = L.polyline(coords, {
        color: color,
        weight: 5,
        opacity: 0.8,
        smoothFactor: 0,
        noClip: true
    }).addTo(map);
    
    // 添加路径信息
    const name = ALGORITHM_NAMES[algorithm];
    routeLayers[algorithm].bindPopup(`<b>${name}</b><br>路径已绘制`);
}

// 清除所有路径
function clearAllRoutes() {
    Object.keys(routeLayers).forEach(algo => {
        if (routeLayers[algo]) {
            map.removeLayer(routeLayers[algo]);
            delete routeLayers[algo];
        }
    });
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
    clearAllRoutes();
    clearStartPoint();
    clearEndPoint();
    updateCompareButton();
    
    // 重置地图视图
    map.setView(ORANGE_COUNTY_CENTER, 11);
    
    // 重新绘制边界
    drawNetworkBoundary();
    
    // 隐藏结果
    document.getElementById('comparison-result').classList.add('hidden');
    document.getElementById('error').classList.add('hidden');
    
    console.log('🔄 已重置所有标记和路径');
}

// 更新比对按钮状态
function updateCompareButton() {
    const startLat = document.getElementById('start-display').dataset.lat;
    const endLat = document.getElementById('end-display').dataset.lat;
    const btn = document.getElementById('btn-compare');
    
    btn.disabled = !(startLat && endLat);
}

// 缩放到显示所有路径
function fitRoutes() {
    const bounds = L.latLngBounds([]);
    let hasRoutes = false;
    
    // 添加起点和终点
    if (startMarker) {
        bounds.extend(startMarker.getLatLng());
        hasRoutes = true;
    }
    if (endMarker) {
        bounds.extend(endMarker.getLatLng());
        hasRoutes = true;
    }
    
    // 添加所有路径的边界
    Object.keys(routeLayers).forEach(algo => {
        if (routeLayers[algo]) {
            routeLayers[algo].getLatLngs().forEach(latlng => {
                bounds.extend(latlng);
            });
            hasRoutes = true;
        }
    });
    
    if (hasRoutes) {
        map.fitBounds(bounds, {
            padding: [50, 50],
            animate: true
        });
    }
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

// 页面加载完成后初始化地图
document.addEventListener('DOMContentLoaded', () => {
    initMap();
});

// 导出函数供其他模块使用
window.mapFunctions = {
    drawRoute,
    clearAllRoutes,
    resetAll,
    fitRoutes,
    getStartPoint: () => ({
        lat: document.getElementById('start-display').dataset.lat,
        lng: document.getElementById('start-display').dataset.lng
    }),
    getEndPoint: () => ({
        lat: document.getElementById('end-display').dataset.lat,
        lng: document.getElementById('end-display').dataset.lng
    }),
    getNetworkBounds: () => NETWORK_BOUNDS,
    getAlgorithmColors: () => ALGORITHM_COLORS,
    getAlgorithmNames: () => ALGORITHM_NAMES
};
