"""Maintainer tools
"""
import os
import utils
from utils.git import *
import subprocess

section = utils.load_config_file()
kernel_src = section['kernel']

def x_git_output(args):
    """Run git and return the output"""
    try:
        o = subprocess.check_output(['git', ] + args, cwd=kernel_src)
    except subprocess.CalledProcessError:
        return None

    return o.strip().decode("utf-8")

def is_uptodate(a, b):
    if a == b:
        return True;

    l = git_output(["log", "--pretty=format:%H", "-1", a])
    r = git_output(["log", "--pretty=format:%H", "-1", b])
    return l == r

def merge_with_rerere(commit):
    try:
        git_call(["merge", "--no-ff", "--no-edit", "--rerere-autoupdate", commit])
    except subprocess.CalledProcessError:
        diff = git_output(["rerere", "diff"])
        num_of_lines = len(diff.splitlines())
        if num_of_lines > 1:
            exit("Fix rebase conflict, continue manually and rerun script once you are done.")
        git_call(["commit", "--no-edit"])

def build_testing(args):
    testing = { 'testing/rdma-rc': ( 'rdma-rc' , 'master' ),
            'testing/rdma-next' : ( 'testing/rdma-rc' , 'rdma-next' )}
    for key, value in testing.items():
        git_checkout_branch(key)
        git_reset_branch(value[0])
        merge_with_rerere(value[1])

def build_queue(args):
    queue = ('rc', 'next')
    for item in queue:
        git_checkout_branch("queue-%s" % (item))
        git_reset_branch("saeed/net-%s" % (item))
        merge_with_rerere("testing/rdma-%s" % (item))

def update_mlx5_next(args):
    """mlx5-next branch"""
    if is_uptodate("mlx5-next", "ml/mlx5-next"):
        return

    git_checkout_branch("mlx5-next")
    git_reset_branch("ml/mlx5-next")

def update_master(args):
    """master branch"""
    linus_tag = git_output(["log", "--pretty=format:%H", "-1",
        "--author=Torvalds", "--no-merges", "linus/master", "--",
        "Makefile"])
    if is_uptodate("master", linus_tag):
        return

    git_checkout_branch("master")
    git_reset_branch(linus_tag)

def update_tags(args):
    """tags update"""
    tags = {'mlx-next' : 'rdma/for-next', 'mlx-rc': 'rdma/for-rc'}
    for key, value in tags.items():
        if not is_uptodate(key, value):
            git_call(["tag", "-f", key, value])

def forward_branches(args):
    branches = {'rdma-next' : ( 'rdma/wip/dl-for-next', 'rdma/wip/jgg-for-next'),
            'rdma-rc' : ( 'rdma/wip/jgg-for-rc', 'rdma/wip/dl-for-rc') }

    for key, value in branches.items():
        latest = None
        try:
            git_call(["merge-base", "--is-ancestor", value[0], value[1]])
            latest = value[1]
        except subprocess.CalledProcessError:
            try:
                git_call(["merge-base", "--is-ancestor", value[1], value[0]])
                latest = value[0]
            except subprocess.CalledProcessError:
                pass

        if latest is None:
            exit("%s and %s diverged, send an email to Doug/Jason, exciting ..." %(value[0], value[1]))

        try:
            git_call(["merge-base", "--is-ancestor", latest, key])
            # rdma-next/rdma-rc is already based on latest branch
            continue
        except subprocess.CalledProcessError:
            pass

        try:
            git_call(['rebase', '--onto', 'remotes/%s' % (latest), '--root', key])
        except subprocess.CalledProcessError:
            diff = git_output(["rerere", "diff"])
            num_of_lines = len(diff.splitlines())
            if num_of_lines > 1:
                exit("Fix rebase conflict, continue manually and rerun script once you are done.")
            git_call(["commit", "--no-edit"])

def args_update(parser):
    pass

def cmd_update(args):
    """Update kernel branches"""

    with in_directory(kernel_src):
        git_call(["remote", "update", "--prune"])
        original_branch = git_checkout_branch();

        update_mlx5_next(args)
        update_master(args)
        update_tags(args)
        forward_branches(args)

        is_master = is_uptodate("master", "origin/master")
        is_next = is_uptodate("rdma-next", "origin/rdma-next")
        is_rc = is_uptodate("rdma-rc", "origin/rdma-rc")

        if not is_master or not is_next or not is_rc:
            build_testing(args)
            build_queue(args)

        git_checkout_branch(original_branch)

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
        message = x_git_output(['show', '--no-patch'] + args.rev)
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
def args_upload(parser):
    pass

def cmd_upload(args):
    """Upload to k.o."""

    print("========================= Insert NitroKey =========================");
    input();

    with in_directory(kernel_src):
        git_fetch("linus")
        git_fetch("rdma")
        git_fetch("s")

        original_br = git_checkout_branch("master")
        git_reset_branch("s/master")

        git_call(["push", "-f", "origin",
        "s/rdma-next:rdma-next", "s/rdma-rc:rdma-rc",
        "s/testing/rdma-next:testing/rdma-next",
        "s/testing/rdma-rc:testing/rdma-rc", "s/master:master",
        "mlx-next", "mlx-rc"])
        git_call(["push", "-f", "ml", "s/master:master",
            "s/queue-next:queue-next", "s/queue-rc:queue-rc"])
        git_call(["push", "ml", "s/mlx5-next:mlx5-next"])

        git_checkout_branch(original_br)
