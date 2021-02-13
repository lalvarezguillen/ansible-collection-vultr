# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import time
import base64
from abc import ABCMeta, abstractmethod
from ansible.module_utils._text import to_text, to_bytes
from ansible.module_utils import six
from ..module_utils.vultr import (
    Vultr,
)


@six.add_metaclass(ABCMeta)
class AnsibleVultrAbstractServer(Vultr):
    module_name = ''
    base_api_path = ''

    def __init__(self, module):
        super(AnsibleVultrAbstractServer, self).__init__(
            module, self.module_name
        )

        self.server = None
        self.returns = {
            'SUBID': dict(key='id'),
            'label': dict(key='name'),
            'date_created': dict(),
            'allowed_bandwidth_gb': dict(convert_to='int'),
            'current_bandwidth_gb': dict(),
            'default_password': dict(),
            'internal_ip': dict(),
            'disk': dict(),
            'cost_per_month': dict(convert_to='float'),
            'location': dict(key='region'),
            'main_ip': dict(key='v4_main_ip'),
            'network_v4': dict(key='v4_network'),
            'gateway_v4': dict(key='v4_gateway'),
            'os': dict(),
            'pending_charges': dict(convert_to='float'),
            'ram': dict(),
            'plan': dict(),
            'status': dict(),
            'tag': dict(),
            'v6_main_ip': dict(),
            'v6_network': dict(),
            'v6_network_size': dict(),
            'v6_networks': dict(),
        }
        self.server_power_state = None

    def get_startup_script(self):
        return self.query_resource_by_key(
            key='name',
            value=self.module.params.get('startup_script'),
            resource='startupscript',
        )

    def get_os(self):
        return self.query_resource_by_key(
            key='name',
            value=self.module.params.get('os'),
            resource='os',
            use_cache=True,
            id_key='OSID',
        )

    def get_ssh_keys(self):
        ssh_key_names = self.module.params.get('ssh_keys')
        if not ssh_key_names:
            return []

        ssh_keys = []
        for ssh_key_name in ssh_key_names:
            ssh_key = self.query_resource_by_key(
                key='name',
                value=ssh_key_name,
                resource='sshkey',
                use_cache=True,
                id_key='SSHKEYID',
            )
            if ssh_key:
                ssh_keys.append(ssh_key)
        return ssh_keys

    def get_region(self):
        return self.query_resource_by_key(
            key='name',
            value=self.module.params.get('region'),
            resource='regions',
            use_cache=True,
            id_key='DCID',
        )

    def get_user_data(self):
        user_data = self.module.params.get('user_data')
        if user_data is not None:
            user_data = to_text(base64.b64encode(to_bytes(user_data)))
        return user_data

    def get_server_user_data(self, server):
        if not server or not server.get('SUBID'):
            return None

        user_data = self.api_query(
            path="%s/get_user_data?SUBID=%s" % (
                self.base_api_path, server.get('SUBID')
            )
        )
        return user_data.get('userdata')

    @abstractmethod
    def get_server(self, refresh=False):
        pass

    def _wait_for_state(self, key='status', state=None, timeout=500):
        time.sleep(1)
        server = self.get_server(refresh=True)
        for s in range(0, timeout):
            if state is None and server.get(key):
                break
            if server.get(key) == state:
                break
            time.sleep(2)
            server = self.get_server(refresh=True)

        # Timed out
        else:
            if state is None:
                msg = "Wait for '%s' timed out" % key
            else:
                msg = "Wait for '%s' to get into state '%s' timed out" % (key, state)
            self.fail_json(msg=msg)
        return server

    def present_server(self, start_server=True):
        server = self.get_server()
        if not server:
            server = self._create_server(server=server)
        else:
            server = self._update_server(
                server=server, start_server=start_server
            )
        return server

    @abstractmethod
    def _create_server(self, server=None):
        pass

    @abstractmethod
    def _update_server(self, server=None, start_server=True):
        pass

    def absent_server(self):
        server = self.get_server()
        if server:
            self.result['changed'] = True
            self.result['diff']['before']['id'] = server['SUBID']
            self.result['diff']['after']['id'] = ""
            if not self.module.check_mode:
                data = {
                    'SUBID': server['SUBID']
                }
                self.api_query(
                    path="%s/destroy" % self.base_api_path,
                    method="POST",
                    data=data
                )
                for s in range(0, 60):
                    if server is not None:
                        break
                    time.sleep(2)
                    server = self.get_server(refresh=True)
                else:
                    self.fail_json(
                        msg="Wait for server '%s' to get deleted timed out" % server['label']
                    )
        return server
