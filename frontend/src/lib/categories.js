import { UtensilsCrossed, Plane, BedDouble, Pencil, Gift, Coffee, Flower2, ShoppingBasket, SprayCan, Boxes } from 'lucide-react';

export const CATEGORIES = [
  { key: 'food', label: 'Food', icon: UtensilsCrossed, sub: ['Breakfast', 'Lunch', 'Dinner', 'Snacks'] },
  { key: 'travel', label: 'Travel', icon: Plane, sub: ['Flight', 'Train', 'Cab', 'Bus', 'Toll'] },
  { key: 'hotel', label: 'Hotel', icon: BedDouble, sub: ['Lodging', 'Meals', 'Conference'] },
  { key: 'stationery', label: 'Stationery', icon: Pencil, sub: ['Office', 'Printing', 'Supplies'] },
  { key: 'gift', label: 'Gift', icon: Gift, sub: ['Client', 'Employee', 'Festive'] },
  { key: 'pantry', label: 'Pantry', icon: Coffee, sub: ['Tea/Coffee', 'Snacks', 'Drinks'] },
  { key: 'flower', label: 'Flower Shop', icon: Flower2, sub: ['Bouquet', 'Decoration', 'Plants'] },
  { key: 'grocery', label: 'Grocery', icon: ShoppingBasket, sub: ['Daily', 'Monthly', 'Mart'] },
  { key: 'cleaning', label: 'Cleaning', icon: SprayCan, sub: ['Housekeeping', 'Supplies', 'Services'] },
  { key: 'other', label: 'Other', icon: Boxes, sub: ['Misc', 'Repairs', 'Subscriptions'] },
];

export const catByKey = (k) => CATEGORIES.find((c) => c.key === k);
