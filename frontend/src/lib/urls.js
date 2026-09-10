const configuredWebUrl = String(process.env.REACT_APP_PUBLIC_WEB_URL || '').trim().replace(/\/+$/, '');

export const publicWebOrigin = () => {
  if (configuredWebUrl) return configuredWebUrl;
  if (typeof window !== 'undefined' && /^https?:$/.test(window.location.protocol)) return window.location.origin;
  return 'https://bill4pe.com';
};

export const publicWebUrl = (path = '/') => {
  const suffix = String(path || '/').startsWith('/') ? String(path || '/') : `/${path}`;
  return `${publicWebOrigin()}${suffix}`;
};
