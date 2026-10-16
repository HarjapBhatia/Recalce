/**
 * src/lib/utils.js
 * Class name merging utility. Combines clsx and tailwind-merge so
 * conditional class lists are deduplicated cleanly.
 */

import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}
