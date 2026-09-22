import React, { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { readBlobBuffer } from '@/lib/billDocuments';

// Canvas rendering works inside Android WebView as well as iOS/browser; an
// iframe relies on a PDF viewer which Android WebViews do not supply.
export default function BillPdfPreview({ blob }) {
  const canvas = useRef(null);
  const container = useRef(null);
  const [pdf, setPdf] = useState(null);
  const [page, setPage] = useState(1);
  const [width, setWidth] = useState(320);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const update = () => setWidth(Math.max(200, container.current?.clientWidth || 320));
    update();
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(update) : null;
    if (container.current) observer?.observe(container.current);
    window.addEventListener('resize', update);
    return () => { observer?.disconnect(); window.removeEventListener('resize', update); };
  }, []);

  useEffect(() => {
    let active = true;
    let task;
    setPage(1); setPdf(null); setError(''); setLoading(true);
    if (!blob) return () => { active = false; };
    (async () => {
      try {
        const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
        pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/legacy/build/pdf.worker.min.mjs', import.meta.url).toString();
        const data = new Uint8Array(await readBlobBuffer(blob));
        if (!active) return;
        task = pdfjs.getDocument({ data, isEvalSupported: false, useSystemFonts: true });
        const doc = await task.promise;
        if (active) setPdf(doc);
      } catch {
        if (active) { setError('Preview could not load. Please close and try again, or download the PDF.'); setLoading(false); }
      }
    })();
    return () => { active = false; task?.destroy(); };
  }, [blob]);

  useEffect(() => {
    if (!pdf) return;
    let active = true;
    let render;
    setLoading(true);
    (async () => {
      try {
        const p = await pdf.getPage(page);
        if (!active) return;
        const base = p.getViewport({ scale: 1 });
        const scale = Math.min(window.devicePixelRatio || 1, 2);
        const viewport = p.getViewport({ scale: width / base.width * scale });
        const element = canvas.current;
        element.width = viewport.width; element.height = viewport.height;
        element.style.width = `${viewport.width / scale}px`;
        element.style.height = `${viewport.height / scale}px`;
        render = p.render({ canvasContext: element.getContext('2d'), viewport });
        await render.promise;
        if (active) setLoading(false);
      } catch (err) {
        if (active && err?.name !== 'RenderingCancelledException') {
          setError('Unable to display this page. Please download the PDF.'); setLoading(false);
        }
      }
    })();
    return () => { active = false; render?.cancel(); };
  }, [pdf, page, width]);

  return <div ref={container} className="w-full min-h-48">
    {loading && !error && <div role="status" className="py-5 flex justify-center gap-2 text-slate-500"><Loader2 className="w-5 h-5 animate-spin" />Loading preview…</div>}
    {error && <p role="alert" className="p-4 text-sm text-red-600">{error}</p>}
    <canvas ref={canvas} aria-label={`Invoice PDF page ${page}`} className="max-w-full bg-white mx-auto" />
    {pdf?.numPages > 1 && <div className="flex justify-between items-center gap-3 py-3">
      <button type="button" aria-label="Previous page" disabled={page === 1 || loading} onClick={() => setPage(page - 1)} className="p-2 disabled:opacity-40"><ChevronLeft /></button>
      <span className="text-sm">Page {page} of {pdf.numPages}</span>
      <button type="button" aria-label="Next page" disabled={page === pdf.numPages || loading} onClick={() => setPage(page + 1)} className="p-2 disabled:opacity-40"><ChevronRight /></button>
    </div>}
  </div>;
}
