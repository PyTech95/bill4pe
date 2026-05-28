# BILL4PE — Product Requirements Document

## Original Problem Statement
BILL4PE is an AI-powered guided reimbursement and invoice generation PWA — "a smart journey, not a normal expense tracker". Users pick a service category (Food/Travel/Hotel/Stationery/Gift/Pantry/Flower Shop/Grocery/Cleaning/Other), drill into a sub-category, capture items via AI image detection or manual entry, pay merchants via UPI QR scan, auto-capture merchant + txn details, then generate a corporate-grade PDF invoice (₹5 from wallet). Includes wallet, dashboard with filters/reports, and a premium landing page for billforpay.com. Must be installable PWA, mobile-first, offline-capable.

## Architecture
- **Frontend**: React 19 PWA (CRA + craco), react-router v7, Framer Motion, Tailwind + shadcn/ui, html5-qrcode (QR), Lucide icons. Routes: `/` landing, `/login`, `/register`, `/app/*` for authenticated app.
- **Backend**: FastAPI + Motor (async MongoDB), JWT auth (bcrypt + PyJWT), ReportLab for PDF, emergentintegrations (Gemini 3 Flash) for AI vision.
- **Database**: MongoDB collections — `users`, `expenses`, `wallet_txns`, `contact_messages`.
- **PWA**: Manifest, service worker (`/public/sw.js`) caching shell, installable on mobile/desktop.

## User Personas
1. **Sales / Field Professional** — captures meals + cab + client gifts in real-time, files monthly reimbursement reports.
2. **Consultant / Freelancer** — generates per-client expense reports from raw bills.
3. **Startup founder / SMB** — replaces messy WhatsApp receipts with structured invoices.
4. **Finance / CFO** — needs auditable trail (merchant + UPI + geo + txn ID + PDF).

## Core Requirements (static)
- Strict palette: dark navy (#0A1128) + electric lime (#D4FF00) + white + black. No purple, no gradients on white.
- Mobile-first guided flow: each step is a full-screen page, not a form.
- AI vision detects items in food/receipt images with qty + price.
- UPI deep-link (`upi://pay?...`) launches user's UPI app; user enters Txn ID after returning.
- Wallet must auto-deduct ₹5 on bill generation; recharge is mocked for v1.
- PDF must be corporate-grade with merchant, items, total, geo, timestamp.

## What's Been Implemented — 2026-05-28 (P2 features)
- **Receipt OCR for printed bills** (`POST /api/ai/scan-receipt`):
  - Gemini 3 Flash with strong receipt-specific prompt
  - Returns `{merchant_name, date, items[], subtotal, tax, total, category}`
  - Auto-detects category (food/grocery/etc.) from store name
  - Verified with synthetic Saravana Bhavan receipt: extracted all 3 items, GST, total ₹462, category=food correctly
  - Frontend: white "Scan printed bill" card on home page → camera → live scanning overlay with laser animation → auto-fills draft → routes to Editor
- **3-slide Onboarding tour**:
  - Shows on first visit (localStorage `bill4pe_onboarded_v1`)
  - Slides: Snap thali photo (AI Vision) → Speak expense (Voice AI) → Scan printed bill (Receipt OCR)
  - Lime accent dots, smooth slide transitions, Skip + Next/Get started CTAs
- **PWA Install banner**:
  - Floating navy pill above bottom nav, shows when `beforeinstallprompt` fires (Android/desktop Chrome)
  - "Install BILL4PE — Faster access, works offline" + lime Install button
  - Dismiss snoozes for 7 days; hidden permanently if already installed (standalone mode)
  - Both `OnboardingTour` and `PWAInstallBanner` mounted in AppShell so they're available across the whole app

## What's Been Implemented — 2026-05-27 (Post-MVP iteration)
- **Voice expense entry (Whisper + Gemini)**: Big "Speak to log expense" hero card on home page.
  - 30-second MediaRecorder capture → uploads to `POST /api/voice/expense`
  - Backend: OpenAI Whisper (`whisper-1`) transcribes (Hindi/English/Hinglish), Gemini 3 Flash parses transcript to structured JSON
  - Returns `{transcript, category, sub_category, merchant_name, total_amount, items[]}`
  - Auto-fills `bill4pe_draft` in sessionStorage → navigates to `/app/editor` for review → Pay Now
  - Verified backend with real audio (JFK MP3): Whisper transcribed perfectly, Gemini correctly fell back to other/Misc when audio isn't an expense note
  - Frontend: Recording overlay shows red pulse mic + timer (0:00/0:30), Stop & Process button, processing overlay shows transcript + Loader
  - Permission-denied gracefully toasts "Microphone permission denied"
- **Prominent AI "Snap your thali photo" hero card** on SubCategory page (Hindi user request).
  - Lime "AI Magic" badge + large camera icon + royal-blue Capture CTA.
  - Verified end-to-end with real thali image: detected 8 items in <3s.
- Fixed runtime bugs in SubCategory.jsx: missing `RefreshCw` import, undefined `captureLocation` function, missing `geo.status` field.

## What's Been Implemented — 2026-05-27 (MVP v1)
- JWT email/password auth with ₹50 welcome bonus.
- Splash + 10 service categories with sub-categories and icons.
- AI item detection via Gemini 3 Flash (verified with real thali image — backend tests 100% pass).
- Manual entry with AI auto-suggest pills.
- Editable items list with live total + sticky pay bar.
- QR scanner (html5-qrcode) parses UPI URLs; manual fallback for UPI ID + Txn ID.
- Geo capture on Pay screen.
- Expense persistence + dashboard with category & date filters, stats by category, recent bills list.
- Wallet UI with balance card, quick-amount recharge sheet, transaction history.
- Bill generation: deducts ₹5, generates unique B4P bill ID, PDF endpoint streams downloadable reimbursement-ready invoice.
- PDF served via Bearer header OR `?token=` query (for direct downloads).
- Landing page: hero with app mockup, marquee trust strip, How It Works, Features, Vision/Mission, Use Cases, Testimonials, Contact form, Footer.
- PWA: manifest, service worker, installable, theme color.
- Backend: 26/26 tests passing.

## Prioritized Backlog
**P0 (next)**
- Sample data seed for empty dashboard demo experience.
- Better image preview during AI scan (loading state polish).

**P1**
- Real wallet recharge via Razorpay UPI (currently mocked).
- Trip History view (group expenses by date/journey for travel reimbursement).
- Bulk export: download all bills as ZIP / CSV monthly report.
- Email/forward PDF to manager from inside the app.
- Phone OTP authentication via MSG91/Twilio.

**P2**
- Org/team workspaces with admin approval flow.
- Merchant directory (auto-fill name from saved UPI IDs).
- Smart category suggestion based on merchant name.
- Expense limits & policy compliance per category.
- Multi-currency support.

## Next Tasks
- Validate live end-to-end on mobile device (PWA install + camera + QR scan + UPI deep-link).
- Add empty-state illustrations on Dashboard and Wallet.
- Consider Razorpay integration for real wallet top-ups.
