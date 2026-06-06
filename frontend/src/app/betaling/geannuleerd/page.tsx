import Link from "next/link";

export default function BetalingGeannuleerd() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-sm border border-gray-200 p-8 text-center">
        <div className="text-5xl mb-4">❌</div>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Betaling geannuleerd</h1>
        <p className="text-gray-600 mb-6">
          Je betaling werd geannuleerd. Je registratie is bewaard — je kan de betaling later voltooien via een bestuurslid.
        </p>
        <Link href="/word-lid" className="btn-primary">
          Opnieuw proberen
        </Link>
      </div>
    </main>
  );
}
