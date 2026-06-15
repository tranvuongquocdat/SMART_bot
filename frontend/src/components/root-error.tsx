import { useT } from '@/lib/i18n';

export default function RootError() {
  const t = useT();
  return (
    <div className="min-h-screen grid place-items-center p-8">
      <div className="text-center max-w-sm">
        <h1 className="text-xl font-semibold mb-2">{t('common.errorTitle')}</h1>
        <p className="text-muted-foreground text-sm mb-4">
          {t('common.errorDesc')}
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
