# Rosetta MCP Gateway

Rosetta is a runtime, schema-aware multilingual translation gateway for the [Model Context Protocol (MCP)](https://modelcontextprotocol.io). It sits on the wire between a multilingual MCP client and one or more English-only MCP servers, and it rewrites only the fields that are safe to translate.

It is a **selective semantic normalization proxy**. Tool names, JSON keys, enums, identifiers, and code stay locked. Natural-language arguments are normalized into canonical English on the way in. Prose in tool results is translated back into the user’s language on the way out. Security checks run on that canonical English form, so English-tuned injection and DLP rules see the same text the backend API will execute.

All four phases are built in **[vaquarkhan/rosetta-mcp](https://github.com/vaquarkhan/rosetta-mcp)**, in **Python**. Proxy, classifier, translation, governance, cache, and the benchmark harness stay in this one tree. Phase 1 has not started.

| | |
| --- | --- |
| Product | Rosetta MCP Gateway |
| Repository | https://github.com/vaquarkhan/rosetta-mcp |
| Language | Python 3.11+ (locked for v1) |
| License target | Apache-2.0 |
| v1 stack | FastAPI / MCP Python SDK, Redis, CTranslate2 |
| v1 base | Extend the IBM ContextForge plugin spine and Redis cache. Run CTranslate2 in-process. |
| v1 default mode | Pivot Mode: English schemas, translated arguments, localized prose results |
| Planning horizon | 16 weeks, four phases |

The three figures below are the original figures from *Multilingual MCP Gateway Architecture*.

---

## What we build

Rosetta fills a gap that no current MCP gateway covers: **human-language translation of live MCP JSON-RPC traffic**, with schema structure preserved.

About 75–80% of the surrounding infrastructure already exists and will be reused: an MCP gateway spine, a structure-preserving field classifier, a local translation runtime, and governance interceptor patterns. The new work is the piece that connects them on the live wire.

### v1 delivers

- A stateless MCP reverse proxy (`stdio` and Streamable HTTP) in front of any upstream MCP server.
- A four-type AST field classifier, cached in Redis and keyed by the SHA-256 of the canonical English tool schema.
- Entity and placeholder locking so shared names, IDs, URLs, and `${VAR}` tokens survive translation.
- Pivot Mode on `tools/call`: free-text arguments become English; enums, keys, and code do not.
- Partial schema localization on `tools/list`: descriptions can be translated; names, keys, and enums stay English.
- Prose in `tools/call` and `resources/read` results translated back to the client locale.
- A pluggable translation router: local CTranslate2 (Opus-MT by default), commercial NMT APIs, and a small-model fallback.
- A fail-closed governance stage that inspects the raw payload and the normalized English payload.
- Localization of MCP 2026-07-28 multi-round-trip (`input_required`) prompts.

### v1 wire methods

| Method | Rosetta’s job |
| --- | --- |
| `tools/list`, `prompts/list`, `resources/list` | Classify, pin, and optionally localize descriptions. Serve from the locale cache with `ttlMs` and `cacheScope`. |
| `tools/call` | Lock structure, translate free text into English, govern, forward, localize prose in the result. |
| `resources/read`, `prompts/get` | Same field policy on textual content. |
| MRTR `resultType: "input_required"` | Translate the elicitation into the user language; normalize `inputResponses` back to English on retry. |
| `ping`, zero-argument tools, numeric-only tools | Header route at the edge and skip the translation pipeline. |

### Later than v1

These stay documented and are not part of the 16-week Python build:

- A Java fork of `vaquarkhan/aegis-mcp-gateway` with a CTranslate2 sidecar (Path B).
- Apache Knox perimeter hosting and the 28 Apache data-engine adapters.
- A glossary-authoring UI and automatic per-model policy selection.
- Domain-adaptive NMT training (Google Adaptive Translation, custom SYSTRAN domains).

### Language

**Python is the v1 language.** Java 17 would be the better fit for a Knox-fronted Apache gateway whose main job is the existing Aegis Flink, Spark, and Kafka adapters. Rosetta’s main job is schema-aware translation on the MCP wire, and that workload belongs in Python.

| Requirement | Where it lives | Why this decides the language |
| --- | --- | --- |
| Sub-120 ms local translation | CTranslate2 Python bindings, in-process | Opus-MT INT8 runs inside the gateway. A Java process would cross a socket to reach the same C++ library and spend the latency budget on the hop. |
| Language ID, tokenization, INT8 conversion | FastText, SentencePiece, `ct2-transformers-converter` | These are Python tools and sit next to the request path. |
| Gateway spine and ontology cache | IBM ContextForge (FastAPI, Redis, plugins) | The `list_tools()` → classify once → Redis pattern we reuse is already Python. |
| Field types and entity locking | BabelFlow (Python) | The reference classifier ports into the same process. |
| MCP 2026-07-28 | Tier-1 Python MCP SDK, OpenTelemetry included | Stdio and Streamable HTTP are supported without a second runtime. |
| Fail-closed governance | Ported in Phase 3 from the Aegis interceptor pattern | The sequence, the catalog pin, and the approval token are the part we need. The Java SPI adapters and Knox hosting stay out of this repo. |

---

## The four gaps that define the product

1. **Protocol translation exists. Human-language translation does not.** ContextForge, `mcp-proxy`, and `microsoft/mcp-gateway` bridge transports (stdio, Streamable HTTP, SSE, gRPC). BabelArena translates offline benchmarks. Nobody has attached structure-preserving translation to live `tools/list`, `tools/call`, `resources/read`, and MRTR traffic.
2. **English-only backend APIs.** A user can prompt Claude, GPT, or Qwen in Spanish, Arabic, Hindi, or Japanese, and the model can pick the right tool, while the downstream server (search, Jira, GitHub, Flink, Spark) still expects English query terms and English enum values. Rosetta normalizes natural-language arguments into canonical English and locks enums, keys, and IDs.
3. **The token tax and English drift.** Low-resource prompts cost 1.89×–2.51× the constant input tokens of English, and 91.2% of language-consistency failures are switches back into English after English tool output lands in context. Pivot Mode keeps schemas in compact English and translates tool prose back into the user’s language.
4. **The cross-lingual security loophole.** Aegis, ZHASK Aegis, and AegisGate run regex, DLP, and injection rules on raw parameters. Those rules are English-centric. Normalizing arguments into canonical English *before* the governance chain closes the bypass.

---

## Why a gateway, not “the model will translate”

Frontier models hold multilingual conversations. Structured tool calling still drops outside English.

MCP tool use asks the model to do five things at once: understand a localized utterance, map it onto an English JSON Schema, extract slots, put those values in the shape the API expects, and emit valid JSON-RPC. MASSIVE-Agents (EMNLP 2025; 52 languages, 47,020 samples, 21 models) separates **function selection accuracy** (right tool name) from **AST accuracy** (right name *and* correctly structured arguments).

- Nova Premier, the strongest model in that study, fell from **57.37% AST in English** to **34.05% averaged across 52 languages**, and to **6.81% in Amharic**. Smaller models scored 0.00% on the hardest languages.
- Llama 3.1 405B reached **81.07% function-selection accuracy** across 52 languages, and only **25.61% AST** (46.32% English, 31.75% German, 30.00% Spanish, 12.04% Amharic).
- Claude 3.5 v2 Sonnet fell from **53.68% AST in English** to 35.98% German, 28.95% Spanish, 22.51% Amharic (27.06% across all 52 languages).

Selection can succeed while execution fails. A Spanish request for overdue invoices that becomes `{"query": "facturas vencidas"}` against an English-indexed ERP returns zero hits. The gateway rewrites the designated free-text field to `{"query": "overdue invoices"}` and leaves `{"status": "OPEN"}` untouched. Neither the client agent nor the backend server changes.

BabelArena (2026; 23 languages, 16,077 agent tasks; Claude-Opus-4.8, GPT-5.6-Terra, Gemini-3.1-Pro, Qwen-3.7-Max, Qwen-3.8-Max) adds the cost and the drift:

- Constant input tokens (system prompt, tool definitions, initial user message) rise to **1.14×–1.31×** English in high-resource languages and **1.89×–2.51×** in low-resource languages (Tamil, Telugu, Khmer, Burmese, Lao). Total trajectory input tokens reach **1.69×–2.06×**.
- **91.2%** of sampled language-consistency errors are unexpected switches back to English, usually after raw English tool feedback enters the context. On DeepPlanning, language consistency fell to **57.5%** (Qwen-3.7-Max) and **61.8%** (Claude-Opus-4.8).

Keeping schemas in English removes the constant-input bloat. Translating tool-result prose at the gateway stops English payloads from pulling the agent back into English.

![Multilingual tool-calling accuracy drops and up to 2.51× token bloat. Panel A: MASSIVE-Agents zero-shot AST accuracy for Nova Premier, Claude 3.5 v2 Sonnet, Llama 3.1 405B, and Llama 3.1 70B in English, German, Spanish, the 52-language average, and Amharic, with selective-schema versus full-prompt ablation callouts. Panel B: BabelArena Pass¹ by resource tier and constant-input token multipliers.](docs/images/01-multilingual-tool-calling-gap.png)

*Figure 1. Multilingual tool-calling suffers steep accuracy drops and up to 2.51× token bloat. Sources: ACL Anthology (MASSIVE-Agents, EMNLP 2025), BabelArena (arXiv, 2026), ModelScope BabelArena dataset.*

### Where naive translation fails

Translating every string in a JSON-RPC frame corrupts function names, schema keys, SQL, and enum literals.

| Policy | What the evidence shows |
| --- | --- |
| Full translation of system instructions and tool descriptions | AST accuracy of smaller models (Llama 3.1 8B, Claude 3.5 Haiku) falls by **up to 73%**. Gains on larger models shrink or reverse. |
| Partial translation: English system instructions, localized tool descriptions only | Claude 3.5 v2 Sonnet **+1% to +44% AST**. Nova Pro **+1% to +26% AST**. |
| Independent translation of tasks, schemas, and database fields | **20.0%** broken cross-references and **5.0%** behavioral mismatches. |
| BabelFlow: classify fields, lock shared entities, then translate | Broken references fall to **2.5%**. Behavioral mismatches fall to **0.0%**. |

Model families disagree. Claude 3 and Claude 3.5 Haiku gain a little function-selection accuracy from description-only translation and still lose AST accuracy in most settings. Claude 3.5 Sonnet and Nova Micro improve across nearly all translation setups, because target-language prompts reduce conversational filler in the tool call. The gateway therefore exposes **per-route, per-model policy**, not one global translation switch.

English-centric security rules have the same structural problem. ZHASK Aegis scans with 43 injection rules and 13 PII/secret classes. AegisGate scans 303 HTTP patterns. A low-resource-language payload can walk past those detectors. Canonical-English normalization runs before policy and DLP.

| Value dimension | Native LLM, no gateway | Naive full-payload translation | Rosetta |
| --- | --- | --- | --- |
| AST tool-calling accuracy | 57.37% English → 34.05% average / 6.81% Amharic (Nova Premier) | Up to −73% AST when system instructions are translated | +1% to +44% AST on large models via partial description localization and English argument normalization |
| Broken schema / reference rate | High against English-indexed backends | 20.0% broken references; 5.0% behavioral mismatches | 2.5% broken references; 0.0% behavioral mismatches via typed field extraction |
| Token cost (low-resource) | 1.89×–2.51× constant input; 1.69×–2.06× total input | Higher still: verbose schemas become multi-token scripts | Near 1.00× English in Pivot Mode |
| Response language consistency | 57.5%–61.8% on complex planning; 91.2% of switches return to English | Fluent prose, corrupted JSON and code inside tool output | Prose localized; JSON and code preserved |
| Security and policy | Cross-lingual prompt injection and PII leaks | Translation outside the governance checks | RBAC, injection, and DLP on the raw source payload and the normalized English payload |

---

## Architecture

Rosetta combines three existing patterns:

- **Aegis** — fail-closed interceptor chain, catalog pinning, approval tokens, egress control, DLP, hash-chained audit.
- **IBM AEGIS** — on registration, call `list_tools()`, classify once per schema hash, cache the ontology in Redis, enforce at runtime.
- **BabelFlow** — assign a translation type to every field, lock shared entities, translate the unlocked text, reconstruct the original structure.

![Architecture of the Multilingual MCP Gateway. A multilingual MCP client talks Streamable HTTP or stdio to the gateway. Inside: a schema classifier and locale cache; a five-stage bidirectional interceptor (auth and locale, AST field extractor and entity locker, translation engine router, canonical English governance gate, outbound response localizer and DLP); and a pluggable engine pool (local CTranslate2 with NLLB-200 or Opus-MT, plus cloud NMT and LLM fallback). English-only MCP servers sit on the far side.](docs/images/02-gateway-architecture.png)

*Figure 2. End-to-end gateway. Clients stay multilingual. Backends stay English. The gateway owns classification, translation, governance, and response localization.*

### Request path

1. **S1 — Auth and locale router.** Resolve locale from `_meta.locale`, then `Accept-Language` or `X-MCP-Locale`, then language identification on free-text fields. Read `Mcp-Method` and `Mcp-Name` and skip translation for non-text calls.
2. **S2 — AST field extractor and entity locker.** Load the cached type map. Extract `TYPE_FREE_TEXT` and `TYPE_ENTITY_LOCKED` values. Mask URLs, emails, UUIDs, ISO dates, code spans, glossary terms, and placeholders (`{{var}}`, `%s`, `$1`, `${VAR}`) with sentinel tokens.
3. **S3 — Translation engine router.** Batch the unlocked strings into one call. Restore sentinels. Rebuild the JSON-RPC frame.
4. **S4 — Canonical English governance gate.** Run the fail-closed chain on the raw source payload and on the normalized English payload. First denial wins (`POLICY_DENIED`, `APPROVAL_REQUIRED`).
5. **S5 — Outbound response localizer and DLP.** Translate prose, MRTR prompts, and refusal messages back into the client locale. Leave JSON and code intact. Redact PII and bound output size before the frame reaches the model.

Discovery is separate from that hot path. When an upstream server registers, Rosetta hashes the canonical English tool definition, classifies every leaf field once, and stores the type map in Redis.

### Aegis is the blueprint, and five things change

Four projects share the name Aegis. This design uses them as follows.

| Project | Role in Rosetta |
| --- | --- |
| [vaquarkhan/aegis-mcp-gateway](https://github.com/vaquarkhan/aegis-mcp-gateway) (Java 17, Apache-2.0) | Governance blueprint: hub-and-spoke interceptors, stdio/HTTP hosts, catalog integrity, read-only defaults, single-use approval tokens, egress and DLP. v0.1 is a linear chain (first denial wins). v2.0 is a fixed 8-stage fail-closed path. |
| IBM Research AEGIS ([arXiv:2608.20481](https://arxiv.org/pdf/2608.20481)) | Bootstrapping blueprint: `list_tools()` once, LLM-assisted ontology, Redis cache, enforce at runtime. Their policies target resource abuse. Ours cache translation types. |
| ZHASK Aegis | Complementary patterns: SHA-256 catalog pin, HMAC-SHA256 hash-chained audit, English-centric injection rules that motivate pre-normalization. |
| AegisGate Platform | Complementary patterns: single-binary Go gateway, 303 HTTP patterns, MITRE ATLAS controls. Same English-filter gap. |

Aegis v2.0’s eight stages, in order: typed resource scope, policy verification, egress control, rate and budget controls, screening and semantic review, independent approval, destructive-action receipts, hash-chained audit. Mutating tools stay locked until writes are unlocked and a single-use approval token (`MCP_GW_APPROVAL_TTL_MS`) is presented. Egress always blocks cloud metadata (`169.254.169.254`). v2.0 can run standalone (JWT/JWKS/HS256, OAuth 2.0 RFC 8693, TLS, `POST /mcp`) or as an Apache Knox extension. Stdio mode reserves stdout for JSON-RPC and sends logs to stderr.

Those mechanisms transfer. The Java adapter model does not, for a gateway that must sit in front of arbitrary Python, TypeScript, Go, and Rust MCP servers.

| Component | Aegis today | Rosetta change |
| --- | --- | --- |
| Backend connectivity | Compiled Java SPI adapters per engine (Flink, Kafka, and 26 others) | Universal reverse-proxy pool. Any upstream server over stdio or Streamable HTTP. |
| Interceptors | Read-and-decide gates. Payload mutation is mostly final DLP redaction. | Bidirectional rewrite on the way in and the way out, with a request-scoped translation context (source locale, target locale, entity-lock map). |
| Protocol | Stateful session patterns and the v2.0 HTTP/stdio bridge | Native MCP 2026-07-28 stateless core, plus a compatibility shim for 2025-11-25 servers. |
| Catalog integrity | Any change to a tool description quarantines the server | Two-layer pin. Layer 1 is the canonical English schema hash. Layer 2 is `(canonical_hash, target_locale, glossary_version)` for localized variants. |
| NLP runtime | Pure Java 17 | Python gateway with CTranslate2 in-process. Commercial APIs are just another provider behind the same SPI. |

---

## Operating modes

Policy is per client or per route, because MASSIVE-Agents showed that model family and size change which translation helps.

### Mode A — Pivot Mode (v1 default)

For frontier models that already select English tool names reliably.

- `tools/list` returns the original English `name`, `description`, and `inputSchema`. A compact localized hint can be appended; the schema itself stays English.
- Constant input tokens stay near the **1.00×** English baseline instead of the **1.89×–2.51×** low-resource multiplier.
- On `tools/call`, free-text arguments are normalized to English. Enum literals stay as declared.

```json
{
  "method": "tools/call",
  "params": {
    "name": "search_invoices",
    "arguments": { "query": "facturas vencidas", "status": "OPEN" }
  }
}
```

The upstream server receives:

```json
{
  "name": "search_invoices",
  "arguments": { "query": "overdue invoices", "status": "OPEN" }
}
```

`status` is an enum (`TYPE_IMMUTABLE`). `query` is free text (`TYPE_FREE_TEXT`). The tool name is never translated.

### Mode B — Partial schema localization

For mid-size and regional models, matching the MASSIVE-Agents setup that gained +1% to +44% AST.

- Human-readable tool descriptions and parameter descriptions are translated.
- English `name`, JSON keys, types, and `enum` arrays stay locked.
- System instructions stay English, avoiding the up-to-73% AST drop from full instruction translation.

`schema_translation_mode` in `gateway.yaml`:

| Value | Behavior |
| --- | --- |
| `none` | Pivot Mode. English schema. Arguments normalized. |
| `descriptions_only` | Partial translation of description fields. |
| `hybrid_hint` | English description plus a short localized summary. |

---

## Translation types

Every leaf under `inputSchema.properties` receives exactly one type. The map is cached by schema hash. Operators override any assignment in `gateway.yaml`.

| Type | Locked or translated | What it covers |
| --- | --- | --- |
| `TYPE_IMMUTABLE` | Locked | Tool names, JSON keys, booleans, numbers, UUIDs, file paths, URLs, ISO dates (`2026-11-08`), any string constrained by `enum`. |
| `TYPE_CODE_SYNTAX` | Locked | SQL, GraphQL, bash, JSONPath, and other formal languages. Natural-language translation must not reshape the syntax tree. |
| `TYPE_ENTITY_LOCKED` | Glossary only | Proper nouns, cluster identifiers, and domain terms that must be rendered identically across `tools/list`, `tools/call`, and `resources/read`. |
| `TYPE_FREE_TEXT` | Fully translated | Search queries, ticket bodies, commit messages, free-form notes. |

Runtime then extracts only `TYPE_FREE_TEXT` and `TYPE_ENTITY_LOCKED`, masks placeholders, batches one translation call, restores sentinels, and rebuilds the frame.

Classification runs at discovery (`tools/list` or the registration equivalent). A structured LLM ontology prompt, cached in Redis the way IBM AEGIS caches tool ontologies, may assist. The deterministic rules (enums, types, key names, regex for URLs/UUIDs/dates) always win over the model on fields they can decide.

---

## Protocol

Rosetta targets **MCP 2026-07-28** and keeps a shim for **2025-11-25** servers.

| 2026-07-28 feature | Spec change | Gateway behavior |
| --- | --- | --- |
| Stateless core (SEP-2575, SEP-2567) | `initialize` / `initialized` and `Mcp-Session-Id` are retired. Each request carries protocol version and client metadata in `_meta`. | Locale and mode travel in `_meta`, for example `"_meta": {"locale": "es-ES", "mode": "pivot"}`. Missing locale falls through to `Accept-Language`, then to language identification on free text. |
| Header routing (SEP-2243) | Streamable HTTP requests include `Mcp-Method` and `Mcp-Name` so a gateway can route without parsing the body. | Non-text calls (`ping`, zero-argument tools, numeric-only tools) bypass translation at the HTTP edge. |
| Cacheable lists (SEP-2549) | `tools/list`, `prompts/list`, `resources/list`, and `resources/read` carry `ttlMs` and `cacheScope`. | Localized schemas are served from Redis with those fields set, so client prompt caches stay stable. |
| Multi-round-trip requests (SEP-2322) | Held-open elicitation and sampling streams are replaced by `resultType: "input_required"` and a later retry carrying `inputResponses`. | The elicitation prompt is translated into the user language. On retry, `inputResponses` are normalized back to English. Approval holds use the same path. |

---

## Translation engine tiers

No academic benchmark measures translation latency on MCP JSON-RPC frames specifically. The millisecond and cost figures below are practitioner baselines for CTranslate2 and published API comparisons. Treat them as engineering targets, not as a protocol benchmark.

![CTranslate2 latency, language coverage, and unit cost. Opus-MT short phrase 28.37 ms, Opus-MT full sentence 96.48 ms, NLLB-200 600M full sentence 228.39 ms. Language counts: NLLB-200 200, Google Cloud 189, DeepL or Azure 100+, Amazon Translate 75, SYSTRAN 60+. Unit cost about $4 per million characters self-hosted versus $25 per million on DeepL API Pro.](docs/images/03-translation-engine-tiers.png)

*Figure 3. Local CTranslate2 stays under 250 ms per sentence. Cloud APIs trade cost for commercial licensing and glossary tooling. Sources: Pristren NLLB-200 notes, CTranslate2 practitioner benchmarks, DeepL API buyer’s guide, ChapsVision, Better i18n.*

The gateway exposes one Translation Provider SPI and three tiers.

### Tier 1 — Local air-gapped NMT

[OpenNMT/CTranslate2](https://github.com/OpenNMT/CTranslate2) (MIT, C++ with Python bindings): AVX2/FMA CPU, CUDA and ROCm GPU, INT8/INT16/FP16, dynamic batching. Converted models run about 2–5× faster than PyTorch.

| Checkpoint | Role in Rosetta | Latency baseline | License |
| --- | --- | --- | --- |
| Opus-MT | **Commercial default** | 28.37 ms for a two-word phrase; 96.48 ms for a full sentence | Permissive checkpoints. This is the v1 default. |
| `facebook/nllb-200-distilled-600M` INT8 | Research and non-commercial profile. 200 languages, including 55 low-resource African languages. | 228.39 ms per sentence; about 200–400 ms on longer sentences. Inputs capped at 512 tokens. | **CC-BY-NC.** Off by default in commercial deployments. |

A self-hosted sizing note used in the brief: an AWS `c5.2xlarge` (8 vCPU, 16 GB, about $200/month) processing 50 million characters/month lands near **$4 per million characters** on CPU. That figure is an infrastructure estimate, not a Rosetta benchmark.

### Tier 2 — Commercial NMT

For glossary enforcement, a commercial license, and lower cloud latency.

| Provider | Coverage used for planning | Notes |
| --- | --- | --- |
| DeepL API | ~33 core languages, 100+ in broader comparisons | Pro plan cited at $25 / million characters. Strong European quality. Buyer’s guide cites up to 29× lower median latency than general-purpose LLMs, and a 94% blind evaluation win rate. |
| Google Cloud Translation v3 | 189 languages | Adaptive Translation for small in-domain sets. |
| Azure Translator | 100+ languages | Enterprise glossary support. |
| Amazon Translate | 75 languages | Glossary customization. |
| SYSTRAN | 60+ languages, 150 domain pairs | Specialized domains. |

Phase 2 ships DeepL and Google Cloud v3 connectors first. Azure, Amazon, and SYSTRAN use the same SPI and can follow without another pipeline.

### Tier 3 — Small language model fallback

Sentence-level NMT has no view of the tool schema. Ambiguous, idiomatic, or code-mixed arguments go to a short instruction model prompted with the JSON Schema and the glossary, and constrained to emit valid JSON arguments. Planning baselines from the brief: Llama 3.2 3B (~198 tok/s), Nova Micro (~197 tok/s), Llama 3.1 8B (~182 tok/s). Phase 2 ships the SPI and one adapter. Phase 4 measures whether the fallback earns its latency.

### Hot-path budgets

| Case | Target |
| --- | --- |
| Cache hit (schema map or a repeated argument string) | Under **5 ms p95** added gateway time |
| Cache miss, short argument, Opus-MT INT8, beam 1–2 | Under **120 ms p95** |
| Cache miss, one sentence, NLLB-200 INT8, within 512 tokens | Under **250 ms p95** |
| After translation | **100%** JSON Schema validation against the upstream `inputSchema` (no mutated keys, types, or enums) |
| Cross-field references | At or below BabelFlow’s **2.5%** broken-reference mark |

Configuration is 12-factor: `MCP_GW_CONFIG` points at `gateway.yaml`, environment variables override it. The air-gapped profile runs with local CTranslate2 weights and no outbound translation traffic. Telemetry is OpenTelemetry plus Prometheus `/metrics`: latency by language pair, token savings, cache hit rate, and governance deny codes. Health endpoints: `/healthz`, `/readyz`.

---

## Requirements

### Functional

| ID | Category | Requirement |
| --- | --- | --- |
| FR-01 | Transport | MCP 2026-07-28 Streamable HTTP (`POST /mcp` with `Mcp-Method` and `Mcp-Name`) and `--stdio` (stdout is JSON-RPC only; logs go to stderr). Compatibility bridge for 2025-11-25 servers. |
| FR-02 | Locale | Resolve language from (1) `_meta.locale`, (2) `Accept-Language` or `X-MCP-Locale`, (3) language identification on inbound `TYPE_FREE_TEXT` when no explicit locale is present. |
| FR-03 | Classifier | On `tools/list`, classify every leaf into the four translation types. Overrides via `gateway.yaml` and environment variables. |
| FR-04 | Entity locking | Mask URLs, emails, UUIDs, ISO dates, code spans, `${VAR}` placeholders, and glossary terms with indexed non-translatable tokens. Restore them after translation. |
| FR-05 | Schema localization | `schema_translation_mode`: `none`, `descriptions_only`, `hybrid_hint`. |
| FR-06 | Response localization | On `tools/call` and `resources/read`, translate prose, `input_required` prompts, and refusal messages (`POLICY_DENIED`, `APPROVAL_REQUIRED`). Preserve structured JSON and code. |
| FR-07 | Governance | Fail-closed chain on **both** the raw source payload and the normalized English payload: JWT / OAuth 2.0 RFC 8693, per-tool RBAC, SHA-256 catalog pin, prompt and shell injection scanning, egress allow-list (block `169.254.169.254`), single-use approval tokens, DLP redaction, HMAC-SHA256 hash-chained audit. |

### Non-functional

- Latency budgets in the table above.
- 100% schema-validation pass after translation, using the same structural standard as BFCL and MASSIVE-Agents AST scoring.
- Cross-field broken references ≤ 2.5%.
- Full offline operation on the air-gapped profile.
- OpenTelemetry and Prometheus as first-class exports, not an afterthought bolted on in Phase 4. Phase 1 already emits method, locale, and cache spans so later phases attach translation and deny-code attributes.

---

## Building blocks we reuse

No existing project is a runtime, schema-aware multilingual MCP gateway. The surrounding blocks are real, licensed for reuse, and should be forked or imported rather than rewritten.

### A. Gateway and plugin spine

**[IBM/mcp-context-forge](https://github.com/IBM/mcp-context-forge)** — Python 3, FastAPI, Apache-2.0. **This is the v1 base.**

Reuse its MCP, A2A, and REST/gRPC gateway, asyncio routing, Redis cache and cluster state, PostgreSQL/SQLite persistence, OpenTelemetry, virtual servers, and the 40+ plugin framework. IBM Research built AEGIS on that plugin framework: `list_tools()` at bootstrap, an LLM ontology step, Redis cache, runtime enforcement. Rosetta uses the same hook for the AST translation classifier and runs CTranslate2 in-process. `mcpgateway.translate` in that repo bridges **network protocols** (stdio ↔ HTTP/SSE, gRPC ↔ MCP). It does not translate human languages. That module is the insertion point we extend, not a feature we already have.

**[vaquarkhan/aegis-mcp-gateway](https://github.com/vaquarkhan/aegis-mcp-gateway)** — Java 17+, Maven, Apache-2.0. **Pattern source for Phase 3, not the v1 fork.**

Reuse the ideas: 8-stage fail-closed chain (`aegis-engine`, `aegis-mcp-guardrails`, `aegis-mcp-security`), SHA-256 catalog pinning, single-use approval tokens, DLP redaction, egress control. The Knox extension and the per-engine SPI adapters stay on Path B.

**Lighter proxies, if the ContextForge surface is more than a given deployment needs:**

- [achetronic/mcp-proxy](https://github.com/achetronic/mcp-proxy) (Go, Apache-2.0)
- [sparfenyuk/mcp-proxy](https://github.com/sparfenyuk/mcp-proxy) (Python)
- lucky-aeon/mcp-gateway

They already bridge stdio to Streamable HTTP/SSE, namespace tools as `{server}_{tool}`, validate OAuth discovery (RFC 8414/9728), and filter JWKS/CEL claims. Useful reference for the Phase 1 edge. They are not the spine, because they have no plugin or Redis ontology cache.

### B. Structure-preserving translation

**[QwenLM/BabelArena](https://github.com/QwenLM/BabelArena)** — BabelFlow pipeline.

Reuse the offline logic: data-flow analysis assigns translation types, only translatable text is extracted, shared entities are locked across tools, databases, and prompts, and the original structure is rebuilt. Port that into the live `tools/list` and `tools/call` interceptors. BabelArena itself is a benchmark and dataset generator, not a proxy.

### C. Local translation runtime

**[OpenNMT/CTranslate2](https://github.com/OpenNMT/CTranslate2)** — C++ / Python, MIT.

Reuse the inference runtime, `ct2-transformers-converter` for INT8, dynamic batching, and the Opus-MT and NLLB-200 checkpoints described above. Respect the NLLB CC-BY-NC terms in the default commercial profile.

### D. An MCP translation repo that is a different product

**[reinier-millo/i18n-mcp-server](https://github.com/reinier-millo/i18n-mcp-server)** is an MCP *tool* a coding agent calls to translate static JSON localization files inside a repository. It does not sit on the wire, and it does not see `tools/list` or `tools/call` for other servers. Rosetta does not wrap it. The two can coexist: one localizes a codebase, the other normalizes live tool traffic.

---

## Competitor landscape

Every shipping MCP gateway in this set focuses on transport, authentication, routing, or English-centric security. None of them normalize natural language or localize schemas on the JSON-RPC path.

| Project | Stack and license | What it already does | The gap Rosetta fills |
| --- | --- | --- | --- |
| vaquarkhan/aegis-mcp-gateway | Java 17+, Apache-2.0 | Fail-closed interceptor chain, SHA-256 catalog pinning, single-use approval tokens, egress and DLP, Knox extension, 28 Apache data adapters | No natural-language translation. Tool descriptions, queries, and regex/DLP checks are assumed to be English. Engines require a Java SPI adapter each. |
| IBM/mcp-context-forge | Python (FastAPI), Apache-2.0 | Unified MCP/A2A/REST/gRPC registry, 40+ plugins, Redis, TOON compression, virtual servers, `mcpgateway.translate` | `mcpgateway.translate` translates protocols (stdio ↔ HTTP/SSE, gRPC ↔ MCP), not human languages. |
| IBM Research AEGIS | Python + OPA + Redis on ContextForge | Offline LLM bootstrap of tool ontologies cached in Redis; parameter-aware OPA policies against CPU and memory abuse | Evaluates resource-abuse thresholds. Does not translate multilingual arguments or schemas. |
| Bifrost (ai-gateways) | Go, Apache-2.0 | `/mcp` over HTTP/SSE, stdio/HTTP/SSE upstreams, per-key and per-request tool filtering, OAuth token exchange, LLM routing across 25+ providers | Access control and routing. Non-English arguments pass straight through to English-only backends. |
| microsoft/mcp-gateway | C# (.NET 8), MIT | Kubernetes StatefulSet, stateless MCP 2026-07-28 reverse proxy, Entra ID RBAC, React portal, dynamic tool router | Routes by tool name and Entra role. No language normalization or schema localization. |
| Docker MCP Gateway | Go, MIT | Docker CLI plugin that isolates local stdio MCP servers in containers, with OAuth and profile-based tool toggles | Container isolation and a transport wrapper. No semantic payload transformation. |
| ZHASK Aegis and AegisGate | Go (19.1 MB binary) / ClickHouse, Apache-2.0 / MIT | 43 prompt and shell injection rules, 303 HTTP patterns, MITRE ATLAS controls, CharCNN-BiLSTM detector, HMAC-SHA256 audit | Scanners are English-centric. Non-English tool arguments are not normalized before English upstream APIs and English rules run. |
| QwenLM/BabelArena (BabelFlow) | Python benchmark suite | Structure-preserving type assignment and entity locking across 23 languages | Offline dataset generator. Not a live, low-latency MCP gateway. |

---

## Phased build

Sixteen weeks, all of it in this repository, in Python. Each phase has a demo, a definition of done, and an explicit stop line so the next phase does not start early and widen the surface.

Suggested layout once Phase 1 starts:

```text
rosetta/
  proxy/         # stdio + Streamable HTTP, header routing, locale
  classifier/    # four translation types, YAML overrides, schema hash
  locking/       # sentinel mask and restore, glossary
  translate/     # provider SPI (wired in Phase 2)
  governance/    # fail-closed chain (wired in Phase 3)
  cache/         # Redis type maps, locale cache, ttlMs
gateway.yaml
```

### Phase 1 — Proxy, catalog pin, AST classifier (weeks 1–4)

Stand up the wire and prove we can *decide* what is translatable without calling a translator.

**Build**

- Stateless MCP 2026-07-28 reverse proxy: `--stdio` and Streamable HTTP `POST /mcp`.
- Header routing on `Mcp-Method` and `Mcp-Name`. Bypass list for `ping`, zero-argument tools, and numeric-only tools.
- Locale resolution: `_meta.locale`, `Accept-Language`, `X-MCP-Locale`. Language identification is stubbed behind the FR-02 interface and returns “locale required” until Phase 2 attaches a detector.
- Legacy 2025-11-25 session bridge sufficient to front one existing server.
- SHA-256 pin of the canonical English tool definition. Mismatch quarantines the tool (rug-pull).
- Deterministic classifier: `TYPE_IMMUTABLE`, `TYPE_CODE_SYNTAX`, `TYPE_ENTITY_LOCKED`, `TYPE_FREE_TEXT`.
- Entity locker: mask and restore URLs, emails, UUIDs, ISO dates, numbers, code spans, and `${VAR}` / `{{var}}` placeholders.
- `gateway.yaml` overrides and environment-variable overlay.
- English passthrough: a request already in English is forwarded byte-stable in structure.
- OpenTelemetry spans for method, server, and cache lookup.

**Demo.** Register a fixture MCP server. `tools/list` produces a type map. A Spanish `tools/call` produces a translation plan (the exact strings that would be sent to NMT) and a reconstructed frame in which every key, enum, and code span is unchanged. No NMT process is running.

**Done when**

- Unit tests show 100% preservation of JSON keys, data types, and enum values across a synthetic schema suite.
- The entity locker round-trips every sentinel.
- An unseen schema hash is classified once and stored. A repeated hash is a cache hit.
- A changed upstream schema hash quarantines that tool until an operator accepts the new pin.

**Stop line.** No CTranslate2, no cloud API keys, no governance denies, no response translation.

### Phase 2 — Translation router and locale cache (weeks 5–8)

Make Pivot Mode real, then turn on description localization and response localization.

**Build**

- CTranslate2 worker via `ct2-transformers-converter --quantization int8`.
- Opus-MT as the commercial default. Beam size configurable (`1` for speed, `4` for quality). Dynamic batching.
- NLLB-200-distilled-600M behind an explicit non-commercial profile flag, default off.
- Async connectors for DeepL and Google Cloud Translation v3.
- Tier 3 SPI plus one small instruction-model adapter for code-mixed arguments.
- FastText (or equivalent) language identification to complete FR-02 when `_meta.locale` is absent.
- Redis (with an in-memory fallback for single-node dev): translation type maps, localized `tools/list` documents, and repeated argument strings. Responses include `ttlMs` and `cacheScope`.
- Mode A end to end on `tools/call`.
- Mode B `descriptions_only` and `hybrid_hint` on `tools/list`.
- FR-06 prose localization on tool results. Code fences and JSON blocks stay untouched.
- Two-layer cache key: `(canonical_hash, target_locale, glossary_version)`.

**Demo.** The invoice call. Client sends `query=facturas vencidas`, `status=OPEN`. Upstream observes `query=overdue invoices`, `status=OPEN`. The tool result’s prose returns in Spanish. A second identical call is a cache hit. `tools/list` in Pivot Mode is the original English schema.

**Done when**

- Pivot Mode, description localization, and prose round-trip pass integration tests on fixture servers in at least English, Spanish, and one non-Latin script.
- Cache-hit overhead is measured against the 5 ms p95 budget, and Opus-MT short-argument misses are measured against the 120 ms p95 budget. Misses are reported, not hidden.
- Post-translation frames validate against the upstream JSON Schema in every test case.
- The air-gapped profile completes the demo with network egress to translation APIs disabled.

**Stop line.** No approval tokens, no injection corpus, no MRTR elicitation, no benchmark harness.

### Phase 3 — Governance and MRTR (weeks 9–12)

Put Aegis’s fail-closed chain on both sides of translation, in Python, on the ContextForge plugin path.

**Build, in this order**

1. Authenticate (JWT / OAuth 2.0 RFC 8693 token exchange).
2. Route and kill-switch.
3. Per-tool RBAC.
4. Approval hold for mutating tools.
5. Schema, injection, and DLP gate on the **raw** payload and the **canonical English** payload.
6. Hash-chained HMAC-SHA256 audit.

Map those steps onto Aegis v2.0’s eight stages (typed scope, policy, egress, rate and budget, screening, independent approval, destructive-action receipts, hash-chained audit). Egress allow-list includes a hard block of `169.254.169.254`. Destructive tools stay unregistered until writes are unlocked.

- Single-use, scope-bound approval tokens. The token binds to the **canonical English argument hash**, so a localized retry cannot swap the action. The operator-facing prompt is localized.
- MRTR: when the upstream server or the approval gate returns `resultType: "input_required"`, translate that prompt into the user language and normalize `inputResponses` on the retry.
- Refusal messages `POLICY_DENIED` and `APPROVAL_REQUIRED` localized per FR-06.
- Stable deny codes. First denial wins.

**Demo.** A non-English injection string is caught on the raw payload or on its English normalization, and the upstream tool is never called. A destructive tool returns `APPROVAL_REQUIRED` with a localized prompt; presenting the single-use token, bound to the English argument hash, lets the call through once.

**Done when**

- A fixture corpus of prompt and shell injections in English plus at least two other languages is denied before the upstream `tools/call`.
- DLP redacts PII on the outbound localized frame.
- An approval token replay, or a token whose argument hash does not match the canonical English arguments, is denied.
- MRTR elicitation round-trips: user-language prompt out, English `inputResponses` in.

**Stop line.** No paper-benchmark runner and no Helm chart in this phase. Security fixtures are integration tests, not the Phase 4 harness.

### Phase 4 — Evidence and packaging (weeks 13–16)

Show the four gaps closing, and ship a stack someone else can run.

**Build**

- Evaluation runner over public MASSIVE-Agents (52 languages) and BabelArena (23 languages) data.
- Report, per mode: AST accuracy, Pass^1 / Pass^3, language consistency, and constant-input token multiplier, Mode A against Mode B, gateway on against gateway off.
- Docker Compose and a Helm chart under `charts/`.
- Profiles: `quickstart`, `air-gapped`, `high-security`.
- Grafana or equivalent dashboards on the Prometheus and OpenTelemetry exports already emitted since Phase 1: latency by language pair, cache hit rate, token savings, deny codes.

**Demo.** `docker compose --profile quickstart up` fronts a fixture English MCP server. A Spanish client completes the invoice scenario. The eval runner writes a report comparing Pivot Mode token cost with fully localized schemas.

**Done when**

- The report is generated from the public datasets by a single command and checked into the release notes.
- Quickstart and air-gapped profiles both boot from the documented commands.
- High-security profile enables the Phase 3 chain by default, with fail-closed behavior when Redis or the translation worker is unavailable.

**Stop line for v1.** Knox hosting, Apache engine adapters, a glossary UI, and automatic per-model policy selection wait for a later release. Phase 4 records them as follow-ons in the report rather than stretching the chart to include them.

### Phase summary

| Phase | Weeks | User-visible result | Definition of done |
| --- | --- | --- | --- |
| 1. Proxy and classifier | 1–4 | English passthrough. A translation *plan* for every other call. Rug-pull pin. | 100% key, type, and enum preservation. Cache the type map by schema hash. |
| 2. Translation and cache | 5–8 | Pivot Mode live. Descriptions and result prose can be localized. Offline Opus-MT. | Invoice demo. Schema still validates. Air-gapped profile runs. Latency measured against budget. |
| 3. Governance and MRTR | 9–12 | Cross-lingual injection denied. Localized approval and elicitation. | Raw and English payloads both scanned. Approval token bound to the English argument hash. |
| 4. Evidence and packaging | 13–16 | Compose profiles and a benchmark report. | One-command eval. Quickstart, air-gapped, and high-security profiles boot. |

---

## Naming and license

The product name is **Rosetta MCP Gateway**. This repository is `rosetta-mcp`.

Names already taken, and avoided: `library-of-babel-mcp`, BabelArena / BabelFlow, `hermes-mcp-gateway`, and `aegis-mcp-gateway`.

| Candidate | Why it was considered |
| --- | --- |
| `rosetta-mcp-gateway` | **Chosen brand.** The Rosetta Stone is structure-preserving translation across scripts. The `-mcp-gateway` suffix matches the category. |
| `dragoman-mcp-gateway` | A dragoman was a diplomatic interpreter and gatekeeper. Use this name if a later edition wants the security role in the title. |
| `polyglot-aegis-mcp` | Fits a Java fork that should stay visibly downstream of Aegis. |
| `glossa-mcp-gateway` | Short CLI-style name (`glossa-mcp serve`), glossary heritage. |
| `targum-mcp-gateway` | Spoken translation with added context. Cleaner namespace, less immediately legible. |
| `pangloss-mcp-proxy` | Fits a tiny sidecar that refuses the governance scope. |

Core license: **Apache-2.0**, aligned with ContextForge, Aegis, and the official TypeScript MCP SDK. NLLB-200 weights stay out of the default image because of CC-BY-NC. Opus-MT checkpoints shipped in the air-gapped profile must be ones whose model license allows commercial use; the README of that profile will name the exact checkpoint.

---

## Source of this document

This README is the engineering scope for Rosetta, written from the architecture brief *Building a Multilingual Model Context Protocol (MCP) Translation Gateway* (value analysis, Aegis review, system design, and the 16-week roadmap), plus the open-source reuse map and competitor gap analysis supplied with it. Figures 1–3 are the original figures from that brief.

### Works cited in the brief

1. MASSIVE-Agents: A Benchmark for Multilingual Function-Calling. Amazon Science. https://www.amazon.science/publications/massive-agents-a-benchmark-for-multilingual-function-calling-in-52-languages
2. MASSIVE-Agents. Findings of EMNLP 2025. https://aclanthology.org/2025.findings-emnlp.1099/ and https://aclanthology.org/2025.findings-emnlp.1099.pdf
3. BabelArena: A Large-Scale Multilingual Benchmark for LLM Agents. https://github.com/QwenLM/BabelArena and https://arxiv.org/abs/2609.23490
4. vaquarkhan/aegis-mcp-gateway. https://github.com/vaquarkhan/aegis-mcp-gateway
5. AEGIS: Preventing Cross-Domain Resource Abuse in MCP. IBM Research. https://arxiv.org/pdf/2608.20481
6. ZHASK Aegis. https://zhask.io/products/aegis and https://zhask.io/docs/aegis
7. AegisGate Platform. https://aegisgatesecurity.io/platform/
8. The 2026-07-28 Specification. Model Context Protocol Blog. https://blog.modelcontextprotocol.io/posts/2026-07-28/
9. MCP SDKs (2025-11-25 docs index). https://modelcontextprotocol.io/docs/2025-11-25/sdk
10. NLLB-200 practitioner notes. https://pristren.com/blog/nllb-200-translation-model/
11. CTranslate2. https://github.com/OpenNMT/CTranslate2
12. The Buyer’s Guide to Translation APIs. DeepL. https://www.deepl.com/en/reports/translation-api-buyers-guide
13. Enterprise AI translation comparisons. https://www.chapsvision.com/blog/comparing-enterprise-ai-translation-software/ and https://better-i18n.com/en/blog/best-ai-translation-tools-2026/
14. Berkeley Function Calling Leaderboard. https://gorilla.cs.berkeley.edu/blogs/8_berkeley_function_calling_leaderboard.html
15. NLLB-200 model card license (CC-BY-NC), as cited in the brief. Commercial profiles default to Opus-MT or Tier 2 APIs.
16. Related gateway reading: Microsoft MCP Gateway (https://microsoft.github.io/mcp-gateway/), Speakeasy (https://www.speakeasy.com/resources/mcp-gateway), TrueFoundry (https://www.truefoundry.com/blog/what-is-mcp-gateway).
