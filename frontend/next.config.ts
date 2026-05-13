import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    webpackBuildWorker: false,
  },
  // In dev, Next may proxy requests based on the request origin/host.
  // Allow common local origins so `next dev --hostname 127.0.0.1` works
  // when users access via http://localhost:3000 or http://127.0.0.1:3000.
  // Keep the LAN IP as well for dev on the local network.
  allowedDevOrigins: [
    "192.168.1.101",
    "localhost",
    "127.0.0.1",
    "100.89.134.45",
    "100.92.78.108",
    "89.116.191.185",
  ],
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "img.clerk.com",
      },
    ],
  },
};

export default nextConfig;
