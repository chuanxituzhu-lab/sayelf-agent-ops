import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

let ocrWorkerPromise;
let pdfModulePromise;

async function loadPdfJs() {
  if (!pdfModulePromise) {
    pdfModulePromise = import("pdfjs-dist").then((module) => {
      module.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
      return module;
    }).catch((error) => {
      pdfModulePromise = undefined;
      throw error;
    });
  }
  return pdfModulePromise;
}

async function getOcrWorker(onProgress) {
  if (!ocrWorkerPromise) {
    ocrWorkerPromise = import("tesseract.js").then(({ default: Tesseract }) => Tesseract.createWorker("chi_sim+eng", 1, {
      workerPath: new URL("/ocr/worker.min.js", window.location.href).href,
      corePath: new URL("/ocr/core/tesseract-core-lstm.js", window.location.href).href,
      langPath: new URL("/ocr/lang/", window.location.href).href,
      gzip: true,
      logger: ({ status, progress }) => onProgress?.(status, progress),
    })).catch((error) => {
      ocrWorkerPromise = undefined;
      throw error;
    });
  }
  return ocrWorkerPromise;
}

async function recognize(bytes, onProgress) {
  const worker = await getOcrWorker(onProgress);
  return worker.recognize(bytes);
}

async function extractPdf(bytes, onProgress) {
  const pdfjs = await loadPdfJs();
  const document = await pdfjs.getDocument({ data: bytes }).promise;
  if (document.numPages > 40) throw new Error("PDF 超过 40 页，请拆分后再添加。");
  const chunks = [];
  let scannedPages = 0;
  let recognizedPages = 0;
  for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
    onProgress?.(`正在读取 PDF 第 ${pageNumber}/${document.numPages} 页…`);
    const page = await document.getPage(pageNumber);
    const textContent = await page.getTextContent();
    const pageText = textContent.items
      .map((item) => ("str" in item ? item.str : ""))
      .filter(Boolean)
      .join(" ")
      .trim();
    if (pageText) {
      chunks.push(pageText);
      continue;
    }
    scannedPages += 1;
    if (scannedPages > 12) {
      chunks.push(`[第 ${pageNumber} 页未识别：单个 PDF 最多离线识别 12 张扫描页]`);
      continue;
    }
    const viewport = page.getViewport({ scale: 1.5 });
    const canvas = document.createElement("canvas");
    canvas.width = Math.ceil(Math.min(viewport.width, 4000));
    canvas.height = Math.ceil(Math.min(viewport.height, 4000));
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("无法读取 PDF 页面图像。");
    const scale = Math.min(canvas.width / viewport.width, canvas.height / viewport.height, 1);
    const renderViewport = page.getViewport({ scale: 1.5 * scale });
    await page.render({ canvas, canvasContext: context, viewport: renderViewport }).promise;
    const result = await recognize(canvas, onProgress);
    const pageOcr = result.data.text.trim();
    if (pageOcr) {
      recognizedPages += 1;
      chunks.push(pageOcr);
    }
  }
  const extractedText = chunks.join("\n\n").trim();
  if (!extractedText) return { text: "", status: "未识别到文字" };
  if (scannedPages) {
    const limitNote = scannedPages > 12 ? "；超过 12 张的扫描页未识别" : "";
    return { text: extractedText, status: `PDF 文字已提取，扫描页识别 ${recognizedPages} 张${limitNote}` };
  }
  return { text: extractedText, status: "PDF 文字已提取" };
}

export async function extractEvidence(file, onProgress) {
  const bytes = file.bytes;
  const lowerName = file.name.toLocaleLowerCase();
  if (lowerName.endsWith(".txt") || lowerName.endsWith(".md")) {
    return { text: new TextDecoder("utf-8").decode(bytes).slice(0, 30000), status: "文字文件已读取" };
  }
  if (lowerName.endsWith(".pdf")) {
    const result = await extractPdf(bytes, onProgress);
    return { ...result, text: result.text.slice(0, 30000) };
  }
  onProgress?.(`正在离线识别图片「${file.name}」…`);
  const result = await recognize(bytes, onProgress);
  const text = result.data.text.trim().slice(0, 30000);
  const confidence = Number.isFinite(result.data.confidence) ? Math.round(result.data.confidence) : null;
  return {
    text,
    status: text ? `图片文字已识别${confidence === null ? "" : ` · 参考置信度 ${confidence}%`}` : "图片中未识别到文字",
  };
}
