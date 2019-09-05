"""Maintainer tools
"""
import os
import utils
from utils.git import *
import subprocess

section = utils.load_config_file()
kernel_src = section['kernel']

#--------------------------------------------------------------------------------------------------------
reverse_port = 3108

def args_proxy(parser):
     parser.add_argument(
        "--stop",
        dest="stop",
        action="store_true",
        help="Stop reversed proxy",
        default=False)

def cmd_proxy(args):
    """Manage reverse proxy on local machine"""
    server = 'leonro@10.137.188.1'
    try:
        ssh_pid = subprocess.check_output(['pgrep', '-f', 'ssh -N -R %s:localhost:22 ' %(reverse_port) + server])
        subprocess.call(['kill', '-9', ssh_pid.strip().decode("utf-8").strip('"')])
    except subprocess.CalledProcessError:
        pass

    try:
        status = subprocess.check_output(['sudo', 'systemctl', 'is-active', 'sshd'])
        args.stop = True
    except subprocess.CalledProcessError:
        pass

    if args.stop:
        print('SSH daemon is active, closing reverse proxy');
        subprocess.check_call(['sudo', 'systemctl', 'stop', 'sshd'])
    else:
        print('SSH daemon is inactive, starting reverse proxy');
        subprocess.check_call(['sudo', 'systemctl', 'restart', 'sshd'])
        subprocess.Popen(['ssh', '-N', '-R', '%s:localhost:22' % (reverse_port), server], close_fds=True)

#--------------------------------------------------------------------------------------------------------
def xremote_call(args):
    """Run X command on remote server"""
    return subprocess.call([
        'ssh', '-p', str(reverse_port), 'leonro@localhost', 'DISPLAY=:0'] + args)

def args_web(parser):
    parser.add_argument(
        "--rev",
        nargs=1,
        default=['HEAD'],
        help="Commit to check")

def cmd_web(args):
    """Open links founded in commit"""
    with in_directory(kernel_src):
        message = git_simple_output(['show', '--no-patch'] + args.rev)
        message = message.splitlines()

    urls = []
    for line in message:
        line = line.split()
        if len(line) < 2:
            continue

        word = line[0].lower()
        link = None
        if word == "issue:" and line[1].isdigit():
            link = 'https://redmine.mellanox.com/issues/%s' % (line[1])
        if word == "change-id:":
            link = 'http://l-gerrit.mtl.labs.mlnx:8080/#/q/change:%s' % (line[1])
        if word == "link:":
            link = line[1]

        if link is not None:
            urls.append('-url')
            urls.append(link)

    cmd = ['firefox', '-new-tab'] + urls
    xremote_call(cmd)
