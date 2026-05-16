/**
 * BLT Trading — reply verification worker (Deno Deploy).
 *
 * Fetches the live lookup.txt itself (with 60-second in-memory cache),
 * then validates every $N in the Claude reply against "→ $N" rows.
 * Returns either the original reply or a safe fallback if any
 * quoted dollar amount isn't a real KEY-row price.
 *
 * Wire from Make.com Module 13:
 *   URL:  https://blt-verify.creatoj5-tech.deno.net/
 *   Method: POST
 *   Body content type: application/json
 *   Body input method: JSON string
 *   Body content: {"reply":"{{15.textResponse}}"}
 *   Parse response: Yes
 *   Map final_reply to the response body's `final_reply` field.
 */

const LOOKUP_URL =
  "https://raw.githubusercontent.com/creatoj5-tech/blt-prices/main/lookup.txt";
const FALLBACK =
  "Not on our current buying list — text Yu (909) 664-5589.";
const CACHE_TTL_MS = 60_000;

let cachedLookup: { text: string; fetchedAt: number } | null = null;

async function getLookup(): Promise<string> {
  const now = Date.now();
  if (cachedLookup && now - cachedLookup.fetchedAt < CACHE_TTL_MS) {
    return cachedLookup.text;
  }
  const r = await fetch(LOOKUP_URL, { cache: "no-store" });
  if (!r.ok) {
    // Stale cache is better than nothing; if no cache, throw.
    if (cachedLookup) return cachedLookup.text;
    throw new Error(`lookup fetch failed: ${r.status}`);
  }
  const text = await r.text();
  cachedLookup = { text, fetchedAt: now };
  return text;
}

function ok(payload: Record<string, unknown>): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

Deno.serve(async (request: Request): Promise<Response> => {
  if (request.method !== "POST") {
    return ok({
      final_reply: "BLT verify worker: POST a JSON body with a reply field.",
    });
  }

  let body: { reply?: unknown };
  try {
    body = await request.json();
  } catch {
    return ok({ final_reply: FALLBACK });
  }

  const reply = typeof body.reply === "string" ? body.reply : "";

  if (!reply) {
    return ok({ final_reply: FALLBACK });
  }

  // Pull every "$<digits>" the reply quotes.
  const dollarMatches = reply.match(/\$\d+/g) ?? [];

  // Templates with no price (ADDR / HRS / L / C / E) — pass through.
  if (dollarMatches.length === 0) {
    return ok({ final_reply: reply });
  }

  // Fetch the live lookup (with caching). If this fails, fail safe.
  let lookup: string;
  try {
    lookup = await getLookup();
  } catch {
    return ok({ final_reply: FALLBACK, rejected: true, reason: "lookup_fetch_failed" });
  }

  // Every quoted $N must appear in the lookup as the substring "→ $N".
  // The arrow + space + dollar guard means a fabricated $410 attached
  // to the wrong storage label still fails — the row must terminate
  // with that exact dollar amount on a real KEY line.
  for (const amount of dollarMatches) {
    if (!lookup.includes(`→ ${amount}`)) {
      return ok({
        final_reply: FALLBACK,
        rejected: true,
        missing_amount: amount,
      });
    }
  }

  return ok({ final_reply: reply });
});
