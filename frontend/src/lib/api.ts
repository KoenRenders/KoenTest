import axios from "axios";

const BASE = process.env.NEXT_PUBLIC_API_URL || "";

export const api = axios.create({ baseURL: BASE, withCredentials: false });

// Attach the juiste JWT uit localStorage. Adminpaden krijgen het admin-token;
// publieke/lid-aanvragen krijgen bij voorkeur het lid-token (en vallen anders
// terug op het admin-token). Zo wordt een activiteitsinschrijving aan het
// ingelogde lid gekoppeld, terwijl het adminpaneel ongemoeid blijft.
if (typeof window !== "undefined") {
  api.interceptors.request.use((config) => {
    const url = config.url || "";
    const adminToken = localStorage.getItem("admin_token");
    const memberToken = localStorage.getItem("member_token");
    const isAdminCall = url.includes("/admin") || url.includes("/auth/verify-login") || url.includes("/auth/me");
    const token = isAdminCall ? adminToken : memberToken || adminToken;
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  });
}

// Activities
export const getActivities = () => api.get("/api/v1/activities");
export const getArchivedActivities = () => api.get("/api/v1/activities/archived");
export const createActivity = (data: unknown) => api.post("/api/v1/activities", data);
export const updateActivity = (id: number, data: unknown) => api.put(`/api/v1/activities/${id}`, data);
export const deleteActivity = (id: number) => api.delete(`/api/v1/activities/${id}`);
export const getRegistrations = (id: number) => api.get(`/api/v1/activities/${id}/registrations`);
export const getWaitlist = (id: number) => api.get(`/api/v1/activities/${id}/waitlist`);
export const registerForActivity = (id: number, data: unknown) => api.post(`/api/v1/activities/${id}/register`, data);
export const getPublicRegistrations = (activityId: number, componentId: number) =>
  api.get(`/api/v1/activities/${activityId}/public-registrations`, { params: { component_id: componentId } });

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

// Auth (admin)
export const requestLogin = (email: string) => api.post("/api/v1/auth/request-login", { email });
export const verifyLoginToken = (token: string) => api.get("/api/v1/auth/verify-login", { params: { token } });
export const verifyLoginOtp = (email: string, code: string) =>
  api.post<{ access_token: string }>("/api/v1/auth/verify-otp", { email, code });
export const getMe = () => api.get("/api/v1/auth/me");

// Auth (lid)
export interface MemberMe {
  person_id: number;
  member_id: number;
  name: string;
  email: string;
  phone?: string | null;
}
export const memberRequestLogin = (email: string) =>
  api.post("/api/v1/auth/member/request-login", { email });
export const memberVerifyLogin = (token: string) =>
  api.get<{ access_token: string }>("/api/v1/auth/member/verify-login", { params: { token } });
export const memberVerifyOtp = (email: string, code: string) =>
  api.post<{ access_token: string }>("/api/v1/auth/member/verify-otp", { email, code });
export const getMemberMe = () => api.get<MemberMe>("/api/v1/auth/member/me");

// Lid-zelfbediening (mijn gezin)
export const getMemberHousehold = () => api.get("/api/v1/member/household");
export const updateMemberPerson = (personId: number, data: unknown) =>
  api.put(`/api/v1/member/household/persons/${personId}`, data);
export const addMemberPerson = (data: unknown) =>
  api.post("/api/v1/member/household/persons", data);
export const removeMemberPerson = (personId: number) =>
  api.delete(`/api/v1/member/household/persons/${personId}`);

// Admin
export const getStats = () => api.get("/api/v1/admin/stats");
export const getAllPages = () => api.get("/api/v1/admin/pages");


// Admin — gebruikersbeheer
export const getAdminUsers = () => api.get("/api/v1/admin/users");
export const createAdminUser = (data: unknown) => api.post("/api/v1/admin/users", data);
export const updateAdminUser = (id: number, data: unknown) => api.put(`/api/v1/admin/users/${id}`, data);
export const deleteAdminUser = (id: number) => api.delete(`/api/v1/admin/users/${id}`);
