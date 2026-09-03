import React from 'react';

/**
 * Stylised Indian auto-rickshaw icon (3-wheeler).
 * Matches the visual weight of lucide-react icons so it can be used as a
 * drop-in replacement for the Travel category.
 */
export const AutoRickshaw = React.forwardRef(function AutoRickshaw(
  { className = '', strokeWidth = 1.8, ...props },
  ref,
) {
  return (
    <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      {/* Curved canopy roof */}
      <path d="M3.5 12c1.2-4.5 5-7 8.5-7s7.3 2.5 8.5 7" />
      {/* Front windshield post */}
      <path d="M8 12V8.6" />
      {/* Cabin body */}
      <path d="M3 17h18" />
      <path d="M5 12v5" />
      <path d="M19 12v5" />
      {/* Passenger seat divider */}
      <path d="M12 12v5" />
      {/* Front headlight */}
      <circle cx="20" cy="14.5" r="0.6" fill="currentColor" stroke="none" />
      {/* Wheels */}
      <circle cx="8" cy="19" r="2" />
      <circle cx="17" cy="19" r="2" />
    </svg>
  );
});

export default AutoRickshaw;
