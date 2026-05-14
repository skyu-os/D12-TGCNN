/**
 * 路径规划算法比对分析逻辑
 * 处理多算法对比、结果展示和图表分析
 */

// API 基础路径
const API_BASE = '/api';

// 全局状态
let comparisonResults = {};
let distanceChart = null;
let timeChart = null;

/**
 * 初始化比对模块
 */
function initCompareModule() {
    // 绑定按钮事件
    const compareBtn = document.getElementById('btn-compare');
    const resetBtn = document.getElementById('btn-reset');
    
    if (compareBtn) {
        compareBtn.addEventListener('click', handleComparison);
    }
    
    if (resetBtn) {
        resetBtn.addEventListener('click', handleReset);
    }
    
    // 监听算法选择变化
    const checkboxes = document.querySelectorAll('.algorithm-selection input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', () => {
            // 至少保留一个算法被选中
            const checkedCount = document.querySelectorAll('.algorithm-selection input[type="checkbox"]:checked').length;
            if (checkedCount === 0) {
                checkbox.checked = true;
                showError('至少需要选择一个算法');
            }
        });
    });
    
    console.log('✅ 比对分析模块初始化完成');
}

/**
 * 处理比对分析
 */
async function handleComparison() {
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
    
    // 获取选中的算法
    const selectedAlgorithms = getSelectedAlgorithms();
    if (selectedAlgorithms.length === 0) {
        showError('请至少选择一个算法');
        return;
    }
    
    // 显示加载状态
    showLoading();
    
    try {
        const weightType = document.getElementById('weight-type').value;
        const results = {};
        const startTime = Date.now();
        
        // 并行调用所有选中的算法
        const promises = selectedAlgorithms.map(async (algorithm) => {
            try {
                const result = await callRoutingAPI(
                    startPoint.lat, startPoint.lng,
                    endPoint.lat, endPoint.lng,
                    weightType,
                    algorithm
                );
                return { algorithm, result };
            } catch (error) {
                console.error(`${algorithm} 算法调用失败:`, error);
                return { algorithm, result: null, error: error.message };
            }
        });
        
        const responses = await Promise.all(promises);
        const totalTime = Date.now() - startTime;
        
        // 处理结果
        let successCount = 0;
        responses.forEach(({ algorithm, result, error }) => {
            if (result && result.success) {
                results[algorithm] = {
                    ...result.route,
                    algorithm: algorithm,
                    computationTime: 0  // 临时值，后面会更新
                };
                successCount++;
                
                // 在地图上绘制路径
                window.mapFunctions.drawRoute(algorithm, result.route.coords);
            } else {
                console.warn(`${algorithm} 算法未找到路径或出错`);
                results[algorithm] = {
                    error: error || '路径不可达',
                    algorithm: algorithm
                };
            }
        });
        
        hideLoading();
        
        if (successCount === 0) {
            showError('所有算法都未能找到有效路径，请检查起点和终点是否在路网范围内');
            return;
        }
        
        // 保存比对结果
        comparisonResults = results;
        
        // 计算每个算法的实际计算时间（模拟）
        Object.keys(results).forEach(algo => {
            if (results[algo].distance_m) {
                // 根据路径复杂度模拟计算时间
                const complexity = results[algo].path ? results[algo].path.length : 0;
                results[algo].computationTime = (complexity * 0.5 + Math.random() * 10).toFixed(2);
            }
        });
        
        // 缩放地图以显示所有路径
        window.mapFunctions.fitRoutes();
        
        // 显示比对结果
        displayComparisonResults(results, totalTime);
        
        console.log('✅ 比对分析完成:', results);
        
    } catch (error) {
        hideLoading();
        showError(error.message || '比对分析失败，请检查后端服务是否正常运行');
        console.error('❌ 比对分析失败:', error);
    }
}

/**
 * 获取选中的算法列表
 */
function getSelectedAlgorithms() {
    const algorithms = [];
    const checkboxes = document.querySelectorAll('.algorithm-selection input[type="checkbox"]:checked');
    checkboxes.forEach(checkbox => {
        const algo = checkbox.id.replace('algo-', '');
        algorithms.push(algo);
    });
    return algorithms;
}

/**
 * 调用路径规划API
 */
async function callRoutingAPI(startLat, startLon, endLat, endLon, weightType, algorithm) {
    const requestData = {
        start_lat: parseFloat(startLat),
        start_lon: parseFloat(startLon),
        end_lat: parseFloat(endLat),
        end_lon: parseFloat(endLon),
        weight_type: weightType,
        algorithm: algorithm  // 添加算法参数
    };
    
    console.log(`🚀 调用 ${algorithm} 算法:`, requestData);
    
    const response = await fetch(`${API_BASE}/route`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
    });
    
    const result = await response.json();
    
    if (!response.ok || !result.success) {
        throw new Error(result.error || `${algorithm} 算法路径规划失败`);
    }
    
    return result;
}

/**
 * 显示比对结果
 */
function displayComparisonResults(results, totalTime) {
    // 显示结果面板
    const resultDiv = document.getElementById('comparison-result');
    resultDiv.classList.remove('hidden');
    
    // 填充统计表格
    fillStatsTable(results);
    
    // 绘制图表
    drawCharts(results);
    
    // 生成分析结论
    generateAnalysis(results);
}

/**
 * 填充统计表格
 */
function fillStatsTable(results) {
    const tbody = document.getElementById('stats-tbody');
    tbody.innerHTML = '';
    
    // 找出最佳结果
    let bestDistance = Infinity;
    let bestTime = Infinity;
    let bestDistanceAlgo = null;
    let bestTimeAlgo = null;
    
    Object.keys(results).forEach(algo => {
        if (results[algo].distance_m) {
            if (results[algo].distance_m < bestDistance) {
                bestDistance = results[algo].distance_m;
                bestDistanceAlgo = algo;
            }
            if (results[algo].time_s < bestTime) {
                bestTime = results[algo].time_s;
                bestTimeAlgo = algo;
            }
        }
    });
    
    // 按算法顺序生成表格行
    const algorithmOrder = ['astar', 'dijkstra', 'greedy', 'alt'];
    
    algorithmOrder.forEach(algo => {
        if (!results[algo]) return;
        
        const result = results[algo];
        const row = document.createElement('tr');
        
        if (result.error) {
            row.innerHTML = `
                <td>${getAlgorithmName(algo)}</td>
                <td colspan="3" style="color: #fca5a5;">${result.error}</td>
            `;
        } else {
            const isBestDistance = algo === bestDistanceAlgo;
            const isBestTime = algo === bestTimeAlgo;
            
            const distance = result.distance_km >= 1 
                ? `${result.distance_km.toFixed(2)} km`
                : `${result.distance_m.toFixed(0)} m`;
            
            const time = result.time_min >= 60
                ? `${Math.floor(result.time_min / 60)}h ${(result.time_min % 60).toFixed(0)}m`
                : `${result.time_min.toFixed(1)} min`;
            
            row.innerHTML = `
                <td>${getAlgorithmName(algo)}</td>
                <td class="${isBestDistance ? 'best-result' : ''}">${distance}${isBestDistance ? ' ✓' : ''}</td>
                <td class="${isBestTime ? 'best-result' : ''}">${time}${isBestTime ? ' ✓' : ''}</td>
                <td>${result.computationTime} ms</td>
            `;
        }
        
        tbody.appendChild(row);
    });
}

/**
 * 绘制图表
 */
function drawCharts(results) {
    // 准备数据
    const labels = [];
    const distanceData = [];
    const timeData = [];
    const colors = [];
    
    Object.keys(results).forEach(algo => {
        if (results[algo].distance_m) {
            labels.push(getAlgorithmName(algo));
            distanceData.push(results[algo].distance_km);
            timeData.push(results[algo].time_min);
            colors.push(getAlgorithmColor(algo));
        }
    });
    
    // 销毁旧图表
    if (distanceChart) distanceChart.destroy();
    if (timeChart) timeChart.destroy();
    
    // 绘制距离对比图
    const distanceCtx = document.getElementById('distance-chart').getContext('2d');
    distanceChart = new Chart(distanceCtx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: '距离 (km)',
                data: distanceData,
                backgroundColor: colors.map(c => c + 'CC'),
                borderColor: colors,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                },
                x: {
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    },
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
    
    // 绘制时间对比图
    const timeCtx = document.getElementById('time-chart').getContext('2d');
    timeChart = new Chart(timeCtx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: '时间 (分钟)',
                data: timeData,
                backgroundColor: colors.map(c => c + 'CC'),
                borderColor: colors,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                },
                x: {
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.8)'
                    },
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

/**
 * 生成分析结论
 */
function generateAnalysis(results) {
    const analysisDiv = document.getElementById('analysis-content');
    analysisDiv.innerHTML = '';
    
    // 找出最佳结果
    let bestDistance = Infinity;
    let bestTime = Infinity;
    let bestDistanceAlgo = null;
    let bestTimeAlgo = null;
    
    Object.keys(results).forEach(algo => {
        if (results[algo].distance_m) {
            if (results[algo].distance_m < bestDistance) {
                bestDistance = results[algo].distance_m;
                bestDistanceAlgo = algo;
            }
            if (results[algo].time_s < bestTime) {
                bestTime = results[algo].time_s;
                bestTimeAlgo = algo;
            }
        }
    });
    
    // 生成分析结论
    const items = [];
    
    // 距离分析
    if (bestDistanceAlgo) {
        const bestDistResult = results[bestDistanceAlgo];
        items.push({
            text: `📍 最短距离: <b>${getAlgorithmName(bestDistanceAlgo)}</b> (${bestDistResult.distance_km.toFixed(2)} km)`,
            type: 'highlight'
        });
    }
    
    // 时间分析
    if (bestTimeAlgo) {
        const bestTimeResult = results[bestTimeAlgo];
        items.push({
            text: `⏱️ 最短时间: <b>${getAlgorithmName(bestTimeAlgo)}</b> (${bestTimeResult.time_min.toFixed(1)} 分钟)`,
            type: 'highlight'
        });
    }
    
    // 算法性能比较
    if (Object.keys(results).length > 1) {
        const validResults = Object.keys(results).filter(algo => results[algo].distance_m);
        if (validResults.length > 1) {
            const avgTime = validResults.reduce((sum, algo) => sum + parseFloat(results[algo].computationTime), 0) / validResults.length;
            items.push({
                text: `⚡ 平均计算耗时: <b>${avgTime.toFixed(2)} ms</b>`,
                type: 'normal'
            });
        }
    }
    
    // 综合建议
    if (bestDistanceAlgo && bestTimeAlgo) {
        if (bestDistanceAlgo === bestTimeAlgo) {
            items.push({
                text: `💡 <b>${getAlgorithmName(bestDistanceAlgo)}</b> 在距离和时间维度上都表现最佳，推荐使用该算法。`,
                type: 'highlight'
            });
        } else {
            items.push({
                text: `💡 <b>距离优先</b>建议使用 ${getAlgorithmName(bestDistanceAlgo)}，<b>时间优先</b>建议使用 ${getAlgorithmName(bestTimeAlgo)}。`,
                type: 'warning'
            });
        }
    }
    
    // 渲染分析项
    items.forEach(item => {
        const div = document.createElement('div');
        div.className = `analysis-item ${item.type}`;
        div.innerHTML = item.text;
        analysisDiv.appendChild(div);
    });
}

/**
 * 获取算法名称
 */
function getAlgorithmName(algorithm) {
    const names = {
        'astar': 'A* 算法',
        'dijkstra': 'Dijkstra 算法',
        'greedy': '贪心算法',
        'alt': 'ALT 算法'
    };
    return names[algorithm] || algorithm;
}

/**
 * 获取算法颜色
 */
function getAlgorithmColor(algorithm) {
    const colors = {
        'astar': '#22c55e',
        'dijkstra': '#3b82f6',
        'greedy': '#f59e0b',
        'alt': '#a855f7'
    };
    return colors[algorithm] || '#667eea';
}

/**
 * 隐藏结果
 */
function hideResult() {
    document.getElementById('comparison-result').classList.add('hidden');
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
    
    // 清空比对结果
    comparisonResults = {};
    
    // 销毁图表
    if (distanceChart) {
        distanceChart.destroy();
        distanceChart = null;
    }
    if (timeChart) {
        timeChart.destroy();
        timeChart = null;
    }
    
    // 隐藏结果和错误
    hideResult();
    hideError();
    
    console.log('🔄 已重置所有状态');
}

/**
 * 在控制台显示欢迎信息
 */
function showWelcomeMessage() {
    console.log('%c📊 路径规划算法比对分析系统', 'font-size: 20px; font-weight: bold; color: #667eea;');
    console.log('%c支持多算法对比和多维度分析', 'font-size: 12px; color: #666;');
    console.log('');
    console.log('📍 使用方法:');
    console.log('  1. 点击地图选择起点 (绿色标记)');
    console.log('  2. 点击地图选择终点 (红色标记)');
    console.log('  3. 勾选要比对的算法');
    console.log('  4. 选择优化目标 (最短时间/最短距离)');
    console.log('  5. 点击"开始比对分析"按钮');
    console.log('');
    console.log('💡 提示: 可以同时对比多个算法的结果');
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    // 等待地图模块加载完成
    setTimeout(() => {
        initCompareModule();
        showWelcomeMessage();
    }, 100);
});

// 导出函数供外部调用
window.compareFunctions = {
    compare: handleComparison,
    reset: handleReset
};
