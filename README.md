# Root Password Rotation

An Ansible role for automated root password rotation on Linux servers with HashiCorp Vault integration for secure credential storage.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Variables](#variables)
- [Test Environment](#test-environment)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

## Overview

The role implements the following workflow:

1. Reads the current password hash from HashiCorp Vault
2. Compares it with the system hash on the target host
3. If mismatched (or no Vault entry exists), generates a new cryptographically secure password
4. Sets the new password on the target host via `chpasswd`
5. Stores the plaintext password and hash in Vault

This enables:

- Automated compliance with password rotation requirements
- Centralized credential storage in Vault
- Audit trail for all changes (via Vault audit log)
- Elimination of passwords in Ansible inventory or playbooks

## Architecture

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Ansible        │      │   HashiCorp     │      │  Target Host    │
│  Controller     │◄────►│     Vault       │      │  (Linux)        │
│                 │      │                 │      │                 │
│  - Playbook     │      │  secret/data/   │      │  - root user    │
│  - passwd_role  │      │  hosts/{host}   │      │  - /etc/shadow  │
└────────┬────────┘      └─────────────────┘      └────────▲────────┘
         │                                                  │
         │              SSH (privilege escalation)          │
         └──────────────────────────────────────────────────┘
```

### Project Structure

```
root_password_rotation/
├── passwd_role/                 # Main Ansible role
│   ├── defaults/
│   │   └── main.yaml           # Default variable values
│   ├── library/
│   │   └── change_user_password.py  # Custom Ansible module
│   └── tasks/
│       ├── main.yaml           # Entry point
│       └── pass_policy.yaml    # Rotation logic
├── test-role/                   # Test playbook
│   ├── main.yaml
│   └── roles/pass/             # Role copy for testing
├── Vagrantfile                  # Test environment
└── README.md
```

## Requirements

### Ansible Controller

- Python 3.8+
- Ansible 2.10+
- `community.hashi_vault` collection
- Python `hvac` library

```bash
pip install ansible hvac
ansible-galaxy collection install community.hashi_vault
```

### Target Hosts

- Linux (tested on Ubuntu 24.04)
- Python 3 (for Ansible modules)
- Sudo access for root password changes

### HashiCorp Vault

- Vault server with KV v2 secrets engine enabled
- Token with read/write permissions on path `secret/data/hosts/*`

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/ruleito/root_password_rotation.git
cd root_password_rotation
```

### 2. Copy the Role

```bash
# Option 1: Copy to standard roles directory
cp -r passwd_role ~/.ansible/roles/passwd_role

# Option 2: Specify path in ansible.cfg
echo "roles_path = ./passwd_role:~/.ansible/roles" >> ansible.cfg
```

### 3. Install Dependencies

```bash
ansible-galaxy collection install community.hashi_vault
pip install hvac
```

## Configuration

### Environment Variables

The role expects the following environment variables:

```bash
export VAULT_ADDR='https://vault.example.com:8200'
export VAULT_TOKEN='s.xxxxxxxxxxxxxxxxx'
```

### ansible.cfg

```ini
[defaults]
inventory = ./inventory/hosts.yml
host_key_checking = False
roles_path = ./roles
library = ./library
interpreter_python = auto_silent

[privilege_escalation]
become = True
become_method = sudo
become_user = root
```

### Inventory

```yaml
# inventory/hosts.yml
all:
  hosts:
    server-01:
      ansible_host: 192.168.1.10
      ansible_user: ansible
      ansible_ssh_private_key_file: ~/.ssh/id_rsa
    server-02:
      ansible_host: 192.168.1.11
      ansible_user: ansible
```

## Usage

### Basic Playbook

```yaml
---
- name: Rotate root passwords
  hosts: all
  gather_facts: yes
  
  tasks:
    - name: Include password rotation role
      include_role:
        name: passwd_role
      tags: def_pass_policy
```

### Execution

```bash
# All hosts
ansible-playbook rotate_passwords.yml

# Specific host
ansible-playbook rotate_passwords.yml --limit server-01

# Check mode (dry-run)
ansible-playbook rotate_passwords.yml --check

# Verbose output
ansible-playbook rotate_passwords.yml -vvv
```

### Using Tags

```bash
# Password rotation only
ansible-playbook rotate_passwords.yml --tags def_pass_policy
```

## Variables

### defaults/main.yaml

| Variable | Default | Description |
|----------|---------|-------------|
| `vault_path` | `secret/data/hosts` | Vault KV path for credential storage |
| `user` | `root` | User whose password will be rotated |
| `pass_enc_type` | `hex` | Password generation type (`hex`) |
| `pass_length` | `16` | Password length (for hex = 32 characters result) |

### Overriding Variables

```yaml
# In playbook
- name: Rotate passwords
  hosts: all
  vars:
    user: admin
    pass_length: 24
    vault_path: "secret/data/credentials"
  tasks:
    - include_role:
        name: passwd_role
```

```yaml
# In inventory (per-host)
all:
  hosts:
    server-01:
      pass_length: 32
```

## Custom Module: change_user_password

The role includes a custom Ansible module at `/library/change_user_password.py`.

### Module Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `username` | yes | - | Username |
| `vault_hash` | no | `''` | Password hash from Vault for comparison |
| `pass_enc_type` | no | `hex` | Password generation method |
| `password_length` | no | `16` | Password length |

### Return Values

| Field | Description |
|-------|-------------|
| `changed` | `true` if password was changed |
| `hash` | SHA512 hash of the new password |
| `plaintext` | Plaintext password (empty if unchanged) |

### Algorithm

```python
1. Get current hash from /etc/shadow (spwd.getspnam)
2. Compare with vault_hash
3. If different or vault_hash is empty:
   - Generate new password: os.urandom(length).hex()
   - Create hash: crypt.crypt(password, crypt.mksalt(METHOD_SHA512))
   - Set via chpasswd
4. Return result
```

## Test Environment

The repository includes a `Vagrantfile` for local testing.

### Components

- **controller** (192.168.56.10): Ansible controller + Vault in Docker
- **host01** (192.168.56.11): Target host for testing

### Setup

```bash
# Start environment
vagrant up

# Connect to controller
vagrant ssh controller

# On controller:
cd ~/ansible
source ~/.bashrc  # loads VAULT_ADDR and VAULT_TOKEN

# Test Vault connection
ansible-playbook test_vault.yml

# Run password rotation
ansible-playbook main.yaml
```

### Verify Results

```bash
# On controller - check Vault
curl -s -H "X-Vault-Token: root" \
  http://192.168.56.10:8200/v1/secret/data/hosts/test-host-01 | jq

# On host01 - check shadow
vagrant ssh host01
sudo grep root /etc/shadow
```

### Vault UI

Available at: `http://localhost:8200` (token: `root`)

## Security

### Production Recommendations

1. **Vault Token Management**
   - Use AppRole or another auth method instead of static tokens
   - Configure TTL and renewal policies
   
   ```bash
   vault auth enable approle
   vault write auth/approle/role/ansible \
     token_policies="ansible-policy" \
     token_ttl=1h \
     token_max_ttl=4h
   ```

2. **Vault Policy**
   ```hcl
   # ansible-policy.hcl
   path "secret/data/hosts/*" {
     capabilities = ["create", "read", "update"]
   }
   
   path "secret/metadata/hosts/*" {
     capabilities = ["list", "read"]
   }
   ```

3. **Audit Logging**
   ```bash
   vault audit enable file file_path=/var/log/vault/audit.log
   ```

4. **Network Security**
   - Use TLS for Vault
   - Restrict Vault access by IP
   - Use bastion host for Ansible

5. **Ansible Vault** for local secrets
   ```bash
   ansible-vault encrypt_string 'vault_token' --name 'vault_token'
   ```

### no_log

The role uses `no_log: true` for all tasks handling credentials:

```yaml
- name: Read password from Vault
  community.hashi_vault.vault_read:
    ...
  no_log: true  # Don't log plaintext

- name: Rotate password
  change_user_password:
    ...
  no_log: true  # Don't log password
```

## Troubleshooting

### Vault Connection Issues

```bash
# Check Vault availability
curl -s $VAULT_ADDR/v1/sys/health | jq

# Verify token
vault token lookup

# Check path permissions
vault token capabilities secret/data/hosts/test-host
```

### Module Errors

```bash
# User not found
# Ensure user exists on target host
grep username /etc/passwd

# Permission denied
# Check sudo access
sudo -l

# chpasswd failed
# Check SELinux/AppArmor
ausearch -m avc -ts recent
```

### Debug Mode

```bash
# Ansible verbose
ansible-playbook main.yaml -vvvv

# Temporarily disable no_log for debugging (DEV ONLY!)
# Comment out no_log: true in tasks
```

### Shadow Verification

```bash
# /etc/shadow entry format
# username:$6$salt$hash:lastchange:min:max:warn:inactive:expire:

# $6$ = SHA-512
# Verify hash was updated
sudo getent shadow root
```

## Roadmap

- [ ] Support for additional password generation methods (base64, dictionary)
- [ ] Integration with external secret managers (AWS Secrets Manager, Azure Key Vault)
- [ ] Scheduled rotation via AWX/Tower
- [ ] Rotation notifications (email, Slack)
- [ ] Password complexity validation
- [ ] Rollback mechanism

## License

MIT

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Author

[@ruleito](https://github.com/ruleito)

docs gen by [cloude](https://claude.ai/)