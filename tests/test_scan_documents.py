"""Behavioural tests; no scanner, credentials or network needed."""

import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from PIL import Image
import pymupdf

SPEC = importlib.util.spec_from_file_location(
    "scan_documents", Path(__file__).resolve().parents[1] / "lib" / "scan_documents.py"
)
scan = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scan
SPEC.loader.exec_module(scan)


def jpeg(dpi=None):
    stream = io.BytesIO()
    Image.new("RGB", (248, 351), "white").save(stream, "JPEG", **({"dpi": dpi} if dpi else {}))
    return stream.getvalue()


def status(state="Idle", feeder="ScannerAdfLoaded", job_state=None, completed=2, pending=0):
    job = ""
    if job_state:
        job = f"""<scan:Jobs><scan:JobInfo>
        <pwg:JobUri>/eSCL/ScanJobs/test</pwg:JobUri>
        <pwg:JobState>{job_state}</pwg:JobState>
        <pwg:ImagesCompleted>{completed}</pwg:ImagesCompleted>
        <pwg:ImagesToTransfer>{pending}</pwg:ImagesToTransfer>
        <pwg:JobStateReasons><pwg:JobStateReason>JobCompletedSuccessfully</pwg:JobStateReason></pwg:JobStateReasons>
        </scan:JobInfo></scan:Jobs>"""
    return f"""<scan:ScannerStatus xmlns:scan="{scan.SCAN_NS}" xmlns:pwg="{scan.PWG_NS}">
    <pwg:State>{state}</pwg:State><scan:AdfState>{feeder}</scan:AdfState>{job}</scan:ScannerStatus>""".encode()


def decision(page, *, blank=False, start=False, confidence=0.99, title="Invoice 123"):
    return scan.PageDecision(page=page, blank=blank, starts_document=start, title=title,
                             confidence=confidence, reason="Test classification")


def source_pdf(path, pages=4):
    with pymupdf.open() as document:
        for number in range(pages):
            page = document.new_page()
            if number != 1:
                page.insert_text((72, 72), f"Original page {number + 1}")
        document.save(path)


class RecoveryTests(unittest.TestCase):
    def test_raw_recovery_uses_saved_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            raw = run / "raw"
            raw.mkdir()
            for number in (1, 2):
                (raw / f"page-{number:04d}.jpg").write_bytes(jpeg())
            (run / "scan-job.json").write_text(json.dumps({"dpi": 600}))
            destination = run / "recovered.pdf"
            scan.import_original(raw, destination, dpi=100)
            with pymupdf.open(destination) as document:
                self.assertEqual(len(document), 2)
                self.assertAlmostEqual(document[0].rect.width, 248 * 72 / 600, places=4)

    def test_raw_recovery_prefers_embedded_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            raw = run / "raw"
            raw.mkdir()
            (raw / "page-0001.jpg").write_bytes(jpeg((200, 100)))
            (run / "scan-job.json").write_text(json.dumps({"dpi": 300}))
            destination = run / "recovered.pdf"
            scan.import_original(raw, destination)
            with pymupdf.open(destination) as document:
                self.assertAlmostEqual(document[0].rect.width, 248 * 72 / 200, places=4)
                self.assertAlmostEqual(document[0].rect.height, 351 * 72 / 100, places=4)

    def test_invalid_embedded_resolution_falls_back(self):
        image = Image.new("RGB", (1, 1))
        for value in (None, (0, 300), (-1, 300), (float("nan"), 300),
                      (float("inf"), 300), ("300", 300), (True, 300), (300,)):
            image.info["dpi"] = value
            self.assertIsNone(scan.embedded_dpi(image))

    def test_raw_recovery_rejects_gaps_and_incomplete_downloads(self):
        for extra, message in [("page-0003.jpg", "consecutive"),
                               ("page-0002.jpg.partial", "incomplete")]:
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                run = Path(directory)
                raw = run / "raw"
                raw.mkdir()
                (raw / "page-0001.jpg").write_bytes(jpeg())
                (raw / extra).write_bytes(jpeg())
                destination = run / "recovered.pdf"
                with self.assertRaisesRegex(scan.ScanError, message):
                    scan.import_original(raw, destination)
                self.assertFalse(destination.exists())


class CaptureTests(unittest.TestCase):
    def run_capture(self, run, reply_codes, final_status=None):
        codes = iter(reply_codes)
        self.deleted = []
        self.posts = 0

        def handle(request):
            if request.method == "POST":
                self.posts += 1
                self.assertEqual(request.headers["Content-Type"], "text/xml; charset=utf-8")
                self.assertEqual(request.content, scan.scan_settings("a4", 300))
                settings = scan.parse_xml(request.content)
                self.assertEqual(settings.findtext("scan:Duplex", namespaces=scan.NS), "true")
                self.assertEqual(settings.findtext("pwg:InputSource", namespaces=scan.NS), "Feeder")
                return httpx.Response(201, headers={"Location": "/eSCL/ScanJobs/test"})
            if request.method == "DELETE":
                self.deleted.append(str(request.url))
                return httpx.Response(200)
            if request.url.path.endswith("ScannerStatus"):
                return httpx.Response(200, content=status() if self.posts == 0 else final_status or status(job_state="Completed"))
            code = next(codes)
            if isinstance(code, httpx.SyncByteStream):
                return httpx.Response(200, stream=code)
            return httpx.Response(code, content=jpeg() if code == 200 else b"")

        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            with patch.object(scan, "check_capabilities"), patch.object(scan.time, "sleep"):
                return scan.capture(client, "http://scanner/eSCL", run, "a4", 300)

    def test_duplex_scan_preserves_both_sides_and_cleans_own_job(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            pages = self.run_capture(run, [200, 200, 404])
            self.assertEqual([page.name for page in pages], ["page-0001.jpg", "page-0002.jpg"])
            self.assertTrue(all(page.read_bytes() == jpeg() for page in pages))
            self.assertEqual(self.posts, 1)
            self.assertEqual(self.deleted, ["http://scanner/eSCL/ScanJobs/test"])

    def test_transient_unavailable_is_retried_without_resubmitting_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(scan, "check_job", side_effect=[False, True]):
                pages = self.run_capture(Path(directory), [503, 200, 200, 410])
            self.assertEqual(len(pages), 2)
            self.assertEqual(self.posts, 1)

    def test_mid_body_read_error_retains_received_bytes_and_previous_side(self):
        class BrokenBody(httpx.SyncByteStream):
            def __iter__(self):
                yield jpeg()[:500]
                raise httpx.ReadError("connection lost mid-page")

        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            with self.assertRaises(httpx.ReadError):
                self.run_capture(run, [200, BrokenBody()])
            self.assertEqual((run / "raw/page-0001.jpg").read_bytes(), jpeg())
            self.assertEqual((run / "raw/page-0002.jpg.partial").read_bytes(), jpeg()[:500])
            self.assertFalse((run / "raw/page-0002.jpg").exists())
            self.assertEqual(len(self.deleted), 1)

    def test_ignored_resolution_retains_partial_and_stops(self):
        class WrongResolution(httpx.SyncByteStream):
            def __iter__(self):
                yield jpeg((200, 200))

        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            with self.assertRaisesRegex(scan.ScanError, "ignored the duplex settings"):
                self.run_capture(run, [200, WrongResolution()])
            self.assertTrue((run / "raw/page-0001.jpg").exists())
            self.assertEqual((run / "raw/page-0002.jpg.partial").read_bytes(), jpeg((200, 200)))
            self.assertFalse((run / "raw/page-0002.jpg").exists())
            self.assertEqual(len(self.deleted), 1)

    def test_damaged_download_remains_partial(self):
        class DamagedBody(httpx.SyncByteStream):
            def __iter__(self):
                yield jpeg()[:500]

        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            with self.assertRaisesRegex(scan.ScanError, "damaged page"):
                self.run_capture(run, [DamagedBody()])
            self.assertEqual((run / "raw/page-0001.jpg.partial").read_bytes(), jpeg()[:500])
            self.assertFalse((run / "raw/page-0001.jpg").exists())

    def test_jam_retains_partial_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            with self.assertRaisesRegex(scan.ScanError, "ScannerAdfJam"):
                self.run_capture(run, [200, 503], status(feeder="ScannerAdfJam", job_state="Aborted"))
            self.assertTrue((run / "raw/page-0001.jpg").exists())
            self.assertEqual(len(self.deleted), 1)

    def test_missing_completion_is_not_treated_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(scan.ScanError, "did not confirm completion"):
                self.run_capture(Path(directory), [200] + [404] * 30, status(job_state="Processing"))

    def test_missing_sides_are_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(scan.ScanError, "reports 4 pages"):
                self.run_capture(Path(directory), [200, 200, 404], status(job_state="Completed", completed=4))

    def test_scanner_busy_does_not_start_job(self):
        with tempfile.TemporaryDirectory() as directory:
            with httpx.Client(transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, content=status(state="Processing")))) as client:
                with patch.object(scan, "check_capabilities"):
                    with self.assertRaisesRegex(scan.ScanError, "not ready"):
                        scan.capture(client, "http://scanner/eSCL", Path(directory), "a4", 300)

    def test_post_timeout_is_not_retried(self):
        posts = []

        def handle(request):
            if request.method == "POST":
                posts.append(request)
                raise httpx.ReadTimeout("lost reply", request=request)
            return httpx.Response(200, content=status())

        with tempfile.TemporaryDirectory() as directory:
            with httpx.Client(transport=httpx.MockTransport(handle)) as client:
                with patch.object(scan, "check_capabilities"):
                    with self.assertRaises(httpx.ReadTimeout):
                        scan.capture(client, "http://scanner/eSCL", Path(directory), "a4", 300)
        self.assertEqual(len(posts), 1)

    def test_untrusted_job_location_is_rejected(self):
        for location in ["http://evil/eSCL/ScanJobs/x", "//evil/job", "/admin", ""]:
            with self.subTest(location=location), self.assertRaises(scan.ScanError):
                scan.job_url("http://scanner/eSCL", location)

    def test_settings_match_tested_brother_request(self):
        fixture = Path(__file__).parent / "fixtures" / "brother-scan-settings.xml"
        self.assertEqual(scan.scan_settings("a4", 300), fixture.read_bytes())

    def test_settings_retain_paper_sizes_and_reject_unvalidated_values(self):
        for size, (width, height) in scan.SIZES.items():
            root = scan.parse_xml(scan.scan_settings(size, 200))
            region = root.find("pwg:ScanRegions/pwg:ScanRegion", scan.NS)
            self.assertEqual(region.findtext("pwg:Width", namespaces=scan.NS), str(width))
            self.assertEqual(region.findtext("pwg:Height", namespaces=scan.NS), str(height))
            self.assertEqual(root.findtext("scan:YResolution", namespaces=scan.NS), "200")
        for size, dpi in (("a3", 300), ("a4", "300"), ("a4", True), ("a4", 301)):
            with self.assertRaises(scan.ScanError):
                scan.scan_settings(size, dpi)

    def test_settings_use_fixed_units_at_all_resolutions(self):
        for dpi in (100, 300, 600):
            root = scan.parse_xml(scan.scan_settings("a4", dpi))
            self.assertEqual(root.findtext("pwg:ScanRegions/pwg:ScanRegion/pwg:Width", namespaces=scan.NS), "2480")
            self.assertEqual(root.findtext("scan:XResolution", namespaces=scan.NS), str(dpi))


class SplittingTests(unittest.TestCase):
    def test_blank_back_does_not_split_multipage_document(self):
        analysis = scan.Analysis(pages=[decision(1, start=True), decision(2, blank=True),
                                        decision(3), decision(4, start=True, title="Letter")])
        groups, blanks = scan.group_pages(analysis, [0.1, 0, 0.1, 0.1], False)
        self.assertEqual([group["pages"] for group in groups], [[1, 3], [4]])
        self.assertEqual([blank["page"] for blank in blanks], [2])

    def test_sparse_text_is_retained_and_uncertain_blank_is_flagged(self):
        analysis = scan.Analysis(pages=[decision(1, start=True), decision(2, confidence=0.9),
                                        decision(3, blank=True, confidence=0.8)])
        groups, blanks = scan.group_pages(analysis, [0.1, 0.00001, 0], False)
        self.assertEqual(groups[0]["pages"], [1, 2, 3])
        self.assertTrue(groups[0]["needs_review"])
        self.assertEqual(blanks, [])

    def test_dark_content_cannot_be_removed_even_if_ai_calls_it_blank(self):
        groups, blanks = scan.group_pages(scan.Analysis(pages=[decision(1, blank=True)]), [0.3], False)
        self.assertEqual(groups[0]["pages"], [1])
        self.assertTrue(groups[0]["needs_review"])
        self.assertEqual(blanks, [])

    def test_keep_blank_pages_retains_every_side_including_leading_blanks(self):
        analysis = scan.Analysis(pages=[decision(1, blank=True), decision(2, start=True),
                                        decision(3, blank=True), decision(4, start=True)])
        groups, blanks = scan.group_pages(analysis, [0, 0.1, 0, 0.1], True)
        self.assertEqual([group["pages"] for group in groups], [[1, 2, 3], [4]])
        self.assertEqual(blanks, [])

    def test_all_blank_batch_has_no_empty_pdf(self):
        analysis = scan.Analysis(pages=[decision(1, blank=True), decision(2, blank=True)])
        groups, blanks = scan.group_pages(analysis, [0, 0], False)
        self.assertEqual(groups, [])
        self.assertEqual(len(blanks), 2)
        groups, blanks = scan.group_pages(analysis, [0, 0], True)
        self.assertEqual(groups[0]["pages"], [1, 2])

    def test_missing_repeated_reordered_and_hallucinated_pages_are_rejected(self):
        for numbers in ([1], [1, 1], [2, 1], [1, 3], [1, 2, 3]):
            with self.subTest(numbers=numbers), self.assertRaises(scan.ScanError):
                scan.validate_analysis(scan.Analysis(pages=[decision(n) for n in numbers]), 2)

    def test_invalid_types_and_confidence_are_rejected(self):
        for field, value in [("page", True), ("page", "1"), ("blank", "false"),
                             ("confidence", float("nan")), ("confidence", 1.1)]:
            data = decision(1).model_dump()
            data[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                scan.PageDecision.model_validate(data)

    def test_titles_are_safe_and_ascii(self):
        for title in ["../../tax; echo secret", "..", "a" * 200, "\u00a3 Tax \u2014 2026"]:
            name = scan.safe_title(title)
            self.assertRegex(name, r"^[a-zA-Z0-9-]+$")
            self.assertLessEqual(len(name), 90)
            self.assertTrue(name.isascii())

    def test_export_preserves_original_page_content_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            original = run / "original.pdf"
            source_pdf(original)
            original_bytes = original.read_bytes()
            analysis = scan.Analysis(pages=[decision(1, start=True), decision(2, blank=True),
                                            decision(3), decision(4, start=True)])
            manifest = scan.export_documents(original, run, analysis, [0.1, 0, 0.1, 0.1], "test", False)
            with pymupdf.open(run / manifest["documents"][0]["file"]) as document:
                self.assertEqual(document.page_count, 2)
                self.assertIn("Original page 1", document[0].get_text())
                self.assertIn("Original page 3", document[1].get_text())
            self.assertEqual(original.read_bytes(), original_bytes)
            with self.assertRaises(FileExistsError):
                scan.export_documents(original, run, analysis, [0.1, 0, 0.1, 0.1], "test", False)

    def test_empty_and_encrypted_pdf_are_not_sent_to_ai(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            original = run / "original.pdf"
            with pymupdf.open() as doc:
                doc.new_page()
                doc.save(original, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="test")
            with patch.object(scan, "OpenAI") as client:
                with self.assertRaisesRegex(scan.ScanError, "unencrypted"):
                    scan.analyse(original, "test", "fake", run)
                client.assert_not_called()

    def test_api_failure_preserves_original_and_recovery_information(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            source_pdf(source)
            with patch.object(scan, "api_key", return_value="fake"), \
                    patch.object(scan, "analyse", side_effect=scan.ScanError("Test API failure")):
                code = scan.main(["--input", str(source), "--output", str(root / "output")])
            self.assertEqual(code, 1)
            run = next((root / "output").iterdir())
            self.assertEqual((run / "original.pdf").read_bytes(), source.read_bytes())
            self.assertEqual(json.loads((run / "error.json").read_text())["status"], "failed")
            self.assertFalse((run / "documents").exists())

    def test_scan_only_import_does_not_access_scanner_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            source_pdf(source)
            with patch.object(scan, "api_key") as key, patch.object(scan, "capture") as capture:
                for _ in range(2):
                    self.assertEqual(scan.main(["--input", str(source), "--scan-only", "--output", str(root / "out")]), 0)
                key.assert_not_called()
                capture.assert_not_called()
            runs = list((root / "out").iterdir())
            self.assertEqual(len(runs), 2)
            self.assertTrue(all(run.stat().st_mode & 0o077 == 0 for run in runs))


if __name__ == "__main__":
    unittest.main()
