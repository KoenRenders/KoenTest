// Omgevingsindicator (#145): een dunne gekleurde balk bovenaan voor niet-PROD
// omgevingen. De kleur komt build-time uit NEXT_PUBLIC_ENV_COLOR (per omgeving
// gezet via de compose-build-args). Op PROD is die leeg → geen balk.
const ENV_COLOR = process.env.NEXT_PUBLIC_ENV_COLOR || "";
const APP_ENV = (process.env.NEXT_PUBLIC_APP_ENV || "").toUpperCase();

export default function EnvBar() {
  if (!ENV_COLOR) return null;
  // Sticky volle balk: blijft bij het scrollen altijd bovenaan zichtbaar en
  // toont de omgevingsnaam. Op PROD is ENV_COLOR leeg → geen balk.
  return (
    <div
      className="sticky top-0 z-50 flex h-7 items-center justify-center text-xs font-bold uppercase tracking-widest text-white"
      style={{ backgroundColor: ENV_COLOR }}
      title={`Omgeving: ${APP_ENV}`}
    >
      {APP_ENV}
    </div>
  );
}
