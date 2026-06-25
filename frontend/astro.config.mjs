// @ts-check
import { defineConfig } from 'astro/config';

import react from '@astrojs/react';

import tailwindcss from '@tailwindcss/vite';

// Dogfooding: the same integration we ship on npm (astro-geoready).
// Skips the hand-curated public/llms.txt; generates the AI discovery files.
import geoReady from './integrations/astro-geoready/index.mjs';

// https://astro.build/config
export default defineConfig({
  site: 'https://geoready.dev',
  trailingSlash: 'always',
  integrations: [
    react(),
    geoReady({
      siteName: 'GeoReady',
      description:
        'AI visibility audit, monitoring, and citation tracking — built on the open-source GEO Optimizer engine.',
    }),
  ],

  vite: {
    plugins: [tailwindcss()],
    preview: {
      allowedHosts: ['geo-optimizer-skill-production.up.railway.app'],
    },
    server: {
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
        },
        '/badge': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
        },
        // AI Visibility OS platform API (Phase 0/1). Proxied so the browser
        // never needs CORS and never sees the API origin directly.
        '/papi': {
          target: 'http://localhost:8001',
          changeOrigin: true,
          secure: false,
          rewrite: (path) => path.replace(/^\/papi/, ''),
        },
      },
    },
  },
});

