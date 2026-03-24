// detect.js — 篡改检测页交互

document.addEventListener('DOMContentLoaded', () => {
    loadOrigSamples();
    setupDetectUploadZones();
});

let origFile = null;
let origSample = null;
let suspectFile = null;
let tamperGenerated = false;
let currentTamperId = null;

// ── 加载示例列表 ──
async function loadOrigSamples() {
    const res = await fetch('/api/samples');
    const data = await res.json();
    const select = document.getElementById('origSampleSelect');

    data.samples.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.filename;
        opt.textContent = s.name;
        select.appendChild(opt);
    });

    select.addEventListener('change', () => {
        if (select.value) {
            origSample = select.value;
            origFile = null;
            document.getElementById('origSelected').textContent = `✅ 选择示例: ${select.selectedOptions[0].text}`;
            document.getElementById('origSelected').classList.remove('hidden');
            updateDetectBtn();
        }
    });
}

// ── 上传区域 ──
function setupDetectUploadZones() {
    // Original
    const origZone = document.getElementById('origUploadZone');
    const origInput = document.getElementById('origInput');
    origZone.addEventListener('click', () => origInput.click());
    origZone.addEventListener('dragover', e => { e.preventDefault(); origZone.classList.add('dragover'); });
    origZone.addEventListener('dragleave', () => origZone.classList.remove('dragover'));
    origZone.addEventListener('drop', e => {
        e.preventDefault();
        origZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) selectOrigFile(e.dataTransfer.files[0]);
    });
    origInput.addEventListener('change', () => {
        if (origInput.files.length) selectOrigFile(origInput.files[0]);
    });

    // Suspect
    const suspZone = document.getElementById('suspectUploadZone');
    const suspInput = document.getElementById('suspectInput');
    suspZone.addEventListener('click', () => suspInput.click());
    suspInput.addEventListener('change', () => {
        if (suspInput.files.length) {
            suspectFile = suspInput.files[0];
            tamperGenerated = false;
            document.getElementById('tamperStatus').textContent = `📎 已选择可疑视频: ${suspectFile.name}`;
            document.getElementById('tamperStatus').classList.remove('hidden');
            updateDetectBtn();
        }
    });
}

function selectOrigFile(file) {
    origFile = file;
    origSample = null;
    document.getElementById('origSelected').textContent = `✅ 已选择: ${file.name}`;
    document.getElementById('origSelected').classList.remove('hidden');
    updateDetectBtn();
}

function updateDetectBtn() {
    const btn = document.getElementById('detectBtn');
    btn.disabled = !(origFile || origSample);
}

// ── 一键生成篡改 ──
async function generateTamper(type) {
    if (!origFile && !origSample) {
        alert('请先选择原始视频');
        return;
    }

    const status = document.getElementById('tamperStatus');
    const labels = { frame_replace: '帧替换', compression: '重压缩', noise_inject: '噪声注入' };
    status.textContent = `⏳ 正在生成 "${labels[type]}" 篡改视频…`;
    status.classList.remove('hidden');

    const formData = new FormData();
    if (origFile) formData.append('video', origFile);
    else formData.append('sample', origSample);
    formData.append('tamper_type', type);
    formData.append('intensity', '0.5');

    try {
        const res = await fetch('/api/tamper', { method: 'POST', body: formData });
        const data = await res.json();
        tamperGenerated = true;
        currentTamperId = data.tamper_id;
        status.innerHTML = `✅ 已生成 "${labels[type]}" 篡改视频 — ${data.tampered_count}/${data.total_gops} 个 GOP 被篡改`;
        updateDetectBtn();
    } catch (e) {
        status.textContent = `❌ 生成失败: ${e.message}`;
    }
}

// ── 执行检测 ──
async function runDetection() {
    if (!currentTamperId && !suspectFile && !origFile && !origSample) {
        alert('请先选择原始视频并生成篡改或上传可疑视频');
        return;
    }

    const btn = document.getElementById('detectBtn');
    btn.disabled = true;
    btn.textContent = '🔄 检测中…';

    const formData = new FormData();
    if (currentTamperId) {
        // 使用服务器保存的篡改数据
        formData.append('tamper_id', currentTamperId);
    } else if (origFile) {
        formData.append('original', origFile);
    } else {
        formData.append('original_sample', origSample);
    }
    if (suspectFile) formData.append('suspect', suspectFile);

    try {
        const res = await fetch('/api/detect', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.error) {
            alert('检测出错: ' + data.error);
        } else {
            renderDetectResults(data);
        }
    } catch (e) {
        alert('检测出错: ' + e.message);
    }

    btn.disabled = false;
    btn.textContent = '🔍 开始检测';
}

function renderDetectResults(data) {
    document.getElementById('detectResults').classList.remove('hidden');

    // Overall
    const overall = document.getElementById('overallResult');
    const labels = {
        INTACT: { text: '✅ INTACT — 视频完整无修改', cls: 'result-intact' },
        RE_ENCODED: { text: '⚠️ RE-ENCODED — 重新编码但内容未篡改', cls: 'result-reencoded' },
        TAMPERED: { text: '❌ TAMPERED — 检测到内容篡改', cls: 'result-tampered' },
    };
    const info = labels[data.overall] || labels.TAMPERED;
    overall.innerHTML = `<div class="result-banner ${info.cls}">${info.text}</div>`;

    // Frame comparison
    const comp = document.getElementById('frameComparison');
    comp.innerHTML = data.comparisons.map(c => {
        const stateCls = c.state === 'INTACT' ? 'state-intact' : c.state === 'TAMPERED' ? 'state-tampered' : 'state-reencoded';
        const borderCls = c.state === 'TAMPERED' ? 'border-red-400' : c.state === 'RE_ENCODED' ? 'border-yellow-400' : 'border-green-200';
        return `
            <div class="flex items-center gap-4 p-3 rounded-xl border ${borderCls} bg-white">
                <img src="${c.orig_thumb}" class="w-20 h-14 object-cover rounded-lg" alt="原始">
                <div class="text-gray-300 text-lg">→</div>
                <img src="${c.suspect_thumb}" class="w-20 h-14 object-cover rounded-lg" alt="可疑">
                <div class="flex-1">
                    <span class="state-badge ${stateCls}">${c.state}</span>
                </div>
                <div class="text-right">
                    <div class="text-xs text-gray-400">Frame #${c.frame_index}</div>
                    <div class="text-xs ${c.sha_match ? 'text-green-600' : 'text-red-500'}">
                        SHA: ${c.sha_match ? '匹配' : '不匹配'}
                    </div>
                    <div class="text-xs text-gray-500">Hamming: ${c.hamming_distance}</div>
                </div>
            </div>
        `;
    }).join('');
}
