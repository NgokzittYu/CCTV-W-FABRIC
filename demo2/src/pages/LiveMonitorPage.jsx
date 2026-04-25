import { useCallback, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { ChevronDown, MapPin, Signal, Video } from 'lucide-react';
import HlsPlayer from '../components/HlsPlayer';
import { CAMERA_FEEDS, DEFAULT_CAMERA_ID } from '../constants/cameras';

const DEFAULT_FEED_SIZE = { width: 720, height: 480 };

const INITIAL_FEED_SIZES = CAMERA_FEEDS.reduce((sizes, feed) => ({
  ...sizes,
  [feed.id]: DEFAULT_FEED_SIZE,
}), {});

function getRevealMotion(shouldReduceMotion, delay = 0) {
  return shouldReduceMotion
    ? {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        transition: { duration: 0.12, delay, ease: [0.2, 0, 0, 1] },
      }
    : {
        initial: { opacity: 0, transform: 'translateY(10px)' },
        animate: { opacity: 1, transform: 'translateY(0px)' },
        transition: { duration: 0.22, delay, ease: [0.23, 1, 0.32, 1] },
      };
}

function getSwapMotion(shouldReduceMotion) {
  return shouldReduceMotion
    ? {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
        transition: { duration: 0.12, ease: [0.2, 0, 0, 1] },
      }
    : {
        initial: { opacity: 0, filter: 'blur(4px)', transform: 'translateY(6px) scale(0.985)' },
        animate: { opacity: 1, filter: 'blur(0px)', transform: 'translateY(0px) scale(1)' },
        exit: { opacity: 0, filter: 'blur(2px)', transform: 'translateY(-2px) scale(0.992)' },
        transition: { duration: 0.18, ease: [0.23, 1, 0.32, 1] },
      };
}

export default function LiveMonitorPage() {
  const [selectedFeedId, setSelectedFeedId] = useState(
    () => CAMERA_FEEDS.find((feed) => feed.id === DEFAULT_CAMERA_ID)?.id || CAMERA_FEEDS[0].id,
  );
  const [feedSizes, setFeedSizes] = useState(INITIAL_FEED_SIZES);
  const shouldReduceMotion = useReducedMotion();
  const selectedFeed = CAMERA_FEEDS.find((feed) => feed.id === selectedFeedId) || CAMERA_FEEDS[0];
  const selectedFeedSize = feedSizes[selectedFeed.id];
  const selectedFeedRatio = selectedFeedSize
    ? selectedFeedSize.width / selectedFeedSize.height
    : DEFAULT_FEED_SIZE.width / DEFAULT_FEED_SIZE.height;

  const handleFeedMetadata = useCallback((feedId, event) => {
    const { videoWidth, videoHeight } = event.currentTarget;
    if (!videoWidth || !videoHeight) return;

    setFeedSizes((current) => {
      const previous = current[feedId];
      if (previous?.width === videoWidth && previous?.height === videoHeight) return current;
      return {
        ...current,
        [feedId]: { width: videoWidth, height: videoHeight },
      };
    });
  }, []);

  return (
    <div className="main-content monitor-shell" style={{ padding: '16px 18px 14px', minHeight: '100%' }}>
      <motion.section
        className="monitor-toolbar tech-panel"
        {...getRevealMotion(shouldReduceMotion, 0)}
      >
        <div className="monitor-toolbar__titleBlock">
          <span className="monitor-toolbar__icon">
            <Video size={18} />
          </span>
          <div className="monitor-toolbar__titleCopy">
            <h2 className="monitor-toolbar__title">实时监控</h2>
          </div>
        </div>

        <div className="monitor-toolbar__controls">
          <div className="monitor-select">
            <span className="monitor-select__label">当前探头</span>
            <div className="monitor-select__field">
              <select
                value={selectedFeed.id}
                onChange={(event) => setSelectedFeedId(event.target.value)}
                aria-label="选择监控探头"
              >
                {CAMERA_FEEDS.map((cam) => (
                  <option key={cam.id} value={cam.id}>
                    {cam.id.toUpperCase()} · {cam.label}
                  </option>
                ))}
              </select>
              <ChevronDown size={16} className="monitor-select__icon" />
            </div>
            <span className="monitor-select__route">
              <MapPin size={12} />
              {selectedFeed.route}
            </span>
          </div>

          <div className="monitor-activeTag">
            <Signal size={14} />
            <strong>在线</strong>
          </div>
        </div>
      </motion.section>

      <section className="monitor-denseGrid">
        <motion.section
          className="monitor-stage tech-panel"
          style={{ '--monitor-feed-ratio': selectedFeedRatio }}
          {...getRevealMotion(shouldReduceMotion, 0.04)}
        >
          <div className="monitor-stage__viewport">
            <div className="monitor-stage__media">
              <div className="monitor-stage__topOverlay">
                <div className="monitor-stage__live">
                  <span className="monitor-stage__pulse" />
                  <span>LIVE</span>
                </div>
                <div className="monitor-stage__badge">原始画面</div>
              </div>
              <div className="monitor-stage__glass" />
              <AnimatePresence initial={false} mode="wait">
                <motion.div
                  key={`feed-${selectedFeed.id}`}
                  style={{ width: '100%', height: '100%' }}
                  {...getSwapMotion(shouldReduceMotion)}
                >
                  <HlsPlayer
                    url={selectedFeed.url}
                    muted
                    autoPlay
                    onLoadedMetadata={(event) => handleFeedMetadata(selectedFeed.id, event)}
                    style={{ objectFit: 'contain' }}
                  />
                </motion.div>
              </AnimatePresence>
              <AnimatePresence initial={false} mode="wait">
                <motion.div
                  key={`meta-${selectedFeed.id}`}
                  className="monitor-stage__caption"
                  {...getSwapMotion(shouldReduceMotion)}
                >
                  <span className="monitor-stage__cameraId">{selectedFeed.id.toUpperCase()}</span>
                  <div className="monitor-stage__meta">
                    <span className="monitor-stage__metaPrimary">{selectedFeed.label}</span>
                    <span className="monitor-stage__metaSecondary">
                      <MapPin size={13} />
                      {selectedFeed.route}
                    </span>
                  </div>
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </motion.section>

        <motion.aside
          className="monitor-sideRail"
          {...getRevealMotion(shouldReduceMotion, 0.08)}
        >
          <div className="monitor-sideRail__header">
            <div>
              <span className="monitor-rail__eyebrow">Camera Rail</span>
              <strong className="monitor-sideRail__title">探头预览</strong>
            </div>
            <span className="monitor-rail__count">{CAMERA_FEEDS.length} 路在线</span>
          </div>

          <div className="monitor-sideRail__list">
            {CAMERA_FEEDS.map((cam, index) => {
              const isSelected = cam.id === selectedFeed.id;

              return (
                <motion.button
                  key={cam.id}
                  type="button"
                  className={`monitor-card tech-panel${isSelected ? ' monitor-card--active' : ''}`}
                  aria-label={`切换到 ${cam.id.toUpperCase()} ${cam.label}`}
                  onClick={() => setSelectedFeedId(cam.id)}
                  {...getRevealMotion(shouldReduceMotion, 0.12 + index * 0.04)}
                >
                  <div
                    className="monitor-card__viewport monitor-card__viewport--dense"
                  >
                    <HlsPlayer
                      url={cam.url}
                      muted
                      autoPlay
                      onLoadedMetadata={(event) => handleFeedMetadata(cam.id, event)}
                      style={{ objectFit: 'cover' }}
                    />
                    <div className="monitor-card__shade" />
                    <div className="monitor-card__badge">原始</div>
                  </div>
                  <div className="monitor-card__meta">
                    <span className="monitor-card__idText">{cam.id.toUpperCase()}</span>
                    <span className="monitor-card__label">{isSelected ? `当前 ${cam.label}` : cam.label}</span>
                  </div>
                </motion.button>
              );
            })}
          </div>
        </motion.aside>
      </section>
    </div>
  );
}
