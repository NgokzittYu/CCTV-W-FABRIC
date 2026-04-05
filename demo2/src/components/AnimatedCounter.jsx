import { useEffect, useRef, useState } from 'react';

export default function AnimatedCounter({ value, suffix = '', prefix = '', duration = 1500, decimals = 0 }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef(null);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting && !started) setStarted(true); },
      { threshold: 0.3 }
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [started]);

  useEffect(() => {
    if (!started) return;
    const numValue = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(numValue)) { setDisplay(value); return; }

    const startTime = performance.now();
    let frame;

    const animate = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = eased * numValue;

      setDisplay(decimals > 0 ? current.toFixed(decimals) : Math.round(current));

      if (progress < 1) {
        frame = requestAnimationFrame(animate);
      }
    };

    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [started, value, duration, decimals]);

  return (
    <span ref={ref} className="font-display" style={{ fontVariantNumeric: 'tabular-nums' }}>
      {prefix}{display}{suffix}
    </span>
  );
}
