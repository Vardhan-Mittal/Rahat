import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The repo root has its own package.json; pin resolution to this app so only one copy of each package loads.
  turbopack: { root: path.resolve(__dirname) },
};

export default nextConfig;
