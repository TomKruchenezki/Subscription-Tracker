import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // No rewrites or proxies to external services — privacy constraint.
  // All API calls go directly from the browser to FastAPI on localhost:8000.
};

export default nextConfig;
