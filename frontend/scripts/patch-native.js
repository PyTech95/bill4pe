#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const only = (process.argv[2] || '').toLowerCase();

function patchAndroid() {
  const manifestPath = path.join(root, 'android/app/src/main/AndroidManifest.xml');
  if (!fs.existsSync(manifestPath)) return;
  let s = fs.readFileSync(manifestPath, 'utf8');
  const permissions = [
    'android.permission.INTERNET',
    'android.permission.CAMERA',
    'android.permission.RECORD_AUDIO',
    'android.permission.ACCESS_FINE_LOCATION',
    'android.permission.ACCESS_COARSE_LOCATION',
  ];
  for (const perm of permissions) {
    const tag = `<uses-permission android:name="${perm}" />`;
    if (!s.includes(perm)) s = s.replace('</manifest>', `    ${tag}\n</manifest>`);
  }
  if (!s.includes('<queries>')) {
    const queries = `\n    <queries>\n        <intent>\n            <action android:name="android.intent.action.VIEW" />\n            <data android:scheme="upi" />\n        </intent>\n        <package android:name="com.phonepe.app" />\n        <package android:name="net.one97.paytm" />\n        <package android:name="com.google.android.apps.nbu.paisa.user" />\n    </queries>\n`;
    s = s.replace('<application', queries + '\n    <application');
  }
  if (!s.includes('android:usesCleartextTraffic=')) {
    s = s.replace('<application\n', '<application\n        android:usesCleartextTraffic="false"\n');
  }
  fs.writeFileSync(manifestPath, s);
}

function plistEntry(key, value) {
  return `\n\t<key>${key}</key>\n\t<string>${value}</string>`;
}
function patchIOS() {
  const plistPath = path.join(root, 'ios/App/App/Info.plist');
  if (!fs.existsSync(plistPath)) return;
  let s = fs.readFileSync(plistPath, 'utf8');
  const entries = {
    NSCameraUsageDescription: 'BILL4PE uses the camera to scan bills and payment receipts.',
    NSPhotoLibraryUsageDescription: 'BILL4PE lets you select bill and payment receipt images for verification.',
    NSMicrophoneUsageDescription: 'BILL4PE uses the microphone for optional voice expense notes.',
    NSLocationWhenInUseUsageDescription: 'BILL4PE uses your location to attach the bill location when you create an expense.',
  };
  for (const [k, v] of Object.entries(entries)) {
    if (!s.includes(`<key>${k}</key>`)) s = s.replace('</dict>', `${plistEntry(k, v)}\n</dict>`);
  }
  if (!s.includes('<key>LSApplicationQueriesSchemes</key>')) {
    const schemes = `\n\t<key>LSApplicationQueriesSchemes</key>\n\t<array>\n\t\t<string>upi</string>\n\t\t<string>phonepe</string>\n\t\t<string>paytmmp</string>\n\t\t<string>gpay</string>\n\t\t<string>tez</string>\n\t</array>`;
    s = s.replace('</dict>', `${schemes}\n</dict>`);
  }
  fs.writeFileSync(plistPath, s);
}

if (!only || only === 'android') patchAndroid();
if (!only || only === 'ios') patchIOS();
console.log('Native permissions/store configuration patched.');
