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

def set_gerrit_url(args):
    args.user = username
    args.host = "l-gerrit.mtl.labs.mlnx"
    args.port = 29418

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

def gerrit_link(args, changeId):
    rev = gerrit.Query(args.host, args.port)

    to_filter = []
    other = gerrit.Items()
    other.add_items('change', changeId)
    other.add_items('limit', 1)
    to_filter.append(other)

    for review in rev.filter(*to_filter):
        return review['url']

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

    set_gerrit_url(args)
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
            link = gerrit_link(args, line[1])
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

def manage_my_review(args):
    if args.id is None and args.topic is None:
        exit("Missing ID or topic to work on")

    rev = gerrit.Query(args.host, args.port)

    to_filter = []
    other = gerrit.Items()
    if args.topic:
        other.add_items('topic', args.topic)
    other.add_items('is', ['open'])
    other.add_items('status', ['new'])

    other.add_items('limit', args.limit)
    to_filter.append(other)

    email = git_simple_output(['config', 'user.email'])
    for review in rev.filter(*to_filter):
        if args.id and review['number'] != args.id:
            continue

        ticket = gerrit.Review(review, args.host, args.port)
        ticket.manage_reviewers(email, args.remove_me)

def reject_patch_set(args):
   old = git_checkout_branch('rdma-next')
   if old.strip().decode("utf-8").startswith('m/'):
       # TODO: posting -1 to gerrit and pushing comments over all patches
       git_call(['branch', '-D', old])

def pull_patch_set(args):
    rev = gerrit.Query(args.host, args.port)

    to_filter = []
    other = gerrit.Items()
    if args.topic:
        other.add_items('topic', args.topic)
        args.limit = 1

    other.add_items('limit', args.limit)
    other.add_items('is', ['open'])
    other.add_items('status', ['new'])
    other.add_items('reviewer', ['self'])

    to_filter.append(other)

    for review in rev.filter(*to_filter):
        if args.id and review['number'] != args.id:
            continue
        git_call(['fetch', 'mellanox', review['currentPatchSet']['ref']])
        git_call(['checkout', '-B', 'm/%s' % (review.get('topic')), 'FETCH_HEAD'])

        if args.rebase:
            br = { 'rdma-next-mlx': 'mlx-next', 'rdma-rc-mlx': 'mlx-rc'}
            try:
                git_output(['rebase', '--onto', br[review['branch']],
                    '--root', 'm/%s' % (review.get('topic'))])
            except subprocess.CalledProcessError:
                # Not a big deal, can't forward to latest dev branches
                print("Aborting branch forwarding ....")
                git_output(['rebase', '--abort'])


def print_review_list(args):

    import texttable
    from texttable import Texttable
    t = Texttable(max_width=0)
    t.set_deco(Texttable.HEADER)
    t.set_header_align(["l", "c", "l", "l", "l"])
    t.header(('Number', 'Subject', 'Topic', 'Owner', 'Modified Time'))

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
    other.add_items('limit', args.limit)

    to_filter.append(other)

    data = []
    for review in rev.filter(*to_filter):
        last_updated = datetime.fromtimestamp(review['lastUpdated'])
        data.append((review['number'], review['subject'][:90],
                review.get('topic'), review['owner']['name'], last_updated))

    t.add_rows(data, False)
    print(t.draw())

def args_review(parser):
    parser.add_argument(
        "--limit",
        dest="limit",
        help="Limit amount of patches to query",
        type=int,
        default=100)
    parser.add_argument(
        "--id",
        dest="id",
        help="Specific ID to work on",
        type=int,
        default=None)
    parser.add_argument(
        "--topic",
        dest="topic",
        help="Specific topic to work on",
        type=str,
        default=None)
    parser.add_argument(
        "--remove-me",
        dest="remove_me",
        help="Remove myself from reviewers list",
        action="store_true",
        default=False)
    parser.add_argument(
        "--add-me",
        dest="add_me",
        help="Add myself from reviewers list",
        action="store_true",
        default=False)
    parser.add_argument(
        "--no-rebase",
        action="store_false",
        dest="rebase",
        help="Skip rebase to latest development branch",
        default=True)
    parser.add_argument(
        "--reject",
        dest="reject",
        help="Reject patch set and post all comments for this topic",
        action="store_true",
        default=False)

def cmd_review(args):
    """Review patches"""

    args.projects = ["upstream/linux"]
    set_gerrit_url(args)

    if args.remove_me or args.add_me:
        manage_my_review(args)
        return

    if args.id or args.topic:
        pull_patch_set(args)
        return

    if args.reject:
        reject_patch_set(args)
        return

    print_review_list(args)
