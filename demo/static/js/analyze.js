// analyze.js — 视频分析页交互

document.addEventListener('DOMContentLoaded', () => {
    loadSamples();
    setupUploadZone();
});

let selectedFile = null;
let selectedSample = null;

// ── 加载内置示例 ──
async function loadSamples() {
    const res = await fetch('/api/samples');
    const data = await res.json();
    const list = document.getElementById('sampleList');

    if (!data.samples.length) {
        list.innerHTML = '<p class="text-xs text-gray-400">无内置示例</p>';
        return;
    }

    list.innerHTML = data.samples.map(s => `
        <button onclick="selectSample('${s.filename}', '${s.name}')"
            class="w-full text-left px-3 py-2 text-sm bg-gray-50 rounded-lg hover:bg-blue-50 hover:text-blue-600 transition border border-gray-100">
            🎬 ${s.name}
        </button>
    `).join('');
}

// ── 上传区域 ──
function setupUploadZone() {
    const zone = document.getElementById('uploadZone');
    const input = document.getElementById('videoInput');

    zone.addEventListener('click', () => input.click());
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            selectFile(e.dataTransfer.files[0]);
        }
    });
    input.addEventListener('change', () => {
        if (input.files.length) selectFile(input.files[0]);
    });
}

function selectFile(file) {
    selectedFile = file;
    selectedSample = null;
    showSelected(file.name);
}

function selectSample(filename, name) {
    selectedSample = filename;
    selectedFile = null;
    showSelected(`示例: ${name}`);
}

function showSelected(name) {
    const el = document.getElementById('selectedVideo');
    document.getElementById('selectedName').textContent = name;
    el.classList.remove('hidden');
}

// ── 开始分析 ──
function startAnalysis() {
    const pipeline = document.getElementById('pipelineSection');
    const results = document.getElementById('resultsSection');
    pipeline.classList.remove('hidden');
    results.classList.add('hidden');

    // Reset steps (preserve step 1's default detail)
    document.querySelectorAll('.pipeline-step').forEach(s => {
        s.classList.remove('running', 'done');
        const detail = s.querySelector('.step-detail');
        const step = s.getAttribute('data-step');
        if (step === '1') {
            detail.textContent = 'I帧边界切分 · SHA-256 · pHash · VIF';
        } else {
            detail.textContent = '等待中';
        }
        s.querySelector('.icon').textContent = step;
    });

    const formData = new FormData();
    if (selectedFile) {
        formData.append('video', selectedFile);
    } else if (selectedSample) {
        formData.append('sample', selectedSample);
    }

    // SSE via fetch
    fetch('/api/analyze', { method: 'POST', body: formData })
        .then(response => {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            function read() {
                reader.read().then(({ done, value }) => {
                    if (done) {
                        // 处理 buffer 中剩余数据
                        if (buffer.trim()) processBuffer(buffer);
                        return;
                    }
                    buffer += decoder.decode(value, { stream: true });

                    // SSE 消息以双换行分隔
                    const messages = buffer.split('\n\n');
                    buffer = messages.pop(); // 最后一个可能不完整

                    for (const msg of messages) {
                        if (!msg.trim()) continue;
                        processBuffer(msg);
                    }
                    read();
                });
            }

            function processBuffer(msg) {
                let eventType = '';
                let dataStr = '';
                for (const line of msg.split('\n')) {
                    if (line.startsWith('event: ')) {
                        eventType = line.slice(7).trim();
                    } else if (line.startsWith('data: ')) {
                        dataStr += line.slice(6);
                    }
                }
                if (eventType && dataStr) {
                    try {
                        const data = JSON.parse(dataStr);
                        handleSSE(eventType, data);
                    } catch (e) {
                        console.error('SSE parse error:', e, dataStr.slice(0, 200));
                    }
                }
            }

            read();
        });
}

function handleSSE(event, data) {
    if (event === 'progress') {
        const step = document.querySelector(`.pipeline-step[data-step="${data.step}"]`);
        if (!step) return;

        step.classList.remove('running', 'done');
        step.classList.add(data.status);

        const detail = step.querySelector('.step-detail');
        if (data.status === 'done') {
            detail.textContent = `✅ ${data.detail || '完成'}`;
            step.querySelector('.icon').textContent = '✓';
        } else {
            detail.textContent = data.label;
        }
    } else if (event === 'result') {
        renderResults(data);
    } else if (event === 'error') {
        alert('分析出错: ' + data.message);
    }
}

// ── 渲染结果 ──
function renderResults(data) {
    document.getElementById('resultsSection').classList.remove('hidden');

    // GOP List
    const gopList = document.getElementById('gopList');
    gopList.innerHTML = data.gops.map(g => {
        // YOLO detections summary
        const detSummary = g.detections && g.detections.length > 0
            ? g.detections.map(d => `${d.class}(${d.confidence})`).join(', ')
            : '无检测';
        const anchorBadge = g.should_anchor
            ? '<span class="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded-full font-medium">⚓ 锚定</span>'
            : '<span class="text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded-full">跳过</span>';

        return `
        <div class="flex gap-4 p-4 bg-gray-50 rounded-xl border border-gray-100">
            <img src="${g.thumbnail}" class="w-28 h-20 object-cover rounded-lg" alt="GOP ${g.gop_id}">
            <div class="flex-1 space-y-1">
                <div class="flex justify-between items-start">
                    <span class="text-sm font-semibold">GOP ${g.gop_id}</span>
                    <div class="flex items-center gap-2">
                        ${anchorBadge}
                        <span class="text-xs text-gray-400">${g.frame_count} frames</span>
                    </div>
                </div>
                <div class="text-xs text-purple-600">🎯 YOLO: ${g.det_count} 目标 — ${detSummary}</div>
                <div class="flex gap-3 text-xs">
                    <span class="text-orange-600">EIS: ${g.eis_score}</span>
                    <span class="text-blue-600">MAB arm=${g.mab_arm} (每${g.mab_interval}GOP)</span>
                </div>
                <div class="hash-text">SHA-256: ${g.sha256}</div>
                <div class="hash-text">pHash: ${g.phash}</div>
                ${g.vif ? `<div class="hash-text text-blue-600">VIF: ${g.vif}</div>` : '<div class="text-xs text-gray-400">VIF: 不可用</div>'}
            </div>
        </div>
    `}).join('');

    // MAB Stats
    if (data.mab_stats) {
        const ms = data.mab_stats;
        document.getElementById('mabStats').innerHTML = `
            <div class="grid grid-cols-3 gap-3 mb-4">
                <div class="p-3 bg-blue-50 rounded-xl text-center">
                    <p class="text-[10px] text-blue-400 uppercase">当前策略臂</p>
                    <p class="text-xl font-bold text-blue-700">Arm ${ms.current_arm}</p>
                    <p class="text-xs text-blue-500">每 ${ms.current_interval} GOP 锚定</p>
                </div>
                <div class="p-3 bg-green-50 rounded-xl text-center">
                    <p class="text-[10px] text-green-400 uppercase">锚定次数</p>
                    <p class="text-xl font-bold text-green-700">${ms.anchor_count}</p>
                </div>
                <div class="p-3 bg-purple-50 rounded-xl text-center">
                    <p class="text-[10px] text-purple-400 uppercase">总决策</p>
                    <p class="text-xl font-bold text-purple-700">${ms.total_decisions}</p>
                </div>
            </div>
            <div class="space-y-2">
                ${(ms.arm_stats || []).map(a => `
                    <div class="flex items-center gap-3 p-2 bg-gray-50 rounded-lg">
                        <span class="text-sm font-semibold w-16">Arm ${a.arm}</span>
                        <span class="text-xs text-gray-500">间隔=${a.interval}</span>
                        <span class="text-xs text-gray-500">拉臂=${a.count}次</span>
                        <span class="text-xs text-blue-600">avg_reward=${a.avg_reward ?? 'N/A'}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    // Merkle Info Summary
    const merkle = document.getElementById('merkleInfo');
    merkle.innerHTML = `
        <div class="p-4 bg-indigo-50 rounded-xl border border-indigo-100 flex-1">
            <p class="text-[10px] text-indigo-400 uppercase tracking-wider mb-1">Merkle Root</p>
            <p class="font-mono text-sm text-indigo-700 break-all">${data.merkle.root}</p>
        </div>
        <div class="grid grid-cols-2 gap-3 mt-3">
            <div class="p-3 bg-gray-50 rounded-xl text-center">
                <p class="text-[10px] text-gray-400 uppercase">叶子节点数 / 支持 VIF</p>
                <p class="text-sm font-semibold">${data.merkle.leaf_count} 叶子 · ${data.vif_available ? '✅ 是' : '❌ 否'}</p>
            </div>
            <div class="p-3 bg-blue-50/50 rounded-xl text-center flex flex-col justify-center">
                <p class="text-xs text-blue-600 font-medium">👇 点击下方根节点展开/折叠层级</p>
            </div>
        </div>
    `;

    // Render Interactive Merkle Tree via ECharts
    const chartDom = document.getElementById('merkleTreeChart');
    chartDom.style.display = 'block';
    
    let chart = echarts.getInstanceByDom(chartDom);
    if (chart) {
        chart.dispose();
    }
    chart = echarts.init(chartDom);

    const option = {
        tooltip: {
            trigger: 'item',
            triggerOn: 'mousemove',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#E5E7EB',
            textStyle: { color: '#374151' },
            formatter: function (info) {
                const title = info.data.name.split('\n')[0];
                return `<div class="p-1">
                    <div class="font-bold text-xs mb-1">${title}</div>
                    <div class="font-mono text-[10px] text-gray-500 break-all w-64 whitespace-normal">${info.data.value}</div>
                </div>`;
            }
        },
        series: [
            {
                type: 'tree',
                data: [data.merkle.tree_data],
                top: '8%',
                left: '4%',
                bottom: '12%',
                right: '4%',
                symbolSize: 12,
                initialTreeDepth: 0, // 一开始只展示根节点
                label: {
                    position: 'top',
                    verticalAlign: 'bottom',
                    align: 'center',
                    fontSize: 10,
                    distance: 6,
                    color: '#6B7280',
                },
                leaves: {
                    label: {
                        position: 'bottom',
                        verticalAlign: 'top',
                        align: 'center',
                        distance: 6
                    }
                },
                emphasis: { focus: 'descendant' },
                expandAndCollapse: true,
                animationDuration: 550,
                animationDurationUpdate: 750
            }
        ]
    };
    chart.setOption(option);

    // Ensure resizing works inside the window
    window.addEventListener('resize', () => {
        if (chart) chart.resize();
    });
}
