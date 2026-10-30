# Deploying Stonks to DigitalOcean

One Ubuntu 24.04 droplet runs everything:

```text
browser → HTTPS → Caddy (host, auto TLS) → 127.0.0.1:8000 → app container (gunicorn + Django + Vue build)
                                                              ├─ db container (Postgres 17, internal network, no port)
                                                              └─ paper container (paper-trading loop)
systemd timers → nightly DB dump to /var/backups/stonks · weekday 5m-history backfill
```

Deliberately small: no object storage (no uploads), no staging server, no
image registry. Market bars and analyses can be re-fetched; the data worth
protecting is the accumulated 5-minute history (Yahoo only serves ~60 days), the
watchlist and paper trades, all of which live in Postgres and are dumped
nightly.

**Mac** = your workstation, **server** = the droplet, **browser** = a web UI.

## 1. Create the droplet (browser)

1. DigitalOcean → Create Droplet: Ubuntu 24.04 LTS, Basic, **2 GB RAM** (1 GB works
   with the swap the setup script adds, but builds are slow). Add your SSH key.
   Enable **weekly backups**.
2. Billing → set a billing alert.
3. Optional: Networking → Firewalls → allow inbound 22, 80, 443 only and attach it
   to the droplet. The setup script also configures `ufw` on the host.

## 2. Admin user (server, as root)

```bash
ssh root@DROPLET_IP
adduser deploy
usermod -aG sudo deploy
install -d -m 0700 -o deploy -g deploy /home/deploy/.ssh
install -m 0600 -o deploy -g deploy /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
```

In a **second** Mac terminal confirm `ssh deploy@DROPLET_IP` and `sudo -v` work
before closing the root session.

## 3. Clone the repo (server, as deploy)

The repo is private, so give the server a read-only deploy key:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/stonks-github -C stonks-droplet
cat ~/.ssh/stonks-github.pub
```

Browser: GitHub → `barkbarkgoose/stock-analyzer` → Settings → Deploy keys → Add,
paste the key, leave **write access off**. Then:

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

If you put a passphrase on the deploy key, `ops.sh deploy` will prompt for it
each time it pulls.

## 4. Point DNS (browser)

At your DNS provider for `allbarker.com`, add an **A** record
`stonks → DROPLET_IP` (no proxy/CDN). Check from the Mac:
`dig +short A stonks.allbarker.com`. Caddy can only get a certificate once this
resolves, so do it before or right after step 5.

## 5. Set up the server (server)

```bash
cd /opt/stonks
sudo scripts/server-setup.sh
# restrict SSH to your home IP instead of anywhere:
#   sudo scripts/server-setup.sh --ssh-from 203.0.113.7/32
```

It installs Docker, Caddy, unattended security updates, a 2 GB swapfile, the
firewall (22/80/443 only), the Caddy site, the backup and backfill timers, and
writes `/etc/stonks/app.env` with **freshly generated secrets**. It is safe to
re-run and never overwrites an existing `app.env`.

**Save the secrets now:** `sudo cat /etc/stonks/app.env` and copy `SECRET_KEY`,
`SETTINGS_ENCRYPTION_KEY` and `POSTGRES_PASSWORD` into your password manager. If
you have Alpaca keys, add them to that file (`sudoedit /etc/stonks/app.env`).

## 6. Deploy and create your login (server)

```bash
sudo scripts/ops.sh deploy
sudo scripts/ops.sh add-user you@example.com --name "Your Name"
# add --admin to also get the Django admin at /admin/
```

Open `https://stonks.allbarker.com` and sign in.

## 7. Lock down SSH (server)

Once key login as `deploy` works from a fresh terminal:

```bash
sudo scripts/server-setup.sh --harden-ssh
```

This turns off password and root SSH logins. Keep the current session open and
confirm a new login works before closing it.

## 8. Optional

- **Uptime monitor:** a free check (UptimeRobot, Better Stack, healthchecks.io) on
  `https://stonks.allbarker.com/health/`, which returns `{"status": "ok"}`.
- **HSTS:** after HTTPS has been fine for a week, set `SECURE_HSTS_SECONDS=31536000`
  in `app.env` and `sudo scripts/ops.sh deploy --no-pull`.

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
- DigitalOcean weekly droplet backups cover the whole disk.
- A copy off the server, from the **Mac**:

  ```bash
  scp deploy@stonks.allbarker.com:/var/backups/stonks/latest.dump \
    ~/Backups/stonks-$(date +%Y%m%d).dump
  ```

  The `deploy` user can read the dumps (they are group-owned by it).

**Rebuilding from scratch** (droplet lost): do steps 1–5 on a new droplet, copy
your saved secrets back into `/etc/stonks/app.env` (at least `SECRET_KEY` and
`SETTINGS_ENCRYPTION_KEY`; `POSTGRES_PASSWORD` can be new on a fresh database),
`sudo scripts/ops.sh deploy`, `scp` a dump to the server, then
`sudo scripts/ops.sh restore /path/to/file.dump`. Point DNS at the new IP.

## Troubleshooting

| Symptom | Look at |
|---|---|
| Browser can't connect / certificate error | `dig +short A stonks.allbarker.com`, `sudo journalctl -u caddy -n 50` |
| 502 from Caddy | `sudo scripts/ops.sh status`, `sudo scripts/ops.sh logs` |
| Analyses fail to fetch data | `sudo scripts/ops.sh logs`; Yahoo sometimes throttles cloud IPs. Add Alpaca keys to `app.env` and redeploy |
| Disk filling up | `df -h`, `sudo docker system df` |
| Kicked to login | A login lasts 7 days (renewed silently within that); sign in again |

Never use `docker compose down -v` or `docker volume rm`: the database lives in
the `stonks_pgdata` volume.
