// Razorpay Checkout helper — loads the SDK on demand and opens the modal.

export const loadRazorpay = () =>
  new Promise((resolve) => {
    if (typeof window !== 'undefined' && window.Razorpay) return resolve(true);
    const s = document.createElement('script');
    s.src = 'https://checkout.razorpay.com/v1/checkout.js';
    s.onload = () => resolve(true);
    s.onerror = () => resolve(false);
    document.body.appendChild(s);
  });

/**
 * Opens the Razorpay checkout modal.
 * @param {object} order   - { order_id, amount, currency, key_id } from backend
 * @param {object} opts    - { user, name, description, onSuccess(resp), onDismiss() }
 */
export const openRazorpay = async (order, opts = {}) => {
  const ok = await loadRazorpay();
  if (!ok) throw new Error('Razorpay SDK failed to load. Check your connection.');
  if (!order || !order.key_id) throw new Error('Payment could not start — API key missing. Please try again.');
  const { user, name = 'BILL4PE', description = 'Payment', onSuccess, onDismiss } = opts;

  return new Promise((resolve, reject) => {
    const rzp = new window.Razorpay({
      key: order.key_id,
      amount: order.amount,
      currency: order.currency || 'INR',
      order_id: order.order_id,
      name,
      description,
      prefill: { name: user?.name || '', email: user?.email || '' },
      theme: { color: '#0A1128' },
      handler: async (resp) => {
        try {
          if (onSuccess) await onSuccess(resp);
          resolve(resp);
        } catch (e) {
          reject(e);
        }
      },
      modal: {
        ondismiss: () => {
          if (onDismiss) onDismiss();
          reject(new Error('CHECKOUT_DISMISSED'));
        },
      },
    });
    rzp.on('payment.failed', (r) => reject(new Error(r?.error?.description || 'Payment failed')));
    rzp.open();
  });
};
