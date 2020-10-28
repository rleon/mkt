"""Maintainer tools
"""
import os
import utils
from utils.git import *
import subprocess
import tempfile

section = utils.load_config_file()
kernel_src = section.get('kernel', None)

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
        status = git_simple_output(["status"])
        for line in status.splitlines():
            if "deleted by us:" in line:
                line = line.split(':')
                git_call(["rm", str(line[1].lstrip())])

        diff = git_output(["rerere", "diff"])
        num_of_lines = len(diff.splitlines())
        if num_of_lines > 1:
            exit("Fix rebase conflict, continue manually and rerun script once you are done.")

        # Add removed files
        git_call(["add", "--update"])
        git_call(["commit", "--no-edit"])

def build_testing(args):
    testing = { 'testing/rdma-rc': ( 'rdma-rc' , ['master'] ),
            'testing/rdma-next' : ( 'testing/rdma-rc' , ['rdma-next', 'rdma/hmm'] )}
    for key, value in testing.items():
        git_checkout_branch(key)
        git_reset_branch(value[0])
        for item in value[1]:
            merge_with_rerere(item)

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
    branches = {'rdma-next' : ( 'rdma/wip/dl-for-next', 'rdma/wip/jgg-for-next', 'rdma/for-next'),
            'rdma-rc' : ( 'rdma/wip/jgg-for-rc', 'rdma/wip/dl-for-rc', 'rdma/for-rc') }

    for key, value in branches.items():
        latest = git_return_latest(value[0], value[1])
        latest = git_return_latest(value[2], latest)
        if latest is None:
            print("%s and %s diverged, send an email to Doug/Jason, Drop an email to them ..." %(value[0], value[1]))
            latest = value[2]

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

def upload_to_gerrit(base, mbranch, branch, changeid):
    testing_br = 'm/%s' % (branch)
    original_br = git_checkout_branch(testing_br);

    git_reset_branch(base)
    log = git_simple_output(['log', '-n', '100', '--abbrev=12', '--format=commit %h (\"%s\")', 'HEAD..', branch])
    git_call(['merge', '--squash', '--ff', branch])

    with tempfile.NamedTemporaryFile('w') as F:
        F.write('%s testing\n\n%s\n\nIssue: 1308201\nChange-Id: %s\nSigned-off-by: Leon Romanovsky <leonro@nvidia.com>' % (branch, log, changeid))
        F.flush()
        git_call(['commit', '--no-edit', '-F', F.name])
        git_call(['push', 'mellanox', 'HEAD:refs/for/%s/leon_testing' % (mbranch)])

    git_checkout_branch(original_br)

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
        # Do it after build_* routines, because they can fail in
        # merge conflicts and we don't want to push again to gerrit
        if not is_next:
            upload_to_gerrit('mellanox/rdma-next-mlx', 'rdma-next-mlx',
                    'rdma-next', 'Iaaf0a270fff9fb7537bee5b90d53a5dff51238a8')
        if not is_rc:
            upload_to_gerrit('mellanox/rdma-rc-mlx', 'rdma-rc-mlx',
                    'rdma-rc', 'I57c11684febd2aa97ebb44ae82368466458dd8f4')

        upload_to_gerrit('origin/master', 'master',
                    'queue-next', 'I57c11684febd2aa97ebb44ae82368466458dd8f5')
        upload_to_gerrit('origin/master', 'master',
                    'queue-rc', 'I57c11684febd2aa97ebb44ae82368466458dd8f6')

        git_checkout_branch(original_branch)

#--------------------------------------------------------------------------------------------------------
def args_upload(parser):
    pass

def cmd_upload(args):
    """Upload to k.o."""

    print("========================= Insert NitroKey =========================");
    input();

    with in_directory(kernel_src):
        git_call(["push", "-f", "origin",
        "rdma-next", "rdma-rc",
        "testing/rdma-next",
        "testing/rdma-rc", "master",
        "mlx-next", "mlx-rc"])
        git_call(["push", "-f", "ml", "master",
            "queue-next", "queue-rc"])
        git_call(["push", "ml", "mlx5-next"])

#--------------------------------------------------------------------------------------------------------
def args_gtest(parser):
    pass

def cmd_gtest(args):
    """Upload to gerrit to test specific patch."""

    with in_directory(kernel_src):
        branch = git_checkout_branch('m/gerrit-ci');

        branches = { 'mlx-next': 'rdma-next-mlx',
                'mlx-rc': 'rdma-rc-mlx', 'master': 'master' }
        base = None
        for key in branches:
            base = git_return_base(key, branch)
            if base is not None:
                break

        if base is None:
            # Try harder, maybe we are based on mega-commii
            line = git_simple_output(['log','-n', '50', '-1',
                '--oneline', '--grep', 'mega-commit', branch])
            line = line.split('on')
            try:
                base = line[1].strip()
            except IndexError:
                pass

        if base is None:
            git_checkout_branch(branch)
            exit("Failed to get patch set base, need to take manually ...")

        git_reset_branch(base)
        log = git_simple_output(['log', '-n', '100', '--abbrev=12',
            '--format=commit %h (\"%s\")', 'HEAD..', branch])
        git_call(['merge', '--squash', '--ff', branch])

        changeid = 'I57c11684febd2aa97ebb44ae82368466458dd810'
        with tempfile.NamedTemporaryFile('w') as F:
            F.write('%s testing\n\n%s\n\nIssue: 1308201\nChange-Id: %s\nSigned-off-by: Leon Romanovsky <leonro@nvidia.com>' % (branch.strip().decode("utf-8"), log, changeid))
            F.flush()
            git_call(['commit', '--no-edit', '-F', F.name])
            git_call(['push', 'mellanox', 'HEAD:refs/for/%s/leon_testing' % (branches[base])])

        git_checkout_branch(branch)

#--------------------------------------------------------------------------------------------------------
def args_mega(parser):
    pass

def cmd_mega(args):
    """Create mega-commit to simulate latest submission queue."""

    with in_directory(kernel_src):
        branch = git_current_branch().strip().decode("utf-8")
        if not branch.startswith('m/'):
            exit("Works on m/* branches only ...")

        branches = { 'mlx-next': 'rdma-next-mlx',
                'mlx-rc': 'rdma-rc-mlx', 'master': 'master' }
        base = None
        for key in branches:
            base = git_return_base(key, branch)
            if base is not None:
                break

        if base is None:
            exit("Failed to get patch set base, need to take manually ...")

        sha = git_simple_output(['rev-parse', branch])
        git_reset_branch(base)
        log = git_simple_output(['log', '-n', '100', '--abbrev=12',
            '--format=commit %h (\"%s\")', 'HEAD..', sha])
        git_call(['merge', '--squash', '--ff', sha])

        import random
        numb = random.randrange(1000000000, 9999999999)
        changeid = 'I57c11684febd2aa97ebb44ae823684' + str(numb)
        with tempfile.NamedTemporaryFile('w') as F:
            F.write('mega-commit based on %s\n\n%s\n\nIssue: 1308201\nChange-Id: %s\nSigned-off-by: Leon Romanovsky <leonro@nvidia.com>' % (base, log, changeid))
            F.flush()
            git_call(['commit', '--no-edit', '-F', F.name])
