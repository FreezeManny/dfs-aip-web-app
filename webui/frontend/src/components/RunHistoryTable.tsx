import { useEffect, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { flexRender, useTable } from "@tanstack/react-table";
import { features, getPaginationItems, type Features } from "@/lib/table";
import { api, type RunSummary, type RunDetail } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { CheckCircle, AlertCircle, Loader2, X } from "lucide-react";

const LOG_PAGE_SIZE = 200;

type LogEntry = RunDetail["logs"][string][number];

function ProfileLogCard({
  profileName,
  messages,
}: {
  profileName: string;
  messages: LogEntry[];
}) {
  const reversed = useMemo(() => [...messages].reverse(), [messages]);
  const [visibleCount, setVisibleCount] = useState(LOG_PAGE_SIZE);

  const visibleMessages = reversed.slice(0, visibleCount);

  return (
    <Card className="border">
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="text-base">{profileName}</CardTitle>
        <span className="text-xs text-muted-foreground">
          {messages.length.toLocaleString()} {messages.length === 1 ? "entry" : "entries"}
        </span>
      </CardHeader>
      <CardContent>
        <div
          className="text-sm space-y-1.5 font-mono bg-muted/50 p-3 rounded max-h-80 overflow-y-auto"
          onScroll={(e) => {
            if (visibleCount >= reversed.length) return;
            const el = e.currentTarget;
            if (el.scrollTop + el.clientHeight >= el.scrollHeight - 150) {
              setVisibleCount((c) => Math.min(c + LOG_PAGE_SIZE, reversed.length));
            }
          }}
        >
          {visibleMessages.map((msg, i) => (
            <div
              key={i}
              className={
                msg.status === "error"
                  ? "text-red-600"
                  : msg.status === "success"
                  ? "text-green-600"
                  : "text-muted-foreground"
              }
            >
              <span className="font-semibold">[{msg.stage}]</span> {msg.message}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

interface RunHistoryTableProps {
  refreshTrigger?: number;
}

export function RunHistoryTable({ refreshTrigger = 0 }: RunHistoryTableProps) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunDetail, setSelectedRunDetail] = useState<RunDetail | null>(null);
  const [loadingRunId, setLoadingRunId] = useState<string | null>(null);

  useEffect(() => {
    api
      .getRuns()
      .then(setRuns)
      .catch((e) => console.error("Failed to load runs:", e));
  }, [refreshTrigger]);

  const viewRunDetail = async (runId: string) => {
    setLoadingRunId(runId);
    try {
      const detail = await api.getRun(runId);
      setSelectedRunDetail(detail);
    } catch (e) {
      console.error("Failed to load run detail:", e);
    } finally {
      setLoadingRunId(null);
    }
  };

  const columns: ColumnDef<Features, RunSummary>[] = [
    {
      accessorKey: "timestamp",
      header: "Time",
      filterFn: (row, columnId, filterValue) => {
        const raw = String(row.getValue(columnId) ?? "");
        const formatted = new Date(raw).toLocaleString();
        const needle = String(filterValue ?? "").toLowerCase();
        return raw.toLowerCase().includes(needle) || formatted.toLowerCase().includes(needle);
      },
      cell: ({ row }) => {
        const isoString = row.getValue("timestamp") as string;
        return new Date(isoString).toLocaleString();
      },
    },
    {
      accessorKey: "status",
      header: "Status",
      filterFn: "equalsString",
      cell: ({ row }) => {
        const status = row.getValue("status") as RunSummary["status"];
        return (
          <div className="flex items-center gap-2">
            {status === "running" ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                <span className="text-blue-600 font-medium">Running</span>
              </>
            ) : status === "success" ? (
              <>
                <CheckCircle className="h-4 w-4 text-green-600" />
                <span className="text-green-600 font-medium">Success</span>
              </>
            ) : (
              <>
                <AlertCircle className="h-4 w-4 text-red-600" />
                <span className="text-red-600 font-medium">Error</span>
              </>
            )}
          </div>
        );
      },
    },
    {
      accessorKey: "pdf_created",
      header: "New PDFs",
      filterFn: (row, columnId, filterValue) => {
        const created = Boolean(row.getValue(columnId));
        return filterValue === "yes" ? created : !created;
      },
      cell: ({ row }) => {
        const pdfCreated = row.getValue("pdf_created") as boolean;
        return pdfCreated ? (
          <Badge variant="default" className="bg-blue-600 hover:bg-blue-700">
            New PDF
          </Badge>
        ) : (
          <span className="text-muted-foreground text-sm">No changes</span>
        );
      },
    },
    {
      accessorKey: "profiles",
      header: "Profiles",
      filterFn: (row, columnId, filterValue) => {
        const profiles = (row.getValue(columnId) as string[]) ?? [];
        const needle = String(filterValue ?? "").toLowerCase();
        return profiles.some((p) => p.toLowerCase().includes(needle));
      },
      cell: ({ row }) => {
        const profiles = row.getValue("profiles") as string[];
        return (
          <div className="flex flex-wrap gap-1">
            {profiles.map((profile) => (
              <span
                key={profile}
                className="bg-secondary text-secondary-foreground px-2 py-0.5 rounded text-xs"
              >
                {profile}
              </span>
            ))}
          </div>
        );
      },
    },
    {
      id: "actions",
      enableColumnFilter: false,
      cell: ({ row }) => {
        const isLoading = loadingRunId === row.original.id;
        return (
          <Button
            onClick={() => viewRunDetail(row.original.id)}
            variant="outline"
            size="sm"
            disabled={isLoading}
          >
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            View Logs
          </Button>
        );
      },
    },
  ];

  const table = useTable({
    features,
    data: runs,
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
    <>
      <Card>
        <CardHeader>
          <CardTitle>Run History</CardTitle>
        </CardHeader>
        <CardContent>
          {runs.length === 0 ? (
            <p className="text-muted-foreground text-sm">No runs yet</p>
          ) : (
            <div className="overflow-hidden rounded-md border">
              <Table>
                <TableHeader>
                  {table.getHeaderGroups().map((headerGroup) => (
                    <TableRow key={headerGroup.id}>
                      {headerGroup.headers.map((header) => {
                        return (
                          <TableHead key={header.id}>
                            {header.isPlaceholder
                              ? null
                              : flexRender(
                                  header.column.columnDef.header,
                                  header.getContext()
                                )}
                          </TableHead>
                        );
                      })}
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
                      if (column.id === "status") {
                        return (
                          <TableHead key={header.id} className="py-1.5">
                            <Select
                              value={(column.getFilterValue() as string) ?? "all"}
                              onValueChange={(val) => {
                                column.setFilterValue(val === "all" ? undefined : val);
                                table.setPageIndex(0);
                              }}
                            >
                              <SelectTrigger className="h-7 text-xs">
                                <SelectValue placeholder="All" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="all">All</SelectItem>
                                <SelectItem value="success">Success</SelectItem>
                                <SelectItem value="error">Error</SelectItem>
                                <SelectItem value="running">Running</SelectItem>
                              </SelectContent>
                            </Select>
                          </TableHead>
                        );
                      }
                      if (column.id === "pdf_created") {
                        return (
                          <TableHead key={header.id} className="py-1.5">
                            <Select
                              value={(column.getFilterValue() as string) ?? "all"}
                              onValueChange={(val) => {
                                column.setFilterValue(val === "all" ? undefined : val);
                                table.setPageIndex(0);
                              }}
                            >
                              <SelectTrigger className="h-7 text-xs">
                                <SelectValue placeholder="All" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="all">All</SelectItem>
                                <SelectItem value="yes">New PDF</SelectItem>
                                <SelectItem value="no">No changes</SelectItem>
                              </SelectContent>
                            </Select>
                          </TableHead>
                        );
                      }
                      const placeholders: Record<string, string> = {
                        timestamp: "Filter time...",
                        profiles: "Filter profile...",
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
                        No matching runs
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          )}
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
        </CardContent>
      </Card>

      {selectedRunDetail && (
        <Dialog open={!!selectedRunDetail} onOpenChange={() => setSelectedRunDetail(null)}>
          <DialogContent className="max-w-5xl max-h-[85vh] flex flex-col">
            <DialogHeader className="shrink-0">
              <DialogTitle className="text-lg">Run Logs - {new Date(selectedRunDetail.timestamp).toLocaleString()}</DialogTitle>
            </DialogHeader>

            <div className="overflow-y-auto flex-1 space-y-3 pr-4">
              {Object.entries(selectedRunDetail.logs).map(([profileName, messages]) => (
                <ProfileLogCard
                  key={profileName}
                  profileName={profileName}
                  messages={messages}
                />
              ))}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
