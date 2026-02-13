const UNITS = ["B", "KB", "MB", "GB", "TB", "PB"];

export function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);
  return `${value.toFixed(decimals)} ${UNITS[i] ?? "??"}`;
}

export const TRAFFIC_COLORS = {
  upload: "#13c2c2",
  download: "#1677ff",
} as const;
