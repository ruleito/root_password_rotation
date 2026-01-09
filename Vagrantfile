Vagrant.configure("2") do |config|
  config.vm.box = "bento/ubuntu-24.04"

  config.vm.define "controller" do |controller|
    controller.vm.hostname = "ansible-controller"
    controller.vm.network "private_network", ip: "192.168.56.10"
    controller.vm.network "forwarded_port", guest: 8200, host: 8200
    controller.vm.synced_folder "test-role/", "/home/vagrant/ansible"
    controller.vm.provider "virtualbox" do |qe|
      qe.memory = "2048"
      qe.cpus = 2
    end

    controller.vm.provision "shell", inline: <<-SHELL
      set -euo pipefail

      echo "=== Controller Setup ==="
      apt-get update
      apt-get upgrade -y
      apt-get install -y python3 python3-pip python3-venv git curl vim jq rsync sshpass
      if ! command -v docker &> /dev/null; then
          echo "Installing Docker..."
          curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
          sh /tmp/get-docker.sh
          rm /tmp/get-docker.sh
          usermod -aG docker vagrant
          systemctl enable docker
          systemctl start docker
      fi

      pip3 install --break-system-packages ansible hvac
      if [ ! -f /home/vagrant/.ssh/id_rsa ]; then
          su - vagrant -c "ssh-keygen -t ed25519 -f /home/vagrant/.ssh/id_rsa -N ''"
      fi
      cp /home/vagrant/.ssh/id_rsa.pub /vagrant/controller_key.pub
      su - vagrant -c "ansible-galaxy collection install community.hashi_vault --force"
      mkdir /home/vagrant/ansible/inventory
      cat > /home/vagrant/ansible/ansible.cfg <<'EOF'
[defaults]
inventory = ./inventory/hosts.yml
host_key_checking = False
roles_path = ./roles
library = ./library
interpreter_python = auto_silent
retry_files_enabled = False

[privilege_escalation]
become = True
become_method = sudo
become_user = root
become_ask_pass = False
EOF
      cat > /home/vagrant/ansible/inventory/hosts.yml <<'EOF'
all:
  hosts:
    test-host-01:
      ansible_host: 192.168.56.11
      ansible_user: vagrant
      ansible_ssh_private_key_file: ~/.ssh/id_rsa
EOF

      chown -R vagrant:vagrant /home/vagrant/ansible

      echo "Starting Vault container..."
      docker pull hashicorp/vault:latest

      docker run -d \
          --name vault \
          --restart unless-stopped \
          --cap-add=IPC_LOCK \
          -p 8200:8200 \
          -e 'VAULT_DEV_ROOT_TOKEN_ID=root' \
          -e 'VAULT_DEV_LISTEN_ADDRESS=0.0.0.0:8200' \
          hashicorp/vault:latest

      sleep 5
      if curl -s http://localhost:8200/v1/sys/health > /dev/null; then
          echo "✓ Vault is running"
      else
          echo "✗ Vault failed to start"
          exit 1
      fi
      cat >> /home/vagrant/.bashrc <<'EOF'

# Vault configuration
export VAULT_ADDR='http://192.168.56.10:8200'
export VAULT_TOKEN='root'
export ANSIBLE_NOCOWS=1
EOF

      docker exec vault vault secrets enable -path=secret kv-v2 || true
      cat > /home/vagrant/ansible/test_vault.yml <<'EOF'
---
- name: test vault con
  hosts: localhost
  gather_facts: no

  tasks:
    - name: write test data
      community.hashi_vault.vault_write:
        url: "{{ lookup('env', 'VAULT_ADDR') }}"
        token: "{{ lookup('env', 'VAULT_TOKEN') }}"
        path: "secret/data/test"
        validate_certs: false
        data:
          data:
            message: "hi, this is test message"

    - name: read vault data
      community.hashi_vault.vault_read:
        url: "{{ lookup('env', 'VAULT_ADDR') }}"
        token: "{{ lookup('env', 'VAULT_TOKEN') }}"
        path: "secret/data/test"
        validate_certs: false
      register: vault_result

    - name: print data
      debug:
        msg: "{{ vault_result.data.data }}"
EOF

      chown vagrant:vagrant /home/vagrant/ansible/test_vault.yml

      echo "=== Controller setup complete ==="
      echo "Vault: http://192.168.56.10:8200 (token: root)"
    SHELL
  end

  config.vm.define "host01" do |host|
    host.vm.hostname = "test-host-01"
    host.vm.network "private_network", ip: "192.168.56.11"

    host.vm.provider "virtualbox" do |qe|
      qe.memory = "2048"
      qe.cpus = 2
    end

    host.vm.provision "shell", inline: <<-SHELL
      set -euo pipefail
      echo "=== Host Setup ==="
      apt-get update
      apt-get upgrade -y

      apt-get install -y python3 python3-pip curl vim

      if [ -f /vagrant/controller_key.pub ]; then
          echo "Adding controller SSH key..."
          mkdir -p /home/vagrant/.ssh
          cat /vagrant/controller_key.pub >> /home/vagrant/.ssh/authorized_keys
          chmod 700 /home/vagrant/.ssh
          chmod 600 /home/vagrant/.ssh/authorized_keys
          chown -R vagrant:vagrant /home/vagrant/.ssh
      fi

      echo "vagrant ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/vagrant
      chmod 440 /etc/sudoers.d/vagrant

      echo "=== Host setup complete ==="
    SHELL
  end
end