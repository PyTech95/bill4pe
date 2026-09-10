#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const root = path.resolve(__dirname, '..');
process.chdir(root);

function run(cmd) {
  console.log(`\n> ${cmd}`);
  execSync(cmd, { stdio: 'inherit', env: process.env });
}
function exists(p) { return fs.existsSync(path.join(root, p)); }

if (!exists('node_modules')) {
  console.error('\nDependencies are not installed. Run: npm install --legacy-peer-deps\n');
  process.exit(1);
}

const envPath = path.join(root, '.env');
if (!fs.existsSync(envPath)) {
  console.warn('\nWARNING: frontend/.env is missing. Copy .env.example to .env and set REACT_APP_BACKEND_URL before release build.\n');
}

run('npm run build');
if (!exists('android')) run('npx cap add android');
if (!exists('ios')) run('npx cap add ios');
run('npx cap sync');
run('node scripts/patch-native.js');
run('node scripts/mobile-doctor.js');

console.log('\nBILL4PE Android + iOS native projects are prepared.');
console.log('Android: npm run mobile:android');
console.log('iOS:     npm run mobile:ios  (macOS + Xcode required)\n');
