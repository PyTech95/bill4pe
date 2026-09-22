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
  // Legacy Android needs storage permission for Documents; scoped storage on
  // Android 11+ does not. Never request all-files/media access for bill PDFs.
  for (const perm of ['READ_EXTERNAL_STORAGE', 'WRITE_EXTERNAL_STORAGE']) {
    if (!s.includes(`android.permission.${perm}`)) {
      s = s.replace('</manifest>', `    <uses-permission android:name="android.permission.${perm}" android:maxSdkVersion="29" />\n</manifest>`);
    }
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

function patchIOS() {
  const plistPath = path.join(root, 'ios/App/App/Info.plist');
  if (!fs.existsSync(plistPath)) return;
  const plist = require('plist');
  const info = plist.parse(fs.readFileSync(plistPath, 'utf8'));
  const entries = {
    NSCameraUsageDescription: 'BILL4PE uses the camera to scan bills and payment receipts.',
    NSPhotoLibraryUsageDescription: 'BILL4PE lets you select bill and payment receipt images for verification.',
    NSMicrophoneUsageDescription: 'BILL4PE uses the microphone for optional voice expense notes.',
    NSLocationWhenInUseUsageDescription: 'BILL4PE uses your location to attach the bill location when you create an expense.',
  };
  for (const [k, v] of Object.entries(entries)) {
    if (!info[k]) info[k] = v;
  }
  info.LSApplicationQueriesSchemes = [...new Set([...(info.LSApplicationQueriesSchemes || []), 'upi', 'phonepe', 'paytmmp', 'gpay', 'tez'])];
  info.UIFileSharingEnabled = true;
  info.LSSupportsOpeningDocumentsInPlace = true;
  fs.writeFileSync(plistPath, plist.build(info));

  // Merge required API reasons without deleting the app's existing privacy
  // declarations. Add the file to the App target so it is in the archive.
  const privacyPath = path.join(root, 'ios/App/App/PrivacyInfo.xcprivacy');
  const privacy = fs.existsSync(privacyPath) ? plist.parse(fs.readFileSync(privacyPath, 'utf8')) : {};
  const apis = privacy.NSPrivacyAccessedAPITypes || [];
  for (const [type, reason] of [
    ['NSPrivacyAccessedAPICategoryFileTimestamp', 'C617.1'],
    ['NSPrivacyAccessedAPICategoryUserDefaults', 'CA92.1'],
  ]) {
    const entry = apis.find((api) => api.NSPrivacyAccessedAPIType === type);
    if (entry) entry.NSPrivacyAccessedAPITypeReasons = [...new Set([...(entry.NSPrivacyAccessedAPITypeReasons || []), reason])];
    else apis.push({ NSPrivacyAccessedAPIType: type, NSPrivacyAccessedAPITypeReasons: [reason] });
  }
  privacy.NSPrivacyAccessedAPITypes = apis;
  fs.writeFileSync(privacyPath, plist.build(privacy));

  const projectPath = path.join(root, 'ios/App/App.xcodeproj/project.pbxproj');
  if (fs.existsSync(projectPath)) {
    const project = require('xcode').project(projectPath);
    project.parseSync();
    const appGroup = project.findPBXGroupKey({ name: 'App' }) || project.findPBXGroupKey({ path: 'App' });
    if (appGroup && !project.hasFile('PrivacyInfo.xcprivacy') && !project.hasFile('App/PrivacyInfo.xcprivacy')) {
      // Capacitor's project has an App group, not a Resources group. Avoid
      // xcode.addResourceFile's implicit lookup of the absent Resources group.
      const file = new (require('xcode/lib/pbxFile'))('PrivacyInfo.xcprivacy');
      file.uuid = project.generateUuid();
      file.fileRef = project.generateUuid();
      file.target = project.getFirstTarget().uuid;
      project.addToPbxBuildFileSection(file);
      project.addToPbxResourcesBuildPhase(file);
      project.addToPbxFileReferenceSection(file);
      project.addToPbxGroup(file, appGroup);
      fs.writeFileSync(projectPath, project.writeSync());
    }
  }
}

if (!only || only === 'android') patchAndroid();
if (!only || only === 'ios') patchIOS();
console.log('Native permissions/store configuration patched.');
