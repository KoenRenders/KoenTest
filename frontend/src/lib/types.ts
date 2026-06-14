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
  max_participants?: number;
  products: ActivityProduct[];
}

export interface ActivityDate {
  id: number;
  activity_id: number;
  start_date: string;
  end_date?: string;
  start_time?: string;
  end_time?: string;
}

export interface Activity {
  id: number;
  name: string;
  sort_date?: string;
  dates: ActivityDate[];
  location?: string;
  poster_url?: string;
  members_only?: boolean;
  status?: string;
  is_cancelled?: boolean;
  registration_count?: number;
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
  memberships: Membership[];
  board_member?: { id: number; first_name: string; last_name: string };
}

export interface FamilyMember {
  id: number;
  family_id: number;
  last_name: string;
  first_name: string;
  date_of_birth?: string;
  gender?: string;
  gender_code?: string;
  email?: string;
  phone?: string;
  mobile?: string;
  relation_type: string;
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

export interface MediaAsset {
  id: number;
  kind: "sponsor" | "activity_photo";
  activity_id?: number | null;
  title?: string | null;
  link_url?: string | null;
  sort_order: number;
  is_active: boolean;
  width?: number | null;
  height?: number | null;
  byte_size?: number | null;
  url: string;
  thumb_url: string;
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
  registered_at: string;
  registration_type: string;
  contact_name?: string;
  contact_email?: string;
}
