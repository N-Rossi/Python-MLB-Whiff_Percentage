import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
} from "recharts";

export default function PitcherScatter({
  data,
  xField,
  yField,
  sizeField,
  xLabel,
  yLabel,
  sizeLabel,
}) {
  if (data.length === 0) {
    return (
      <div className="caption">Not enough data to plot at current settings.</div>
    );
  }
  const sizes = data.map((d) => d[sizeField]).filter((v) => v != null);
  const maxSize = sizes.length ? Math.max(...sizes) : 1;

  return (
    <div className="card">
      <ResponsiveContainer width="100%" height={420}>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 32, left: 16 }}>
          <CartesianGrid stroke="#2a3344" />
          <XAxis
            type="number"
            dataKey={xField}
            name={xLabel}
            stroke="#8b949e"
            fontSize={11}
            domain={["dataMin", "dataMax"]}
            label={{
              value: xLabel,
              position: "bottom",
              offset: 0,
              fill: "#8b949e",
            }}
          />
          <YAxis
            type="number"
            dataKey={yField}
            name={yLabel}
            stroke="#8b949e"
            fontSize={11}
            domain={["dataMin - 2", "dataMax + 2"]}
            label={{
              value: yLabel,
              angle: -90,
              position: "insideLeft",
              fill: "#8b949e",
            }}
          />
          <ZAxis
            type="number"
            dataKey={sizeField}
            range={[40, 500]}
            domain={[0, maxSize]}
            name={sizeLabel}
          />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            contentStyle={{
              background: "#161b22",
              border: "1px solid #2a3344",
            }}
            content={({ active, payload }) => {
              if (!active || !payload || !payload.length) return null;
              const d = payload[0].payload;
              return (
                <div
                  style={{
                    background: "#161b22",
                    border: "1px solid #2a3344",
                    padding: "6px 10px",
                    fontSize: 12,
                  }}
                >
                  <div>
                    <strong>{d.Pitcher}</strong>
                    {d.Division ? ` — ${d.Division}` : ""}
                  </div>
                  <div>
                    {xLabel}: {d[xField]?.toFixed?.(1) ?? d[xField]}
                  </div>
                  <div>Whiff %: {d["Whiff rate"] ?? "n/a"}</div>
                  <div>CSW %: {d["CSW %"] ?? "n/a"}</div>
                  <div>
                    Pitches {d.Pitches} · Swings {d.Swings} · Whiffs {d.Whiffs}{" "}
                    · Called {d.Called}
                  </div>
                </div>
              );
            }}
          />
          <Scatter data={data} fill="#4f8cff" fillOpacity={0.75} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
