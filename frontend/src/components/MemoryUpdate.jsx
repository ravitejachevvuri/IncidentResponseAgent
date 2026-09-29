export default function MemoryUpdate({ lessons }) {
  if (!lessons || lessons.length === 0) return null;
  return (
    <section className="card memory-update">
      <h2>Memory Update</h2>
      <p className="muted">New organizational experience written back into incident memory:</p>
      <ul>
        {lessons.map((l) => (
          <li key={l.id}>{l.lesson_text}</li>
        ))}
      </ul>
    </section>
  );
}
