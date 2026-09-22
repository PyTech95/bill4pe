import api from '@/lib/api';
import { isNative, nativePlatform } from '@/lib/native';

export const billFilename = (billId) => `${String(billId || 'BILL4PE-bill').replace(/[^a-zA-Z0-9_-]/g, '_')}.pdf`;
export const isShareCancelled = (error) => error?.name === 'AbortError' || /cancel|dismiss/i.test(error?.message || '');

export async function fetchBillPdf(expenseId) {
  const { data } = await api.get(`/bills/${encodeURIComponent(expenseId)}/pdf`, { responseType: 'blob' });
  // Never save an error response as a PDF. FileReader also works in older WebViews.
  const header = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsText(data.slice(0, 5));
  });
  if (header !== '%PDF-') throw new Error('The server did not return a PDF. Please try again.');
  return new Blob([data], { type: 'application/pdf' });
}

export const readBlobBuffer = (blob) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(reader.result);
  reader.onerror = reject;
  reader.readAsArrayBuffer(blob);
});

const blobBase64 = (blob) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result).split(',')[1]);
  reader.onerror = reject;
  reader.readAsDataURL(blob);
});

export function downloadWebPdf(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // A synchronous revoke can abort the browser/iOS download.
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export async function downloadBillPdf(blob, filename) {
  if (!isNative()) {
    downloadWebPdf(blob, filename);
    return 'Download started. Check your browser downloads.';
  }
  const { Filesystem, Directory } = await import('@capacitor/filesystem');
  if (nativePlatform() === 'android') {
    let permission = await Filesystem.checkPermissions();
    if (permission.publicStorage !== 'granted') permission = await Filesystem.requestPermissions();
    if (permission.publicStorage !== 'granted') {
      throw new Error('Storage permission was not granted. Use Share to save a copy instead.');
    }
  }
  await Filesystem.writeFile({
    path: `BILL4PE/${filename}`, directory: Directory.Documents,
    data: await blobBase64(blob), recursive: true,
  });
  return nativePlatform() === 'ios'
    ? 'Saved in Files → On My iPhone/iPad → BILL4PE → BILL4PE.'
    : 'Saved in Documents/BILL4PE.';
}

export function canSharePdf(blob, filename) {
  if (isNative()) return true;
  try {
    return !!navigator.share && !!navigator.canShare?.({ files: [new File([blob], filename, { type: 'application/pdf' })] });
  } catch { return false; }
}

export async function shareBillPdf(blob, filename, target = 'share') {
  const title = `Invoice ${filename.replace(/\.pdf$/, '')}`;
  if (!isNative()) {
    // No await before navigator.share: iOS Safari requires the click activation.
    return navigator.share({ title, files: [new File([blob], filename, { type: 'application/pdf' })] });
  }
  const [{ Filesystem, Directory }, { Share }] = await Promise.all([
    import('@capacitor/filesystem'), import('@capacitor/share'),
  ]);
  const { uri } = await Filesystem.writeFile({
    path: `bill4pe-share/${filename}`, directory: Directory.Cache,
    data: await blobBase64(blob), recursive: true,
  });
  // Cache is FileProvider-shareable on Android. Never share the login token/URL.
  await Share.share({ title, files: [uri], dialogTitle: target === 'whatsapp'
    ? 'Choose WhatsApp to send your invoice' : target === 'email'
      ? 'Choose your email app' : 'Share invoice PDF' });
}
