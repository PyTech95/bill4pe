// Native (Capacitor) helpers. Every function is a safe no-op/fallback on web so
// BILL4PE keeps one React codebase for browser, Android and iOS.
import { Capacitor } from '@capacitor/core';

export const isNative = () => Capacitor?.isNativePlatform?.() === true;
export const nativePlatform = () => (isNative() ? Capacitor.getPlatform() : 'web');

export async function initNative() {
  if (!isNative()) return;

  document.documentElement.classList.add('native-app');
  document.documentElement.classList.add(`platform-${Capacitor.getPlatform()}`);

  try {
    const { StatusBar, Style } = await import('@capacitor/status-bar');
    await StatusBar.setStyle({ style: Style.Dark });
    await StatusBar.setOverlaysWebView({ overlay: false });
    if (Capacitor.getPlatform() === 'android') {
      await StatusBar.setBackgroundColor({ color: '#0A1128' });
    }
  } catch (_) { /* plugin unavailable */ }

  try {
    const { SplashScreen } = await import('@capacitor/splash-screen');
    setTimeout(() => SplashScreen.hide().catch(() => {}), 350);
  } catch (_) { /* noop */ }

  try {
    const { App } = await import('@capacitor/app');
    App.addListener('backButton', ({ canGoBack }) => {
      if (canGoBack && window.history.length > 1) window.history.back();
      else App.exitApp();
    });
  } catch (_) { /* noop */ }
}

/**
 * Native-first image picker. Returns a browser File so all existing upload APIs
 * can stay unchanged. On web it returns null and callers use their file input.
 */
export async function pickNativeImage({ cameraOnly = false, quality = 88 } = {}) {
  if (!isNative()) return null;
  const { Camera, CameraResultType, CameraSource } = await import('@capacitor/camera');
  const photo = await Camera.getPhoto({
    quality,
    allowEditing: false,
    correctOrientation: true,
    resultType: CameraResultType.Uri,
    source: cameraOnly ? CameraSource.Camera : CameraSource.Prompt,
    saveToGallery: false,
  });
  if (!photo?.webPath) return null;
  const response = await fetch(photo.webPath);
  const blob = await response.blob();
  const ext = String(photo.format || 'jpeg').toLowerCase() === 'png' ? 'png' : 'jpg';
  const mime = blob.type || (ext === 'png' ? 'image/png' : 'image/jpeg');
  return new File([blob], `bill4pe-${Date.now()}.${ext}`, { type: mime });
}

/**
 * Cross-platform current GPS location. Native apps use Capacitor Geolocation;
 * the web app keeps navigator.geolocation as a fallback.
 */
export async function getCurrentGeo({ timeout = 8000, maximumAge = 30000 } = {}) {
  if (isNative()) {
    try {
      const { Geolocation } = await import('@capacitor/geolocation');
      let permission = await Geolocation.checkPermissions();
      if (permission.location !== 'granted' && permission.coarseLocation !== 'granted') {
        permission = await Geolocation.requestPermissions();
      }
      if (permission.location !== 'granted' && permission.coarseLocation !== 'granted') return null;
      const p = await Geolocation.getCurrentPosition({ enableHighAccuracy: true, timeout, maximumAge });
      return p?.coords ? { lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy } : null;
    } catch (_) {
      return null;
    }
  }

  return new Promise((resolve) => {
    if (!navigator.geolocation) { resolve(null); return; }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout, maximumAge },
    );
  });
}
