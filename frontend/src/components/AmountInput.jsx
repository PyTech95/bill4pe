import React, { forwardRef, useEffect, useRef, useState } from 'react';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export const amountDisplayValue = (value) => {
  if (value == null || value === '' || Number(value) === 0) return '';
  return String(value);
};

export const normalizeAmountText = (text) => {
  if (!/^\d*(\.\d{0,2})?$/.test(text)) return null;
  return text.replace(/^0+(?=\d)/, '').replace(/^\./, '0.');
};

/** Money only: a blank value displays a grey 0; quantity/PIN inputs stay unchanged.
 * Keep decimal drafts (0., 0.0) while typing, and convert to numbers only on submit.
 */
export const AmountInput = forwardRef(({ value, onChange, onBlur, className,
  type, inputMode, placeholder, min, max, step, ...props }, ref) => {
  const [text, setText] = useState(() => amountDisplayValue(value));
  const lastValue = useRef(value);
  useEffect(() => {
    if (value !== lastValue.current) {
      lastValue.current = value;
      setText(amountDisplayValue(value));
    }
  }, [value]);

  return <Input {...props} ref={ref} type="text" inputMode="decimal"
    placeholder="0" value={text} aria-label={props['aria-label'] || 'Amount in rupees'}
    className={cn('placeholder:text-slate-400 placeholder:font-normal', className)}
    onChange={(event) => {
      const next = normalizeAmountText(event.target.value);
      if (next == null) return;
      lastValue.current = next;
      setText(next);
      event.target.value = next;
      onChange?.(event);
    }}
    onBlur={(event) => {
      setText(amountDisplayValue(text));
      onBlur?.(event);
    }} />;
});
AmountInput.displayName = 'AmountInput';
