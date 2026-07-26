# Phantaslate Relay

The server-side component of Phantaslate. It sits between the browser extension
and the LLM translation API.

**Key properties**
- **Stateless** — no database, no logging of request content.
- **Open source** — this folder is the relay; what you read is what runs.
- **Self-hostable** — run your own instance so your text never touches a shared server.

## Architecture

```
Extension  ->  Relay  ->  LLM API  ->  translation  ->  Extension renders
                 |
                 +-- stores nothing
```

## API

### `POST /translate`

Request:
```json
{ "text": "Bonjour le monde", "source_lang": "auto", "target_lang": "en" }
```

Response:
```json
{ "translation": "Hello world", "detected_lang": "French" }
```

`detected_lang` is returned only when `source_lang` is `auto`, and is always the
language name in English (e.g. `Japanese`, not `日本語`). It is `null` when the
source language was specified explicitly, or if the model's reply could not be
parsed — the translation itself is still returned in that case.

`source_lang` accepts `auto` or any supported code. `target_lang` must be a
specific language (not `auto`). Supported codes: `en`, `zh-Hans`, `zh-Hant`,
`ja`, `ko`, `vi`, `es`, `fr`, `de`. Text is limited to 5000 characters.

### `GET /health`

Returns `{ "status": "ok", "model": "...", "stateless": true }`. Reveals no
request content.

## Run locally

```bash
cd relay
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

# Set your key (get one at https://platform.deepseek.com):
# Windows (PowerShell):  $env:DEEPSEEK_API_KEY="sk-..."
# macOS/Linux:           export DEEPSEEK_API_KEY="sk-..."

uvicorn main:app --reload --port 8000
```

Test it:
```bash
curl -X POST http://localhost:8000/translate \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"Bonjour\",\"source_lang\":\"auto\",\"target_lang\":\"en\"}"
```

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `DEEPSEEK_API_KEY` | yes | — | API key (never commit it) |
| `PHANTASLATE_MODEL` | no | `deepseek-v4-flash` | Model name |
| `DEEPSEEK_BASE_URL` | no | `https://api.deepseek.com` | API base URL |
| `PHANTASLATE_ORIGINS` | no | `*` | Comma-separated allowed CORS origins |

> Note: the legacy `deepseek-chat` model name is deprecated and retires
> 2026-07-24. This relay defaults to `deepseek-v4-flash`.

## Tests

```bash
pip install pytest
pytest -q
```

These run offline — no API key or network needed.

## Docker

```bash
cd relay
docker build -t phantaslate-relay .
docker run -p 8000:8000 -e DEEPSEEK_API_KEY="sk-..." phantaslate-relay
```

The image runs with `--no-access-log`, so request paths are kept out of logs too.
