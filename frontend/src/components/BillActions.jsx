import React, { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { Download, FileText, Loader2, Mail, MessageCircle, Share2 } from 'lucide-react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import api from '@/lib/api';
import { isNative } from '@/lib/native';
import { billFilename, canSharePdf, downloadBillPdf, downloadWebPdf, fetchBillPdf, isShareCancelled, shareBillPdf } from '@/lib/billDocuments';

const BillPdfPreview = lazy(() => import('@/components/BillPdfPreview'));
const outline = 'press-down h-12 border-2 border-navy text-navy rounded-full font-semibold flex items-center justify-center gap-2 disabled:opacity-50';
const primary = 'press-down h-12 bg-navy text-white hover:bg-[#152042] rounded-full font-semibold flex items-center justify-center gap-2 disabled:opacity-50';

export default function BillActions({ expense }) {
  const filename = billFilename(expense.bill_id);
  const [blob, setBlob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pdfError, setPdfError] = useState('');
  const pending = useRef(null);
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState('');
  const [fallback, setFallback] = useState('');
  const [emailOpen, setEmailOpen] = useState(false);
  const [recipient, setRecipient] = useState('');
  const [note, setNote] = useState('');
  const [sending, setSending] = useState(false);
  const [emailError, setEmailError] = useState('');

  const loadPdf = useCallback(() => {
    if (!pending.current) {
      pending.current = fetchBillPdf(expense.id).catch((err) => { pending.current = null; throw err; });
    }
    return pending.current;
  }, [expense.id]);

  useEffect(() => {
    let active = true;
    loadPdf().then((value) => { if (active) setBlob(value); })
      .catch(() => { if (active) setPdfError('PDF could not load. Please retry.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [loadPdf]);

  const retry = async () => {
    setLoading(true); setPdfError('');
    try { setBlob(await loadPdf()); }
    catch { setPdfError('PDF could not load. Check your connection and try again.'); }
    finally { setLoading(false); }
  };

  const download = async () => {
    if (!blob) return;
    setBusy('download');
    try { toast.success(await downloadBillPdf(blob, filename)); }
    catch (err) { toast.error(err?.message || 'Download failed. Please try again.'); }
    finally { setBusy(''); }
  };

  const share = async (target) => {
    if (!blob) return;
    if (!canSharePdf(blob, filename)) { setFallback(target); return; }
    setBusy(target);
    try {
      if (target !== 'share') toast.info(target === 'whatsapp' ? 'Choose WhatsApp in the share sheet.' : 'Choose your email app in the share sheet.');
      await shareBillPdf(blob, filename, target);
      // Resolving a share sheet does NOT prove a message was sent; no success claim.
    } catch (err) {
      if (isShareCancelled(err)) toast.info('Sharing cancelled. Your bill is still available.');
      else if (!isNative()) setFallback(target);
      else toast.error('Unable to share the PDF. Check the app update and try again, or use Download.');
    } finally { setBusy(''); }
  };

  const sendInvoice = async (event) => {
    event.preventDefault();
    if (sending) return;
    setSending(true); setEmailError('');
    try {
      await api.post(`/bills/${encodeURIComponent(expense.id)}/email`, { recipient_email: recipient.trim(), note: note.trim() || null });
      toast.success('Invoice email accepted for delivery with the PDF attached.');
      setEmailOpen(false); setNote('');
    } catch (err) {
      setEmailError(err?.response?.data?.detail || 'Email could not be sent. Please try again.');
    } finally { setSending(false); }
  };

  const message = `Invoice ${expense.bill_id}\nAmount: INR ${Number(expense.total || 0).toFixed(2)}\nPlease find the invoice PDF attached.`;
  const mailto = `mailto:?subject=${encodeURIComponent(`Invoice ${expense.bill_id}`)}&body=${encodeURIComponent(message)}`;
  const disabled = loading || !blob || !!busy;

  return <>
    <div className="grid grid-cols-2 gap-3">
      <button type="button" onClick={() => setPreview(true)} className={outline} data-testid="preview-pdf-btn"><FileText className="w-4 h-4" />Preview</button>
      <button type="button" onClick={download} disabled={disabled} className={primary} data-testid="download-pdf-btn">
        {busy === 'download' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}Download
      </button>
    </div>
    <button type="button" onClick={() => share('share')} disabled={disabled} className={`${outline} w-full`} data-testid="share-bill-btn"><Share2 className="w-5 h-5" />Share</button>
    <div className="grid grid-cols-2 gap-3">
      <button type="button" onClick={() => share('whatsapp')} disabled={disabled} className="press-down h-12 rounded-full bg-[#128C4A] text-white font-semibold flex items-center justify-center gap-2 disabled:opacity-50" data-testid="whatsapp-bill-btn"><MessageCircle className="w-5 h-5" />WhatsApp</button>
      <button type="button" onClick={() => share('email')} disabled={disabled} className={outline} data-testid="email-bill-btn"><Mail className="w-5 h-5" />Email</button>
    </div>
    <button type="button" onClick={() => { setEmailError(''); setEmailOpen(true); }} className={`${primary} w-full`} data-testid="email-invoice-client-btn"><Mail className="w-5 h-5" />Email invoice to client</button>
    {loading && <p role="status" className="text-xs text-slate-500 text-center">Preparing your PDF…</p>}
    {pdfError && <div role="alert" className="text-sm text-red-600 text-center">{pdfError} <button type="button" className="underline" onClick={retry} disabled={loading}>Retry PDF</button></div>}

    <Dialog open={preview} onOpenChange={setPreview}>
      <DialogContent className="w-[calc(100%-1rem)] max-w-3xl max-h-[90dvh] overflow-y-auto p-4 rounded-2xl">
        <DialogHeader><DialogTitle>Bill preview</DialogTitle><DialogDescription>{expense.bill_id} · PDF preview</DialogDescription></DialogHeader>
        {pdfError ? <div role="alert">{pdfError} <button type="button" onClick={retry} className="underline">Retry</button></div> : <Suspense fallback={<p role="status">Opening preview…</p>}><BillPdfPreview blob={blob} /></Suspense>}
        <Button type="button" onClick={download} disabled={disabled} className="rounded-full bg-navy text-white"><Download className="w-4 h-4 mr-2" />Download PDF</Button>
      </DialogContent>
    </Dialog>

    <Dialog open={!!fallback} onOpenChange={(open) => { if (!open) setFallback(''); }}>
      <DialogContent className="w-[calc(100%-2rem)] max-w-md rounded-2xl">
        <DialogHeader><DialogTitle>Share invoice PDF</DialogTitle><DialogDescription>This browser cannot attach a PDF directly to another app. Download it, then attach it in WhatsApp or email.</DialogDescription></DialogHeader>
        <Button type="button" onClick={() => downloadWebPdf(blob, filename)} className="rounded-full bg-navy text-white">1. Download PDF</Button>
        {fallback !== 'email' && <a href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noopener noreferrer" className={outline}>2. Open WhatsApp</a>}
        {fallback !== 'whatsapp' && <a href={mailto} className={outline}>2. Open email app</a>}
        <p className="text-xs text-slate-500">Attach {filename} before sending. Or use “Email invoice to client” to send the attachment through BILL4PE.</p>
      </DialogContent>
    </Dialog>

    <Dialog open={emailOpen} onOpenChange={(open) => { if (!sending) setEmailOpen(open); }}>
      <DialogContent className="w-[calc(100%-2rem)] max-w-md rounded-2xl">
        <DialogHeader><DialogTitle>Email invoice to client</DialogTitle><DialogDescription>The PDF will be attached to an email sent by BILL4PE. Confirm the recipient before sending.</DialogDescription></DialogHeader>
        <form onSubmit={sendInvoice} className="space-y-4">
          <div><label htmlFor="invoice-recipient" className="text-sm font-medium">Client email</label><Input id="invoice-recipient" type="email" required maxLength={254} value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="client@example.com" disabled={sending} className="mt-1 h-12" /></div>
          <div><label htmlFor="invoice-note" className="text-sm font-medium">Message (optional)</label><Textarea id="invoice-note" maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} disabled={sending} className="mt-1" /></div>
          {emailError && <p role="alert" className="text-sm text-red-600">{emailError}</p>}
          <Button type="submit" disabled={sending} className="w-full h-12 rounded-full bg-navy text-white">{sending ? 'Sending…' : 'Send invoice with PDF'}</Button>
        </form>
      </DialogContent>
    </Dialog>
  </>;
}
