// Native (Capacitor) bootstrap. No-op on the web build so the same codebase
// runs identically in the browser and inside the Android/iOS shell.
import { Capacitor } from '@capacitor/core';

export const isNative = () => Capacitor?.isNativePlatform?.() === true;

export async function initNative() {
  if (!isNative()) return;

  // Tag the document so CSS can add safe-area insets only inside the app.
  document.documentElement.classList.add('native-app');
  document.documentElement.classList.add(`platform-${Capacitor.getPlatform()}`);

  try {
    const { StatusBar, Style } = await import('@capacitor/status-bar');
    await StatusBar.setStyle({ style: Style.Dark });
    if (Capacitor.getPlatform() === 'android') {
      await StatusBar.setBackgroundColor({ color: '#0A1128' });
      await StatusBar.setOverlaysWebView({ overlay: false });
    }
  } catch (_) { /* plugin unavailable */ }

  try {
    const { SplashScreen } = await import('@capacitor/splash-screen');
    // Hide once React has painted the first screen.
    setTimeout(() => SplashScreen.hide().catch(() => {}), 300);
  } catch (_) { /* noop */ }

  try {
    const { App } = await import('@capacitor/app');
    // Android hardware back button: go back in history, else exit.
    App.addListener('backButton', ({ canGoBack }) => {
      if (canGoBack && window.history.length > 1) {
        window.history.back();
      } else {
        App.exitApp();
      }
    });
  } catch (_) { /* noop */ }
}
