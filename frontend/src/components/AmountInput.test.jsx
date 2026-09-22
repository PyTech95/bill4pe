import React, { act, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { AmountInput, amountDisplayValue, normalizeAmountText } from './AmountInput';

global.IS_REACT_ACT_ENVIRONMENT = true;
let host, root;
beforeEach(() => { host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });
function Harness({ initial = 0 }) {
  const [value, setValue] = useState(initial);
  return <><AmountInput value={value} onChange={(e) => setValue(e.target.value)} /><output>{value}</output></>;
}
function input(text) {
  const element = host.querySelector('input');
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(element, text);
    element.dispatchEvent(new Event('input', { bubbles: true }));
  });
  return element;
}
test.each([0, '0', '0.00', '', null, undefined])('zero/empty %s is a placeholder, not a value', (initial) => {
  act(() => root.render(<Harness initial={initial} />));
  expect(host.querySelector('input').value).toBe('');
  expect(host.querySelector('input').placeholder).toBe('0');
});
test('type 1 then 0 gives 1 then 10; delete restores blank', () => {
  act(() => root.render(<Harness />));
  expect(input('1').value).toBe('1');
  expect(host.querySelector('output').textContent).toBe('1');
  expect(input('10').value).toBe('10');
  expect(input('').value).toBe('');
});
test('decimal drafts are not lost during typing', () => {
  act(() => root.render(<Harness />));
  for (const text of ['0', '0.', '0.0', '0.05', '12.50']) expect(input(text).value).toBe(text);
  expect(host.querySelector('output').textContent).toBe('12.50');
});
test('saved positive values remain editable; external changes are applied', () => {
  act(() => root.render(<AmountInput value={20} />));
  expect(host.querySelector('input').value).toBe('20');
  act(() => root.render(<AmountInput value={0} />));
  expect(host.querySelector('input').value).toBe('');
});
test('zeros turn back to placeholder after blur', () => {
  act(() => root.render(<Harness />));
  const element = input('0.00');
  act(() => element.dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
  expect(element.value).toBe('');
});
test('leading zeros normalize and invalid monetary text is rejected', () => {
  expect(normalizeAmountText('00012')).toBe('12');
  expect(normalizeAmountText('.5')).toBe('0.5');
  for (const text of ['-1', '1e4', '1.2.3', '3.456', 'NaN']) expect(normalizeAmountText(text)).toBeNull();
  expect(amountDisplayValue('0.00')).toBe('');
});
