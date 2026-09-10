# BILL4PE — Start Here (Web + Android + iOS)

This ZIP contains the shared BILL4PE web frontend, FastAPI backend and mobile-ready Capacitor configuration.

## Put your backend URL in the app

Inside `frontend/`:

1. Copy `.env.example` to `.env`
2. Set:

```env
REACT_APP_BACKEND_URL=https://YOUR-BACKEND-DOMAIN
REACT_APP_PUBLIC_WEB_URL=https://bill4pe.com
```

The Android/iOS app uses this same backend and therefore the same MongoDB data, accounts, wallet, bills and payment state as the website.

## Generate Android + iOS projects

```powershell
cd frontend
npm install --legacy-peer-deps
npm run mobile:prepare
```

Then:

```powershell
npm run mobile:android
```

For iOS run on a Mac with Xcode:

```bash
npm run mobile:ios
```

Read `frontend/MOBILE_BUILD.md` for Play Store and App Store release steps.

## Important

- Razorpay secret key stays only in `backend/.env`, never in the app/frontend.
- MongoDB URL stays only in `backend/.env`.
- Mobile app needs only the public backend URL.
- `emergentintegrations==0.2.0` has been removed.
