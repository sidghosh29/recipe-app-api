"""
Sample Tests for Calculator Functions
"""

from django.test import SimpleTestCase
from . import calc


class CalcTests(SimpleTestCase):
    """Tests for calculator functions."""

    def test_add_numbers(self):
        """Test adding two numbers together."""
        res = calc.add(5, 6)

        self.assertEqual(res, 11)

    def test_subtract(self):
        """Test subtracting two numbers."""
        res = calc.subtract(10, 4)

        self.assertEqual(res, 6)
