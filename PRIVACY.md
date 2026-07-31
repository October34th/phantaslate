# Phantaslate Privacy Policy

**Effective date:** 31 July 2026
**Applies to:** Phantaslate browser extension for Chrome (and Chromium-based browsers)

---

## Summary

Phantaslate is a translation tool built on a stateless relay. Text you submit is
passed through for translation and is not stored, logged, or associated with you.

- No account is required, and none exists.
- No translation history is kept — not on your device, not on our server.
- No advertising, no analytics, no tracking, no profiling.
- The text you submit is sent to a machine-translation provider in order to
  translate it. This is disclosed in full below.
- The extension is free and open source. The claims on this page can be verified
  by reading the code.

This document describes exactly what happens to your data. If anything here is
unclear or appears to contradict the source code, please open an issue on GitHub.

---

## 1. What Phantaslate does not collect

Phantaslate does not collect, request, or store:

- Names, email addresses, or any account identifiers
- Passwords or authentication credentials
- Payment or financial information
- Browsing history or the list of pages you visit
- Clicks, scrolling, keystrokes, mouse position, or other behavioural telemetry
- Device fingerprints
- Health, biometric, or demographic information

There is no analytics SDK, no advertising SDK, and no third-party tracking script
in the extension.

---

## 2. What is transmitted, and to whom

Phantaslate only transmits text that **you** explicitly submit for translation —
by typing or pasting it into the panel and pressing Translate. Text on a page you
are merely viewing is never read or transmitted.

When you press Translate, the following happens:

1. Your submitted text, along with your chosen source and target languages, is
   sent over HTTPS to the Phantaslate relay at `api.phantaslate.com`.
2. The relay forwards that text to **DeepSeek**, a third-party machine-translation
   provider, in order to produce the translation.
3. The translation is returned through the relay to your browser and displayed in
   the panel.
4. The relay holds the text only in memory for the duration of the request. Once
   the response is returned, it is gone. Nothing is written to disk, to a
   database, or to a log.

### The DeepSeek disclosure

The relay is stateless, but it is not a translation engine on its own. Producing a
translation requires sending your text to DeepSeek's API. **Once your text reaches
DeepSeek, it is subject to DeepSeek's own data handling practices, which
Phantaslate does not control and cannot make guarantees about.**

We state this plainly because a privacy promise that quietly omits it would not be
worth much. What Phantaslate controls is everything on its own side of that
boundary: no retention, no logging, no linkage between your text and any
identifier.

Please review DeepSeek's own privacy documentation if this matters to your use
case. If you handle text that must never reach a third-party API, Phantaslate —
like every hosted translation service — is not the right tool for it.

### Other infrastructure providers

- **Render** hosts the relay. As with any hosting provider, Render may generate
  transient operational and network-level logs as part of running the service.
  Phantaslate does not create, request, or retain application logs of translation
  content.
- **Cloudflare** provides DNS resolution for the `phantaslate.com` domain. The
  `api` subdomain is configured as DNS-only, meaning Cloudflare resolves the
  address but does not proxy or inspect the traffic itself.

---

## 3. Abuse prevention

To keep a free, account-free service usable, Phantaslate applies a daily usage cap
(a baseline of 20,000 characters per day, which may be reduced during periods of
high demand or cost pressure).

Enforcing a limit without accounts requires some way to distinguish one user from
another. Phantaslate does this in the least identifying way we could design:

- Your IP address is combined with a rotating salt and hashed. The resulting hash
  is used as a short-lived counter key. **The raw IP address is not stored**, and
  because the salt rotates, hashes cannot be correlated across time periods.
- A short-lived, randomly generated install token accompanies requests from your
  browser. It is not tied to your identity and carries no personal information.

These values exist solely to count usage against a cap. They are not used to build
a profile, are not linked to translation content, and are not shared.

Because an IP address is processed — even momentarily, and even in hashed form —
we disclose "Location" in the Chrome Web Store data usage form. We would rather
over-disclose than have a technically true claim mislead you.

---

## 4. Data stored on your device

Phantaslate stores a small number of preferences locally using
`chrome.storage.local`. These never leave your browser and are never sent to the
relay:

| Stored value | Purpose |
| --- | --- |
| Panel position and size | Keeps the panel where you left it |
| Relay URL | Allows you to point the extension at a different relay |
| "Remember last used languages" preference | Opt-in only; off by default |
| Last used language pair | Stored **only** if you enable the option above |

Translation text and results are never written to storage. Closing the panel
clears its contents.

You can remove all locally stored data at any time by uninstalling the extension,
or by clearing the extension's storage from your browser's settings.

---

## 5. Permissions and why they are needed

| Permission | Why it is required |
| --- | --- |
| `activeTab` | Opens and focuses the panel on the page you are currently viewing when you click the extension icon |
| `scripting` | Injects the translation panel into the page so you can translate without leaving it |
| `storage` | Saves the local preferences listed in section 4 |
| `clipboardWrite` | Powers the panel's Copy button, on click only |
| Host permission — page access | Required to display the panel on the pages you visit |
| Host permission — `api.phantaslate.com` | Required to send submitted text to the relay and receive the translation |

No permission is used for any purpose beyond the one stated above.

---

## 6. Data retention

| Data | Retention |
| --- | --- |
| Submitted text | Held in memory for the duration of the request only |
| Translation results | Not retained by the relay |
| Usage counters (salted hashes) | Short-lived; expire with the rate-limit window and salt rotation |
| Local preferences | Kept on your device until you clear or uninstall |

Phantaslate has no database of user content. There is no archive to search, no
history to export, and nothing to hand over in response to a request — because
nothing is kept.

---

## 7. Your rights

Because Phantaslate does not hold personal data associated with you, there is
nothing to access, correct, export, or delete on our side. There is no account to
close.

If you are in a jurisdiction with data protection rights such as the GDPR or CCPA
and believe personal data of yours has nonetheless been processed, you are welcome
to contact us using the details in section 10.

Phantaslate does not sell personal information, and does not share it for
cross-context behavioural advertising.

---

## 8. Children

Phantaslate is not directed at children and does not knowingly collect information
from them. Since no personal information is collected from anyone, this holds
generally.

---

## 9. Verification and changes

Phantaslate is open source. Every claim in this document can be checked against
the source code, including the relay:

**https://github.com/October34th/phantaslate**

If this policy changes, the revised version will be published at the same URL with
an updated effective date, and material changes will be noted in the repository's
release notes. Continued use of the extension after a change indicates acceptance
of the revised policy.

---

## 10. Contact

Questions, corrections, or concerns about this policy:

- GitHub issues: https://github.com/October34th/phantaslate/issues
- Email: cdxyu@tuta.com

---

*Phantaslate — Translate Without a Trail.*
