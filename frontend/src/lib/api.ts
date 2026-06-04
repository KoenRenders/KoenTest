import axios from "axios";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
export const getActivities = () => api.get("/api/activities");
export const getArchivedActivities = () => api.get("/api/activities/archived");
export const createActivity = (data: unknown) => api.post("/api/activities", data);
export const updateActivity = (id: number, data: unknown) => api.put(`/api/activities/${id}`, data);
export const deleteActivity = (id: number) => api.delete(`/api/activities/${id}`);
export const getRegistrations = (id: number) => api.get(`/api/activities/${id}/registrations`);
export const getWaitlist = (id: number) => api.get(`/api/activities/${id}/waitlist`);
export const registerForActivity = (id: number, data: unknown) => api.post(`/api/activities/${id}/register`, data);

// Families
export const getFamilies = () => api.get("/api/families");
export const getFamily = (id: number) => api.get(`/api/families/${id}`);
export const createFamily = (data: unknown) => api.post("/api/families", data);
export const updateFamily = (id: number, data: unknown) => api.put(`/api/families/${id}`, data);
export const addFamilyMember = (familyId: number, data: unknown) => api.post(`/api/families/${familyId}/members`, data);
export const createMembership = (familyId: number, data: unknown) => api.post(`/api/families/${familyId}/memberships`, data);
export const getMemberships = (year?: number) => api.get("/api/memberships", { params: year ? { year } : {} });

// Ideas
export const getIdeas = () => api.get("/api/ideas");
export const submitIdea = (data: unknown) => api.post("/api/ideas", data);
export const markIdeaReviewed = (id: number) => api.put(`/api/ideas/${id}`);

// CMS
export const getPages = () => api.get("/api/pages");
export const getPage = (slug: string) => api.get(`/api/pages/${slug}`);
export const createPage = (data: unknown) => api.post("/api/pages", data);
export const updatePage = (id: number, data: unknown) => api.put(`/api/pages/${id}`, data);
export const deletePage = (id: number) => api.delete(`/api/pages/${id}`);

// Webshop
export const getProducts = () => api.get("/api/products");
export const createOrder = (data: unknown) => api.post("/api/orders", data);
export const getOrders = () => api.get("/api/orders");
export const exportOrders = () => api.get("/api/orders/export", { responseType: "blob" });

// Auth
export const login = (username: string, password: string) =>
  api.post("/api/auth/login", { username, password });
export const getMe = () => api.get("/api/auth/me");

// Admin
export const getStats = () => api.get("/api/admin/stats");
export const getProductTotals = () => api.get("/api/admin/product-totals");
