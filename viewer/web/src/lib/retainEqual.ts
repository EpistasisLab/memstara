/** Preserve subscribers' references when a polled JSON payload has not changed. */
export function retainEqual<T>(previous: T, incoming: T): T {
 return previous === incoming || JSON.stringify(previous) === JSON.stringify(incoming) ? previous : incoming;
}
