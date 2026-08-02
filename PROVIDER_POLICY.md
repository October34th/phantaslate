# Provider Policy

How Phantaslate decides which translation models it offers, and which ones it
lets you bring yourself.

*Status: decided. This document exists so the question doesn't get
re-litigated mid-implementation.*

---

## The decision

**Two tiers, two different rules.**

| | Shared free tier | Bring-your-own-key |
|---|---|---|
| Who pays | Phantaslate | You |
| Whose promise | Phantaslate's | Yours with your provider |
| Who chooses | Phantaslate curates | You choose, including closed models |
| Where text goes | Your browser → Phantaslate relay → provider | Your browser → provider |
| Phantaslate in the path | Yes (stateless) | **No** |

The curation applies **only** to the tier Phantaslate pays for and makes
promises about. BYOK is the user's key, the user's provider, the user's data
relationship — Phantaslate isn't in the request path at all under the
direct-from-browser design, so there is nothing for it to promise or withhold.

---

## Why closed models are allowed under BYOK

**Open weights aren't doing privacy work in the current architecture.** When
the relay calls `api.deepseek.com`, it is not running open weights — it is
calling a proprietary hosted service with its own retention policy, exactly
like OpenAI's. The published weights change nothing about what happens to text
sent to that company's API. Phantaslate's privacy claim rests on the relay
being stateless and on honest disclosure, not on any model's license.

**Under BYOK the direction reverses.** A user pointing their own key at OpenAI
has *one less party* in the path than a user on the shared DeepSeek relay.
Refusing that on open-source grounds would mean blocking the more private
configuration on principle.

**Autonomy is the point.** A privacy tool that dictates which vendor you may
use is being paternalistic in the name of user control.

## Why the shared tier stays curated anyway

- **Cost.** Every provider on the shared tier is a recurring bill against a
  product with no revenue.
- **Availability.** Some providers are unreachable in regions Phantaslate
  cares about; the default must work for the people it's aimed at.
- **Forward compatibility.** Open weights become a *real* privacy feature —
  not a symbolic one — when the desktop apps ship local models. Preferring
  open-weights providers now builds toward something concrete later.

Note that "open source" is generous for most of this category. DeepSeek, Qwen,
and Llama are open-**weights**: training data isn't published, and Llama's
license carries use restrictions that fail the OSI definition. This is a
preference, not a purity test, and the docs should say so.

---

## Implementation

### 1. One provider registry, one source of truth

Every provider-specific fact lives in a single structure shared by the relay
and the extension, so displayed copy cannot drift from actual behaviour:

```js
{
  id: "deepseek",
  name: "DeepSeek",
  models: ["deepseek-v4-flash"],
  tier: "shared",              // "shared" | "byok" | "both"
  weights: "open",             // "open" | "closed"
  jurisdiction: "China",
  endpoint: "https://api.deepseek.com",
  privacyUrl: "https://...",
  apiStyle: "openai-compatible"
}
```

Adding a provider means adding a row, not editing five files.

### 2. One adapter covers nearly everything

DeepSeek, Qwen (Model Studio's compatible mode), Mistral, and OpenAI all
expose an OpenAI-compatible `/chat/completions` endpoint. The provider adapter
is therefore mostly base URL + auth header + model name, not four separate
integrations.

This is worth stating plainly: **supporting ChatGPT under BYOK is not extra
work.** It's the same code path already carrying DeepSeek. The question was
never technical.

### 3. Disclosure at the point of choice

The mitigation for the one genuine risk — someone uses Phantaslate → OpenAI,
OpenAI has an incident, "Phantaslate" appears in the story — is disclosure when
the user picks, not buried in a policy page.

When a provider is selected, show a short card:

> **OpenAI** · Closed weights · United States
> Your text is sent directly from your browser to OpenAI using your key.
> It does not pass through Phantaslate's servers.
> OpenAI's handling of it is governed by their policy → [link]

Three rules for this copy:

- **Never summarise a third party's retention policy in our own words.** It
  changes without notice and we'd be liable for the paraphrase. Name the
  company, name the jurisdiction, link their policy.
- **Always state what Phantaslate does**, since that's the part we control and
  can stand behind.
- **Don't editorialise about the provider.** "Closed weights" is a fact.
  "Less private" is a claim we can't support.

### 4. The permission constraint (Phase 3)

Direct-from-browser BYOK needs `host_permissions` for each provider's domain.
Two options, and they should be chosen deliberately:

- **Curated BYOK list** — static `host_permissions` for known providers. Clean,
  predictable install warnings. Users can't use a provider we haven't listed.
- **Arbitrary endpoint field** — requires `optional_host_permissions` with a
  broad pattern, granted per-domain at runtime by the user. Maximum autonomy,
  and arguably *more* privacy-respecting since each grant is explicit — but
  the install-time permission story gets harder to explain.

Recommendation: **ship the curated list first**, add the custom-endpoint field
once the settings UI rework (Phase 4) can present the permission grant clearly.
Since direct-from-browser means no request ever originates from our server, the
usual SSRF concern with user-supplied endpoints doesn't apply here — this is a
UX and permissions question, not a security one.

---

## Claim hygiene

The current copy needs one distinction held consistently:

| Say | Don't say |
|---|---|
| "Open-source translation tool" | "Open-source models" |
| "Phantaslate is open source" (AGPL — true) | implying the models are OSI open source |
| "Stateless — your text isn't logged or retained *by us*" | "your text is never stored anywhere" |

The last row matters most. The stateless promise is about Phantaslate's own
handling. It was never a claim about the provider on the other end, and
PRIVACY.md already gets this right for DeepSeek — the same framing extends to
every provider added.

---

## Sequencing

**Phase 2 (now)** — Registry + adapter. Shared tier only, curated. Build the
disclosure card now even though every current provider is open-weights; it's
much easier than retrofitting it when the first closed provider lands.

**Phase 3 (BYOK)** — Curated BYOK list, including closed providers. This is
where the policy above actually takes effect.

**Phase 4** — Custom endpoint field, if the settings rework can present the
permission grant clearly.

**Phase 5** — Privacy policy revised: the data story now branches by user
choice, and needs to say so.

---

## Open question this doesn't answer

Whether provider selection is **purely a user choice**, or whether the relay may
also route on its own for cost reasons. The business plan describes regional
cost routing; the roadmap describes a user-facing picker. They're compatible,
but they're different code, and building one while assuming the other is how
this gets tangled.

If backend routing stays in scope, the disclosure card has a problem: a user who
picked "DeepSeek" and silently got routed elsewhere was shown the wrong card.
Either routing is confined to endpoints of the same named provider, or the
picker has to reflect what actually happens.
