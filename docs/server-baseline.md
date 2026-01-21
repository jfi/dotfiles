# Server baseline

## What this repo deliberately does not do

This repository focuses on user-level developer ergonomics (shell, tmux, git). It intentionally does **not**:

- perform server hardening automatically (easy to lock yourself out)
- install or configure Docker / containers
- manage system services (databases, web servers, queues, cron)
- manage users, groups, or SSH keys beyond your own login
- modify kernel/sysctl settings
- configure backups or disaster recovery
- configure monitoring/alerting
- manage cloud networking (VPCs, security groups, load balancers)
- manage secrets at rest (use 1Password / provider secrets / vault tooling)

If you want full machine provisioning, use Ansible or cloud-init and keep this repo as the final “developer shell layer”.

---

## VPS baseline (provider-agnostic)

These steps work across Hostinger, Hetzner, DigitalOcean, AWS Lightsail, etc.

### Provisioning

- Debian 12 (bookworm) or Ubuntu LTS
- Add your **SSH public key** at provision time if the provider supports it
- Create a non-root user (or ensure one exists) with `sudo`
- Ensure the server has a hostname that matches your mental model (e.g. `hub`)

### Networking

- Allow inbound:
  - `22/tcp` (SSH) — restrict by IP if practical
  - Any app ports you truly need (avoid “open by default”)
- Disable everything else at the edge if your provider supports it
- Enable a host firewall as well (`ufw`)

### Security baseline

- Disable SSH password login
- Disable root login
- Enable unattended upgrades
- Optional: fail2ban (if SSH is public)

### Reliability baseline

- Ensure time sync is working (`systemd-timesyncd`)
- Basic log rotation is enabled (default on Debian/Ubuntu)
- Optional: reboot strategy for kernel upgrades (manual vs unattended)

Accurate system time is essential for:

- TLS certificates
- SSH authentication
- package management
- log correlation
- distributed systems

On modern Debian/Ubuntu this is typically handled by `systemd-timesyncd`, but it should still be verified.

### After baseline

- Install your toolchain (zsh, tmux, git, etc.)
- Clone dotfiles
- Run `setup`
- Use tmux sessions per project

See `docs/server-hardening.md` for a safe checklist.

---

## cloud-init example (safe, commented)

This example is intentionally conservative:

- creates a non-root user with sudo
- installs baseline packages
- enables unattended upgrades
- hardens SSH (no passwords, no root login)
- enables UFW with SSH allowed
- does **not** install Docker or expose app ports

Save as `docs/cloud-init.example.yml` and adapt as needed.

```yaml
#cloud-config

# --- Users ---------------------------------------------------
users:
  - name: james
    groups: [sudo]
    shell: /bin/bash
    sudo: ["ALL=(ALL) NOPASSWD:ALL"]
    ssh_authorized_keys:
      # Replace with your SSH public key (safe to include)
      - ssh-ed25519 AAAA... your-key-comment

# --- Packages ------------------------------------------------
package_update: true
package_upgrade: true

packages:
  - ca-certificates
  - curl
  - git
  - gnupg
  - ufw
  - unattended-upgrades
  - zsh
  - tmux
  - fzf
  - python3
  - jq

# --- SSH hardening ------------------------------------------
write_files:
  - path: /etc/ssh/sshd_config.d/99-hardening.conf
    permissions: "0644"
    content: |
      PermitRootLogin no
      PasswordAuthentication no
      PubkeyAuthentication yes
      ChallengeResponseAuthentication no
      X11Forwarding no

# --- Unattended upgrades ------------------------------------
write_files:
  - path: /etc/apt/apt.conf.d/20auto-upgrades
    permissions: "0644"
    content: |
      APT::Periodic::Update-Package-Lists "1";
      APT::Periodic::Unattended-Upgrade "1";

# --- Firewall ------------------------------------------------
runcmd:
  # Ensure SSH remains possible
  - ufw allow OpenSSH
  - ufw --force enable

  # Reload sshd after writing config
  - systemctl reload ssh || systemctl reload sshd

  # Optional: set zsh as default shell for the user (commented)
  # - chsh -s /usr/bin/zsh james

final_message: |
  cloud-init complete.
  Next steps:
    - SSH in as 'james'
    - Clone dotfiles and run ~/.dotfiles/setup
```

### Notes

- Some providers merge/override `sshd_config` differently. Using `sshd_config.d/*.conf` is generally the safest modern approach.
- Never apply SSH hardening without confirming your key-based login works.
- Don’t expose app ports in cloud-init unless you’re certain.

---

# Health check script (read-only)

This script:

- **reports only**
- never mutates state
- exits non-zero if something is clearly wrong
- is safe to run repeatedly
- is SSH/VPS friendly

Run `bin/check-server-baseline`
