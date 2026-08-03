# rpdf

A small FastAPI service that normalises print-ready book PDFs — removing crop
marks, trimming whitespace, detecting and removing cover flaps, and resizing
covers/interiors to supported trim sizes. Bytes in, bytes out.

## Endpoints

- `POST /rpdf/covers?width_in=<w>&height_in=<h>` — fix and resize a cover PDF.
- `POST /rpdf/interiors?is_domestic=<bool>` — fix an interior (book block) PDF.
- `GET /rpdf/health` — liveness check.
- `GET /rpdf/source` — AGPL-3.0 source offer.
- `GET /rpdf` — the browser UI.

The PDF is sent as the raw request body and returned as the raw response body.

## Run

```sh
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## License

This project is licensed under the **GNU Affero General Public License v3.0 or
later (AGPL-3.0-or-later)**. See [LICENSE](LICENSE) for the full text.
