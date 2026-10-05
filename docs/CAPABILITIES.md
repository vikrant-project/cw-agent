# Capabilities and configured limits

CW Agent selects work according to the user's requested result. It distinguishes conversation, source code, web apps and native media. Completion requires the requested output format, executed checks and an explicit review tied to the current files.

| Capability | Available behavior | Practical limit |
|---|---|---|
| Chat | Direct single-assistant reply and tenant-scoped recent conversation | Model availability and context limits |
| Coding | Python, Node and PHP tools, task-specific source and tests | Installed executables and offline dependencies |
| Web verification | Fresh desktop/mobile browser contexts and core journey assertions | Available browser dependencies and isolated local target |
| PowerPoint | Editable text, charts, tables, diagrams and speaker notes | Generator quality still needs factual and pixel review |
| Images | Actual native generation, current raster inspection and reference repair | Provider capacity, native resolution and output quality |
| Documents/research | Requested-format checks and primary-source reads where allowed | Actual file tooling must be available |
| Mobile | Source work and available build verification | SDKs, signing credentials and device access |
| Delivery | Owner portal downloads and connected WhatsApp native attachments | Session health and uncertain-send handling |

## Default operating envelope

| Setting | Value | Unit |
|---|---:|---|
| Role slots | 10 | Authenticated profile mappings |
| Active task lanes | 2 | Concurrent tasks |
| Model budget per task | 100 | Submissions |
| Daily model budget | 600 | Submissions per UTC day |
| Role turn limit | 16 | Decisions per role |
| Repair limit | 3 | Cycles |
| Model timeout | 360 | Seconds |
| Task deadline | 7,200 | Seconds |
| Generated command timeout | 90 | Seconds |
| Visual inspection batch | 4 | Images/slides |

These values describe the published configuration. They are not throughput benchmarks. Provider-side limits can be stricter.

## Outcomes

An answered conversation can finish immediately. An artifact becomes ready only after fresh evidence and independent approval. A visible needs-attention result records unavailable capabilities, exhausted limits or remaining defects. Cancellation and one bounded crash recovery retain history. The controller cannot promise that every arbitrary request will succeed.

[Architecture](ARCHITECTURE.md) · [Validation](VALIDATION.md)
