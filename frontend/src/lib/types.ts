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
  info_asset_url?: string;
  info_asset_is_pdf?: boolean;
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
  poster_asset_url?: string;
  poster_asset_is_pdf?: boolean;
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
  show_in_nav: boolean;
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

// ── Form engine (#327) ──────────────────────────────────────────────────────
export interface FormFieldOption {
  id: number;
  label: string;
  value?: string | null;
  position: number;
  is_other?: boolean;
  skip_to_section_id?: number | null;
  skip_to_end?: boolean;
}

export interface FormSection {
  id: number;
  title?: string | null;
  description?: string | null;
  position: number;
  next_section_id?: number | null;
  next_is_end?: boolean;
}

export interface FormFieldDef {
  id: number;
  field_type: string;
  label: string;
  help_text?: string | null;
  required: boolean;
  position: number;
  section_id?: number | null;
  min_value?: number | null;
  max_value?: number | null;
  min_length?: number | null;
  max_length?: number | null;
  regex_pattern?: string | null;
  rating_max?: number | null;
  rating_low_label?: string | null;
  rating_high_label?: string | null;
  options: FormFieldOption[];
}

export interface FormAdmin {
  id: number;
  title: string;
  slug?: string | null;
  description?: string | null;
  share_token: string;
  status: string;
  requires_login: boolean;
  max_submissions?: number | null;
  send_confirmation: boolean;
  confirmation_message?: string | null;
  allow_edit: boolean;
  is_anonymous?: boolean;
  created_at: string;
  updated_at: string;
  sections: FormSection[];
  fields: FormFieldDef[];
  submission_count: number;
}

export interface FormSummary {
  id: number;
  title: string;
  status: string;
  share_token: string;
  submission_count: number;
  created_at: string;
}

export interface PublicFormField {
  id: number;
  field_type: string;
  label: string;
  help_text?: string | null;
  required: boolean;
  position: number;
  section_id?: number | null;
  min_value?: number | null;
  max_value?: number | null;
  min_length?: number | null;
  max_length?: number | null;
  rating_max?: number | null;
  rating_low_label?: string | null;
  rating_high_label?: string | null;
  options: { id: number; label: string; value?: string | null; is_other?: boolean; skip_to_section_id?: number | null; skip_to_end?: boolean }[];
}

export interface PublicForm {
  id: number;
  title: string;
  description?: string | null;
  status: string;
  allow_edit: boolean;
  send_confirmation?: boolean;
  confirmation_message?: string | null;
  is_anonymous?: boolean;
  sections: FormSection[];
  fields: PublicFormField[];
}

export interface AnswerPayload {
  field_id: number;
  text?: string | null;
  number?: number | null;
  option_ids?: number[];
  rating?: number | null;
  other_text?: string | null;
}

// ── E-maillog (#328) ────────────────────────────────────────────────────────
export interface EmailLogItem {
  id: number;
  recipient: string;
  subject: string;
  email_type: string;
  body?: string | null;
  status: string;
  error_message?: string | null;
  created_at: string;
}
