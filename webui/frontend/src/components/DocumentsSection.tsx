import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { api } from "@/lib/api";
import type { Document } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { Download, RefreshCw, Trash2, FileText } from "lucide-react";
import { toast } from "sonner";

interface DocumentsSectionProps {
  documents: Document[];
  onDocumentsChange: () => void;
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

export function DocumentsSection({ documents, onDocumentsChange }: DocumentsSectionProps) {
  const handleDeleteDocument = async (profile: string, filename: string) => {
    if (!confirm(`Delete ${filename}?`)) return;
    await api.deleteDocument(profile, filename);
    onDocumentsChange();
  };

  const handleForceFetch = async () => {
    try {
      const result = await api.triggerUpdate();
      if (result.status === "started") {
        toast.success("Update started", {
          description: "Charts are being fetched in the background",
        });
      } else if (result.status === "already_running") {
        toast.warning("Update already running", {
          description: "Please wait for the current update to finish",
        });
      }
    } catch (error) {
      toast.error("Failed to start update", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    }
  };

  const filteredDocuments = useMemo(
    () => documents.filter((d) => !d.is_ocr),
    [documents]
  );

  const columns: ColumnDef<Document>[] = useMemo(
    () => [
      {
        accessorKey: "profile",
        header: "Profile",
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
      },
      {
        accessorKey: "size",
        header: "Size",
        cell: ({ row }) => formatBytes(row.getValue("size")),
      },
      {
        accessorKey: "modified",
        header: "Date",
        cell: ({ row }) => formatDate(row.getValue("modified")),
      },
      {
        id: "actions",
        header: () => <div className="text-right">Actions</div>,
        cell: ({ row }) => {
          const d = row.original;
          const ocrDoc = documents.find(
            (doc) => doc.profile === d.profile && doc.airac_date === d.airac_date && doc.is_ocr
          );
          return (
            <div className="text-right space-x-2">
              <Button size="sm" variant="outline" asChild>
                <a href={api.getDocumentUrl(d.path)} target="_blank" rel="noopener">
                  <Download className="mr-1 h-4 w-4" /> PDF
                </a>
              </Button>
              <Button
                size="sm"
                variant={ocrDoc ? "default" : "secondary"}
                disabled={!ocrDoc}
                asChild={!!ocrDoc}
              >
                {ocrDoc ? (
                  <a href={api.getDocumentUrl(ocrDoc.path)} target="_blank" rel="noopener">
                    <Download className="mr-1 h-4 w-4" /> OCR
                  </a>
                ) : (
                  <span>
                    <Download className="mr-1 h-4 w-4" /> OCR
                  </span>
                )}
              </Button>
              <Button size="sm" variant="destructive" onClick={() => handleDeleteDocument(d.profile, d.name)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          );
        },
      },
    ],
    [documents]
  );

  const table = useReactTable({
    data: filteredDocuments,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: {
      pagination: {
        pageSize: 10,
      },
    },
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Documents</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={onDocumentsChange}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
          <Button size="sm" onClick={handleForceFetch} className="bg-blue-600 hover:bg-blue-700">
            Force Fetch Charts
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {filteredDocuments.length === 0 ? (
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
                        No documents yet
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
            {filteredDocuments.length > 10 && (
              <div className="flex items-center justify-between pt-4">
                <div className="text-sm text-muted-foreground">
                  Page {table.getState().pagination.pageIndex + 1} of{" "}
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
