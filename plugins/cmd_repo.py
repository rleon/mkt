"""Maintainer tools
"""
import os
import utils
from utils.git import *
import subprocess

section = utils.load_config_file()
kernel_src = section['kernel']

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