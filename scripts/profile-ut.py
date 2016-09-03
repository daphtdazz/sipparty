#!/usr/bin/env python
import argparse
import re
import sys
from unittest import TestLoader, TestResult, TestSuite

import cProfile


def filtered_tests(suite, cond_func):
    for test_or_suite in suite:
        if isinstance(test_or_suite, TestSuite):
            for tst in filtered_tests(test_or_suite, cond_func):
                yield tst
        else:
            if cond_func(test_or_suite):
                yield test_or_suite


def main():

    ap = argparse.ArgumentParser()
    ap.add_argument('pattern')
    ap.add_argument(
        '-c', '--cprofile', dest='cprofile', default=False,
        action='store_true')
    args = ap.parse_args()
    pattern = args.pattern
    do_cp = args.cprofile

    tl = TestLoader()
    tr = TestResult()
    all_suite = tl.discover(start_dir='.', pattern='*.py')

    tre = re.compile(pattern, re.IGNORECASE)

    tests = [
        ts for ts in filtered_tests(
            all_suite, lambda test: tre.search('.'.join((
                test.__module__, test._testMethodName))))]

    filtered_suite = TestSuite()
    filtered_suite.addTests(tests)

    if do_cp:
        cp = cProfile.Profile()
        cp.enable()
        filtered_suite.run(tr)
        cp.disable()
        cp.create_stats()
        cp.print_stats(sort=1)
    else:
        filtered_suite.run(tr)

    print(tr)
    return len(tr.errors)


if __name__ == '__main__':
    sys.exit(main())

