import { useEffect, useRef, useState } from 'react';

export default function GlassCard({
  children,
  className = '',
  glowColor,
  hover = true,
  onClick,
  style = {},
}) {
  const cardRef = useRef(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setIsVisible(true); },
      { threshold: 0.1, rootMargin: '20px' }
    );
    if (cardRef.current) observer.observe(cardRef.current);
    return () => observer.disconnect();
  }, []);

  const glowStyle = glowColor ? {
    '--glow-color': glowColor,
  } : {};

  return (
    <div
      ref={cardRef}
      className={`glass-card-component ${hover ? 'hoverable' : ''} ${isVisible ? 'visible' : ''} ${onClick ? 'clickable' : ''} ${className}`}
      onClick={onClick}
      style={{ ...glowStyle, ...style }}
    >
      {children}

      <style>{`
        .glass-card-component {
          background: var(--glass-bg);
          backdrop-filter: blur(16px);
          -webkit-backdrop-filter: blur(16px);
          border: 1px solid var(--glass-border);
          border-radius: 16px;
          padding: 24px;
          opacity: 0;
          transform: translateY(12px);
          transition:
            opacity 500ms cubic-bezier(0.23, 1, 0.32, 1),
            transform 500ms cubic-bezier(0.23, 1, 0.32, 1),
            border-color 200ms ease,
            box-shadow 200ms ease;
        }
        .glass-card-component.visible {
          opacity: 1;
          transform: translateY(0);
        }
        .glass-card-component.hoverable:hover {
          border-color: var(--glow-color, rgba(139, 92, 246, 0.4));
          box-shadow: 0 0 24px color-mix(in srgb, var(--glow-color, #8B5CF6) 20%, transparent);
        }
        .glass-card-component.clickable {
          cursor: pointer;
        }
        .glass-card-component.clickable:active {
          transform: scale(0.98);
        }
      `}</style>
    </div>
  );
}
