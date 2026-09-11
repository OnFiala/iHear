import type { NextConfig } from "next";
const config: NextConfig = {
  poweredByHeader: false,
  agentRules: false,
  allowedDevOrigins: process.env.APP_PUBLIC_ORIGIN
    ? [new URL(process.env.APP_PUBLIC_ORIGIN).hostname]
    : [],
  serverExternalPackages: ["pg"],
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          {
            key: "Permissions-Policy",
            value: "camera=(self), microphone=(self), geolocation=()",
          },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};
export default config;
