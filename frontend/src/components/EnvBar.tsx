// Omgevingsindicator (#145): een dunne gekleurde balk bovenaan voor niet-PROD
// omgevingen. De kleur komt build-time uit NEXT_PUBLIC_ENV_COLOR (per omgeving
// gezet via de compose-build-args). Op PROD is die leeg → geen balk.
const ENV_COLOR = process.env.NEXT_PUBLIC_ENV_COLOR || "";
const APP_ENV = (process.env.NEXT_PUBLIC_APP_ENV || "").toUpperCase();

export default function EnvBar() {
  if (!ENV_COLOR) return null;
  return (
    <div
      className="h-1.5 w-full"
      style={{ backgroundColor: ENV_COLOR }}
      title={`Omgeving: ${APP_ENV}`}
      aria-hidden="true"
    />
  );
}
