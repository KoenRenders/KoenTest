export interface SubRegistration {
  id: number;
  name: string;
  description?: string;
  external_register_url?: string;
  external_registrations_url?: string;
  info_url?: string;
  is_free: boolean;
  price: string;
  sort_order: number;
  reg_form_type?: string;
}

export interface Activity {
  id: number;
  name: string;
  date: string;
  date_end?: string;
  time?: string;
  location?: string;
  max_participants?: number;
  registration_type: "individual" | "family";
  price: string;
  member_price?: string;
  poster_url?: string;
  is_archived: boolean;
  status?: string;
  registration_count?: number;
  waitlist_count?: number;
  sub_registrations?: SubRegistration[];
  reg_form_type?: string;
  age_category_config?: string;
}

export interface RegistrationItem {
  sub_registration_id: number;
  quantity: number;
}

export interface PublicRegistrationSummary {
  names: string[];
  total_registrations: number;
  total_participants: number;
}

export interface Family {
  id: number;
  street: string;
  house_number: string;
  bus_number?: string;
  postal_code: string;
  municipality: string;
  members: FamilyMember[];
}

export interface FamilyMember {
  id: number;
  family_id: number;
  last_name: string;
  first_name: string;
  date_of_birth?: string;
  gender?: string;
  email?: string;
  phone?: string;
  is_primary: boolean;
}

export interface Membership {
  id: number;
  family_id: number;
  year: number;
  is_active: boolean;
}

export interface CmsPage {
  id: number;
  title: string;
  slug: string;
  content?: string;
  is_published: boolean;
  sort_order: number;
}

export interface Idea {
  id: number;
  submitter_name: string;
  submitter_email?: string;
  content: string;
  submitted_at: string;
  is_reviewed: boolean;
}

export interface Product {
  id: number;
  name: string;
  regular_price: string;
  member_price?: string;
  category?: string;
  is_active: boolean;
}

export interface OrderItem {
  product_id: number;
  quantity: number;
}

export interface CartItem {
  product: Product;
  quantity: number;
}

export interface Order {
  id: number;
  confirmation_number: string;
  customer_name: string;
  customer_email: string;
  is_member: boolean;
  total_amount: string;
  payment_status: string;
  created_at: string;
  items: Array<{ product_id: number; quantity: number; unit_price: string; product?: Product }>;
}

export interface Registration {
  id: number;
  activity_id: number;
  family_id?: number;
  family_member_id?: number;
  is_waitlist: boolean;
  registered_at: string;
  registration_type: string;
  contact_name?: string;
  contact_email?: string;
}
