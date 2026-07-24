import { type ReactNode, useState } from 'react'

type Column<T> = {
  key: string
  header: string
  render?: (row: T) => ReactNode
  sortable?: boolean
}

type TableProps<T> = {
  columns: Column<T>[]
  data: T[]
  sortable?: boolean
  emptyMessage?: string
}

export default function Table<T extends Record<string, unknown>>({
  columns,
  data,
  emptyMessage = 'No data',
}: TableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const handleSort = (col: Column<T>) => {
    if (!col.sortable) return
    if (sortKey === col.key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(col.key)
      setSortDir('asc')
    }
  }

  const sorted = sortKey
    ? [...data].sort((a, b) => {
        const av = a[sortKey]
        const bv = b[sortKey]
        if (av == null) return 1
        if (bv == null) return -1
        const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true })
        return sortDir === 'asc' ? cmp : -cmp
      })
    : data

  if (data.length === 0) {
    return (
      <div className="border border-border rounded-lg overflow-hidden">
        <div className="p-8 text-center text-fg-muted text-sm">{emptyMessage}</div>
      </div>
    )
  }

  return (
    <div className="border border-border rounded-lg overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-bg-subtle border-b border-border">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-4 py-3 text-left font-medium text-fg-muted ${
                  col.sortable ? 'cursor-pointer select-none hover:text-fg' : ''
                }`}
                onClick={() => handleSort(col)}
              >
                <span className="inline-flex items-center gap-1">
                  {col.header}
                  {col.sortable && sortKey === col.key && (
                    <span className="text-xs">{sortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr
              key={i}
              className={`border-b border-border last:border-0 hover:bg-bg-subtle transition-colors ${
                i % 2 === 1 ? 'bg-bg-subtle/50' : ''
              }`}
            >
              {columns.map((col) => (
                <td key={col.key} className="px-4 py-3 text-fg">
                  {col.render ? col.render(row) : String(row[col.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
