// @ts-check
import { defineConfig } from 'astro/config';

import react from '@astrojs/react';

import tailwindcss from '@tailwindcss/vite';

// Dogfooding: the same integration we ship on npm (astro-geoready).
// Skips the hand-curated public/llms.txt; generates the AI discovery files.
import geoReady from './integrations/astro-geoready/index.mjs';

// https://astro.build/config
export default defineConfig({
  site: 'https://visibletoai.io',
  trailingSlash: 'always',
  integrations: [
    react(),
    geoReady({
      siteName: 'Visible to AI',
      description:
        'See what AI says about your business — and fix what’s costing you customers.',
    }),
  ],

  vite: {
    plugins: [tailwindcss()],
    preview: {
      // Leading dot = wildcard for that domain, so any Railway subdomain works
      // (avoids surprises on rename / preview environments / redeploys).
      allowedHosts: [
        '.up.railway.app',
        'visibletoai.io',
        'www.visibletoai.io',
      ],
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

