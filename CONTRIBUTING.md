# Contributing to Phantaslate

Thank you for your interest in contributing. Phantaslate is built on the belief that translation should serve users, not study them — and that starts with a community that builds in the open.

---

## Ways to Contribute

You don't have to write code to contribute meaningfully.

- **Report bugs** — open an Issue describing what happened, what you expected, and your browser/OS
- **Suggest features** — open an Issue with the `enhancement` label
- **Improve documentation** — typos, unclear instructions, missing steps
- **Test language quality** — native speakers are especially valuable for catching translation errors
- **Write code** — see the development guide below

---

## Before You Start

- Check existing Issues and Pull Requests to avoid duplicate work
- For significant changes, open an Issue first to discuss the approach
- Keep pull requests focused — one change per PR

---

## Development Setup

```bash
# 1. Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/phantaslate.git
cd phantaslate

# 2. Install dependencies (once package.json is ready)
npm install

# 3. Build the extension
npm run build

# 4. Load in Chrome/Chromium:
#    → chrome://extensions → Enable Developer Mode → Load unpacked → select /dist folder

# 5. Load in Firefox:
#    → about:debugging → This Firefox → Load Temporary Add-on → select /dist/manifest.json
```

---

## Code Style

- Clear, readable code over clever code
- Comments explaining *why*, not just *what*
- No tracking, analytics, or logging of user text — ever
- If you're unsure whether a change could affect user privacy, ask in the Issue before coding

---

## Commit Messages

Use plain, descriptive commit messages:

```
Add Japanese language selector to popup
Fix relay timeout on slow connections
Update README installation steps
```

---

## Pull Request Process

1. Fork → Branch → Commit → Push → Open PR
2. Describe what your PR does and why
3. Reference any related Issue numbers
4. A maintainer will review within a few days

---

## Code of Conduct

Be respectful. We welcome contributors regardless of background, experience level, or native language. Criticism should be directed at code, not people.

---

## License

By contributing, you agree that your contributions will be licensed under the same [AGPL-3.0 license](LICENSE) that covers the project.
