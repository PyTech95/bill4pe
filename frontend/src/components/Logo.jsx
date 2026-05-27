import React from 'react';

/**
 * BILL4PE logo. Renders the brand mark with optional text.
 * Accepts `variant`: 'mark' (just the icon) | 'full' (mark + wordmark) — default 'full'.
 * `theme`: 'dark' (for dark backgrounds — uses light wordmark) | 'light' (default — navy wordmark).
 */
export default function Logo({ variant = 'full', theme = 'light', className = '', size = 40 }) {
  const wordmarkColor = theme === 'dark' ? '#FFFFFF' : '#0A1128';
  return (
    <div className={`inline-flex items-center gap-2 ${className}`}>
      <img
        src="/logo.png"
        alt="Bill4Pe"
        style={{ height: size, width: 'auto' }}
        className="object-contain"
        draggable="false"
      />
      {variant === 'wordmark-only' && (
        <span
          className="font-display font-bold tracking-tight"
          style={{ color: wordmarkColor, fontSize: size * 0.55 }}
        >Bill4Pe</span>
      )}
    </div>
  );
}
