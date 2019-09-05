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
