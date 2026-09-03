import { UtensilsCrossed, BedDouble, Pencil, Gift, Coffee, Flower2, ShoppingBasket, SprayCan, Boxes } from 'lucide-react';
import { AutoRickshaw } from '@/components/icons/AutoRickshaw';

// Each category carries its own pastel tile palette (Paytm / Jio style):
//   tint   – very light bg behind the icon
//   ink    – icon foreground colour
//   accent – stronger version for chips / progress bars
export const CATEGORIES = [
  { key: 'food',       label: 'Food',        icon: UtensilsCrossed, tint: '#FFF1E6', ink: '#EA580C', accent: '#F97316', sub: ['Breakfast', 'Lunch', 'Dinner', 'Snacks'] },
  { key: 'travel',     label: 'Travel',      icon: AutoRickshaw,    tint: '#E0F2FE', ink: '#0284C7', accent: '#0EA5E9', sub: ['Auto Booking', 'E-Rickshaw Booking', 'Bike Booking', 'Cab Booking', 'Bus Booking', 'Taxi Booking', 'Self Booking', 'Flight', 'Train', 'Toll'] },
  { key: 'hotel',      label: 'Hotel',       icon: BedDouble,       tint: '#EEF2FF', ink: '#4F46E5', accent: '#6366F1', sub: ['Standard Room', 'Deluxe Room', 'Suite', 'Family Room', 'Dormitory', 'Other'] },
  { key: 'stationery', label: 'Stationery',  icon: Pencil,          tint: '#FEF3C7', ink: '#B45309', accent: '#F59E0B', sub: ['Office Supplies', 'Printing', 'Notebooks', 'Pens & Markers', 'Files & Folders', 'Printer Cartridge'] },
  { key: 'gift',       label: 'Gift',        icon: Gift,            tint: '#FCE7F3', ink: '#BE185D', accent: '#EC4899', sub: ['Client Gift', 'Employee Reward', 'Festive Hamper', 'Anniversary', 'Birthday'] },
  { key: 'pantry',     label: 'Pantry',      icon: Coffee,          tint: '#FEF3C7', ink: '#92400E', accent: '#D97706', sub: ['Tea & Coffee', 'Snacks & Biscuits', 'Beverages & Water', 'Milk & Dairy', 'Sugar & Sweetener', 'Disposables'] },
  { key: 'flower',     label: 'Flower Shop', icon: Flower2,         tint: '#FFE4E6', ink: '#E11D48', accent: '#F43F5E', sub: ['Bouquet', 'Decoration', 'Plants', 'Garlands'] },
  { key: 'grocery',    label: 'Grocery',     icon: ShoppingBasket,  tint: '#DCFCE7', ink: '#15803D', accent: '#10B981', sub: ['Atta, Rice & Dal', 'Oil, Ghee & Spices', 'Vegetables & Fruits', 'Dairy & Eggs', 'Snacks & Beverages', 'Household & Cleaning', 'Daily Top-up', 'Weekly Bulk'] },
  { key: 'cleaning',   label: 'Cleaning',    icon: SprayCan,        tint: '#CFFAFE', ink: '#0891B2', accent: '#06B6D4', sub: ['Housekeeping Service', 'Cleaning Supplies', 'Pest Control', 'Laundry'] },
  { key: 'other',      label: 'Other',       icon: Boxes,           tint: '#F1F5F9', ink: '#475569', accent: '#64748B', sub: ['Misc', 'Repairs & Maintenance', 'Subscriptions', 'Internet & Phone', 'Courier'] },
];

export const catByKey = (k) => CATEGORIES.find((c) => c.key === k);
