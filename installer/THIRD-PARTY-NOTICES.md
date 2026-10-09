# Third-party notices

The desktop installer includes locally bundled PDF and OCR assets. These assets are used offline; user documents and OCR text are not sent to these projects or services.

| Component | Version | License and source |
| --- | --- | --- |
| PDF.js (`pdfjs-dist`) | 6.3.289 | Apache-2.0; Mozilla PDF.js project |
| Tesseract.js | 7.0.0 | Apache-2.0; Naptha |
| Tesseract.js Core | 7.0.0 | Apache-2.0; Naptha |
| Simplified Chinese model (`@tesseract.js-data/chi_sim`) | 1.0.0 | npm package metadata declares MIT; the upstream `naptha/tessdata` repository declares Apache-2.0. Both notices are included pending clarification of this discrepancy. |
| English model (`@tesseract.js-data/eng`) | 1.0.0 | npm package metadata declares MIT; the upstream `naptha/tessdata` repository declares Apache-2.0. Both notices are included pending clarification of this discrepancy. |

Full license texts are in the adjacent `licenses` folder. Exact dependency versions are pinned in `desktop/tauri/package-lock.json`. The model assets are copied from the pinned npm packages during the local build and are not committed to this repository.

Sources: [PDF.js](https://github.com/mozilla/pdf.js), [Tesseract.js](https://github.com/naptha/tesseract.js), [tessdata repository](https://github.com/naptha/tessdata), [Simplified Chinese model package](https://www.npmjs.com/package/%40tesseract.js-data/chi_sim), and [English model package](https://www.npmjs.com/package/%40tesseract.js-data/eng).
