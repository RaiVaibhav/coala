import multiprocessing
import unittest
import sys

from io import StringIO

from coalib.bears.Bear import Bear, Debugger, debug_run
from coalib.bears.LocalBear import LocalBear
from coalib.settings.Section import Section


class TestOneBear(LocalBear):
    def __init__(self, section, queue, timeout=0.1, debugger=False):
        Bear.__init__(self, section, queue, timeout, debugger)

    def run(self, filename, file, x: int, y: str, z: int = 79, w: str = 'kbc'):
        yield 1
        yield 2


def func1(*args, **kwargs):
    yield 1
    yield 2
    yield 3


def func2(*args, **kwargs):
    return([1, 2])


def func3(*args, **kwargs):
    return func1(*args, **kwargs)


def execute_debugger(debugger_commands, func, *args, **kwargs):
    input = StringIO('\n'.join(debugger_commands))
    output = StringIO()
    dbg = Debugger(stdin=input, stdout=output)
    return debug_run(func, dbg, *args, **kwargs), output.getvalue()


class DebugBearsTest(unittest.TestCase):
    def setUp(self):
        # restore the coverage settrace to prevent the coverage breakage
        # on project because  we can't chain coverage trace to run parallel
        # with debugger. To increase the coverage Mock test has been added in
        # BearTest file.
        # https://goo.gl/sKaJfh
        self.trace = sys.gettrace()
        self.queue = multiprocessing.Queue()
        self.section = Section('name')

    def tearDown(self):
        sys.settrace(self.trace)

    def test_run_return_yield_with_debugger(self):
        args = ('a', ('b', 'c'))
        kwargs = {'d': 'e'}
        result, output = execute_debugger('qcqc', func1, *args, **kwargs)
        self.assertEqual(result, [1, 2, 3])
        lines = output.splitlines()
        self.assertEqual(lines[1], '-> yield 1')
        self.assertEqual(lines[3], '-> yield 2')
        self.assertEqual(lines[5], '-> yield 3')

    def test_run_return_list_with_debugger(self):
        args = ('a', ('b', 'c'))
        kwargs = {'d': 'e'}
        result, output = execute_debugger('qc', func2, *args, **kwargs)
        self.assertEqual(result, [1, 2])
        lines = output.splitlines()
        self.assertEqual(lines[1], '-> return([1, 2])')

    def test_run_return_generator_with_debugger(self):
        args = ('a', ('b', 'c'))
        kwargs = {'d': 'e'}
        result, output = execute_debugger('qcqcqc', func3, *args, **kwargs)
        self.assertEqual(result, [1, 2, 3])
        lines = output.splitlines()
        self.assertEqual(lines[3], '-> yield 1')
        self.assertEqual(lines[5], '-> yield 2')
        self.assertEqual(lines[7], '-> yield 3')

    def test_do_initialize(self):
        my_bear = TestOneBear(self.section, self.queue)
        args = ('a', ('b', 'c'))
        kwargs = {'x': 2, 'y': 'abc'}
        result, output = execute_debugger(['settings', 'q', 'c', 'q'],
                                          my_bear.run, *args, **kwargs)
        lines = output.splitlines()
        self.assertEqual(lines[2], '(Pdb) x = 2')
        self.assertEqual(lines[3], "y = 'abc'")
        self.assertEqual(lines[4], 'z = 79')
        self.assertEqual(lines[5], "w = 'kbc'")
