import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  transpilePackages: ["react-day-picker"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_URL}/:path*`,
      },
    ]
  },
}

export default nextConfig
