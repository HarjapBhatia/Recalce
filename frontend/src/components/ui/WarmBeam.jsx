import React from 'react';

export function WarmBeam({ className }) {
  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden ${className || ''}`}>
      <div 
        className="absolute -top-1/2 left-1/2 w-[1200px] h-[800px] -translate-x-1/2 opacity-[0.03]"
        style={{
          background: 'radial-gradient(circle, var(--primary-container) 0%, transparent 70%)',
          transform: 'translateX(-50%) scale(1.5)',
        }}
      />
    </div>
  );
}
