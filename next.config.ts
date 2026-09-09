import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    // In production `vercel.json` owns the /api/v1 rewrite. `next dev` knows
    // nothing about that file, so the API 404s locally unless you run
    // `vercel dev`. Pointing this at a locally-run FastAPI makes `pnpm dev`
    // self-sufficient — one server, one port, no proxy.
    //
    // Inert unless LOCAL_API_URL is set, so production behaviour is unchanged.
    const api = process.env.LOCAL_API_URL;
    if (!api) return [];
    return [{ source: "/api/v1/:path*", destination: `${api}/api/v1/:path*` }];
  },
};

export default nextConfig;
