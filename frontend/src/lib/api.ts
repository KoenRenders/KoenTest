import axios from "axios";

const BASE = process.env.NEXT_PUBLIC_API_URL || "";

export const api = axios.create({ baseURL: BASE, withCredentials: false });

// Eén login voor iedereen: één JWT in localStorage. Wat de gebruiker mág
// (admin, lid, …) wordt server-side per request afgeleid uit de identiteit in
// het token — de frontend hoeft geen onderscheid te maken.
if (typeof window !== "undefined") {
  api.interceptors.request.use((config) => {
    const token = localStorage.getItem("auth_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  });
}

// Activities
// Eén endpoint met scope (#136): upcoming (default, homepage), archived (archief),
// all (admin: alle activiteiten + álle datums).
export type ActivityScope = "upcoming" | "archived" | "all";
export const getActivities = (scope: ActivityScope = "upcoming") =>
  api.get("/api/v1/activities", { params: { scope } });
export const getArchivedActivities = () => getActivities("archived");
export const createActivity = (data: unknown) => api.post("/api/v1/activities", data);
export const updateActivity = (id: number, data: unknown) => api.put(`/api/v1/activities/${id}`, data);
export const deleteActivity = (id: number) => api.delete(`/api/v1/activities/${id}`);
export const getRegistrations = (id: number) => api.get(`/api/v1/activities/${id}/registrations`);
export const registerForActivity = (id: number, data: unknown) => api.post(`/api/v1/activities/${id}/register`, data);
export const getPublicRegistrations = (activityId: number, componentId: number) =>
  api.get(`/api/v1/activities/${activityId}/public-registrations`, { params: { component_id: componentId } });

// Bestelregels bewerken (admin) — audit + herberekend saldo (#84)
export const addOrderLine = (activityId: number, registrationId: number, data: { product_id: number; quantity: number }) =>
  api.post(`/api/v1/activities/${activityId}/registrations/${registrationId}/items`, data);
export const updateOrderLine = (activityId: number, registrationId: number, itemId: number, data: { product_id?: number; quantity?: number }) =>
  api.patch(`/api/v1/activities/${activityId}/registrations/${registrationId}/items/${itemId}`, data);
export const deleteOrderLine = (activityId: number, registrationId: number, itemId: number) =>
  api.delete(`/api/v1/activities/${activityId}/registrations/${registrationId}/items/${itemId}`);

// Excel-export per onderdeel (#85) — blob, met Bearer-token via de axios-instance
export const exportComponentXlsx = (activityId: number, componentId: number) =>
  api.get(`/api/v1/activities/${activityId}/components/${componentId}/export`, { responseType: "blob" });

// Ledendata-wijzigingen sinds datum (#82)
export const getMemberChanges = (since: string) =>
  api.get("/api/v1/admin/member-changes", { params: { since } });
export const exportMemberChanges = (since: string) =>
  api.get("/api/v1/admin/member-changes/export", { params: { since }, responseType: "blob" });

// Activity dates
export const addActivityDate = (activityId: number, data: unknown) =>
  api.post(`/api/v1/activities/${activityId}/dates`, data);
export const updateActivityDate = (activityId: number, dateId: number, data: unknown) =>
  api.put(`/api/v1/activities/${activityId}/dates/${dateId}`, data);
export const deleteActivityDate = (activityId: number, dateId: number) =>
  api.delete(`/api/v1/activities/${activityId}/dates/${dateId}`);

// Components (onderdelen) under an activity
export const addComponent = (activityId: number, data: unknown) =>
  api.post(`/api/v1/activities/${activityId}/components`, data);
export const updateComponent = (activityId: number, componentId: number, data: unknown) =>
  api.put(`/api/v1/activities/${activityId}/components/${componentId}`, data);
export const deleteComponent = (activityId: number, componentId: number) =>
  api.delete(`/api/v1/activities/${activityId}/components/${componentId}`);

// Products under a component
export const addProduct = (activityId: number, componentId: number, data: unknown) =>
  api.post(`/api/v1/activities/${activityId}/components/${componentId}/products`, data);
export const updateProduct = (activityId: number, componentId: number, productId: number, data: unknown) =>
  api.put(`/api/v1/activities/${activityId}/components/${componentId}/products/${productId}`, data);
export const deleteProduct = (activityId: number, componentId: number, productId: number) =>
  api.delete(`/api/v1/activities/${activityId}/components/${componentId}/products/${productId}`);

// Families
export const getFamilies = () => api.get("/api/v1/families");
export const getFamily = (id: number) => api.get(`/api/v1/families/${id}`);
export const createFamily = (data: unknown) => api.post("/api/v1/families", data);
export const updateFamily = (id: number, data: unknown) => api.put(`/api/v1/families/${id}`, data);
export const deleteFamily = (id: number) => api.delete(`/api/v1/families/${id}`);
export const addFamilyMember = (familyId: number, data: unknown) => api.post(`/api/v1/families/${familyId}/members`, data);
export const addPersonToFamily = (familyId: number, data: unknown) => api.post(`/api/v1/families/${familyId}/persons`, data);
export const assignBoardMember = (familyId: number, data: unknown) => api.put(`/api/v1/families/${familyId}/board-member`, data);
export const createMembership = (familyId: number, data: unknown) => api.post(`/api/v1/families/${familyId}/memberships`, data);
export const deleteMembership = (id: number) => api.delete(`/api/v1/memberships/${id}`);
export const getMemberships = (year?: number) => api.get("/api/v1/memberships", { params: year ? { year } : {} });

// Persons
export const listPersons = () => api.get("/api/v1/persons");
export const updatePerson = (id: number, data: unknown) => api.put(`/api/v1/persons/${id}`, data);
export const updatePersonAddress = (id: number, data: unknown) => api.put(`/api/v1/persons/${id}/address`, data);
export const updatePersonContacts = (id: number, data: unknown) => api.put(`/api/v1/persons/${id}/contacts`, data);
export const deletePerson = (id: number) => api.delete(`/api/v1/persons/${id}`);

// Ideas
export const getIdeas = () => api.get("/api/v1/ideas");
export const submitIdea = (data: unknown) => api.post("/api/v1/ideas", data);
export const markIdeaReviewed = (id: number) => api.put(`/api/v1/ideas/${id}`);

// CMS
export const getGenderCodes = () => api.get<{ code: string; value: string }[]>("/api/v1/gender-codes");
export const getRelationTypes = () => api.get<{ code: string; value: string }[]>("/api/v1/relation-types");
export const getPages = () => api.get("/api/v1/pages");
export const getPage = (slug: string) => api.get(`/api/v1/pages/${slug}`);
export const getBlock = (slug: string) => api.get(`/api/v1/blocks/${slug}`);
export const getCmsPlaceholders = () =>
  api.get<{ code: string; label: string; preview: string }[]>("/api/v1/cms/placeholders");
export const createPage = (data: unknown) => api.post("/api/v1/pages", data);
export const updatePage = (id: number, data: unknown) => api.put(`/api/v1/pages/${id}`, data);
export const deletePage = (id: number) => api.delete(`/api/v1/pages/${id}`);

// Media / assetbibliotheek
import type { MediaAsset } from "@/lib/types";
export const getSponsors = () => api.get<MediaAsset[]>("/api/v1/sponsors");
export const getActivityPhotos = (activityId: number) =>
  api.get<MediaAsset[]>(`/api/v1/activities/${activityId}/photos`);
export const getActivityPhotoAvailability = () =>
  api.get<number[]>("/api/v1/media/activity-photos/availability");
export const getActivityPhotoCovers = () =>
  api.get<{ activity_id: number; thumb_url: string }[]>("/api/v1/media/activity-photos/covers");
export const adminListMedia = (params: { kind?: string; activity_id?: number } = {}) =>
  api.get<MediaAsset[]>("/api/v1/admin/media", { params });
export const uploadMedia = (
  files: File[],
  opts: { kind: string; activity_id?: number; title?: string; link_url?: string }
) => {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  fd.append("kind", opts.kind);
  if (opts.activity_id != null) fd.append("activity_id", String(opts.activity_id));
  if (opts.title) fd.append("title", opts.title);
  if (opts.link_url) fd.append("link_url", opts.link_url);
  return api.post<MediaAsset[]>("/api/v1/admin/media", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};
export const updateMedia = (id: number, data: Partial<MediaAsset>) =>
  api.patch<MediaAsset>(`/api/v1/admin/media/${id}`, data);
export const deleteMedia = (id: number) => api.delete(`/api/v1/admin/media/${id}`);

// Payment records
export const listPaymentRecords = () => api.get("/api/v1/payment-status/records");
export const updatePaymentRecord = (id: string, data: unknown) => api.patch(`/api/v1/payment-status/records/${id}`, data);
export const refreshPaymentRecord = (id: string) => api.post(`/api/v1/payment-status/records/${id}/refresh`);
export const refundPaymentRecord = (id: string, data: { amount: number; note?: string }) =>
  api.post(`/api/v1/payment-status/records/${id}/refund`, data);
export const deletePaymentRecord = (id: string) =>
  api.delete(`/api/v1/payment-status/records/${id}`);

// Auth — één login voor iedereen (magic link + OTP)
export const requestLogin = (email: string) => api.post("/api/v1/auth/request-login", { email });
export const verifyLoginToken = (token: string) =>
  api.get<{ access_token: string }>("/api/v1/auth/verify-login", { params: { token } });
export const verifyLoginOtp = (email: string, code: string) =>
  api.post<{ access_token: string }>("/api/v1/auth/verify-otp", { email, code });

export interface AuthMe {
  email: string;
  roles: string[];
  is_admin: boolean;
  is_member: boolean;
  member_name: string | null;
}
export const getAuthMe = () => api.get<AuthMe>("/api/v1/auth/me");

// Leden-domein (eigen gezin) — los van het rollensysteem
export interface MemberMe {
  person_id: number;
  member_id: number;
  name: string;
  email: string;
  phone?: string | null;
  has_valid_membership: boolean;
  membership_valid_until: string | null;
  renewal_available: boolean;
}
export const getMemberMe = () => api.get<MemberMe>("/api/v1/auth/member/me");

// Lid-zelfbediening (mijn gezin)
export const getMemberHousehold = () => api.get("/api/v1/member/household");
export const renewMembership = () =>
  api.post<{ checkout_url: string; amount: string }>("/api/v1/member/household/renew-membership");
export const updateMemberPerson = (personId: number, data: unknown) =>
  api.put(`/api/v1/member/household/persons/${personId}`, data);
export const addMemberPerson = (data: unknown) =>
  api.post("/api/v1/member/household/persons", data);
export const removeMemberPerson = (personId: number) =>
  api.delete(`/api/v1/member/household/persons/${personId}`);

// Admin
export interface SystemInfo {
  version: string;
  commit: string;
  environment: string;
  server_time: string;
  timezone: string;
  flags: { log_level: string; debug: boolean; sql_echo: boolean };
  limits: { max_item_quantity: number; max_registrations_per_email: number };
  membership: {
    price_full: string;
    price_half: string;
    half_price_start_md: string;
    half_price_end_md: string;
    next_year_from_md: string;
    renewal_start_md: string | null;
  };
  urls: { frontend_url: string; public_url: string };
  mollie_mode: string;
}
export const getStats = () => api.get("/api/v1/admin/stats");
export const getSystemInfo = () => api.get<SystemInfo>("/api/v1/admin/system-info");
export const getAllPages = () => api.get("/api/v1/admin/pages");


// Gebruikers- en rollenbeheer (ADMIN-gated)
export const getUsers = () => api.get("/api/v1/users");
export const createUser = (data: unknown) => api.post("/api/v1/users", data);
export const updateUser = (id: number, data: unknown) => api.put(`/api/v1/users/${id}`, data);
export const deleteUser = (id: number) => api.delete(`/api/v1/users/${id}`);
