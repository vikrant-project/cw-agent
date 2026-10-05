# Security and privacy

CW Agent handles model credentials, user projects and WhatsApp sessions. Deploy it only on infrastructure you administer. Reviewed controller instructions and transport settings belong to the operator; task-created playbooks cannot grant additional permissions.

## Private data

Keep `private/`, `portal-data/`, `bridge-private/`, `projects/`, `downloads/`, `media-staging/`, certificates, OAuth profiles and session backups outside public source control. `.gitignore` covers common runtime paths, but the repository's exclusion list is not a substitute for reviewing every commit.

The public snapshot contains placeholders for host/administration details. Setup generates private keys; it does not require a published VPS password. Never commit real invitation codes or replace placeholder examples with live credentials in a public branch.

## Boundaries

The portal uses account ownership checks, password hashes, CSRF handling and session controls. Model sessions have temporary homes and a provider-only proxy. Generated commands run in unprivileged isolated namespaces with limited mounts and budgets. Review and file hashes guard delivery against stale evidence. These controls require correct host permissions and configuration.

## Reporting

Use a private GitHub security advisory if private vulnerability reporting is enabled. Otherwise contact the maintainer through a private channel before disclosing a sensitive reproduction. Public issues may describe a non-sensitive symptom, but must omit credentials, customer data and exploitable deployment details.

No comprehensive external security audit is claimed. Important generated software and documents need appropriate human review before production use.
