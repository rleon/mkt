"""Maintainer tools
"""
import os
import utils
from utils.git import *
import utils.gerrit as gerrit
import subprocess
import time
from datetime import datetime,timedelta
import operator
from utils.config import username

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

#--------------------------------------------------------------------------------------------------------
def get_review_votes(patch_set):
    data = []
    approvals = patch_set.get('approvals', [])
    for ps in sorted(approvals, key=operator.itemgetter('value')):
        data.append("Name: %s, Value: %s" %
                (ps['by']['name'],
                    ps['value']))

    return '\n'.join(data)

def build_review_list(args):
    rev = gerrit.Query(args.host, args.port)

    to_filter = []
    if args.projects:
        pjs = args.projects
        projects = gerrit.OrFilter().add_items('project', pjs)
        to_filter.append(projects)

    other = gerrit.Items()
    other.add_items('is', ['open'])
    other.add_items('status', ['new'])
    other.add_items('reviewer', ['self'])
    other.add_items('label', ['Code-Review=2'], True)
    other.add_items('label', ['ml=1'], True)
    td = timedelta(days=30)
    one_month = datetime.today() - td
    other.add_items('after', ["%.4d-%.2d-%.2d" % (one_month.year, one_month.month, one_month.day)])

    if args.limit is not None:
        other.add_items('limit', args.limit)

    to_filter.append(other)

    data = []
    for review in rev.filter(*to_filter):
        last_updated = datetime.fromtimestamp(review['lastUpdated'])
        data.append((review['number'], review['subject'][:90],
                review.get('topic'), review['owner']['name'], last_updated))

    return data

def args_review(parser):
    parser.add_argument(
        "--limit",
        dest="limit",
        help="Limit amount of patches to query",
        type=int,
        default=100)

def cmd_review(args):
    """Review patches"""

    args.projects = ["upstream/linux"]
    args.user = username
    args.host = "l-gerrit.mtl.labs.mlnx"
    args.port = 29418

    import texttable
    from texttable import Texttable
    t = Texttable(max_width=0)
    t.set_deco(Texttable.HEADER)
    t.set_header_align(["l", "c", "l", "l", "l"])
    t.header(('Number', 'Subject', 'Topic', 'Owner', 'Modified Time'))

    data = build_review_list(args)
    t.add_rows(data, False)
    print(t.draw())
