/**
 * One install line per language, for the cards on the home page and at the top of /install/
 * (LanguageInstalls.astro). Each package is on its language's own registry, so the line is the one
 * a developer of that language already types; /install/#<id> has the swap, the notes and the API.
 */
import type { MarkName } from './brands';

export interface LanguageInstall {
  /** The section on /install/. */
  id: string;
  title: string;
  mark: MarkName;
  /** The card's accent: the language's own color, lightened where its mark is dark. */
  accent: string;
  registry: { name: string; mark?: MarkName; url: string };
  command: string;
  /** The same install for other tools of that language. */
  also?: string[];
  /** The BLAKE3 package it stands in for. */
  replaces: string;
}

export const LANGUAGE_INSTALLS: readonly LanguageInstall[] = [
  {
    id: 'rust',
    title: 'Rust',
    mark: 'rust',
    accent: '#f46623',
    registry: { name: 'crates.io', url: 'https://crates.io/crates/turboblake' },
    command: 'cargo add turboblake',
    replaces: 'blake3',
  },
  {
    id: 'python',
    title: 'Python',
    mark: 'python',
    accent: '#5a9fd4',
    registry: { name: 'PyPI', mark: 'pypi', url: 'https://pypi.org/project/turboblake/' },
    command: 'pip install turboblake',
    also: ['uv add turboblake'],
    replaces: 'blake3',
  },
  {
    id: 'node',
    title: 'TypeScript',
    mark: 'typescript',
    accent: '#4a9be8',
    registry: { name: 'npm', mark: 'npm', url: 'https://www.npmjs.com/package/turboblake' },
    command: 'npm install turboblake',
    also: ['bun add turboblake', 'deno add npm:turboblake'],
    replaces: '@noble/hashes, blake3',
  },
  {
    id: 'go',
    title: 'Go',
    mark: 'go',
    accent: '#00add8',
    registry: { name: 'Go modules', url: 'https://pkg.go.dev/github.com/gunta/turboblake/bend/go' },
    command: 'go get github.com/gunta/turboblake/bend/go',
    replaces: 'lukechampine.com/blake3, zeebo/blake3',
  },
  {
    id: 'c',
    title: 'C',
    mark: 'c',
    accent: '#a8b9cc',
    registry: { name: 'Homebrew', mark: 'homebrew', url: 'https://github.com/gunta/homebrew-tap' },
    command: 'brew install gunta/tap/libturboblake',
    also: ['cmake -S bend/lib'],
    replaces: 'blake3.h',
  },
];
