# Phantaslate — Roadmap

This document plans the path from "works on one machine" to a product other
people can actually install and use — covering three requirements:

1. All users should be able to use the extension on their own computers.
2. All users should be able to freely switch between the AI models we provide.
3. All users should be able to use their own API keys for those models.

Requirement 1 is now met. Requirements 2 and 3 are the active work.

---

## The core architectural decision

Getting from "works on my computer" to "works on everyone's computer" required
a default relay that **we deploy and pay for**, because most users will not run
a Python server just to translate text.

That decision is now made and executed. It also means the relay is a real cost
center rather than a dev tool — rate limiting and abuse protection are no
longer optional.

---

## Phase 1 — Deploy the relay ✅ Complete

Goal: move off `localhost` so the extension works for anyone, out of the box.

- ✅ **Hosted on Render**, containerised from the existing Dockerfile. Running
  on the Starter instance rather than the free tier — the free tier's cold
  starts (50s+) made the panel report "Offline" on a perfectly healthy relay,
  which would have been a poor first impression and a review risk.
- ✅ **Live at `api.phantaslate.com`** over HTTPS. DNS via Cloudflare, set to
  DNS-only (grey cloud) rather than proxied, so translation request bodies
  don't pass through an additional party. This trades away free edge rate
  limiting — see the open item below.
- ✅ **CORS locked down.** `PHANTASLATE_ORIGINS` moved off its `*` default to
  the specific extension origins.
- ✅ **Free tier decided:** a dynamic daily character cap, baseline 20,000
  chars/day, flexing down under pricing or budget pressure. See the extension
  business plan for the full design.

### Still outstanding from this phase

- **Rate limiting is designed but not yet enforced.** The cap design exists on
  paper; the relay does not yet count usage against it. Until that ships,
  nothing prevents a single caller from consuming the shared budget. This is
  the highest-priority remaining item on the relay side.
- **Operational logging** (request counts, error rates, stopping short of
  content) has not been added. Worth doing deliberately and reviewing against
  the brand doc before it ships, rather than reaching for a default logging
  setup under pressure.
- **Edge protection.** With Cloudflare in DNS-only mode there is no upstream
  rate limiting or DDoS filtering. Either accept that and handle it in the
  relay, or revisit the proxy decision — but decide it rather than inherit it.

---

## Phase 2 — Support multiple AI models 🚧 In progress

Goal: satisfy requirement 2. The relay currently hardcodes DeepSeek; this
phase makes the model a parameter instead of an assumption.

- Refactor the relay around a **provider adapter** pattern: each provider
  implements the same interface — take text and languages in, return a
  translation — behind one shared request/response shape. Providers differ in
  base URL, auth header format, and sometimes response structure, so this is a
  real abstraction, not just a model-name swap.
- **Add Qwen as the second provider**, offered alongside DeepSeek as a
  user-selectable choice rather than a silent backend swap.
- Extension side: the settings panel gets a **provider + model picker**
  instead of just a relay URL field.
- Cost implication: the relay needs its own key for every model it offers on
  the shared free tier. That's a real added cost per provider, and it feeds
  directly into the cap design — worth confirming which models are offered by
  default versus reserved for BYOK.

**Open question worth settling before the adapter is finalised:** whether
provider selection is purely a user choice, or whether the relay may also route
on its own for cost reasons. Those are different designs — a user-facing picker
and a backend routing policy — and building one while assuming the other is how
this gets messy.

---

## Phase 3 — Bring-your-own-key

Goal: satisfy requirement 3.

**Decision made: Option A — direct from browser.**

When a user supplies their own key, the extension calls the provider's API
directly, never touching the relay at all. Chrome extensions with
`host_permissions` for a domain are exempt from normal CORS restrictions, so
this is workable from the panel.

Why this over proxying keys through the relay:

- Stronger privacy story: "bring your own key and your text never touches our
  server, full stop."
- Fits the brand more directly.
- More defensible if the privacy claim is ever audited.
- Proxying would require airtight "received, used once, never logged, never
  stored" guarantees for other people's API keys — a much harder claim to make
  credible.

The tradeoff accepted: two networking code paths instead of one, since BYOK
and shared-relay translation no longer share a route.

### This phase also needs

- A per-provider key input in settings (masked field, stored only in
  `chrome.storage.local`, never synced to Google's cloud storage, never
  transmitted anywhere but the provider itself).
- A "Test key" button, following the same pattern as the existing relay health
  check.
- Clear fallback logic: if a BYOK key is present for the selected model, use
  it; otherwise fall back to the shared relay.
- **New host permissions per provider**, which will change the extension's
  install warnings. Worth planning the permission story before adding them
  rather than accumulating domains one at a time.

---

## Phase 4 — Settings UI rework

The current gear panel was designed around a single relay URL field. Once
Phases 2 and 3 land, settings need to hold: provider, model, an API key per
provider, the self-host relay URL (keep this — it remains valuable for anyone
running their own full stack), and the existing clear/remember toggles. That's
more than the current popover holds well; it likely needs to become a proper
settings view rather than a small dropdown panel.

---

## Phase 5 — Docs and privacy policy

Once BYOK and multiple providers exist, "what happens to my data" no longer has
one answer — it depends on the choices a given user has made. This needs to be
written down clearly in two places:

- In-app copy, so users understand what they're choosing between when they pick
  a provider or enter a key.
- An actual privacy policy document.

**Partially pulled forward:** the Chrome Web Store requires a privacy policy at
submission regardless of BYOK, so the policy itself is being written ahead of
the rest of this phase, and will need revising once BYOK ships and the data
story branches.

---

## Suggested order

**2 → 3 → 4**, with Phase 5 written alongside Phase 3, since that's where the
privacy story genuinely gets more complex and needs capturing while the design
decisions are fresh.

Running in parallel, outside the phase sequence:

- **Chrome Web Store submission** — listing drafted, store assets prepared
- **phantaslate.com homepage** — domain registered, site not yet built
- **Relay rate limiting** — carried over from Phase 1, and the item most worth
  not deferring, since it protects the shared budget the free tier depends on

---

## Open decisions

- **Provider selection semantics** (Phase 2): user-facing picker only, or
  user picker plus backend cost routing?
- **Cloudflare proxy** (Phase 1 carry-over): stay DNS-only and build abuse
  protection into the relay, or enable the proxy and accept an additional party
  in the request path?
- **Which models are free-tier vs BYOK-only** (Phases 2–3): every added
  provider on the shared tier is a recurring cost against a product with no
  revenue.
