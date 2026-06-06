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


## What's Been Implemented — 2026-06-06 (Tagline rollout + .json() audit)
- **Tagline "An Intelligent Billing"** (small italic, slate-400) added below logo in all remaining auth screens:
  - `Login.jsx` (mobile-only logo block — desktop already had it)
  - `Register.jsx` (both desktop sidebar logo and mobile inline logo)
  - `PhoneLogin.jsx` (both desktop sidebar logo and mobile inline logo)
  - Existing locations (AppShell, LegalLayout, Login desktop) confirmed intact.
- **Double `.json()` fetch audit**: Grepped entire `frontend/src` — only ONE `.json()` call exists (`TravelSubCategory.jsx` line 37 — Nominatim reverse-geocode) and it is correctly used (single `await res.json()`). All other API calls use axios via `lib/api.js` which auto-parses JSON. **No actual bug found**; handoff summary was inaccurate.
- Verified visually via screenshot on `/login` and `/register` — tagline renders correctly below logo card.



## What's Been Implemented — 2026-02-28 (Vision/Mission/Ethics official copy)
- Replaced placeholder Vision & Mission copy on Landing page with the **official corporate Vision, Mission and Ethics** content from user's "Vision Mission Ethics-Bill4Pe.docx".
- Layout upgraded from 2-card to **3-card grid** (Vision · Mission · Ethics) inside `#vision` section of `Landing.jsx`.
- Added `Scale` icon (lucide) for Ethics card; data-testids: `vision-card`, `mission-card`, `ethics-card`.
- Section heading updated to "Smart, secure & leakage-free expense management for modern corporates."
- Footer link relabeled "Vision, Mission & Ethics".
- Visually verified via screenshot at `/#vision` — all 3 cards render cleanly side-by-side on desktop, stack on mobile.

## What's Been Implemented — 2026-02-28 (Testing debt cleared)
- Ran `testing_agent_v3_fork` for full regression on the UX polish batch (tagline, splash reorder, datetime, Cash mode).
- **Backend**: 16/16 pytest pass on `/app/backend/tests/test_bill4pe_v2.py` — Phone OTP, auth/me, referrals, Cash payment_method E2E, PDF date+time, PDF tagline "Intelligent Billing", Reports CRUD+PDF, scan-receipt route, voice/expense route, GSTIN auto-print.
- **Frontend**: 100% on tested flows — Landing tagline, Phone OTP login (9999999999 / 123456) → /app, Splash shows 6 categories + VoiceExpense adjacent to ReceiptScan, Dashboard datetime `YYYY-MM-DD HH:MM`, Food/Travel/Hotel subcategory pages render expected fields.
- No critical bugs. Minor optional items logged in ROADMAP (route aliases, referral validate contract, Login default mode).

## What's Been Implemented — 2026-06-03 (UX polish batch)
- **Tagline updated** to "An Intelligent Billing" — visible as the pill on Landing (`Landing.jsx`) and as the sub-title on every generated PDF (`server.py`).
- **Splash AI tool order swapped** — Receipt OCR scanner now appears first, Voice (Whisper) expense entry second (`Splash.jsx`).
- **Date+time everywhere** — Dashboard recent expenses, Reports page (Expenses tab + Reports tab), single-bill PDF header, multi-bill report PDF header, and Items table now show `YYYY-MM-DD HH:MM` instead of just `YYYY-MM-DD`. (`Dashboard.jsx`, `Reports.jsx`, `server.py`)
- **Cash payment mode** added to PayNow:
  - New Payment Mode toggle ("UPI / QR" vs "Cash") with `data-testid=paymode-upi-btn` / `paymode-cash-btn`.
  - Scanner stage now has a "Pay in Cash" shortcut (`data-testid=pay-cash-skip-btn`) that bypasses QR scanning.
  - In Cash mode: UPI ID becomes optional, UPI app picker card is hidden, transaction ID becomes "Receipt # (optional)", confirm button reads "Mark Cash Paid".
  - Backend `PaymentInfo.payment_method` documents the new "Cash" value; merchant_upi & transaction_id remain Optional so Cash submissions validate cleanly.
  - PDF "Payment Method" row reflects "Cash" correctly.
- Backend regression: 41/42 pytest pass (`/app/backend/tests/test_bill4pe_v2.py`) — Cash E2E, GSTIN auto-print, PDF date+time, tagline, voice/receipt endpoints all verified. Single failure is a pre-existing missing-fixture (`/tmp/thali.jpg`), not a code regression.


## What's Been Implemented — 2026-02-28 (PayNow UPI app picker)
- Replaced single generic "Pay via UPI App" button (which silently opened only the default UPI app — typically WhatsApp Pay on Android) with a 2-column app picker grid in `PayNow.jsx`.
- User now explicitly chooses: Google Pay (`tez://upi/pay`), PhonePe (`phonepe://pay`), Paytm (`paytmmp://pay`), BHIM (`bhim://upi/pay`), Amazon Pay (`amazonpay://upi/pay`), WhatsApp (`whatsapp://pay`), or Other UPI (`upi://pay` Android chooser).
- Each button uses brand-specific colors and the app's deep-link scheme to bypass Android's default-app behaviour.
- Smoke-tested in preview at `/app/pay` — picker renders all 7 buttons with merchant + total intact.


## What's Been Implemented — 2026-02-28 (PayNow in-app browser detection)
- Detect WhatsApp / Instagram / Facebook / iOS WKWebView in PayNow.jsx and show amber warning banner immediately on entry.
- 9-second hard timeout on `getUserMedia` probe — if camera never responds (typical iOS WhatsApp behaviour), auto-switch to `inapp` status with overlay + "Enter UPI Manually" CTA.
- "Copy link & open in Safari" button — copies current URL so user can paste in real browser.
- "Camera not opening?" inline link visible during "Starting camera…" state (no longer blocks pointer events).
- Eliminates infinite "STARTING CAMERA…" spinner reported when app is opened from WhatsApp link on iPhone.

## What's Been Implemented — 2026-05-28 (Grocery / Pantry / Stationery specialised AI)
- **Category-aware AI image prompts** added in backend:
  - **GROCERY_PROMPT**: detects Aashirvaad Atta, Toor Dal, Tata Salt, Sunflower Oil, Parle-G etc. with brand + pack size + realistic INR retail prices
  - **PANTRY_PROMPT**: detects Nescafé, Bru, Tata Tea, Britannia Marie Gold, Bisleri, Lays etc. — office break-room SKUs
  - **STATIONERY_PROMPT**: detects pens, notebooks, A4 reams, markers, file folders, printer cartridges
  - `_category_prompt()` helper routes correctly per category
- **Frontend AI hero copy is now category-aware** via `AI_COPY` map in SubCategory.jsx — title, accent items list, and CTA all change per category (e.g. "Snap your grocery haul" / "Capture grocery items" / "Atta, Rice, Dal, Oil, Spices, Sugar")
- **Sub-category lists upgraded** in categories.js with richer, more useful options:
  - Grocery: Atta/Rice/Dal, Oil/Ghee/Spices, Vegetables/Fruits, Dairy/Eggs, Snacks/Beverages, Household/Cleaning, Daily Top-up, Weekly Bulk
  - Pantry: Tea & Coffee, Snacks & Biscuits, Beverages & Water, Milk & Dairy, Sugar & Sweetener, Disposables
  - Stationery: Office Supplies, Printing, Notebooks, Pens & Markers, Files & Folders, Printer Cartridge
  - Gift: Client Gift, Employee Reward, Festive Hamper, Anniversary, Birthday
  - Flower: Bouquet, Decoration, Plants, Garlands
  - Cleaning: Housekeeping Service, Cleaning Supplies, Pest Control, Laundry
  - Other: Misc, Repairs & Maintenance, Subscriptions, Internet & Phone, Courier
- Verified end-to-end with synthetic grocery + pantry images: 6/6 items correctly detected with brand names + pack sizes + accurate INR prices for both categories.

## What's Been Implemented — 2026-05-28 (Hotel category redesigned)
- **Dedicated HotelSubCategory page** (separate route `/app/category/hotel`):
  - Sub-categories now Room Types: **Standard Room (default)**, Deluxe Room, Suite, Family Room, Dormitory, Other
  - **Check-in** auto-set to today (read-only "Today (auto)" badge)
  - **Check-out** picks from native date input (calendar), defaults to today+1, auto-bumps if check-in changes
  - **Hotel name** input
  - **Per-night rate** input
  - Live **Booking Summary** card: Nights · Room · Rate/night · **TOTAL** (nights × rate) — updates in real time
  - Notes voice mic + GPS + Pay Now bar
- **Backend `PaymentInfo.stay`** (StayInfo) added: hotel_name, room_type, check_in, check_out, nights, per_night_rate, nature_of_business
- **Bill PDF** now renders a dedicated **STAY DETAILS** table (7 rows: hotel, room type, in/out dates, nights, rate, total) with lime-highlighted Total Amount cell, only when expense has stay metadata
- End-to-end tested: 2-night Deluxe Room stay at Taj Palace → expense + bill → PDF text confirms all stay fields + merchant details + notes

## What's Been Implemented — 2026-05-28 (Travel category redesigned)
- **Dedicated TravelSubCategory page** (separate route `/app/category/travel`) — completely different flow from Food:
  - Sub-categories reordered: **Auto Booking (default)**, E-Rickshaw, Bike, Cab, Bus, Taxi, Self Booking, Flight, Train, Toll (flight/train moved to bottom)
  - **AI photo capture removed** (irrelevant for travel)
  - **Items table removed**
  - New **Destination block**: From (auto-filled from GPS via OpenStreetMap Nominatim reverse-geocode), To, Amount inputs
  - **Two-point GPS**: Pickup point captured on page load; Dropping point captured on Pay Now click
  - Live "Nature of business on bill" preview that updates with selected service ("Auto Driver", "Cab Driver", "Airline" etc.)
  - Notes voice mic retained
- **Backend `PaymentInfo`** extended with optional `trip: TripInfo` nested model (from_text, to_text, pickup_lat/lng, drop_lat/lng, nature_of_business)
- **Bill PDF** now renders dedicated TRIP DETAILS block + Picking Point / Dropping Point GPS table for travel-category expenses; uses `trip.nature_of_business` when present
- End-to-end tested: travel expense with full trip metadata → PDF extracted text confirms all fields render correctly

## What's Been Implemented — 2026-05-28 (SubCategory redesign per user feedback)
- **Auto-select sub-category by time of day** (Food only): Breakfast (5-11AM), Lunch (11AM-4PM), Snacks (4-8PM), Dinner (8PM-5AM).
- **Merchant entry block removed completely** from SubCategory page. Merchant details are now captured ONLY on PayNow page via QR scan (which is where it logically belongs — at point of payment).
- **Notes field added** with prominent "Speak" mic button — uses existing `/api/voice/expense` endpoint, takes only the transcript, appends to notes textarea (500 char limit, char counter shown).
- **Bill PDF improved**:
  - "Business Type" relabeled to "Nature of Business" with full label (e.g. "Food / Lunch")
  - New "NOTES" section in PDF that prints user-entered notes (line-break preserved)
- Tested end-to-end: created expense with notes via API → generated bill (₹5 deducted from wallet) → PDF extracted text confirms all 7 merchant fields + items + total + notes correctly printed.

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

## Update — Feb 2026 (PayNow camera UX)
- Removed prominent "Enter UPI Manually" shortcut buttons from `PayNow.jsx` (top-of-page CTA + inside "Starting camera…" overlay) per user request — focus is on the camera actually opening.
- Increased camera watchdog timeout from 5s to **15s** so iOS Safari has enough time to render its native permission prompt and for the user to tap *Allow* before the page shows a false-failure overlay.
- Added a primary **"Retry Camera"** button in the error overlay (replaces the manual-entry CTA). Manual entry is now a tiny secondary text link inside the error overlay only — never on the happy path.
- Removed unused `KeyRound` import.
- File touched: `/app/frontend/src/pages/app/PayNow.jsx`.
- Production note: user must redeploy to `ai-payment-workflow.emergent.host` to see these fixes live.


## Update — Feb 2026 (P0 Paytm-style UI Redesign — VERIFIED)
- Applied massive UI/UX overhaul to a modern fintech Paytm-style look:
  - Light cream/white backgrounds, **dark navy `#0A1128`** as primary accent, **electric lime `#D4FF00`** as highlight.
  - Rounded buttons (pill / xl-rounded), white cards on cream bg, no purple gradients.
- Files touched: `frontend/src/index.css`, `frontend/src/pages/Landing.jsx` (Vision/Mission/Ethics + marquee + Contact "Ujjwal"), `frontend/src/lib/categories.js` (auto icon for travel), `frontend/src/components/ReceiptScan.jsx` (Rescan button reorder), `frontend/src/pages/app/Splash.jsx`.
- Regression run via `testing_agent_v3_fork` → **iteration_5.json — 100% pass on all 13 verification points** (Landing theme, Phone OTP login, Splash home, Food/Travel/Hotel sub-category pages, Dashboard date-time format, Wallet, PayNow render, bottom-nav, zero React errors).
- Minor cosmetic notes (non-blocking) flagged for future polish: Landing.jsx is 750 lines — candidate for component split (Hero/HowItWorks/Features/VisionMission/UseCases/Contact/Footer).


## Update — Feb 2026 (P1 PDF Bill upgrade + GSTIN + Wallet copy — DONE)
- **PDF Bill upgrade (P1) — VERIFIED via curl + pdfplumber on live preview-generated bill:**
  - Bill ID format: `B4P-YYYYMMDD-XXXXXX` (e.g. `B4P-20260604-9C17A4`). ✓
  - Tagline below logo: `An Intelligent Billing — Scan QR to verify authenticity`. ✓
  - QR code on every PDF (verify URL `/api/bills/verify/{bill_id}`). ✓
  - GSTIN + Company Name auto-print in "BILLED TO" when set. ✓
- **Share options (P1) — NEW** in `frontend/src/pages/app/BillGen.jsx`:
  - WhatsApp share button (`share-whatsapp-btn`) opens `wa.me` with pre-filled invoice message + link.
  - Email share button (`share-email-btn`) opens `mailto:` with subject + body containing Bill ID, amount, txn ID, download link.
- **GSTIN field in Profile (P2) — NEW** in `frontend/src/pages/app/Profile.jsx`:
  - Added Company name + GSTIN inputs (auto-uppercase, 15-char limit) wired to `PUT /api/auth/me`. End-to-end verified.
- **Wallet credit clarification (P2)** — added explanatory line in `Wallet.jsx`: *"Prepaid pool · auto-adjusted against ₹5 convenience fee per generated bill. New users get ₹50 free credit."*

## Still pending
- P1: Refactor `server.py` (~1650 lines) into `routers/{auth,expenses,ai,pdf,wallet}.py`.
- P1: "Forward to Manager" via Resend — blocked on API key.
- P2: "Quick Re-stock" favourites list for Pantry/Grocery.
- P3: Empty-state illustrations, Org/team workspaces, Razorpay real wallet top-up (blocked on keys).
