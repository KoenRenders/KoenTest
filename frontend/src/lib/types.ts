export interface ActivityProduct {
  id: number;
  component_id: number;
  name: string;
  price: string;
  member_price?: string;
  is_free: boolean;
  max_participants?: number;
  sort_order: number;
}

export interface ActivityComponent {
  id: number;
  name: string;
  team_name_required: boolean;
  sort_order: number;
  external_register_url?: string;
  external_registrations_url?: string;
  info_url?: string;
  products: ActivityProduct[];
}

export interface Activity {
  id: number;
  name: string;
  date: string;
  date_end?: string;
  time?: string;
  location?: string;
  max_participants?: number;
  poster_url?: string;
  status?: string;
  registration_count?: number;
  waitlist_count?: number;
  sub_registrations?: ActivityComponent[];
}

export interface Family {
  id: number;
  street: string;
  house_number: string;
  bus_number?: string;
  postal_code: string;
  municipality: string;
  members: FamilyMember[];
  board_member?: { id: number; first_name: string; last_name: string };
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
