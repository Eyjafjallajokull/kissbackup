from datetime import date, datetime
from glob import glob
from os import path, mkdir, unlink
from os.path import basename
import yaml
import subprocess
import sys
import logging

config = yaml.load(open('config.yml'))


def call(cmd):
    logging.debug('Exec: %s' % (cmd,))
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout, stderr) = process.communicate()
    if process.returncode != 0:
        print stdout, stderr
        raise RuntimeError('Last command failed: ' + cmd)


class Kissbackup(object):
    def __init__(self):
        logging.debug('Initialize backend')
        self.backend = Hubic(config['backends']['hubic'])
        self.task = None
        self.task_name = None
        self.time = datetime.now()
        try:
            mkdir(config['backup_dir'], 0700)
        except OSError as e:
            if e.errno != 17:
                raise e

    def process_tasks(self):
        for task_name, task in config['tasks'].items():
            self.task_name = task_name
            self.task = task
            logging.info('Backup task: %s' % (task_name,))
            self.simple_command_stage('prepare')
            self.simple_command_stage('compress')
            self.upload()
            self.simple_command_stage('cleanup')
            self.cleanup_archives()
        logging.info('Finished')

    def simple_command_stage(self, code):
        if not code in self.task:
            return
        logging.info('Stage %s' % code)
        cmd = self.task[code] % {'prepared': self.get_prepared_path(), 'compressed': self.get_compressed_path()}
        call(cmd)

    def upload(self):
        if not 'upload' in self.task or self.task['upload'] != 1:
            return
        logging.info('Stage upload')
        self.backend.upload(self.get_compressed_path())

    def get_output_name(self):
        return '{1:%Y}-{1:%m}-{1:%d}-{0}'.format(self.task_name, self.time)

    def get_prepared_path(self):
        return path.join(config['backup_dir'], self.get_output_name())

    def get_compressed_path(self):
        ext = ''
        if 'compress_ext' in self.task:
            ext = self.task['compress_ext']
        return path.join(config['backup_dir'], self.get_output_name()) + ext

    def cleanup_archives(self):
        if not 'keep_archives' in self.task:
            return
        logging.info('Stage archive cleanup')
        count = int(self.task['keep_archives'])
        to_remove = sorted(glob(path.join(config['backup_dir'], '*-%s.*' % self.task_name)))
        for f in to_remove[0:-count]:
            logging.debug('Remove: %s' % (f,))
            unlink(f)


class Backend(object):
    def __init__(self, config):
        pass

    def list(self):
        pass

    def upload(self, file):
        pass

    def delete(self):
        pass


class Hubic(Backend):
    def __init__(self, config):
        self.config = config
        super(Hubic, self).__init__(config)
        cmd = ('python vendor/hubic.py --hubic-username=%s --hubic-password=%s --hubic-client-id=%s ' +
               '--hubic-client-secret=%s --hubic-redirect-uri=%s --token') % \
              (config['username'],
               config['password'],
               config['client_id'],
               config['client_secret'],
               config['redirect_uri'])
        subprocess.call(cmd.split(' '), stdout=sys.stdout, stderr=sys.stderr, stdin=sys.stdin)

    def upload(self, file):
        cmd = 'python vendor/hubic.py --swift -- upload --object-name %s %s %s ' % \
              (self.config['remote_path']+basename(file), self.config['container'], file)
        call(cmd)
