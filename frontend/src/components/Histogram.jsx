import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

function bin(values, maxBins = 20) {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return [{ range: min.toFixed(1), count: values.length }];
  const width = (max - min) / maxBins;
  const bins = Array.from({ length: maxBins }, (_, i) => ({
    start: min + i * width,
    end: min + (i + 1) * width,
    count: 0,
  }));
  for (const v of values) {
    let idx = Math.floor((v - min) / width);
    if (idx >= maxBins) idx = maxBins - 1;
    bins[idx].count += 1;
  }
  return bins.map((b) => ({
    range: `${b.start.toFixed(1)}`,
    count: b.count,
    label: `${b.start.toFixed(1)}–${b.end.toFixed(1)}`,
  }));
}

export default function Histogram({ title, unit, values }) {
  const data = bin(values);
  if (data.length === 0) return null;
  return (
    <div className="card">
      <h3>
        {title} ({unit})
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="#2a3344" />
          <XAxis dataKey="range" stroke="#8b949e" fontSize={11} />
          <YAxis stroke="#8b949e" fontSize={11} />
          <Tooltip
            contentStyle={{
              background: "#161b22",
              border: "1px solid #2a3344",
            }}
            formatter={(v) => [v, "Pitchers"]}
            labelFormatter={(_, p) => p?.[0]?.payload?.label || ""}
          />
          <Bar dataKey="count" fill="#4f8cff" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
