import { billFilename, canSharePdf, downloadBillPdf, isShareCancelled, shareBillPdf } from './billDocuments';
import { isNative, nativePlatform } from './native';
import { Filesystem } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';

jest.mock('./api', () => ({ __esModule: true, default: { get: jest.fn() } }));
jest.mock('./native', () => ({ isNative: jest.fn(), nativePlatform: jest.fn() }));
jest.mock('@capacitor/filesystem', () => ({ Filesystem: { writeFile: jest.fn(), checkPermissions: jest.fn(), requestPermissions: jest.fn() }, Directory: { Documents: 'DOCUMENTS', Cache: 'CACHE' } }));
jest.mock('@capacitor/share', () => ({ Share: { share: jest.fn() } }));
const blob = new Blob(['%PDF-1.4 sample'], { type: 'application/pdf' });
beforeEach(() => { jest.clearAllMocks(); isNative.mockReturnValue(false); Filesystem.writeFile.mockResolvedValue({ uri: 'file:///cache/bill.pdf' }); });
test('filename cannot traverse folders', () => expect(billFilename('../a/b')).toBe('___a_b.pdf'));
test('web shares the actual file, without an authentication URL', async () => {
  navigator.canShare = jest.fn().mockReturnValue(true);
  navigator.share = jest.fn().mockResolvedValue({});
  expect(canSharePdf(blob, 'bill.pdf')).toBe(true);
  const pending = shareBillPdf(blob, 'bill.pdf');
  expect(navigator.share).toHaveBeenCalledTimes(1); // invoked before yielding activation
  expect(navigator.share.mock.calls[0][0].files[0].name).toBe('bill.pdf');
  expect(navigator.share.mock.calls[0][0].url).toBeUndefined();
  await pending;
});
test.each(['android', 'ios'])('%s shares from native cache and saves Downloads in Documents', async (platform) => {
  isNative.mockReturnValue(true); nativePlatform.mockReturnValue(platform);
  Filesystem.checkPermissions.mockResolvedValue({ publicStorage: 'granted' });
  Share.share.mockResolvedValue({});
  await shareBillPdf(blob, 'bill.pdf', 'whatsapp');
  expect(Filesystem.writeFile.mock.calls[0][0].directory).toBe('CACHE');
  expect(Share.share.mock.calls[0][0].files).toEqual(['file:///cache/bill.pdf']);
  await downloadBillPdf(blob, 'bill.pdf');
  expect(Filesystem.writeFile.mock.calls[1][0].directory).toBe('DOCUMENTS');
});
test('storage refusal does not falsely claim a saved file', async () => {
  isNative.mockReturnValue(true); nativePlatform.mockReturnValue('android');
  Filesystem.checkPermissions.mockResolvedValue({ publicStorage: 'prompt' });
  Filesystem.requestPermissions.mockResolvedValue({ publicStorage: 'denied' });
  await expect(downloadBillPdf(blob, 'bill.pdf')).rejects.toThrow('Storage permission');
  expect(Filesystem.writeFile).not.toHaveBeenCalled();
});
test('sharing cancellation is distinct from failure', () => {
  expect(isShareCancelled({ name: 'AbortError' })).toBe(true);
  expect(isShareCancelled({ message: 'Share cancelled' })).toBe(true);
  expect(isShareCancelled({ message: 'Network error' })).toBe(false);
});
