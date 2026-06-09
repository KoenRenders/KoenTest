import axios from "axios";

const BASE = process.env.NEXT_PUBLIC_API_URL || "";

export const api = axios.create({ baseURL: BASE, withCredentials: false });

// Attach JWT token from localStorage for admin requests
if (typeof window !== "undefined") {
  api.interceptors.request.use((config) => {
    const token = localStorage.getItem("admin_token");
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
export const getPublicRegistrations = (activityId: number, productId: number) =>
  api.get(`/api/v1/activities/${activityId}/public-registrations`, { params: { product_id: productId } });

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
export const addFamilyMember = (familyId: number, data: unknown) => api.post(`/api/v1/families/${familyId}/members`, data);
export const createMembership = (familyId: number, data: unknown) => api.post(`/api/v1/families/${familyId}/memberships`, data);
export const getMemberships = (year?: number) => api.get("/api/v1/memberships", { params: year ? { year } : {} });

// Ideas
export const getIdeas = () => api.get("/api/v1/ideas");
export const submitIdea = (data: unknown) => api.post("/api/v1/ideas", data);
export const markIdeaReviewed = (id: number) => api.put(`/api/v1/ideas/${id}`);

// CMS
export const getPages = () => api.get("/api/v1/pages");
export const getPage = (slug: string) => api.get(`/api/v1/pages/${slug}`);
export const createPage = (data: unknown) => api.post("/api/v1/pages", data);
export const updatePage = (id: number, data: unknown) => api.put(`/api/v1/pages/${id}`, data);
export const deletePage = (id: number) => api.delete(`/api/v1/pages/${id}`);

// Auth
export const requestLogin = (email: string) => api.post("/api/v1/auth/request-login", { email });
export const verifyLoginToken = (token: string) => api.get("/api/v1/auth/verify-login", { params: { token } });
export const getMe = () => api.get("/api/v1/auth/me");

// Admin
export const getStats = () => api.get("/api/v1/admin/stats");
export const getAllPages = () => api.get("/api/v1/admin/pages");
