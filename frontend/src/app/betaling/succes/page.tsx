import Link from "next/link";

export default function BetalingSucces() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-sm border border-gray-200 p-8 text-center">
        <div className="text-5xl mb-4">✅</div>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Betaling ontvangen!</h1>
        <p className="text-gray-600 mb-6">
          Bedankt! Je inschrijving bij Raak Millegem is bevestigd. Je ontvangt een bevestiging per e-mail.
        </p>
        <Link href="/" className="btn-primary">
          Terug naar de startpagina
        </Link>
      </div>
    </main>
  );
}
