# BILL4PE — Web + Backend deployment (2026-09-10)

This release is for the web frontend + shared backend. The existing `frontend/android` and `frontend/ios` folders are deliberately left unchanged in this release. Use this exact web/backend baseline later when making the native-app copy.

## 1. Before pushing from Windows

Keep `.env` files out of Git. From the project root:

```powershell
cd C:\Users\Dheeraj\pytech\bill4pe-main

git status
git add .
git commit -m "Fix voice photo payment recovery and corporate bill charges"
git push
```

If your local folder was created from this ZIP rather than an existing clone, copy/merge the files into your Git clone first, then run the commands above.

## 2. Production backend environment

Do NOT replace the server's working `.env`. Confirm these values exist as appropriate:

```env
MONGO_URL=...
DB_NAME=...
JWT_SECRET=...
CORS_ORIGINS=https://bill4pe.com,https://www.bill4pe.com,https://localhost,capacitor://localhost

GEMINI_API_KEY=...
RAZORPAY_KEY_ID=...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...

# Production phone OTP
OTP_MODE=live
MSG91_AUTH_KEY=...
MSG91_TEMPLATE_ID=...
OTP_EXPIRY_MINUTES=5
```

Do not put live secrets in GitHub.

## 3. Pull and build on VPS

```bash
cd /var/www/bill4pe
git status
git pull

cd /var/www/bill4pe/backend
./venv/bin/pip install -r requirements.txt
python -m compileall -q .

cd /var/www/bill4pe/frontend
npm install --legacy-peer-deps
npm run build
```

The production frontend `.env` should continue to contain:

```env
REACT_APP_BACKEND_URL=https://bill4pe.com
REACT_APP_PUBLIC_WEB_URL=https://bill4pe.com
```

## 4. Restart the BILL4PE backend

This server previously used direct Uvicorn on port 8000 rather than a systemd unit.

```bash
cd /var/www/bill4pe/backend
fuser -k 8000/tcp || true
sleep 2
nohup ./venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
sleep 3
curl http://127.0.0.1:8000/api/
```

Live log:

```bash
tail -f /var/www/bill4pe/backend/backend.log
```

## 5. Production checks before inviting users

- Super Admin > Settings: set Individual and Corporate Bill Generation Charges (for example 1% and 2%). Corporate admin + employee bills use the Corporate percentage and debit the central company wallet. 0% waives the charge.
- Corporate admin: recharge the central company wallet through Razorpay and confirm the balance updates once.
- Corporate employee: log in with 6-digit Employee Code + 6-digit PIN; create/approve a bill and confirm the configured corporate charge is deducted only once.
- Voice: test English, Hindi and Hinglish. Confirm spoken text appears even if audio-AI parsing fails.
- Photo item identification: test food, stationery and a general product photo; identified products with no visible price should still appear for review with price 0.
- Payment receipt: upload a successful receipt, verify amount + UTR, then simulate/retry bill generation. It must reuse the protected payment instead of asking to discard/pay again.
- Confirm Replace Receipt / Start New Payment only operate on unverified attempts; verified/fee-paid/generated transactions are protected.
- Confirm `OTP_MODE=live` before real users; no demo `123456` flow in production.

## 6. Native app

Do not run a native release from this package as the client-feedback app-layer pass has not been applied yet. When requested, create a separate app copy from this exact web/backend baseline, then sync Capacitor and rebuild APK/AAB.
