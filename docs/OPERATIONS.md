# Coding Workshop

A PHP account portal and a durable Python coordinator drive ten existing AntiGravity CLI login accounts: intake, research, architecture, backend, frontend, mobile, testing, debugging, independent review and release. These are real model-driven workers, not a collection of skill files. Intake selects an adaptive subset and assigns task-specific responsibilities. Conversation uses one assistant and produces a direct answer; larger builds can use all ten. Selected roles run sequentially over shared task memory so edits do not race. Recent answered conversation is scoped to the same user.

Users send any request in the portal or connect their own WhatsApp and chat in **Message yourself**. Plain messages are classified automatically; `/build ...` expresses a build request and `/chat ...` is also supported. Intake records acceptance criteria and creates temporary task-specific playbooks. Specialist roles generate source, execute sandboxed commands, test, debug and review. Failed work gets up to three revision cycles. A failed or interrupted task remains visible instead of running forever or being called successful.

## Portal and privacy

PHP uses password hashes, session rotation, HttpOnly/SameSite cookies, CSRF checks, prepared SQL, invitation-based signup and rate limits. Every task, event view and download checks the signed-in user. The invitation code is in `portal-data/invite.key`; share it only with intended users. Generated source ZIPs and the SQLite database are outside the web root.

Example deployments use an HTTPS reverse proxy in front of a loopback-only PHP service. Configure your own hostname, certificates and renewal. Use PHP-FPM for larger production deployments.

## Model and execution boundary

`cli_sandbox.py` uses the existing role-specific OAuth profiles in ephemeral homes and a provider-only CONNECT proxy. CLI account locking must be shared by any other service using these same profiles. No portal database, WhatsApp credentials, SSH credentials or other tenant projects are mounted in a model sandbox.

Generated commands execute in a separate network namespace and unprivileged bubblewrap filesystem. They can read runtimes and write only their task tree. CPU, memory, process count, output size and wall time are bounded. Dependency downloads are disabled inside generated code; the agent should use installed tools or document a missing requirement. Supported built-in executables include Python, Node and PHP. Mobile source generation is supported, but APK/IPA compilation and physical-device verification need their actual SDKs and devices.

Allowed primary documentation requests are explicit in `config.json`, resolve only public IPs, pin the connection address and do not follow redirects. Temporary model-created playbooks are task data; they cannot grant additional tools, network access or permissions.

## Native PowerPoint output

PowerPoint requests preserve their requested `.pptx` format and slide count in a controller output contract. The `presentation` tool uses a trusted PptxGenJS renderer inside the task sandbox. It creates editable text, charts, network diagrams, tables and speaker notes from structured content. The independent `presentation_check` opens the actual file with LibreOffice, checks page count and renders every slide to a PNG. Both the initial and final testing cycles require new execution evidence. Package inspection rejects missing PowerPoint files, wrong slide counts, empty slides and missing requested charts. A Markdown outline cannot satisfy a PowerPoint request.

Verified deliverables are exported to private per-task download folders. The portal exposes a direct PowerPoint download alongside the supporting source ZIP. The WhatsApp bridge sends the native document with its PowerPoint MIME type. Only ready outputs are delivered, and superseded candidate notifications are retained with a visible status instead of sending unfinished drafts.

Install the artifact runtime at `/opt/coding-artifacts`: copy the supplied `artifact-runtime/package.json` and lockfile, run `npm ci --ignore-scripts`, and copy `render_presentation.cjs` and `check_presentation.cjs` into that directory. Install LibreOffice Impress, poppler-utils and fonts-liberation. Keep this runtime read-only to generated projects. The source does not bundle dependency binaries or account credentials. Render checks establish file usability and page count; factual and visual quality still require independent review.

Web tasks require controller-recorded passing Playwright evidence, including separate fresh desktop and mobile contexts. The tester can exercise signup/login, forms, invalid inputs and core journeys. JavaScript errors and horizontal overflow fail the harness. External network traffic is unavailable in the namespace. Other code tasks require executed tests and independent model review. Document and research artifacts require actual file presence, signature/integrity checks and independent content review, without invented application tests. Ordinary conversation returns an `answered` result without a source archive or coding pipeline. This verifies the selected acceptance checks, not every possible bug or arbitrary task.

Code source packaging happens after release documentation and a new tester/reviewer pass. Testers cannot finish a web verification cycle without executing a fresh browser check. Failed final checks return to bounded debugging and retesting; previous-cycle evidence cannot satisfy the final gate. Packages contain source plus `WORKSHOP_EVIDENCE.json`. Task events contain short decisions and tool evidence, not private chain-of-thought.

## WhatsApp

The connector uses the unofficial Baileys library. Each portal user scans their own device-link QR. Sessions are separately encrypted with AES-256-GCM, saved outside source and web roots, and never sent to coding models. Text messages sent by the connected user to their own self-chat are accepted. Bot-generated text carries a marker and is ignored on incoming events to prevent feedback loops. Groups and other senders cannot initiate builds. History backfills are ignored and message IDs deduplicate task creation.

No real WhatsApp account is linked automatically. Real QR production has been checked. The current user has linked an account; delivery status is recorded separately for each notification. A connected state alone does not prove every future message or ZIP delivery. Reconnects are bounded; uncertain notification delivery is visible and is not blindly repeated. The sidecar runs as the unprivileged coding-whatsapp account with its own bridge-private secrets directory.

## Operations

For a fresh installation, place this source at `/opt/coding-workshop`, install PHP CLI with PDO SQLite, Python 3 with venv, Node 20+, bubblewrap, iproute2, systemd and Caddy. Install AntiGravity CLI and log in to the ten Linux profiles listed in `state.py`; credentials are not in this archive. Run `python3 setup.py` to initialize the account database and private keys without starting services. Use `npm ci --ignore-scripts` in `whatsapp/` for the pinned connector dependencies. Put the Playwright virtual environment at `/opt/coding-runtime/venv`, install `requirements-browser.txt`, install Chromium with `PLAYWRIGHT_BROWSERS_PATH=/opt/coding-runtime/browsers`, and copy `browser_runner.py` to `/opt/coding-runtime/browser_runner.py`.

Before enabling the supplied systemd services on another server, update the HTTPS hostname/IP and certificate paths in `Caddyfile`, provision its actual certificate and renewal, and ensure `/opt/coding-runtime` is readable by the unprivileged runner. `scope.json` contains only the public model-provider origin allowlist; all OAuth and WhatsApp credentials remain private.

Configuration: `config.json`; private provider scope: `scope.json`; database: `portal-data/portal.sqlite3`; task trees: `projects/<task-id>`; private shared memory: `private/memory/<task-id>`; ZIPs: `downloads/<task-id>.zip`.

The internal controller unit suite is excluded from this public repository. Linux is required for native sandbox execution. The systemd worker, gateway, internal bridge, WhatsApp sidecar, loopback PHP portal and TLS proxy are separate services. Restart policies are limited to three starts per hour. On a worker crash, each in-flight task can be requeued once using its retained source and original model-call budget. Intake replans and all test/review evidence must be regenerated. A second interruption or exhausted budget remains visible as needs attention; cancellation is respected.

Each build runs in a separate task subprocess that imports the latest reviewed controller code. The parent coordinator maintains heartbeats and enforces a hard task deadline. Model transport failures have up to two retries. A role that reaches its turn limit hands its partial contribution to testing/debugging with a visible event; this does not satisfy the release gate. Read-only reviewers must provide a fresh explicit verdict. Testers may write tests and TEST_PLAN.md, while debugging changes implementation code. Current source and compact tool history prevent stateless reread loops.

The **Revise project** action copies only that user's existing task source into a new private build. It does not overwrite the previous delivered version. Generated applications are tested using local isolated HTTP servers; automatic public hosting of arbitrary generated applications is not included in this version.

## Reference documentation

- PHP sessions: https://www.php.net/manual/en/features.session.security.management.php
- Fresh browser contexts: https://playwright.dev/python/docs/api/class-browsercontext
- Playwright browser runtimes: https://playwright.dev/python/docs/browsers
- Baileys connection and pairing: https://github.com/WhiskeySockets/docs/blob/main/quickstart.mdx
- IP TLS certificates and renewal: https://letsencrypt.org/2026/03/11/shorter-certs-certbot

Private keys, real account credentials, QR codes and login data are intentionally excluded from this source package.


## Autonomous goal workflow, version 2

The AntiGravity accounts create task solutions. Controller maintenance does not author or repair a user's application, report or presentation. Intake understands the message, replies directly for ordinary chat, or states an explicit goal, requested file manifest, numbered acceptance criteria and task-specific assignments. The existing account slots can act as writers, analysts, designers or engineers according to the request. Temporary playbooks cover how to implement, test and repair that particular task.

Independent testing maps every acceptance criterion to real current-cycle evidence identifiers with `verify`. Checks include exact files and meaningful behavior/content, rather than treating an exit code or a peer's summary as sufficient. The reviewer independently compares the original request with final files and criterion results and must state whether the goal is achieved. It cannot edit the implementation. Failed checks and review issues route back to debugging and fresh testing automatically. Release documentation is followed by a new final tester/reviewer pass.

Source and test-file fingerprints invalidate evidence when the checked project changes. Requested native artifacts are inspected for real package signatures; renamed Markdown cannot count as a Word, Excel or PowerPoint file. Validated files are available directly in the owner's portal and are delivered through their connected WhatsApp session. The portal shows the goal, expected outputs, criteria, evidence identifiers, failures and review issues. It exposes concise decisions and actual actions, not private chain-of-thought.

This is orchestration and tool support for the existing Gemini model, not a claim to retrain model weights. Missing SDKs, integrations, credentials, unsupported output tooling, exhausted budgets and refusals remain explicit limitations. The worker is available continuously; each task has bounded retries and repair cycles. Capability is established by executed acceptance tests for that request, not a promise that arbitrary requests always succeed.


## Native media and visual verification

Image requests use `image` plans and `image_generate`, backed by the existing AntiGravity CLI native image-generator capability. The isolated CLI profile's generated raster artifact is collected before its temporary home is removed. The controller never draws substitute pixels or creates a user's image from code. Install `python3-pil` for trusted image decoding. A generated raster must meet the requested size/aspect requirements and retain its native generation hash. Both independent testing and review must open the actual pixels through `visual_check`; publishing requires these checks again after release changes.

PowerPoint testing renders all slides. Both tester and reviewer must inspect every preview, in batches of at most four, and their pixel hashes must match the actual render evidence. Technical educational decks also require successful source reads. Research accepts a short `focus` phrase to extract relevant sections from long primary documentation. The trusted renderer keeps diagram labels apart, uses 14pt edge/axis labels and rejects diagrams without readable label space. Full-width layouts and editable network symbols support larger architecture visuals. Model reviewers still make qualitative and factual judgments; these checks cannot guarantee perfect content.

Native-provider capacity errors remain distinct from refusals and tool-validation errors. Image generation may try one other existing account after a quota/capacity failure; it never loops indefinitely or substitutes a placeholder. Concrete failures appear in task evidence and the user-visible error. Unsupported integrations remain explicit instead of being marked done.


Decision sessions select the custom `agents/cw-controller.md` agent and disable slash-command expansion. They emit a single controller action; they do not run their own coding loop. Actual completed native tools are audited separately from the CLI's registry metadata. Image generation and vision run in dedicated native sessions. Native image/PowerPoint files are published unchanged after independent testing/review; they do not receive an irrelevant application setup-documentation phase. A repaired task's final ready notification is queued even when an earlier failure notification was already sent; uncertain deliveries are not blindly repeated.


## Media repair operations

The queue has two bounded lanes, with a shared hard limit of two active tasks and shared per-account locking. `coding-queue-lane.service` uses the same canonical task runner, approval gates and model budget as the primary worker. Recovery excludes a live task owned by the other lane. Each lane can recover its interrupted task once; recovery retains repaired source and model calls. Atomic budget reservations cover both lanes.

Decision sessions carry the complete JSON action in a required structured-object payload, with versioned compatibility for older serialized callers. Role- and phase-specific schemas retain only relevant parameters and advance intake from accepted plan to playbook to handoff. Media testing advances from a fresh artifact check through all actual pixel batches to verification and an independent review. The controller validates every action. For CLI versions that append an incomplete structured envelope after a complete fenced response, the decoder accepts a single complete same-action object from the terminal response; ambiguous responses are rejected. This recovery does not read model reasoning or tool-log prose.

Writing `presentation.json` automatically rebuilds the native PowerPoint. The requested-topic contract provides a minimum visible coverage check, while independent reviewers still assess meaning and factual accuracy. Rebuilding invalidates old render and visual evidence. Native media may be published directly after unchanged final testing and review, without an irrelevant application documentation stage.

Native raster export uses a root-private manifest, deduplicates copies by hash and selects the actual reported artifact path. Bytes are fully decoded before use. Successful generator invocation or a model's claim alone cannot prove an image was created. The provider must explicitly report creation, and the decoded output must differ from every staged reference hash. Failed generations cannot silently export cached reference images. The manifest and raw provider logs remain private; they are excluded from this archive. Qualitative failures, generation limitations and provider capacity errors remain visible and bounded.


A completed native pixel inspection may support individual observed facts even when it rejects the overall image. Such a partial result remains a failed visual gate and cannot authorize publishing. Timed-out tools, failed commands, missing pixel observations or mismatched image hashes cannot support passing criteria. Provider stream interruptions receive bounded transport retries; malformed function-call responses use bounded formatting retries. Neither is misreported as a policy refusal.


Account admission uses the shared per-account file lock before reserving a model call or starting its execution timeout. The admitted descriptor is passed only to the trusted launcher and checked against the expected role account. A second queue lane waits without concurrent OAuth use or premature model timeouts; cancelled or persistently busy work follows bounded failure handling. Legacy callers still take the same lock in the launcher.


Both provider CONNECT hops retain idle connections for the configured model timeout plus 30 seconds, with a 45-second minimum. A long provider response therefore has the same execution window as the calling model session. The session timeout and task deadline remain enforced; this does not increase generation attempts or model budgets. Gateway maintenance is performed under all shared account locks after active handlers have drained.

Every native image generation carries the complete original request alongside the specialist's design or repair proposal. A short repair instruction cannot silently replace the original quality, originality or no-text constraints. Combined context is bounded; oversized proposals fail explicitly. The actual private media staging workspace receives `skills/native-media/SKILL.md`, with purpose-specific native generation and inspection instructions. The trusted launcher also inserts these reviewed instructions directly into each native model request, including an explicit main-session reference-viewing step before image-generator delegation. External controller actions are not the native tool protocol. Staged input pixels remain unchanged, directories remain private, and symlinks are rejected before copying instructions. Independent visual inspection distinguishes real defects from ordinary occlusion without weakening the original request.
