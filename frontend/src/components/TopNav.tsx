"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearSession, UserInfo } from "@/lib/api";

export default function TopNav({ user }: { user: UserInfo | null }) {
  const pathname = usePathname();
  const router = useRouter();

  const navLinks = [
    { href: "/chat", label: "Workspace" },
    { href: "/documents", label: "Documents" },
    { href: "/dashboard", label: "FinOps & Logs" },
  ];

  function handleLogout() {
    clearSession();
    router.push("/");
  }

  return (
    <header className="border-b border-white/10 bg-[#151619]">
      <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link href="/chat" className="flex items-center gap-2.5 font-semibold tracking-tight text-base text-white">
            <span className="inline-flex w-5 h-5 bg-[#C6F432] text-[#151619] font-mono text-xs items-center justify-center font-bold">
              V
            </span>
            <span>VEILGUARD</span>
          </Link>

          <nav className="flex items-center gap-1">
            {navLinks.map((link) => {
              const active = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider transition-colors ${
                    active
                      ? "bg-[#C6F432] text-[#151619] font-semibold"
                      : "text-white/65 hover:text-white"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {user && (
            <div className="flex items-center gap-2 font-mono text-xs">
              <span className="text-white/65 hidden sm:inline">{user.full_name}</span>
              <span className="px-2 py-0.5 bg-white text-[#151619] font-semibold">
                {user.role}
              </span>
            </div>
          )}
          <button
            onClick={handleLogout}
            className="text-xs font-mono uppercase tracking-wider border border-white/20 text-white px-2.5 py-1 hover:border-[#C6F432] cursor-pointer"
          >
            Switch Role
          </button>
        </div>
      </div>
    </header>
  );
}