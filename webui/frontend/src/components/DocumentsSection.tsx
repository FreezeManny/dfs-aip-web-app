import { useCallback, useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { flexRender, useTable } from "@tanstack/react-table";
import { features, getPaginationItems, type Features } from "@/lib/table";
import { api } from "@/lib/api";
import type { Document } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { Archive, Download, Loader2, Trash2, FileText, X } from "lucide-react";
import { toast } from "sonner";

interface DocumentsSectionProps {
  documents: Document[];
  onDocumentsChange: () => void;
  /** True while an update (or cleanup) is running on the server. */
  running: boolean;
  /** Called after an update was started so the parent starts polling for its status. */
  onUpdateStarted: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function DocumentsSection({
  documents,
  onDocumentsChange,
  running,
  onUpdateStarted,
}: DocumentsSectionProps) {
  const handleDeleteDocument = useCallback(
    async (doc: Document) => {
      if (!confirm(`Delete ${doc.name}?`)) return;
      await api.deleteDocument(doc.id);
      onDocumentsChange();
    },
    [onDocumentsChange]
  );

  const handleDownloadDocument = useCallback(async (doc: Document, zip: boolean) => {
    try {
      await api.downloadDocument(doc.id, doc.name, zip);
    } catch (error) {
      toast.error("Failed to download document", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    }
  }, []);

  const startUpdate = useCallback(async () => {
    try {
      const result = await api.triggerUpdate();
      if (result.status === "started") {
        toast.success("Update started", {
          description: "Documents are being fetched in the background",
        });
      } else {
        toast.warning("Update already running", {
          description: "Please wait for the current update to finish",
        });
      }
      onUpdateStarted();
    } catch (error) {
      toast.error("Failed to start update", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    }
  }, [onUpdateStarted]);

  const columns: ColumnDef<Features, Document>[] = useMemo(
    () => [
      {
        accessorKey: "profile",
        header: "Profile",
        filterFn: "includesString",
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground" />
            {row.getValue("profile")}
          </div>
        ),
      },
      {
        accessorKey: "airac_date",
        header: "AIRAC",
        filterFn: "includesString",
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            {row.getValue("airac_date")}
            {!row.original.is_ocr && (
              <Badge variant="secondary" title="OCR has not completed for this document">
                No OCR
              </Badge>
            )}
          </div>
        ),
      },
      {
        accessorKey: "size",
        header: "Size",
        enableColumnFilter: false,
        cell: ({ row }) => formatBytes(row.getValue("size")),
      },
      {
        accessorKey: "modified",
        header: "Date",
        filterFn: (row, columnId, filterValue) => {
          const raw = String(row.getValue(columnId) ?? "");
          const formatted = formatDate(raw);
          const needle = String(filterValue ?? "").toLowerCase();
          return raw.toLowerCase().includes(needle) || formatted.toLowerCase().includes(needle);
        },
        cell: ({ row }) => formatDate(row.getValue("modified")),
      },
      {
        id: "actions",
        enableColumnFilter: false,
        header: () => <div className="text-right">Actions</div>,
        cell: ({ row }) => {
          const d = row.original;
          return (
            <div className="flex flex-wrap justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => void handleDownloadDocument(d, false)}>
                <Download className="mr-1 h-4 w-4" /> PDF
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => void handleDownloadDocument(d, true)}
                title="Download as ZIP (saves as a file on mobile instead of opening a preview)"
              >
                <Archive className="mr-1 h-4 w-4" /> ZIP
              </Button>
              <Button size="sm" variant="destructive" onClick={() => void handleDeleteDocument(d)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          );
        },
      },
    ],
    [handleDeleteDocument, handleDownloadDocument]
  );

  const table = useTable({
    features,
    data: documents,
    columns,
    initialState: {
      pagination: {
        pageIndex: 0,
        pageSize: 10,
      },
    },
  });

  const hasActiveFilters = table.state.columnFilters.length > 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Documents</CardTitle>
        <Button
          size="sm"
          disabled={running}
          onClick={() => void startUpdate()}
          className="bg-blue-600 hover:bg-blue-700"
        >
          {running && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {running ? "Updating..." : "Check for updates"}
        </Button>
      </CardHeader>
      <CardContent>
        {documents.length === 0 ? (
          <p className="text-muted-foreground text-center py-4">No documents yet</p>
        ) : (
          <>
            <div className="overflow-hidden rounded-md border">
              <Table>
                <TableHeader>
                  {table.getHeaderGroups().map((headerGroup) => (
                    <TableRow key={headerGroup.id}>
                      {headerGroup.headers.map((header) => (
                        <TableHead key={header.id}>
                          {header.isPlaceholder
                            ? null
                            : flexRender(
                                header.column.columnDef.header,
                                header.getContext()
                              )}
                        </TableHead>
                      ))}
                    </TableRow>
                  ))}
                  <TableRow className="bg-muted/30 hover:bg-muted/30">
                    {table.getHeaderGroups()[0]?.headers.map((header) => {
                      const column = header.column;
                      if (column.id === "actions") {
                        return (
                          <TableHead key={header.id} className="py-1.5 text-right">
                            {hasActiveFilters && (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 px-2 text-xs"
                                onClick={() => {
                                  table.resetColumnFilters();
                                  table.setPageIndex(0);
                                }}
                              >
                                <X className="mr-1 h-3 w-3" /> Clear
                              </Button>
                            )}
                          </TableHead>
                        );
                      }
                      if (!column.getCanFilter()) {
                        return <TableHead key={header.id} className="py-1.5" />;
                      }
                      const placeholders: Record<string, string> = {
                        profile: "Filter profile...",
                        airac_date: "Filter AIRAC...",
                        modified: "Filter date...",
                      };
                      return (
                        <TableHead key={header.id} className="py-1.5">
                          <Input
                            placeholder={placeholders[column.id] ?? "Filter..."}
                            value={(column.getFilterValue() as string) ?? ""}
                            onChange={(e) => {
                              column.setFilterValue(e.target.value || undefined);
                              table.setPageIndex(0);
                            }}
                            className="h-7 text-xs"
                          />
                        </TableHead>
                      );
                    })}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {table.getRowModel().rows?.length ? (
                    table.getRowModel().rows.map((row) => (
                      <TableRow key={row.id}>
                        {row.getVisibleCells().map((cell) => (
                          <TableCell key={cell.id}>
                            {flexRender(
                              cell.column.columnDef.cell,
                              cell.getContext()
                            )}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell
                        colSpan={columns.length}
                        className="h-24 text-center text-muted-foreground"
                      >
                        No matching documents
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
            {table.getPageCount() > 1 && (
              <div className="flex items-center justify-between pt-4">
                <div className="text-sm text-muted-foreground">
                  Page {table.state.pagination.pageIndex + 1} of{" "}
                  {table.getPageCount()}
                </div>
                <Pagination className="mx-0 w-auto">
                  <PaginationContent>
                    <PaginationItem>
                      <PaginationPrevious
                        href="#"
                        onClick={(e) => {
                          e.preventDefault();
                          table.previousPage();
                        }}
                        className={!table.getCanPreviousPage() ? "pointer-events-none opacity-50" : "cursor-pointer"}
                      />
                    </PaginationItem>
                    {getPaginationItems(
                      table.state.pagination.pageIndex,
                      table.getPageCount()
                    ).map((item, idx) =>
                      item === "ellipsis" ? (
                        <PaginationItem key={`ellipsis-${idx}`}>
                          <PaginationEllipsis />
                        </PaginationItem>
                      ) : (
                        <PaginationItem key={item}>
                          <PaginationLink
                            href="#"
                            isActive={item === table.state.pagination.pageIndex}
                            onClick={(e) => {
                              e.preventDefault();
                              table.setPageIndex(item);
                            }}
                            className="cursor-pointer"
                          >
                            {item + 1}
                          </PaginationLink>
                        </PaginationItem>
                      )
                    )}
                    <PaginationItem>
                      <PaginationNext
                        href="#"
                        onClick={(e) => {
                          e.preventDefault();
                          table.nextPage();
                        }}
                        className={!table.getCanNextPage() ? "pointer-events-none opacity-50" : "cursor-pointer"}
                      />
                    </PaginationItem>
                  </PaginationContent>
                </Pagination>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
