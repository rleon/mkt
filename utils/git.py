import os
import re
import subprocess
from contextlib import contextmanager

# Regex that matches a git object name/SHA1
IDRE = b"^[0-9a-fA-F]{40}$"


def bytes_join(*args):
    """Concatinate args together. If any of args are a bytes then the result
    will be bytes, otherwise it is str. This is useful when appending
    constant strings known to be simple characters."""
    if any(isinstance(I, bytes) for I in args):
        return b"".join(
            I if isinstance(I, bytes) else I.encode() for I in args)
    else:
        return "".join(args)


@contextmanager
def in_directory(dir):
    """Context manager that chdirs into a directory and restores the original
    directory when closed."""
    cdir = os.getcwd()
    try:
        os.chdir(dir)
        yield True
    finally:
        os.chdir(cdir)


def git_call(args):
    """Run git and display the output to the terminal"""
    return subprocess.check_call([
        'git',
    ] + args)


def git_output(args, mode=None, null_stderr=False, input=None):
    """Run git and return the output"""
    if null_stderr:
        with open("/dev/null") as F:
            o = subprocess.check_output(
                [
                    'git',
                ] + args, stderr=F, input=input)
    else:
        o = subprocess.check_output(
            [
                'git',
            ] + args, input=input)
    if mode == "raw":
        return o
    elif mode == "lines":
        return o.splitlines()
    elif mode is None:
        return o.strip()
    else:
        raise ValueError("Bad mode %r" % (mode))

def git_norm_id(gid):
    if not re.match(IDRE, gid):
        raise ValueError("Not a git ID %r" % (gid))
    if isinstance(gid, bytes):
        return gid.decode()
    return gid

def git_ref_id(thing, fail_is_none=False):
    """Return the git ID for a ref or None"""
    try:
        o = git_output(["rev-parse", thing], null_stderr=True)
    except subprocess.CalledProcessError:
        if fail_is_none:
            return None
        raise
    return git_norm_id(o)


def git_commit_id(thing, fail_is_none=False):
    """Returns a commit ID for thing. If thing is a tag or something then it is
    converted to a object ID"""
    return git_ref_id(
        bytes_join(thing, "^{commit}"), fail_is_none=fail_is_none)

def git_fetch(remote):
    """Run git fetch on specific remote"""
    return git_call(["fetch", remote, "--tags", "--force"])

def git_reset_branch(commit):
    """Reset to specific commit"""
    git_call(["reset", "--hard", commit])

def git_current_branch():
    return git_output(["symbolic-ref", "--short", "-q", "HEAD"])

def git_checkout_branch(branch=None):
    """Checkout specific branch and return previous branch"""
    prev = git_current_branch()
    if prev is None:
        exit("You are not in any branch, exciting ...");

    if branch is None:
        return prev;

    if prev != branch:
        git_call(["checkout", branch])
    return prev

def git_simple_output(args):
    """Run git and return the output"""
    try:
        o = subprocess.check_output(['git', ] + args)
    except subprocess.CalledProcessError:
        return None

    return o.strip().decode("utf-8")

def git_return_latest(left, right):
    """Try to decide if "left" is newer than "right" or vice-verse"""

    latest = None
    try:
        git_call(["merge-base", "--is-ancestor", left, right])
        latest = right
    except subprocess.CalledProcessError:
        try:
            git_call(["merge-base", "--is-ancestor", right, left])
            latest = left
        except subprocess.CalledProcessError:
            pass

    return latest

def git_return_base(left, right):
    """Try to get decide if "left" is based on "right" or vice-verse"""

    base = None
    try:
        git_call(["merge-base", "--is-ancestor", left, right])
        base = left
    except subprocess.CalledProcessError:
        try:
            git_call(["merge-base", "--is-ancestor", right, left])
            base = right
        except subprocess.CalledProcessError:
            pass

    return base
