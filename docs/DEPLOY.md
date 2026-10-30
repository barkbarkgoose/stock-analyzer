# Deploying Stonks

The same setup runs on any always-on Ubuntu 24.04 machine. This guide covers
three places to put it, and two ways to make it reachable for the people you
share it with:

| | Host | People open | You need |
|---|---|---|---|
| **1** | DigitalOcean droplet | `https://stonks.allbarker.com` | DO account, DNS record |
| **2** | Google Cloud VM (Compute Engine) | `https://stonks.allbarker.com` | GCP project with billing, DNS record |
| **3a** | Home machine + Tailscale Funnel | `https://stonks.<tailnet>.ts.net` | Tailscale; no router changes |
| **3b** | Home machine + your dedicated IP | `https://stonks.allbarker.com` | Dedicated IP, router port-forwarding, DNS record |

Everyone you share with just opens the URL and signs in with the account you
create for them. **Nobody but you needs Tailscale.** Tailscale is only used for
your own admin access (SSH), and in 3a to publish the site.

```text
public HTTPS ─▶ Caddy (1, 2, 3b) or Tailscale Funnel (3a) ─▶ 127.0.0.1:8000
                  app container: gunicorn + Django + built Vue app
                    ├─ db container: Postgres 17, internal network, no port
                    └─ paper container: paper-trading loop
systemd timers: nightly DB dump to /var/backups/stonks · weekday 5m-history backfill
```

**Choosing:**

- **Least to look after:** DigitalOcean (1). Google Cloud (2) is equivalent, with
  a busier console and fiddlier pricing.
- **Free to run, no router changes:** home + Funnel (3a). The catch is the
  `ts.net` address instead of your domain, and your tailnet name appears in it.
- **Your own domain from home:** home + dedicated IP (3b). This exposes a machine
  on your home network to the internet, so isolate it (see 3b).
- **Market data:** Yahoo throttles cloud IPs more often than home connections,
  which favours 3a/3b. On 1 or 2, Alpaca keys are the fallback.
- **Uptime:** at home, a power or internet outage stops paper trading and
  history collection until it comes back. History backfill catches up only
  within Yahoo's ~60-day window.

Throughout: **Mac** = your workstation, **server** = the machine running Stonks,
**browser** = a web console.

---

## Part 1 — Get an Ubuntu 24.04 server

Do **one** of 1A, 1B or 1C. Each ends with you able to `ssh deploy@SERVER` and
run `sudo`.

### 1A. DigitalOcean droplet

1. **Browser:** Create Droplet → Ubuntu 24.04 LTS → Basic, **2 GB RAM** (1 GB works
   with the swap the setup script adds, but builds are slow). Add your SSH key.
   Turn on **weekly backups**. Billing → set a billing alert.
2. Optional: Networking → Firewalls → allow inbound TCP 22, 80, 443, and attach it.
   The server's own firewall (`ufw`) is configured by the setup script either way.
3. **Server, as root** — create your admin user:

   ```bash
   ssh root@DROPLET_IP
   adduser deploy
   usermod -aG sudo deploy
   install -d -m 0700 -o deploy -g deploy /home/deploy/.ssh
   install -m 0600 -o deploy -g deploy /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
   ```

   In a **second** Mac terminal confirm `ssh deploy@DROPLET_IP` and `sudo -v`
   work before closing the root session.

If you ever lock yourself out, Droplet → Access → **Recovery Console** works
without SSH.

### 1B. Google Cloud VM (Compute Engine)

Google's equivalent of a droplet. (Cloud Run, Google's serverless option, does
**not** fit: the paper-trading loop and the timers need a machine that stays on.)

1. **Browser:** create or pick a project with billing enabled, then Billing →
   Budgets & alerts → add a budget alert.
2. Compute Engine → VM instances → **Create instance**:
   - Region near you; machine type **e2-small** (2 GB). The free-tier `e2-micro`
     (1 GB) can work with swap but is slow.
   - Boot disk → Change → **Ubuntu 24.04 LTS** (x86/64), 20 GB balanced persistent disk.
   - Firewall: tick **Allow HTTP traffic** and **Allow HTTPS traffic**.
   - Security → Manage access → **Add manually generated SSH keys**: paste your
     public key with ` deploy` appended to the end, e.g.
     `ssh-ed25519 AAAAC3Nz... deploy`. Google creates a `deploy` user with sudo.
3. **Keep the IP:** VPC network → IP addresses → find the VM's external IP →
   **Reserve** (makes it static). Without this the IP can change on restart and
   DNS breaks.
4. **Disk backups:** Compute Engine → Snapshots → **Create snapshot schedule**
   (e.g. daily, keep 14 days) → attach it to the VM's boot disk. This replaces
   DigitalOcean's weekly backups.
5. **Mac:** `ssh deploy@EXTERNAL_IP` and check `sudo -v`.

Google's default network allows SSH from anywhere (`default-allow-ssh`); Part 4
narrows it. If you lock yourself out, the VM page's **Serial console** works
without SSH (enable it under the VM's settings first).

### 1C. Machine at home

**Hardware:** anything that can run Ubuntu Server 24.04 and stay on: a mini PC,
an old laptop, or a VM on a home server. 2 GB RAM minimum (4 GB nicer), 20 GB+
disk, **wired** ethernet. A small UPS is worth it. x86-64 is what has been
tested; ARM64 (e.g. a Raspberry Pi 5) should work since every image and
package is multi-arch, but it is untested.

1. Install **Ubuntu Server 24.04 LTS**. In the installer: create the user
   `deploy`, tick **Install OpenSSH server**, and import your SSH key (from
   GitHub, or paste it).
2. In the BIOS/UEFI, set **power on after power loss** so it comes back by itself.
3. On your router, give it a **DHCP reservation** so its LAN IP never changes.
4. Install Tailscale on it (Part 4 uses it for SSH; 3a also uses it to publish):

   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up                       # opens a login link; approve it
   sudo tailscale set --hostname stonks    # machine becomes "stonks" in your tailnet
   ```

5. **Mac:** `ssh deploy@stonks` (via Tailscale MagicDNS) and check `sudo -v`.

There are no provider snapshots at home, so the off-server backup copy in
[Backups](#backups) is not optional here.

---

## Part 2 — Install Stonks (all hosts)

### 2.1 Clone the repo (server, as deploy)

The repo is private, so give the server a read-only deploy key:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/stonks-github -C stonks-server
cat ~/.ssh/stonks-github.pub
```

**Browser:** GitHub → `barkbarkgoose/stock-analyzer` → Settings → Deploy keys →
Add, paste the key, leave **write access off**. Then:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  User git
  IdentityFile ~/.ssh/stonks-github
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh -T git@github.com          # answer "yes"; a "no shell access" message is success
sudo install -d -o deploy -g deploy -m 0755 /opt/stonks
git clone git@github.com:barkbarkgoose/stock-analyzer.git /opt/stonks
cd /opt/stonks
git checkout codex/v3          # or main, once merged
```

If you put a passphrase on the deploy key, `ops.sh deploy` will ask for it each
time it pulls.

### 2.2 Run the setup script (server)

Pick the line for your host:

```bash
cd /opt/stonks

# 1A DigitalOcean, 1B Google Cloud, 3b home with dedicated IP:
sudo scripts/server-setup.sh --domain stonks.allbarker.com

# 3a home with Tailscale Funnel (use your tailnet's name; see 3a below):
sudo scripts/server-setup.sh --proxy none --domain stonks.YOUR-TAILNET.ts.net --ssh-from 100.64.0.0/10
```

It installs Docker, unattended security updates, a 2 GB swapfile and the `ufw`
firewall. With the default `--proxy caddy` it also installs Caddy and opens
80/443; `--proxy none` leaves both closed. It installs the backup and backfill
timers and writes `/etc/stonks/app.env` with **freshly generated secrets**. It
is safe to re-run, and never overwrites an existing `app.env`.

**Save the secrets now:** `sudo cat /etc/stonks/app.env`, then copy
`SECRET_KEY`, `SETTINGS_ENCRYPTION_KEY` and `POSTGRES_PASSWORD` into your
password manager. If you have Alpaca keys, add them now with
`sudoedit /etc/stonks/app.env`.

### 2.3 Deploy and create your login (server)

```bash
sudo scripts/ops.sh deploy
sudo scripts/ops.sh add-user you@example.com --name "Your Name" --admin
```

`--admin` also gives you the Django admin at `/admin/`. The app is now running
on `127.0.0.1:8000`; Part 3 makes it reachable.

---

## Part 3 — Make it reachable

### 3-Caddy. Your domain via Caddy (1A, 1B, 3b)

1. **DNS (browser):** at the DNS provider for `allbarker.com`, add an **A** record
   `stonks →` the server's public IP: the droplet IP, the reserved Google IP, or
   your home dedicated IP. No CDN/proxy in front.
2. **Mac:** `dig +short A stonks.allbarker.com` until it shows that IP.
3. Caddy requests the certificate automatically once DNS resolves (usually under
   a minute). Open `https://stonks.allbarker.com` and sign in.

**Extra for 3b (home with a dedicated IP):**

- **Router:** forward **TCP 80 and TCP 443** to the server's reserved LAN IP.
  Port 80 is needed for certificate issuance and the HTTP→HTTPS redirect. Never
  forward 22.
- **Isolate it:** if your router supports it, put the server on a separate
  VLAN or guest/DMZ network so a compromise cannot reach your other devices.
- **Check your ISP:** some residential plans block inbound 80/443 or forbid
  servers; a dedicated-IP plan usually allows both.
- **Inside your house** the domain may not load if your router lacks "NAT
  loopback" (hairpin NAT). Test from mobile data; if it fails only at home, turn
  on NAT loopback in the router, or use the site from a phone off Wi-Fi.

### 3a. Home via Tailscale Funnel

Funnel publishes the app at `https://stonks.YOUR-TAILNET.ts.net` to the whole
internet through Tailscale's servers. Visitors do **not** need Tailscale, and
nothing on your router changes. It cannot use `stonks.allbarker.com`.

1. **Browser:** Tailscale admin console → **DNS**: turn on **MagicDNS** and
   **HTTPS Certificates**. While there, note your tailnet name
   (`something.ts.net`). You can switch it to a randomly generated "fun name" if
   you would rather not expose the default one.
2. The setup script must have been run with `--domain stonks.YOUR-TAILNET.ts.net`
   (2.2). If you used another domain, fix `ALLOWED_HOSTS` with
   `sudoedit /etc/stonks/app.env`, then `sudo scripts/ops.sh deploy --no-pull`.
3. **Server:**

   ```bash
   sudo tailscale funnel --bg 8000
   ```

   The first time, it prints a link to allow Funnel for this machine in your
   tailnet policy; open it and approve, then run the command again.
   `tailscale funnel status` shows the public URL. `--bg` keeps it running
   across reboots.
4. Open the URL from a phone on mobile data (not on Tailscale) and sign in.

To take it offline: `sudo tailscale serve reset` (Stonks keeps running privately).

**Moving from 3a to 3b later:** forward ports and add DNS as in 3-Caddy, set
`ALLOWED_HOSTS=stonks.allbarker.com` in `app.env`, run
`sudo scripts/server-setup.sh --proxy caddy --domain stonks.allbarker.com`, then
`sudo scripts/ops.sh deploy --no-pull` and `sudo tailscale serve reset`.

---

## Part 4 — Lock down admin access

### 4.1 Key-only SSH (all hosts)

When key login as `deploy` works from a fresh terminal:

```bash
sudo scripts/server-setup.sh --harden-ssh
```

This turns off password and root SSH logins. Keep the current session open and
confirm a new login works before closing it.

### 4.2 SSH only over Tailscale (recommended, all hosts)

With Tailscale on the server (1C did this; on 1A/1B run the three commands from
1C step 4), you can close SSH to the internet entirely:

```bash
cd /opt/stonks
sudo scripts/server-setup.sh --domain YOUR-DOMAIN --ssh-from 100.64.0.0/10   # add --proxy none for 3a
```

`100.64.0.0/10` is the Tailscale address range. Re-running with `--ssh-from`
replaces the open SSH rule. From then on, use `ssh deploy@stonks` (your Mac must
be on Tailscale). On 1A/1B you can also remove port 22 from the provider's
firewall. If Tailscale ever breaks, use the provider console (1A/1B) or a
keyboard and monitor (1C).

### 4.3 Optional

- **Uptime monitor:** a free check (UptimeRobot, Better Stack, healthchecks.io) on
  `https://YOUR-URL/health/`, which returns `{"status": "ok"}`.
- **HSTS:** after HTTPS has been fine for a week, set `SECURE_HSTS_SECONDS=31536000`
  in `app.env`, then `sudo scripts/ops.sh deploy --no-pull`.

---

## Sharing with people

There is no sign-up page. For each person:

```bash
sudo scripts/ops.sh add-user friend@example.com --name "Friend"
```

Choose a password at the prompt and send it, together with the URL, privately
(e.g. a password-manager share). There is no in-app "change password" yet; to
change or reset one, run `sudo scripts/ops.sh manage changepassword EMAIL`.

Everyone shares the **same watchlist and paper-trading account**: the app is
built as a single shared workbench, not per-user portfolios. Analyses are
cached on the server and shared; study settings and per-stock targets are saved
in each person's own browser.

To cut someone off, disable their account (see the table below). A login lasts
up to 7 days, so for an immediate cut-off also change `SECRET_KEY` in `app.env`
and redeploy. That signs **everyone** out.

---

## Everyday operations

All from `/opt/stonks` on the server:

| Task | Command |
|---|---|
| Ship the latest code | `sudo scripts/ops.sh deploy` |
| Is it up? | `sudo scripts/ops.sh status` |
| Add a user | `sudo scripts/ops.sh add-user EMAIL --name "Name" [--admin]` |
| Reset a password | `sudo scripts/ops.sh manage changepassword EMAIL` |
| Disable a user | `sudo scripts/ops.sh manage shell -c "from apps.users.models import User; User.objects.filter(email='EMAIL').update(is_active=False)"` |
| Logs | `sudo scripts/ops.sh logs` (or `logs paper`, `logs db`) |
| Backup now | `sudo scripts/ops.sh backup` |
| Restore a backup | `sudo scripts/ops.sh restore /var/backups/stonks/FILE.dump` |
| Undo a bad release | `sudo scripts/ops.sh rollback` (code only; see below) |
| Collect history now | `sudo scripts/ops.sh backfill` |
| Timers | `systemctl list-timers 'stonks-*'` |

**What `deploy` does:** pulls (fast-forward only), builds a new image tagged with
the commit, dumps the database, runs migrations with the new image, restarts
`app` and `paper`, then waits for `/health/`. If the health check fails it shows
the app logs and stops; the old image is still on disk for `rollback`.

**Rollback** swaps back to the previous image. It does not undo database
migrations, so only use it when the bad release had no migration. Otherwise
restore the pre-deploy dump (`stonks-*-predeploy-*.dump`), which deploy takes
automatically.

**Changing `app.env`:** edit with `sudoedit /etc/stonks/app.env`, then
`sudo scripts/ops.sh deploy --no-pull` to recreate containers. Never change
`POSTGRES_PASSWORD` after the first start: the database keeps the old one.

## Backups

- Nightly at 08:15 UTC and before every deploy: `pg_dump` custom-format to
  `/var/backups/stonks`, verified with `pg_restore --list`, newest 14 kept.
  `latest.dump` always points at the newest.
- Whole-disk backups: DigitalOcean weekly backups (1A) or the Google snapshot
  schedule (1B). **None at home (1C)**, so the copy below matters most there.
- A copy off the server, from the **Mac** (use `deploy@stonks` over Tailscale,
  or the public hostname if SSH is still open):

  ```bash
  scp deploy@stonks:/var/backups/stonks/latest.dump ~/Backups/stonks-$(date +%Y%m%d).dump
  ```

  The `deploy` user can read the dumps (they are group-owned by it).

**Rebuilding from scratch** (server lost, or moving hosts): do Part 1 and 2.1–2.2
on the new machine. Copy your saved secrets back into `/etc/stonks/app.env`: at
least `SECRET_KEY` and `SETTINGS_ENCRYPTION_KEY`; `POSTGRES_PASSWORD` can be new
on a fresh database. Then `sudo scripts/ops.sh deploy`, `scp` a dump to the
server, `sudo scripts/ops.sh restore /path/to/file.dump`, and redo Part 3 for
the new address. Moving between any of the three hosts is exactly this.

## Troubleshooting

| Symptom | Look at |
|---|---|
| Certificate error / can't connect (Caddy) | `dig +short A stonks.allbarker.com`, `sudo journalctl -u caddy -n 50`; at home, check the port forwards and test from mobile data |
| Can't connect (Funnel) | `tailscale funnel status`, `tailscale status`; Funnel and HTTPS Certificates must be enabled in the admin console |
| 502 / bad gateway | `sudo scripts/ops.sh status`, `sudo scripts/ops.sh logs` |
| "Bad Request (400)" | The hostname you used is not in `ALLOWED_HOSTS` in `app.env` |
| Analyses fail to fetch data | `sudo scripts/ops.sh logs`; Yahoo sometimes throttles cloud IPs. Add Alpaca keys to `app.env` and redeploy |
| Disk filling up | `df -h`, `sudo docker system df` |
| Kicked to login | A login lasts 7 days (renewed silently within that); sign in again |

Never use `docker compose down -v` or `docker volume rm`: the database lives in
the `stonks_pgdata` volume.
