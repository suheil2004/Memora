export const MAX_QUERY_LENGTH = 2000;
export const MIN_TOP_K = 1;
export const MAX_TOP_K = 10;
export const MAX_IMPORT_FILES = 10;
export const MIN_LOCAL_TOKEN_LENGTH = 32;

export function isAllowedBackendUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" &&
      (url.hostname === "127.0.0.1" || url.hostname === "localhost") &&
      url.port === "8765" &&
      url.pathname === "/" &&
      !url.username && !url.password && !url.search && !url.hash;
  } catch {
    return false;
  }
}
