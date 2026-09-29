export default function Timeline({ events }) {
  if (!events || events.length === 0) return null;
  return (
    <section className="card">
      <h2>Timeline</h2>
      <ol className="timeline">
        {events.map((event, i) => (
          <li key={i}>
            <span className="timeline-label">{event.label}</span>
            <span className="timeline-time">
              {event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : ""}
            </span>
            <span className="timeline-detail">{event.detail}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
