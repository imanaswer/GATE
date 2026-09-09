import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    // In production `vercel.json` owns the /api/v1 rewrite. `next dev` knows
    // nothing about that file, so the API 404s locally unless you run
    // `vercel dev`. Pointing this at a locally-run FastAPI makes `pnpm dev`
    // self-sufficient — one server, one port, no proxy.
    //
    // Inert unless LOCAL_API_URL is set, so production behaviour is unchanged.
    // Ignored on Vercel even if the variable is set. It points at a loopback
    // address, so a copy of it reaching production would rewrite every API call
    // to 127.0.0.1 — which is exactly what happens when someone imports their
    // local .env into a project's settings.
    const api = process.env.VERCEL ? undefined : process.env.LOCAL_API_URL;
    if (!api) return [];
    return [{ source: "/api/v1/:path*", destination: `${api}/api/v1/:path*` }];
  },
};

export default nextConfig;
