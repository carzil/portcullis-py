import unittest
from unittest.mock import MagicMock
from portcullis.matchers import Matcher


class TestMatcherCreationError(unittest.TestCase):
    def test_incomplete_upper_matcher(self):
        conf = {"upper": {"upper": {}}}
        with self.assertRaises(ValueError):
            Matcher.from_yaml(conf)

    def test_upper_matcher(self):
        conf = {"upper": {"match_regex": {"regex": "ADMIN"}}}
        matcher = Matcher.from_yaml(conf)
        mock = MagicMock()
        mock.upper.return_value = "ADMIN"
        self.assertTrue(matcher.is_match(mock))
        mock.upper.assert_called_once_with()

    def test_incomplete_lower_matcher(self):
        conf = {"lower": {"lower": {}}}
        with self.assertRaises(ValueError):
            Matcher.from_yaml(conf)

    def test_upper_matcher(self):
        conf = {"lower": {"match_regex": {"regex": "admin"}}}
        matcher = Matcher.from_yaml(conf)
        mock = MagicMock()
        mock.lower.return_value = "admin"
        self.assertTrue(matcher.is_match(mock))
        mock.lower.assert_called_once_with()
