# Deploy CW Agent on your own Linux server

Use a Linux host with systemd and working user/network namespaces. The default layout is `/opt/coding-workshop` for the controller, `/opt/coding-runtime` for browser tooling and `/opt/coding-artifacts` for the trusted presentation runtime. Commands below assume this layout and operator privileges.

## 1. Install prerequisites

Install Python 3 with venv and Pillow, PHP CLI with PDO SQLite, Node 20 or newer with npm, bubblewrap, iproute2, systemd and Caddy. Install LibreOffice Impress, Poppler and Liberation fonts for slide rendering. Choose versions and package names appropriate to your distribution.

Install AntiGravity CLI using its [official CLI documentation](https://antigravity.google/docs/cli/headless/). Authenticate the role profiles listed in `state.py` using accounts you are entitled to use. The repository contains no OAuth credentials. `setup.py` verifies that each configured profile already exists and is authenticated.

## 2. Install runtime dependencies

```bash
sudo git clone https://github.com/vikrant-project/cw-agent.git /opt/coding-workshop
cd /opt/coding-workshop/whatsapp
npm ci --ignore-scripts

sudo mkdir -p /opt/coding-artifacts
sudo cp /opt/coding-workshop/artifact-runtime/{package.json,package-lock.json,render_presentation.cjs,check_presentation.cjs} /opt/coding-artifacts/
cd /opt/coding-artifacts
sudo npm ci --ignore-scripts

sudo mkdir -p /opt/coding-runtime
sudo python3 -m venv /opt/coding-runtime/venv
sudo /opt/coding-runtime/venv/bin/pip install -r /opt/coding-workshop/requirements-browser.txt
sudo env PLAYWRIGHT_BROWSERS_PATH=/opt/coding-runtime/browsers /opt/coding-runtime/venv/bin/playwright install chromium
sudo cp /opt/coding-workshop/browser_runner.py /opt/coding-runtime/browser_runner.py
```

Browser OS dependencies must also be installed for your distribution. The trusted runtimes and browser binaries must be readable/executable by the unprivileged runner. Keep trusted renderer code and dependencies outside writable generated projects.

## 3. Replace placeholders and initialize

`deployment.example.json` is documentation only. It is not automatically loaded, and no SSH password is needed by the application itself. Use your own host administration method.

Replace **YOUR_PUBLIC_HOST** in `Caddyfile` and the certificate-renewal service template with your real hostname or supported certificate identity. Provision the certificate at the referenced paths before starting TLS. The supplied renewal command uses `certbot`; configure and verify an appropriate ACME challenge method, then install or replace its renewal service. An ordinary hostname certificate may be simpler than IP-certificate provisioning.

Keep `config.json` budgets and `scope.json` provider origins under operator control. The provider allowlist contains public vendor endpoints, not the owner's VPS identity. Review origin availability when the vendor changes its transport.

```bash
cd /opt/coding-workshop
sudo python3 setup.py
```

Setup creates service users, a private database, invitation code and private bridge/encryption keys. It does not start services. Obtain the invitation from `portal-data/invite.key` and share it privately with intended users.

## 4. Enable services

```bash
sudo cp /opt/coding-workshop/systemd/coding-*.service /etc/systemd/system/
sudo cp /opt/coding-workshop/systemd/coding-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now coding-gateway coding-internal coding-portal coding-worker coding-queue-lane coding-watchdog coding-whatsapp coding-tls
```

Enable the certificate renewal timer only after its command and challenge method work for your host. The PHP service listens on loopback port 9872; the internal API uses loopback port 9871. The TLS portal uses port 9870. Public exposure should be limited to the intended HTTPS listener and any required certificate challenge route. Larger deployments should use a configured PHP-FPM service instead of the supplied PHP development server.

## 5. Verify your deployment

- Open the HTTPS portal and verify the certificate identity.
- Create an invitation-authorized account, log out and log in.
- Connect your own WhatsApp session, then try ordinary conversation in Message yourself.
- Submit a small task; inspect actual tool evidence, final review and native downloads.
- Check cancellation, tenant separation and recovery using accounts/data you control.
- Confirm private directories and database files cannot be fetched through HTTP.

The internal unit suite is deliberately excluded from this public source snapshot. A running service or successful login alone does not establish that your provider quota, browser, image or presentation toolchain works.

[Troubleshooting](TROUBLESHOOTING.md) · [Security](../SECURITY.md)
