export default function ErrorBox({ message }) {
  if (!message) return null;
  return (
    <div className="notice critical" role="alert">
      <span aria-hidden="true">✕</span> {message}
    </div>
  );
}
