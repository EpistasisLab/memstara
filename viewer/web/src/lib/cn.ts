import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** The usual Tailwind class merger — later utilities win over earlier ones. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
