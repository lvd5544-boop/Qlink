import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'e2e-report', 'playwright-report', 'test-results']),
  {
    files: ['**/*.{js,jsx}'],
    ignores: ['e2e/**', 'playwright.config.mjs'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
  {
    files: ['e2e/**/*.{js,mjs}', 'playwright.config.mjs'],
    languageOptions: {
      globals: globals.node,
    },
  },
])
