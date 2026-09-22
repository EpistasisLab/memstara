import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useEffect, useState } from "react";
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
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize:50, pageIndex:0 } },
    autoResetPageIndex:false,
  });

  const {pageIndex,pageSize}=table.getState().pagination;
  const pages=Math.max(1,table.getPageCount());
  useEffect(()=>{if(pageIndex>=pages)table.setPageIndex(pages-1);},[pageIndex,pages,table]);
  return (
    <div className="min-w-0">
      {data.length>25 && <div className="table-pagination" aria-label="Table pages">
        <span>Rows {data.length ? pageIndex*pageSize+1 : 0}–{Math.min((pageIndex+1)*pageSize,data.length)} of {data.length.toLocaleString()}</span>
        <label>Rows per page <select value={pageSize} onChange={e=>{table.setPageSize(Number(e.target.value));table.setPageIndex(0);}}>{[25,50,100].map(n=><option key={n}>{n}</option>)}</select></label>
        <button disabled={!table.getCanPreviousPage()} onClick={()=>table.previousPage()}>Previous page</button>
        <span>Page {pageIndex+1} of {pages}</span>
        <button disabled={!table.getCanNextPage()} onClick={()=>table.nextPage()}>Next page</button>
      </div>}
    <div tabIndex={0} role="region" aria-label="Data table; scroll horizontally for all columns" className="overflow-x-auto rounded-lg border border-paper-line bg-white">
      <table className="telemetry-table w-full border-collapse text-sm">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-paper-line bg-paper/60">
              {hg.headers.map((h) => {
                const sorted = h.column.getIsSorted();
                return (
                  <th
                    key={h.id}
                    aria-sort={sorted==='asc'?'ascending':sorted==='desc'?'descending':'none'}
                    className={cn(
                      "px-3 py-2 text-left text-xs font-bold text-ink-soft",
                      h.column.getCanSort() && "cursor-pointer select-none hover:text-ink",
                      (h.column.columnDef.meta as { align?: string })?.align === "right" && "text-right",
                    )}
                  >
                    <button type="button" disabled={!h.column.getCanSort()} onClick={event=>{h.column.getToggleSortingHandler()?.(event);table.setPageIndex(0);}} className="inline-flex items-center gap-1 text-left">
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {h.column.getCanSort() &&
                        (sorted === "asc" ? <ArrowUp className="h-3 w-3" />
                         : sorted === "desc" ? <ArrowDown className="h-3 w-3" />
                         : <ChevronsUpDown className="h-3 w-3 opacity-30" />)}
                    </button>
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
                Nothing here
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div></div>
  );
}
