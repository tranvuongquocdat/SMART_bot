import { BarChart, RankBars } from '@/components/charts';

/**
 * Render chart-spec JSON mà bot chèn trong fenced block ```chart``` (tool
 * render_chart). Spec: {type: bar|rank|line|pie, title, labels[], series[{name,data[]}]}.
 * Spec hỏng → im lặng bỏ qua (bot vẫn có phần chữ).
 */

export type ChartSpec = {
  type: 'bar' | 'rank' | 'line' | 'pie';
  title?: string;
  labels: string[];
  series: { name?: string; data: number[] }[];
};

export function parseChartBlocks(text: string): (string | ChartSpec)[] {
  const parts: (string | ChartSpec)[] = [];
  const re = /```chart\n([\s\S]*?)```/g;
  let last = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    try {
      const spec = JSON.parse(m[1]) as ChartSpec;
      if (spec && Array.isArray(spec.labels) && Array.isArray(spec.series)) {
        parts.push(spec);
      }
    } catch {
      // spec hỏng → bỏ block, giữ phần chữ
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

const PALETTE = [
  'hsl(var(--primary))',
  'hsl(210 70% 55%)',
  'hsl(150 55% 45%)',
];

function LineChart({ spec }: { spec: ChartSpec }) {
  const W = 320, H = 130, PAD = 6;
  const all = spec.series.flatMap((s) => s.data);
  const max = Math.max(1, ...all);
  const step = spec.labels.length > 1 ? (W - PAD * 2) / (spec.labels.length - 1) : 0;
  const y = (v: number) => H - PAD - (v / max) * (H - PAD * 2);
  const lblStep = Math.max(1, Math.ceil(spec.labels.length / 6));
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {spec.series.map((s, si) => (
          <polyline
            key={si}
            fill="none"
            stroke={PALETTE[si % PALETTE.length]}
            strokeWidth="2"
            points={s.data.map((v, i) => `${PAD + i * step},${y(v)}`).join(' ')}
          />
        ))}
      </svg>
      <div className="flex justify-between text-[9px] text-[hsl(var(--dim))]">
        {spec.labels.map((l, i) => (
          <span key={i}>{i % lblStep === 0 ? l : ''}</span>
        ))}
      </div>
      {spec.series.length > 1 && (
        <div className="mt-1 flex gap-3 text-[10px] text-muted-foreground">
          {spec.series.map((s, si) => (
            <span key={si} className="inline-flex items-center gap-1">
              <i className="h-2 w-2 rounded-full" style={{ background: PALETTE[si % PALETTE.length] }} />
              {s.name || `Dãy ${si + 1}`}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function PieChart({ spec }: { spec: ChartSpec }) {
  const data = spec.series[0]?.data ?? [];
  const total = data.reduce((a, b) => a + b, 0) || 1;
  let acc = 0;
  const R = 46, C = 2 * Math.PI * R;
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 120 120" className="h-28 w-28 -rotate-90 shrink-0">
        {data.map((v, i) => {
          const frac = v / total;
          const el = (
            <circle
              key={i}
              cx="60" cy="60" r={R} fill="none"
              stroke={PALETTE[i % PALETTE.length]}
              strokeOpacity={1 - Math.floor(i / PALETTE.length) * 0.35}
              strokeWidth="22"
              strokeDasharray={`${frac * C} ${C}`}
              strokeDashoffset={-acc * C}
            />
          );
          acc += frac;
          return el;
        })}
      </svg>
      <div className="flex flex-col gap-1 text-[11px]">
        {spec.labels.map((l, i) => (
          <span key={i} className="inline-flex items-center gap-1.5">
            <i
              className="h-2 w-2 rounded-full shrink-0"
              style={{
                background: PALETTE[i % PALETTE.length],
                opacity: 1 - Math.floor(i / PALETTE.length) * 0.35,
              }}
            />
            <span className="text-muted-foreground">{l}</span>
            <span className="tabular-nums font-medium">
              {Math.round(((spec.series[0].data[i] ?? 0) / total) * 100)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

export function ChatChart({ spec }: { spec: ChartSpec }) {
  const s0 = spec.series[0] ?? { data: [] };
  return (
    <div className="my-2 rounded-lg border bg-background/60 p-3">
      {spec.title && <p className="mb-2 text-xs font-medium">{spec.title}</p>}
      {spec.type === 'rank' ? (
        <RankBars
          data={spec.labels.map((l, i) => ({
            label: l,
            value: s0.data[i] ?? 0,
            display: String(s0.data[i] ?? 0),
          }))}
        />
      ) : spec.type === 'line' ? (
        <LineChart spec={spec} />
      ) : spec.type === 'pie' ? (
        <PieChart spec={spec} />
      ) : (
        <BarChart
          data={spec.labels.map((l, i) => ({ label: l, value: s0.data[i] ?? 0 }))}
        />
      )}
    </div>
  );
}
