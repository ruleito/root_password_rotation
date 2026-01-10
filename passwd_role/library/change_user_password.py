#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Ansible module for secure user password rotation with vault integration."""

from __future__ import absolute_import, division, print_function

# __metaclass__ = type

import crypt
import os
import spwd
import subprocess

from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = r'''
module: change_user_password
short_description: Rotate user password with vault hash verification
description:
    - Securely rotates user password if vault hash doesn't match system hash
    - Generates cryptographically secure random passwords
    - Supports SHA512 hashing
version_added: "1.0.0"
options:
    username:
        required: true
        type: str
        description: Target username to change password for
    vault_hash:
        type: str
        default: ''
        description: Expected password hash from vault (no_log for security)
        no_log: true
    pass_enc_type:
        type: str
        default: 'hex'
        description: Password encoding type (currently only 'hex' supported)
    password_length:
        type: int
        default: 16
        description: Length of generated password in bytes
author:
    - System Admin Team
'''

EXAMPLES = r'''
- name: Rotate password if not synced with vault
  change_user_password:
    username: appuser
    vault_hash: "{{ vault_password_hash }}"
    password_length: 24
'''


def generate_secure_password(length, encoding_type):
    """Generate a cryptographically secure random password.

    Args:
        length: Password length in bytes
        encoding_type: Encoding format ('hex' supported)

    Returns:
        Generated password string

    Raises:
        ValueError: If encoding_type is unsupported
    """
    if encoding_type == 'hex':
        return os.urandom(length).hex()
    raise ValueError(f"Unsupported pass_enc_type: {encoding_type}")


def get_system_password_hash(username):
    """Retrieve password hash from system shadow file.

    Args:
        username: Username to look up

    Returns:
        Password hash string

    Raises:
        KeyError: If user doesn't exist
    """
    return spwd.getspnam(username).sp_pwdp


def update_user_password(username, password):
    """Update user password via chpasswd.

    Args:
        username: Username to update
        password: New password in plaintext

    Returns:
        Tuple (success: bool, error_message: str)
    """
    try:
        proc = subprocess.run(
            ['chpasswd'],
            input=f"{username}:{password}\n",
            capture_output=True,
            text=True,
            check=False
        )
        if proc.returncode != 0:
            return False, f"chpasswd failed: {proc.stderr}"
        return True, ""
    except FileNotFoundError as e:
        return False, f"chpasswd command not found: {str(e)}"


def run_module():
    """Main module execution logic."""
    module = AnsibleModule(
        argument_spec={
            'username': {'type': 'str', 'required': True},
            'vault_hash': {'type': 'str', 'default': '', 'no_log': True},
            'pass_enc_type': {'type': 'str', 'default': 'hex'},
            'password_length': {'type': 'int', 'default': 16},
        },
        supports_check_mode=True
    )

    username = module.params['username']
    vault_hash = module.params['vault_hash']
    pass_enc_type = module.params['pass_enc_type']
    length = module.params['password_length']

    try:
        system_hash = get_system_password_hash(username)

        # Check if password needs rotation
        if not vault_hash or system_hash != vault_hash:
            try:
                password = generate_secure_password(length, pass_enc_type)
            except ValueError as e:
                module.fail_json(msg=str(e))
                return

            new_hash = crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))

            if module.check_mode:
                module.exit_json(
                    changed=True,
                    hash=new_hash,
                    plaintext=password
                )

            # Apply password change
            success, error_msg = update_user_password(username, password)
            if not success:
                module.fail_json(msg=error_msg)

            module.exit_json(
                changed=True,
                hash=new_hash,
                plaintext=password
            )

        # No change needed
        module.exit_json(
            changed=False,
            hash=system_hash,
            plaintext=''
        )

    except KeyError:
        module.fail_json(msg=f"User {username} not found")
    except PermissionError as e:
        module.fail_json(msg=f"Permission denied accessing shadow file: {str(e)}")
    except OSError as e:
        module.fail_json(msg=f"System error: {str(e)}")
    except ValueError as e:
        module.fail_json(msg=f"Invalid configuration: {str(e)}")


def main():
    """Entry point."""
    run_module()


if __name__ == '__main__':
    main()

