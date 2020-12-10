"""Run tests inside mkt container
"""
import os
import utils
import subprocess

def args_test(parser):
    pass

def cmd_test(args):
    """Run test command."""
    from . import cmd_images
    section = utils.load_config_file()
    #test = section[test]

    try:
        subprocess.run(["/home/leonro/src/scripts/sf"], check=True)
    except subprocess.CalledProcessError:
        exit("TEST FAILED")

    print("TEST PASSED")
