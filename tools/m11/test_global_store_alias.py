#!/usr/bin/env python3
"""m11_global_store_alias の判定の負例・正例 (#5449 / M11-N244). 実行: python3 test_global_store_alias.py"""
import collections, os, subprocess, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, 'fixtures', 'alias_probe.ll')
CHECKER = os.path.join(HERE, 'm11_global_store_alias.py')


def run_counts(ir):
    out = subprocess.run([sys.executable, CHECKER, ir, '--va', '0x15e3a70', '--span', '8'],
                         capture_output=True, text=True, check=True).stdout
    counts = collections.Counter()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            counts[parts[0]] = int(parts[1])
    return counts


class GlobalStoreAliasTest(unittest.TestCase):
    def test_probe_fixture_counts(self):
        c = run_counts(FIXTURE)
        self.assertEqual(c['va_hit'], 6)
        self.assertEqual(c['const_other'], 1)
        self.assertEqual(c['const_var_offset'], 1)
        self.assertEqual(c['alloca'], 1)


if __name__ == '__main__':
    unittest.main()
