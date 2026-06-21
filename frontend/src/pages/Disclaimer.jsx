import React from 'react';
import LegalLayout, { H2, P, UL } from '@/components/LegalLayout';

export default function Disclaimer() {
  return (
    <LegalLayout title="Disclaimer" updatedOn="Feb 21, 2026">
      <P>
        The information, services, and features provided through DIC Mailer are offered on an
        "as is" and "as available" basis. While we strive to provide reliable email delivery,
        platform availability, and communication services, DIC Mailer does not guarantee
        uninterrupted operation, specific delivery rates, inbox placement, campaign performance,
        or marketing results.
      </P>

      <P>Users are solely responsible for:</P>
      <UL>
        <li>The content of emails sent through the platform.</li>
        <li>Obtaining proper consent from recipients before sending communications.</li>
        <li>Compliance with applicable anti-spam, privacy, data protection, and telecommunications laws.</li>
        <li>Maintaining the accuracy, legality, and ownership of their contact databases.</li>
        <li>Ensuring that all email communications are lawful, ethical, and authorized.</li>
      </UL>

      <P>
        DIC Mailer reserves the right to suspend, restrict, or terminate any account found to
        be involved in spam, phishing, fraud, malware distribution, unauthorized bulk messaging,
        illegal marketing activities, or any misuse of the platform.
      </P>

      <P>
        Email delivery and campaign performance may be affected by factors beyond our control,
        including but not limited to recipient server policies, spam filters, sender reputation,
        domain reputation, internet connectivity, authentication settings (SPF, DKIM, DMARC),
        and third-party service providers.
      </P>

      <H2>Fraud &amp; User Responsibility</H2>
      <P>
        DIC Mailer is a communication and email delivery platform only. DIC Mailer and its team
        do not review, verify, endorse, or take responsibility for the accuracy, legality,
        authenticity, or intent of any email, attachment, content, link, offer, or
        communication sent by users through the platform.
      </P>
      <P>Users are solely responsible for all communications sent through their accounts.</P>
      <P>
        DIC Mailer shall not be liable for any fraudulent, deceptive, misleading, unauthorized,
        or unlawful activities conducted by users, including but not limited to:
      </P>
      <UL>
        <li>Sending misleading or false marketing communications.</li>
        <li>Phishing attempts or impersonation of individuals, organizations, or brands.</li>
        <li>Distribution of malicious links, malware, or harmful content.</li>
        <li>Fraudulent promotions, investment schemes, or financial solicitations.</li>
        <li>Unauthorized use of recipient data or contact information.</li>
        <li>Violation of intellectual property, privacy, or consumer protection laws.</li>
        <li>Any misuse of email communications resulting in financial, legal, or reputational loss.</li>
      </UL>
      <P>
        Any account found engaging in such activities may be suspended or permanently terminated
        without prior notice. DIC Mailer reserves the right to cooperate with law enforcement
        agencies, regulatory authorities, and legal entities when required by applicable laws.
      </P>

      <H2>Limitation of Liability</H2>
      <P>
        To the maximum extent permitted by law, DIC Mailer, its owners, employees, affiliates,
        partners, licensors, and service providers shall not be liable for any direct, indirect,
        incidental, consequential, special, or punitive damages arising from:
      </P>
      <UL>
        <li>Use or inability to use the platform.</li>
        <li>Delayed or failed email delivery.</li>
        <li>Loss of data, revenue, profits, business opportunities, or goodwill.</li>
        <li>Unauthorized access to user accounts.</li>
        <li>Third-party actions or service interruptions.</li>
        <li>User-generated content or communications.</li>
      </UL>
      <P>
        Users assume full responsibility for their use of the platform and all communications
        sent through it.
      </P>

      <H2>Changes to This Disclaimer</H2>
      <P>
        DIC Mailer reserves the right to modify, update, or replace this Disclaimer at any time
        without prior notice. Continued use of the platform after any changes constitutes
        acceptance of the updated Disclaimer.
      </P>

      <P>
        By accessing or using DIC Mailer, you acknowledge that you have read, understood, and
        agreed to the terms outlined in this Disclaimer.
      </P>
    </LegalLayout>
  );
}
