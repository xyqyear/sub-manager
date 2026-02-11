import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 10_000,
});

export default api;
