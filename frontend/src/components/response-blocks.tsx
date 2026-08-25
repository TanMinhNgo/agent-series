import { useState } from 'react';
import { CalendarClock, Check, X } from 'lucide-react';

import type { ResponseBlock } from '@/src/types';
import { Button } from '@/components/ui/button';

const limit = (value: number, minimum: number, maximum: number) =>
  Math.min(Math.max(value, minimum), maximum);

type ProposalAction = (proposalId: string, action: 'confirm' | 'dismiss') => void;

export function ResponseBlocks({
  blocks,
  onScheduleProposalAction,
}: {
  blocks: ResponseBlock[];
  onScheduleProposalAction?: ProposalAction;
}) {
  return (
    <div className="mt-5 space-y-4">
      {blocks.map((block, index) => {
        if (block.type === 'trig-circle') return <TrigCircle key={index} config={block.config} />;
        if (block.type === 'chart') return <Chart key={index} config={block.config} />;
        if (block.type === 'data-table') return <DataTable key={index} config={block.config} />;
        return <ScheduleProposal key={index} config={block.config} onAction={onScheduleProposalAction} />;
      })}
    </div>
  );
}

function ScheduleProposal({
  config,
  onAction,
}: {
  config: Extract<ResponseBlock, { type: 'schedule-proposal' }>['config'];
  onAction?: ProposalAction;
}) {
  const date = new Date(config.startsAt);
  const when = Number.isNaN(date.getTime())
    ? config.startsAt
    : new Intl.DateTimeFormat('vi-VN', {
        dateStyle: 'full',
        timeStyle: 'short',
        timeZone: config.timezone || 'Asia/Ho_Chi_Minh',
      }).format(date);
  const recurrence = { once: 'Một lần', daily: 'Mỗi ngày', weekly: 'Mỗi tuần' }[config.recurrence];
  const status = { pending: 'Chờ xác nhận', confirmed: 'Đã tạo lịch', dismissed: 'Đã hủy' }[config.status];
  return (
    <section className="rounded-2xl border border-primary/25 bg-primary/[.04] p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
          <CalendarClock size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">{config.title}</h3>
            <span className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground">{status}</span>
          </div>
          <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">{config.prompt}</p>
          <p className="mt-3 text-sm">
            <span className="text-muted-foreground">Chạy: </span>
            {when} · {recurrence}
          </p>
          {config.projectId ? (
            <p className="mt-1 text-xs text-muted-foreground">Thuộc dự án hiện tại</p>
          ) : null}
          {config.status === 'pending' && onAction ? (
            <div className="mt-4 flex flex-wrap gap-2">
              <Button size="sm" onClick={() => onAction(config.proposalId, 'confirm')}>
                <Check />
                Tạo lịch
              </Button>
              <Button size="sm" variant="outline" onClick={() => onAction(config.proposalId, 'dismiss')}>
                <X />
                Hủy
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function TrigCircle({ config }: { config: Extract<ResponseBlock, { type: 'trig-circle' }>['config'] }) {
  const [angle, setAngle] = useState(limit(config.angle ?? 45, 0, 360));
  const radius = limit(config.radius ?? 1, 0.1, 10);
  const radians = (angle * Math.PI) / 180;
  const sin = Math.sin(radians) * radius;
  const cos = Math.cos(radians) * radius;
  const center = 120;
  const drawingRadius = 78;
  const x = center + Math.cos(radians) * drawingRadius;
  const y = center - Math.sin(radians) * drawingRadius;
  return (
    <section className="overflow-hidden rounded-2xl border bg-card/45 p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="font-semibold">{config.title || 'Đường tròn lượng giác'}</h3>
        <span className="text-sm text-muted-foreground">θ = {angle.toFixed(0)}°</span>
      </div>
      <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_240px] sm:items-center">
        <div className="space-y-2 text-sm">
          <p>
            <strong>sin(θ)</strong> = {sin.toFixed(3)}
          </p>
          <p>
            <strong>cos(θ)</strong> = {cos.toFixed(3)}
          </p>
          <p className="text-muted-foreground">
            P = ({cos.toFixed(3)}, {sin.toFixed(3)})
          </p>
          <label className="mt-4 block text-xs font-medium text-muted-foreground" htmlFor="trig-angle">
            Góc θ
          </label>
          <input
            id="trig-angle"
            className="mt-2 w-full accent-primary"
            type="range"
            min="0"
            max="360"
            value={angle}
            onChange={(event) => setAngle(Number(event.target.value))}
          />
        </div>
        <svg
          viewBox="0 0 240 240"
          className="mx-auto w-full max-w-60"
          role="img"
          aria-label={`Đường tròn lượng giác góc ${angle} độ`}
        >
          <circle
            cx={center}
            cy={center}
            r={drawingRadius}
            fill="none"
            stroke="currentColor"
            className="text-border"
            strokeWidth="2"
          />
          <path
            d={`M42 ${center}H198M${center} 42V198`}
            className="text-muted-foreground/60"
            stroke="currentColor"
            strokeWidth="1"
          />
          <path
            d={`M${center} ${center}L${x} ${y}L${x} ${center}Z`}
            className="fill-primary/15 text-primary"
            stroke="currentColor"
            strokeWidth="2"
          />
          <circle cx={x} cy={y} r="5" className="fill-primary" />
        </svg>
      </div>
    </section>
  );
}

function Chart({ config }: { config: Extract<ResponseBlock, { type: 'chart' }>['config'] }) {
  const series = (config.series || [])
    .slice(0, 4)
    .map((item) => ({ ...item, values: (item.values || []).slice(0, 24) }));
  const values = series.flatMap((item) => item.values || []);
  if (!values.length) return null;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const width = 520;
  const height = 230;
  const padding = 26;
  const count = Math.max(...series.map((item) => item.values?.length || 0));
  return (
    <section className="overflow-hidden rounded-2xl border bg-card/45 p-4 sm:p-5">
      <h3 className="mb-3 font-semibold">{config.title || 'Biểu đồ'}</h3>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        role="img"
        aria-label={config.title || 'Biểu đồ dữ liệu'}
      >
        <path
          d={`M${padding} ${padding}V${height - padding}H${width - padding}`}
          className="text-border"
          stroke="currentColor"
        />
        {series.map((item, seriesIndex) => {
          const color = item.color || ['#dc9379', '#8bb4e8', '#82b38a', '#d4aa5b'][seriesIndex];
          const points = (item.values || [])
            .map(
              (value, index) =>
                `${padding + (index * (width - padding * 2)) / Math.max(count - 1, 1)},${height - padding - ((value - min) * (height - padding * 2)) / span}`,
            )
            .join(' ');
          if (config.kind === 'bar')
            return (item.values || []).map((value, index) => {
              const barWidth = (width - padding * 2) / Math.max(count, 1) / series.length;
              const x =
                padding + (index * (width - padding * 2)) / Math.max(count, 1) + seriesIndex * barWidth;
              const barHeight = ((value - min) * (height - padding * 2)) / span;
              return (
                <rect
                  key={`${seriesIndex}-${index}`}
                  x={x}
                  y={height - padding - barHeight}
                  width={barWidth - 2}
                  height={barHeight}
                  rx="2"
                  fill={color}
                />
              );
            });
          return (
            <polyline
              key={seriesIndex}
              fill="none"
              points={points}
              stroke={color}
              strokeWidth="3"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {series.map((item, index) => (
          <span key={index}>
            <i
              className="mr-1 inline-block size-2 rounded-full"
              style={{ background: item.color || ['#dc9379', '#8bb4e8', '#82b38a', '#d4aa5b'][index] }}
            />
            {item.label || `Chuỗi ${index + 1}`}
          </span>
        ))}
      </div>
    </section>
  );
}

function DataTable({ config }: { config: Extract<ResponseBlock, { type: 'data-table' }>['config'] }) {
  const columns = (config.columns || []).slice(0, 8);
  const rows = (config.rows || []).slice(0, 30);
  if (!columns.length) return null;
  return (
    <section className="overflow-x-auto rounded-2xl border bg-card/45 p-4 sm:p-5">
      <h3 className="mb-3 font-semibold">{config.title || 'Bảng dữ liệu'}</h3>
      <table className="w-full min-w-max text-left text-sm">
        <thead className="border-b text-muted-foreground">
          <tr>
            {columns.map((column) => (
              <th key={column} className="px-3 py-2 font-medium">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-b last:border-0">
              {columns.map((_, columnIndex) => (
                <td key={columnIndex} className="px-3 py-2">
                  {row[columnIndex] ?? '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
