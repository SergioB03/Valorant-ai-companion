# Security

## Reporting an issue

Found something? Open a [GitHub issue](https://github.com/SergioB03/Valorant-ai-companion/issues)
for anything non-sensitive, or use GitHub's **private vulnerability reporting**
(Security tab → *Report a vulnerability*) if disclosing it publicly would put
users at risk. I'll respond as quickly as I can — this is a solo project, so
please allow a few days.

Please don't run load tests, credential-stuffing, or automated scanners against
the live site. Every AI request costs me real money, and the abuse controls
below will simply lock you out.

---

## What this document is

This project started as a "vibe-coded" side project — built fast, with real
enthusiasm and very little security knowledge. Then it went on the public
internet with an API key attached to a credit card.

What follows is an honest record of what was wrong, how it was found, and what
fixed it. Every issue listed here is **fixed and deployed**. It's published
because the mistakes are ordinary ones — the kind almost every self-taught
developer makes on their first deployment — and reading about them beforehand is
considerably cheaper than discovering them the way I did.

If you're shipping your first real app, the *Lesson* lines are the part worth
your time.

---

## Findings

### 1. Private coach conversations were readable by anyone

**Severity: critical.** `GET /mental/profile/{name}/{tag}` was unauthenticated
and returned the full text of Mental Coach conversations for any Riot ID.

The root cause was a data-modelling mistake, not a missing auth check.
Conversations were stored keyed by the *searched* player's Riot ID — but the
person typing is not the person being searched, because anyone can look up
anyone. So one visitor's candid messages about tilting were filed under a
stranger's gamertag, where the next visitor could read them back.

There was a second, quieter path: the coach prompt loaded those same stored
rows as "previous conversation," so a stranger's words were narrated back to
whoever searched that player next — no API call required.

**Fixed by:** the endpoint now returns only counts and timestamps; the server
stores no conversation text at all; a migration nulls anything previously
stored; and conversation context is supplied by the browser having the
conversation, so it is scoped to the right person.

> **Lesson:** ask *"whose data is this, and what identifies them?"* before
> choosing a database key. A key that looks unique can still be the wrong
> subject entirely. And when a feature is optional, deleting the data beats
> securing it.

### 2. An open relay to a paid AI account

**Severity: critical.** A `POST /claude/ask` endpoint forwarded arbitrary user
text straight to Claude — no system prompt, no filtering, no authentication —
on a public URL. Nothing in the app ever called it; it was left over from early
development. Anyone who found it could spend the owner's API credits and steer
the model wherever they liked, with the account holder responsible for the
output under the provider's terms.

**Fixed by:** deleting the route, and removing the README lines that advertised
it. Every remaining endpoint wraps user input in a purpose-built prompt.

> **Lesson:** debug endpoints don't stay private just because they're
> undocumented. Delete them before you go public — and remember that your own
> README is a map for anyone looking.

### 3. Rate limits that silently didn't work

**Severity: high.** The API used per-IP rate limiting, and it was configured
incorrectly in a way that produced *no error and no warning*.

The library's default keying strategy builds each limit bucket from the
**concrete request path**. Every expensive endpoint takes the player name in the
path, so `/analyze/playerA/tag` and `/analyze/playerB/tag` were counted as
entirely separate quotas. Changing one character in the URL reset the counter.

It was found by accident: a sloppy test used a different player name each time
and *every* request passed a limit that should have blocked most of them.

**Fixed by:** keying limits on the view function instead of the URL. Verified by
measurement — 25 requests to one path now yield 15 allowed and 10 blocked, where
varying the path previously allowed all of them.

> **Lesson:** a security control you haven't *tested by attacking it* is a
> guess. This one looked correct in code review, in the config, and in the
> documentation. Only a deliberate attempt to bypass it revealed the truth.

### 4. No ceiling on spending

**Severity: high.** Per-request rate limits cap how fast *one* visitor can
spend. They do not cap the total. With an AI call behind several endpoints,
there was no upper bound on a day's bill — from traffic, abuse, or a bug in the
app's own code.

**Fixed by:** a daily spend ceiling enforced at the single function every AI
call passes through. Once the day's estimated spend crosses the limit, AI
endpoints return a friendly 503 until midnight UTC, and the operator is alerted
at 80%.

Placing the check at one chokepoint rather than decorating each route was
deliberate — an earlier per-route approach had already missed an endpoint.

> **Lesson:** put safety checks where the money is actually spent, not on each
> caller. Callers multiply; the chokepoint doesn't. And set a hard limit in your
> provider's billing console too — that's the only one your own bugs can't
> defeat.

### 5. The fix for #4 became a denial-of-service

**Severity: high.** A single shared budget with no per-visitor allowance means
one person can consume all of it. Measured against the then-current limits, one
address could exhaust a day's budget in **under nine minutes** and leave every
other user with errors until midnight — at no cost to the attacker.

**Fixed by:** giving each source its own daily allowance underneath the global
cap. Verified: 120 requests from one source now consume 9% of the budget instead
of all of it, and other visitors are unaffected. Sources are recorded as a
per-day salted hash, never as an address, so the control doesn't quietly
reintroduce the IP logging the analytics design deliberately avoids.

> **Lesson:** shared resources need per-user shares, or protecting a resource
> becomes a way to deny it. Ask of every new control: *what happens if one
> person consumes all of it?*

### 6. An error handler that crashed

**Severity: medium.** A function called `notify_error(...)` without importing
it. The result was a `NameError` raised *inside* the error path — so a handled,
recoverable failure turned into a generic 500, the helpful message never
reached anyone, and the alert that line existed to send was never sent.

It went unnoticed because error-handling code is the least-exercised code in any
application: the bug is invisible until the failure it handles actually occurs.

**Fixed by:** the missing import, plus a linter in CI (`ruff`, rules F821/F401/
F811) that gates every push. It found no other instances.

> **Lesson:** your error paths are code too, and they're the code you never run.
> A linter reads them anyway. This is the cheapest CI you will ever add.

### 7. Unbounded inputs and unbounded storage

**Severity: medium.** Two variants of the same oversight:

- Free-text fields sent to a *per-token billed* model had no length limit, so
  one request could carry arbitrary text into a paid API call.
- The analytics endpoint is unauthenticated by design (the browser posts to it)
  and had no retention policy, making it the one thing an anonymous caller could
  grow without limit. A full disk takes down the entire application, not just
  analytics.

**Fixed by:** length caps on user-supplied text, and both a retention window and
a hard row ceiling on the analytics table.

> **Lesson:** for every input ask "what if this is huge?" and for every table
> "what if this never stops growing?" Unauthenticated writes need a ceiling,
> not just a rate limit.

### 8. Two smaller ones

- **Unrate-limited upstream routes.** Two endpoints didn't call the AI, so they
  looked cheap — but each still consumed quota from a third-party data provider
  with a hard ceiling. Exhausting it would have taken down every other feature.
  *Lesson: "expensive" isn't only about your own bill.*
- **A missing AI disclosure.** A feature branded as a "coach" that types back is
  precisely where a person might assume they're talking to a human. A vendor
  credit in the page footer is not a disclosure. There's now a clear notice
  above the chat, which is also what applicable regulation requires.

---

## What the current design does

- **Secrets** live in AWS SSM Parameter Store as encrypted values, pulled onto
  the host at deploy time into a `600`-mode file. None are in the repository or
  its history — verified by scanning every commit, not just the current tree.
- **Deploys** authenticate with short-lived OIDC credentials. No long-lived
  cloud keys exist in CI.
- **The origin is not directly reachable.** Only the CDN's published ranges may
  reach it, and it additionally requires a shared secret header that the CDN
  attaches, so it can't be reached through someone else's CDN distribution
  either. No SSH port is open; shell access is via the cloud provider's session
  manager.
- **Admin endpoints fail closed** — they return 403 when the token is unset, and
  compare tokens in constant time.
- **Analytics are first-party and anonymous.** No cookies, no third-party
  trackers, no IP addresses in the database, and no player names in events. See
  [ANALYTICS.md](./ANALYTICS.md).

---

## Honest limitations

- Analytics identifiers are browser-generated, so "visitors" counts **browser
  sessions, not people** — private windows and cleared storage inflate it. The
  numbers are directional only.
- Spend tracking is *estimated* from token counts. It's a circuit breaker, not
  an accounting system; the provider's own billing console is authoritative.
- There is no user authentication anywhere. This is a deliberate trade for a
  no-login, no-PII product, and it's why per-source controls are keyed on
  network address rather than an account.

## How these were found

A mix of reading the code, probing the running system, and adversarial review —
proposing a finding, then trying hard to *disprove* it before accepting it. That
last step mattered: across the reviews, roughly two-thirds of candidate findings
were discarded as inapplicable or overstated. Chasing every plausible-sounding
issue would have buried the handful that were real.

The two most valuable findings — #3 and #6 — came from **testing the failure
paths**, not the happy path.
