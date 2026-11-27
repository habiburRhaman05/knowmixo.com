import type { Metadata } from "next";
import Link from "next/link";
import { Logo } from "@/components/ui/icon-logo";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "How Knowmivo collects, uses, and protects your data.",
};

const EFFECTIVE_DATE = "November 27, 2026";

export default function PrivacyPolicyPage() {
  return (
    <main className="min-h-screen bg-background">
      <header className="border-b border-border">
        <div className="container flex h-16 items-center justify-between">
          <Link href="/" aria-label="Knowmivo home" className="flex items-center gap-2">
            <Logo withWordmark />
          </Link>
          <nav className="flex gap-6 text-sm text-muted-foreground">
            <Link href="/terms" className="hover:text-foreground">
              Terms
            </Link>
            <Link href="/login" className="hover:text-foreground">
              Sign in
            </Link>
          </nav>
        </div>
      </header>

      <div className="container max-w-3xl py-12">
        <h1 className="text-3xl font-bold tracking-tight">Privacy Policy</h1>
        <p className="mt-2 text-sm text-muted-foreground">Effective date: {EFFECTIVE_DATE}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          This is a working draft covering our current data practices. Have counsel review before relying on it for compliance sign-off.
        </p>

        <Section title="1. Who we are">
          <p>
            Knowmivo ("Knowmivo," "we," "us") provides an AI-powered chat assistant that companies ("Owners")
            embed on their websites to answer questions using their own knowledge base. This policy explains
            how we collect, use, and share information when Owners use our dashboard and when end users
            ("Visitors") chat with an Owner&apos;s assistant.
          </p>
        </Section>

        <Section title="2. Information we collect">
          <ul className="list-disc space-y-1 pl-5">
            <li><strong>Account information:</strong> name, email address, and password hash (or Google account identifier) when an Owner signs up.</li>
            <li><strong>Knowledge content:</strong> documents, URLs, and text an Owner uploads to power their assistant.</li>
            <li><strong>Conversation data:</strong> messages exchanged between Visitors and an assistant, including any contact details a Visitor voluntarily submits through a lead form.</li>
            <li><strong>Usage and diagnostic data:</strong> IP address, browser/device information, timestamps, and product analytics events (e.g., which features are used) needed to operate and secure the service.</li>
            <li><strong>Billing information:</strong> payment details are collected and processed directly by Stripe; we store subscription status and invoice records, never raw card numbers.</li>
          </ul>
        </Section>

        <Section title="3. How we use information">
          <ul className="list-disc space-y-1 pl-5">
            <li>To operate, maintain, and improve the assistant and dashboard.</li>
            <li>To generate AI responses, which may involve sending Visitor messages and relevant knowledge-base excerpts to our AI model providers (see Section 6).</li>
            <li>To detect and respond to safety-critical situations (for example, language suggesting a visitor may be in danger), including notifying the Owner's team.</li>
            <li>To send account-related email: verification, password reset, team invitations, billing receipts, and service alerts.</li>
            <li>To monitor for abuse, enforce our Terms, and keep the service secure.</li>
          </ul>
        </Section>

        <Section title="4. AI-generated content">
          <p>
            Visitor messages are processed by large language model providers to generate answers grounded in
            the Owner&apos;s knowledge base. Responses are AI-generated and may be incorrect; see the
            disclosure shown in every chat session. We do not use Visitor conversation content to train
            third-party foundation models.
          </p>
        </Section>

        <Section title="5. Sharing of information">
          <p>We share information only as follows:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>With the Owner of the assistant a Visitor is chatting with (an Owner can see transcripts and any contact details submitted through their assistant).</li>
            <li>With service providers who process data on our behalf under contract — see our subprocessor list below.</li>
            <li>When required by law, to protect our rights, or to prevent harm.</li>
            <li>In connection with a merger, acquisition, or sale of assets, with notice to affected Owners.</li>
          </ul>
          <p className="mt-2">We do not sell personal information.</p>
        </Section>

        <Section title="6. Subprocessors">
          <p>We use the following categories of service providers to operate Knowmivo:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li><strong>Hosting &amp; database:</strong> Neon (PostgreSQL), Upstash/Redis</li>
            <li><strong>AI model providers:</strong> Groq, Cloudflare Workers AI (embeddings, reranking)</li>
            <li><strong>Vector search:</strong> Pinecone</li>
            <li><strong>Payments:</strong> Stripe</li>
            <li><strong>Messaging channels (where connected by an Owner):</strong> Meta (WhatsApp, Messenger, Instagram), Slack, Twilio</li>
            <li><strong>Email delivery:</strong> our SMTP provider</li>
            <li><strong>Error monitoring:</strong> Sentry</li>
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">
            This list reflects providers configured in our infrastructure as of the effective date above.
          </p>
        </Section>

        <Section title="7. Data retention">
          <p>
            Conversation data is retained for 30 days by default, after which it is eligible for deletion.
            Account data is retained until an Owner deletes their account, at which point associated company
            data is purged per our deletion process.
          </p>
        </Section>

        <Section title="8. Your rights (California / CCPA-CPRA and other US state laws)">
          <p>
            Depending on where you live, you may have the right to request access to, deletion of, or a copy
            of your personal information, and to opt out of certain uses. Owners can export or delete their
            account data from Settings. Visitors who want to exercise these rights for information held about
            them should contact the Owner of the assistant they used, or email us at{" "}
            <a className="underline" href="mailto:privacy@knowmivo.com">privacy@knowmivo.com</a>.
          </p>
        </Section>

        <Section title="9. Children's privacy">
          <p>
            Knowmivo is not directed to children under 13, and we do not knowingly collect personal
            information from children under 13. Owners are responsible for ensuring their own use of an
            assistant complies with COPPA if their website is directed to children.
          </p>
        </Section>

        <Section title="10. Health information">
          <p>
            Knowmivo is not a HIPAA-covered entity or business associate and is not intended for the
            transmission of protected health information (PHI). Owners in healthcare-adjacent industries
            should not configure their assistant to collect or process PHI.
          </p>
        </Section>

        <Section title="11. Security">
          <p>
            We use industry-standard safeguards including encryption in transit, encryption at rest for
            sensitive secrets, tenant-isolated data access, and multi-factor authentication for Owner accounts.
            No system is 100% secure, and we cannot guarantee absolute security.
          </p>
        </Section>

        <Section title="12. Changes to this policy">
          <p>
            We may update this policy from time to time. Material changes will be announced via email or an
            in-app notice before they take effect.
          </p>
        </Section>

        <Section title="13. Contact us">
          <p>
            Questions about this policy? Email{" "}
            <a className="underline" href="mailto:privacy@knowmivo.com">privacy@knowmivo.com</a>.
          </p>
        </Section>
      </div>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      <div className="mt-2 space-y-2 text-sm leading-relaxed text-muted-foreground">{children}</div>
    </section>
  );
}
