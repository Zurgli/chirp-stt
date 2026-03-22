import unittest

from chirp.recording_overlay import compute_top_center_geometry


class TestRecordingOverlay(unittest.TestCase):
    def test_compute_top_center_geometry(self):
        geometry = compute_top_center_geometry(1920, width=280, height=42, top_margin=16)
        self.assertEqual(geometry.width, 280)
        self.assertEqual(geometry.height, 42)
        self.assertEqual(geometry.x, 820)
        self.assertEqual(geometry.y, 16)

    def test_compute_top_center_geometry_clamps_x(self):
        geometry = compute_top_center_geometry(200, width=280, height=42, top_margin=16)
        self.assertEqual(geometry.x, 0)
        self.assertEqual(geometry.y, 16)


if __name__ == "__main__":
    unittest.main()
