# Phantaslate Relay

The relay is the server-side component of Phantaslate. It sits between the browser extension and the LLM translation APIs.

**Key properties:**
- Stateless — no database, no logs, no user data stored
- Open source — this entire folder is the relay; what you read is what runs
- Self-hostable — Docker instructions coming soon

## Architecture

```
Extension → Relay → LLM API (Qwen / Mistral / Llama)
                ↓
         Translation result
                ↓
         Extension renders
         (Relay stores nothing)
```

## Coming Soon

Relay code, Docker setup, and self-hosting documentation will be added here during V1 development.
