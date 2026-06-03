export default function RootError() {
  return (
    <div className="min-h-screen grid place-items-center p-8">
      <div className="text-center max-w-sm">
        <h1 className="text-xl font-semibold mb-2">Có lỗi xảy ra</h1>
        <p className="text-muted-foreground text-sm mb-4">
          Không tải được trang. Thử reload, hoặc đăng nhập lại.
        </p>
        <button
          onClick={() => window.location.reload()}
          className="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm"
        >
          Reload
        </button>
      </div>
    </div>
  );
}
