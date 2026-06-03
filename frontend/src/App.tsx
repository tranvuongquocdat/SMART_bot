export default function App() {
  return (
    <div className="min-h-screen flex items-center justify-center text-foreground">
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">SMART_bot</h1>
        <p className="text-muted-foreground mt-2">Frontend foundation OK ✓</p>
        <button
          className="mt-4 px-3 py-2 rounded-md bg-primary text-primary-foreground text-sm"
          onClick={() => document.documentElement.classList.toggle('light')}
        >
          Toggle theme
        </button>
      </div>
    </div>
  );
}
