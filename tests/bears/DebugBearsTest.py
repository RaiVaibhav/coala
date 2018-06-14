import unittest
from io import StringIO
from coalib.bears.Bear import db, debug_run


class DebugBearsTest(unittest.TestCase):

    def test_debug_run(self):
        args = ('a', ('b', 'c'))
        kwargs = {'d': 'e'}

        def fun(*args, **kwargs):
            yield 1
            yield 2
            yield 3

        input = StringIO('q\nc\nq\nc')
        output = StringIO()
        dbg = db(stdin=input, stdout=output)
        dbg.do_q = dbg.do_continue
        self.assertEqual(debug_run(fun, dbg, *args, **kwargs), [1, 2, 3])
        output = output.getvalue()
        self.assertEqual(output.split('\n')[1], '-> yield 1')
        self.assertEqual(output.split('\n')[3], '-> yield 2')
        self.assertEqual(output.split('\n')[5], '-> yield 3')
