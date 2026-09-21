import { useState } from "react";
import { type InboundMail } from "../services/api";
import { formatIst } from "../utils/datetime";

function decodeEntities(text: string): string {
  return text
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

function stripHtml(html: string): string {
  return decodeEntities(
    html
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>/gi, "\n")
      .replace(/<[^>]+>/g, "")
      .replace(/\r\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim()
  );
}

function isHtml(text: string): boolean {
  return /<[a-z][\s\S]*>/i.test(text);
}

export function InboundMailPanel({ mail }: { mail: InboundMail }) {
  const [view, setView] = useState<"plain" | "html" | "raw">("plain");
  const bodyIsHtml = isHtml(mail.mail_body);
  const plainBody = bodyIsHtml ? stripHtml(mail.mail_body) : decodeEntities(mail.mail_body);

  return (
    <section className="bg-white border border-hairline rounded-md p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h2 className="font-display font-semibold">Received Email (Zoho Webhook)</h2>
        <div className="flex gap-1">
          {(["plain", "html", "raw"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setView(mode)}
              className={`px-2 py-1 text-xs font-mono rounded capitalize ${
                view === mode ? "bg-own text-white" : "border border-hairline hover:bg-own-tint"
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      <dl className="grid md:grid-cols-2 gap-x-6 gap-y-2 font-mono text-sm mb-4">
        <div>
          <dt className="text-ink-soft text-xs uppercase">From</dt>
          <dd className="break-all">{decodeEntities(mail.mail_from || "") || "—"}</dd>
        </div>
        <div>
          <dt className="text-ink-soft text-xs uppercase">To</dt>
          <dd className="break-all">{decodeEntities(mail.mail_to || "") || "—"}</dd>
        </div>
        <div className="md:col-span-2">
          <dt className="text-ink-soft text-xs uppercase">Subject</dt>
          <dd>{decodeEntities(mail.mail_subject || "") || "—"}</dd>
        </div>
        <div>
          <dt className="text-ink-soft text-xs uppercase">Message ID</dt>
          <dd className="break-all text-xs">{mail.mail_message_id || "—"}</dd>
        </div>
        <div>
          <dt className="text-ink-soft text-xs uppercase">Received</dt>
          <dd>{mail.received_at ? formatIst(mail.received_at) : "—"}</dd>
        </div>
      </dl>

      <div className="border border-hairline rounded-md bg-paper p-3 max-h-72 overflow-y-auto">
        {view === "plain" && (
          <pre className="text-sm whitespace-pre-wrap font-sans">{plainBody || "(empty body)"}</pre>
        )}
        {view === "html" && bodyIsHtml && (
          <div
            className="text-sm prose prose-sm max-w-none"
            dangerouslySetInnerHTML={{ __html: mail.mail_body }}
          />
        )}
        {view === "html" && !bodyIsHtml && (
          <pre className="text-sm whitespace-pre-wrap font-sans">{mail.mail_body || "(empty body)"}</pre>
        )}
        {view === "raw" && (
          <pre className="text-xs whitespace-pre-wrap font-mono">{mail.mail_body || "(empty body)"}</pre>
        )}
      </div>
    </section>
  );
}
