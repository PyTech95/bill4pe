import { UtensilsCrossed, Plane, BedDouble, Pencil, Gift, Coffee, Flower2, ShoppingBasket, SprayCan, Boxes } from 'lucide-react';

export const CATEGORIES = [
  { key: 'food', label: 'Food', icon: UtensilsCrossed, sub: ['Breakfast', 'Lunch', 'Dinner', 'Snacks'] },
  { key: 'travel', label: 'Travel', icon: Plane, sub: ['Auto Booking', 'E-Rickshaw Booking', 'Bike Booking', 'Cab Booking', 'Bus Booking', 'Taxi Booking', 'Self Booking', 'Flight', 'Train', 'Toll'] },
  { key: 'hotel', label: 'Hotel', icon: BedDouble, sub: ['Standard Room', 'Deluxe Room', 'Suite', 'Family Room', 'Dormitory', 'Other'] },
  { key: 'stationery', label: 'Stationery', icon: Pencil, sub: ['Office Supplies', 'Printing', 'Notebooks', 'Pens & Markers', 'Files & Folders', 'Printer Cartridge'] },
  { key: 'gift', label: 'Gift', icon: Gift, sub: ['Client Gift', 'Employee Reward', 'Festive Hamper', 'Anniversary', 'Birthday'] },
  { key: 'pantry', label: 'Pantry', icon: Coffee, sub: ['Tea & Coffee', 'Snacks & Biscuits', 'Beverages & Water', 'Milk & Dairy', 'Sugar & Sweetener', 'Disposables'] },
  { key: 'flower', label: 'Flower Shop', icon: Flower2, sub: ['Bouquet', 'Decoration', 'Plants', 'Garlands'] },
  { key: 'grocery', label: 'Grocery', icon: ShoppingBasket, sub: ['Atta, Rice & Dal', 'Oil, Ghee & Spices', 'Vegetables & Fruits', 'Dairy & Eggs', 'Snacks & Beverages', 'Household & Cleaning', 'Daily Top-up', 'Weekly Bulk'] },
  { key: 'cleaning', label: 'Cleaning', icon: SprayCan, sub: ['Housekeeping Service', 'Cleaning Supplies', 'Pest Control', 'Laundry'] },
  { key: 'other', label: 'Other', icon: Boxes, sub: ['Misc', 'Repairs & Maintenance', 'Subscriptions', 'Internet & Phone', 'Courier'] },
];

export const catByKey = (k) => CATEGORIES.find((c) => c.key === k);
