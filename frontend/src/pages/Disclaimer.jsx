import React from 'react';
import LegalLayout, { H2, P, UL } from '@/components/LegalLayout';

export default function Disclaimer() {
  return (
    <LegalLayout title="Disclaimer" updatedOn="Feb 21, 2026">
      <P>
        The information, services, and features provided through BILL4PE are offered on an
        &ldquo;as is&rdquo; and &ldquo;as available&rdquo; basis. While we strive to provide
        reliable expense capture, invoice generation, and payment workflows, BILL4PE does not
        guarantee uninterrupted operation, specific reimbursement outcomes, tax compliance,
        merchant authenticity, or financial accuracy of user-supplied data.
      </P>

      <P>Users are solely responsible for:</P>
      <UL>
        <li>The accuracy, legitimacy, and supporting evidence of every expense entry, item list, and invoice generated through the platform.</li>
        <li>Verifying merchant details, UPI identifiers, and payment confirmations before transacting.</li>
        <li>Compliance with applicable tax, GST, reimbursement, anti-fraud, privacy, and data-protection laws of their jurisdiction and employer policies.</li>
        <li>Maintaining the accuracy of profile information, GSTIN, and company affiliation declared in the app.</li>
        <li>Ensuring that all bills submitted for reimbursement are authentic, lawful, and authorised.</li>
      </UL>

      <P>
        BILL4PE reserves the right to suspend, restrict, or terminate any account found to be
        involved in invoice fabrication, reimbursement fraud, payment misuse, identity
        impersonation, or any other misuse of the platform.
      </P>

      <P>
        Payment processing, OCR recognition, AI item extraction, voice transcription, UPI
        routing, and bill verification may be affected by factors beyond our control, including
        bank/UPI provider availability, image quality, network connectivity, third-party AI
        accuracy, and authentication settings.
      </P>

      <H2>Fraud &amp; User Responsibility</H2>
      <P>
        BILL4PE is a digital expense capture and invoice generation platform only. BILL4PE and
        its team do not review, verify, endorse, or take responsibility for the accuracy,
        legality, authenticity, or intent of any expense, receipt, item, merchant, transaction,
        or bill recorded by users through the platform.
      </P>
      <P>Users are solely responsible for all entries and bills generated under their accounts.</P>
      <P>
        BILL4PE shall not be liable for any fraudulent, deceptive, misleading, unauthorised,
        or unlawful activities conducted by users, including but not limited to:
      </P>
      <UL>
        <li>Fabricating expenses, inflating amounts, or duplicating receipts for reimbursement.</li>
        <li>Impersonation of merchants, employees, or organisations.</li>
        <li>Sending falsified invoices to managers, finance teams, or third parties.</li>
        <li>Misuse of UPI QR scanning to mislead payers or payees.</li>
        <li>Unauthorised use of company wallet funds, GSTIN, or workspace privileges.</li>
        <li>Violation of intellectual property, privacy, tax, or consumer-protection laws.</li>
        <li>Any misuse of generated PDFs resulting in financial, legal, or reputational loss.</li>
      </UL>
      <P>
        Any account found engaging in such activities may be suspended or permanently
        terminated without prior notice. BILL4PE reserves the right to cooperate with law
        enforcement agencies, regulatory authorities, and legal entities when required by
        applicable laws.
      </P>

      <H2>Limitation of Liability</H2>
      <P>
        To the maximum extent permitted by law, BILL4PE, its owners, employees, affiliates,
        partners, licensors, and service providers shall not be liable for any direct,
        indirect, incidental, consequential, special, or punitive damages arising from:
      </P>
      <UL>
        <li>Use or inability to use the platform.</li>
        <li>Delayed, failed, or duplicate UPI payments.</li>
        <li>Loss of data, revenue, profits, business opportunities, or goodwill.</li>
        <li>Unauthorised access to user accounts or wallets.</li>
        <li>Third-party actions or service interruptions (banks, UPI providers, AI APIs, etc.).</li>
        <li>User-generated content, entries, bills, or communications.</li>
      </UL>
      <P>
        Users assume full responsibility for their use of the platform and all bills and
        payments processed through it.
      </P>

      <H2>Changes to This Disclaimer</H2>
      <P>
        BILL4PE reserves the right to modify, update, or replace this Disclaimer at any time
        without prior notice. Continued use of the platform after any changes constitutes
        acceptance of the updated Disclaimer.
      </P>

      <P>
        By accessing or using BILL4PE, you acknowledge that you have read, understood, and
        agreed to the terms outlined in this Disclaimer.
      </P>
    </LegalLayout>
  );
}
