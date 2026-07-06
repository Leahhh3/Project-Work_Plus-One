# Plus One AI Evaluation Plan

The MVP uses two AI strategies:

| Strategy | Purpose | Dependency | Logged in app |
|---|---|---|---|
| DeepSeek / OpenAI LLM | Natural language post parsing, icebreakers, moderation | `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` | `LLMLog` |
| Rule-based fallback | Deterministic demo-safe baseline | none | `LLMLog` |

Run the local baseline evaluation after seeding data:

```bash
.venv/bin/python manage.py seed_demo
.venv/bin/python manage.py evaluate_ai
```

Report metrics:

- Activity type accuracy over 15 manually written campus requests.
- Location accuracy over the same 15 requests.
- Safety flag accuracy over 5 moderation examples.
- Runtime behavior: DeepSeek or OpenAI calls are logged when a key is available; fallback is used when no key is set or an API call fails.

Recommended report comparison:

| Dimension | LLM | Rule baseline |
|---|---|---|
| Flexible language | Higher | Lower |
| Deterministic demo | Depends on API | Strong |
| Latency | Network-dependent | Near-instant |
| Cost | API cost | Free |
| Failure mode | API/key/network errors | Misses unusual phrasing |

For the classroom demo, the fallback strategy guarantees the MVP works without an external service. For the report, use `LLMLog` rows and `evaluate_ai` output to compare the strategies.
