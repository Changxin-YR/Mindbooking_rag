export const shellStates = ['loading', 'empty', 'error', 'unauthorized', 'ready'] as const
export type ShellState = (typeof shellStates)[number]

export function parseShellState(value: unknown): ShellState {
  return typeof value === 'string' && shellStates.includes(value as ShellState) ? (value as ShellState) : 'ready'
}
