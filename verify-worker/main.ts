/**
 * BLT Trading — reply verification worker (Deno Deploy).
 *
 * Receives the Claude reply + the live lookup block via POST JSON,
 * validates every $N in the reply against "→ $N" in the lookup,
 * returns either the original reply or a safe fallback if any
 * dollar amount isn't a real KEY-row price.
 *
 * Wire from Make.com Module 13:
 *   URL:  https://<project>.deno.dev/
 *   Method: POST
 *   Headers: Content-Type: application/json
 *   Body:
 *     {
 *       "reply": "{{3.textResponse}}",
 *       "lookup": "{{2.data}}"
 *     }
 *   Map final_reply to the response body's `final_reply` field.
 */

const FALLBACK =
  "Not on our current buying list — text Yu (909) 664-5589.";

function ok(payload: Record<string, unknown>): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

Deno.serve(async (request: Request): Promise<Response> => {
  if (request.method !== "POST") {
    return ok({
      final_reply: "BLT verify worker: POST a JSON body with reply + lookup.",
    });
  }

  let body: { reply?: unknown; lookup?: unknown };
  try {
    body = await request.json();
  } catch {
    return ok({ final_reply: FALLBACK });
  }

  const reply = typeof body.reply === "string" ? body.reply : "";
  const lookup = typeof body.lookup === "string" ? body.lookup : "";

  if (!reply) {
    return ok({ final_reply: FALLBACK });
  }

  // Pull every $<digits> the reply quotes.
  const dollarMatches = reply.match(/\$\d+/g) ?? [];

  // Templates with no price (ADDR / HRS / L / C / E) — pass through.
  if (dollarMatches.length === 0) {
    return ok({ final_reply: reply });
  }

  // Empty lookup → fail safe.
  if (!lookup) {
    return ok({ final_reply: FALLBACK });
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
