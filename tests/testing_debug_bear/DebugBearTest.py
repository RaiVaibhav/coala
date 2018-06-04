import unittest
from coalib.bears.Bear import db, debug_mode_function
from io import StringIO

class DebugBearTest(unittest.TestCase):

    def test_debug_mode_function(self):
        # section = Section('name')
        args = {}
        kwargs = {}
        # my_bear = TestOneBear(section,self.queue, debug_flag=True)

        def fun(*args, **kwargs):
            yield 1
            yield 2

        something = StringIO
        input = something("q\nq\nq")
        output = StringIO()
        dbg = db(stdin=input ,stdout=output)
        dbg.do_q = dbg.do_continue
        self.assertEqual(debug_mode_function(fun, dbg, *args, **kwargs), [1,2])
        # import pdb; pdb.set_trace()
        my_output = output.getvalue()
        self.assertEqual(my_output.split('\n')[1], '-> yield 1')
        self.assertEqual(my_output.split('\n')[3], '-> yield 2')
        output.close()
        something().close()
