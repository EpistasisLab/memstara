import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useState } from "react";
import { cn } from "../lib/cn";

/** One sortable table used by every tab, so the tabs differ in content rather than in
 *  how a table behaves. */
export default function DataTable<T>({
  columns,
  data,
  initialSorting = [],
  rowClass,
}: {
  columns: ColumnDef<T, any>[];
  data: T[];
  initialSorting?: SortingState;
  rowClass?: (row: T) => string | undefined;
}) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="overflow-x-auto rounded-lg border border-paper-line bg-white">
      <table className="w-full border-collapse text-sm">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-paper-line bg-paper/60">
              {hg.headers.map((h) => {
                const sorted = h.column.getIsSorted();
                return (
                  <th
                    key={h.id}
                    onClick={h.column.getToggleSortingHandler()}
                    className={cn(
                      "px-3 py-2 text-left text-xs font-bold text-ink-soft",
                      h.column.getCanSort() && "cursor-pointer select-none hover:text-ink",
                      (h.column.columnDef.meta as { align?: string })?.align === "right" && "text-right",
                    )}
                  >
                    <span className="inline-flex items-center gap-1">
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {h.column.getCanSort() &&
                        (sorted === "asc" ? <ArrowUp className="h-3 w-3" />
                         : sorted === "desc" ? <ArrowDown className="h-3 w-3" />
                         : <ChevronsUpDown className="h-3 w-3 opacity-30" />)}
                    </span>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              className={cn("border-b border-paper-line/60 last:border-0", rowClass?.(row.original))}
            >
              {row.getVisibleCells().map((cell) => (
                <td
                  key={cell.id}
                  className={cn(
                    "px-3 py-2",
                    (cell.column.columnDef.meta as { align?: string })?.align === "right" && "text-right",
                  )}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
          {data.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="px-3 py-8 text-center text-ink-faint">
                내용 없음
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
