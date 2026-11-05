import unittest

from tests.fixtures import png, webp_lossless
from avatars import png as png_mod
from avatars import webp as webp_mod


class PngTest(unittest.TestCase):
    def test_png_clean_passes(self):
        self.assertEqual(png_mod.check(png(4, 3, [(b"sRGB", b"\x00")])), [])

    def test_png_rejects_text(self):
        for kind in (b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"caBX", b"iCCP"):
            with self.subTest(kind=kind):
                problems = png_mod.check(png(4, 3, [(kind, b"Software\x00x")]))
                self.assertEqual(len(problems), 1)
                self.assertIn(kind.decode(), problems[0])

    def test_png_strip_removes_disallowed_and_passes_check(self):
        dirty = png(4, 3, [(b"tEXt", b"a\x00b"), (b"pHYs", b"\x00" * 9), (b"iCCP", b"p\x00\x00x")])
        clean = png_mod.strip(dirty)
        self.assertEqual(png_mod.check(clean), [])
        self.assertEqual([k for k, _ in png_mod.chunks(clean)], [b"IHDR", b"pHYs", b"IDAT", b"IEND"])
        self.assertEqual(clean, png(4, 3, [(b"pHYs", b"\x00" * 9)]))

    def test_png_size(self):
        self.assertEqual(png_mod.size(png(7, 5)), (7, 5))

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            png_mod.chunks(b"not a png")
        with self.assertRaises(ValueError):
            png_mod.chunks(png(1, 1)[:-3])


class WebpTest(unittest.TestCase):
    def test_webp_clean_passes(self):
        self.assertEqual(webp_mod.check(webp_lossless(4, 3)), [])
        self.assertEqual(webp_mod.check(webp_lossless(4, 3, vp8x_flags=0x10)), [])

    def test_webp_rejects_metadata(self):
        for kind in (b"EXIF", b"XMP ", b"ICCP"):
            with self.subTest(kind=kind):
                problems = webp_mod.check(webp_lossless(4, 3, [(kind, b"abc")], vp8x_flags=0))
                self.assertEqual(len(problems), 1)
                self.assertIn(kind.decode().strip(), problems[0])

    def test_webp_strip_removes_and_passes_check(self):
        dirty = webp_lossless(4, 3, [(b"EXIF", b"abc"), (b"XMP ", b"<x/>")], vp8x_flags=0x0C)
        clean = webp_mod.strip(dirty)
        self.assertEqual(webp_mod.check(clean), [])
        self.assertEqual([k for k, _ in webp_mod.chunks(clean)], [b"VP8X", b"VP8L"])
        self.assertEqual(clean, webp_lossless(4, 3, vp8x_flags=0))

    def test_strip_webp_clears_vp8x_flags(self):
        dirty = webp_lossless(4, 3, [(b"ICCP", b"p")], vp8x_flags=0x20 | 0x08 | 0x04 | 0x10)
        clean = webp_mod.strip(dirty)
        vp8x = dict(webp_mod.chunks(clean))[b"VP8X"]
        self.assertEqual(vp8x[0], 0x10)

    def test_webp_size_vp8x_and_vp8l(self):
        self.assertEqual(webp_mod.size(webp_lossless(9, 6)), (9, 6))
        self.assertEqual(webp_mod.size(webp_lossless(9, 6, vp8x_flags=0)), (9, 6))

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            webp_mod.chunks(b"RIFF\x00\x00\x00\x00WEBX")
        with self.assertRaises(ValueError):
            webp_mod.chunks(webp_lossless(2, 2)[:-4])


if __name__ == "__main__":
    unittest.main()
