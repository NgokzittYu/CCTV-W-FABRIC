// benchmark.js — 实验数据页图表

document.addEventListener('DOMContentLoaded', loadBenchmark);

async function loadBenchmark() {
    try {
        const res = await fetch('/api/benchmark');
        const data = await res.json();

        if (!res.ok || data.error) {
            document.getElementById('noData').classList.remove('hidden');
            document.getElementById('chartsContainer').classList.add('hidden');
            return;
        }
        const scenarios = data.scenarios || {};

        if (scenarios.throughput) renderThroughput(scenarios.throughput);
        if (scenarios.latency) renderLatency(scenarios.latency);
        if (scenarios.tamper_detection) renderTamperDetection(scenarios.tamper_detection);
        if (scenarios.resource_usage) renderResource(scenarios.resource_usage);
    } catch (e) {
        document.getElementById('noData').classList.remove('hidden');
        document.getElementById('chartsContainer').classList.add('hidden');
    }
}

function renderThroughput(data) {
    const chart = echarts.init(document.getElementById('throughputChart'));
    const items = Object.values(data.throughput_by_resolution || {});

    chart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { data: ['GOP/s', 'P95 延迟 (ms)'] },
        xAxis: { type: 'category', data: items.map(i => i.resolution) },
        yAxis: [
            { type: 'value', name: 'GOP/s', position: 'left' },
            { type: 'value', name: 'ms', position: 'right' },
        ],
        series: [
            {
                name: 'GOP/s',
                type: 'bar',
                data: items.map(i => i.throughput?.items_per_second?.toFixed(1)),
                itemStyle: { color: '#3B82F6', borderRadius: [6, 6, 0, 0] },
                barWidth: 40,
            },
            {
                name: 'P95 延迟 (ms)',
                type: 'line',
                yAxisIndex: 1,
                data: items.map(i => i.latency?.p95_ms?.toFixed(1)),
                itemStyle: { color: '#8B5CF6' },
                lineStyle: { width: 3 },
                symbol: 'circle',
                symbolSize: 8,
            },
        ],
    });
    window.addEventListener('resize', () => chart.resize());
}

function renderLatency(data) {
    const chart = echarts.init(document.getElementById('latencyChart'));
    const breakdown = data.latency_breakdown || {};
    const stages = Object.keys(breakdown).filter(k => k !== 'total');
    const labels = { sha256: 'SHA-256', phash: 'pHash', merkle_leaf: 'Merkle' };

    chart.setOption({
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'value', name: '延迟 (ms)' },
        yAxis: { type: 'category', data: stages.map(s => labels[s] || s) },
        series: [{
            type: 'bar',
            data: stages.map(s => breakdown[s].mean_ms?.toFixed(2)),
            itemStyle: {
                color: (params) => ['#3B82F6', '#8B5CF6', '#10B981'][params.dataIndex % 3],
                borderRadius: [0, 6, 6, 0],
            },
            barWidth: 28,
            label: { show: true, position: 'right', formatter: '{c} ms', fontSize: 12 },
        }],
        grid: { left: 80, right: 60 },
    });
    window.addEventListener('resize', () => chart.resize());
}

function renderTamperDetection(data) {
    const chart = echarts.init(document.getElementById('tamperChart'));
    const detection = data.tamper_detection || {};
    const methods = Object.keys(detection);
    const display = { naive_sha256: 'SHA-256', phash: 'pHash', vif_fusion: 'VIF (Ours)' };

    const metrics = ['tpr', 'fpr', 'f1', 'accuracy'];
    const metricLabels = { tpr: 'TPR', fpr: 'FPR', f1: 'F1', accuracy: 'Accuracy' };
    const colors = ['#3B82F6', '#EF4444', '#10B981', '#F59E0B'];

    chart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { data: metrics.map(m => metricLabels[m]) },
        xAxis: { type: 'category', data: methods.map(m => display[m] || m) },
        yAxis: { type: 'value', max: 1.1 },
        series: metrics.map((m, i) => ({
            name: metricLabels[m],
            type: 'bar',
            data: methods.map(method => detection[method]?.overall?.[m]?.toFixed(3) || 0),
            itemStyle: { color: colors[i], borderRadius: [4, 4, 0, 0] },
        })),
    });
    window.addEventListener('resize', () => chart.resize());
}

function renderResource(data) {
    const chart = echarts.init(document.getElementById('resourceChart'));
    const stages = Object.keys(data.resource_by_stage || {});
    const labels = {
        sha256: 'SHA-256', phash: 'pHash',
        merkle_build: 'Merkle Build', full_pipeline: 'Full Pipeline'
    };

    const stageData = stages.map(s => data.resource_by_stage[s]);

    chart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { data: ['内存 (MB)', '耗时 (ms)'] },
        xAxis: { type: 'category', data: stages.map(s => labels[s] || s) },
        yAxis: [
            { type: 'value', name: 'MB', position: 'left' },
            { type: 'value', name: 'ms', position: 'right' },
        ],
        series: [
            {
                name: '内存 (MB)',
                type: 'bar',
                data: stageData.map(d => d.memory?.memory_mb?.toFixed(0)),
                itemStyle: { color: '#3B82F6', borderRadius: [6, 6, 0, 0] },
            },
            {
                name: '耗时 (ms)',
                type: 'line',
                yAxisIndex: 1,
                data: stageData.map(d => d.latency?.mean_ms?.toFixed(0)),
                itemStyle: { color: '#EF4444' },
                lineStyle: { width: 3 },
                symbol: 'circle',
                symbolSize: 8,
            },
        ],
    });
    window.addEventListener('resize', () => chart.resize());
}
