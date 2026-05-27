import React from 'react';
import LegalLayout, { H2, H3, P, UL } from '@/components/LegalLayout';

export default function Privacy() {
  return (
    <LegalLayout title="Privacy Policy" updatedOn="May 27, 2026">
      <P>
        BILL4PE ("we", "us", "our") is operated under the brand billforpay.com. This Privacy
        Policy describes how we collect, use, store and protect personal information when you
        use the BILL4PE mobile app, web app and related services (the "Service").
      </P>

      <H2>1. What we collect</H2>
      <H3>Account information</H3>
      <UL>
        <li>Name, email address, phone number (only the one you provide).</li>
        <li>A password hash (never the raw password).</li>
        <li>Wallet balance and wallet transaction history.</li>
      </UL>
      <H3>Expense & invoice data</H3>
      <UL>
        <li>Items, quantities, prices, total amount and notes you enter.</li>
        <li>Photos of bills/food you upload. Photos are processed by an AI vision model to
            extract items, and may be temporarily stored to deliver the Service.</li>
        <li>Merchant details captured from UPI QR codes (name, UPI ID, transaction ID).</li>
        <li>Approximate location (latitude, longitude) and timestamp at the moment of payment,
            only if you grant browser location permission.</li>
      </UL>
      <H3>Technical data</H3>
      <UL>
        <li>Device, browser, OS and IP-address-derived region for security and abuse prevention.</li>
        <li>Service worker cache state for offline support (stored only on your device).</li>
      </UL>

      <H2>2. How we use your information</H2>
      <UL>
        <li>To deliver the core BILL4PE workflow: detect items, capture payments, generate
            PDF invoices and maintain your expense dashboard.</li>
        <li>To process wallet recharges and bill generation charges (currently mocked in v1).</li>
        <li>To prevent fraud, abuse and unauthorised access.</li>
        <li>To improve our AI models, in aggregate and de-identified form only.</li>
      </UL>

      <H2>3. Sharing</H2>
      <P>
        We do not sell your personal data. We share data only with the following categories of
        processors strictly for delivering the Service:
      </P>
      <UL>
        <li><b>AI vision provider</b> (Google Gemini via Emergent) — receives your uploaded
            image solely to return detected items. No personally identifying account info is sent.</li>
        <li><b>Cloud hosting</b> — to store your account, expenses and PDFs.</li>
        <li><b>Payment gateway</b> (when integrated) — only the transaction info needed to
            process a recharge.</li>
        <li><b>Law enforcement</b> — only when required by a valid legal request.</li>
      </UL>

      <H2>4. Your rights</H2>
      <UL>
        <li><b>Access</b> — request a copy of all data we hold about you.</li>
        <li><b>Correction</b> — update any wrong details in your profile or expenses.</li>
        <li><b>Deletion</b> — request permanent deletion of your account and all associated
            expenses, invoices and wallet history.</li>
        <li><b>Export</b> — download all your expenses as a CSV at any time from the Dashboard.</li>
        <li><b>Withdraw consent</b> — disable location permission, decline photo uploads,
            or revoke account access by logging out.</li>
      </UL>

      <H2>5. Retention</H2>
      <P>
        Expense records and generated invoices are kept as long as your account is active, so
        that your bills remain available for reimbursement claims. Uploaded photos used only
        for AI detection are not retained after item extraction completes. If you delete your
        account, all records are removed within 30 days.
      </P>

      <H2>6. Security</H2>
      <P>
        We use industry-standard practices: encrypted transport (HTTPS), hashed passwords
        (bcrypt), token-based authentication (JWT) and least-privilege access controls. No
        system is perfectly secure — please use a strong unique password and report any
        suspicious activity immediately.
      </P>

      <H2>7. Children</H2>
      <P>
        BILL4PE is intended for users 18 years and older. We do not knowingly collect data
        from minors.
      </P>

      <H2>8. Changes</H2>
      <P>
        We may update this policy from time to time. The "Last updated" date at the top of
        this page reflects the latest revision. Continued use of the Service after an update
        constitutes acceptance of the revised policy.
      </P>

      <H2>9. Contact</H2>
      <P>
        Questions about this policy? Reach us via the contact form on{' '}
        <a href="/#contact" className="text-brand underline">our home page</a>{' '}
        or email <span className="text-brand">privacy@billforpay.com</span>.
      </P>
    </LegalLayout>
  );
}
