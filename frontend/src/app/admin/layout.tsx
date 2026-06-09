"use client";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";

const navItems = [
  { href: "/admin", label: "Dashboard" },
  { href: "/admin/activiteiten", label: "Activiteiten" },
  { href: "/admin/leden", label: "Leden" },
  { href: "/admin/paginas", label: "CMS Pagina's" },
  { href: "/admin/ideeen", label: "Ideeën" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (pathname === "/admin/login") return;
    const token = localStorage.getItem("admin_token");
    if (!token) router.push("/admin/login");
  }, [pathname, router]);

  if (pathname === "/admin/login") return <>{children}</>;

  function logout() {
    localStorage.removeItem("admin_token");
    router.push("/admin/login");
  }

  return (
    <div className="flex flex-col md:flex-row gap-6 -mt-8">
      <aside className="md:w-52 shrink-0">
        <div className="card p-4">
          <div className="flex items-center justify-between mb-4">
            <span className="font-bold text-blue-800">Admin</span>
            <button onClick={logout} className="text-sm text-red-600 hover:underline">Uitloggen</button>
          </div>
          <nav className="space-y-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`block px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  pathname === item.href
                    ? "bg-blue-700 text-white"
                    : "text-gray-700 hover:bg-gray-100"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </aside>
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  );
}
