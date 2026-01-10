#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
module: change_user_password
short_description: Rotate user password
options:
    username:
        required: true
        type: str
    vault_hash:
        type: str
        default: ''
    pass_enc_type:
        type: str
        default: 'hex'
    password_length:
        type: int
        default: 16
'''

import os
import spwd
import crypt
import subprocess
from ansible.module_utils.basic import AnsibleModule


def run_module():
    module = AnsibleModule(
        argument_spec=dict(
            username=dict(type='str', required=True),
            vault_hash=dict(type='str', default='', no_log=True),
            pass_enc_type=dict(type='str', default='hex'),
            password_length=dict(type='int', default=16),
        ),
        supports_check_mode=True
    )

    username = module.params['username']
    vault_hash = module.params['vault_hash']
    pass_enc_type = module.params['pass_enc_type']
    length = module.params['password_length']

    try:
        system_hash = spwd.getspnam(username).sp_pwdp

        if not vault_hash or system_hash != vault_hash:
            if pass_enc_type == 'hex':
                password = os.urandom(length).hex()
            else:
                module.fail_json(msg=f"Unsupported pass_enc_type: {pass_enc_type}")
            new_hash = crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))
            if module.check_mode:
                module.exit_json(changed=True, hash=new_hash, plaintext=password)
            proc = subprocess.run(
                ['chpasswd'],
                input=f"{username}:{password}\n",
                capture_output=True,
                text=True
            )
            if proc.returncode != 0:
                module.fail_json(msg=f"chpasswd failed: {proc.stderr}")
            module.exit_json(changed=True, hash=new_hash, plaintext=password)
        module.exit_json(changed=False, hash=system_hash, plaintext='')

    except KeyError:
        module.fail_json(msg=f"User {username} not found")
    except Exception as e:
        module.fail_json(msg=str(e))


def main():
    run_module()


if __name__ == '__main__':
    main()