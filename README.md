# Phantaslate

**Translate Without a Trail.**

> Translation should serve you, not study you.

Phantaslate is an open-source, privacy-first translation tool. Your words are yours — we keep no logs, we publish everything we do, and we let you verify it.

---

## Why Phantaslate?

| Problem | Phantaslate's Answer |
|---|---|
| Google Translate feels like surveillance | Stateless relay — nothing is stored |
| DeepL is unstable or blocked in many regions | Region-aware model routing |
| ImmersiveTranslate had a data breach | Open-source relay, auditable by anyone |
| CJKV translations route awkwardly through English | Native CJKV model support — no English pivot |

---

## Features

- 🔒 **Privacy by design** — stateless relay, zero translation logs
- 🌏 **CJKV-native** — Chinese, Japanese, Korean, Vietnamese translated without routing through English
- 🌍 **9 languages** — focused and done well, not 100 languages done poorly
- 🔍 **Fully auditable** — every line of code is open, from extension to relay
- ⚖️ **Region-aware backends** — Qwen/DeepSeek for Asia · Mistral for Europe · Llama for the US
- 🧩 **Browser extension first** — Chrome, Chromium, and Firefox
- 🖥️ **Desktop & mobile apps coming in V2**

---

## Supported Languages (V1)

| Code | Language |
|---|---|
| `en` | 🇺🇸 English (American) |
| `zh-Hans` | 🇨🇳 Chinese (Simplified) |
| `zh-Hant` | 🇹🇼 Chinese (Traditional) |
| `ja` | 🇯🇵 Japanese |
| `ko` | 🇰🇷 Korean |
| `vi` | 🇻🇳 Vietnamese |
| `fr` | 🇫🇷 French |
| `de` | 🇩🇪 German |
| `ru` | 🇷🇺 Russian |
| `es` | 🇪🇸 Spanish |

Arabic (`ar`) is planned for V1.1.

---

## Architecture

```
User text
    │
    ▼
Browser Extension  (lightweight UI shell, ~500KB)
    │
    ▼
Phantaslate Relay  (open source, stateless, self-hostable)
    │
    ├── Qwen / DeepSeek  ← default · Asia-Pacific users
    ├── Mistral          ← EU users · GDPR-native
    └── Meta Llama       ← US users · open weights
    │
    ▼
Translation returned → Extension renders → Nothing stored
```

**The relay is stateless by design.** It receives text, calls the model API, returns the result, and writes nothing to disk. Even if the server were compromised, there is nothing to leak.

---

## Roadmap

| Version | Scope | Status |
|---|---|---|
| **V1** | Browser Extension (Chrome, Chromium, Firefox) | 🚧 In development |
| **V2** | Desktop app (Windows, macOS) + Mobile (iOS, Android) | 📋 Planned |
| **V1.1** | Arabic language support + RTL rendering | 📋 Planned |

---

## Self-Hosting the Relay

Power users and privacy maximalists can run their own relay. This means your translation text never touches our servers at all.

```bash
# Coming soon — Docker instructions will be added here
```

---

## Contributing

We welcome contributions of all kinds. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

Areas where help is especially welcome:
- Firefox extension compatibility
- RTL rendering (for future Arabic support)
- Language quality testing (native speakers)
- Documentation and translations of the docs themselves

---

## License

Phantaslate is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

This means:
- ✅ You can use, study, and modify the code freely
- ✅ You can self-host your own relay
- ✅ You can fork and build on this project
- ❌ You cannot take this code, modify it, and run it as a closed proprietary service without releasing your changes

See [LICENSE](LICENSE) for the full text.

---

## Mission

> *Phantaslate exists because translation should never come at the cost of trust.*
>
> *We build an open, auditable, lightweight tool focused on the languages people actually use — including the CJKV pairs that big platforms route awkwardly through English.*
>
> *We keep no logs. We publish what we do. We let you verify it.*
>
> *Translation should serve you, not study you.*

---

<p align="center">
  <a href="https://phantaslate.com">phantaslate.com</a>
</p>
