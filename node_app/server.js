// Minimal Express app that serves the UI and proxies raw PDF bytes to the
// FastAPI PDF-fix service. Browser -> Node (raw body) -> FastAPI -> back.
//
// Env:
//   PORT          (default 3000)        port this app listens on
//   PDF_API_URL   (default http://127.0.0.1:8000)  base URL of the FastAPI service

const path = require("path");
const express = require("express");

const PORT = process.env.PORT || 3000;
const PDF_API_URL = "http://64.227.150.124:8181";

const app = express();

app.use(express.static(path.join(__dirname, "public")));

// Accept raw PDF bytes for the proxy routes (large enough for print PDFs).
const rawPdf = express.raw({ type: "*/*", limit: "300mb" });

// type = "cover" | "interior". Cover also needs width_in & height_in query params.
app.post("/api/fix", rawPdf, async (req, res) => {
  try {
    const type = req.query.type;

    if (!req.body || req.body.length === 0) {
      return res.status(400).json({ error: "empty request body" });
    }

    let target;
    if (type === "cover") {
      const { width_in, height_in } = req.query;
      if (!width_in || !height_in) {
        return res
          .status(400)
          .json({ error: "width_in and height_in are required for cover" });
      }
      target = `${PDF_API_URL}/fix-cover?width_in=${encodeURIComponent(
        width_in,
      )}&height_in=${encodeURIComponent(height_in)}`;
    } else if (type === "interior") {
      target = `${PDF_API_URL}/fix-interior`;
    } else {
      return res
        .status(400)
        .json({ error: 'type must be "cover" or "interior"' });
    }

    const upstream = await fetch(target, {
      method: "POST",
      headers: { "Content-Type": "application/pdf" },
      body: req.body,
    });

    const buf = Buffer.from(await upstream.arrayBuffer());

    if (!upstream.ok) {
      // FastAPI returns JSON like {"detail": "..."} on error.
      let detail = buf.toString("utf8");
      try {
        detail = JSON.parse(detail).detail || detail;
      } catch (_) {
        /* keep raw text */
      }
      return res.status(upstream.status).json({ error: detail });
    }

    res.set("Content-Type", "application/pdf");
    return res.send(buf);
  } catch (err) {
    return res
      .status(502)
      .json({ error: `could not reach PDF service: ${err.message}` });
  }
});

app.listen(PORT, () => {
  console.log(
    `pdf-fix UI on http://127.0.0.1:${PORT}  (proxying to ${PDF_API_URL})`,
  );
});
