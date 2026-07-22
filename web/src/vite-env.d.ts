/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_OPS_USER?: string
  readonly VITE_OPS_PASSWORD?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
