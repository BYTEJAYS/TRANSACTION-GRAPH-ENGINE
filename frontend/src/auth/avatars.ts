// Animal avatar characters for investigators. Keys must match backend (auth/store.py AVATARS).
export interface AvatarOption { key: string; glyph: string; label: string }

export const AVATARS: AvatarOption[] = [
  { key: 'fox',     glyph: '🦊', label: 'Fox' },
  { key: 'wolf',    glyph: '🐺', label: 'Wolf' },
  { key: 'cat',     glyph: '🐱', label: 'Cat' },
  { key: 'dog',     glyph: '🐶', label: 'Dog' },
  { key: 'owl',     glyph: '🦉', label: 'Owl' },
  { key: 'tiger',   glyph: '🐯', label: 'Tiger' },
  { key: 'lion',    glyph: '🦁', label: 'Lion' },
  { key: 'bear',    glyph: '🐻', label: 'Bear' },
  { key: 'panda',   glyph: '🐼', label: 'Panda' },
  { key: 'raccoon', glyph: '🦝', label: 'Raccoon' },
  { key: 'eagle',   glyph: '🦅', label: 'Eagle' },
  { key: 'leopard', glyph: '🐆', label: 'Leopard' },
]

const BY_KEY: Record<string, string> = Object.fromEntries(AVATARS.map(a => [a.key, a.glyph]))

export function avatarGlyph(key?: string): string {
  return (key && BY_KEY[key]) || '🦊'
}
