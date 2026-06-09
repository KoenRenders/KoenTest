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
export const getPublicRegistrations = (activityId: number, subRegistrationId?: number) =>
  api.get(`/api/v1/activities/${activityId}/registrations/public`, {
    params: subRegistrationId ? { sub_registration_id: subRegistrationId } : {},
  });
export const createSubRegistration = (activityId: number, data: unknown) => api.post(`/api/v1/activities/${activityId}/sub-registrations`, data);
export const updateSubRegistration = (activityId: number, subId: number, data: unknown) => api.put(`/api/v1/activities/${activityId}/sub-registrations/${subId}`, data);
export const deleteSubRegistration = (activityId: number, subId: number) => api.delete(`/api/v1/activities/${activityId}/sub-registrations/${subId}`);

// Families
export const getFamilies = (params?: { page?: number; page_size?: number }) => api.get("/api/v1/families", { params });
export const getFamily = (id: number) => api.get(`/api/v1/families/${id}`);
export const createFamily = (data: unknown) => api.post("/api/v1/families", data);
export const updateFamily = (id: number, data: unknown) => api.put(`/api/v1/families/${id}`, data);
export const deleteFamily = (id: number) => api.delete(`/api/v1/families/${id}`);
export const addFamilyMember = (familyId: number, data: unknown) => api.post(`/api/v1/families/${familyId}/members`, data);
export const addPersonToFamily = (familyId: number, data: unknown) => api.post(`/api/v1/families/${familyId}/persons`, data);
export const createMembership = (familyId: number, data: unknown) => api.post(`/api/v1/families/${familyId}/memberships`, data);
export const deleteMembership = (membershipId: number) => api.delete(`/api/v1/memberships/${membershipId}`);
export const getMemberships = (year?: number) => api.get("/api/v1/memberships", { params: year ? { year } : {} });
export const assignBoardMember = (familyId: number, data: unknown) => api.put(`/api/v1/families/${familyId}/board-member`, data);

// Persons
export const listPersons = () => api.get("/api/v1/persons");
export const updatePerson = (personId: number, data: unknown) => api.put(`/api/v1/persons/${personId}`, data);
export const updatePersonAddress = (personId: number, data: unknown) => api.put(`/api/v1/persons/${personId}/address`, data);
export const updatePersonContacts = (personId: number, data: unknown) => api.put(`/api/v1/persons/${personId}/contacts`, data);
export const deletePerson = (personId: number) => api.delete(`/api/v1/persons/${personId}`);

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
export const requestLogin = (email: string) =>
  api.post("/api/v1/auth/request-login", { email });
export const verifyLoginToken = (token: string) =>
  api.get("/api/v1/auth/verify-login", { params: { token } });
export const getMe = () => api.get("/api/v1/auth/me");

// Admin
export const getStats = () => api.get("/api/v1/admin/stats");
