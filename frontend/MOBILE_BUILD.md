# BILL4PE — Mobile App (Android & iOS)

The mobile apps are built with **Capacitor 7**, which wraps the **exact same React
frontend** as the web portal in a native Android/iOS shell. The UI, graphics and
layout are identical to the web app — there is a single codebase in `frontend/`.

```
frontend/
├── src/                     # shared React app (web + mobile)
├── build/                   # production web bundle (generated)
├── capacitor.config.json    # app id, name, splash/status-bar config
├── android/                 # native Android Studio project  <-- open to build APK/AAB
├── ios/                     # native Xcode project           <-- open to build IPA
└── assets/                  # source logo used to generate app icons + splash
```

- **App name:** BILL4PE
- **Bundle / package ID:** `com.bill4pe.app`
- **Backend:** the app calls the same BILL4PE API via `REACT_APP_BACKEND_URL`
  (baked into the web build at build time).

---

## ⚠️ Before you build a release: point at the PRODUCTION backend

The web bundle hardcodes the backend URL at build time. Set it to your **deployed**
backend (not the preview) before building the release, then re-sync:

```bash
cd frontend
# edit .env -> REACT_APP_BACKEND_URL="https://<your-deployed-backend-domain>"
yarn mobile:sync
```

---

## Prerequisites (install on your own machine — not needed on the server)

- **Node.js 20+** and **Yarn**
- **Android:** Android Studio (Otter / 2025.2.1+), JDK 17, Android SDK
- **iOS:** macOS + Xcode 16+, CocoaPods (`sudo gem install cocoapods`)

## Convenience scripts (added to `frontend/package.json`)

```bash
yarn mobile:sync      # build web + copy into android & ios
yarn mobile:android   # build + sync + open Android Studio
yarn mobile:ios       # build + sync + open Xcode (macOS only)
yarn mobile:icons     # regenerate app icons + splash from assets/logo.png
```

## Android — build an APK / AAB

```bash
cd frontend
yarn mobile:android          # opens Android Studio
# In Android Studio: Build > Build Bundle(s)/APK(s) > Build APK(s)
# Release AAB for Play Store: Build > Generate Signed Bundle/APK > Android App Bundle
```
Debug APK path after a Gradle build:
`android/app/build/outputs/apk/debug/app-debug.apk`

CLI alternative (with Android SDK installed):
```bash
cd frontend/android && ./gradlew assembleDebug
```

## iOS — build / run (macOS only)

```bash
cd frontend/ios/App && pod install      # first time only
cd ../.. && yarn mobile:ios             # opens Xcode
# In Xcode: pick your Team (Signing & Capabilities), then Product > Archive
```

---

## Native features already wired

| Feature | Plugin / mechanism | Permission |
|---|---|---|
| QR scan + receipt photo | web `getUserMedia` + `@capacitor/camera` | Camera |
| Voice expense | web MediaRecorder | Microphone |
| UPI payment deep links | `upi://` intents | `<queries>` (Android) / `LSApplicationQueriesSchemes` (iOS) |
| Splash screen | `@capacitor/splash-screen` | — |
| Status bar theming | `@capacitor/status-bar` | — |
| Android hardware back | `@capacitor/app` back button handler | — |
| Local token storage | `@capacitor/preferences` (available) | — |

Permissions are declared in:
- Android: `android/app/src/main/AndroidManifest.xml`
- iOS: `ios/App/App/Info.plist`

Native-only behavior lives in `frontend/src/lib/native.js` and is a **no-op on the
web build**, so the browser app is completely unaffected.

## Cloud builds (no local Mac/Android Studio)

You can build both platforms in CI without local tooling using **Ionic Appflow**
or GitHub Actions (macOS runner for iOS). Point the pipeline at the `frontend/`
folder and run `yarn install && yarn mobile:sync` before the native build step.
