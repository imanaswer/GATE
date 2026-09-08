import type { MetadataRoute } from "next";

/**
 * The admin panel is behind authentication, and a verification page carries a
 * student's name and college. Neither belongs in a search index — the verify
 * URL is meant to be reached from the QR code or the link on the certificate,
 * by someone who was handed one.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", disallow: ["/admin", "/verify", "/arena", "/api"] },
  };
}
