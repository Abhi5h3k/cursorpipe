# SDK Limitations

cursorpipe v2 is built on the official `cursor-sdk`. The SDK does not expose
all OpenAI API features. The table below documents the gaps.

**Unsupported parameters are accepted in the request body and silently ignored**
so existing clients never receive unexpected 422 errors.

---

## OpenAI parameters not supported

| Parameter | SDK support | Notes |
|---|---|---|
| `temperature` | None | Accepted but ignored. The SDK does not expose sampling temperature. |
| `top_p` | None | Accepted but ignored. |
| `stop` sequences | None | Accepted but ignored. |
| `n` > 1 (multiple completions) | None | Only one completion per request. Would require N parallel agents. |
| `usage.prompt_tokens` | None | SDK returns no token counts. `usage` fields are always 0. |
| `function_calling` / `tools` | None | The SDK handles tools internally. You cannot define custom tools. |
| `logprobs` | None | Not applicable to Cursor models. |
| `presence_penalty` / `frequency_penalty` | None | Accepted but ignored. |
| `logit_bias` | None | Accepted but ignored. |
| `seed` | None | Accepted but ignored. |
| `response_format` | None | Accepted but ignored. JSON mode is not guaranteed. |

---

## Endpoints not supported

| Endpoint | Notes |
|---|---|
| `POST /v1/embeddings` | The Cursor SDK has no embedding API. |
| `POST /v1/images/generations` | Not available. |
| `POST /v1/audio/transcriptions` | Not available. |
| `POST /v1/fine-tuning/jobs` | Not applicable. |

---

## Other known differences

| Feature | v2 behaviour |
|---|---|
| Token counts | Always `0`. The SDK does not return prompt or completion token counts. |
| `finish_reason` | Always `"stop"`. The SDK does not distinguish length cutoffs from normal completion. |
| `model` in response | The SDK resolves the model; if it returns a model ID, it is reflected in the response. Otherwise the requested model ID is echoed. |
| Concurrent requests | Each stateless request creates a temporary SDK agent. Stateful sessions share one agent per session. There is no global concurrency limit in cursorpipe — the SDK and Cursor API impose their own limits. |
| Rate limiting | When the Cursor API rate-limits a request, the server returns `429` with a standard OpenAI error body. The `Retry-After` header is not forwarded (SDK does not expose it). |

---

## Workarounds

**Token counts needed?** Estimate using tiktoken client-side:

```python
import tiktoken

enc = tiktoken.encoding_for_model("gpt-4")
n_tokens = len(enc.encode(prompt))
```

**Structured JSON output?** Append an explicit instruction to your prompt:

```
"Respond with valid JSON only. No other text."
```

**Multiple completions (`n > 1`)?** Send N parallel requests:

```python
import asyncio, httpx

async def complete(client, prompt):
    resp = await client.post("/v1/chat/completions", json={"model": "composer-2.5", "messages": [{"role":"user","content":prompt}]})
    return resp.json()["choices"][0]["message"]["content"]

async def n_completions(prompt, n=3):
    async with httpx.AsyncClient(base_url="http://localhost:8080") as c:
        return await asyncio.gather(*[complete(c, prompt) for _ in range(n)])
```
