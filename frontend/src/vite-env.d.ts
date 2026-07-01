/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_BELS_API: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*?worker&inline' {
  const ctor: new () => Worker
  export default ctor
}

declare module '*?worker' {
  const ctor: new () => Worker
  export default ctor
}
