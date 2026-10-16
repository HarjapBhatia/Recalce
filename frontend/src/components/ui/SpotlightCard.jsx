import React, { useRef, useState } from 'react';
import { cn } from '../../lib/utils';

export function SpotlightCard({ children, className, ...props }) {
  const divRef = useRef(null);
  const [isFocused, setIsFocused] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [opacity, setOpacity] = useState(0);

  const handleMouseMove = (e) => {
    if (!divRef.current || isFocused) return;

    const div = divRef.current;
    const rect = div.getBoundingClientRect();

    setPosition({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  const handleFocus = () => {
    setIsFocused(true);
    setOpacity(1);
  };

  const handleBlur = () => {
    setIsFocused(false);
    setOpacity(0);
  };

  const handleMouseEnter = () => {
    setOpacity(1);
  };

  const handleMouseLeave = () => {
    setOpacity(0);
  };

  return (
    <div
      ref={divRef}
      onMouseMove={handleMouseMove}
      onFocus={handleFocus}
      onBlur={handleBlur}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className={cn(
        "relative rounded-lg border border-[var(--outline-variant)] bg-[var(--surface)] overflow-hidden transition-all duration-300",
        className
      )}
      {...props}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-0 transition duration-300"
        style={{
          opacity,
          background: `radial-gradient(400px circle at ${position.x}px ${position.y}px, rgba(242,146,28,0.03), transparent 40%)`,
        }}
      />
      {/* Border spotlight */}
      <div
        className="pointer-events-none absolute -inset-px rounded-lg opacity-0 transition duration-300"
        style={{
          opacity,
          background: `radial-gradient(300px circle at ${position.x}px ${position.y}px, rgba(242,146,28,0.15), transparent 40%)`,
          WebkitMaskImage: `url("data:image/svg+xml,%3Csvg width='100%25' height='100%25' xmlns='http://www.w3.org/2000/svg'%3E%3Crect width='100%25' height='100%25' fill='none' stroke='black' stroke-width='3' rx='8' ry='8' /%3E%3C/svg%3E")`,
        }}
      />
      <div className="relative h-full w-full">{children}</div>
    </div>
  );
}

