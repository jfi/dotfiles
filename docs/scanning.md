# Scanning documents

`scan-documents` scans the loaded Brother MFC-J5740DW feeder in duplex, asks OpenAI
to recognise document boundaries and blank sides, and saves separate named PDFs.
It uses the scanner's eSCL network interface, so no scanning application or driver
installation is needed. The Mac and scanner must be on the same network.

## Run

Load the stack in the automatic document feeder, then run:

```bash
scan-documents
```

The defaults are A4, colour, 300 dpi, both sides, and a new batch folder inside
`~/Documents/Scans`. Use the feeder's normal paper orientation and keep pages in
document order. No separator sheets are necessary. Each run creates a unique
folder and preserves the original scan.

```text
2026-09-12_143000-example/
  original.pdf
  raw/page-0001.jpg
  raw/page-0002.jpg
  scan-job.json
  analysis.json
  manifest.json
  documents/001-supplier-invoice-123.pdf
  documents/002-letter.pdf
```

`manifest.json` records the original page numbers in each document, removed blank
sides, and uncertain decisions that need checking. A blank back does not imply a
document boundary. Blank removal requires a highly confident AI decision and a
low dark-pixel fraction; uncertain or visibly marked pages are retained.

## Credentials and privacy

The command requires `uv`, already included in the Brewfile. It downloads its
Python dependencies into the uv cache on first use.

It uses `OPENAI_API_KEY` if set. Otherwise it reads `op://AI/OpenAI/api_key` through
the 1Password CLI. Unlock 1Password if prompted. Keys are never saved in the scan
folder or printed.

Page previews are sent to the OpenAI API for recognition and naming, using
`gpt-4.1-mini` by default. API usage is billed to your OpenAI account separately
from a ChatGPT subscription. The request uses `store=False`; this does not override
OpenAI's API data retention policies. Local batch folders are private to your user.

The PDFs preserve the original page images; they are not OCR-searchable. AI
recognition can misidentify boundaries or faint marks, so keep `original.pdf` until
you have checked the output. The original is never changed by splitting.

## Options

Check whether the scanner is ready, without moving any paper:

```bash
scan-documents --status
```

Save the whole scan without using AI:

```bash
scan-documents --scan-only
```

Reprocess an existing scan without feeding it through again:

```bash
scan-documents --input ~/Documents/Scans/previous-batch/original.pdf
```

Choose an output location, paper size, or preserve all blank sides:

```bash
scan-documents --output ~/Documents/Invoices --size letter
scan-documents --input batch.pdf --keep-blank-pages
```

Change the scanner or vision model for a run:

```bash
scan-documents --scanner http://scanner.local/eSCL --model gpt-4.1-mini
```

`SCAN_DOCUMENTS_SCANNER` and `SCAN_DOCUMENTS_MODEL` set persistent defaults when
exported from your local shell configuration. Supported sizes are `a4`, `letter`
and `legal`; supported resolutions are 100, 200, 300 and 600 dpi, subject to the
scanner's advertised duplex capabilities. Choose the correct size to avoid cropping
larger pages. Scan mixed paper sizes in separate batches.

## Recovery

A jam, timeout, incomplete scan or invalid AI response exits with an error and
retains any captured files. `error.json` records the problem. The command checks
the scanner's matching job status and page count before declaring a scan complete.
It does not restart a scan automatically after a network failure.

If `original.pdf` exists, use `--input` to retry recognition. If a physical scan
failed, recover its saved sides with `scan-documents --input previous-batch/raw`.
The saved job supplies the original resolution. Interrupted or damaged downloads
remain as `.jpg.partial` files; raw-folder recovery refuses these so an incomplete
side cannot silently disappear. Check the saved images and rescan missing sides
before recovering the complete consecutive JPEG files. Keep the failed batch.
A failed POST can still start the feeder even when its reply is lost; check the
scanner before starting another run.

AI analysis is limited to 80 sides per batch. Larger scans are preserved intact
but not submitted to AI; use smaller input PDFs for recognition. The scanner is
never silently stopped at the AI limit. Completion and page accounting checks
protect against software omissions, but cannot detect two sheets fed together by
the hardware.

## Development checks

```bash
uv run --with 'httpx>=0.28,<1' --with 'openai>=2,<3' \
  --with 'pillow>=11,<13' --with 'pymupdf>=1.26,<2' \
  python -m unittest discover -s tests -p 'test_scan_documents.py'
hk run pre-commit
```

The tests use a simulated scanner and synthetic PDFs, without accessing credentials
or sending page content to an AI provider.

Protocol and API references:

- [sane-airscan eSCL implementation](https://github.com/alexpevzner/sane-airscan/blob/master/airscan-escl.c)
- [OpenAI image inputs](https://developers.openai.com/api/docs/guides/images-vision)
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
