"""Maintainer tools
"""
import os
import utils
import subprocess

section = utils.load_config_file()
kernel_src = section['kernel']

def git_call(args):
    """Run git and display the output to the terminal"""
    return subprocess.check_call([
        'git',
    ] + args, cwd=kernel_src)

def git_output(args):
    """Run git and return the output"""
    try:
        o = subprocess.check_output(['git', ] + args, cwd=kernel_src)
    except subprocess.CalledProcessError:
        return None

    return o.strip().decode("utf-8")

def checkout_branch(branch=None):
    """Checkout specific branch and return previous branch"""
    prev = git_output(["symbolic-ref", "--short", "-q", "HEAD"])
    if prev is None:
        exit("You are not in any branch, exciting ...");

    if branch is None:
        return prev;

    if prev != branch:
        git_call(["checkout", branch])
    return prev

def reset_branch(commit):
    """Reset to specific commit"""
    git_call(["reset", "--hard", commit])

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
        checkout_branch(key)
        reset_branch(value[0])
        merge_with_rerere(value[1])

def build_queue(args):
    queue = ('rc', 'next')
    for item in queue:
        checkout_branch("queue-%s" % (item))
        reset_branch("saeed/net-%s" % (item))
        merge_with_rerere("testing/rdma-%s" % (item))

def update_mlx5_next(args):
    """mlx5-next branch"""
    if is_uptodate("mlx5-next", "ml/mlx5-next"):
        return

    checkout_branch("mlx5-next")
    reset_branch("ml/mlx5-next")

def update_master(args):
    """master branch"""
    linus_tag = git_output(["log", "--pretty=format:%H", "-1",
        "--author=Torvalds", "--no-merges", "linus/master", "--",
        "Makefile"])
    if is_uptodate("master", linus_tag):
        return

    checkout_branch("master")
    reset_branch(linus_tag)

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

    git_call(["remote", "update", "--prune"])
    original_branch = checkout_branch();

    update_mlx5_next(args)
    update_master(args)
    update_tags(args)
    forward_branches(args)

    build_testing(args)
    build_queue(args)

    checkout_branch(original_branch)
