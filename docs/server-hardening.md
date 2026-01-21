# Server hardening checklist (Debian / Ubuntu)

This is a **manual checklist**, not an automated script.

Do not blindly copy/paste commands unless you understand them.
Locking yourself out of a remote server is easy.

---

## 1. Create a non-root user

If you are logged in as `root`:

```bash
adduser james
usermod -aG sudo james
```

Log out and back in as the new user before continuing.

---

## 2. Set up SSH key authentication

On your local machine:

```bash
ssh-copy-id james@your-server
```

Verify you can log in **without a password** before proceeding.

---

## 3. Harden SSH configuration

Edit:

```bash
sudo nano /etc/ssh/sshd_config
```

Recommended minimum settings:

```text
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding no
```

Then reload SSH:

```bash
sudo systemctl reload ssh
```

⚠️ **Do not close your SSH session until you have verified you can reconnect.**

---

## 4. Enable a firewall

Using `ufw` (recommended for most VPS hosts):

```bash
sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw enable
```

Check status:

```bash
sudo ufw status
```

---

## 5. Enable automatic security updates

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure unattended-upgrades
```

Verify:

```bash
cat /etc/apt/apt.conf.d/20auto-upgrades
```

---

## X. Verify time synchronisation

Check time status:

```bash
timedatectl status
```

You should see:

- `System clock synchronized: yes`
- `NTP service: active`

If not enabled:

```bash
sudo timedatectl set-ntp true
```

Ensure the service is running:

```bash
systemctl status systemd-timesyncd
```

Accurate time is critical for SSH, TLS, package management, and log integrity.

### Timezone

- Set the system timezone explicitly (e.g. `Europe/London`)
- Verify with `timedatectl`
- Avoid relying on provider defaults

Set the timezone specifically for your region:

```bash
sudo timedatectl set-timezone Europe/London
```

---

## 7. (Optional) Fail2ban

Useful on public-facing servers:

```bash
sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
```

---

## 8. Verify sudo access

```bash
sudo -v
```

You should be prompted for **your user password**, not root.

---

## 9. Final checks

From a new terminal:

```bash
ssh your-user@your-server
```

Confirm:

- password login is disabled
- root login is blocked
- firewall is active

---

## 10. After hardening

Once the above is complete, you can safely:

```bash
git clone https://github.com/jfi/dotfiles ~/.dotfiles
~/.dotfiles/install
```

---

## Philosophy

This repository assumes:

- security first
- explicit steps over magic
- no automation that can lock you out of a server

If you need fully automated provisioning, use Ansible or cloud-init instead.
