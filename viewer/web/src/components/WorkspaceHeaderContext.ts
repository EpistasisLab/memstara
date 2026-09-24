import {createContext} from "react";

// Only the active workspace may populate its window header.
export const WorkspaceHeaderContext=createContext<HTMLDivElement|null>(null);
