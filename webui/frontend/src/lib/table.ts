import {
  columnFilteringFeature,
  columnVisibilityFeature,
  createFilteredRowModel,
  createPaginatedRowModel,
  filterFn_equalsString,
  filterFn_includesString,
  rowPaginationFeature,
  tableFeatures,
} from "@tanstack/react-table";

/**
 * Feature set shared by every table in the app.
 *
 * v9 no longer bundles features automatically: a table only has the APIs whose
 * features it registers here, and a missing method at runtime almost always
 * means a missing registration rather than a removed API.
 *
 * Shared rather than declared per component so the `TFeatures` type argument
 * threaded through `ColumnDef` cannot drift between tables.
 */
export const features = tableFeatures({
  columnVisibilityFeature,
  columnFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  filterFns: {
    includesString: filterFn_includesString,
    equalsString: filterFn_equalsString,
  },
  rowPaginationFeature,
  paginatedRowModel: createPaginatedRowModel(),
});

export type Features = typeof features;

/**
 * Compute 0-based page indices and ellipsis markers for a pagination bar.
 */
export function getPaginationItems(
  pageIndex: number,
  pageCount: number
): Array<number | "ellipsis"> {
  if (pageCount <= 7) {
    return Array.from({ length: pageCount }, (_, i) => i);
  }

  const pages = new Set<number>([
    0,
    pageCount - 1,
    Math.max(0, pageIndex - 1),
    pageIndex,
    Math.min(pageCount - 1, pageIndex + 1),
  ]);
  if (pageIndex <= 2) {
    pages.add(1);
    pages.add(2);
    pages.add(3);
  } else if (pageIndex >= pageCount - 3) {
    pages.add(pageCount - 2);
    pages.add(pageCount - 3);
    pages.add(pageCount - 4);
  }

  const sorted = Array.from(pages).sort((a, b) => a - b);
  const items: Array<number | "ellipsis"> = [];

  for (let i = 0; i < sorted.length; i++) {
    const current = sorted[i];
    const prev = sorted[i - 1];
    if (prev !== undefined) {
      if (current - prev === 2) {
        items.push(prev + 1);
      } else if (current - prev > 2) {
        items.push("ellipsis");
      }
    }
    items.push(current);
  }

  return items;
}
