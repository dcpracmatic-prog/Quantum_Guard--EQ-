import unittest

from ddqpu.product_engine import (
    approximation_ratio, evaluate_product, path_cut, select_morph_path,
)


class ProductEngineTests(unittest.TestCase):
    def test_morph_selects_low_friction_connected_path(self):
        self.assertEqual(
            select_morph_path(3, [0.8, 0.1, 0.2, 0.9], [(0, 1), (1, 2), (2, 3)]),
            [1, 2, 3] if False else [0, 1, 2],
        )

    def test_cut_and_ratio(self):
        self.assertEqual(path_cut("0101", 4), 3)
        ar, se = approximation_ratio({"0101": 10}, 4)
        self.assertAlmostEqual(ar, 1.0)
        self.assertAlmostEqual(se, 0.0)

    def test_product_gate(self):
        result = evaluate_product(0.6927, 0.0061, 0.6387, 0.0061)
        self.assertEqual(result["veredicto"], "PRODUCTO_OK")
        self.assertAlmostEqual(result["delta_ar"], 0.054)

    def test_no_path_fails_closed(self):
        with self.assertRaises(ValueError):
            select_morph_path(3, [0.1, 0.2, 0.3], [(0, 1)])

    def test_invalid_counts_rejected(self):
        with self.assertRaises(ValueError):
            approximation_ratio({"010": -1}, 3)


if __name__ == "__main__":
    unittest.main()
