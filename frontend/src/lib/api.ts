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

// Webshop
export const getProducts = () => api.get("/api/v1/products");
export const createOrder = (data: unknown) => api.post("/api/v1/orders", data);
export const getOrders = () => api.get("/api/v1/orders");
export const exportOrders = () => api.get("/api/v1/orders/export", { responseType: "blob" });

// Auth
export const login = (username: string, password: string) =>
  api.post("/api/v1/auth/login", { username, password });
export const getMe = () => api.get("/api/v1/auth/me");

// Admin
export const getStats = () => api.get("/api/v1/admin/stats");
export const getProductTotals = () => api.get("/api/v1/admin/product-totals");
