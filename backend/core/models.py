"""Pydantic request/response models for BILL4PE."""
from pydantic import BaseModel, EmailStr
from typing import List, Optional


class RegisterReq(BaseModel):
    email: EmailStr
    password: str
    name: str
    referrer_code: Optional[str] = None
    user_type: Optional[str] = "individual"  # "individual" or "corporate"
    corporate_name: Optional[str] = None
    subscription_plan: Optional[str] = None  # "monthly_50" | "monthly_100" | "quarterly_50" | "quarterly_100" | "yearly_50" | "yearly_100"
    employee_limit: Optional[int] = None


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class OtpRequestReq(BaseModel):
    phone: str
    name: Optional[str] = None


class OtpVerifyReq(BaseModel):
    phone: str
    otp: str
    name: Optional[str] = None
    referrer_code: Optional[str] = None


class User(BaseModel):
    id: str
    email: str
    name: str
    wallet_balance: float = 0.0
    created_at: str


class ItemIn(BaseModel):
    name: str
    quantity: float = 1
    unit_price: float


class ExpenseDraft(BaseModel):
    category: str
    sub_category: Optional[str] = None
    items: List[ItemIn]
    notes: Optional[str] = None


class TripInfo(BaseModel):
    from_text: Optional[str] = None
    to_text: Optional[str] = None
    pickup_lat: Optional[float] = None
    pickup_lng: Optional[float] = None
    drop_lat: Optional[float] = None
    drop_lng: Optional[float] = None
    nature_of_business: Optional[str] = None  # e.g. "Auto Driver"


class StayInfo(BaseModel):
    hotel_name: Optional[str] = None
    room_type: Optional[str] = None
    check_in: Optional[str] = None       # YYYY-MM-DD
    check_out: Optional[str] = None      # YYYY-MM-DD
    nights: Optional[int] = None
    per_night_rate: Optional[float] = None
    nature_of_business: Optional[str] = None  # e.g. "Hotel & Lodging"


class PaymentInfo(BaseModel):
    merchant_name: Optional[str] = None
    merchant_upi: Optional[str] = None
    merchant_mobile: Optional[str] = None
    transaction_id: Optional[str] = None
    amount: float
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    payment_method: str = "UPI"  # UPI/Cash/GPay/PhonePe/Paytm/BharatPe/BHIM
    trip: Optional[TripInfo] = None
    stay: Optional[StayInfo] = None


class ExpenseCreate(BaseModel):
    category: str
    sub_category: Optional[str] = None
    items: List[ItemIn]
    payment: PaymentInfo
    notes: Optional[str] = None


class WalletRecharge(BaseModel):
    amount: float


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    company_name: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class ReportCreate(BaseModel):
    title: str
    expense_ids: List[str]
    notes: Optional[str] = None


class ContactMsg(BaseModel):
    name: str
    email: EmailStr
    message: str


class FavouriteItem(BaseModel):
    name: str
    unit_price: float = 0.0


class FavouritesSave(BaseModel):
    category: str
    items: List[FavouriteItem]


# ----- Corporate / B2B -----

class EmployeeCreate(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    employee_id: Optional[str] = None
    monthly_cap: Optional[float] = None
    temp_password: Optional[str] = None  # if omitted, system generates one


class EmployeeInvite(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    employee_id: Optional[str] = None
    monthly_cap: Optional[float] = None


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    employee_id: Optional[str] = None
    monthly_cap: Optional[float] = None
    is_active: Optional[bool] = None


class AcceptInviteReq(BaseModel):
    token: str
    password: str


class ApprovalDecision(BaseModel):
    reason: Optional[str] = None
