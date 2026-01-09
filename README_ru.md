# Root Password Rotation

Ansible-роль для автоматической ротации паролей root-пользователя на Linux-серверах с интеграцией HashiCorp Vault для безопасного хранения credentials.

## Содержание

- [Обзор](#обзор)
- [Архитектура](#архитектура)
- [Требования](#требования)
- [Установка](#установка)
- [Конфигурация](#конфигурация)
- [Использование](#использование)
- [Переменные](#переменные)
- [Тестовое окружение](#тестовое-окружение)
- [Безопасность](#безопасность)
- [Troubleshooting](#troubleshooting)

## Обзор

Роль реализует следующий workflow:

1. Читает текущий хеш пароля из HashiCorp Vault
2. Сравнивает с системным хешем на целевом хосте
3. При несовпадении (или отсутствии записи в Vault) генерирует новый криптографически стойкий пароль
4. Устанавливает новый пароль на целевом хосте через `chpasswd`
5. Сохраняет plaintext-пароль и хеш в Vault

Это позволяет:
- Автоматизировать compliance-требования по ротации паролей
- Централизованно хранить credentials в Vault
- Иметь аудит-трейл изменений (через Vault audit log)
- Избежать хранения паролей в Ansible inventory или playbooks

## Архитектура

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

### Структура проекта

```
root_password_rotation/
├── passwd_role/                 # Основная Ansible-роль
│   ├── defaults/
│   │   └── main.yaml           # Дефолтные значения переменных
│   ├── library/
│   │   └── change_user_password.py  # Custom Ansible module
│   └── tasks/
│       ├── main.yaml           # Entry point
│       └── pass_policy.yaml    # Логика ротации
├── test-role/                   # Тестовый playbook
│   ├── main.yaml
│   └── roles/pass/             # Копия роли для тестов
├── Vagrantfile                  # Тестовое окружение
└── README.md
```

## Требования

### Ansible Controller

- Python 3.8+
- Ansible 2.10+
- `community.hashi_vault` collection
- Python-библиотека `hvac`

```bash
pip install ansible hvac
ansible-galaxy collection install community.hashi_vault
```

### Target Hosts

- Linux (тестировалось на Ubuntu 24.04)
- Python 3 (для Ansible modules)
- Sudo-доступ для смены пароля root

### HashiCorp Vault

- Vault server с включённым KV v2 secrets engine
- Токен с правами read/write на path `secret/data/hosts/*`

## Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/ruleito/root_password_rotation.git
cd root_password_rotation
```

### 2. Копирование роли

```bash
# Вариант 1: Копирование в стандартную директорию ролей
cp -r passwd_role ~/.ansible/roles/passwd_role

# Вариант 2: Указание пути в ansible.cfg
echo "roles_path = ./passwd_role:~/.ansible/roles" >> ansible.cfg
```

### 3. Установка зависимостей

```bash
ansible-galaxy collection install community.hashi_vault
pip install hvac
```

## Конфигурация

### Environment Variables

Роль ожидает следующие переменные окружения:

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

## Использование

### Базовый playbook

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

### Запуск

```bash
# Все хосты
ansible-playbook rotate_passwords.yml

# Конкретный хост
ansible-playbook rotate_passwords.yml --limit server-01

# Check mode (dry-run)
ansible-playbook rotate_passwords.yml --check

# С verbose output
ansible-playbook rotate_passwords.yml -vvv
```

### Использование тегов

```bash
# Только ротация паролей
ansible-playbook rotate_passwords.yml --tags def_pass_policy
```

## Переменные

### defaults/main.yaml

| Переменная | Default | Описание |
|------------|---------|----------|
| `vault_path` | `secret/data/hosts` | KV path в Vault для хранения credentials |
| `user` | `root` | Пользователь, чей пароль ротируется |
| `pass_enc_type` | `hex` | Тип генерации пароля (`hex`) |
| `pass_length` | `16` | Длина пароля (для hex = 32 символа в результате) |

### Переопределение переменных

```yaml
# В playbook
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
# В inventory (per-host)
all:
  hosts:
    server-01:
      pass_length: 32
```

## Custom Module: change_user_password

Роль включает custom Ansible module `/library/change_user_password.py`.

### Параметры модуля

| Параметр | Required | Default | Описание |
|----------|----------|---------|----------|
| `username` | yes | - | Имя пользователя |
| `vault_hash` | no | `''` | Хеш пароля из Vault для сравнения |
| `pass_enc_type` | no | `hex` | Метод генерации пароля |
| `password_length` | no | `16` | Длина пароля |

### Возвращаемые значения

| Поле | Описание |
|------|----------|
| `changed` | `true` если пароль был изменён |
| `hash` | SHA512 хеш нового пароля |
| `plaintext` | Plaintext пароль (пустой если не изменялся) |

### Алгоритм работы

```python
1. Получить текущий хеш из /etc/shadow (spwd.getspnam)
2. Сравнить с vault_hash
3. Если различаются или vault_hash пуст:
   - Сгенерировать новый пароль: os.urandom(length).hex()
   - Создать хеш: crypt.crypt(password, crypt.mksalt(METHOD_SHA512))
   - Установить через chpasswd
4. Вернуть результат
```

## Тестовое окружение

Репозиторий включает `Vagrantfile` для локального тестирования.

### Компоненты

- **controller** (192.168.56.10): Ansible controller + Vault в Docker
- **host01** (192.168.56.11): Target host для тестирования

### Запуск

```bash
# Поднять окружение
vagrant up

# Подключиться к controller
vagrant ssh controller

# На controller:
cd ~/ansible
source ~/.bashrc  # загрузит VAULT_ADDR и VAULT_TOKEN

# Тест подключения к Vault
ansible-playbook test_vault.yml

# Запуск ротации паролей
ansible-playbook main.yaml
```

### Проверка результата

```bash
# На controller - проверить Vault
curl -s -H "X-Vault-Token: root" \
  http://192.168.56.10:8200/v1/secret/data/hosts/test-host-01 | jq

# На host01 - проверить shadow
vagrant ssh host01
sudo grep root /etc/shadow
```

### Vault UI

Доступен по адресу: `http://localhost:8200` (token: `root`)

## Безопасность

### Рекомендации для Production

1. **Vault Token Management**
   - Используйте AppRole или другой auth method вместо static token
   - Настройте TTL и renewal policies
   
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
   - Используйте TLS для Vault
   - Ограничьте доступ к Vault по IP
   - Используйте bastion host для Ansible

5. **Ansible Vault** для локальных secrets
   ```bash
   ansible-vault encrypt_string 'vault_token' --name 'vault_token'
   ```

### no_log

Роль использует `no_log: true` для всех tasks, работающих с credentials:

```yaml
- name: Read password from Vault
  community.hashi_vault.vault_read:
    ...
  no_log: true  # Не логировать plaintext

- name: Rotate password
  change_user_password:
    ...
  no_log: true  # Не логировать пароль
```

## Troubleshooting

### Vault Connection Issues

```bash
# Проверить доступность Vault
curl -s $VAULT_ADDR/v1/sys/health | jq

# Проверить токен
vault token lookup

# Проверить права на path
vault token capabilities secret/data/hosts/test-host
```

### Module Errors

```bash
# User not found
# Убедитесь, что пользователь существует на target host
grep username /etc/passwd

# Permission denied
# Проверьте sudo доступ
sudo -l

# chpasswd failed
# Проверьте SELinux/AppArmor
ausearch -m avc -ts recent
```

### Debug Mode

```bash
# Ansible verbose
ansible-playbook main.yaml -vvvv

# Временно отключить no_log для отладки (ТОЛЬКО в dev!)
# Закомментировать no_log: true в tasks
```

### Проверка shadow

```bash
# Формат записи в /etc/shadow
# username:$6$salt$hash:lastchange:min:max:warn:inactive:expire:

# $6$ = SHA-512
# Проверить, что хеш обновился
sudo getent shadow root
```

## Roadmap

- [ ] Поддержка других методов генерации паролей (base64, словарный)
- [ ] Интеграция с external secret managers (AWS Secrets Manager, Azure Key Vault)
- [ ] Scheduled rotation через AWX/Tower
- [ ] Notification при ротации (email, Slack)
- [ ] Password complexity validation
- [ ] Rollback mechanism

## Лицензия

MIT

## Contributing

1. Fork репозитория
2. Создайте feature branch (`git checkout -b feature/amazing-feature`)
3. Commit изменения (`git commit -m 'Add amazing feature'`)
4. Push в branch (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

## Автор

[@ruleito](https://github.com/ruleito)