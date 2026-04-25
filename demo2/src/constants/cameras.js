export const DEFAULT_CAMERA_ID = 'bot128';

export const CAMERA_FEEDS = [
  {
    id: 'bot128',
    label: '基隆路',
    route: 'Keelung Rd.',
    url: 'https://jtmctrafficcctv2.gov.taipei/NVR/0b0ea88c-4ac6-4e76-b1d0-6868c0354cf3/live.m3u8',
  },
  {
    id: 'bot382',
    label: '忠孝东路 / 光复南路',
    route: 'Zhongxiao E. Rd. / Guangfu S. Rd.',
    url: 'https://jtmctrafficcctv2.gov.taipei/NVR/4ad0b078-a5d3-4fa5-ae4d-c1b7a7ce7d7a/live.m3u8',
  },
  {
    id: 'bot287',
    label: '基隆路二段 / 嘉兴街',
    route: 'Keelung Rd. Sec. 2 / Jiaxing St.',
    url: 'https://jtmctrafficcctv5.gov.taipei/NVR/f6b2f98e-9456-4d89-9b30-b8ae98fe4062/live.m3u8',
  },
  {
    id: 'bot343',
    label: '市高光复西行',
    route: 'Civic Blvd. Expressway / Guangfu W.',
    url: 'https://jtmctrafficcctv3.gov.taipei/NVR/74f29e27-6d4c-4dd0-996b-9fe4a7b7bc4e/live.m3u8',
  },
  {
    id: 'bot136',
    label: '信义路',
    route: 'Xinyi Rd.',
    url: 'https://jtmctrafficcctv2.gov.taipei/NVR/77671f83-baa4-48e9-b028-3d5f9f37f5e9/live.m3u8',
  },
];

export const CAMERA_CONFIGS = CAMERA_FEEDS.map((feed) => ({
  device_id: feed.id,
  label: feed.label,
  route: feed.route,
  video_source: feed.url,
}));

export function mergeDevicesWithCameraDefaults(devices = []) {
  const byId = new Map();

  devices.forEach((device) => {
    const deviceId = device?.device_id;
    if (!deviceId) return;
    byId.set(deviceId, device);
  });

  CAMERA_CONFIGS.forEach((camera) => {
    const current = byId.get(camera.device_id);
    byId.set(camera.device_id, {
      ...camera,
      status: 'online',
      ...current,
      label: current?.label || camera.label,
      video_source: current?.video_source || camera.video_source,
      route: current?.route || camera.route,
    });
  });

  const order = new Map(CAMERA_CONFIGS.map((camera, index) => [camera.device_id, index]));
  return [...byId.values()].sort((a, b) => {
    const aOrder = order.has(a.device_id) ? order.get(a.device_id) : Number.MAX_SAFE_INTEGER;
    const bOrder = order.has(b.device_id) ? order.get(b.device_id) : Number.MAX_SAFE_INTEGER;
    if (aOrder !== bOrder) return aOrder - bOrder;
    return String(a.label || a.device_id).localeCompare(String(b.label || b.device_id), 'zh-CN');
  });
}

export function pickDefaultDeviceId(devices = [], fallbackId = '') {
  if (devices.some((device) => device?.device_id === DEFAULT_CAMERA_ID)) {
    return DEFAULT_CAMERA_ID;
  }
  return fallbackId || devices[0]?.device_id || '';
}
