export default function Metric({ label, value, help }) {
  return (
    <div className="metric" title={help || ""}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {help && <div className="help">{help}</div>}
    </div>
  );
}
