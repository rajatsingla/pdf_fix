# pdf_fix

A small FastAPI service that normalises print-ready book PDFs — removing crop
marks, trimming whitespace, detecting and removing cover flaps, and resizing
covers/interiors to supported trim sizes. Bytes in, bytes out.

## Endpoints

- `POST /fix-cover?width_in=<w>&height_in=<h>` — fix and resize a cover PDF.
- `POST /fix-interior` — fix an interior (book block) PDF.
- `GET /health` — liveness check.
- `GET /source` — AGPL source offer (see License below).

The PDF is sent as the raw request body and returned as the raw response body.

## Run

```sh
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## License

This project is licensed under the **GNU Affero General Public License v3.0 or
later (AGPL-3.0-or-later)**. See [LICENSE](LICENSE) for the full text.

### Why AGPL

This service depends on [PyMuPDF](https://github.com/pymupdf/PyMuPDF), which is
distributed under the AGPL-3.0 (or a commercial license from Artifex). Because
`pdf_fix` imports and combines with PyMuPDF, the combined work is governed by
the AGPL, and this project is released under the same license accordingly.

### Network use and your obligations (AGPL §13)

The AGPL is a network-copyleft license. **If you run a modified version of this
software and let users interact with it over a network, you must offer those
users the complete corresponding source of your version.**

This service advertises its source in two ways so that obligation is met
automatically when deployed unmodified:

- a `GET /source` endpoint, and
- a `Link: <source-url>; rel="source"` header on every HTTP response.

If you deploy a **modified** version, set the `SOURCE_URL` environment variable
to a URL where *your* corresponding source can be obtained:

```sh
SOURCE_URL=https://example.com/your-fork uvicorn main:app ...
```

### Consuming this service from other code

A separate program (e.g. a frontend) that only calls these HTTP endpoints over
the network is not a derivative work of this service and is not bound by the
AGPL. The AGPL obligations apply to *this service's* source, operated by
whoever deploys it — not to independent network clients.

Source: https://github.com/rajatsingla/pdf_fix
