# coding: utf-8

import json
import subprocess
import sys
import time

class Stack(object):
    """
    Heat Stack manager.
    Keyword Arguments
    -------------------
    url : string or None
    path : string or None
        Location of template file
    template : string or None
        Template contents (if not a file).
    exit_delay : number, default: 0
        Number of seconds to pause before attempting to delete the
        stack. This can be used to avoid race conditions when tearing things
        down.
    """
    def __init__(self, stack_name=None, url=None, path=None, template=None, parameters=None, verbose=False, exit_delay=0):
        if not stack_name:
            raise ValueError('Stack name is required!')
        self.stack_name = stack_name
        self.stack_id = None
        if sum(1 for source in [url, path, template] if source) != 1:
            raise ValueError('only provide one of url, path, or template.')
        if url or path:
            self.path = url or path
        else:
            self.template = template
            self.path = None
        self.parameters = parameters if parameters is not None else {}
        self.verbose = verbose
        self.exit_delay = exit_delay

    def _pv(self, *args, **kwargs):
        """print if verbose"""
        if not self.verbose:
            return
        print(*args, **kwargs)

    def _popen(self, cmd, **kwargs):
        pkwargs = {
            'shell': True,
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'universal_newlines': True,
            'check': False
        }
        pkwargs.update(kwargs)
        check = pkwargs.pop('check')

        proc = subprocess.Popen(cmd, **pkwargs)
        proc.wait()
        stdout, stderr = proc.communicate()
        self._pv(stdout, file=sys.stdout)
        self._pv(stderr, file=sys.stderr)
        self._stdout, self._stderr = stdout, stderr # debug
        if check and proc.returncode:
            raise RuntimeError('command returned code {}. {}'.format(proc.returncode, stderr))
        return proc, stdout, stderr

    def create(self):
        params = ' '.join('--parameter {}={}'.format(k, v) for k, v in self.parameters.items())
        try:
            if self.path is None:
                with tempfile.NamedTemporaryFile(mode='w') as tf:
                    tf.write(self.template)
                    tf.flush()
                    cmd = ('openstack stack create '
                               '--template {path} '
                               '{params} '
                               '--wait '
                               '--format json '
                               '{name}'
                          ).format(name=self.stack_name, path=tf.name, params=params)
                    proc, stdout, stderr = self._popen(cmd, check=True)
            else:
                cmd = ('openstack stack create '
                           '--template {path} '
                           '{params} '
                           '--wait '
                           '--format json '
                           '{name}'
                      ).format(name=self.stack_name, path=self.path, params=params)
                proc, stdout, stderr = self._popen(cmd, check=True)
        except RuntimeError as e:
            if not str(e).startswith('command returned code'):
                # some unknown exception
                raise

            cmd = 'openstack stack show --format json {}'.format(self.stack_name)
            proc, stdout, stderr = self._popen(cmd)
            if proc.returncode == 0:
                # stack exists, attempt deletion
                cmd = 'openstack stack delete --yes --wait {}'.format(self.stack_name)
                proc, stdout, stderr = self._popen(cmd, check=True)

            raise

        cmd = 'openstack stack show --format json {}'.format(self.stack_name)
        proc, stdout, stderr = self._popen(cmd, check=True)
        self.stack = json.loads(stdout)
        self.stack_id = self.stack['id']
        self.outputs = {o['output_key']: o['output_value'] for o in self.stack['outputs']}

    def delete(self):
        if self.stack_id:
            cmd = ('openstack stack delete --yes --wait {}').format(self.stack_id)
            proc, stdout, stderr = self._popen(cmd, check=True)
            self.stack_id = None

    def __enter__(self):
        self.create()

    def __exit__(self, exc_type, exc_value, traceback):
        time.sleep(self.exit_delay)
        self.delete()
