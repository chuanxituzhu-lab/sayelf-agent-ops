import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const project = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const publicRoot = resolve(project, "public/ocr");

async function copy(source, destination) {
  await mkdir(dirname(destination), { recursive: true });
  await copyFile(resolve(project, source), destination);
}

await copy("node_modules/tesseract.js/dist/worker.min.js", resolve(publicRoot, "worker.min.js"));
await copy("node_modules/tesseract.js-core/tesseract-core-lstm.js", resolve(publicRoot, "core/tesseract-core-lstm.js"));
await copy("node_modules/tesseract.js-core/tesseract-core-lstm.wasm", resolve(publicRoot, "core/tesseract-core-lstm.wasm"));
await copy("node_modules/@tesseract.js-data/chi_sim/4.0.0/chi_sim.traineddata.gz", resolve(publicRoot, "lang/chi_sim.traineddata.gz"));
await copy("node_modules/@tesseract.js-data/eng/4.0.0/eng.traineddata.gz", resolve(publicRoot, "lang/eng.traineddata.gz"));
