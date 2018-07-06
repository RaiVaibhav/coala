import unittest

from coalib.core.PersistentHash import persistent_hash


class PersistentHashTest(unittest.TestCase):

    def test_int(self):
        try:
            self.assertEqual(
                persistent_hash(3),
                b'\xd8YA\x03x|c"@\xe8\x8b~\xb9\xb6\x8d\x95\x8dzp\x8a')
        # Exception has be handeled because of changes in python3.7 digets()
        # method and also made test work for all the version of python.
        except AssertionError:
            self.assertEqual(
                persistent_hash(3),
                b'\xf9\x85\xb9\x15H\xa0\x8f\xb7;\xb3\xa8\xc3\x82'
                b'\xa3\xe8\xe0!\xf7\xfc\xfc')

    def test_int_tuples(self):
        self.assertEqual(
            persistent_hash((1, 2, 3)),
            b'\xb5\xd6\xd7\xbeLD\x90\x9fz.\xae\xc4\xb9P\n\xf8\xf5\x03S\xb6')
