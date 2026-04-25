import { useEffect, useRef } from 'react';
import Hls from 'hls.js';

export default function HlsPlayer({ url, autoPlay = true, muted = true, ...props }) {
  const videoRef = useRef(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let hls;

    if (Hls.isSupported()) {
      hls = new Hls({
        maxBufferLength: 10,
        maxMaxBufferLength: 20,
        lowLatencyMode: true
      });
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (autoPlay) {
          video.play().catch(() => {});
        }
      });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url;
      video.addEventListener('loadedmetadata', () => {
        if (autoPlay) {
          video.play().catch(() => {});
        }
      });
    }

    return () => {
      if (hls) hls.destroy();
    };
  }, [url, autoPlay]);

  return (
    <video 
      ref={videoRef} 
      playsInline 
      muted={muted}
      autoPlay={autoPlay}
      style={{
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        backgroundColor: '#000',
        ...props.style
      }}
      {...props} 
    />
  );
}
